"""2단계 · 응답을 해부한다.

    python step2_anatomy.py

이 파일도 완성돼 있습니다. 도구를 하나 붙인 채로 요청을 보내고,
응답이 어떻게 생겼는지 있는 그대로 찍어봅니다.

이번 주 체크포인트가 여기 있습니다.
    "모델이 tool_use 를 반환하는 걸 눈으로 확인한다"

주의: 도구를 '정의'만 했지 '실행'은 하지 않습니다.
모델이 도구를 부르겠다고 말하는 데서 멈춥니다. 그 다음이 4단계입니다.
"""

import json
import os

import anthropic

import env  # .env 로드 + 워크스페이스 헤더

client = anthropic.Anthropic(
    api_key=os.environ["ANTHROPIC_API_KEY"],
    # 사용자 키는 어느 워크스페이스로 보내는지 헤더로 알려줘야 합니다. env.py 참고.
    default_headers=env.workspace_headers(),
)

# ---------------------------------------------------------------------------
# 도구 정의
#
# 모델은 이 딕셔너리만 보고 언제 이 도구를 부를지 정합니다.
# description 이 곧 프롬프트라는 뜻입니다. 함수 이름이 아니라 설명을 잘 써야 합니다.
#
# 이 도구를 고른 이유가 있습니다. 모델은 여러분 컴퓨터의 파이썬 버전을
# 알 방법이 없습니다. 그러니 답이 맞으면 반드시 도구를 부른 것입니다.
# 도구를 정말 썼는지 눈으로 확인할 수 있는 도구여야 합니다.
# ---------------------------------------------------------------------------

PYTHON_ENV_TOOL = {
    "name": "python_env",
    "description": (
        "이 코드가 돌고 있는 컴퓨터의 파이썬 실행 환경 정보를 반환한다. "
        "버전, 운영체제, 설치된 주요 패키지 버전을 알려준다. "
        "사용자가 '지금 이 환경' 에 대해 물으면 추측하지 말고 이 도구를 부른다."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},  # 입력이 필요 없는 도구입니다
        "required": [],
    },
}


def ask(question: str, *, with_tools: bool) -> None:
    print("=" * 74)
    print(f"질문: {question}")
    print(f"도구: {'붙임' if with_tools else '안 붙임'}")
    print("=" * 74)

    kwargs = {
        "model": "claude-sonnet-5",
        "max_tokens": 512,
        "messages": [{"role": "user", "content": question}],
    }
    if with_tools:
        kwargs["tools"] = [PYTHON_ENV_TOOL]

    response = client.messages.create(**kwargs)

    print(f"\nstop_reason: {response.stop_reason}")
    print(f"블록 개수  : {len(response.content)}\n")

    for i, block in enumerate(response.content):
        print(f"── 블록 {i} · type={block.type} " + "─" * 40)

        if block.type == "text":
            print(block.text.strip())

        elif block.type == "tool_use":
            # 이 세 개가 핵심입니다.
            #   id    — 나중에 결과를 돌려줄 때 이 id 로 짝을 맞춥니다
            #   name  — 어떤 도구를 부르려는지
            #   input — 어떤 인자로 부르려는지 (스키마에 맞춰 모델이 만들어냅니다)
            print(f"id    : {block.id}")
            print(f"name  : {block.name}")
            print(f"input : {json.dumps(block.input, ensure_ascii=False)}")

        print()


if __name__ == "__main__":
    question = "지금 이 컴퓨터의 파이썬 버전이 뭐야?"

    # 1) 도구 없이. 모델은 알 수 없으니 모른다고 하거나 지어냅니다.
    ask(question, with_tools=False)

    print("\n\n")

    # 2) 도구를 붙이고. stop_reason 이 tool_use 로 바뀝니다.
    ask(question, with_tools=True)

    print("―" * 74)
    print("""
확인할 것

1. 도구를 붙였을 때 stop_reason 이 무엇으로 바뀌었습니까?
   end_turn 과 tool_use 는 각각 무슨 뜻입니까?

2. 도구를 붙인 응답의 블록 개수가 1개가 아닐 수도 있습니다.
   여러 번 돌려보고, text 블록과 tool_use 블록이 함께 오는 경우를 찾아보세요.
   content 가 왜 리스트인지 여기서 답이 나옵니다.

3. 모델이 도구를 부르겠다고 말했지만, 아직 아무것도 실행되지 않았습니다.
   지금 대화는 어정쩡하게 멈춰 있습니다.
   이걸 이어가려면 우리가 무엇을 해야 합니까?

4. description 을 "환경 정보를 반환한다" 한 줄로 줄여보세요.
   모델이 여전히 도구를 부릅니까? 언제 안 부릅니까?
""")

# ==========================================================================
# 질문: 지금 이 컴퓨터의 파이썬 버전이 뭐야?
# 도구: 안 붙임
# ==========================================================================

# stop_reason: end_turn
# 블록 개수  : 1

# ── 블록 0 · type=text ────────────────────────────────────────
# 죄송하지만 저는 사용자의 컴퓨터에 직접 접근할 수 없어서, 현재 사용 중인 컴퓨터의 파이썬 버전을 확인해드릴 수 없습니다.

# 파이썬 버전을 확인하려면 다음 방법을 사용해보세요:

# **터미널/명령 프롬프트에서 확인:**
# ```bash
# python --version
# ```
# 또는
# ```bash
# python3 --version
# ```

# **파이썬 인터프리터 내에서 확인:**
# ```python
# import sys
# print(sys.version)
# ```

# **운영체제별 참고사항:**
# - Windows: 명령 프롬프트(cmd)나 PowerShell 사용
# - Mac/Linux: 터미널 사용
# - 여러 버전이 설치되어 있다면 `python`과 `python3` 명령어 결과가 다를 수 있습니다

# 명령어를 실행하시고 결과를 알려주시면, 그에 대한 추가 설명이나 도움을 드릴 수 있습니다!




# ==========================================================================
# 질문: 지금 이 컴퓨터의 파이썬 버전이 뭐야?
# 도구: 붙임
# ==========================================================================

# stop_reason: tool_use
# 블록 개수  : 1

# ── 블록 0 · type=tool_use ────────────────────────────────────────
# id    : toolu_01Aw7w13f7Nvq1Yg2FReGCcD
# name  : python_env
# input : {}

# ――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――
