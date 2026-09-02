"""가짜 Anthropic 클라이언트 · 2주차판.

1주차 것보다 사납습니다. 실제 모델이 하는 일을 재현합니다.

    1턴  list_files("*.py")                        ← 연쇄의 시작
    2턴  read_file × 3   (하나는 없는 파일)          ← 병렬 + 실패
    3턴  count_lines × 2                            ← 병렬
    4턴  최종 답

여기에 더해, 같은 호출을 반복하는 모델도 흉내냅니다 (예산 시나리오).

막히면 정답 파일보다 여기를 먼저 보세요.
가짜 API 가 무엇을 검사하는지 읽으면 진짜 API 가 뭘 기대하는지 명확해집니다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class Usage:
    input_tokens: int = 200
    output_tokens: int = 60


@dataclass
class FakeResponse:
    content: list
    stop_reason: str
    model: str = "fake-model"
    usage: Usage = field(default_factory=Usage)


class ProtocolError(AssertionError):
    """대화 형식 위반. 메시지가 곧 채점 피드백입니다."""


class FakeMessages:
    def __init__(self, owner: "FakeAnthropic") -> None:
        self.owner = owner

    def create(self, *, messages, tools=None, **_kw) -> FakeResponse:
        self.owner.calls += 1
        self._validate(messages, tools)

        if self.owner.scenario == "budget":
            return self._budget_turn()
        return self._main_turn()

    # -- 시나리오 ----------------------------------------------------------

    def _main_turn(self) -> FakeResponse:
        n = self.owner.calls

        if n == 1:
            return FakeResponse(
                content=[
                    TextBlock("먼저 어떤 파일이 있는지 보겠습니다."),
                    ToolUseBlock("tu_list", "list_files", {"pattern": "*.py"}),
                ],
                stop_reason="tool_use",
            )

        if n == 2:
            files = self.owner.seen.get("list_files", {}).get("files", [])
            if not files:
                raise ProtocolError(
                    "list_files 결과에 files 가 없습니다.\n"
                    '        {"files": [...], "count": N} 형태로 돌려주세요.\n'
                    "        → tools.py 의 list_files 를 확인하세요."
                )
            # 병렬 호출. 마지막 하나는 일부러 없는 파일 — 실패 경로를 강제한다.
            blocks = [TextBlock("세 파일을 한 번에 읽겠습니다.")]
            for i, name in enumerate(files[:2]):
                blocks.append(ToolUseBlock(f"tu_read_{i}", "read_file", {"name": name}))
            blocks.append(
                ToolUseBlock("tu_read_x", "read_file", {"name": "존재하지_않음.py"})
            )
            return FakeResponse(content=blocks, stop_reason="tool_use")

        if n == 3:
            reads = self.owner.reads
            if len(reads) < 2:
                raise ProtocolError(
                    f"read_file 결과를 {len(reads)}개만 받았습니다. 3개를 보냈습니다.\n"
                    "        tool_use 하나마다 tool_result 하나가 있어야 합니다.\n"
                    "        → 빈칸 1 을 확인하세요."
                )
            if not self.owner.saw_error_flag:
                raise ProtocolError(
                    "실패한 도구에 is_error 가 붙지 않았습니다.\n"
                    "        없는 파일을 읽으라고 했는데 실패가 형식으로 드러나지 않습니다.\n"
                    "        → 빈칸 2 를 확인하세요."
                )
            blocks = [TextBlock("이제 줄 수를 세겠습니다.")]
            for i, content in enumerate(reads[:2]):
                blocks.append(
                    ToolUseBlock(f"tu_count_{i}", "count_lines", {"code": content})
                )
            return FakeResponse(content=blocks, stop_reason="tool_use")

        counts = self.owner.counts
        if len(counts) < 2:
            raise ProtocolError(
                f"count_lines 결과를 {len(counts)}개만 받았습니다.\n"
                "        → 빈칸 1 을 확인하세요."
            )
        best = max(counts, key=lambda c: c.get("total", 0))
        return FakeResponse(
            content=[
                TextBlock(
                    f"가장 긴 파일은 {best['total']}줄이고, "
                    f"주석과 빈 줄을 빼면 {best['code']}줄입니다. "
                    "존재하지_않음.py 는 읽지 못했습니다."
                )
            ],
            stop_reason="end_turn",
        )

    def _budget_turn(self) -> FakeResponse:
        """같은 호출만 반복하는 모델. 예산이 없으면 MAX_TURNS 까지 돕니다."""
        if self.owner.blocked:
            return FakeResponse(
                content=[TextBlock("반복 호출이 차단되어 중단합니다.")],
                stop_reason="end_turn",
            )
        return FakeResponse(
            content=[ToolUseBlock("tu_same", "list_files", {"pattern": "*.py"})],
            stop_reason="tool_use",
        )

    # -- 형식 검사 ---------------------------------------------------------

    def _validate(self, messages: list[dict], tools) -> None:
        if not messages:
            raise ProtocolError("messages 가 비어 있습니다. 질문을 붙이지 않았습니다.\n        → 빈칸 4 를 확인하세요.")
        if messages[0]["role"] != "user":
            raise ProtocolError("첫 메시지의 role 은 'user' 여야 합니다.")
        if not tools:
            raise ProtocolError("tools 를 넘기지 않았습니다.")

        if self.owner.calls == 1:
            return

        last = messages[-1]
        if last["role"] != "user":
            raise ProtocolError(
                f"마지막 메시지의 role 이 '{last['role']}' 입니다. "
                "도구 결과는 'user' 로 보냅니다."
            )

        content = last["content"]
        if not isinstance(content, list):
            raise ProtocolError("도구 결과는 블록 리스트여야 합니다.")

        blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
        if not blocks:
            raise ProtocolError("tool_result 블록이 없습니다.\n        → 빈칸 1 을 확인하세요.")

        # 직전 assistant 턴의 tool_use 와 짝이 맞는지
        assistant = None
        for message in reversed(messages[:-1]):
            if message["role"] == "assistant":
                assistant = message
                break
        if assistant is None:
            raise ProtocolError("assistant 메시지가 없습니다.")

        expected = [
            b for b in assistant["content"] if getattr(b, "type", None) == "tool_use"
        ]
        ids = {b.id for b in expected}

        if len(blocks) != len(ids):
            raise ProtocolError(
                f"tool_use 는 {len(ids)}개인데 tool_result 는 {len(blocks)}개입니다.\n"
                "        한 응답에 도구가 여러 개 올 수 있습니다. 전부 실행하세요.\n"
                "        → 빈칸 1 을 확인하세요."
            )

        # tool_result 를 여러 메시지에 나눠 담았는지
        earlier = [
            m
            for m in messages[:-1]
            if m["role"] == "user"
            and isinstance(m["content"], list)
            and any(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in m["content"]
            )
        ]
        expected_rounds = self.owner.calls - 2
        if len(earlier) > expected_rounds:
            raise ProtocolError(
                "tool_result 가 여러 user 메시지에 나뉘어 있습니다.\n"
                "        한 라운드의 결과는 하나의 메시지 안에 전부 담아야 합니다.\n"
                "        결과마다 append 를 부르지 마세요.\n"
                "        → 빈칸 1 을 확인하세요."
            )

        # 결과 수집
        self.owner.reads = []
        self.owner.counts = []
        for block in blocks:
            if block["tool_use_id"] not in ids:
                raise ProtocolError(
                    f"tool_use_id '{block['tool_use_id']}' 가 짝이 없습니다."
                )
            if not isinstance(block.get("content"), str):
                raise ProtocolError(
                    "tool_result 의 content 는 문자열이어야 합니다. json.dumps 를 쓰세요."
                )
            if block.get("is_error"):
                self.owner.saw_error_flag = True
                if "반복" in block["content"]:
                    self.owner.blocked = True

            try:
                payload = json.loads(block["content"])
            except json.JSONDecodeError:
                continue

            source = next(b for b in expected if b.id == block["tool_use_id"])
            self.owner.seen[source.name] = payload

            if source.name == "read_file" and "content" in payload:
                self.owner.reads.append(payload["content"])
            elif source.name == "count_lines" and "total" in payload:
                self.owner.counts.append(payload)


class FakeAnthropic:
    def __init__(self, *_a, scenario: str = "main", **_kw) -> None:
        self.calls = 0
        self.scenario = scenario
        self.seen: dict = {}
        self.reads: list = []
        self.counts: list = []
        self.saw_error_flag = False
        self.blocked = False
        self.messages = FakeMessages(self)
