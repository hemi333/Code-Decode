#!/usr/bin/env python3
"""벤치마크 실행기.

    python -m benchmarks.run_bench            # 전체 실행, 결과를 주차 폴더에 저장
    python -m benchmarks.run_bench --ast      # LLM 없이 AST 해석률만
    python -m benchmarks.run_bench --diff w03 w04   # 두 주차 결과 비교

출력은 benchmarks/results/<라벨>/ 에 쌓인다. 매주 같은 5개를 돌려
나란히 놓고 보는 것이 목적이므로 파일명을 스니펫 이름으로 고정한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarks.snippets import SNIPPETS  # noqa: E402
from decoder.analyzer import analyze_code  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"


def run_ast() -> None:
    """LLM 없이 정적 해석률만 본다. 4~5주차의 성적표."""
    total = resolved = 0
    print(f"{'스니펫':<16} {'심볼':>4} {'해석':>4} {'실패':>4}  미해석 항목")
    print("-" * 78)

    for name in sorted(SNIPPETS):
        result = analyze_code(SNIPPETS[name]["code"])
        symbols = result["symbols"]
        misses = [s for s in symbols if s["qualname"] is None]
        total += len(symbols)
        resolved += len(symbols) - len(misses)
        detail = ", ".join(s["source"] for s in misses) or "—"
        print(f"{name:<16} {len(symbols):>4} {len(symbols) - len(misses):>4} {len(misses):>4}  {detail}")

    rate = resolved / total * 100 if total else 0
    print("-" * 78)
    print(f"{'합계':<16} {total:>4} {resolved:>4} {total - resolved:>4}  해석률 {rate:.0f}%")
    print("\n해석 실패는 결함이 아니라 정적 분석의 경계입니다.")
    print("실패한 항목에 receiver_origin 단서가 붙어 LLM 에게 넘어갑니다.")


def run_full(label: str, model: str | None) -> None:
    from decoder.agent import DEFAULT_MODEL, decode

    out_dir = RESULTS / label
    out_dir.mkdir(parents=True, exist_ok=True)
    model = model or DEFAULT_MODEL

    grand = {"input": 0, "output": 0}

    for name in sorted(SNIPPETS):
        print(f"\n▶ {name}  ({SNIPPETS[name]['why']})")
        entries: list[dict] = []
        usage = {"input": 0, "output": 0}

        for event in decode(SNIPPETS[name]["code"], model=model):
            kind = event["type"]
            if kind == "tool_use":
                print(f"    → {event['name']}({event['input']})")
            elif kind == "tool_result":
                print(f"      {event['summary']}")
            elif kind == "entry":
                entries.append(event["entry"])
            elif kind == "error":
                print(f"    ✗ {event['message']}")
            elif kind == "done":
                usage = {"input": event["input"], "output": event["output"]}

        grand["input"] += usage["input"]
        grand["output"] += usage["output"]

        payload = {
            "snippet": name,
            "model": model,
            "date": date.today().isoformat(),
            "expect": SNIPPETS[name]["expect"],
            "usage": usage,
            "entries": entries,
        }
        (out_dir / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"    항목 {len(entries)}개 · 기대: {SNIPPETS[name]['expect']}")

    cost = (grand["input"] * 2 + grand["output"] * 10) / 1e6
    print(f"\n저장 위치: {out_dir}")
    print(f"토큰 합계: 입력 {grand['input']:,} · 출력 {grand['output']:,} · 약 ${cost:.4f}")


def run_diff(left: str, right: str) -> None:
    """두 주차 결과를 항목 수와 필드 채움률로 비교한다."""
    print(f"{'스니펫':<16} {left:>14} {right:>14}   변화")
    print("-" * 62)

    for name in sorted(SNIPPETS):
        a = _load(left, name)
        b = _load(right, name)
        sa, sb = _score(a), _score(b)
        arrow = "→" if sa["entries"] == sb["entries"] else ("↑" if sb["entries"] > sa["entries"] else "↓")
        print(
            f"{name:<16} "
            f"{sa['entries']:>3}항목 {sa['filled']:>3}필드 "
            f"{sb['entries']:>3}항목 {sb['filled']:>3}필드   {arrow}"
        )

    print("\n숫자는 출발점일 뿐입니다. 실제 비교는 두 폴더의 JSON 을 나란히 열어")
    print("what/why/gotcha 의 내용을 읽고 하세요. 항목 수가 늘었다고 좋아진 게 아닙니다.")


def _load(label: str, name: str) -> dict:
    path = RESULTS / label / f"{name}.json"
    if not path.exists():
        return {"entries": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _score(payload: dict) -> dict:
    entries = payload.get("entries", [])
    filled = sum(
        1
        for e in entries
        for key in ("what", "why", "gotcha", "example", "check", "source")
        if e.get(key)
    )
    return {"entries": len(entries), "filled": filled}


def main() -> None:
    parser = argparse.ArgumentParser(description="Code Decode 벤치마크")
    parser.add_argument("--ast", action="store_true", help="LLM 없이 AST 해석률만")
    parser.add_argument("--label", default=f"w{date.today():%m%d}", help="결과 저장 폴더명")
    parser.add_argument("--model", default=None)
    parser.add_argument("--diff", nargs=2, metavar=("이전", "이후"))
    args = parser.parse_args()

    if args.ast:
        run_ast()
    elif args.diff:
        run_diff(*args.diff)
    else:
        run_full(args.label, args.model)


if __name__ == "__main__":
    main()
