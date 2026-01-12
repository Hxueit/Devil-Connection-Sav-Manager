"""样式管理模块

提供字体、颜色和UI样式的统一管理功能。
"""

import logging
import platform
from typing import Tuple, Optional, Any, Dict
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
import customtkinter as ctk

logger = logging.getLogger(__name__)

# =====================================================
# 字体管理
# =====================================================

# 缓存字体对象，避免重复创建
_FONT_CACHE: Dict[Tuple[int, str], Tuple[str, int, ...]] = {}

# 字体整体放大倍率（影响 get_cjk_font 与下方默认字体）
_FONT_SCALE = 1.25


def get_cjk_font(size: int = 10, weight: str = "normal") -> Tuple[str, int, ...]:
    """获取适合中文和日文的字体（带缓存）
    
    Args:
        size: 字体大小，默认10
        weight: 字体粗细，可选 "normal" 或 "bold"，默认 "normal"
    
    Returns:
        字体元组，格式为 (字体名, 大小) 或 (字体名, 大小, "bold")
    """
    scaled_size = max(1, int(round(size * _FONT_SCALE)))
    cache_key = (scaled_size, weight)
    
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]
    
    system_name = platform.system()
    if system_name == "Windows":
        font_name = "Microsoft YaHei"
    elif system_name == "Darwin":  # macOS
        font_name = "PingFang SC"
    else:  # Linux 和其他系统
        font_name = "Arial"
    
    if weight == "bold":
        font_tuple: Tuple[str, int, ...] = (font_name, scaled_size, "bold")
    else:
        font_tuple = (font_name, scaled_size)
    
    _FONT_CACHE[cache_key] = font_tuple
    return font_tuple


# =====================================================
# 等宽字体（代码/行号）
# =====================================================

def get_mono_font(size: int = 10) -> Tuple[str, int]:
    """获取跨平台等宽字体
    
    Args:
        size: 字体大小，默认10
    
    Returns:
        等宽字体元组，格式为 (字体名, 大小)
    """
    scaled_size = max(1, int(round(size * _FONT_SCALE)))
    
    system_name = platform.system()
    if system_name == "Windows":
        return ("Consolas", scaled_size)
    elif system_name == "Darwin":
        return ("Monaco", scaled_size)
    else:
        # Linux 和其他系统
        try:
            return ("DejaVu Sans Mono", scaled_size)
        except (OSError, AttributeError):
            # 如果字体不可用，回退到 Courier
            logger.debug("DejaVu Sans Mono not available, falling back to Courier")
            return ("Courier", scaled_size)


# =====================================================
# 颜色常量
# =====================================================

class Colors:
    # 主要背景色（默认值，初始化后会根据主题更新）
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
    ACCENT_GREEN = "#2f9e44"
    ACCENT_BLUE = "#228be6"
    
    # Toast 背景
    TOAST_BG = "#0f172a"
    TOAST_TEXT = "#cbd5e1"

    # 代码编辑区域
    CODE_BG = "#f5f5f5"
    CODE_GUTTER_BG = "#e8e8e8"

    # 弹窗背景
    MODAL_BG = "#f5f5f7"

    @classmethod
    def apply_palette(cls, palette: Any) -> None:
        """使用ttkbootstrap主题调色板更新颜色
        
        Args:
            palette: ttkbootstrap 调色板对象，如果为 None 或缺少属性则保持默认值
        """
        if palette is None:
            return
        
        try:
            cls.WHITE = getattr(palette, "bg", cls.WHITE)
            cls.LIGHT_GRAY = getattr(palette, "light", cls.LIGHT_GRAY)
            cls.GRAY = getattr(palette, "secondary", cls.GRAY)
            cls.DARK_GRAY = getattr(palette, "dark", cls.DARK_GRAY)
            cls.PREVIEW_BG = getattr(palette, "light", cls.PREVIEW_BG)
            cls.TEXT_PRIMARY = getattr(palette, "fg", cls.TEXT_PRIMARY)
            cls.TEXT_SECONDARY = getattr(palette, "secondary", cls.TEXT_SECONDARY)
            cls.TEXT_DISABLED = getattr(palette, "disabledfg", cls.TEXT_DISABLED)
            cls.TEXT_HINT = getattr(palette, "primary", cls.TEXT_HINT)
            cls.TEXT_SUCCESS = getattr(palette, "success", cls.TEXT_SUCCESS)
            cls.ACCENT_PINK = getattr(palette, "primary", cls.ACCENT_PINK)
            cls.ACCENT_GREEN = getattr(palette, "success", cls.ACCENT_GREEN)
            cls.ACCENT_BLUE = getattr(palette, "info", cls.ACCENT_BLUE)
            cls.TOAST_BG = getattr(palette, "dark", cls.TOAST_BG)
            cls.TOAST_TEXT = getattr(palette, "light", cls.TOAST_TEXT)
        except (AttributeError, TypeError) as e:
            # palette 不可用或类型错误时保持默认值
            logger.debug(f"Failed to apply palette: {e}")


