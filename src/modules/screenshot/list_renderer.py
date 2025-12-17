"""列表渲染模块

负责截图列表的渲染和更新，包括列表项的创建、分页显示等。
"""

from typing import Optional
import tkinter as tk
from tkinter import ttk

# 每页显示的截图数量
SCREENSHOTS_PER_PAGE = 12
# 每半页显示的截图数量（用于中间分页标记）
SCREENSHOTS_PER_HALF_PAGE = 6


class ListRenderer:
    """列表渲染器
    
    负责截图列表的渲染和更新。
    """
    
    def __init__(self, tree: ttk.Treeview, checkbox_manager, 
                 t_func, screenshot_manager):
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
        
        for item in self.screenshot_manager.ids_data:
            # 每页开始时添加左侧页眉
            if screenshot_count % SCREENSHOTS_PER_PAGE == 0:
                self._insert_page_header(page_number, "left")
            
            # 插入截图项
            self._insert_screenshot_item(item, screenshot_count)
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
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.checkbox_manager.clear_all()
    
    def _insert_screenshot_item(self, item_data: dict, screenshot_count: int) -> None:
        """插入截图项
        
        Args:
            item_data: 截图数据字典
            screenshot_count: 当前截图计数
        """
        id_str = item_data['id']
        date_str = item_data['date']
        main_file = (self.screenshot_manager.sav_pairs.get(id_str, [None, None])[0] or 
                    self.t("missing_main_file"))
        display_text = f"{id_str} - {main_file} - {date_str}"
        
        item_id = self.tree.insert("", tk.END, text="", 
                                   values=("", display_text), 
                                   tags=(id_str,))
        
        self.checkbox_manager.register_checkbox(item_id, id_str)
    
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
        
        self.tree.insert("", tk.END, text="", values=("", page_text), tags=(tag,))

