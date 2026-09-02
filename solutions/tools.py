"""도구 모음 · 정답.

먼저 직접 해보고 여세요.

원본:

1주차에는 도구가 하나였습니다. 이번 주는 셋입니다.
셋이 되면 새로운 일들이 생깁니다.

    · 모델이 한 응답에서 도구를 여러 개 부를 수 있다      → 병렬
    · 한 도구의 결과가 다음 도구의 인자가 된다            → 연쇄
    · 도구가 실패할 수 있고, 모델이 그걸 읽고 대응해야 한다 → 실패

이번 주 시나리오는 이겁니다.

    "fixtures 폴더에서 가장 긴 파이썬 파일이 뭐야?"

    list_files("*.py")            ← 무엇이 있는지 모른다. 먼저 물어봐야 한다.
        ↓
    read_file(...) × 3            ← 한 번에 여러 개. 병렬.
        ↓
    count_lines(...) × 3          ← 또 병렬.
        ↓
    답

도구 하나로는 볼 수 없던 것들이 여기서 다 나옵니다.
"""

from __future__ import annotations

from pathlib import Path

# 도구가 접근할 수 있는 유일한 디렉터리.
# 왜 이런 게 필요한지는 read_file 의 주석에 있습니다.
SANDBOX = Path(__file__).resolve().parent.parent / "fixtures"


# ===========================================================================
# 도구 1 · count_lines   (1주차에서 그대로 가져왔습니다)
# ===========================================================================

COUNT_LINES_TOOL = {
    "name": "count_lines",
    "description": (
        "파이썬 코드 문자열을 받아 줄 수를 센다. "
        "전체 줄 수와, 빈 줄과 주석을 제외한 실제 코드 줄 수를 함께 반환한다. "
        "코드의 길이를 물으면 눈으로 세거나 추측하지 말고 이 도구를 부른다."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "줄 수를 셀 파이썬 코드 전문"}
        },
        "required": ["code"],
    },
}


def count_lines(code: str) -> dict:
    text = code.rstrip("\n")
    lines = text.split("\n") if text else []
    code_lines = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    return {"total": len(lines), "code": len(code_lines)}


# ===========================================================================
# 도구 2 · list_files   ← 빈칸 1
# ===========================================================================

LIST_FILES_TOOL = {
    "name": "list_files",
    "description": (
        "작업 디렉터리 안의 파일 목록을 반환한다. "
        "어떤 파일이 있는지는 이 도구로만 알 수 있으므로, "
        "파일에 대해 무언가 하기 전에 먼저 이것을 불러 존재를 확인한다. "
        "파일 이름을 추측해서 read_file 을 부르지 않는다."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": (
                    "glob 패턴. 예: '*.py' 는 파이썬 파일만. "
                    "생략하면 '*' 로 전체를 반환한다."
                ),
            }
        },
        "required": [],
    },
}


def list_files(pattern: str = "*") -> dict:
    """SANDBOX 안에서 패턴에 맞는 파일 이름을 돌려준다.

    반환 형태 (이대로 맞춰주세요):
        {"files": ["a.py", "b.py"], "count": 2}

    힌트:
        - Path.glob() 은 Path 객체를 내놓습니다. 이름만 필요합니다.
        - 순서를 고정하세요. 실행할 때마다 순서가 달라지면
          같은 질문에 다른 답이 나옵니다. (1주차 CHECKPOINT D13 을 떠올려보세요)
    """
    names = sorted(p.name for p in SANDBOX.glob(pattern) if p.is_file())
    return {"files": names, "count": len(names)}


# ===========================================================================
# 도구 3 · read_file   ← 빈칸 2
# ===========================================================================

READ_FILE_TOOL = {
    "name": "read_file",
    "description": (
        "지정한 파일의 내용을 문자열로 읽어 반환한다. "
        "파일 이름은 list_files 가 돌려준 것 중에서 고른다. "
        "파일이 없으면 오류를 반환하므로, 존재를 추측하지 말고 먼저 list_files 를 부른다."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "읽을 파일 이름. 경로가 아니라 이름만. 예: resize.py",
            }
        },
        "required": ["name"],
    },
}