# =====================================================
# 样式初始化
# =====================================================

_STYLES_INITIALIZED = False
_STYLE_INSTANCE: Optional[ttk.Style] = None
_CTK_INITIALIZED = False
_CTK_APPEARANCE = "system"
_CTK_COLOR_THEME = "blue"
_CTK_WIDGET_SCALING = 1.5
_CTK_WINDOW_SCALING = 1.5


def init_ctk_theme(appearance_mode: Optional[str] = None, color_theme: Optional[str] = None) -> None:
    """初始化 customtkinter 主题（只执行一次）
    
    Args:
        appearance_mode: 外观模式，可选 "light"、"dark" 或 "system"
        color_theme: 颜色主题，默认为 "blue"
    """
    global _CTK_INITIALIZED, _CTK_APPEARANCE, _CTK_COLOR_THEME
    
    if _CTK_INITIALIZED:
        return
    
    if appearance_mode:
        _CTK_APPEARANCE = appearance_mode
    if color_theme:
        _CTK_COLOR_THEME = color_theme
    
    try:
        # 关闭 CTk 默认的 DPI 感知，保持与系统缩放一致（尤其是 Canvas 绘制）
        if hasattr(ctk, "deactivate_automatic_dpi_awareness"):
            ctk.deactivate_automatic_dpi_awareness()
        ctk.set_appearance_mode(_CTK_APPEARANCE)
        ctk.set_default_color_theme(_CTK_COLOR_THEME)
        
        # 某些环境可能不支持缩放，需要单独处理
        try:
            ctk.set_widget_scaling(_CTK_WIDGET_SCALING)
            ctk.set_window_scaling(_CTK_WINDOW_SCALING)
        except (AttributeError, TypeError) as e:
            logger.debug(f"Scaling not supported: {e}")
        
        _CTK_INITIALIZED = True
    except (AttributeError, ImportError, RuntimeError) as e:
        # 容错：即便 CTk 初始化失败也不阻塞后续 ttk 样式
        logger.warning(f"Failed to initialize CTk theme: {e}")

def init_styles(root: Optional[tk.Tk] = None) -> ttk.Style:
    """初始化应用样式
    
    Args:
        root: 可选的根窗口，用于获取 ttk.Style 和配置 DPI
    
    Returns:
        初始化后的 ttk.Style 实例
    """
    global _STYLES_INITIALIZED, _STYLE_INSTANCE
    
    if _STYLES_INITIALIZED and _STYLE_INSTANCE is not None:
        return _STYLE_INSTANCE
    
    # 先初始化 customtkinter 主题，保持与 ttk 样式的色感一致
    init_ctk_theme()

    style = ttk.Style()
    _STYLE_INSTANCE = style

    # 窗口背景与基础色统一，并调整 tk scaling 以匹配系统 DPI
    if root is not None:
        _configure_root_window(root)
        _configure_system_fonts()

    _configure_ttk_styles(style)
    
    _STYLES_INITIALIZED = True
    return style


