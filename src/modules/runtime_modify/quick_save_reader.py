"""快速存档信息读取工具

提供快速存档文件的读取和信息提取功能。
"""
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Callable

from src.modules.others.tyrano_service import TyranoService
from src.modules.save_analysis.tyrano.constants import TYRANO_QUICK_SAVE_FILENAME

logger = logging.getLogger(__name__)


def load_quick_save_info(storage_dir: Optional[str]) -> Optional[Dict[str, Any]]:
    """加载快速存档数据
    
    Args:
        storage_dir: 存储目录路径
        
    Returns:
        存档槽数据字典，如果不存在则返回 None
    """
    if not storage_dir:
        return None
    
    try:
        quick_save_path = Path(storage_dir) / TYRANO_QUICK_SAVE_FILENAME
        if not quick_save_path.exists():
            return None
        
        tyrano_service = TyranoService()
        save_data = tyrano_service.load_tyrano_save_file(quick_save_path)
        
        if isinstance(save_data, dict):
            if 'data' in save_data and isinstance(save_data['data'], list) and len(save_data['data']) > 0:
                slot_data = save_data['data'][0]
                if isinstance(slot_data, dict):
                    return slot_data
            elif 'stat' in save_data or 'save_date' in save_data:
                return save_data
        
        return None
    except Exception as e:
        logger.debug(f"Failed to load quick save info: {e}")
        return None


def extract_save_info_data(slot_data: Dict[str, Any]) -> Dict[str, Any]:
    """从存档槽数据提取信息
    
    Args:
        slot_data: 存档槽数据字典
        
    Returns:
        包含 day_value, is_epilogue, finished_count, save_date, subtitle_text 的字典
    """
    stat = slot_data.get('stat', {})
    if not isinstance(stat, dict):
        stat = {}
    
    f = stat.get('f', {})
    if not isinstance(f, dict):
        f = {}
    
    day_epilogue = f.get('day_epilogue')
    day = f.get('day')
    
    day_value = None
    is_epilogue = False
    
    if day_epilogue is not None:
        try:
            day_epilogue_value = int(day_epilogue)
            if day_epilogue_value != 0:
                day_value = day_epilogue_value
                is_epilogue = True
            elif day is not None:
                day_value = int(day)
        except (ValueError, TypeError):
            pass
    
    if day_value is None and day is not None:
        try:
            day_value = int(day)
        except (ValueError, TypeError):
            pass
    
    finished = f.get('finished', [])
    if not isinstance(finished, list):
        finished = []
    
    if day_value is not None and day_value > 0:
        start_index = day_value * 3
        day_finished = finished[start_index:start_index + 3] if start_index < len(finished) else []
        finished_count = min(len(day_finished), 3)
    elif day_value == 0:
        day_finished = finished[:3] if finished else []
        finished_count = min(len(day_finished), 3)
    else:
        finished_count = 0
    
    save_date = slot_data.get('save_date')
    save_date = str(save_date) if save_date is not None else None
    
    subtitle = slot_data.get('subtitle')
    subtitle_text = slot_data.get('subtitleText')
    subtitle_text = str(subtitle_text) if (subtitle and subtitle_text) else None
    
    return {
        'day_value': day_value,
        'is_epilogue': is_epilogue,
        'finished_count': finished_count,
        'save_date': save_date,
        'subtitle_text': subtitle_text
    }


def format_quick_save_info(
    slot_data: Optional[Dict[str, Any]],
    translate_func: Callable[[str], str]
) -> str:
    """格式化快速存档信息为显示字符串
    
    Args:
        slot_data: 存档槽数据字典，如果为 None 则返回"无快速存档"
        translate_func: 翻译函数，接受翻译键返回翻译文本
        
    Returns:
        格式化的存档信息字符串
    """
    if not slot_data:
        return translate_func("runtime_modify_console_no_quick_save")
    
    info = extract_save_info_data(slot_data)
    parts = []
    
    if info['day_value'] is not None:
        if info['is_epilogue']:
            parts.append(translate_func("tyrano_epilogue_day_label").format(day=info['day_value']))
        else:
            parts.append(translate_func("tyrano_day_label").format(day=info['day_value']))
    
    if not info['is_epilogue'] and info['day_value'] is not None:
        circles = "".join("●" if i < info['finished_count'] else "○" for i in range(3))
        parts.append(circles)
    
    if info['save_date']:
        parts.append(info['save_date'])
    
    if info['subtitle_text']:
        parts.append(info['subtitle_text'])
    
    return " · ".join(parts) if parts else translate_func("runtime_modify_console_no_quick_save")