def read_file(name: str) -> dict:
    """SANDBOX 안의 파일 하나를 읽는다.

    반환 형태:
        성공  {"name": "resize.py", "content": "...", "bytes": 412}
        실패  {"error": "무슨 일이 있었는지"}

    ── 이 함수에서 진짜 배울 것 ──────────────────────────────────────────

    `name` 은 **모델이 만들어낸 값**입니다. 여러분이 넘긴 게 아닙니다.
    모델은 사용자 입력에 영향을 받고, 나중에는 인터넷에서 긁어온 문서에도
    영향을 받습니다. 그러니까 이 값은 신뢰할 수 없는 입력입니다.

    1주차 CHECKPOINT B6 에서 물었던 것과 같은 이야기입니다.
    도구 결과의 role 이 "user" 인 이유가 여기서 실감납니다.

    구현할 것:
        1. name 에 경로 구분자나 ".." 가 있으면 거절할 것
        2. 최종 경로가 정말 SANDBOX 안인지 확인할 것
           (1번만으로는 부족합니다. 왜 부족한지 생각해보세요.)
        3. 파일이 없으면 예외를 던지지 말고 {"error": ...} 를 돌려줄 것

    힌트:
        - Path.resolve() 는 심볼릭 링크와 .. 를 다 풀어줍니다.
        - Path.is_relative_to(other) 로 포함 관계를 볼 수 있습니다. (3.9+)
        - 거절할 때도 예외 대신 {"error": ...} 입니다.
          도구가 터지면 루프가 멈추고, 모델은 왜 실패했는지 모릅니다.
    """
    # 1) 눈에 보이는 거절. 이름만 받기로 했으니 경로 흔적이 있으면 안 된다.
    if "/" in name or "\\" in name or name.startswith(".."):
        return {"error": f"파일 이름만 넘기세요 (경로 불가): {name!r}"}

    # 2) 그래도 확인한다. 1)만으로 부족한 이유:
    #    심볼릭 링크가 있으면 이름에 아무 흔적이 없어도 밖을 가리킬 수 있다.
    #    "무엇을 막을지" 나열하는 대신 "무엇만 허용할지" 확인하는 쪽이 안전하다.
    target = (SANDBOX / name).resolve()
    if not target.is_relative_to(SANDBOX.resolve()):
        return {"error": f"작업 디렉터리 밖입니다: {name!r}"}

    if not target.exists():
        return {"error": f"파일이 없습니다: {name!r}. list_files 로 목록을 먼저 확인하세요."}
    if not target.is_file():
        return {"error": f"파일이 아닙니다: {name!r}"}

    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"error": f"텍스트 파일이 아닙니다: {name!r}"}

    return {"name": name, "content": content, "bytes": len(content.encode("utf-8"))}


# ===========================================================================
# 등록
# ===========================================================================

TOOLS = [COUNT_LINES_TOOL, LIST_FILES_TOOL, READ_FILE_TOOL]

_IMPL = {
    "count_lines": lambda p: count_lines(p["code"]),
    "list_files": lambda p: list_files(p.get("pattern", "*")),
    "read_file": lambda p: read_file(p["name"]),
}


def dispatch(name: str, payload: dict) -> dict:
    """도구 하나를 실행한다. 예외는 값으로 바꿔 돌려준다."""
    impl = _IMPL.get(name)
    if impl is None:
        return {"error": f"알 수 없는 도구: {name}"}
    try:
        return impl(payload)
    except KeyError as exc:
        return {"error": f"필수 인자가 없습니다: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


if __name__ == "__main__":
    print("list_files('*.py') →", dispatch("list_files", {"pattern": "*.py"}))
    print("read_file('tiny.py') →", dispatch("read_file", {"name": "tiny.py"}))
    print("read_file('../env.py') →", dispatch("read_file", {"name": "../env.py"}))
    print("read_file('없음.py') →", dispatch("read_file", {"name": "없음.py"}))
