"""搜索处理器

负责文本搜索、高亮和导航功能。
"""

import logging
from typing import Callable, List, Tuple

import tkinter as tk
from tkinter import ttk

from .config import SEARCH_HIGHLIGHT_COLOR

logger = logging.getLogger(__name__)


class SearchHandler:
    """搜索处理器，管理文本搜索和高亮"""
    
    def __init__(
        self,
        text_widget: tk.Text,
        search_entry: ttk.Entry,
        results_label: ttk.Label,
        translate_func: Callable[[str], str]
    ):
        """初始化搜索处理器
        
        Args:
            text_widget: 文本编辑器组件
            search_entry: 搜索输入框
            results_label: 结果显示标签
            translate_func: 翻译函数
        """
        self.text_widget = text_widget
        self.search_entry = search_entry
        self.results_label = results_label
        self.t = translate_func
        self.search_matches: List[Tuple[str, str]] = []
        self.current_search_pos = 0
    
    def find_text(self, direction: str = "next") -> None:
        """搜索文本并高亮显示
        
        Args:
            direction: 搜索方向，"next" 或 "prev"
        """
        search_term = self.search_entry.get().strip()
        if not search_term:
            self.results_label.config(text="")
            return
        
        was_disabled = self.text_widget.cget("state") == "disabled"
        if was_disabled:
            self.text_widget.config(state="normal")
        
        try:
            content = self.text_widget.get("1.0", "end-1c")
            self.text_widget.tag_delete("search_highlight")
            self.text_widget.tag_config("search_highlight", background=SEARCH_HIGHLIGHT_COLOR)
            
            self.search_matches.clear()
            start_pos = "1.0"
            
            while True:
                pos = self.text_widget.search(search_term, start_pos, "end", nocase=True)
                if not pos:
                    break
                end_pos = f"{pos}+{len(search_term)}c"
                self.search_matches.append((pos, end_pos))
                self.text_widget.tag_add("search_highlight", pos, end_pos)
                start_pos = end_pos
            
            if self.search_matches:
                if direction == "next":
                    self.current_search_pos = (self.current_search_pos + 1) % len(self.search_matches)
                else:
                    self.current_search_pos = (self.current_search_pos - 1) % len(self.search_matches)
                
                pos, end_pos = self.search_matches[self.current_search_pos]
                self.text_widget.see(pos)
                self.text_widget.mark_set("insert", pos)
                self.text_widget.see(pos)
                
                self.results_label.config(
                    text=f"{self.current_search_pos + 1}/{len(self.search_matches)}"
                )
            else:
                self.results_label.config(text=self.t("search_not_found"))
        except tk.TclError as e:
            logger.warning(f"Search error: {e}")
            self.results_label.config(text="")
        finally:
            if was_disabled:
                self.text_widget.config(state="disabled")
    
    def find_next(self) -> None:
        """查找下一个匹配项"""
        self.find_text("next")
    
    def find_prev(self) -> None:
        """查找上一个匹配项"""
        self.find_text("prev")
    
    def clear_search(self) -> None:
        """清除搜索高亮"""
        if not self.text_widget.winfo_exists():
            return
        
        self.text_widget.tag_delete("search_highlight")
        self.search_matches.clear()
        self.current_search_pos = 0
        if self.results_label and self.results_label.winfo_exists():
            self.results_label.config(text="")
