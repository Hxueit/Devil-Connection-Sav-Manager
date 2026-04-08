"""Tyrano存档分析UI组件（向后兼容包装器）

此文件已重构为多个模块：
- image_cache.py: 图片缓存
- image_utils.py: 图片工具函数
- save_slot.py: 存档槽组件
- save_viewer.py: 存档查看器

此文件保留用于向后兼容，请使用新的模块导入。
"""

from src.modules.save_analysis.tyrano.save_slot import TyranoSaveSlot
from src.modules.save_analysis.tyrano.save_viewer import TyranoSaveViewer

__all__ = [
    "TyranoSaveSlot",
    "TyranoSaveViewer",
]
