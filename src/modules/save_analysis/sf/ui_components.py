"""UI组件创建模块

提供创建section、信息行等UI组件的函数。
这些函数需要访问widget_manager和layout_manager的状态，因此接受这些依赖作为参数。
"""

import tkinter as tk
from tkinter import ttk, Scrollbar
from typing import Optional, Callable, List, Any, Dict
import customtkinter as ctk
from src.utils.styles import get_cjk_font, Colors

from .widget_manager import WidgetManager


# 常量定义
DEFAULT_BG_COLOR = Colors.WHITE
DEFAULT_TEXT_COLOR = "#000000"
DEFAULT_TOOLTIP_COLOR = "blue"
SECTION_BORDER_WIDTH = 2
TITLE_FONT_SIZE = 12
LABEL_FONT_SIZE = 10
HINT_FONT_SIZE = 9
VAR_NAME_FONT_SIZE = 9
TOOLTIP_FONT_SIZE = 9

# 宽度比例常量
TITLE_WRAPLENGTH_RATIO = 0.9
TITLE_WITH_BUTTON_WRAPLENGTH_RATIO = 0.6
LABEL_WRAPLENGTH_RATIO = 0.7
TOOLTIP_WRAPLENGTH_RATIO = 0.85
HORIZONTAL_LIST_SCROLL_THRESHOLD = 10

# 标签文本换行宽度（0 = 不换行）
LABEL_TEXT_WRAPLENGTH = 400


def create_section(
    parent: tk.Widget,
    title: str,
    widget_manager: WidgetManager,
    cached_width: int,
    bg_color: Optional[str] = None,
    text_color: Optional[str] = None,
    title_key: Optional[str] = None
) -> tk.Frame:
    """创建带标题的分区
    
    Args:
        parent: 父容器
        title: 标题文本（已翻译）
        widget_manager: widget管理器实例
        cached_width: 缓存的宽度值
        bg_color: 背景颜色（可选，默认为白色）
        text_color: 文字颜色（可选，默认为黑色）
        title_key: 标题的翻译键（可选，用于语言切换时更新）
        
    Returns:
        content_frame - 用于添加内容的frame
    """
    if bg_color is None:
        bg_color = DEFAULT_BG_COLOR
    if text_color is None:
        text_color = DEFAULT_TEXT_COLOR
    
    section_frame = tk.Frame(
        parent, 
        bg=bg_color, 
        relief="ridge", 
        borderwidth=SECTION_BORDER_WIDTH
    )
    section_frame.pack(fill="x", padx=10, pady=5)
    
    title_wraplength = int(cached_width * TITLE_WRAPLENGTH_RATIO)
    
    title_label = ttk.Label(
        section_frame, 
        text=title, 
        font=get_cjk_font(TITLE_FONT_SIZE, "bold"), 
        wraplength=title_wraplength, 
        justify="left",
        foreground=text_color
    )
    title_label.pack(anchor="w", padx=5, pady=5)
    
    content_frame = tk.Frame(section_frame, bg=bg_color)
    content_frame.pack(fill="x", padx=10, pady=5)
    
    # 存储section_frame引用以便后续访问
    content_frame._section_frame = section_frame
    
    # 保存标题的引用，用于语言切换
    key = title_key if title_key else title
    widget_manager.register_section_title(key, {
        'title_label': title_label,
        'button': None,
        'button_text_key': None,
        'title_key': title_key
    })
    
    return content_frame


