"""存档缩略图：解码 img_data、计算缩略图尺寸、缓存、占位图和完成状态圆点

这里的函数和 ImageCache 都可以在后台线程中调用（不涉及 Tk）。
"""

import hashlib
import logging
import platform
import threading
from collections import OrderedDict
from functools import lru_cache
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from src.utils.images import decode_image_data

logger = logging.getLogger(__name__)

Size = Tuple[int, int]

DEFAULT_THUMBNAIL_SIZE: Size = (120, 90)
_ASPECT_RATIO_4_3 = 4.0 / 3.0


def thumbnail_size(slot_size: Size, image_size: Optional[Size] = None) -> Size:
    """存档槽卡片中缩略图的尺寸：保持图片宽高比，最多占卡片宽度的 35%、高度的 85%"""
    slot_w, slot_h = slot_size
    if slot_w <= 0 or slot_h <= 0:
        return DEFAULT_THUMBNAIL_SIZE
    # 20 = 卡片内容区左右（或上下）各 10px 的内边距
    max_w = max(int(slot_w * 0.35) - 20, 80)
    max_h = max(int(slot_h * 0.85) - 20, 80)
    if image_size and image_size[1] > 0:
        ratio = image_size[0] / image_size[1]
    else:
        ratio = _ASPECT_RATIO_4_3
    width_by_height = int(max_h * ratio)
    if width_by_height <= max_w:
        return (width_by_height, max_h)
    return (max_w, int(max_w / ratio))


class ImageCache:
    """解码后的原图和缩略图的 LRU 缓存（线程安全）

    翻页时主界面、删除对话框和邻页预取可能同时在不同线程里读写，所以所有操作都加锁。
    """

    def __init__(self, max_originals: int = 12, max_thumbnails: int = 120) -> None:
        self._lock = threading.Lock()
        self._originals: "OrderedDict[str, Image.Image]" = OrderedDict()
        self._thumbnails: "OrderedDict[Tuple[str, Size], Image.Image]" = OrderedDict()
        self._max_originals = max_originals
        self._max_thumbnails = max_thumbnails

    def _get(self, store: OrderedDict, key) -> Optional[Image.Image]:
        with self._lock:
            image = store.get(key)
            if image is not None:
                store.move_to_end(key)
            return image

    def _put(self, store: OrderedDict, key, image: Image.Image, max_size: int) -> None:
        with self._lock:
            store[key] = image
            store.move_to_end(key)
            while len(store) > max_size:
                store.popitem(last=False)

    def get_thumbnail(self, image_data: str, slot_size: Size) -> Optional[Image.Image]:
        """返回适合放进 slot_size 大小的存档槽卡片的缩略图；图片无法解码时返回 None"""
        if not isinstance(image_data, str):
            return None
        # 用 md5 而不是 base64 字符串本身作键：缓存就不会一直引用几百 KB 的字符串
        # （重新读文件后旧字符串可以被释放）；算 md5 比解码图片快得多
        key = hashlib.md5(image_data.encode("utf-8")).hexdigest()
        original = self._get(self._originals, key)
        if original is None:
            original = decode_image_data(image_data)
            if original is None:
                return None
            self._put(self._originals, key, original, self._max_originals)

        size = thumbnail_size(slot_size, original.size)
        thumbnail = self._get(self._thumbnails, (key, size))
        if thumbnail is None:
            thumbnail = original.resize(size, Image.Resampling.BILINEAR)
            self._put(self._thumbnails, (key, size), thumbnail, self._max_thumbnails)
        return thumbnail

    def clear(self) -> None:
        with self._lock:
            self._originals.clear()
            self._thumbnails.clear()


def slot_thumbnail(image_data: Optional[str], slot_size: Size, cache: ImageCache,
                   no_image_text: str, decode_failed_text: str) -> Image.Image:
    """存档槽要显示的图片：缩略图，或者写着原因的灰色占位图"""
    if not image_data:
        return create_placeholder_image(thumbnail_size(slot_size), no_image_text)
    thumbnail = cache.get_thumbnail(image_data, slot_size)
    if thumbnail is None:
        return create_placeholder_image(thumbnail_size(slot_size), decode_failed_text)
    return thumbnail


def _font_paths(prefer_cjk: bool) -> list:
    system_name = platform.system()
    if system_name == "Windows":
        cjk = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc", "C:/Windows/Fonts/simhei.ttf"]
    elif system_name == "Darwin":
        cjk = ["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Light.ttc"]
    else:
        cjk = ["/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "/usr/share/fonts/truetype/arphic/uming.ttc"]
    return cjk + ["arial.ttf"] if prefer_cjk else ["arial.ttf"] + cjk


@lru_cache(maxsize=None)
def _load_font(size: int, prefer_cjk: bool):
    for path in _font_paths(prefer_cjk):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _has_cjk(text: str) -> bool:
    return any('\u4e00' <= c <= '\u9fff' or '\u3040' <= c <= '\u30ff' or '\uac00' <= c <= '\ud7a3'
               for c in text)


@lru_cache(maxsize=64)
def create_placeholder_image(size: Size, text: str) -> Image.Image:
    """浅灰底、居中灰字的占位图（结果会被缓存，调用方不要修改返回的图片）"""
    if size[0] <= 0 or size[1] <= 0:
        raise ValueError(f"Invalid size: {size}")
    text = text or ""
    image = Image.new('RGB', size, color='lightgray')
    draw = ImageDraw.Draw(image)
    font_size = max(10, min(size[0] // len(text) if text else 12, size[1] // 4))
    font = _load_font(font_size, _has_cjk(text))
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(((size[0] - (right - left)) // 2, (size[1] - (bottom - top)) // 2), text, fill='gray', font=font)
    return image


@lru_cache(maxsize=16)
def create_status_circle_image(diameter: int, is_active: bool) -> Image.Image:
    """事件完成状态的圆点：已完成为青到粉的竖向渐变，未完成为深色，都带金色描边"""
    if diameter <= 0:
        raise ValueError(f"Diameter must be positive, got {diameter}")
    padding = 2
    size = diameter + padding * 2
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    center = size // 2
    radius = diameter // 2
    bbox = [center - radius, center - radius, center + radius, center + radius]

    if is_active:
        start, end = (107, 176, 168), (226, 80, 141)
        top, bottom = center - radius, center + radius
        for y in range(top, bottom + 1):
            progress = (y - top) / (bottom - top) if bottom > top else 0.0
            color = tuple(int(s + (e - s) * progress) for s, e in zip(start, end)) + (255,)
            dx = int((radius ** 2 - (y - center) ** 2) ** 0.5)
            draw.line([(center - dx, y), (center + dx, y)], fill=color, width=1)
    else:
        draw.ellipse(bbox, fill=(34, 37, 54, 255))

    draw.ellipse(bbox, outline='#E1C183', width=2)
    return image
