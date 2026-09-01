"""벤치마크 스니펫.

3주차에 확정하는 평가 기준이다. 이 5개를 고정해두고 매주 같은 것을 돌려
출력을 나란히 비교한다. 기준이 없으면 이터레이션이 취향 논쟁이 된다.

의도적으로 다른 종류의 실패를 유도하도록 골랐다.
스터디원이 실제로 막힌 코드가 생기면 그것으로 교체하는 편이 낫다.
"""

SNIPPETS: dict[str, dict[str, str]] = {
    "01_glob": {
        "why": "표준 라이브러리. 변수 타입을 알아야 .glob 의 정체를 알 수 있다.",
        "expect": "GEN_IMAGES_DIR.glob → pathlib.Path.glob 로 해석되어야 함",
        "code": '''from pathlib import Path

GEN_IMAGES_DIR = Path("./generated")
files = sorted(GEN_IMAGES_DIR.glob("*.png"))
''',
    },
    "02_thumbnail": {
        "why": "서드파티. 제자리 수정 + None 반환이라 반환값을 쓰면 버그.",
        "expect": "thumbnail 이 None 을 반환한다는 함정이 gotcha 에 잡혀야 함",
        "code": '''from PIL import Image

img = Image.open("photo.png")
img.thumbnail((800, 800))
img.save("thumb.png")
''',
    },
    "03_lru_cache": {
        "why": "데코레이터 문법. 호출이 아니라 감싸는 구조.",
        "expect": "maxsize=None 의 의미와 캐시 무한 증가 위험이 설명되어야 함",
        "code": '''import functools

@functools.lru_cache(maxsize=None)
def fib(n: int) -> int:
    return n if n < 2 else fib(n - 1) + fib(n - 2)
''',
    },
    "04_async_httpx": {
        "why": "async 문법 + 컨텍스트 매니저 + 서드파티가 한 줄에.",
        "expect": "async with 가 왜 필요한지(연결 정리)가 why 에 나와야 함",
        "code": '''import httpx

async def fetch_all(urls):
    async with httpx.AsyncClient() as client:
        results = []
        for url in urls:
            r = await client.get(url)
            results.append(r.json())
        return results
''',
    },
    "05_pandas_agg": {
        "why": "메서드 체이닝, 문자열로 넘기는 인자는 정적 분석이 못 본다.",
        "expect": '"mean" 이라는 문자열이 어떻게 함수로 해석되는지 설명되어야 함',
        "code": '''import pandas as pd

df = pd.read_csv("sales.csv")
summary = df.groupby("region").agg({"revenue": "mean", "units": "sum"})
''',
    },
}


def get(name: str) -> str:
    return SNIPPETS[name]["code"]


def all_names() -> list[str]:
    return sorted(SNIPPETS)