def _configure_root_window(root: tk.Tk) -> None:
    """配置根窗口的背景色和 DPI 缩放
    
    Args:
        root: 根窗口对象
    """
    try:
        root.configure(bg=Colors.LIGHT_GRAY)
    except (tk.TclError, AttributeError) as e:
        logger.debug(f"Failed to configure root background: {e}")
    
    # Windows 上 tk scaling 受 DPI 影响，缺省为 1.0（96dpi）；这里根据当前窗口 DPI 调整
    if platform.system() == "Windows":
        try:
            import ctypes
            window_id = root.winfo_id()
            if window_id:
                dpi = ctypes.windll.user32.GetDpiForWindow(window_id)
                if dpi and dpi > 0:
                    scaling_factor = dpi / 96.0
                    root.tk.call("tk", "scaling", scaling_factor)
        except (OSError, AttributeError, ctypes.ArgumentError) as e:
            # 获取 DPI 失败则保持默认
            logger.debug(f"Failed to get/set DPI scaling: {e}")


def _configure_system_fonts() -> None:
    """将 Tk 系统字体同步放大，保证未显式设置字体的控件也变大"""
    system_font_names = [
        "TkDefaultFont",
        "TkTextFont",
        "TkMenuFont",
        "TkHeadingFont",
        "TkTooltipFont"
    ]
    
    for font_name in system_font_names:
        try:
            font_obj = tkfont.nametofont(font_name)
            current_size = font_obj.cget("size")
            new_size = max(1, int(round(current_size * _FONT_SCALE)))
            font_obj.configure(size=new_size)
        except (tk.TclError, ValueError, AttributeError) as e:
            logger.debug(f"Failed to configure font {font_name}: {e}")
            continue


def _configure_ttk_styles(style: ttk.Style) -> None:
    """配置所有 ttk 样式
    
    Args:
        style: ttk.Style 实例
    """
    
    # =====================================================
    # TLabel 样式
    # =====================================================
    
    style.configure(
        "TLabel",
        background=Colors.WHITE,
        foreground=Colors.TEXT_PRIMARY,
        borderwidth=0,
        relief="flat",
        font=get_cjk_font(10),
        padding=(2, 2)
    )
    style.map("TLabel",
              background=[("active", Colors.WHITE), ("!active", Colors.WHITE)])
    
    style.configure(
        "Gray.TLabel",
        background=Colors.LIGHT_GRAY,  # 确保这个颜色和父容器一致
        foreground=Colors.TEXT_PRIMARY,
        borderwidth=0,
        relief="flat",
        font=get_cjk_font(10)
    )
    # 添加 map 确保所有状态下背景色都正确
    style.map("Gray.TLabel",
              background=[("active", Colors.LIGHT_GRAY), 
                         ("!active", Colors.LIGHT_GRAY),
                         ("disabled", Colors.LIGHT_GRAY)])
    
    style.configure(
        "Preview.TLabel",
        background=Colors.PREVIEW_BG,
        foreground=Colors.TEXT_PRIMARY,
        borderwidth=0,
        relief="flat",
        font=get_cjk_font(10)
    )
    
    style.configure(
        "Transparent.TLabel",
        borderwidth=0,
        relief="flat"
    )
    
    # =====================================================
    # TCheckbutton 样式
    # =====================================================
    
    style.configure(
        "TCheckbutton",
        background=Colors.WHITE,
        foreground=Colors.TEXT_PRIMARY,
        borderwidth=0,
        relief="flat",
        font=get_cjk_font(10)
    )
    
    style.configure(
        "Gray.TCheckbutton",
        background=Colors.LIGHT_GRAY,
        foreground=Colors.TEXT_PRIMARY,
        borderwidth=0,
        relief="flat",
        font=get_cjk_font(10)
    )
    
    # =====================================================
    # TRadiobutton 样式
    # =====================================================
    
    style.configure(
        "TRadiobutton",
        background=Colors.WHITE,
        foreground=Colors.TEXT_PRIMARY,
        font=get_cjk_font(10)
    )
    style.map("TRadiobutton",
              background=[("active", Colors.WHITE), 
                         ("!active", Colors.WHITE),
                         ("selected", Colors.WHITE),
                         ("disabled", Colors.WHITE)])
    
    # =====================================================
    # TButton 样式
    # =====================================================
    
    style.configure(
        "TButton",
        borderwidth=0,
        padding=(10, 6),
        font=get_cjk_font(10, "bold")
    )
    
    # =====================================================
    # TNotebook 样式
    # =====================================================
    
    style.configure(
        "TNotebook",
        borderwidth=0,
        background=Colors.LIGHT_GRAY,
        padding=(8, 0, 8, 0)
    )
    style.configure(
        "TNotebook.Tab",
        padding=[18, 8],
        font=get_cjk_font(10, "bold"),
        borderwidth=0
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", Colors.WHITE), ("!selected", Colors.LIGHT_GRAY)],
        foreground=[("selected", Colors.TEXT_PRIMARY), ("!selected", Colors.TEXT_SECONDARY)],
        expand=[("selected", [1, 1, 1, 0])]
    )
    
    # =====================================================
    # 其他控件样式
    # =====================================================
    style.configure("White.TFrame", background=Colors.WHITE)
    style.configure("Gray.TFrame", background=Colors.LIGHT_GRAY)
    style.configure(
        "Treeview",
        background=Colors.WHITE,
        fieldbackground=Colors.WHITE,
        foreground=Colors.TEXT_PRIMARY,
        borderwidth=0,
        font=get_cjk_font(10)
    )
    style.configure(
        "Vertical.TScrollbar",
        gripcount=0,
        background=Colors.GRAY,
        troughcolor=Colors.LIGHT_GRAY,
        bordercolor=Colors.LIGHT_GRAY,
        lightcolor=Colors.WHITE,
        darkcolor=Colors.DARK_GRAY
    )


