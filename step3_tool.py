"""3단계 · 도구를 직접 정의한다.  ← 여기부터 여러분이 씁니다

    python check.py 3     # 채점

2단계의 python_env 는 입력이 없는 도구였습니다. 이제 입력을 받는 도구를 만듭니다.

만들 도구: count_lines
    코드 문자열을 받아 줄 수를 센다.

일부러 시시한 도구를 골랐습니다. 이번 주의 주제는 도구가 아니라 루프입니다.
도구가 복잡하면 루프가 안 보입니다. 진짜 도구는 4주차부터 만듭니다.

빈칸은 두 군데입니다. TODO 를 찾으세요.
"""

# ---------------------------------------------------------------------------
# 빈칸 1 · 도구 스키마
#
# input_schema 는 JSON Schema 입니다. 모델은 이걸 보고 어떤 인자를 만들지 정합니다.
# 필요한 것:
#   - code 라는 문자열 파라미터 하나
#   - 그 파라미터는 필수
#   - 각 파라미터에 description 을 달 것 (모델이 읽습니다. 빼먹으면 엉뚱한 걸 넣습니다)
#
# 참고할 것: step2_anatomy.py 의 PYTHON_ENV_TOOL
#           https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
# ---------------------------------------------------------------------------

COUNT_LINES_TOOL = {
    "name": "count_lines",
    "description": (
        "파이썬 코드 문자열을 받아 줄 수를 센다. "
        "전체 줄 수(total)와, 빈 줄과 주석 줄을 제외한 실제 코드 줄 수(code)를 "
        "함께 돌려준다. "
        "코드가 몇 줄인지 묻는 질문에는 눈대중으로 세거나 추측하지 말고 "
        "반드시 이 도구를 부를 것."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": (
                    "줄 수를 셀 파이썬 소스 코드 전문. "
                    "일부만 잘라 넣지 말고 사용자가 준 코드를 그대로 넣을 것."
                ),
            },
        },
        "required": ["code"],
    },
}


# ---------------------------------------------------------------------------
# 빈칸 2 · 도구 구현
#
# 모델이 부를 실제 함수입니다. 스키마와 시그니처가 맞아야 합니다.
#
# 한 가지 규칙: 예외를 밖으로 던지지 마세요.
# 도구가 터지면 에이전트 루프 전체가 멈춥니다. 실패도 값으로 돌려줘야
# 모델이 그 실패를 읽고 다음 수를 정할 수 있습니다.
# ---------------------------------------------------------------------------


def count_lines(code: str) -> dict:
    """코드의 줄 수를 센다.

    반환 형태 (이대로 맞춰주세요):
        {"total": 전체 줄 수, "code": 빈 줄과 주석을 뺀 줄 수}

    힌트:
        - "a\\nb".split("\\n") 이 무엇을 돌려주는지 확인해보세요.
        - 마지막에 개행이 있는 코드와 없는 코드에서 결과가 달라집니다.
          어느 쪽이 맞는 답입니까? 여러분이 정하고, 그 이유를 주석에 남기세요.
    """
    # split("\n") 이 아니라 splitlines() 를 쓴다.
    #   "a\nb".split("\n")     -> ["a", "b"]       (2)
    #   "a\nb\n".split("\n")   -> ["a", "b", ""]   (3)  <- 빈 줄이 하나 생긴다
    #   "a\nb\n".splitlines()  -> ["a", "b"]       (2)
    #
    # Why: 마지막 개행을 세지 않기로 정했다. 파일 끝의 개행은
    #      "새 줄의 시작"이 아니라 "마지막 줄의 끝"을 뜻하기 때문이다.
    #      에디터가 보여주는 줄 번호와도 이쪽이 맞는다.
    lines = code.splitlines()

    # 같은 근거의 연장으로, 끝에 붙은 빈 줄도 세지 않는다.
    # 덕분에 "" 와 "\n\n\n" 이 둘 다 0 줄로 일관되게 나온다.
    while lines and not lines[-1].strip():
        lines.pop()

    code_lines = 0
    for line in lines:
        stripped = line.strip()
        # 빈 줄과 # 로 시작하는 줄은 코드로 세지 않는다.
        # (문자열 안의 # 이나 docstring 은 구분하지 못한다. 진짜 파싱은 4주차 AST 의 몫이다.)
        if stripped and not stripped.startswith("#"):
            code_lines += 1

    return {"total": len(lines), "code": code_lines}


# ---------------------------------------------------------------------------
# 디스패치 — 이건 채워뒀습니다
#
# 모델은 "count_lines 를 이 인자로 불러줘" 라고 이름과 인자만 말합니다.
# 그 이름을 실제 함수에 연결하는 게 이 함수입니다.
# ---------------------------------------------------------------------------

TOOLS = [COUNT_LINES_TOOL]


def dispatch(name: str, payload: dict) -> dict:
    if name == "count_lines":
        try:
            return count_lines(payload["code"])
        except Exception as exc:  # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {exc}"}
    return {"error": f"알 수 없는 도구: {name}"}


if __name__ == "__main__":
    sample = "import os\n\n# 주석\nprint(os.getcwd())\n"
    print("입력:")
    print(repr(sample))
    print("\n결과:")
    print(dispatch("count_lines", {"code": sample}))
