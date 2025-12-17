"""复选框管理模块

负责管理截图列表中的复选框状态，包括单个复选框的选中状态、
全选/取消全选功能，以及选中项的数量统计。
"""

from typing import Dict, Tuple, List, Optional, Callable
import tkinter as tk
from tkinter import ttk


class CheckboxManager:
    """复选框管理器
    
    管理Treeview中复选框的状态，提供选中项查询和全选功能。
    """
    
    def __init__(
        self,
        tree: ttk.Treeview,
        root: tk.Tk,
        t_func: Callable[[str], str],
        selection_change_callback: Optional[Callable[[], None]] = None
    ) -> None:
        """初始化复选框管理器
        
        Args:
            tree: Treeview组件实例
            root: 根窗口实例
            t_func: 翻译函数
            selection_change_callback: 选中状态变化时的回调函数，可选
        """
        self.tree = tree
        self.root = root
        self.t = t_func
        self.checkbox_vars: Dict[str, Tuple[tk.BooleanVar, str]] = {}
        self.selection_change_callback = selection_change_callback
    
    def register_checkbox(self, item_id: str, id_str: str) -> None:
        """注册一个新的复选框
        
        Args:
            item_id: Treeview项目ID
            id_str: 截图ID字符串
        """
        var = tk.BooleanVar()
        var.trace('w', lambda *args, v=var, iid=id_str: self._on_checkbox_change(v, iid))
        self.checkbox_vars[item_id] = (var, id_str)
        self.update_checkbox_display(item_id)
    
    def unregister_checkbox(self, item_id: str) -> Optional[Tuple[tk.BooleanVar, str]]:
        """注销一个复选框
        
        Args:
            item_id: Treeview项目ID
            
        Returns:
            如果存在则返回 (var, id_str) 元组，否则返回None
        """
        return self.checkbox_vars.pop(item_id, None)
    
    def clear_all(self) -> None:
        """清除所有复选框注册"""
        self.checkbox_vars.clear()
    
    def update_checkbox_display(self, item_id: str) -> None:
        """更新复选框显示状态
        
        Args:
            item_id: Treeview项目ID
        """
        if item_id not in self.checkbox_vars:
            return
        
        var, _ = self.checkbox_vars[item_id]
        checkbox_text = "☑" if var.get() else "☐"
        
        current_values = list(self.tree.item(item_id, "values"))
        if len(current_values) >= 2:
            current_values[0] = checkbox_text
            self.tree.item(item_id, values=tuple(current_values))
    
    def _on_checkbox_change(self, var: tk.BooleanVar, id_str: str) -> None:
        """复选框状态变化时的处理
        
        Args:
            var: 复选框变量对象
            id_str: 截图ID字符串
        """
        # 使用字典查找优化：通过id_str反向查找item_id
        item_id = self._find_item_id_by_screenshot_id(id_str)
        if item_id:
            self.update_checkbox_display(item_id)
        
        # 通知选中状态变化
        if self.selection_change_callback:
            self.selection_change_callback()
    
    def _find_item_id_by_screenshot_id(self, screenshot_id: str) -> Optional[str]:
        """根据截图ID查找对应的Treeview项目ID
        
        Args:
            screenshot_id: 截图ID字符串
            
        Returns:
            Treeview项目ID，如果不存在则返回None
        """
        for item_id, (_, stored_id) in self.checkbox_vars.items():
            if stored_id == screenshot_id:
                return item_id
        return None
    
    def get_selected_ids(self) -> List[str]:
        """获取所有选中的ID列表
        
        Returns:
            选中的截图ID列表
        """
        return [id_str for var, id_str in self.checkbox_vars.values() if var.get()]
    
    def get_selected_count(self) -> int:
        """获取选中的数量
        
        Returns:
            选中的截图数量
        """
        return sum(var.get() for var, _ in self.checkbox_vars.values())
    
    def is_all_selected(self) -> bool:
        """检查是否全部选中
        
        Returns:
            如果全部选中返回True，否则返回False
        """
        if not self.checkbox_vars:
            return False
        return all(var.get() for var, _ in self.checkbox_vars.values())
    
    def toggle_select_all(self) -> None:
        """切换全选/取消全选状态"""
        if not self.checkbox_vars:
            return
        
        select_all = not self.is_all_selected()
        for var, _ in self.checkbox_vars.values():
            var.set(select_all)
        
        for item_id in self.checkbox_vars.keys():
            self.update_checkbox_display(item_id)
        
        # 通知选中状态变化
        if self.selection_change_callback:
            self.selection_change_callback()
    
    def update_select_all_header(self) -> None:
        """更新全选标题显示"""
        checkbox_text = "☑" if self.is_all_selected() else "☐"
        self.tree.heading("select", text=checkbox_text, anchor="center", 
                         command=self.toggle_select_all)
    
    def get_checkbox_var(self, item_id: str) -> Optional[tk.BooleanVar]:
        """获取指定项目的复选框变量
        
        Args:
            item_id: Treeview项目ID
            
        Returns:
            复选框变量，如果不存在则返回None
        """
        if item_id in self.checkbox_vars:
            return self.checkbox_vars[item_id][0]
        return None
    
    def get_id_str(self, item_id: str) -> Optional[str]:
        """获取指定项目的ID字符串
        
        Args:
            item_id: Treeview项目ID
            
        Returns:
            截图ID字符串，如果不存在则返回None
        """
        if item_id in self.checkbox_vars:
            return self.checkbox_vars[item_id][1]
        return None

