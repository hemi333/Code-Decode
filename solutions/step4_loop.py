"""4단계 정답.

빈칸 4개가 채워진 상태입니다. 채운 부분에 ★ 표시를 해뒀습니다.

이 20줄 남짓이 에이전트의 전부입니다. 앞으로 도구가 늘고 프롬프트가 길어져도
이 구조는 바뀌지 않습니다. 6주차의 Code Decode Agent 도 같은 루프를 씁니다.
"""

import json
import os
import sys

import anthropic

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
import env  # noqa: E402,F401  (.env 로드)

try:
    from solutions.step3_tool import TOOLS, dispatch
except ImportError:
    from step3_tool import TOOLS, dispatch

MODEL = "claude-sonnet-5"
MAX_TURNS = 6

SYSTEM = """당신은 코드에 대한 질문에 답합니다.
줄 수처럼 세어봐야 아는 것은 추측하지 말고 도구를 부르세요."""


def run(question: str, verbose: bool = True, client=None) -> str:
    client = client or anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        default_headers=env.workspace_headers(),
    )

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

        # ★ 빈칸 1 — 종료 조건
        #
        # content 를 뒤져서 tool_use 블록을 찾아도 결과는 같습니다. 다만
        # stop_reason 은 모델이 "왜 멈췄는지"를 직접 말해주는 값입니다.
        # max_tokens 로 잘린 경우처럼 우리가 미처 생각 못 한 상황도 여기 나타납니다.
        # 남의 자료구조를 추론하는 것보다 남이 알려준 이유를 읽는 편이 낫습니다.
        if response.stop_reason != "tool_use":
            break

        # ★ 빈칸 2 — 모델의 말을 대화에 남긴다
        #
        # content 를 통째로 넣습니다. tool_use 블록의 id 가 살아 있어야
        # 아래에서 만드는 tool_result 와 짝이 맞습니다.
        messages.append({"role": "assistant", "content": response.content})

        # ★ 빈칸 3 — 도구 실행
        results: list[dict] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            output = dispatch(block.name, block.input)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,  # 이 id 로 짝을 맞춥니다
                    "content": json.dumps(output, ensure_ascii=False),
                }
            )

        # ★ 빈칸 4 — 결과를 대화에 붙인다. role 은 "user".
        messages.append({"role": "user", "content": results})

        if verbose:
            for r in results:
                print(f"  → {r['content'][:70]}")

    else:
        return f"(MAX_TURNS={MAX_TURNS} 도달. 루프가 끝나지 않았습니다)"

    return "\n".join(b.text for b in response.content if b.type == "text")


if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else (
        '다음 코드는 몇 줄이야?\n\nimport os\n\n# 현재 경로\nprint(os.getcwd())\n'
    )
    print(f"\n{'=' * 60}\n{run(question)}")
