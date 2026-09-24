"""UI 构建器

负责创建和配置文件查看器的UI组件，包括窗口、工具栏、文本编辑器等。
"""

import logging
from typing import Callable, Tuple

import tkinter as tk
from tkinter import Scrollbar, ttk

from src.utils.styles import Colors, get_cjk_font, get_mono_font

from .config import (
    DEFAULT_WINDOW_SIZE,
    HINT_WRAPLENGTH,
    LINE_NUMBER_PADX,
    LINE_NUMBER_PADY,
    LINE_NUMBER_WIDTH,
    TEXT_FONT_SIZE,
    TEXT_TABS,
)

logger = logging.getLogger(__name__)


class UIBuilder:
    """UI构建器，负责创建文件查看器的UI组件"""
    
    def __init__(
        self,
        viewer_window: tk.Toplevel,
        translate_func: Callable[[str], str]
    ):
        """初始化UI构建器
        
        Args:
            viewer_window: 查看器窗口
            translate_func: 翻译函数
        """
        self.viewer_window = viewer_window
        self.t = translate_func
    
    def setup_modal_styles(self) -> None:
        """设置模态窗口样式"""
        modal_style = ttk.Style(self.viewer_window)
        
        modal_style.configure(
            "Modal.TLabel",
            background=Colors.MODAL_BG,
            foreground="gray",
            borderwidth=0,
            relief="flat"
        )
        modal_style.map(
            "Modal.TLabel",
            background=[("active", Colors.MODAL_BG), ("!active", Colors.MODAL_BG)]
        )
        
        modal_style.configure(
            "Modal.TCheckbutton",
            background=Colors.MODAL_BG,
            foreground=Colors.TEXT_PRIMARY,
            borderwidth=0,
            relief="flat"
        )
        modal_style.map(
            "Modal.TCheckbutton",
            background=[
                ("active", Colors.MODAL_BG),
                ("!active", Colors.MODAL_BG),
                ("selected", Colors.MODAL_BG)
            ]
        )
    
    def create_main_frame(self) -> tk.Frame:
        """创建主框架
        
        Returns:
            主框架组件
        """
        main_frame = tk.Frame(self.viewer_window, bg=Colors.MODAL_BG)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        return main_frame
    
    def create_hint_label(self, parent: tk.Widget) -> None:
        """创建提示标签
        
        Args:
            parent: 父组件
        """
        hint_frame = tk.Frame(parent, bg=Colors.MODAL_BG)
        hint_frame.pack(fill="x", pady=(0, 10))
        
        hint_label = ttk.Label(
            hint_frame,
            text=self.t("viewer_hint_text"),
            font=get_cjk_font(9),
            wraplength=HINT_WRAPLENGTH,
            justify="left",
            style="Modal.TLabel"
        )
        hint_label.pack(anchor="w", padx=5)
    
    def create_toolbar(self, parent: tk.Widget) -> tk.Frame:
        """创建工具栏
        
        Args:
            parent: 父组件
            
        Returns:
            工具栏框架
        """
        toolbar = tk.Frame(parent, bg=Colors.MODAL_BG)
        toolbar.pack(fill="x", pady=(0, 5))
        return toolbar
    
    def create_text_widgets(
        self,
        parent: tk.Widget,
        initial_content: str,
        enable_edit: bool = False
    ) -> Tuple[tk.Text, tk.Text]:
        """创建文本显示组件（文本编辑器和行号）
        
        Args:
            parent: 父组件
            initial_content: 初始内容
            enable_edit: 是否启用编辑
            
        Returns:
            (文本编辑器, 行号组件) 元组
        """
        text_frame = tk.Frame(parent)
        text_frame.pack(fill="both", expand=True)
        
        mono_font = get_mono_font(TEXT_FONT_SIZE)
        
        # 创建行号组件
        line_numbers = tk.Text(
            text_frame,
            font=mono_font,
            bg=Colors.CODE_GUTTER_BG,
            fg=Colors.TEXT_MUTED,
            width=LINE_NUMBER_WIDTH,
            padx=LINE_NUMBER_PADX,
            pady=LINE_NUMBER_PADY,
            state="disabled",
            wrap="none",
            highlightthickness=0,
            borderwidth=0
        )
        line_numbers.pack(side="left", fill="y")
        
        # 创建文本容器
        text_container = tk.Frame(text_frame)
        text_container.pack(side="left", fill="both", expand=True)
        
        # 创建滚动条
        v_scrollbar = Scrollbar(text_container, orient="vertical")
        v_scrollbar.pack(side="right", fill="y")
        
        h_scrollbar = Scrollbar(text_container, orient="horizontal")
        h_scrollbar.pack(side="bottom", fill="x")
        
        # 配置滚动同步函数
        def sync_line_numbers(*args):
            """同步行号滚动位置"""
            if line_numbers.winfo_exists() and text_widget.winfo_exists():
                try:
                    line_numbers.yview_moveto(text_widget.yview()[0])
                except (tk.TclError, AttributeError):
                    pass
        
        def yscroll_command(*args):
            """文本编辑器垂直滚动回调，更新滚动条并同步行号"""
            v_scrollbar.set(*args)
            sync_line_numbers()
        
        # 创建文本编辑器
        text_widget = tk.Text(
            text_container,
            font=mono_font,
            bg=Colors.CODE_BG,
            fg=Colors.TEXT_DARK,
            yscrollcommand=yscroll_command,
            xscrollcommand=h_scrollbar.set,
            wrap="none",
            tabs=TEXT_TABS
        )
        text_widget.pack(side="left", fill="both", expand=True)
        
        # 配置滚动条
        v_scrollbar.config(command=text_widget.yview)
        h_scrollbar.config(command=text_widget.xview)
        
        # 绑定滚动事件以同步行号
        text_widget.bind("<MouseWheel>", lambda e: sync_line_numbers(), add="+")
        text_widget.bind("<Button-4>", lambda e: sync_line_numbers(), add="+")
        text_widget.bind("<Button-5>", lambda e: sync_line_numbers(), add="+")
        text_widget.bind("<KeyPress>", lambda e: sync_line_numbers() if e.keysym in ("Up", "Down", "Page_Up", "Page_Down", "Home", "End") else None, add="+")
        
        # 插入初始内容
        text_widget.insert("1.0", initial_content)
        text_widget.config(state="normal" if enable_edit else "disabled")
        
        return text_widget, line_numbers


    def update_line_numbers(
        self,
        text_widget: tk.Text,
        line_numbers: tk.Text
    ) -> None:
        """更新行号显示
        
        Args:
            text_widget: 文本编辑器
            line_numbers: 行号组件
        """
        if not text_widget.winfo_exists() or not line_numbers.winfo_exists():
            return
        
        line_numbers.config(state="normal")
        line_numbers.delete("1.0", "end")
        
        content = text_widget.get("1.0", "end-1c")
        line_count = content.count('\n') + 1 if content else 1
        
        line_numbers.insert("end", "\n".join(str(i) for i in range(1, line_count + 1)) + "\n")
        line_numbers.config(state="disabled")
        line_numbers.yview_moveto(text_widget.yview()[0])