def create_section_with_button(
    parent: tk.Widget,
    title: str,
    button_text: str,
    widget_manager: WidgetManager,
    cached_width: int,
    button_command: Optional[Callable] = None,
    title_key: Optional[str] = None,
    button_text_key: Optional[str] = None
) -> tk.Frame:
    """创建带标题和按钮的分区
    
    Args:
        parent: 父容器
        title: 标题文本（已翻译）
        button_text: 按钮文本（已翻译）
        widget_manager: widget管理器实例
        cached_width: 缓存的宽度值
        button_command: 按钮命令
        title_key: 标题的翻译键（可选，用于语言切换时更新）
        button_text_key: 按钮文本的翻译键（可选，用于语言切换时更新）
        
    Returns:
        content_frame - 用于添加内容的frame
    """
    section_frame = tk.Frame(
        parent, 
        bg=DEFAULT_BG_COLOR, 
        relief="ridge", 
        borderwidth=SECTION_BORDER_WIDTH
    )
    section_frame.pack(fill="x", padx=10, pady=5)
    
    # 标题和按钮在同一行
    header_frame = tk.Frame(section_frame, bg=DEFAULT_BG_COLOR)
    header_frame.pack(fill="x", padx=5, pady=5)
    
    title_wraplength = int(cached_width * TITLE_WITH_BUTTON_WRAPLENGTH_RATIO)
    
    title_label = ttk.Label(
        header_frame, 
        text=title, 
        font=get_cjk_font(TITLE_FONT_SIZE, "bold"), 
        wraplength=title_wraplength, 
        justify="left"
    )
    title_label.pack(side="left", padx=5)
    
    button: Optional[ttk.Button] = None
    if button_text:
        button = ttk.Button(
            header_frame, 
            text=button_text, 
            command=button_command if button_command else lambda: None
        )
        button.pack(side="right", padx=5)
    
    content_frame = tk.Frame(section_frame, bg=DEFAULT_BG_COLOR)
    content_frame.pack(fill="x", padx=10, pady=5)
    
    # 保存标题和按钮的引用，用于语言切换
    key = title_key if title_key else title
    widget_manager.register_section_title(key, {
        'title_label': title_label,
        'button': button,
        'button_text_key': button_text_key if button_text_key else ('view_requirements' if button_text else None),
        'title_key': title_key
    })
    
    return content_frame


def add_info_line(
    parent: Optional[tk.Widget],
    label: str,
    value: Any,
    widget_manager: WidgetManager,
    cached_width: int,
    translation_func: Callable[[str], str],
    var_name: Optional[str] = None,
    widget_key: Optional[str] = None,
    text_color: Optional[str] = None,
    is_initialized_ref: Optional[Dict[str, bool]] = None
) -> Optional[ttk.Label]:
    """添加信息行
    
    Args:
        parent: 父容器（如果为None，则进行增量更新）
        label: 标签文本
        value: 值
        widget_manager: widget管理器实例
        cached_width: 缓存的宽度值
        translation_func: 翻译函数
        var_name: 变量名（可选）
        widget_key: widget标识键，用于增量更新（可选）
        text_color: 文字颜色（可选）
        is_initialized_ref: 初始化状态引用字典（用于标记需要重建）
        
    Returns:
        value_widget: 值widget的引用，如果增量更新失败则返回None
    """
    # 如果提供了widget_key且widget已存在，进行增量更新
    if widget_key:
        widget_info = widget_manager.get_widget(widget_key)
        if widget_info:
            value_widget = widget_info.get('value_widget')
            label_widget = widget_info.get('label_widget')
            
            if value_widget and value_widget.winfo_exists():
                # 使用StringVar进行自动更新
                widget_manager.update_string_var(widget_key, str(value))
                widget_manager.update_label_var(widget_key, f"{label}:")
                return value_widget
            else:
                # widget已无效，从映射中删除
                widget_manager.remove_widget(widget_key)
    
    # 如果parent为None，说明是增量更新模式但widget已无效
    # 需要触发完整重建
    if parent is None:
        if is_initialized_ref is not None:
            is_initialized_ref['value'] = False
        return None
    
    # 创建新的widget
    parent_bg = parent.cget("bg") if hasattr(parent, "cget") else DEFAULT_BG_COLOR
    line_frame = tk.Frame(parent, bg=parent_bg)
    line_frame.pack(fill="x", padx=5, pady=2)
    
    # 创建或获取Label StringVar
    if widget_key:
        label_var = widget_manager.get_or_create_label_var(widget_key, f"{label}:")
        label_widget = ttk.Label(
            line_frame, 
            textvariable=label_var, 
            font=get_cjk_font(LABEL_FONT_SIZE), 
            wraplength=LABEL_TEXT_WRAPLENGTH, 
            foreground=text_color if text_color else None
        )
    else:
        label_widget = ttk.Label(
            line_frame, 
            text=f"{label}:", 
            font=get_cjk_font(LABEL_FONT_SIZE), 
            wraplength=LABEL_TEXT_WRAPLENGTH, 
            foreground=text_color if text_color else None
        )
    label_widget.pack(side="left", padx=5)
    
    # 如果有变量名，在冒号前面显示灰色的变量名
    var_name_widget: Optional[ttk.Label] = None
    if var_name:
        var_name_widget = ttk.Label(
            line_frame, 
            text=f"[{var_name}]", 
            font=get_cjk_font(VAR_NAME_FONT_SIZE), 
            foreground="gray"
        )
        # 默认隐藏，只有勾选复选框时才显示
        if widget_manager.show_var_names_var.get():
            var_name_widget.pack(side="left", padx=2, before=label_widget)
        # 存储widget信息以便后续切换显示
        widget_manager.var_name_widgets.append({
            'widget': var_name_widget,
            'parent': line_frame,
            'label_widget': label_widget
        })
    
    wraplength = int(cached_width * LABEL_WRAPLENGTH_RATIO)
    
    # 创建或获取StringVar
    if widget_key:
        value_var = widget_manager.get_or_create_string_var(widget_key, str(value))
        value_widget = ttk.Label(
            line_frame, 
            textvariable=value_var, 
            font=get_cjk_font(LABEL_FONT_SIZE), 
            wraplength=wraplength, 
            justify="left",
            foreground=text_color if text_color else None
        )
    else:
        value_widget = ttk.Label(
            line_frame, 
            text=str(value), 
            font=get_cjk_font(LABEL_FONT_SIZE), 
            wraplength=wraplength, 
            justify="left",
            foreground=text_color if text_color else None
        )
    value_widget.pack(side="left", padx=5, fill="x", expand=True)
    
    # 如果提供了widget_key，存储到映射中
    if widget_key:
        widget_manager.register_widget(widget_key, {
            'value_widget': value_widget,
            'label_widget': label_widget,
            'line_frame': line_frame,
            'var_name_widget': var_name_widget
        })
    
    return value_widget


