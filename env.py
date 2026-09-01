"""`.env` 를 읽어 환경변수로 올립니다.

step1~4 를 실행하기 전에 자동으로 불립니다. 직접 쓸 일은 없습니다.
python-dotenv 를 안 깔아도 되도록 직접 파싱합니다.
"""

import os
from pathlib import Path


def load() -> None:
    path = Path(__file__).resolve().parent / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


load()
