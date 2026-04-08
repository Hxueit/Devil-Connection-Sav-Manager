"""列表渲染模块

负责截图列表的渲染和更新，包括列表项的创建、分页显示等。
"""

from typing import Optional, Dict, Any
import tkinter as tk
from tkinter import ttk

# 常量定义
SCREENSHOTS_PER_PAGE = 12
SCREENSHOTS_PER_HALF_PAGE = 6


class ListRenderer:
    """列表渲染器
    
    负责截图列表的渲染和更新。
    """
    
    def __init__(
        self,
        tree: ttk.Treeview,
        checkbox_manager: Any,
        t_func: Any,
        screenshot_manager: Any
    ) -> None:
        """初始化列表渲染器
        
        Args:
            tree: Treeview组件实例
            checkbox_manager: 复选框管理器实例
            t_func: 翻译函数
            screenshot_manager: 截图管理器实例
        """
        self.tree = tree
        self.checkbox_manager = checkbox_manager
        self.t = t_func
        self.screenshot_manager = screenshot_manager
    
    def render_list(self) -> None:
        """渲染截图列表"""
        self._clear_existing_items()
        
        screenshot_count = 0
        page_number = 1
        
        for item_data in self.screenshot_manager.ids_data:
            # 每页开始时添加左侧页眉
            if screenshot_count % SCREENSHOTS_PER_PAGE == 0:
                self._insert_page_header(page_number, "left")
            
            # 插入截图项
            self._insert_screenshot_item(item_data, screenshot_count)
            screenshot_count += 1
            
            # 每半页（但不是整页）时添加右侧页眉
            if (screenshot_count % SCREENSHOTS_PER_HALF_PAGE == 0 and
                    screenshot_count % SCREENSHOTS_PER_PAGE != 0):
                self._insert_page_header(page_number, "right")
            
            # 每页结束时增加页码
            if screenshot_count % SCREENSHOTS_PER_PAGE == 0:
                page_number += 1
        
        self.checkbox_manager.update_select_all_header()
    
    def _clear_existing_items(self) -> None:
        """清除现有列表项"""
        try:
            for item_id in self.tree.get_children():
                self.tree.delete(item_id)
        except (tk.TclError, AttributeError):
            # Treeview可能已被销毁，忽略错误
            pass
        self.checkbox_manager.clear_all()
    
    def _insert_screenshot_item(self, item_data: Dict[str, str], screenshot_count: int) -> None:
        """插入截图项
        
        Args:
            item_data: 截图数据字典
            screenshot_count: 当前截图计数
        """
        screenshot_id = item_data.get('id', '')
        date_string = item_data.get('date', '')
        
        file_pair = self.screenshot_manager.sav_pairs.get(screenshot_id, [None, None])
        main_file = file_pair[0] or self.t("missing_main_file")
        display_text = f"{screenshot_id} - {main_file} - {date_string}"
        
        try:
            item_id = self.tree.insert(
                "",
                tk.END,
                text="",
                values=("", display_text),
                tags=(screenshot_id,)
            )
            self.checkbox_manager.register_checkbox(item_id, screenshot_id)
        except (tk.TclError, AttributeError) as e:
            # Treeview可能已被销毁，忽略错误
            pass
    
    def _insert_page_header(self, page_number: int, position: str) -> None:
        """插入页眉
        
        Args:
            page_number: 页码
            position: 位置，"left"或"right"
        """
        if position == "left":
            page_text = f"{self.t('page')} {page_number} ←"
            tag = "PageHeaderLeft"
        else:
            page_text = f"{self.t('page')} {page_number} →"
            tag = "PageHeaderRight"
        
        try:
            self.tree.insert("", tk.END, text="", values=("", page_text), tags=(tag,))
        except (tk.TclError, AttributeError):
            # Treeview可能已被销毁，忽略错误
            pass
