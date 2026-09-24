"""字体、颜色与 ttk/customtkinter 样式"""

import ctypes
import logging
import platform
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Optional, Tuple

import customtkinter as ctk

logger = logging.getLogger(__name__)

# 字体整体放大倍率（影响 get_cjk_font / get_mono_font 与 Tk 系统默认字体）
_FONT_SCALE = 1.25

_SYSTEM = platform.system()
_CJK_FONT_NAME = {"Windows": "Microsoft YaHei", "Darwin": "PingFang SC"}.get(_SYSTEM, "Arial")
_MONO_FONT_NAME = {"Windows": "Consolas", "Darwin": "Monaco"}.get(_SYSTEM, "DejaVu Sans Mono")


def _scaled(size: int) -> int:
    return max(1, int(round(size * _FONT_SCALE)))


def get_cjk_font(size: int = 10, weight: str = "normal") -> Tuple:
    """适合中日文的字体元组，weight 为 "bold" 时加粗"""
    if weight == "bold":
        return (_CJK_FONT_NAME, _scaled(size), "bold")
    return (_CJK_FONT_NAME, _scaled(size))


def get_mono_font(size: int = 10) -> Tuple[str, int]:
    """等宽字体元组（代码/行号）"""
    return (_MONO_FONT_NAME, _scaled(size))


class Colors:
    # 主要背景色
    WHITE = "#f8fafc"
    LIGHT_GRAY = "#eef2f7"
    GRAY = "#d9dde5"
    DARK_GRAY = "#c5cad3"

    # 预览区域背景
    PREVIEW_BG = "#e9edf4"

    # 文字颜色
    TEXT_PRIMARY = "#1f2933"
    TEXT_SECONDARY = "#4b5563"
    TEXT_MUTED = "#666666"
    TEXT_DARK = "#333333"
    TEXT_DISABLED = "#9ca3af"
    TEXT_HINT = "#d86daa"
    TEXT_SUCCESS = "#2f9e44"
    TEXT_SUCCESS_MINT = "#6DB8AC"
    TEXT_WARNING_PINK = "#FF57FD"
    TEXT_WARNING_AQUA = "#83A9A3"
    TEXT_INFO = "#2196F3"
    TEXT_INFO_BRIGHT = "#00bfff"
    TEXT_HIGHLIGHT = "#D554BC"
    TEXT_WARNING_ORANGE = "#FF6B35"  # 红橙色，用于提示

    # 强调色
    ACCENT_PINK = "#d6336c"
    ACCENT_BLUE = "#228be6"

    # Toast
    TOAST_BG = "#0f172a"
    TOAST_TEXT = "#cbd5e1"

    # 代码编辑区域
    CODE_BG = "#f5f5f5"
    CODE_GUTTER_BG = "#e8e8e8"

    # 弹窗背景
    MODAL_BG = "#f5f5f7"


_style: Optional[ttk.Style] = None


def init_styles(root: Optional[tk.Tk] = None) -> ttk.Style:
    """初始化 customtkinter 主题和全部 ttk 样式（只执行一次）"""
    global _style
    if _style is not None:
        return _style

    _init_ctk_theme()
    _style = ttk.Style()
    if root is not None:
        _configure_root_window(root)
        _scale_system_fonts()
    _configure_ttk_styles(_style)
    return _style


def _init_ctk_theme() -> None:
    try:
        # 关闭 CTk 自带的 DPI 感知，保持与系统缩放一致（尤其是 Canvas 绘制）
        if hasattr(ctk, "deactivate_automatic_dpi_awareness"):
            ctk.deactivate_automatic_dpi_awareness()
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        ctk.set_widget_scaling(1.5)
        ctk.set_window_scaling(1.5)
    except (AttributeError, TypeError, ImportError, RuntimeError) as e:
        # 即便 CTk 初始化失败也不阻塞后续 ttk 样式
        logger.warning(f"Failed to initialize CTk theme: {e}")