def add_list_info(
    parent: tk.Widget,
    label: str,
    items: List[Any],
    cached_width: int,
    translation_func: Callable[[str], str]
) -> None:
    """添加列表信息，显示完整列表
    
    Args:
        parent: 父容器
        label: 标签文本
        items: 要显示的列表项
        cached_width: 缓存的宽度值
        translation_func: 翻译函数
    """
    line_frame = tk.Frame(parent, bg=DEFAULT_BG_COLOR)
    line_frame.pack(fill="x", padx=5, pady=2)
    
    label_widget = ttk.Label(
        line_frame, 
        text=f"{label}:", 
        font=get_cjk_font(LABEL_FONT_SIZE), 
            wraplength=LABEL_TEXT_WRAPLENGTH
    )
    label_widget.pack(side="left", padx=5)
    
    wraplength = int(cached_width * LABEL_WRAPLENGTH_RATIO)
    
    if not items:
        value_widget = ttk.Label(
            line_frame, 
            text=translation_func("none"), 
            font=get_cjk_font(LABEL_FONT_SIZE), 
            foreground="gray", 
            wraplength=wraplength, 
            justify="left"
        )
    else:
        value_text = ", ".join(str(item) for item in items)
        value_widget = ttk.Label(
            line_frame, 
            text=value_text, 
            font=get_cjk_font(LABEL_FONT_SIZE), 
            wraplength=wraplength, 
            justify="left"
        )
    value_widget.pack(side="left", padx=5, fill="x", expand=True)


