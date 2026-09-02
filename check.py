#!/usr/bin/env python3
"""채점기 · 2주차.

    python check.py tools     # 도구 두 개
    python check.py agent     # 루프 확장
    python check.py           # 둘 다

API 키 없이 돌아갑니다.
통과했다고 이해한 건 아닙니다. CHECKPOINT.md 를 확인하세요.
"""

from __future__ import annotations

import os
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
    for line in detail.splitlines():
        if line.strip():
            print(f"        {GREY}{line.strip()}{RESET}")


# ---------------------------------------------------------------------------


def check_tools() -> bool:
    print("\n도구 · list_files / read_file")
    print("─" * 64)

    try:
        import tools
    except Exception as exc:  # noqa: BLE001
        fail("tools.py 를 불러올 수 없습니다", f"{type(exc).__name__}: {exc}")
        return False

    passed = True

    # -- 스키마 --
    schema = tools.LIST_FILES_TOOL
    if len(schema.get("description", "").strip()) < 20:
        fail("list_files 의 description 이 비었거나 짧습니다")
        passed = False
    elif "pattern" not in schema["input_schema"]["properties"]:
        fail("list_files 스키마에 pattern 이 없습니다")
        passed = False
    else:
        ok("list_files 스키마")

    # -- list_files --
    try:
        result = tools.dispatch("list_files", {"pattern": "*.py"})
    except NotImplementedError:
        fail("list_files 가 아직 구현되지 않았습니다")
        return False

    if not isinstance(result, dict) or "files" not in result or "count" not in result:
        fail(f"반환 형태가 다릅니다: {result!r}", '{"files": [...], "count": N} 이어야 합니다')
        passed = False
    elif result["files"] != sorted(result["files"]):
        fail("파일 목록이 정렬되지 않았습니다", "순서가 흔들리면 같은 질문에 다른 답이 나옵니다")
        passed = False
    elif "notes.txt" in result["files"]:
        fail("*.py 패턴인데 txt 가 섞였습니다")
        passed = False
    elif len(result["files"]) < 3:
        fail(f"파일이 {len(result['files'])}개만 잡힙니다", "fixtures 에 py 파일이 3개 있습니다")
        passed = False
    else:
        ok(f"list_files('*.py') → {result['files']}")

    # -- read_file 성공 --
    try:
        good = tools.dispatch("read_file", {"name": "tiny.py"})
    except NotImplementedError:
        fail("read_file 이 아직 구현되지 않았습니다")
        return False

    if "content" not in good:
        fail(f"read_file 성공 시 content 가 없습니다: {good!r}")
        passed = False
    else:
        ok("read_file('tiny.py')")

    # -- read_file 실패 경로 --
    cases = [
        ({"name": "없는파일.py"}, "없는 파일"),
        ({"name": "../agent.py"}, "상위 경로"),
        ({"name": "/etc/passwd"}, "절대 경로"),
        ({"name": "sub/../../agent.py"}, "우회 경로"),
    ]
    for payload, label in cases:
        got = tools.dispatch("read_file", payload)
        if not isinstance(got, dict) or "error" not in got:
            fail(f"{label} 을 막지 못했습니다: {payload['name']!r} → {got!r}")
            passed = False
        else:
            ok(f"{label} 거절 · {payload['name']!r}")

    # -- 심볼릭 링크 --
    link = tools.SANDBOX / "_check_link.py"
    try:
        link.symlink_to(ROOT / "agent.py")
        got = tools.dispatch("read_file", {"name": "_check_link.py"})
        if "error" not in got:
            fail(
                "심볼릭 링크로 샌드박스를 빠져나갔습니다",
                "이름에 경로 흔적이 없어도 밖을 가리킬 수 있습니다.\n"
                "resolve() 한 뒤 정말 안에 있는지 확인하세요.",
            )
            passed = False
        else:
            ok("심볼릭 링크 거절")
    except OSError:
        print(f"  {GREY}건너뜀{RESET}  심볼릭 링크 (이 환경에서 만들 수 없음)")
    finally:
        link.unlink(missing_ok=True)

    return passed


