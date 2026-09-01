"""가짜 Anthropic 클라이언트.

API 키 없이 4단계 루프를 채점하기 위한 것입니다. 실제 모델처럼
tool_use 를 한 번 돌려주고, 결과를 제대로 받으면 최종 답을 내놓습니다.

부수 효과가 하나 있습니다. 이 파일을 읽으면 API 가 무엇을 기대하는지가
아주 명확해집니다. 4단계가 막히면 여기를 먼저 보세요.
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
    input_tokens: int = 120
    output_tokens: int = 45


@dataclass
class FakeResponse:
    content: list
    stop_reason: str
    model: str = "fake-model"
    usage: Usage = field(default_factory=Usage)


class ProtocolError(AssertionError):
    """대화 형식이 API 규칙에 어긋났을 때. 메시지가 곧 채점 피드백입니다."""


class FakeMessages:
    def __init__(self, owner: "FakeAnthropic") -> None:
        self.owner = owner

    def create(self, *, messages, tools=None, **_kwargs) -> FakeResponse:
        self.owner.calls += 1
        self._validate(messages)

        # 첫 호출 — 도구를 부르겠다고 답한다
        if self.owner.calls == 1:
            if not tools:
                raise ProtocolError("tools 를 넘기지 않았습니다. 도구를 정의만 하고 붙이지 않았습니다.")
            code = "import os\n\n# 현재 경로\nprint(os.getcwd())\n"
            return FakeResponse(
                content=[
                    TextBlock("줄 수를 세어보겠습니다."),
                    ToolUseBlock(id="toolu_fake_01", name="count_lines", input={"code": code}),
                ],
                stop_reason="tool_use",
            )

        # 두 번째 호출 — 결과를 제대로 받았으면 최종 답
        payload = self.owner.last_tool_result
        if payload is None:
            raise ProtocolError("두 번째 호출에 tool_result 가 들어 있지 않습니다.")

        total = payload.get("total")
        code_lines = payload.get("code")
        if payload.get("error"):
            return FakeResponse(
                content=[TextBlock(f"도구가 실패했습니다: {payload['error']}")],
                stop_reason="end_turn",
            )

        return FakeResponse(
            content=[TextBlock(f"전체 {total}줄이고, 그중 실제 코드는 {code_lines}줄입니다.")],
            stop_reason="end_turn",
        )

    # -- 형식 검사 ---------------------------------------------------------

    def _validate(self, messages: list[dict]) -> None:
        if not messages:
            raise ProtocolError("messages 가 비어 있습니다.")

        if messages[0]["role"] != "user":
            raise ProtocolError("첫 메시지의 role 은 'user' 여야 합니다.")

        # 두 번째 호출부터는 assistant 턴과 tool_result 가 있어야 한다
        if self.owner.calls == 1:
            return

        roles = [m["role"] for m in messages]

        if "assistant" not in roles:
            raise ProtocolError(
                "assistant 메시지가 없습니다. 모델의 응답을 messages 에 붙이지 않았습니다.\n"
                "        → 빈칸 2 를 확인하세요."
            )

        assistant = next(m for m in messages if m["role"] == "assistant")
        blocks = assistant["content"]
        if isinstance(blocks, str):
            raise ProtocolError(
                "assistant content 가 문자열입니다. 블록 리스트를 통째로 넣어야 합니다.\n"
                "        텍스트만 뽑아 넣으면 tool_use 블록의 id 가 사라집니다.\n"
                "        → 빈칸 2 를 확인하세요."
            )

        ids = {getattr(b, "id", None) for b in blocks if getattr(b, "type", None) == "tool_use"}
        if not ids:
            raise ProtocolError(
                "assistant content 에 tool_use 블록이 없습니다.\n"
                "        response.content 를 통째로 넣었는지 확인하세요.\n"
                "        → 빈칸 2 를 확인하세요."
            )

        last = messages[-1]
        if last["role"] != "user":
            raise ProtocolError(
                f"마지막 메시지의 role 이 '{last['role']}' 입니다. "
                "도구 결과는 'user' 역할로 보냅니다.\n"
                "        → 빈칸 4 를 확인하세요."
            )

        content = last["content"]
        if not isinstance(content, list):
            raise ProtocolError(
                "도구 결과는 블록 리스트여야 합니다. 문자열이 아닙니다.\n"
                "        → 빈칸 3, 4 를 확인하세요."
            )

        tool_results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
        if not tool_results:
            raise ProtocolError(
                "tool_result 블록이 없습니다. 도구를 실행하고 결과를 담았습니까?\n"
                "        → 빈칸 3 을 확인하세요."
            )

        for block in tool_results:
            if "tool_use_id" not in block:
                raise ProtocolError(
                    "tool_result 에 tool_use_id 가 없습니다.\n"
                    "        어느 호출에 대한 답인지 알려주지 않으면 API 가 거절합니다.\n"
                    "        → 빈칸 3 을 확인하세요."
                )
            if block["tool_use_id"] not in ids:
                raise ProtocolError(
                    f"tool_use_id '{block['tool_use_id']}' 가 assistant 의 tool_use id 와 다릅니다.\n"
                    f"        기대: {ids}\n"
                    "        → 빈칸 3 을 확인하세요."
                )
            if not isinstance(block.get("content"), str):
                raise ProtocolError(
                    "tool_result 의 content 는 문자열이어야 합니다.\n"
                    "        dict 를 그대로 넣지 말고 json.dumps 로 바꾸세요.\n"
                    "        → 빈칸 3 을 확인하세요."
                )

        if len(tool_results) != len(ids):
            raise ProtocolError(
                f"tool_use 는 {len(ids)}개인데 tool_result 는 {len(tool_results)}개입니다.\n"
                "        모든 tool_use 에 결과를 돌려줘야 합니다."
            )

        try:
            self.owner.last_tool_result = json.loads(tool_results[0]["content"])
        except json.JSONDecodeError:
            self.owner.last_tool_result = {"error": "JSON 이 아닙니다"}


class FakeAnthropic:
    """anthropic.Anthropic 자리에 끼워넣는 가짜."""

    def __init__(self, *_args, **_kwargs) -> None:
        self.calls = 0
        self.last_tool_result: dict | None = None
        self.messages = FakeMessages(self)
