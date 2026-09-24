"""图片工具模块

图片解码、占位图生成、状态圆绘制等功能
"""

import base64
import logging
import platform
from io import BytesIO
from typing import Optional, Tuple, Dict

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

logger = logging.getLogger(__name__)

BASE64_SEPARATOR: str = ';base64,'
ASPECT_RATIO_4_3: float = 4.0 / 3.0
DEFAULT_FONT_SIZE: int = 12
FONT_SIZE_MIN: int = 10
FONT_SIZE_DIVISOR: int = 4
PLACEHOLDER_COLOR: str = 'lightgray'
TEXT_COLOR_GRAY: str = 'gray'

STATUS_CIRCLE_BORDER_COLOR: str = '#E1C183'
STATUS_CIRCLE_ACTIVE_START: Tuple[int, int, int] = (107, 176, 168)
STATUS_CIRCLE_ACTIVE_END: Tuple[int, int, int] = (226, 80, 141)
STATUS_CIRCLE_INACTIVE: Tuple[int, int, int] = (34, 37, 54)
STATUS_CIRCLE_BORDER_WIDTH: int = 2
STATUS_CIRCLE_PADDING: int = 2


def extract_base64_data(image_data: str) -> Optional[str]:
    """从data URI中提取base64数据部分"""
    if not isinstance(image_data, str) or not image_data:
        return None
    
    sep_pos = image_data.find(BASE64_SEPARATOR)
    if sep_pos == -1:
        return None
    
    base64_part = image_data[sep_pos + len(BASE64_SEPARATOR):]
    if not base64_part:
        return None
    
    return base64_part


def decode_base64_to_bytes(base64_data: str) -> Optional[bytes]:
    """将base64字符串解码为字节"""
    try:
        image_bytes = base64.b64decode(base64_data, validate=True)
        return image_bytes if image_bytes else None
    except (ValueError, base64.binascii.Error):
        return None


def load_image_from_bytes(image_bytes: bytes) -> Optional[Image.Image]:
    """从字节数据加载PIL Image"""
    try:
        with BytesIO(image_bytes) as buffer:
            image = Image.open(buffer)
            return image.copy()
    except (UnidentifiedImageError, OSError, IOError):
        return None


def decode_image_data(image_data: str) -> Optional[Image.Image]:
    """解码base64图片数据"""
    base64_data = extract_base64_data(image_data)
    if not base64_data:
        return None
    
    image_bytes = decode_base64_to_bytes(base64_data)
    if not image_bytes:
        return None
    
    return load_image_from_bytes(image_bytes)


def _get_cjk_font_paths() -> list[str]:
    """获取支持CJK字符的字体文件路径列表（基于平台）"""
    system_name = platform.system()
    
    if system_name == "Windows":
        return [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simsun.ttc",
            "C:/Windows/Fonts/simhei.ttf",
        ]
    elif system_name == "Darwin":
        return [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
        ]
    else:
        return [
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/truetype/arphic/uming.ttc",
        ]


def get_placeholder_font(size: Tuple[int, int], text: str) -> ImageFont.FreeTypeFont:
    """获取占位图字体"""
    has_cjk = any(
        '\u4e00' <= char <= '\u9fff' or
        '\u3040' <= char <= '\u309f' or
        '\u30a0' <= char <= '\u30ff' or
        '\uac00' <= char <= '\ud7a3'
        for char in text
    )
    
    font_size = max(FONT_SIZE_MIN, min(
        size[0] // len(text) if text else DEFAULT_FONT_SIZE,
        size[1] // FONT_SIZE_DIVISOR
    ))
    
    font_candidates = (
        _get_cjk_font_paths() + ["arial.ttf"] if has_cjk
        else ["arial.ttf"] + _get_cjk_font_paths()
    )
    
    for font_path in font_candidates:
        try:
            return ImageFont.truetype(font_path, font_size)
        except (OSError, IOError):
            continue
    
    return ImageFont.load_default()


def create_placeholder_image(size: Tuple[int, int], text: str) -> Image.Image:
    """创建灰色占位图
    
    Raises:
        ValueError: 当尺寸无效时
    """
    if size[0] <= 0 or size[1] <= 0:
        raise ValueError(f"Invalid size: {size}")
    
    display_text = text or ""
    
    placeholder_img = Image.new('RGB', size, color=PLACEHOLDER_COLOR)
    draw = ImageDraw.Draw(placeholder_img)
    
    font = get_placeholder_font(size, display_text)
    
    bbox = draw.textbbox((0, 0), display_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    text_x = (size[0] - text_width) // 2
    text_y = (size[1] - text_height) // 2
    
    draw.text((text_x, text_y), display_text, fill=TEXT_COLOR_GRAY, font=font)
    
    return placeholder_img


def create_status_circle_image(
    diameter: int,
    is_active: bool,
    circle_cache: Optional[Dict[Tuple[int, bool], Image.Image]] = None
) -> Image.Image:
    """创建状态圆圈图片
    
    Raises:
        ValueError: 当直径小于等于0时
    """
    if diameter <= 0:
        raise ValueError(f"Diameter must be positive, got {diameter}")
    
    cache_key = (diameter, is_active)
    if circle_cache and cache_key in circle_cache:
        return circle_cache[cache_key]
    
    size = diameter + STATUS_CIRCLE_PADDING * 2
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    center = size // 2
    radius = diameter // 2
    bbox = [center - radius, center - radius, center + radius, center + radius]
    
    if is_active:
        start_color = STATUS_CIRCLE_ACTIVE_START
        end_color = STATUS_CIRCLE_ACTIVE_END
        
        top_y = center - radius
        bottom_y = center + radius
        
        for y in range(top_y, bottom_y + 1):
            progress = (y - top_y) / (bottom_y - top_y) if bottom_y > top_y else 0.0
            
            r = int(start_color[0] + (end_color[0] - start_color[0]) * progress)
            g = int(start_color[1] + (end_color[1] - start_color[1]) * progress)
            b = int(start_color[2] + (end_color[2] - start_color[2]) * progress)
            color = (r, g, b, 255)
            
            dy = y - center
            if abs(dy) <= radius:
                dx = int((radius ** 2 - dy ** 2) ** 0.5)
                x_start = center - dx
                x_end = center + dx
                draw.line([(x_start, y), (x_end, y)], fill=color, width=1)
    else:
        fill_color = STATUS_CIRCLE_INACTIVE + (255,)
        draw.ellipse(bbox, fill=fill_color)
    
    draw.ellipse(
        bbox,
        outline=STATUS_CIRCLE_BORDER_COLOR,
        width=STATUS_CIRCLE_BORDER_WIDTH
    )
    
    if circle_cache is not None:
        circle_cache[cache_key] = img
    
    return img
