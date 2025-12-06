# styles.py

import tkinter as tk
from tkinter import ttk
import platform

# =====================================================
# 字体管理
# =====================================================

# 缓存字体对象，避免重复创建
_FONT_CACHE = {}

def get_cjk_font(size=10, weight="normal"):
    """
    获取适合中文和日文的字体（带缓存）
    """
    cache_key = (size, weight)
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]
    
    if platform.system() == "Windows":
        font_name = "Microsoft YaHei"
    elif platform.system() == "Darwin":  # macOS
        font_name = "PingFang SC"
    else:  # Linux
        font_name = "Arial"
    
    if weight == "bold":
        font = (font_name, size, "bold")
    else:
        font = (font_name, size)
    
    _FONT_CACHE[cache_key] = font
    return font


# =====================================================
# 颜色常量
# =====================================================

class Colors:
    # 主要背景色
    WHITE = "#ffffff"
    LIGHT_GRAY = "#fafafa"
    GRAY = "#e8e8e8"
    DARK_GRAY = "#d0d0d0"
    
    # 预览区域背景
    PREVIEW_BG = "#d3d3d3"  
    
    # 文字颜色
    TEXT_PRIMARY = "#333333"
    TEXT_SECONDARY = "#666666"
    TEXT_DISABLED = "#999999"
    TEXT_HINT = "#D554BC"  
    TEXT_SUCCESS = "#6DB8AC"  
    
    # 强调色
    ACCENT_PINK = "#D554BC"
    ACCENT_GREEN = "#6DB8AC"
    ACCENT_BLUE = "#2196F3"
    
    # Toast 背景
    TOAST_BG = "#1a1a1a"
    TOAST_TEXT = "#b0b0b0"


# =====================================================
# 样式初始化
# =====================================================

_STYLES_INITIALIZED = False

def init_styles(root=None):
    """
    初始化应用样式
    
    Args:
        root: 可选的根窗口，用于获取 ttk.Style
    """
    global _STYLES_INITIALIZED
    if _STYLES_INITIALIZED:
        return
    
    style = ttk.Style()
    
    # =====================================================
    # TLabel 样式
    # =====================================================
    
    # 默认白色背景的 Label（用于主要内容区域）
    style.configure("TLabel",
                   background=Colors.WHITE,
                   borderwidth=0,
                   relief="flat")
    style.map("TLabel",
             background=[("active", Colors.WHITE), ("!active", Colors.WHITE)])
    
    # 浅灰色背景的 Label（用于灰色区域）
    style.configure("Gray.TLabel",
                   background=Colors.LIGHT_GRAY,
                   borderwidth=0,
                   relief="flat")
    style.map("Gray.TLabel",
             background=[("active", Colors.LIGHT_GRAY), ("!active", Colors.LIGHT_GRAY)])
    
    # 预览区域专用 Label（lightgray 背景）
    style.configure("Preview.TLabel",
                   background=Colors.PREVIEW_BG,
                   borderwidth=0,
                   relief="flat")
    style.map("Preview.TLabel",
             background=[("active", Colors.PREVIEW_BG), ("!active", Colors.PREVIEW_BG)])
    
    # 透明/继承背景的 Label（不设置背景色，让其继承父容器）
    style.configure("Transparent.TLabel",
                   borderwidth=0,
                   relief="flat")
    
    # =====================================================
    # TCheckbutton 样式
    # =====================================================
    
    style.configure("TCheckbutton",
                   background=Colors.WHITE,
                   borderwidth=0,
                   relief="flat")
    style.map("TCheckbutton",
             background=[("active", Colors.WHITE), ("!active", Colors.WHITE)])
    
    style.configure("Gray.TCheckbutton",
                   background=Colors.LIGHT_GRAY,
                   borderwidth=0,
                   relief="flat")
    style.map("Gray.TCheckbutton",
             background=[("active", Colors.LIGHT_GRAY), ("!active", Colors.LIGHT_GRAY)])
    
    # =====================================================
    # TButton 样式
    # =====================================================
    
    style.configure("TButton", borderwidth=0)
    style.map("TButton",
             background=[("active", "SystemButtonFace"), ("!active", "SystemButtonFace")])
    
    # =====================================================
    # TNotebook 样式
    # =====================================================
    
    style.configure("TNotebook",
                   borderwidth=0,
                   background=Colors.LIGHT_GRAY)
    style.configure("TNotebook.Tab",
                   padding=[16, 1],
                   font=get_cjk_font(10),
                   borderwidth=0)
    style.map("TNotebook.Tab",
             background=[("selected", Colors.LIGHT_GRAY), ("!selected", Colors.GRAY)],
             expand=[("selected", [1, 1, 1, 0])])
    
    # =====================================================
    # TFrame 样式
    # =====================================================
    
    style.configure("White.TFrame", background=Colors.WHITE)
    style.configure("Gray.TFrame", background=Colors.LIGHT_GRAY)
    
    _STYLES_INITIALIZED = True


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

