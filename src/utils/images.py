"""图片和 data URI 的转换。游戏把图片存成 "data:image/png;base64,..." 字符串"""

import base64
from io import BytesIO
from pathlib import Path

from PIL import Image

# 选择图片文件时允许的扩展名
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.apng', '.tiff', '.tif', '.ico'}

# 文件选择框的类型过滤
IMAGE_FILE_TYPES = [
    ("Image files", "*.png *.jpg *.jpeg *.gif *.apng *.webp *.bmp"),
    ("PNG files", "*.png"),
    ("JPEG files", "*.jpg *.jpeg"),
    ("All files", "*.*"),
]

ImageSource = str | Path | Image.Image | bytes


def is_image_file(path: Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def bytes_to_data_uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def image_to_data_uri(image: Image.Image, format: str = "PNG") -> str:
    buffer = BytesIO()
    image.save(buffer, format=format)
    return bytes_to_data_uri(buffer.getvalue(), f"image/{format.lower()}")


def data_uri_to_bytes(data_uri: object) -> bytes:
    if not isinstance(data_uri, str) or not data_uri.startswith("data:") or "," not in data_uri:
        raise ValueError("not a data URI")
    header, payload = data_uri.split(",", 1)
    if not header.endswith(";base64"):
        raise ValueError("data URI is not base64 encoded")
    return base64.b64decode(payload)


def open_image(source: ImageSource) -> Image.Image:
    """得到完整载入内存的图片，原文件随即关闭（Windows 上文件开着就删不掉）"""
    if isinstance(source, Image.Image):
        return source
    if isinstance(source, str) and source.startswith("data:"):
        source = data_uri_to_bytes(source)
    if isinstance(source, bytes):
        source = BytesIO(source)
    with Image.open(source) as img:
        img.load()
        return img.copy()


def decode_image_data(data_uri: object) -> Image.Image | None:
    try:
        return open_image(data_uri_to_bytes(data_uri))
    except (OSError, ValueError):
        return None