def add_list_info_horizontal(
    parent: tk.Widget,
    label: str,
    items: List[Any],
    translation_func: Callable[[str], str]
) -> tk.Frame:
    """添加列表信息，横向一行展示
    
    Args:
        parent: 父容器
        label: 标签文本
        items: 要显示的列表项
        translation_func: 翻译函数
        
    Returns:
        可滚动的frame容器
    """
    line_frame = tk.Frame(parent, bg=DEFAULT_BG_COLOR)
    line_frame.pack(fill="x", padx=5, pady=2)
    
    label_widget = ttk.Label(
        line_frame, 
        text=f"{label}:", 
        font=get_cjk_font(LABEL_FONT_SIZE)
    )
    label_widget.pack(side="left", padx=5)
    
    canvas_frame = tk.Frame(line_frame, bg=DEFAULT_BG_COLOR)
    canvas_frame.pack(side="left", fill="x", expand=True, padx=5)
    canvas = ctk.CTkCanvas(
        canvas_frame, 
        height=25, 
        bg=DEFAULT_BG_COLOR, 
        highlightthickness=0
    )
    scrollbar_h = Scrollbar(
        canvas_frame, 
        orient="horizontal", 
        command=canvas.xview
    )
    scrollable_frame = tk.Frame(canvas, bg=DEFAULT_BG_COLOR)
    
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(xscrollcommand=scrollbar_h.set)
    
    if not items:
        value_widget = ttk.Label(
            scrollable_frame, 
            text=translation_func("none"), 
            font=get_cjk_font(LABEL_FONT_SIZE), 
            foreground="gray"
        )
    else:
        value_text = ", ".join(str(item) for item in items)
        value_widget = ttk.Label(
            scrollable_frame, 
            text=value_text, 
            font=get_cjk_font(LABEL_FONT_SIZE)
        )
    value_widget.pack(side="left", padx=2)
    
    canvas.pack(side="left", fill="x", expand=True)
    if len(items) > HORIZONTAL_LIST_SCROLL_THRESHOLD:
        scrollbar_h.pack(side="bottom", fill="x")
    
    scrollable_frame.items_data = items
    scrollable_frame.label_key = label
    
    return scrollable_frame


