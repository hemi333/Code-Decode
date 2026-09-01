"""분석기 테스트.

여기서 고정하는 것은 '무엇이 해석되는가'와 '무엇이 해석되지 않는가' 둘 다다.
해석 실패도 명세다. 실패할 때 단서를 남기지 않으면 LLM 이 추측하게 되고,
추측한 설명은 이 도구가 가장 피하려는 결과다.

    pytest tests/          또는          python tests/test_analyzer.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from decoder.analyzer import analyze_code  # noqa: E402
from decoder.docs import lookup_documentation  # noqa: E402


def _symbols(code: str) -> dict[str, dict]:
    return {s["source"]: s for s in analyze_code(code)["symbols"]}


# ── 해석되어야 하는 것 ──────────────────────────────────────────────────────


def test_from_import_resolves():
    s = _symbols("from pathlib import Path\np = Path('.')\n")
    assert s["Path"]["qualname"] == "pathlib.Path"
    assert s["Path"]["resolution"] == "import"


def test_aliased_module_resolves():
    s = _symbols("import pandas as pd\ndf = pd.read_csv('a.csv')\n")
    assert s["pd.read_csv"]["qualname"] == "pandas.read_csv"


def test_class_instance_binding():
    """핵심 케이스. 변수에 담긴 클래스 인스턴스의 메서드를 추적한다."""
    s = _symbols("from pathlib import Path\nD = Path('./x')\nfiles = D.glob('*.png')\n")
    assert s["D.glob"]["qualname"] == "pathlib.Path.glob"
    assert s["D.glob"]["resolution"] == "binding"


def test_return_annotation_binding():
    """정적으로는 모르지만 런타임 어노테이션으로 알 수 있는 경우."""
    s = _symbols("import pandas as pd\ndf = pd.read_csv('a.csv')\ng = df.groupby('x')\n")
    assert s["df.groupby"]["qualname"] == "pandas.DataFrame.groupby"


def test_literal_binding():
    s = _symbols("out = []\nout.append(1)\n")
    assert s["out.append"]["qualname"] == "list.append"


def test_builtin():
    s = _symbols("x = sorted([3, 1])\n")
    assert s["sorted"]["resolution"] == "builtin"


def test_decorator():
    s = _symbols("import functools\n\n@functools.lru_cache(maxsize=None)\ndef f(n): return n\n")
    assert s["functools.lru_cache"]["kind"] == "decorator"
    assert s["functools.lru_cache"]["qualname"] == "functools.lru_cache"


def test_await_unwrapping():
    code = "import httpx\nasync def f(u):\n    c = httpx.AsyncClient()\n    r = await c.get(u)\n    return r.json()\n"
    s = _symbols(code)
    # httpx 미설치 환경에서도 origin 단서는 남아야 한다.
    assert s["r.json"]["receiver_origin"] is not None


# ── 해석되지 않아야 하는 것 ────────────────────────────────────────────────


def test_bare_snippet_fails_with_clue():
    """컨텍스트 없는 스니펫. 실패하되 이유를 남긴다."""
    s = _symbols('sorted(GEN_IMAGES_DIR.glob("*.png"))')
    entry = s["GEN_IMAGES_DIR.glob"]
    assert entry["qualname"] is None
    assert entry["resolution"] == "unresolved"
    assert "GEN_IMAGES_DIR" in entry["receiver_origin"]


def test_function_return_without_annotation_leaves_origin():
    code = "def make():\n    return 1\nx = make()\ny = x.bit_length()\n"
    s = _symbols(code)
    assert s["x.bit_length"]["qualname"] is None
    assert "make" in (s["x.bit_length"]["receiver_origin"] or "")


# ── 문법 요소 ───────────────────────────────────────────────────────────────


def test_syntax_features():
    code = "async def f():\n    async with open('x') as fh:\n        return [c for c in fh]\n"
    features = {f["feature"] for f in analyze_code(code)["syntax"]}
    assert {"AsyncFunctionDef", "AsyncWith", "ListComp"} <= features


def test_syntax_error_is_reported():
    result = analyze_code("def broken(:\n")
    assert result["error"] is not None


# ── 문서 조회 ───────────────────────────────────────────────────────────────


def test_stdlib_doc():
    r = lookup_documentation("pathlib.Path.glob")
    assert r["found"] and r["doc"] and "docs.python.org" in r["doc_url"]


def test_disallowed_root_is_refused():
    r = lookup_documentation("somerandompkg.thing")
    assert not r["found"] and "허용 목록" in r["note"]


def test_truncation_is_flagged():
    r = lookup_documentation("functools.lru_cache", max_chars=40)
    assert r["truncated"] and len(r["doc"]) < 120


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            passed += 1
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {name}  {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ERR   {name}  {type(exc).__name__}: {exc}")
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
