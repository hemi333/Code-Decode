"""에이전트 루프 · 2주차판.

1주차 루프를 그대로 가져와 네 가지를 더합니다.

    빈칸 1  병렬   한 응답에 tool_use 가 여러 개일 때
    빈칸 2  실패   도구가 실패했다는 걸 모델에게 알리기
    빈칸 3  예산   같은 도구를 무한히 부르는 걸 막기
    빈칸 4  세션   여러 질문에 걸쳐 대화를 이어가기

1주차 코드가 있으면 옆에 열어두고 비교하며 채우세요.
어디가 같고 어디가 달라졌는지 보는 게 이번 주 공부의 절반입니다.

    python check.py            # 채점 (API 키 없이 됨)
    python agent.py            # 실제로 돌려보기 (키 필요)
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter

import anthropic

import env  # noqa: F401  (.env 로드)
from tools import TOOLS, dispatch

MODEL = "claude-sonnet-5"
MAX_TURNS = 10

# 한 세션에서 같은 (도구, 인자) 조합을 몇 번까지 허용할 것인가.
# 빈칸 3 에서 씁니다.
MAX_REPEATS = 2

SYSTEM = """당신은 코드베이스에 대한 질문에 답합니다.

파일 목록이나 내용은 추측하지 말고 도구로 확인하세요.
여러 파일을 봐야 한다면 도구를 한 번에 여러 개 부르는 편이 빠릅니다.
도구가 실패하면 실패한 사실을 사용자에게 알리고, 가능한 범위에서 답하세요."""


class Session:
    """대화 하나. messages 를 들고 있는 게 전부입니다.

    모델은 아무것도 기억하지 못하므로, 이 객체가 곧 기억입니다.
    """

    def __init__(self, client=None) -> None:
        self.client = client or anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", "")
        )
        self.messages: list[dict] = []
        self.usage = {"input": 0, "output": 0}
        self.tool_calls: Counter[str] = Counter()

    # ------------------------------------------------------------------
    def ask(self, question: str, verbose: bool = True) -> str:
        """질문 하나를 처리하고 최종 답을 돌려준다.

        같은 Session 에 두 번 물으면 두 번째 질문은 첫 번째 대화를 기억합니다.
        """
        # ------------------------------------------------------------------
        # 빈칸 4 · 세션 유지
        #
        # 새 질문을 messages 에 붙입니다.
        # self.messages 를 매번 새로 만들면 대화가 이어지지 않습니다.
        #
        # 왜 이게 빈칸일까요? 1주차에는 run() 안에서 messages 를 만들고
        # 끝나면 버렸습니다. 그래서 "방금 말한 그 파일 말이야" 같은
        # 후속 질문이 안 됐습니다. 지금은 됩니다.
        # ------------------------------------------------------------------
        # TODO: question 을 self.messages 에 user 메시지로 추가하세요.

        for turn in range(1, MAX_TURNS + 1):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=SYSTEM,
                tools=TOOLS,
                messages=self.messages,
            )

            self.usage["input"] += response.usage.input_tokens
            self.usage["output"] += response.usage.output_tokens

            if verbose:
                kinds = ", ".join(b.type for b in response.content)
                print(f"\n[{turn}] stop={response.stop_reason}  blocks=[{kinds}]")

            if response.stop_reason != "tool_use":
                self.messages.append({"role": "assistant", "content": response.content})
                return "\n".join(b.text for b in response.content if b.type == "text")

            self.messages.append({"role": "assistant", "content": response.content})

            # --------------------------------------------------------------
            # 빈칸 1 · 병렬 처리
            #
            # response.content 에 tool_use 블록이 **여러 개** 있을 수 있습니다.
            # 1주차 가짜 API 는 항상 하나만 줬지만, 진짜 모델은
            # "파일 3개를 읽어줘" 상황에서 세 개를 한 번에 냅니다.
            #
            # 전부 실행해서 results 에 담으세요. 하나라도 빠뜨리면 API 가 400 입니다.
            #
            # ★ 가장 흔한 실수 ★
            #   결과 하나마다 messages.append 를 부르는 것.
            #   tool_result 는 **하나의 user 메시지 안에 전부** 들어가야 합니다.
            #   아래 빈칸 2 다음에 딱 한 번만 append 합니다.
            # --------------------------------------------------------------
            results: list[dict] = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                # ----------------------------------------------------------
                # 빈칸 3 · 호출 예산
                #
                # 모델이 같은 도구를 같은 인자로 계속 부르는 경우가 있습니다.
                # 결과가 마음에 안 들면 다시 시도하기 때문입니다.
                # MAX_REPEATS 를 넘으면 실행하지 말고, 그 사실을 결과로 돌려주세요.
                #
                # 실행을 건너뛰더라도 tool_result 는 반드시 만들어야 합니다.
                # tool_use 하나에 tool_result 하나. 짝이 안 맞으면 API 가 거절합니다.
                #
                # 서명 만들기: f"{block.name}:{json.dumps(block.input, sort_keys=True)}"
                # ----------------------------------------------------------
                # TODO: 서명을 만들고 self.tool_calls 로 횟수를 세세요.
                #       한도를 넘으면 output 을 에러로 만들고 dispatch 는 건너뜁니다.

                output = dispatch(block.name, block.input)

                if verbose:
                    preview = json.dumps(output, ensure_ascii=False)[:70]
                    print(f"     {block.name}({json.dumps(block.input, ensure_ascii=False)[:40]}) → {preview}")

                # ----------------------------------------------------------
                # 빈칸 2 · 실패를 모델에게 알리기
                #
                # 도구가 {"error": ...} 를 돌려줬을 때, 그냥 JSON 문자열로
                # 넘겨도 모델은 대충 알아챕니다. 하지만 API 에는 전용 필드가 있습니다.
                #
                #     {"type": "tool_result", "tool_use_id": ..., "content": ...,
                #      "is_error": True}
                #
                # 왜 굳이 쓸까요? 실패가 **형식으로** 드러나면 모델이 헷갈릴 여지가
                # 줄기 때문입니다. {"error": "..."} 라는 문자열은 성공한 도구가
                # 우연히 그런 내용을 돌려준 것일 수도 있습니다.
                #
                # output 에 "error" 키가 있으면 is_error 를 붙이세요.
                # ----------------------------------------------------------
                # TODO: tool_result 블록을 만들어 results 에 넣으세요.

            # --------------------------------------------------------------
            # 여기서 딱 한 번. 위 for 문 안이 아닙니다.
            # --------------------------------------------------------------
            if not results:
                break
            self.messages.append({"role": "user", "content": results})

        return f"(MAX_TURNS={MAX_TURNS} 도달)"

    # ------------------------------------------------------------------
    def cost(self) -> float:
        return (self.usage["input"] * 2 + self.usage["output"] * 10) / 1e6


def main() -> None:
    session = Session()

    questions = sys.argv[1:] or [
        "fixtures 폴더에서 가장 긴 파이썬 파일이 뭐야?",
        "그 파일에서 주석과 빈 줄을 빼면 몇 줄이야?",  # ← 세션이 되면 이게 됩니다
    ]

    for question in questions:
        print("=" * 68)
        print(f"Q. {question}")
        print("=" * 68)
        print(f"\nA. {session.ask(question)}\n")

    print("─" * 68)
    print(
        f"입력 {session.usage['input']:,} · 출력 {session.usage['output']:,} 토큰 "
        f"· 약 ${session.cost():.4f}"
    )
    print(f"도구 호출: {dict(session.tool_calls)}")


if __name__ == "__main__":
    main()
