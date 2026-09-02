"""1단계 · 일단 한 번 불러본다.

    python step1_hello.py

이 파일은 완성돼 있습니다. 고칠 것 없이 실행하고, 그 다음 읽으세요.
실행 결과와 코드를 번갈아 보는 게 순서입니다.

여기서 확인할 것은 딱 하나입니다.
    "요청은 무엇을 담고, 응답은 무엇을 돌려주는가"
"""

import os

import anthropic

import env  # .env 로드 + 워크스페이스 헤더

client = anthropic.Anthropic(
    api_key=os.environ["ANTHROPIC_API_KEY"],
    # 사용자 키는 어느 워크스페이스로 보내는지 헤더로 알려줘야 합니다. env.py 참고.
    default_headers=env.workspace_headers(),
)

response = client.messages.create(
    # 어떤 모델을 쓸지. 개발 중에는 Sonnet 으로 충분합니다.
    model="claude-sonnet-5",
    # 응답 길이 상한. 이걸 넘으면 문장 중간에서 잘립니다.
    max_tokens=512,
    # 모델의 역할과 규칙. 매 요청마다 통째로 다시 보냅니다.
    # 모델은 지난 대화를 기억하지 못합니다. 상태는 전부 우리가 들고 있어야 합니다.
    system="당신은 파이썬을 가르치는 사람입니다. 짧고 정확하게 답합니다.",
    # 대화 내역. 지금은 한 턴짜리입니다.
    messages=[
        {"role": "user", "content": "파이썬에서 sorted() 와 list.sort() 는 무엇이 다른가요?"}
    ],
)

print("=" * 70)
print("응답 본문")
print("=" * 70)
# content 는 문자열이 아니라 '블록의 리스트' 입니다.
#
# [0] 을 그냥 꺼내면 안 됩니다. 최신 모델은 답하기 전에 스스로 생각하고,
# 그 흔적이 thinking 블록으로 리스트 맨 앞에 들어옵니다. thinking 블록에는
# .text 가 없으므로 [0].text 는 AttributeError 로 터집니다.
#
# 그래서 '몇 번째'가 아니라 'type 이 무엇인지'로 골라야 합니다.
# 도구를 붙이면 여기에 tool_use 블록까지 섞여 들어옵니다.
# 3단계에서 이 리스트가 왜 리스트인지 알게 됩니다.
print("\n".join(b.text for b in response.content if b.type == "text"))

print()
print("=" * 70)
print("응답 메타")
print("=" * 70)
print(f"stop_reason : {response.stop_reason}")
print(f"model       : {response.model}")
print(f"입력 토큰    : {response.usage.input_tokens:,}")
print(f"출력 토큰    : {response.usage.output_tokens:,}")

cost = (response.usage.input_tokens * 2 + response.usage.output_tokens * 10) / 1e6
print(f"이번 호출 비용: 약 ${cost:.5f}")

print()
print("―" * 70)
print("생각해볼 것")
print("―" * 70)
print("""
1. system 을 지우고 다시 돌려보세요. 답변이 어떻게 달라집니까?

2. max_tokens 를 30 으로 줄여보세요. stop_reason 이 무엇으로 바뀝니까?
   그 값이 의미하는 바는 무엇입니까?

3. messages 에 이전 대화를 넣지 않으면 모델은 그걸 모릅니다.
   그렇다면 여러 턴 대화는 누가 기억하고 있어야 합니까?
   (이 질문의 답이 4단계 루프의 전부입니다)
""")
