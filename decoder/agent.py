"""에이전트 루프.

1~2주차에서 손으로 짠 그 루프다. 프레임워크에 위임하지 않았다.
    모델 호출 → stop_reason 확인 → tool_use 면 도구 실행 → 결과를 붙여 다시 호출
이 구조를 직접 보는 것이 스터디의 목적이므로 추상화를 얇게 유지한다.

이벤트를 흘려보내기 때문에 화면에서 루프가 도는 모습을 실시간으로 볼 수 있다.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

from .prompts import SYSTEM, build_user_message
from .tools import TOOLS, dispatch

DEFAULT_MODEL = os.environ.get("CODE_DECODE_MODEL", "claude-sonnet-5")
MAX_TURNS = 8


class DecodeError(RuntimeError):
    pass


def decode(code: str, model: str = DEFAULT_MODEL, api_key: str | None = None) -> Iterator[dict[str, Any]]:
    """코드를 해독한다. 이벤트를 순서대로 내보내는 제너레이터.

    이벤트 종류
        turn        루프 n번째 시작
        tool_use    모델이 도구를 부름
        tool_result 도구 실행 결과 요약
        entry       완성된 학습 항목 하나 (스트리밍 중 점진적으로)
        usage       토큰 사용량
        done        종료
        error       실패
    """
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise DecodeError("anthropic 패키지가 없습니다. pip install anthropic") from exc

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise DecodeError("ANTHROPIC_API_KEY 가 설정되지 않았습니다. .env 를 확인하세요.")

    client = anthropic.Anthropic(api_key=key)
    messages: list[dict[str, Any]] = [{"role": "user", "content": build_user_message(code)}]

    totals = {"input": 0, "output": 0, "cache_read": 0}
    parser = _EntryStream()

    for turn in range(1, MAX_TURNS + 1):
        yield {"type": "turn", "n": turn}

        blocks: list[dict[str, Any]] = []
        stop_reason: str | None = None

        try:
            with client.messages.stream(
                model=model,
                max_tokens=4096,
                system=[
                    # 시스템 프롬프트와 도구 정의는 매 호출마다 동일하다.
                    # 캐시해두면 두 번째 호출부터 입력 비용이 1/10 이 된다.
                    {"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}
                ],
                tools=TOOLS,
                messages=messages,
            ) as stream:
                for event in stream.text_stream:
                    for entry in parser.feed(event):
                        yield {"type": "entry", "entry": entry}

                final = stream.get_final_message()
                stop_reason = final.stop_reason
                blocks = [b.model_dump() for b in final.content]
                usage = final.usage
                totals["input"] += usage.input_tokens
                totals["output"] += usage.output_tokens
                totals["cache_read"] += getattr(usage, "cache_read_input_tokens", 0) or 0
        except Exception as exc:  # noqa: BLE001
            yield {"type": "error", "message": f"{type(exc).__name__}: {exc}"}
            return

        yield {"type": "usage", **totals}

        if stop_reason != "tool_use":
            break

        messages.append({"role": "assistant", "content": blocks})

        results: list[dict[str, Any]] = []
        for block in blocks:
            if block.get("type") != "tool_use":
                continue
            name, payload, use_id = block["name"], block["input"], block["id"]
            yield {"type": "tool_use", "name": name, "input": _summarize_input(name, payload)}

            output = dispatch(name, payload)
            yield {"type": "tool_result", "name": name, "summary": _summarize_result(name, output)}

            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": use_id,
                    "content": json.dumps(output, ensure_ascii=False),
                }
            )

        if not results:
            break
        messages.append({"role": "user", "content": results})

    leftover = parser.finish()
    for entry in leftover:
        yield {"type": "entry", "entry": entry}

    yield {"type": "done", "entries": parser.count, **totals}


# ---------------------------------------------------------------------------
# 스트리밍 JSON 파서
# ---------------------------------------------------------------------------


class _EntryStream:
    """JSON 배열이 흘러들어오는 대로 완성된 객체를 하나씩 꺼낸다.

    모델이 배열 전체를 다 뱉을 때까지 기다리면 화면이 오래 비어 있다.
    중괄호 깊이를 세면서 객체가 닫히는 순간 파싱해 바로 내보낸다.
    """

    def __init__(self) -> None:
        self.buffer = ""
        self.depth = 0
        self.start: int | None = None
        self.in_string = False
        self.escaped = False
        self.count = 0

    def feed(self, chunk: str) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for char in chunk:
            self.buffer += char
            index = len(self.buffer) - 1

            if self.in_string:
                if self.escaped:
                    self.escaped = False
                elif char == "\\":
                    self.escaped = True
                elif char == '"':
                    self.in_string = False
                continue

            if char == '"':
                self.in_string = True
            elif char == "{":
                if self.depth == 0:
                    self.start = index
                self.depth += 1
            elif char == "}":
                self.depth -= 1
                if self.depth == 0 and self.start is not None:
                    raw = self.buffer[self.start : index + 1]
                    self.start = None
                    parsed = _safe_load(raw)
                    if parsed is not None:
                        self.count += 1
                        found.append(parsed)
        return found

    def finish(self) -> list[dict[str, Any]]:
        """루프가 끝났는데 아무것도 못 건졌다면 통째로 한 번 더 시도한다."""
        if self.count:
            return []
        text = self.buffer.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        parsed = _safe_load(text)
        if isinstance(parsed, list):
            self.count = len(parsed)
            return [p for p in parsed if isinstance(p, dict)]
        return []


def _safe_load(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# 화면에 보여줄 요약
# ---------------------------------------------------------------------------


def _summarize_input(name: str, payload: dict[str, Any]) -> str:
    if name == "analyze_code":
        lines = payload.get("code", "").count("\n") + 1
        return f"{lines}줄"
    if name == "lookup_documentation":
        names = payload.get("qualnames", [])
        head = ", ".join(names[:3])
        return head + (f" 외 {len(names) - 3}개" if len(names) > 3 else "")
    return ""


def _summarize_result(name: str, output: dict[str, Any]) -> str:
    if output.get("error"):
        return f"실패 — {output['error']}"
    if name == "analyze_code":
        total = len(output.get("symbols", []))
        unresolved = output.get("unresolved_count", 0)
        syntax = len(output.get("syntax", []))
        return f"심볼 {total}개(미해석 {unresolved}) · 문법 {syntax}개"
    if name == "lookup_documentation":
        results = output.get("results", [])
        hit = sum(1 for r in results if r.get("found"))
        return f"{hit}/{len(results)}건 문서 확보"
    return ""


__all__ = ["decode", "DecodeError", "DEFAULT_MODEL"]
