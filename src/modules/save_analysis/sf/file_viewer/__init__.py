"""文件查看器模块

提供存档文件的查看和编辑功能

注意：为避免循环导入，SaveFileViewer 等类从 save_file_viewer 模块导入，
而不是从本包导入。此包仅包含辅助工具模块。
"""

from .json_highlighter import apply_json_syntax_highlight

__all__ = [
    "apply_json_syntax_highlight",
]


def __getattr__(name):
    """延迟导入以避免循环依赖"""
    if name in ("SaveFileViewer", "ViewerConfig", "DEFAULT_SF_COLLAPSED_FIELDS"):
        from ..save_file_viewer import SaveFileViewer, ViewerConfig, DEFAULT_SF_COLLAPSED_FIELDS
        globals()["SaveFileViewer"] = SaveFileViewer
        globals()["ViewerConfig"] = ViewerConfig
        globals()["DEFAULT_SF_COLLAPSED_FIELDS"] = DEFAULT_SF_COLLAPSED_FIELDS
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

