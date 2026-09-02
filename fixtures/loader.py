from pathlib import Path


def load_all(directory):
    """디렉터리 안의 모든 텍스트 파일을 읽어 딕셔너리로 돌려준다."""
    result = {}
    for path in sorted(Path(directory).glob("*.txt")):
        result[path.name] = path.read_text(encoding="utf-8")
    return result
