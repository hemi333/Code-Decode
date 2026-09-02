from pathlib import Path

from PIL import Image

GEN_IMAGES_DIR = Path("./generated")


def make_thumbnails(size=(800, 800)):
    """생성된 이미지들의 썸네일을 만든다."""
    made = []
    for src in sorted(GEN_IMAGES_DIR.glob("*.png")):
        img = Image.open(src)
        img.thumbnail(size)
        target = src.with_suffix(".thumb.png")
        img.save(target)
        made.append(target)
    return made


def clear_thumbnails():
    for path in GEN_IMAGES_DIR.glob("*.thumb.png"):
        path.unlink()
