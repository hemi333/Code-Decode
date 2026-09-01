"""3단계 정답.

먼저 직접 해보고 나서 여세요. 답을 보고 짠 코드는 다음 주에 기억나지 않습니다.

정답이 하나만 있는 건 아닙니다. description 문구, 빈 줄 처리 방식은
팀마다 다를 수 있습니다. 아래는 한 가지 선택입니다.
"""

COUNT_LINES_TOOL = {
    "name": "count_lines",
    "description": (
        "파이썬 코드 문자열을 받아 줄 수를 센다. "
        "전체 줄 수와, 빈 줄과 주석을 제외한 실제 코드 줄 수를 함께 반환한다. "
        "코드의 길이를 물으면 눈으로 세거나 추측하지 말고 이 도구를 부른다."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "줄 수를 셀 파이썬 코드 전문",
            }
        },
        "required": ["code"],
    },
}


def count_lines(code: str) -> dict:
    """코드의 줄 수를 센다.

    마지막 개행 처리에 대한 선택:
        "a\\nb\\n".split("\\n") 은 ['a', 'b', ''] 를 돌려줍니다.
        마지막 빈 문자열은 '줄' 이 아니라 파일 끝 개행의 흔적이므로 세지 않습니다.
        에디터가 보여주는 줄 번호와 맞추는 쪽을 골랐습니다.
    """
    text = code.rstrip("\n")
    lines = text.split("\n") if text else []

    code_lines = [
        line for line in lines if line.strip() and not line.strip().startswith("#")
    ]

    return {"total": len(lines), "code": len(code_lines)}


TOOLS = [COUNT_LINES_TOOL]


def dispatch(name: str, payload: dict) -> dict:
    if name == "count_lines":
        try:
            return count_lines(payload["code"])
        except Exception as exc:  # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {exc}"}
    return {"error": f"알 수 없는 도구: {name}"}
