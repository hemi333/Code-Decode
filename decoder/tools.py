"""Tool 정의와 디스패치.

Tool 은 두 개뿐이다. 4주차와 5~7주차의 산출물이 각각 하나씩이다.
스키마의 description 이 곧 프롬프트라는 점에 주의할 것 — 모델은 이 문장만 보고
언제 이 도구를 부를지 정한다.
"""

from __future__ import annotations

from typing import Any

from .analyzer import analyze_code
from .docs import lookup_many

TOOLS: list[dict[str, Any]] = [
    {
        "name": "analyze_code",
        "description": (
            "파이썬 코드를 AST 로 파싱해 학습 대상을 추출한다. "
            "함수 호출, 속성 접근, 데코레이터, 문법 요소를 찾아내고 "
            "가능한 경우 정규화된 경로(pathlib.Path.glob 등)까지 해석한다. "
            "해석에 실패한 심볼은 qualname 이 null 이고 receiver_origin 에 단서가 담긴다. "
            "코드를 받으면 가장 먼저 이 도구를 부른다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "분석할 파이썬 코드 전문"}
            },
            "required": ["code"],
        },
    },
    {
        "name": "lookup_documentation",
        "description": (
            "심볼의 공식 문서를 가져온다. 시그니처, docstring, 문서 URL 을 반환한다. "
            "analyze_code 가 해석한 qualname 을 그대로 넘긴다. "
            "여러 개를 배열로 한 번에 넘길 수 있고, 그렇게 하는 편이 낫다. "
            "표준 라이브러리와 허용된 서드파티만 조회되며, 그 외에는 found=false 로 답한다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "qualnames": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "정규화된 경로 목록. 예: ['pathlib.Path.glob', 'sorted']",
                }
            },
            "required": ["qualnames"],
        },
    },
]


def dispatch(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """도구를 실행한다. 예외를 밖으로 던지지 않는다 — 루프가 멈추면 안 된다."""
    try:
        if name == "analyze_code":
            return analyze_code(payload["code"])
        if name == "lookup_documentation":
            return lookup_many(payload["qualnames"])
        return {"error": f"알 수 없는 도구: {name}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


__all__ = ["TOOLS", "dispatch"]
