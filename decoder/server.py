"""웹 서버.

SSE 로 에이전트 이벤트를 그대로 흘려보낸다. 화면에서 Tool Calling 루프가
도는 모습을 실시간으로 보는 것이 목적이므로, 서버는 중간에서 가공하지 않는다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from .agent import DEFAULT_MODEL, DecodeError, decode
from .analyzer import analyze_code
from .docs import ALLOWED_THIRD_PARTY

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = Flask(__name__, static_folder=None)


@app.get("/")
def index() -> Response:
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/<path:filename>")
def assets(filename: str) -> Response:
    return send_from_directory(WEB_DIR, filename)


@app.get("/api/config")
def config():
    return jsonify(
        {
            "model": DEFAULT_MODEL,
            "has_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "third_party": sorted(ALLOWED_THIRD_PARTY),
        }
    )


@app.post("/api/analyze")
def analyze():
    """LLM 없이 AST 분석만. 4~5주차 결과를 눈으로 확인할 때 쓴다."""
    code = (request.get_json(silent=True) or {}).get("code", "")
    return jsonify(analyze_code(code))


@app.post("/api/decode")
def decode_endpoint():
    code = (request.get_json(silent=True) or {}).get("code", "")
    model = (request.get_json(silent=True) or {}).get("model") or DEFAULT_MODEL

    if not code.strip():
        return jsonify({"error": "코드가 비어 있습니다."}), 400

    def stream():
        try:
            for event in decode(code, model=model):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except DecodeError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def main() -> None:
    port = int(os.environ.get("PORT", "5001"))
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
