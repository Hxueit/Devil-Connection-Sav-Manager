"""编辑器控制器

负责管理文本编辑器的状态、变更检测、高亮显示等功能。
"""

import logging
from typing import Callable, List, Optional, Tuple

import tkinter as tk
from tkinter import ttk

from src.utils.ui_utils import showwarning_relative

from .config import USER_EDIT_HIGHLIGHT_COLOR

logger = logging.getLogger(__name__)


class EditorController:
    """编辑器控制器，管理编辑状态和变更检测"""
    
    def __init__(
        self,
        text_widget: tk.Text,
        line_numbers: tk.Text,
        enable_edit_var: tk.BooleanVar,
        translate_func: Callable[[str], str],
        window: tk.Widget,
        update_line_numbers: Callable[[], None]
    ):
        """初始化编辑器控制器
        
        Args:
            text_widget: 文本编辑器组件
            line_numbers: 行号组件
            enable_edit_var: 编辑模式变量
            translate_func: 翻译函数
            window: 窗口对象
            update_line_numbers: 更新行号的回调函数
        """
        self.text_widget = text_widget
        self.line_numbers = line_numbers
        self.enable_edit_var = enable_edit_var
        self.t = translate_func
        self.window = window
        self.update_line_numbers = update_line_numbers
        self.original_content: str = ""
        self.collapsed_text_ranges: List[Tuple[str, str]] = []
        
        self._setup_text_widget()
    
    def _setup_text_widget(self) -> None:
        """设置文本组件"""
        self.text_widget.tag_config("user_edit", background=USER_EDIT_HIGHLIGHT_COLOR)
        self.text_widget.config(undo=True)
        
        # 绑定事件
        self.text_widget.bind("<<Modified>>", self._on_text_change)
        self.text_widget.bind("<KeyRelease>", lambda e: self.update_line_numbers())
        self.text_widget.bind("<Button-1>", lambda e: self.update_line_numbers())
    
    def set_original_content(self, content: str) -> None:
        """设置原始内容（用于变更检测）
        
        Args:
            content: 原始内容
        """
        self.original_content = content
    
    def get_current_content(self) -> str:
        """获取当前文本内容
        
        Returns:
            当前文本内容
        """
        if not self.text_widget.winfo_exists():
            return ""
        return self.text_widget.get("1.0", "end-1c")
    
    def has_unsaved_changes(self) -> bool:
        """检查是否有未保存的更改
        
        Returns:
            是否有未保存的更改
        """
        if not self.enable_edit_var.get():
            return False
        return self.get_current_content() != self.original_content
    
    def update_collapsed_ranges(self, collapsed_text: str) -> None:
        """更新折叠文本范围
        
        Args:
            collapsed_text: 折叠文本占位符
        """
        self.collapsed_text_ranges.clear()
        if not self.enable_edit_var.get() or not self.text_widget.winfo_exists():
            return
        
        content = self.get_current_content()
        start_pos = "1.0"
        while True:
            pos = self.text_widget.search(collapsed_text, start_pos, "end", exact=True)
            if not pos:
                break
            end_pos = f"{pos}+{len(collapsed_text)}c"
            self.collapsed_text_ranges.append((pos, end_pos))
            start_pos = end_pos
    
    def is_in_collapsed_range(self, pos: str) -> bool:
        """检查位置是否在折叠范围内
        
        Args:
            pos: 文本位置
            
        Returns:
            是否在折叠范围内
        """
        if not self.enable_edit_var.get() or not self.text_widget.winfo_exists():
            return False
        
        return any(
            self.text_widget.compare(start, "<=", pos) and 
            self.text_widget.compare(pos, "<", end)
            for start, end in self.collapsed_text_ranges
        )
    
    def handle_edit_attempt(self, event: Optional[tk.Event] = None) -> str:
        """处理编辑尝试（检查是否允许编辑）
        
        Args:
            event: 事件对象（可选）
            
        Returns:
            "break" 如果应该阻止编辑，否则 None
        """
        if not self.enable_edit_var.get():
            if event:
                key = event.keysym
                is_ctrl_c = (event.state & 0x4 and key.lower() == "c")
                if is_ctrl_c:
                    return None
            return "break"
        
        if not self.text_widget.winfo_exists():
            return None
        
        cursor_pos = self.text_widget.index("insert")
        if self.is_in_collapsed_range(cursor_pos):
            showwarning_relative(
                self.window,
                self.t("cannot_edit_collapsed"),
                self.t("cannot_edit_collapsed_detail")
            )
            return "break"
        
        return None
    
    def detect_and_highlight_changes(self) -> None:
        """检测并高亮显示变更"""
        if not self.enable_edit_var.get() or not self.text_widget.winfo_exists():
            return
        
        self.text_widget.tag_remove("user_edit", "1.0", "end")
        current_content = self.get_current_content()
        
        if current_content != self.original_content:
            original_lines = self.original_content.split('\n')
            current_lines = current_content.split('\n')
            max_lines = max(len(original_lines), len(current_lines))
            
            for i in range(max_lines):
                original_line = original_lines[i] if i < len(original_lines) else ""
                current_line = current_lines[i] if i < len(current_lines) else ""
                
                if original_line != current_line:
                    line_start = f"{i+1}.0"
                    line_end = f"{i+1}.end"
                    if (self.text_widget.compare(line_start, "<=", "end") and
                        self.text_widget.compare(line_end, "<=", "end")):
                        self.text_widget.tag_add("user_edit", line_start, line_end)
    
    def _on_text_change(self, *args) -> None:
        """文本变更事件处理"""
        self.update_line_numbers()
        if self.enable_edit_var.get():
            self.detect_and_highlight_changes()
