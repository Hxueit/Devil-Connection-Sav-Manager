"""状态指示器模块

负责管理截图列表中的状态指示器，包括新截图标记和替换标记的显示与清除。
"""

from typing import List, Tuple, Optional
import tkinter as tk
from tkinter import ttk


class StatusIndicator:
    """状态指示器管理器
    
    管理截图列表中的状态指示器显示，包括新截图和替换标记。
    """
    
    # 指示器自动清除时间（毫秒）
    INDICATOR_TIMEOUT = 15000
    
    # 指示器前缀
    NEW_INDICATOR_PREFIX = "⚝ "
    REPLACE_INDICATOR_PREFIX = "✧ "
    
    def __init__(self, tree: ttk.Treeview, root: tk.Tk):
        """初始化状态指示器管理器
        
        Args:
            tree: Treeview组件实例
            root: 根窗口实例
        """
        self.tree = tree
        self.root = root
        # 状态指示器列表：(item_id, original_text, after_id, indicator_type)
        self.status_indicators: List[Tuple[str, str, Optional[int], str]] = []
    
    def show_status_indicator(self, id_str: str, is_new: bool = True) -> None:
        """在指定ID的截图名称前显示状态指示器
        
        Args:
            id_str: 截图ID字符串
            is_new: 是否为新截图，True显示新截图标记，False显示替换标记
        """
        item_id = self._find_item_by_id(id_str)
        if not item_id or not self.tree.exists(item_id):
            return
        
        current_values = list(self.tree.item(item_id, "values"))
        if len(current_values) < 2:
            return
        
        original_text = self._extract_original_text(current_values[1])
        
        if is_new:
            indicator_prefix = self.NEW_INDICATOR_PREFIX
            style_tag = "NewIndicator"
            indicator_type = "new"
        else:
            indicator_prefix = self.REPLACE_INDICATOR_PREFIX
            style_tag = "ReplaceIndicator"
            indicator_type = "replace"
        
        new_text = f"{indicator_prefix}{original_text}"
        current_values[1] = new_text
        
        current_tags = list(self.tree.item(item_id, "tags"))
        if style_tag not in current_tags:
            current_tags.append(style_tag)
        
        self.tree.item(item_id, values=tuple(current_values), tags=tuple(current_tags))
        
        after_id = self.root.after(self.INDICATOR_TIMEOUT, 
                                   lambda: self._remove_indicator_from_item(item_id))
        self.status_indicators.append((item_id, original_text, after_id, indicator_type))
    
    def clear_all_indicators(self) -> None:
        """清除所有状态指示器"""
        for item_id, original_text, after_id, indicator_type in self.status_indicators:
            if after_id and self.root.winfo_exists():
                try:
                    self.root.after_cancel(after_id)
                except (ValueError, AttributeError):
                    pass
        
        self.status_indicators.clear()
    
    def _find_item_by_id(self, id_str: str) -> Optional[str]:
        """根据ID字符串查找项目
        
        Args:
            id_str: 截图ID字符串
            
        Returns:
            项目ID，如果不存在则返回None
        """
        for tree_item_id in self.tree.get_children():
            item_tags = self.tree.item(tree_item_id, "tags")
            if item_tags and item_tags[0] == id_str:
                return tree_item_id
        return None
    
    def _extract_original_text(self, info_text: str) -> str:
        """从信息文本中提取原始文本（移除已有指示器前缀）
        
        Args:
            info_text: 信息文本
            
        Returns:
            原始文本
        """
        if info_text.startswith(self.NEW_INDICATOR_PREFIX):
            return info_text[len(self.NEW_INDICATOR_PREFIX):].lstrip()
        elif info_text.startswith(self.REPLACE_INDICATOR_PREFIX):
            return info_text[len(self.REPLACE_INDICATOR_PREFIX):].lstrip()
        return info_text
    
    def _remove_indicator_from_item(self, item_id: str) -> None:
        """从指定项目移除指示器
        
        Args:
            item_id: Treeview项目ID
        """
        if not self.tree.exists(item_id):
            return
        
        current_values = list(self.tree.item(item_id, "values"))
        if len(current_values) >= 2:
            info_text = current_values[1]
            info_text = self._extract_original_text(info_text)
            current_values[1] = info_text
            self.tree.item(item_id, values=tuple(current_values))
            
            current_tags = list(self.tree.item(item_id, "tags"))
            if "NewIndicator" in current_tags:
                current_tags.remove("NewIndicator")
            if "ReplaceIndicator" in current_tags:
                current_tags.remove("ReplaceIndicator")
            self.tree.item(item_id, tags=tuple(current_tags))
        
        self.status_indicators = [(iid, orig, aid, itype) 
                                 for iid, orig, aid, itype in self.status_indicators 
                                 if iid != item_id]