def add_info_line_with_tooltip(
    parent: Optional[tk.Widget],
    label: str,
    value: Any,
    tooltip_text: str,
    widget_manager: WidgetManager,
    cached_width: int,
    translation_func: Callable[[str], str],
    var_name: Optional[str] = None,
    widget_key: Optional[str] = None,
    text_color: Optional[str] = None,
    is_initialized_ref: Optional[Dict[str, bool]] = None
) -> Optional[ttk.Label]:
    """添加带可点击问号的信息行
    
    Args:
        parent: 父容器（如果为None，则进行增量更新）
        label: 标签文本
        value: 值
        tooltip_text: 提示文本
        widget_manager: widget管理器实例
        cached_width: 缓存的宽度值
        translation_func: 翻译函数
        var_name: 变量名（可选）
        widget_key: widget标识键，用于增量更新（可选）
        text_color: 文字颜色（可选）
        is_initialized_ref: 初始化状态引用字典（用于标记需要重建）
        
    Returns:
        值widget的引用，如果增量更新失败则返回None
    """
    # 如果提供了widget_key且widget已存在，进行增量更新
    if widget_key:
        widget_info = widget_manager.get_widget(widget_key)
        if widget_info:
            value_widget = widget_info.get('value_widget')
            label_widget = widget_info.get('label_widget')
            tooltip_text_widget = widget_info.get('tooltip_text_widget')
            
            if value_widget and value_widget.winfo_exists():
                widget_manager.update_string_var(widget_key, str(value))
                widget_manager.update_label_var(widget_key, f"{label}:")
                widget_manager.update_tooltip_var(widget_key, tooltip_text)
                
                if text_color:
                    if label_widget:
                        label_widget.config(foreground=text_color)
                    value_widget.config(foreground=text_color)
                
                return value_widget
            else:
                widget_manager.remove_widget(widget_key)
    
    # 如果parent为None，说明是增量更新模式但widget已无效
    if parent is None:
        if is_initialized_ref is not None:
            is_initialized_ref['value'] = False
        return None
    
    parent_bg = parent.cget("bg") if hasattr(parent, "cget") else DEFAULT_BG_COLOR
    container = tk.Frame(parent, bg=parent_bg)
    container.pack(fill="x", padx=5, pady=2)
    
    line_frame = tk.Frame(container, bg=parent_bg)
    line_frame.pack(fill="x")
    
    # 创建label widget
    if widget_key:
        label_var = widget_manager.get_or_create_label_var(widget_key, f"{label}:")
        label_widget = ttk.Label(
            line_frame, 
            textvariable=label_var, 
            font=get_cjk_font(LABEL_FONT_SIZE), 
            wraplength=LABEL_TEXT_WRAPLENGTH, 
            foreground=text_color if text_color else None
        )
    else:
        label_widget = ttk.Label(
            line_frame, 
            text=f"{label}:", 
            font=get_cjk_font(LABEL_FONT_SIZE), 
            wraplength=LABEL_TEXT_WRAPLENGTH, 
            foreground=text_color if text_color else None
        )
    label_widget.pack(side="left", padx=5)
    
    # 创建变量名widget
    var_name_widget: Optional[ttk.Label] = None
    if var_name:
        var_name_widget = ttk.Label(
            line_frame, 
            text=f"[{var_name}]", 
            font=get_cjk_font(VAR_NAME_FONT_SIZE), 
            foreground="gray"
        )
        if widget_manager.show_var_names_var.get():
            var_name_widget.pack(side="left", padx=2, before=label_widget)
        widget_manager.var_name_widgets.append({
            'widget': var_name_widget,
            'parent': line_frame,
            'label_widget': label_widget
        })
    
    wraplength = int(cached_width * LABEL_WRAPLENGTH_RATIO)
    
    # 创建value widget
    if widget_key:
        value_var = widget_manager.get_or_create_string_var(widget_key, str(value))
        value_widget = ttk.Label(
            line_frame, 
            textvariable=value_var, 
            font=get_cjk_font(LABEL_FONT_SIZE), 
            wraplength=wraplength, 
            justify="left",
            foreground=text_color if text_color else None
        )
    else:
        value_widget = ttk.Label(
            line_frame, 
            text=str(value), 
            font=get_cjk_font(LABEL_FONT_SIZE), 
            wraplength=wraplength, 
            justify="left",
            foreground=text_color if text_color else None
        )
    value_widget.pack(side="left", padx=5, fill="x", expand=True)
    
    # 创建tooltip label
    tooltip_label = ttk.Label(
        line_frame, 
        text="ℹ", 
        font=get_cjk_font(LABEL_FONT_SIZE, "bold"), 
        foreground=text_color if text_color else DEFAULT_TOOLTIP_COLOR, 
        cursor="hand2"
    )
    tooltip_label.pack(side="left", padx=2)
    
    # 创建tooltip frame
    tooltip_frame = tk.Frame(container, bg=parent_bg)
    tooltip_wraplength = int(cached_width * TOOLTIP_WRAPLENGTH_RATIO)
    
    if widget_key:
        tooltip_var = widget_manager.get_or_create_tooltip_var(widget_key, tooltip_text)
        tooltip_text_widget = ttk.Label(
            tooltip_frame, 
            textvariable=tooltip_var, 
            font=get_cjk_font(TOOLTIP_FONT_SIZE), 
            foreground="gray",
            wraplength=tooltip_wraplength,
            justify="left"
        )
    else:
        tooltip_text_widget = ttk.Label(
            tooltip_frame, 
            text=tooltip_text, 
            font=get_cjk_font(TOOLTIP_FONT_SIZE), 
            foreground="gray",
            wraplength=tooltip_wraplength,
            justify="left"
        )
    tooltip_text_widget.pack(anchor="w", padx=15, pady=2)
    
    def toggle_tooltip(event: Optional[tk.Event] = None) -> None:
        if tooltip_frame.winfo_viewable():
            tooltip_frame.pack_forget()
        else:
            tooltip_frame.pack(fill="x", padx=5, pady=2)
    
    tooltip_label.bind("<Button-1>", toggle_tooltip)
    
    if widget_key:
        widget_manager.register_widget(widget_key, {
            'value_widget': value_widget,
            'label_widget': label_widget,
            'container': container,
            'line_frame': line_frame,
            'var_name_widget': var_name_widget,
            'tooltip_text_widget': tooltip_text_widget
        })
    
    return value_widget
