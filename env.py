"""`.env` 를 읽어 환경변수로 올립니다.

step1~4 를 실행하기 전에 자동으로 불립니다.
python-dotenv 를 안 깔아도 되도록 직접 파싱합니다.

`workspace_headers()` 하나만 밖에서 씁니다. 아래 설명을 보세요.
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


def workspace_headers() -> dict[str, str]:
    """사용자(identity)에 연결된 API 키를 쓸 때 필요한 헤더를 만듭니다.

    콘솔에서 발급하는 키에는 두 종류가 있습니다.

      - 워크스페이스 키 : 키 자체가 워크스페이스에 속합니다. 그냥 쓰면 됩니다.
      - 사용자 키       : 어느 워크스페이스로 보내는 요청인지 매번 알려줘야 합니다.
                          안 보내면 400 이 돌아옵니다.
                          "anthropic-workspace-id is required ..."

    `.env` 에 ANTHROPIC_WORKSPACE_ID 가 있으면 그 헤더를 붙이고,
    없거나 비어 있으면 빈 dict 를 돌려줍니다. 나중에 워크스페이스 키로
    바꾸더라도 코드는 고칠 것이 없습니다.
    """
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip()
    if not workspace_id:
        return {}
    return {"anthropic-workspace-id": workspace_id}
