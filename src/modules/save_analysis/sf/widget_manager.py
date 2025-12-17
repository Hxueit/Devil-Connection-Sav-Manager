"""Widget状态管理模块

负责管理所有UI widget的状态、映射关系、StringVar变量和变量名显示切换。
此模块专注于widget生命周期管理，不涉及UI创建逻辑。
"""

import tkinter as tk
from typing import Dict, Any, List, Optional, Tuple
from tkinter import ttk


class WidgetManager:
    """管理widget状态和映射的类"""
    
    def __init__(self, show_var_names_var: tk.BooleanVar):
        """初始化widget管理器
        
        Args:
            show_var_names_var: 控制变量名显示的BooleanVar
        """
        self.show_var_names_var = show_var_names_var
        self.var_name_widgets: List[Dict[str, Any]] = []
        self._widget_map: Dict[str, Dict[str, Any]] = {}
        self._section_map: Dict[str, tk.Widget] = {}
        self._dynamic_widgets: Dict[str, Dict[str, Any]] = {}
        self._section_title_widgets: Dict[str, Dict[str, Any]] = {}
        self._hint_labels: List[Dict[str, Any]] = []
        self._string_vars: Dict[str, tk.StringVar] = {}
        self._label_vars: Dict[str, tk.StringVar] = {}
        self._tooltip_vars: Dict[str, tk.StringVar] = {}
    
    def toggle_var_names_display(self) -> None:
        """切换变量名显示状态"""
        show = self.show_var_names_var.get()
        invalid_indices: List[int] = []
        
        for idx, widget_info in enumerate(self.var_name_widgets):
            widget = widget_info.get('widget')
            label_widget = widget_info.get('label_widget')
            
            if widget is None or not widget.winfo_exists():
                invalid_indices.append(idx)
                continue
            
            if label_widget is None or not label_widget.winfo_exists():
                invalid_indices.append(idx)
                continue
            
            if show:
                widget.pack(side="left", padx=2, before=label_widget)
            else:
                widget.pack_forget()
        
        # 从后往前删除，避免索引变化
        for idx in reversed(invalid_indices):
            if 0 <= idx < len(self.var_name_widgets):
                self.var_name_widgets.pop(idx)
    
    def register_widget(
        self,
        widget_key: str,
        widget_info: Dict[str, Any]
    ) -> None:
        """注册widget到映射中
        
        Args:
            widget_key: widget的唯一标识键
            widget_info: widget信息字典
        """
        self._widget_map[widget_key] = widget_info
    
    def get_widget(self, widget_key: str) -> Optional[Dict[str, Any]]:
        """获取widget信息
        
        Args:
            widget_key: widget的唯一标识键
            
        Returns:
            widget信息字典，如果不存在则返回None
        """
        return self._widget_map.get(widget_key)
    
    def remove_widget(self, widget_key: str) -> None:
        """从映射中移除widget
        
        Args:
            widget_key: widget的唯一标识键
        """
        self._widget_map.pop(widget_key, None)
        self._string_vars.pop(widget_key, None)
        self._label_vars.pop(widget_key, None)
        self._tooltip_vars.pop(widget_key, None)
    
    def register_section(self, section_key: str, section_widget: tk.Widget) -> None:
        """注册section widget
        
        Args:
            section_key: section的唯一标识键
            section_widget: section widget
        """
        self._section_map[section_key] = section_widget
    
    def get_section(self, section_key: str) -> Optional[tk.Widget]:
        """获取section widget
        
        Args:
            section_key: section的唯一标识键
            
        Returns:
            section widget，如果不存在则返回None
        """
        return self._section_map.get(section_key)
    
    def register_dynamic_widget(
        self,
        widget_key: str,
        widget_info: Dict[str, Any]
    ) -> None:
        """注册动态widget
        
        Args:
            widget_key: widget的唯一标识键
            widget_info: widget信息字典
        """
        self._dynamic_widgets[widget_key] = widget_info
    
    def get_dynamic_widget(self, widget_key: str) -> Optional[Dict[str, Any]]:
        """获取动态widget信息
        
        Args:
            widget_key: widget的唯一标识键
            
        Returns:
            widget信息字典，如果不存在则返回None
        """
        return self._dynamic_widgets.get(widget_key)
    
    def register_section_title(
        self,
        title_key: str,
        title_info: Dict[str, Any]
    ) -> None:
        """注册section标题widget
        
        Args:
            title_key: 标题的唯一标识键
            title_info: 标题信息字典
        """
        self._section_title_widgets[title_key] = title_info
    
    def get_section_title(self, title_key: str) -> Optional[Dict[str, Any]]:
        """获取section标题信息
        
        Args:
            title_key: 标题的唯一标识键
            
        Returns:
            标题信息字典，如果不存在则返回None
        """
        return self._section_title_widgets.get(title_key)
    
    def register_hint_label(self, hint_info: Dict[str, Any]) -> None:
        """注册提示标签
        
        Args:
            hint_info: 提示标签信息字典
        """
        self._hint_labels.append(hint_info)
    
    def get_or_create_string_var(self, widget_key: str, initial_value: str = "") -> tk.StringVar:
        """获取或创建StringVar
        
        Args:
            widget_key: widget的唯一标识键
            initial_value: 初始值
            
        Returns:
            StringVar对象
        """
        if widget_key not in self._string_vars:
            self._string_vars[widget_key] = tk.StringVar(value=initial_value)
        return self._string_vars[widget_key]
    
    def get_or_create_label_var(self, widget_key: str, initial_value: str = "") -> tk.StringVar:
        """获取或创建Label StringVar
        
        Args:
            widget_key: widget的唯一标识键
            initial_value: 初始值
            
        Returns:
            StringVar对象
        """
        if widget_key not in self._label_vars:
            self._label_vars[widget_key] = tk.StringVar(value=initial_value)
        return self._label_vars[widget_key]
    
    def get_or_create_tooltip_var(self, widget_key: str, initial_value: str = "") -> tk.StringVar:
        """获取或创建Tooltip StringVar
        
        Args:
            widget_key: widget的唯一标识键
            initial_value: 初始值
            
        Returns:
            StringVar对象
        """
        if widget_key not in self._tooltip_vars:
            self._tooltip_vars[widget_key] = tk.StringVar(value=initial_value)
        return self._tooltip_vars[widget_key]
    
    def update_string_var(self, widget_key: str, value: str) -> None:
        """更新StringVar的值
        
        Args:
            widget_key: widget的唯一标识键
            value: 新值
        """
        if widget_key in self._string_vars:
            self._string_vars[widget_key].set(value)
    
    def update_label_var(self, widget_key: str, value: str) -> None:
        """更新Label StringVar的值
        
        Args:
            widget_key: widget的唯一标识键
            value: 新值
        """
        if widget_key in self._label_vars:
            self._label_vars[widget_key].set(value)
    
    def update_tooltip_var(self, widget_key: str, value: str) -> None:
        """更新Tooltip StringVar的值
        
        Args:
            widget_key: widget的唯一标识键
            value: 新值
        """
        if widget_key in self._tooltip_vars:
            self._tooltip_vars[widget_key].set(value)
    
    def clear_all(self) -> None:
        """清除所有widget映射和状态"""
        self._widget_map.clear()
        self._section_map.clear()
        self._dynamic_widgets.clear()
        self._section_title_widgets.clear()
        self.var_name_widgets.clear()
        self._string_vars.clear()
        self._label_vars.clear()
        self._tooltip_vars.clear()
        self._hint_labels.clear()
    
    def cleanup_invalid_widgets(self) -> None:
        """清理无效的widget引用"""
        invalid_widget_keys: List[str] = []
        
        for widget_key, widget_info in self._widget_map.items():
            value_widget = widget_info.get('value_widget')
            if value_widget is None or not value_widget.winfo_exists():
                invalid_widget_keys.append(widget_key)
        
        for widget_key in invalid_widget_keys:
            self.remove_widget(widget_key)
        
        invalid_section_keys: List[str] = []
        for section_key, section_widget in self._section_map.items():
            if section_widget is None or not section_widget.winfo_exists():
                invalid_section_keys.append(section_key)
        
        for section_key in invalid_section_keys:
            self._section_map.pop(section_key, None)
        
        invalid_hint_indices: List[int] = []
        for idx, hint_info in enumerate(self._hint_labels):
            label = hint_info.get('label')
            if label is None or not label.winfo_exists():
                invalid_hint_indices.append(idx)
        
        for idx in reversed(invalid_hint_indices):
            if 0 <= idx < len(self._hint_labels):
                self._hint_labels.pop(idx)