# ---------------------------------------------------------------------------


def _load_agent(scenario: str):
    fake = types.ModuleType("anthropic")
    fake.Anthropic = lambda *a, **kw: FakeAnthropic(scenario=scenario)  # type: ignore
    sys.modules["anthropic"] = fake
    os.environ.setdefault("ANTHROPIC_API_KEY", "fake")
    for name in ("agent", "tools"):
        sys.modules.pop(name, None)
    import agent

    return agent


def check_agent() -> bool:
    print("\n루프 · 병렬 / 실패 / 예산 / 세션")
    print("─" * 64)

    try:
        agent = _load_agent("main")
    except Exception as exc:  # noqa: BLE001
        fail("agent.py 를 불러올 수 없습니다", f"{type(exc).__name__}: {exc}")
        return False

    # -- 본 시나리오 --
    session = agent.Session()
    try:
        answer = session.ask("가장 긴 파이썬 파일이 뭐야?", verbose=False)
    except ProtocolError as exc:
        fail("대화 형식이 API 규칙에 어긋납니다", str(exc))
        return False
    except NotImplementedError:
        fail("아직 구현되지 않은 부분이 있습니다")
        return False
    except Exception as exc:  # noqa: BLE001
        fail("루프 실행 중 예외", f"{type(exc).__name__}: {exc}")
        return False

    if "MAX_TURNS" in answer:
        fail("루프가 끝나지 않았습니다")
        return False
    if not answer.strip():
        fail("최종 답이 비어 있습니다")
        return False

    ok("연쇄 호출 (list_files → read_file → count_lines)")
    ok("병렬 호출 (한 응답의 도구를 모두 처리)")
    ok("실패한 도구에 is_error 표시")
    ok(f"최종 답: {answer.strip()[:56]}…")

    # -- 세션 유지 --
    before = len(session.messages)
    try:
        session.ask("그럼 두 번째로 긴 건?", verbose=False)
    except ProtocolError:
        pass  # 가짜 시나리오가 끝났으므로 형식 오류는 여기선 무시
    except Exception:  # noqa: BLE001
        pass

    if len(session.messages) <= before:
        fail("두 번째 질문이 대화에 붙지 않았습니다", "→ 빈칸 4 를 확인하세요.")
        return False
    ok("세션 유지 (두 번째 질문이 이전 대화를 이어받음)")

    # -- 예산 --
    agent = _load_agent("budget")
    budget_session = agent.Session()
    try:
        result = budget_session.ask("반복해봐", verbose=False)
    except Exception as exc:  # noqa: BLE001
        fail("예산 시나리오에서 예외", f"{type(exc).__name__}: {exc}")
        return False

    if "MAX_TURNS" in result:
        fail(
            "같은 호출 반복을 막지 못했습니다",
            "모델이 같은 도구를 같은 인자로 계속 부르면 MAX_TURNS 까지 돕니다.\n"
            "→ 빈칸 3 을 확인하세요.",
        )
        return False
    ok(f"호출 예산 (같은 호출 {agent.MAX_REPEATS}회 초과 시 차단)")

    return True


# ---------------------------------------------------------------------------


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    results = {}
    if which in ("tools", "all"):
        results["도구"] = check_tools()
    if which in ("agent", "all"):
        results["루프"] = check_agent()

    print("\n" + "═" * 64)
    for name, passed in results.items():
        print(f"  {name}  " + (f"{GREEN}통과{RESET}" if passed else f"{RED}미완{RESET}"))
    if all(results.values()):
        print(f"\n  이제 {GREY}CHECKPOINT.md{RESET} 의 질문에 답해보세요.")
    print("═" * 64 + "\n")
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