# =====================================================
# 辅助函数
# =====================================================

def get_parent_bg(widget: tk.Widget) -> str:
    """获取父容器的背景色
    
    Args:
        widget: tkinter widget
    
    Returns:
        背景色字符串，如果无法获取则返回默认白色
    """
    try:
        parent = widget.master
        while parent is not None:
            # 尝试获取 bg 属性
            try:
                bg_color = parent.cget("bg")
                if bg_color and bg_color != "":
                    return bg_color
            except (tk.TclError, AttributeError):
                pass
            
            # 尝试获取 background 属性
            try:
                bg_color = parent.cget("background")
                if bg_color and bg_color != "":
                    return bg_color
            except (tk.TclError, AttributeError):
                pass
            
            # 移动到父级
            parent = getattr(parent, 'master', None)
    except (AttributeError, tk.TclError) as e:
        logger.debug(f"Failed to get parent background: {e}")
    
    return Colors.WHITE


def create_label_with_auto_bg(
    parent: tk.Widget,
    text: str,
    font: Optional[Tuple[str, int, ...]] = None,
    fg: Optional[str] = None,
    **kwargs: Any
) -> tk.Label:
    """创建一个自动继承父容器背景色的 Label
    
    Args:
        parent: 父容器
        text: 标签文本
        font: 字体（可选），如果为 None 则使用默认 CJK 字体
        fg: 前景色（可选），如果为 None 则使用默认文本颜色
        **kwargs: 其他 Label 参数
    
    Returns:
        tk.Label 实例
    """
    bg_color = get_parent_bg(parent)
    label_font = font if font is not None else get_cjk_font(10)
    label_fg = fg if fg is not None else Colors.TEXT_PRIMARY
    
    return tk.Label(parent, text=text, font=label_font, fg=label_fg, bg=bg_color, **kwargs)


def update_widget_bg_recursive(widget: tk.Widget, bg_color: str) -> None:
    """递归更新 widget 及其所有子组件的背景色
    
    Args:
        widget: 根 widget
        bg_color: 目标背景色
    """
    # 尝试设置背景色
    try:
        widget.configure(bg=bg_color)
    except (tk.TclError, AttributeError):
        try:
            widget.configure(background=bg_color)
        except (tk.TclError, AttributeError):
            pass
    
    # 递归处理子组件
    try:
        for child in widget.winfo_children():
            update_widget_bg_recursive(child, bg_color)
    except (tk.TclError, AttributeError) as e:
        logger.debug(f"Failed to update child widget background: {e}")


# =====================================================
# 性能优化工具
# =====================================================

