"""数据提取模块

提供从存档数据中提取统计信息的功能
"""

import bisect
import logging
import urllib.parse
from pathlib import Path
from tkinter import font as tkfont
from typing import Dict, Any, Optional, Tuple, Union

from .constants import (
    TOTAL_STICKERS,
    STICKER_COLOR_THRESHOLDS,
    FANATIC_ROUTE_COLOR,
    NEO_FILENAME,
    NEO_GOOD_MESSAGE,
    NEO_BAD_MESSAGE,
    NEO_GOOD_COLOR,
    NEO_BAD_COLOR,
    NEO_DEFAULT_COLOR,
)

logger = logging.getLogger(__name__)


def get_progress_color(stickers_percent: float, is_fanatic_route: bool) -> str:
    """根据贴纸百分比和路线获取进度颜色
    
    Args:
        stickers_percent: 贴纸百分比 (0-100)
        is_fanatic_route: 是否为狂信徒路线
        
    Returns:
        颜色十六进制字符串
    """
    if is_fanatic_route:
        return FANATIC_ROUTE_COLOR
    
    # 阈值列表是降序排列的，我们需要找到第一个 >= percent 的阈值
    # 由于列表很小（只有5个元素），使用简单循环即可，性能差异可忽略
    for threshold, color in STICKER_COLOR_THRESHOLDS:
        if stickers_percent >= threshold:
            return color
    
    # 如果percent小于所有阈值，返回最后一个（默认蓝色）
    return STICKER_COLOR_THRESHOLDS[-1][1]


def is_fanatic_route(save_data: Dict[str, Any]) -> bool:
    """判断是否为狂信徒路线
    
    Args:
        save_data: 存档数据字典
        
    Returns:
        是否为狂信徒路线
    """
    if not save_data:
        return False
    
    kill_flag = save_data.get("kill", 0)
    killed_flag = save_data.get("killed", 0)
    return kill_flag == 1 or killed_flag == 1


def extract_sticker_data(save_data: Dict[str, Any]) -> Tuple[int, float]:
    """提取贴纸数据
    
    Args:
        save_data: 存档数据字典
        
    Returns:
        (collected_count, percent) 元组
    """
    if not save_data:
        return 0, 0.0
    
    sticker_list = save_data.get("sticker")
    if not isinstance(sticker_list, list):
        sticker_list = []
    
    collected_count = len(set(sticker_list))
    percent = (collected_count / TOTAL_STICKERS * 100.0) if TOTAL_STICKERS > 0 else 0.0
    return collected_count, percent


def extract_judge_data(save_data: Dict[str, Any]) -> Dict[str, int]:
    """提取判定统计数据
    
    Args:
        save_data: 存档数据字典
        
    Returns:
        包含perfect, good, bad的字典
    """
    if not save_data:
        return {"perfect": 0, "good": 0, "bad": 0}
    
    judge_counts = save_data.get("judgeCounts")
    if not isinstance(judge_counts, dict):
        judge_counts = {}
    
    def safe_int(value: Any, default: int = 0) -> int:
        """安全地将值转换为整数"""
        if isinstance(value, (int, float)):
            return int(value)
        return default
    
    return {
        "perfect": safe_int(judge_counts.get("perfect"), 0),
        "good": safe_int(judge_counts.get("good"), 0),
        "bad": safe_int(judge_counts.get("bad"), 0),
    }


def load_neo_content(storage_dir: str) -> Optional[Tuple[Optional[str], str]]:
    """加载NEO文件内容
    
    Args:
        storage_dir: 存储目录路径
        
    Returns:
        (neo_text, text_color) 元组，如果文件不存在或读取失败则返回None
        
    Raises:
        不抛出异常，失败时返回None并记录日志
    """
    if not storage_dir:
        return None
    
    neo_path = Path(storage_dir) / NEO_FILENAME
    if not neo_path.exists() or not neo_path.is_file():
        return None
    
    try:
        with open(neo_path, 'r', encoding='utf-8') as neo_file:
            encoded_content = neo_file.read().strip()
        
        if not encoded_content:
            return None
        
        decoded_content = urllib.parse.unquote(encoded_content)
        
        if decoded_content == NEO_GOOD_MESSAGE:
            return (None, NEO_GOOD_COLOR)
        elif decoded_content == NEO_BAD_MESSAGE:
            return (None, NEO_BAD_COLOR)
        else:
            return (decoded_content, NEO_DEFAULT_COLOR)
            
    except FileNotFoundError:
        logger.debug(f"NEO file not found: {neo_path}")
        return None
    except PermissionError as e:
        logger.warning(f"Permission denied reading NEO file: {neo_path}, error: {e}")
        return None
    except UnicodeDecodeError as e:
        logger.warning(f"Failed to decode NEO file as UTF-8: {neo_path}, error: {e}")
        return None
    except urllib.parse.UnquotePlusError as e:
        logger.warning(f"Failed to decode NEO file content: {neo_path}, error: {e}")
        return None
    except OSError as e:
        logger.warning(f"OS error reading NEO file: {neo_path}, error: {e}")
        return None


def create_font_object(font_spec: Union[tuple, tkfont.Font]) -> tkfont.Font:
    """创建字体对象
    
    Args:
        font_spec: 字体规格（元组(family, size)或字体对象）
        
    Returns:
        tkinter Font对象
        
    Raises:
        ValueError: 如果font_spec格式无效
    """
    if isinstance(font_spec, tuple):
        if len(font_spec) < 2:
            raise ValueError(f"Font tuple must have at least 2 elements, got {len(font_spec)}")
        return tkfont.Font(family=font_spec[0], size=font_spec[1])
    elif isinstance(font_spec, tkfont.Font):
        return tkfont.Font(font=font_spec)
    else:
        raise ValueError(f"Invalid font_spec type: {type(font_spec)}, expected tuple or Font")

