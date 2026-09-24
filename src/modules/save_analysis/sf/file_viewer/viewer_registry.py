"""文件查看器注册表

管理活跃的文件查看器实例，支持单例模式和窗口聚焦。
"""

import logging
import tkinter as tk
from typing import Dict, Optional

from src.utils.ui_utils import restore_and_activate_window

logger = logging.getLogger(__name__)

# 全局注册表：存储所有活跃的查看器实例
_active_viewers: Dict[str, 'SaveFileViewer'] = {}


def is_viewer_alive(viewer: 'SaveFileViewer') -> bool:
    """检查查看器窗口是否仍然存活
    
    Args:
        viewer: SaveFileViewer 实例
        
    Returns:
        窗口是否存活且可用
    """
    if viewer is None:
        return False
    
    if not hasattr(viewer, 'viewer_window'):
        return False
    
    try:
        return (viewer.viewer_window is not None and 
                viewer.viewer_window.winfo_exists())
    except (tk.TclError, AttributeError):
        return False


def register_viewer(viewer_id: str, viewer: 'SaveFileViewer') -> None:
    """注册查看器实例
    
    Args:
        viewer_id: 查看器唯一标识符
        viewer: SaveFileViewer 实例
    """
    if viewer_id and viewer:
        _active_viewers[viewer_id] = viewer
        logger.debug(f"Registered viewer: {viewer_id}")


def unregister_viewer(viewer_id: str) -> None:
    """注销查看器实例
    
    Args:
        viewer_id: 查看器唯一标识符
    """
    if viewer_id in _active_viewers:
        _active_viewers.pop(viewer_id, None)
        logger.debug(f"Unregistered viewer: {viewer_id}")


def get_viewer(viewer_id: str) -> Optional['SaveFileViewer']:
    """获取已注册的查看器实例
    
    Args:
        viewer_id: 查看器唯一标识符
        
    Returns:
        SaveFileViewer 实例，如果不存在或已销毁则返回 None
    """
    if viewer_id not in _active_viewers:
        return None
    
    viewer = _active_viewers[viewer_id]
    if not is_viewer_alive(viewer):
        unregister_viewer(viewer_id)
        return None
    
    return viewer


def focus_existing_viewer(viewer_id: str) -> Optional['SaveFileViewer']:
    """聚焦已存在的查看器窗口
    
    Args:
        viewer_id: 查看器唯一标识符
        
    Returns:
        SaveFileViewer 实例，如果不存在则返回 None
    """
    viewer = get_viewer(viewer_id)
    if viewer and hasattr(viewer, 'viewer_window'):
        try:
            restore_and_activate_window(viewer.viewer_window)
            return viewer
        except (tk.TclError, AttributeError) as e:
            logger.warning(f"Failed to focus viewer {viewer_id}: {e}")
            unregister_viewer(viewer_id)
    
    return None
