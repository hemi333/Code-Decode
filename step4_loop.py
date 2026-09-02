"""4단계 · 루프를 직접 짠다.  ← 이번 주의 본론

    python step4_loop.py "이 코드 몇 줄이야?  import os\\nprint(1)"
    python check.py 4

2단계에서 대화가 어정쩡하게 멈췄던 것을 기억하세요.
모델이 "count_lines 를 불러줘" 라고 말했는데 아무도 부르지 않았습니다.

그 다음을 이어붙이는 게 이번 실습입니다. 흐름은 이렇습니다.

    ┌─ 모델 호출
    │      ↓
    │  stop_reason 이 tool_use 인가?
    │      ↓ 예                        ↓ 아니오
    │  도구 실행                      끝. 텍스트를 뽑아 반환
    │      ↓
    │  결과를 대화에 붙이고
    └──── 다시 호출

라이브러리에 맡기지 마세요. 이 구조를 손으로 한 번 짜보는 게 목적입니다.
LangChain 이나 SDK 의 편의 함수를 쓰면 이 주차는 배운 게 없이 지나갑니다.
"""

import json
import os
import sys

import anthropic

import env  # .env 로드 + 워크스페이스 헤더

from step3_tool import TOOLS, dispatch

MODEL = "claude-sonnet-5"
MAX_TURNS = 6  # 무한 루프 방지. 도구를 계속 부르는 모델을 만나면 필요합니다.

SYSTEM = """당신은 코드에 대한 질문에 답합니다.
줄 수처럼 세어봐야 아는 것은 추측하지 말고 도구를 부르세요."""


def run(question: str, verbose: bool = True) -> str:
    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        # 사용자 키는 어느 워크스페이스로 보내는지 헤더로 알려줘야 합니다. env.py 참고.
        default_headers=env.workspace_headers(),
    )

    # 대화 내역. 모델은 아무것도 기억하지 못하므로 이 리스트가 곧 기억입니다.
    # 매 호출마다 통째로 다시 보냅니다.
    messages: list[dict] = [{"role": "user", "content": question}]

    for turn in range(1, MAX_TURNS + 1):
        if verbose:
            print(f"\n{'─' * 60}\n{turn}번째 호출  (messages 길이: {len(messages)})")

        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
        )

        if verbose:
            kinds = ", ".join(b.type for b in response.content)
            print(f"  stop_reason={response.stop_reason}  blocks=[{kinds}]")

        # ------------------------------------------------------------------
        # 빈칸 1 · 언제 멈출 것인가
        #
        # stop_reason 이 "tool_use" 가 아니면 모델은 할 말을 다 한 것입니다.
        # 루프를 빠져나가세요.
        #
        # 왜 stop_reason 으로 판단합니까? content 에 tool_use 블록이 있는지
        # 직접 뒤져도 되지 않을까요? 둘 중 무엇이 나은지 생각해보세요.
        # ------------------------------------------------------------------
        # content 를 뒤지지 않고 stop_reason 으로 판단한다.
        # stop_reason 은 모델이 "왜 멈췄는가"를 스스로 말해주는 값이고,
        # content 를 뒤지는 건 우리가 그걸 추측하는 것이다.
        # 예를 들어 max_tokens 로 잘려 tool_use 블록이 반쪽만 온 경우,
        # 블록을 뒤지는 방식은 그걸 정상적인 도구 호출로 착각한다.
        if response.stop_reason != "tool_use":
            break

        # ------------------------------------------------------------------
        # 빈칸 2 · 모델이 한 말을 대화에 남긴다
        #
        # 방금 받은 응답을 messages 에 붙여야 합니다. 안 붙이면 다음 호출에서
        # 모델은 자기가 도구를 부르려 했다는 사실 자체를 모릅니다.
        #
        # 주의: response.content 를 통째로 넣어야 합니다.
        #       텍스트 블록만 골라 넣거나 문자열로 바꾸면 안 됩니다.
        #       tool_use 블록의 id 가 사라지면 다음 단계에서 짝을 맞출 수 없습니다.
        #
        #       {"role": "assistant", "content": <여기>}
        # ------------------------------------------------------------------
        # response.content 를 통째로 넣는다. 텍스트만 뽑거나 str() 로 바꾸면
        # tool_use 블록의 id 가 사라지고, 다음 턴에서 tool_result 와 짝이 맞지 않는다.
        messages.append({"role": "assistant", "content": response.content})

        # ------------------------------------------------------------------
        # 빈칸 3 · 도구를 실행하고 결과를 모은다
        #
        # response.content 를 돌면서 type 이 "tool_use" 인 블록만 골라
        # dispatch(이름, 인자) 로 실행합니다.
        #
        # 결과는 이 형태로 만듭니다.
        #     {
        #       "type": "tool_result",
        #       "tool_use_id": <이 결과가 어느 호출에 대한 답인지>,
        #       "content": <문자열. dict 는 json.dumps 로 바꾸세요>
        #     }
        #
        # 한 번에 도구를 여러 개 부를 수도 있습니다. 그래서 리스트입니다.
        # 하나라도 빠뜨리면 API 가 400 을 돌려줍니다. 직접 빠뜨려보세요.
        # ------------------------------------------------------------------
        results: list[dict] = []
        for block in response.content:
            # 같은 응답에 text 블록이 섞여 있을 수 있다. tool_use 만 고른다.
            if block.type != "tool_use":
                continue

            output = dispatch(block.name, block.input)

            results.append(
                {
                    "type": "tool_result",
                    # 어느 호출에 대한 답인지. 한 턴에 도구가 여러 개면 이게 유일한 단서다.
                    "tool_use_id": block.id,
                    # content 는 문자열이어야 한다. dict 는 그대로 넣을 수 없다.
                    # ensure_ascii=False 는 한글이 이스케이프되지 않게 하려는 것.
                    "content": json.dumps(output, ensure_ascii=False),
                }
            )

        # ------------------------------------------------------------------
        # 빈칸 4 · 결과를 대화에 붙인다
        #
        # 여기가 제일 헷갈리는 지점입니다.
        # 도구 결과의 role 은 "user" 입니다. "tool" 이 아닙니다.
        #
        # 왜일까요? 모델 입장에서 도구 결과는 '바깥에서 들어온 정보' 이고,
        # 바깥에서 들어오는 것은 전부 user 턴이기 때문입니다.
        # 이 관점은 나중에 중요해집니다 — 도구 결과는 신뢰할 수 있는
        # 시스템 지시가 아니라, 검증이 필요한 입력이라는 뜻이니까요.
        # ------------------------------------------------------------------
        # role 은 "user". 이번 턴의 tool_result 를 한 메시지에 전부 담는다.
        # 하나라도 빠뜨리면 API 가 400 을 돌려준다.
        messages.append({"role": "user", "content": results})

        if verbose:
            for r in results:
                print(f"  → {r['content'][:70]}")

    else:
        return f"(MAX_TURNS={MAX_TURNS} 도달. 루프가 끝나지 않았습니다)"

    # 루프를 정상적으로 빠져나왔으면 마지막 응답에서 텍스트를 뽑습니다.
    return "\n".join(b.text for b in response.content if b.type == "text")


if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else (
        '다음 코드는 몇 줄이야?\n\nimport os\n\n# 현재 경로\nprint(os.getcwd())\n'
    )
    answer = run(question)
    print(f"\n{'=' * 60}\n{answer}")
