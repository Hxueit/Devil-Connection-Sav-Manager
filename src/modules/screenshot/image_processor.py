"""图片处理服务模块

提供图片处理相关的功能，包括宽高比检查、base64编码/解码等
"""

import base64
import json
import logging
import urllib.parse
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

# 常量定义
ASPECT_RATIO_TOLERANCE: int = 30
ASPECT_RATIO: float = 4.0 / 3.0
BASE64_SEPARATOR: str = ';base64,'


def check_aspect_ratio(image_path: Path) -> bool:
    """检查图片是否为4:3比例
    
    Args:
        image_path: 图片路径
        
    Returns:
        如果是4:3比例返回True，否则返回False
    """
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            expected_height = width * (1 / ASPECT_RATIO)
            return abs(height - expected_height) <= ASPECT_RATIO_TOLERANCE
    except (OSError, IOError, UnidentifiedImageError) as e:
        logger.debug(f"Failed to check aspect ratio for {image_path}: {e}")
        return False


def extract_image_from_sav(sav_file_path: Path) -> Optional[Image.Image]:
    """从SAV文件中提取图片
    
    Args:
        sav_file_path: SAV文件路径
        
    Returns:
        PIL Image对象，如果提取失败返回None
    """
    try:
        with open(sav_file_path, 'r', encoding='utf-8') as f:
            encoded = f.read().strip()
        
        unquoted = urllib.parse.unquote(encoded)
        data_uri = json.loads(unquoted)
        
        sep_pos = data_uri.find(BASE64_SEPARATOR)
        if sep_pos == -1:
            logger.debug("Invalid data URI format: missing base64 separator")
            return None
        
        b64_part = data_uri[sep_pos + len(BASE64_SEPARATOR):]
        img_data = base64.b64decode(b64_part)
        
        return Image.open(BytesIO(img_data))
    except (OSError, IOError, json.JSONDecodeError, ValueError, UnidentifiedImageError) as e:
        logger.debug(f"Failed to extract image from {sav_file_path}: {e}")
        return None


def encode_image_to_base64(image: Image.Image, format: str = "PNG") -> str:
    """将PIL Image编码为base64 data URI
    
    Args:
        image: PIL Image对象
        format: 图片格式（PNG, JPEG等）
        
    Returns:
        base64编码的data URI字符串
    """
    buffer = BytesIO()
    image.save(buffer, format=format)
    img_bytes = buffer.getvalue()
    b64_data = base64.b64encode(img_bytes).decode('utf-8')
    return f"data:image/{format.lower()};base64,{b64_data}"




