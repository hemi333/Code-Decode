#!/usr/bin/env python3
"""진입점.  python run.py  →  http://127.0.0.1:5001"""

from pathlib import Path


def load_env() -> None:
    """python-dotenv 가 없어도 돌아가도록 .env 를 직접 읽는다."""
    env = Path(__file__).parent / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        import os

        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


if __name__ == "__main__":
    load_env()
    from decoder.server import main

    print("Code Decode → http://127.0.0.1:" + __import__("os").environ.get("PORT", "5001"))
    main()
