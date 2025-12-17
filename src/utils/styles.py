# styles.py

import tkinter as tk
from tkinter import ttk
import platform
import customtkinter as ctk
import tkinter.font as tkfont

# =====================================================
# 字体管理
# =====================================================

# 缓存字体对象，避免重复创建
_FONT_CACHE = {}

def get_cjk_font(size=10, weight="normal"):
    """
    获取适合中文和日文的字体（带缓存）
    """
    scaled_size = max(1, int(round(size * _FONT_SCALE)))
    cache_key = (scaled_size, weight)
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]
    
    if platform.system() == "Windows":
        font_name = "Microsoft YaHei"
    elif platform.system() == "Darwin":  # macOS
        font_name = "PingFang SC"
    else:  # Linux
        font_name = "Arial"
    
    if weight == "bold":
        font = (font_name, scaled_size, "bold")
    else:
        font = (font_name, scaled_size)
    
    _FONT_CACHE[cache_key] = font
    return font


# =====================================================
# 等宽字体（代码/行号）
# =====================================================

def get_mono_font(size=10):
    """
    获取跨平台等宽字体
    """
    scaled_size = max(1, int(round(size * _FONT_SCALE)))
    try:
        if platform.system() == "Windows":
            return ("Consolas", scaled_size)
        elif platform.system() == "Darwin":
            return ("Monaco", scaled_size)
        else:
            return ("DejaVu Sans Mono", scaled_size)
    except Exception:
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
    def apply_palette(cls, palette):
        """使用ttkbootstrap主题调色板更新颜色"""
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
        except Exception:
            # palette 不可用时保持默认值
            pass


# =====================================================
# 样式初始化
# =====================================================

_STYLES_INITIALIZED = False
_STYLE_INSTANCE = None
_CTK_INITIALIZED = False
_CTK_APPEARANCE = "system"
_CTK_COLOR_THEME = "blue"
# 字体整体放大倍率（影响 get_cjk_font 与下方默认字体）
_FONT_SCALE = 1.25
_CTK_WIDGET_SCALING = 1.5
_CTK_WINDOW_SCALING = 1.5


def init_ctk_theme(appearance_mode: str = None, color_theme: str = None):
    """
    初始化 customtkinter 主题（只执行一次）
    """
    global _CTK_INITIALIZED, _CTK_APPEARANCE, _CTK_COLOR_THEME
    if appearance_mode:
        _CTK_APPEARANCE = appearance_mode
    if color_theme:
        _CTK_COLOR_THEME = color_theme
    if _CTK_INITIALIZED:
        return
    try:
        # 关闭 CTk 默认的 DPI 感知，保持与系统缩放一致（尤其是 Canvas 绘制）
        if hasattr(ctk, "deactivate_automatic_dpi_awareness"):
            ctk.deactivate_automatic_dpi_awareness()
        ctk.set_appearance_mode(_CTK_APPEARANCE)
        ctk.set_default_color_theme(_CTK_COLOR_THEME)
        try:
            ctk.set_widget_scaling(_CTK_WIDGET_SCALING)
            ctk.set_window_scaling(_CTK_WINDOW_SCALING)
        except Exception:
            # 某些环境可能不支持缩放，忽略
            pass
        _CTK_INITIALIZED = True
    except Exception:
        # 容错：即便 CTk 初始化失败也不阻塞后续 ttk 样式
        pass

def init_styles(root=None):
    """
    初始化应用样式
    
    Args:
        root: 可选的根窗口，用于获取 ttk.Style
    """
    global _STYLES_INITIALIZED, _STYLE_INSTANCE
    if _STYLES_INITIALIZED and _STYLE_INSTANCE:
        return _STYLE_INSTANCE
    
    # 先初始化 customtkinter 主题，保持与 ttk 样式的色感一致
    init_ctk_theme()

    style = ttk.Style()
    _STYLE_INSTANCE = style

    # 窗口背景与基础色统一，并调整 tk scaling 以匹配系统 DPI
    if root is not None:
        try:
            root.configure(bg=Colors.LIGHT_GRAY)
        except Exception:
            pass
        try:
            # Windows 上 tk scaling 受 DPI 影响，缺省为 1.0（96dpi）；这里根据当前窗口 DPI 调整
            import ctypes
            dpi = ctypes.windll.user32.GetDpiForWindow(root.winfo_id())
            if dpi and dpi > 0:
                root.tk.call("tk", "scaling", dpi / 96.0)
        except Exception:
            # 获取 DPI 失败则保持默认
            pass
        # 将 Tk 系统字体同步放大，保证未显式设置字体的控件也变大
        try:
            for fname in ["TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkTooltipFont"]:
                try:
                    f = tkfont.nametofont(fname)
                    f.configure(size=max(1, int(round(f.cget("size") * _FONT_SCALE))))
                except Exception:
                    continue
        except Exception:
            pass
    
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
        padding=(8, 6, 8, 0)
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
    
    _STYLES_INITIALIZED = True
    return style