def _configure_root_window(root: tk.Tk) -> None:
    """设置根窗口背景色；Windows 上按窗口 DPI 调整 tk scaling（缺省按 96dpi 计算）"""
    try:
        root.configure(bg=Colors.LIGHT_GRAY)
    except (tk.TclError, AttributeError) as e:
        logger.debug(f"Failed to configure root background: {e}")

    if _SYSTEM != "Windows":
        return
    try:
        window_id = root.winfo_id()
        if window_id:
            dpi = ctypes.windll.user32.GetDpiForWindow(window_id)
            if dpi and dpi > 0:
                root.tk.call("tk", "scaling", dpi / 96.0)
    except (OSError, AttributeError, ctypes.ArgumentError) as e:
        logger.debug(f"Failed to get/set DPI scaling: {e}")


def _scale_system_fonts() -> None:
    """同步放大 Tk 系统字体，让未显式设置字体的控件也变大"""
    for font_name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkTooltipFont"):
        try:
            font_obj = tkfont.nametofont(font_name)
            font_obj.configure(size=_scaled(font_obj.cget("size")))
        except (tk.TclError, ValueError) as e:
            logger.debug(f"Failed to configure font {font_name}: {e}")


def _configure_ttk_styles(style: ttk.Style) -> None:
    font = get_cjk_font(10)
    bold_font = get_cjk_font(10, "bold")
    flat = {"borderwidth": 0, "relief": "flat"}

    style.configure("TLabel", background=Colors.WHITE, foreground=Colors.TEXT_PRIMARY,
                    font=font, padding=(2, 2), **flat)
    style.map("TLabel", background=[("active", Colors.WHITE), ("!active", Colors.WHITE)])

    style.configure("Gray.TLabel", background=Colors.LIGHT_GRAY, foreground=Colors.TEXT_PRIMARY,
                    font=font, **flat)
    style.map("Gray.TLabel", background=[("active", Colors.LIGHT_GRAY),
                                         ("!active", Colors.LIGHT_GRAY),
                                         ("disabled", Colors.LIGHT_GRAY)])

    style.configure("Preview.TLabel", background=Colors.PREVIEW_BG, foreground=Colors.TEXT_PRIMARY,
                    font=font, **flat)
    style.configure("Transparent.TLabel", **flat)

    style.configure("TCheckbutton", background=Colors.WHITE, foreground=Colors.TEXT_PRIMARY,
                    font=font, **flat)
    style.configure("Gray.TCheckbutton", background=Colors.LIGHT_GRAY, foreground=Colors.TEXT_PRIMARY,
                    font=font, **flat)

    style.configure("TRadiobutton", background=Colors.WHITE, foreground=Colors.TEXT_PRIMARY, font=font)
    style.map("TRadiobutton", background=[("active", Colors.WHITE), ("!active", Colors.WHITE),
                                          ("selected", Colors.WHITE), ("disabled", Colors.WHITE)])

    style.configure("TButton", borderwidth=0, padding=(10, 6), font=bold_font)

    style.configure("TNotebook", borderwidth=0, background=Colors.LIGHT_GRAY, padding=(8, 0, 8, 0))
    style.configure("TNotebook.Tab", padding=[18, 8], font=bold_font, borderwidth=0)
    style.map(
        "TNotebook.Tab",
        background=[("selected", Colors.WHITE), ("!selected", Colors.LIGHT_GRAY)],
        foreground=[("selected", Colors.TEXT_PRIMARY), ("!selected", Colors.TEXT_SECONDARY)],
        expand=[("selected", [1, 1, 1, 0])],
    )

    style.configure("White.TFrame", background=Colors.WHITE)
    style.configure("Gray.TFrame", background=Colors.LIGHT_GRAY)
    style.configure("Treeview", background=Colors.WHITE, fieldbackground=Colors.WHITE,
                    foreground=Colors.TEXT_PRIMARY, borderwidth=0, font=font)
    style.configure("Vertical.TScrollbar", gripcount=0, background=Colors.GRAY,
                    troughcolor=Colors.LIGHT_GRAY, bordercolor=Colors.LIGHT_GRAY,
                    lightcolor=Colors.WHITE, darkcolor=Colors.DARK_GRAY)


def ease_out_cubic(t: float) -> float:
    """三次缓出：t ∈ [0, 1] -> [0, 1]"""
    return 1.0 - pow(1.0 - t, 3)