class Debouncer:
    """防抖工具类，用于避免频繁更新
    
    在指定延迟时间内，如果多次调用，只执行最后一次调用。
    """
    
    def __init__(self, widget: tk.Widget, delay_ms: int = 16) -> None:
        """初始化防抖器
        
        Args:
            widget: tkinter widget（用于 after 调用）
            delay_ms: 延迟时间（毫秒），默认 16ms（约 60 FPS）
        """
        self.widget = widget
        self.delay_ms = delay_ms
        self._pending_job: Optional[str] = None
    
    def call(self, func: Any, *args: Any, **kwargs: Any) -> None:
        """延迟调用函数，如果在延迟期间再次调用，则取消之前的调用
        
        Args:
            func: 要调用的函数
            *args: 传递给函数的位置参数
            **kwargs: 传递给函数的关键字参数
        """
        if self._pending_job is not None:
            try:
                self.widget.after_cancel(self._pending_job)
            except (ValueError, AttributeError):
                pass
        
        def execute() -> None:
            self._pending_job = None
            try:
                func(*args, **kwargs)
            except Exception as e:
                logger.debug(f"Debounced function call failed: {e}")
        
        self._pending_job = self.widget.after(self.delay_ms, execute)
    
    def cancel(self) -> None:
        """取消待执行的调用"""
        if self._pending_job is not None:
            try:
                self.widget.after_cancel(self._pending_job)
            except (ValueError, AttributeError):
                pass
            self._pending_job = None


class ThrottledUpdater:
    """节流更新器，限制更新频率
    
    确保更新间隔不小于指定的最小间隔时间。
    """
    
    def __init__(self, widget: tk.Widget, min_interval_ms: int = 16) -> None:
        """初始化节流更新器
        
        Args:
            widget: tkinter widget（用于 after 调用）
            min_interval_ms: 最小更新间隔（毫秒），默认 16ms（约 60 FPS）
        """
        self.widget = widget
        self.min_interval_ms = min_interval_ms
        self._last_update_time = 0.0
        self._pending_update: Optional[str] = None
    
    def update(self, func: Any, *args: Any, **kwargs: Any) -> None:
        """节流更新，确保更新间隔不小于 min_interval_ms
        
        Args:
            func: 要调用的函数
            *args: 传递给函数的位置参数
            **kwargs: 传递给函数的关键字参数
        """
        import time
        current_time = time.time() * 1000  # 转换为毫秒
        
        if current_time - self._last_update_time >= self.min_interval_ms:
            # 可以立即更新
            self._last_update_time = current_time
            try:
                func(*args, **kwargs)
            except Exception as e:
                logger.debug(f"Throttled function call failed: {e}")
        else:
            # 需要延迟更新
            if self._pending_update is not None:
                try:
                    self.widget.after_cancel(self._pending_update)
                except (ValueError, AttributeError):
                    pass
            
            delay_ms = int(self.min_interval_ms - (current_time - self._last_update_time))
            
            def execute() -> None:
                self._pending_update = None
                self._last_update_time = time.time() * 1000
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    logger.debug(f"Throttled function call failed: {e}")
            
            self._pending_update = self.widget.after(max(1, delay_ms), execute)


# =====================================================
# 缓动函数
# =====================================================

def ease_out_cubic(t: float) -> float:
    """三次缓出函数
    
    Args:
        t: 时间参数，范围 [0, 1]
    
    Returns:
        缓动后的值，范围 [0, 1]
    """
    return 1.0 - pow(1.0 - t, 3)


def ease_in_out_cubic(t: float) -> float:
    """三次缓入缓出函数
    
    Args:
        t: 时间参数，范围 [0, 1]
    
    Returns:
        缓动后的值，范围 [0, 1]
    """
    if t < 0.5:
        return 4.0 * t * t * t
    else:
        return 1.0 - pow(-2.0 * t + 2.0, 3) / 2.0


def ease_out_quad(t: float) -> float:
    """二次缓出函数
    
    Args:
        t: 时间参数，范围 [0, 1]
    
    Returns:
        缓动后的值，范围 [0, 1]
    """
    return 1.0 - (1.0 - t) * (1.0 - t)