# =====================================================
# 辅助函数
# =====================================================

def get_parent_bg(widget):
    """
    获取父容器的背景色
    
    Args:
        widget: tkinter widget
    
    Returns:
        背景色字符串
    """
    try:
        parent = widget.master
        while parent:
            try:
                bg = parent.cget("bg")
                if bg and bg != "":
                    return bg
            except:
                pass
            try:
                bg = parent.cget("background")
                if bg and bg != "":
                    return bg
            except:
                pass
            parent = parent.master if hasattr(parent, 'master') else None
    except:
        pass
    return Colors.WHITE


def create_label_with_auto_bg(parent, text, font=None, fg=None, **kwargs):
    """
    创建一个自动继承父容器背景色的 Label
    
    Args:
        parent: 父容器
        text: 标签文本
        font: 字体（可选）
        fg: 前景色（可选）
        **kwargs: 其他 Label 参数
    
    Returns:
        tk.Label 实例
    """
    bg = get_parent_bg(parent)
    if font is None:
        font = get_cjk_font(10)
    if fg is None:
        fg = Colors.TEXT_PRIMARY
    
    return tk.Label(parent, text=text, font=font, fg=fg, bg=bg, **kwargs)


def update_widget_bg_recursive(widget, bg_color):
    """
    递归更新 widget 及其所有子组件的背景色
    
    Args:
        widget: 根 widget
        bg_color: 目标背景色
    """
    try:
        # 尝试设置背景色
        widget.configure(bg=bg_color)
    except:
        try:
            widget.configure(background=bg_color)
        except:
            pass
    
    # 递归处理子组件
    try:
        for child in widget.winfo_children():
            update_widget_bg_recursive(child, bg_color)
    except:
        pass


# =====================================================
# 性能优化工具
# =====================================================

class Debouncer:
    """
    防抖工具类，用于避免频繁更新
    """
    def __init__(self, widget, delay_ms=16):
        """
        Args:
            widget: tkinter widget（用于 after 调用）
            delay_ms: 延迟时间（毫秒）
        """
        self.widget = widget
        self.delay_ms = delay_ms
        self._pending_job = None
    
    def call(self, func, *args, **kwargs):
        """
        延迟调用函数，如果在延迟期间再次调用，则取消之前的调用
        """
        if self._pending_job is not None:
            try:
                self.widget.after_cancel(self._pending_job)
            except:
                pass
        
        def execute():
            self._pending_job = None
            try:
                func(*args, **kwargs)
            except:
                pass
        
        self._pending_job = self.widget.after(self.delay_ms, execute)
    
    def cancel(self):
        """取消待执行的调用"""
        if self._pending_job is not None:
            try:
                self.widget.after_cancel(self._pending_job)
            except:
                pass
            self._pending_job = None


class ThrottledUpdater:
    """
    节流更新器，限制更新频率
    """
    def __init__(self, widget, min_interval_ms=16):
        """
        Args:
            widget: tkinter widget
            min_interval_ms: 最小更新间隔（毫秒）
        """
        self.widget = widget
        self.min_interval_ms = min_interval_ms
        self._last_update_time = 0
        self._pending_update = None
        self._pending_args = None
    
    def update(self, func, *args, **kwargs):
        """
        节流更新，确保更新间隔不小于 min_interval_ms
        """
        import time
        current_time = time.time() * 1000  # 转换为毫秒
        
        if current_time - self._last_update_time >= self.min_interval_ms:
            # 可以立即更新
            self._last_update_time = current_time
            try:
                func(*args, **kwargs)
            except:
                pass
        else:
            # 需要延迟更新
            if self._pending_update is not None:
                try:
                    self.widget.after_cancel(self._pending_update)
                except:
                    pass
            
            delay = int(self.min_interval_ms - (current_time - self._last_update_time))
            
            def execute():
                self._pending_update = None
                self._last_update_time = time.time() * 1000
                try:
                    func(*args, **kwargs)
                except:
                    pass
            
            self._pending_update = self.widget.after(max(1, delay), execute)


# =====================================================
# 一些缓动函数
# =====================================================

def ease_out_cubic(t):
    return 1 - pow(1 - t, 3)


def ease_in_out_cubic(t):
    if t < 0.5:
        return 4 * t * t * t
    else:
        return 1 - pow(-2 * t + 2, 3) / 2


def ease_out_quad(t):
    return 1 - (1 - t) * (1 - t)

