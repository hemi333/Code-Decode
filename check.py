#!/usr/bin/env python3
"""채점기.

    python check.py 3     # 3단계 도구 정의
    python check.py 4     # 4단계 루프
    python check.py       # 둘 다

API 키가 없어도 돌아갑니다. 가짜 클라이언트가 실제 API 와 같은 형식 검사를
하기 때문입니다. 틀리면 어느 빈칸이 문제인지 알려줍니다.

통과했다고 이해한 건 아닙니다. CHECKPOINT.md 의 질문에 답할 수 있어야
이번 주가 끝난 것입니다.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from _fake.client import FakeAnthropic, ProtocolError  # noqa: E402

GREEN, RED, GREY, RESET = "\033[32m", "\033[31m", "\033[90m", "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}통과{RESET}  {msg}")


def fail(msg: str, detail: str = "") -> None:
    print(f"  {RED}실패{RESET}  {msg}")
    if detail:
        print(f"        {GREY}{detail}{RESET}")


# ---------------------------------------------------------------------------
# 3단계
# ---------------------------------------------------------------------------


def check_step3() -> bool:
    print("\n3단계 · 도구 정의")
    print("─" * 62)

    try:
        import step3_tool
    except Exception as exc:  # noqa: BLE001
        fail("step3_tool.py 를 불러올 수 없습니다", f"{type(exc).__name__}: {exc}")
        return False

    passed = True
    tool = getattr(step3_tool, "COUNT_LINES_TOOL", {})

    # 스키마
    desc = tool.get("description", "")
    if len(desc.strip()) < 20:
        fail("description 이 비어 있거나 너무 짧습니다", "모델은 이 문장만 보고 부를지 정합니다")
        passed = False
    else:
        ok(f"description ({len(desc)}자)")

    props = tool.get("input_schema", {}).get("properties", {})
    if "code" not in props:
        fail("input_schema 에 code 파라미터가 없습니다")
        passed = False
    elif props["code"].get("type") != "string":
        fail("code 의 type 이 string 이 아닙니다")
        passed = False
    elif not props["code"].get("description"):
        fail("code 에 description 이 없습니다", "설명 없는 파라미터에는 엉뚱한 값이 들어옵니다")
        passed = False
    else:
        ok("input_schema.properties.code")

    if "code" not in tool.get("input_schema", {}).get("required", []):
        fail("code 가 required 에 없습니다")
        passed = False
    else:
        ok("required")

    # 구현
    cases = [
        ("import os\n\n# 주석\nprint(1)\n", 4, 2),
        ("x = 1", 1, 1),
        ("", 0, 0),
        ("\n\n\n", 0, 0),
        ("# 주석만\n# 또 주석\n", 2, 0),
    ]

    for code, want_total, want_code in cases:
        try:
            got = step3_tool.count_lines(code)
        except NotImplementedError:
            fail("count_lines 가 아직 구현되지 않았습니다")
            return False
        except Exception as exc:  # noqa: BLE001
            fail(f"count_lines({code!r}) 에서 예외", f"{type(exc).__name__}: {exc}")
            passed = False
            continue

        if not isinstance(got, dict) or "total" not in got or "code" not in got:
            fail(f"반환 형태가 다릅니다: {got!r}", '{"total": int, "code": int} 여야 합니다')
            passed = False
        elif got["total"] != want_total or got["code"] != want_code:
            fail(
                f"count_lines({code!r})",
                f"기대 total={want_total}, code={want_code} / 받음 {got}",
            )
            passed = False
        else:
            ok(f"count_lines({code!r:28s}) → {got}")

    # 예외를 값으로 돌려주는지
    result = step3_tool.dispatch("count_lines", {})
    if not isinstance(result, dict) or "error" not in result:
        fail("인자가 빠졌을 때 dispatch 가 error 를 돌려주지 않습니다", "도구가 터지면 루프가 멈춥니다")
        passed = False
    else:
        ok("도구 실패를 값으로 반환")

    return passed


# ---------------------------------------------------------------------------
# 4단계
# ---------------------------------------------------------------------------


def check_step4() -> bool:
    print("\n4단계 · 에이전트 루프")
    print("─" * 62)

    # anthropic 자리에 가짜를 끼워넣는다
    fake_module = types.ModuleType("anthropic")
    fake_module.Anthropic = FakeAnthropic  # type: ignore[attr-defined]
    sys.modules["anthropic"] = fake_module
    import os

    os.environ.setdefault("ANTHROPIC_API_KEY", "fake-key-for-check")

    for name in ("step4_loop", "step3_tool"):
        sys.modules.pop(name, None)

    try:
        import step4_loop
    except Exception as exc:  # noqa: BLE001
        fail("step4_loop.py 를 불러올 수 없습니다", f"{type(exc).__name__}: {exc}")
        return False

    try:
        answer = step4_loop.run("이 코드 몇 줄이야?", verbose=False)
    except ProtocolError as exc:
        fail("대화 형식이 API 규칙에 어긋납니다")
        for line in str(exc).splitlines():
            print(f"        {GREY}{line}{RESET}")
        return False
    except NotImplementedError:
        fail("아직 구현되지 않은 부분이 있습니다")
        return False
    except Exception as exc:  # noqa: BLE001
        fail("루프 실행 중 예외", f"{type(exc).__name__}: {exc}")
        return False

    if not answer or not answer.strip():
        fail("최종 답이 비어 있습니다", "루프를 빠져나온 뒤 text 블록을 뽑았습니까? (빈칸 1)")
        return False

    if "MAX_TURNS" in answer:
        fail("루프가 끝나지 않았습니다", "종료 조건이 동작하지 않습니다 (빈칸 1)")
        return False

    if "4" not in answer or "2" not in answer:
        fail("도구 결과가 답에 반영되지 않았습니다", f"받은 답: {answer!r}")
        return False

    ok("모델 호출 → 도구 실행 → 결과 전달 → 최종 응답")
    ok(f"최종 답: {answer.strip()}")
    return True


# ---------------------------------------------------------------------------

def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"

    results = {}
    if which in ("3", "all"):
        results["3단계"] = check_step3()
    if which in ("4", "all"):
        results["4단계"] = check_step4()

    print("\n" + "═" * 62)
    for name, passed in results.items():
        mark = f"{GREEN}통과{RESET}" if passed else f"{RED}미완{RESET}"
        print(f"  {name}  {mark}")

    if all(results.values()):
        print(f"\n  루프가 돕니다. 이제 {GREY}CHECKPOINT.md{RESET} 의 질문에 답해보세요.")
        print("  코드가 도는 것과 이해한 것은 다릅니다.")
    print("═" * 62 + "\n")

    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
