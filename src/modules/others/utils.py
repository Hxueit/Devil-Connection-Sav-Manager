"""其他功能模块工具函数

提供通用的工具函数，如日期格式化、窗口布局等。
"""
import logging
import re
from tkinter import TclError
from typing import TYPE_CHECKING, Final
from src.modules.others.config import OthersTabConfig

if TYPE_CHECKING:
    import customtkinter as ctk

logger = logging.getLogger(__name__)

# 时区和毫秒的正则表达式模式
_TIMEZONE_PATTERN: Final[re.Pattern[str]] = re.compile(r'[Z+\-]|\.\d+')


def format_release_date(published_at: str) -> str:
    """
    格式化GitHub发布的ISO日期时间字符串为可读格式
    
    Args:
        published_at: ISO格式的日期时间字符串 (例如: "2024-01-01T12:00:00Z")
        
    Returns:
        格式化后的日期时间字符串 (例如: "2024-01-01 12:00:00")
        如果输入为空或格式无效，返回空字符串或日期部分
    """
    if not published_at or not isinstance(published_at, str):
        return ""
    
    published_at = published_at.strip()
    if not published_at:
        return ""
    
    # 检查是否有日期时间分隔符
    separator_index = published_at.find(OthersTabConfig.ISO_DATE_TIME_SEPARATOR)
    
    if separator_index >= 0:
        date_part = published_at[:separator_index]
        time_part = published_at[separator_index + 1:]
        
        # 使用正则表达式移除时区标识和毫秒
        time_part = _TIMEZONE_PATTERN.split(time_part)[0]
        
        # 验证时间部分格式（HH:MM:SS）
        if not re.match(r'^\d{2}:\d{2}:\d{2}$', time_part):
            # 如果时间格式不正确，使用默认时间
            time_part = OthersTabConfig.DEFAULT_TIME_STR
    else:
        # 没有时间部分，只提取日期
        if len(published_at) >= OthersTabConfig.MIN_DATE_STRING_LENGTH:
            date_part = published_at[:OthersTabConfig.MIN_DATE_STRING_LENGTH]
        else:
            date_part = published_at
        time_part = OthersTabConfig.DEFAULT_TIME_STR
    
    # 验证日期部分格式（YYYY-MM-DD）
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_part):
        logger.warning(f"日期格式无效: {published_at}")
        if len(published_at) >= OthersTabConfig.MIN_DATE_STRING_LENGTH:
            return published_at[:OthersTabConfig.MIN_DATE_STRING_LENGTH]
        return published_at
    
    return f"{date_part} {time_part}"


def center_window(window: "ctk.CTkToplevel") -> None:
    """
    将窗口居中显示在屏幕上
    
    Args:
        window: 要居中的窗口对象
        
    Raises:
        AttributeError: 窗口对象无效
    """
    if not window:
        raise ValueError("窗口对象不能为None")
    
    try:
        window.update_idletasks()
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        window_width = window.winfo_width()
        window_height = window.winfo_height()
        
        # 确保窗口尺寸有效
        if window_width <= 0 or window_height <= 0:
            logger.warning("窗口尺寸无效，使用默认位置")
            return
        
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        
        # 确保坐标不为负
        x = max(0, x)
        y = max(0, y)
        
        window.geometry(f"+{x}+{y}")
    except (AttributeError, TclError) as e:
        logger.error(f"居中窗口失败: {e}")
        raise



