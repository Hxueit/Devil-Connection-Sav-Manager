"""文件查看器模块

提供存档文件的查看和编辑功能

注意：为避免循环导入，SaveFileViewer 等类从 save_file_viewer 模块导入，
而不是从本包导入。此包包含辅助工具模块和重构后的子模块。
"""

from .json_highlighter import apply_json_syntax_highlight
from .config import (
    DEFAULT_SF_COLLAPSED_FIELDS,
    SAVE_FILE_NAME,
    CLOSE_CALLBACK_DELAY_MS,
    REFRESH_AFTER_INJECT_DELAY_MS,
    SINGLE_LINE_LIST_FIELDS,
    DEFAULT_WINDOW_SIZE,
    HINT_WRAPLENGTH,
    CHECKBOX_PADX,
)
from .models import ViewerConfig

__all__ = [
    "apply_json_syntax_highlight",
    "DEFAULT_SF_COLLAPSED_FIELDS",
    "SAVE_FILE_NAME",
    "CLOSE_CALLBACK_DELAY_MS",
    "REFRESH_AFTER_INJECT_DELAY_MS",
    "SINGLE_LINE_LIST_FIELDS",
    "DEFAULT_WINDOW_SIZE",
    "HINT_WRAPLENGTH",
    "CHECKBOX_PADX",
    "ViewerConfig",
]


def __getattr__(name):
    """延迟导入以避免循环依赖"""
    if name == "SaveFileViewer":
        from ..save_file_viewer import SaveFileViewer
        globals()["SaveFileViewer"] = SaveFileViewer
        return SaveFileViewer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

