"""图片与 data URI 之间的转换

游戏把图片存成 "data:image/png;base64,...." 形式的字符串（再经 .sav 编码写入文件）。
"""

import base64
from io import BytesIO

from PIL import Image


def encode_image_to_base64(image: Image.Image, format: str = "PNG") -> str:
    """把 PIL 图片编码成 data URI 字符串"""
    buffer = BytesIO()
    image.save(buffer, format=format)
    return bytes_to_data_uri(buffer.getvalue(), f"image/{format.lower()}")


def bytes_to_data_uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


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
