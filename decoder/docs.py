"""공식 문서 조회.

커리큘럼 6~7주차에 해당한다. 두 단계로 나뉘는 이유는 난이도가 다르기 때문이다.

  6주차 · 표준 라이브러리
      importlib + inspect 로 로컬에서 끝난다. 네트워크가 필요 없다.
      docstring 이 곧 공식 문서이므로 출처가 명확하다.

  7주차 · 서드파티
      라이브러리마다 문서 구조가 달라 통합 API 가 없다.
      여기서는 '지원 대상을 좁힌다'는 선택을 했다. ALLOWED_THIRD_PARTY 에
      없는 패키지는 조회하지 않고 그 사실을 그대로 반환한다.

조회는 임포트를 수반한다 = 남의 코드가 실행된다. 그래서 allowlist 가 있다.
allowlist 를 지우고 아무거나 임포트하게 만들지 말 것.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from functools import lru_cache
from typing import Any

# ---------------------------------------------------------------------------
# 허용 목록
# ---------------------------------------------------------------------------

STDLIB_ROOTS: frozenset[str] = frozenset(sys.stdlib_module_names)

# 7주차에서 지원 대상으로 못 박은 서드파티. 늘리려면 여기에 추가한다.
ALLOWED_THIRD_PARTY: dict[str, str] = {
    "PIL": "https://pillow.readthedocs.io/en/stable/reference/",
    "httpx": "https://www.python-httpx.org/api/",
    "pandas": "https://pandas.pydata.org/docs/reference/api/",
    "numpy": "https://numpy.org/doc/stable/reference/generated/",
    "requests": "https://requests.readthedocs.io/en/latest/api/",
}

# 조회 결과에서 잘라낼 최대 길이. 비용에 직결된다.
# 문서 전문을 컨텍스트에 밀어넣으면 토큰이 훅 뛴다.
MAX_DOC_CHARS = 1400


def module_is_allowed(qualname: str) -> bool:
    import builtins

    root = qualname.split(".")[0]
    if root in STDLIB_ROOTS or root in ALLOWED_THIRD_PARTY:
        return True
    # sorted, len … 그리고 list.append, str.join 처럼 내장 타입에 뿌리를 둔 경로
    return hasattr(builtins, root)


# ---------------------------------------------------------------------------
# 심볼 해석
# ---------------------------------------------------------------------------


@lru_cache(maxsize=512)
def _import_root(name: str) -> Any | None:
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _resolve_object(qualname: str) -> tuple[Any | None, str | None]:
    """'pathlib.Path.glob' → 실제 객체. 실패하면 (None, 사유)."""
    if not module_is_allowed(qualname):
        root = qualname.split(".")[0]
        return None, f"'{root}' 는 조회 허용 목록에 없습니다. docs.ALLOWED_THIRD_PARTY 에 추가하세요."

    parts: list[str] = qualname.split(".")

    # 내장 이름에 뿌리를 둔 경로: sorted, list.append, str.join …
    import builtins

    if hasattr(builtins, parts[0]):
        obj: Any = getattr(builtins, parts[0])
        try:
            for attr in parts[1:]:
                obj = getattr(obj, attr)
        except AttributeError:
            return None, f"내장 '{parts[0]}' 에 '{'.'.join(parts[1:])}' 가 없습니다."
        return obj, None

    # 가장 긴 것부터 모듈로 임포트를 시도하고, 나머지는 getattr 로 내려간다.
    for split in range(len(parts), 0, -1):
        module_path = ".".join(parts[:split])
        module = _import_root(module_path)
        if module is None:
            continue
        obj: Any = module
        try:
            for attr in parts[split:]:
                obj = getattr(obj, attr)
        except AttributeError:
            return None, f"'{module_path}' 안에 '{'.'.join(parts[split:])}' 가 없습니다."
        return obj, None

    # 내장 함수
    import builtins

    if len(parts) == 1 and hasattr(builtins, parts[0]):
        return getattr(builtins, parts[0]), None

    return None, f"'{qualname}' 를 임포트할 수 없습니다."


def is_class(qualname: str) -> bool:
    """호출 대상이 클래스인지. analyzer 의 바인딩 추적이 이걸 쓴다."""
    obj, _ = _resolve_object(qualname)
    return obj is not None and inspect.isclass(obj)


@lru_cache(maxsize=256)
def return_type_of(qualname: str) -> str | None:
    """함수의 반환 타입을 런타임 어노테이션으로 추론한다.

    AST 만으로는 df = pd.read_csv(...) 의 df 가 무엇인지 알 수 없다.
    실제 객체를 들여다보면 알 수 있는 경우가 있다 — 정적 분석의 한계를
    런타임 정보로 메우는, 5주차에서 고른 (b)+(c) 혼합 전략이다.

    어노테이션이 없거나 문자열을 해석하지 못하면 None. 추측하지 않는다.
    """
    obj, _ = _resolve_object(qualname)
    if obj is None or not callable(obj):
        return None

    try:
        annotation: Any = inspect.signature(obj).return_annotation
    except (TypeError, ValueError):
        return None
    if annotation is inspect.Signature.empty:
        return None

    # from __future__ import annotations 환경에서는 문자열로 들어온다.
    if isinstance(annotation, str):
        head = annotation.split("|")[0].strip().split("[")[0].strip()
        if not head or head in {"None", "Any"}:
            return None
        annotation = _lookup_in_module(obj, head)
        if annotation is None:
            return None

    if inspect.isclass(annotation):
        resolved = f"{annotation.__module__}.{annotation.__qualname__}"
        return resolved if module_is_allowed(resolved) else None
    return None


def _lookup_in_module(fn: Any, dotted: str) -> Any | None:
    """정의된 모듈의 네임스페이스에서 'ImageFile.ImageFile' 같은 이름을 찾는다."""
    module = inspect.getmodule(fn)
    if module is None:
        return None
    current: Any = module
    for part in dotted.split("."):
        nxt = getattr(current, part, None)
        if nxt is None:
            package = getattr(current, "__package__", None)
            if package:
                nxt = _import_root(f"{package}.{part}")
        if nxt is None:
            return None
        current = nxt
    return current


# ---------------------------------------------------------------------------
# 문서 URL
# ---------------------------------------------------------------------------


def _doc_url(qualname: str, obj: Any) -> str | None:
    import builtins

    root = qualname.split(".")[0]

    if hasattr(builtins, root):
        if "." not in qualname:
            return _builtin_doc_url(qualname)
        # list.append, str.join → 표준 타입 문서
        return f"https://docs.python.org/3/library/stdtypes.html#{qualname}"

    if root in STDLIB_ROOTS:
        anchor = qualname
        return f"https://docs.python.org/3/library/{root}.html#{anchor}"

    if root in ALLOWED_THIRD_PARTY:
        base = ALLOWED_THIRD_PARTY[root]
        if root == "pandas":
            return f"{base}{qualname}.html"
        if root == "numpy":
            return f"{base}{qualname}.html"
        return base

    return None


def _builtin_doc_url(name: str) -> str:
    return f"https://docs.python.org/3/library/functions.html#{name}"


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------


def lookup_documentation(qualname: str, max_chars: int = MAX_DOC_CHARS) -> dict[str, Any]:
    """심볼 하나의 공식 문서를 가져온다. Tool Calling 진입점.

    반환 형태는 항상 동일하다. 실패해도 예외를 던지지 않고 found=False 로 답한다.
    에이전트 루프가 도구 실패로 멈추면 안 되기 때문이다.
    """
    result: dict[str, Any] = {
        "qualname": qualname,
        "found": False,
        "kind": None,
        "signature": None,
        "doc": None,
        "doc_url": None,
        "defined_in": None,
        "truncated": False,
        "note": None,
    }

    obj, reason = _resolve_object(qualname)
    if obj is None:
        result["note"] = reason
        return result

    result["found"] = True
    result["kind"] = _kind_of(obj)

    # 시그니처
    try:
        result["signature"] = f"{qualname.split('.')[-1]}{inspect.signature(obj)}"
    except (TypeError, ValueError):
        result["signature"] = None

    # docstring — 이게 공식 문서다
    doc = inspect.getdoc(obj)
    if doc:
        if len(doc) > max_chars:
            doc = doc[:max_chars].rstrip() + "\n… (이하 생략)"
            result["truncated"] = True
        result["doc"] = doc

    # 정의 위치
    try:
        module = inspect.getmodule(obj)
        if module is not None:
            result["defined_in"] = getattr(module, "__name__", None)
    except Exception:
        pass

    import builtins

    if getattr(builtins, qualname, None) is obj:
        result["doc_url"] = _builtin_doc_url(qualname)
    else:
        result["doc_url"] = _doc_url(qualname, obj)

    if result["doc"] is None:
        result["note"] = "docstring 이 없습니다. 문서 URL 을 직접 확인해야 합니다."

    return result


def lookup_many(qualnames: list[str], max_chars: int = MAX_DOC_CHARS) -> dict[str, Any]:
    """여러 심볼을 한 번에. 왕복 횟수를 줄여 비용을 아낀다."""
    seen: list[str] = []
    for name in qualnames:
        if name not in seen:
            seen.append(name)
    return {"results": [lookup_documentation(n, max_chars) for n in seen]}


def _kind_of(obj: Any) -> str:
    if inspect.isclass(obj):
        return "class"
    if inspect.ismodule(obj):
        return "module"
    if inspect.iscoroutinefunction(obj):
        return "coroutine function"
    if inspect.isgeneratorfunction(obj):
        return "generator function"
    if inspect.isfunction(obj) or inspect.isbuiltin(obj):
        return "function"
    if inspect.ismethod(obj) or inspect.ismethoddescriptor(obj):
        return "method"
    if isinstance(obj, property):
        return "property"
    return type(obj).__name__


__all__ = [
    "lookup_documentation",
    "lookup_many",
    "is_class",
    "module_is_allowed",
    "ALLOWED_THIRD_PARTY",
    "STDLIB_ROOTS",
]
