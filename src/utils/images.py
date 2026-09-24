"""图片工具：data URI 转换、打开图片

游戏把图片存成 "data:image/png;base64,...." 形式的字符串（再经 .sav 编码写入文件）。
这里的函数不涉及 Tk，可以在后台线程中调用。
"""

import base64
from io import BytesIO
from pathlib import Path
from typing import Optional, Union

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

ImageSource = Union[str, Path, Image.Image, bytes]


def is_image_file(path: Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def bytes_to_data_uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def image_to_data_uri(image: Image.Image, format: str = "PNG") -> str:
    """把 PIL 图片编码成 data URI 字符串"""
    buffer = BytesIO()
    image.save(buffer, format=format)
    return bytes_to_data_uri(buffer.getvalue(), f"image/{format.lower()}")


def data_uri_to_bytes(data_uri: object) -> bytes:
    """取出 data URI 里的图片字节

    Raises:
        ValueError: 不是 base64 形式的 data URI（binascii.Error 也是 ValueError 的子类）
    """
    if not isinstance(data_uri, str) or not data_uri.startswith("data:") or "," not in data_uri:
        raise ValueError("not a data URI")
    header, payload = data_uri.split(",", 1)
    if not header.endswith(";base64"):
        raise ValueError("data URI is not base64 encoded")
    return base64.b64decode(payload)


def open_image(source: ImageSource) -> Image.Image:
    """从文件路径 / data URI / 字节 / PIL 图片得到一个已完整载入内存的 PIL 图片

    载入后原文件就被关闭了（Windows 上文件被打开时无法删除）。

    Raises:
        OSError: 无法读取或不是图片（PIL 的 UnidentifiedImageError 是 OSError 的子类）
        ValueError: data URI 格式不对
    """
    if isinstance(source, Image.Image):
        return source
    if isinstance(source, str) and source.startswith("data:"):
        source = data_uri_to_bytes(source)
    if isinstance(source, bytes):
        source = BytesIO(source)
    with Image.open(source) as img:
        img.load()
        return img.copy()


def decode_image_data(data_uri: object) -> Optional[Image.Image]:
    """解码存档里的 data URI 图片，失败返回 None"""
    try:
        return open_image(data_uri) if isinstance(data_uri, str) else None
    except (OSError, ValueError):
        return None
