"""状态指示器模块

负责管理截图列表中的状态指示器，包括新截图标记和替换标记的显示与清除。
"""

from typing import List, Tuple, Optional
import logging
import tkinter as tk
from tkinter import ttk

logger = logging.getLogger(__name__)

# 常量定义
INDICATOR_TIMEOUT_MS = 15000
NEW_INDICATOR_PREFIX = "⚝ "
REPLACE_INDICATOR_PREFIX = "✧ "
MIN_VALUES_LENGTH = 2


class StatusIndicator:
    """状态指示器管理器
    
    管理截图列表中的状态指示器显示，包括新截图和替换标记。
    """
    
    def __init__(self, tree: ttk.Treeview, root: tk.Tk) -> None:
        """初始化状态指示器管理器
        
        Args:
            tree: Treeview组件实例
            root: 根窗口实例
        """
        self.tree = tree
        self.root = root
        # 状态指示器列表：(item_id, original_text, after_id, indicator_type)
        self.status_indicators: List[Tuple[str, str, Optional[int], str]] = []
    
    def show_status_indicator(self, screenshot_id: str, is_new: bool = True) -> None:
        """在指定ID的截图名称前显示状态指示器
        
        Args:
            screenshot_id: 截图ID字符串
            is_new: 是否为新截图，True显示新截图标记，False显示替换标记
        """
        item_id = self._find_item_by_id(screenshot_id)
        if not item_id:
            return
        
        try:
            if not self.tree.exists(item_id):
                return
        except (tk.TclError, AttributeError):
            return
        
        try:
            current_values = list(self.tree.item(item_id, "values"))
            if len(current_values) < MIN_VALUES_LENGTH:
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
            
            after_id = self.root.after(
                INDICATOR_TIMEOUT_MS,
                lambda: self._remove_indicator_from_item(item_id)
            )
            self.status_indicators.append((item_id, original_text, after_id, indicator_type))
        except (tk.TclError, AttributeError, IndexError) as e:
            logger.debug(f"Failed to show status indicator: {e}")
    
    def clear_all_indicators(self) -> None:
        """清除所有状态指示器"""
        for item_id, original_text, after_id, indicator_type in self.status_indicators:
            if after_id:
                try:
                    if self.root.winfo_exists():
                        self.root.after_cancel(after_id)
                except (ValueError, AttributeError, tk.TclError):
                    pass
        
        self.status_indicators.clear()
    
    def _find_item_by_id(self, screenshot_id: str) -> Optional[str]:
        """根据ID字符串查找项目
        
        Args:
            screenshot_id: 截图ID字符串
            
        Returns:
            项目ID，如果不存在则返回None
        """
        try:
            for tree_item_id in self.tree.get_children():
                try:
                    item_tags = self.tree.item(tree_item_id, "tags")
                    if item_tags and item_tags[0] == screenshot_id:
                        return tree_item_id
                except (tk.TclError, AttributeError):
                    continue
        except (tk.TclError, AttributeError):
            pass
        
        return None
    
    def _extract_original_text(self, info_text: str) -> str:
        """从信息文本中提取原始文本（移除已有指示器前缀）
        
        Args:
            info_text: 信息文本
            
        Returns:
            原始文本
        """
        if info_text.startswith(NEW_INDICATOR_PREFIX):
            return info_text[len(NEW_INDICATOR_PREFIX):].lstrip()
        elif info_text.startswith(REPLACE_INDICATOR_PREFIX):
            return info_text[len(REPLACE_INDICATOR_PREFIX):].lstrip()
        return info_text
    
    def _remove_indicator_from_item(self, item_id: str) -> None:
        """从指定项目移除指示器
        
        Args:
            item_id: Treeview项目ID
        """
        try:
            if not self.tree.exists(item_id):
                return
        except (tk.TclError, AttributeError):
            return
        
        try:
            current_values = list(self.tree.item(item_id, "values"))
            if len(current_values) >= MIN_VALUES_LENGTH:
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
            
            self.status_indicators = [
                (iid, orig, aid, itype)
                for iid, orig, aid, itype in self.status_indicators
                if iid != item_id
            ]
        except (tk.TclError, AttributeError, IndexError) as e:
            logger.debug(f"Failed to remove indicator from item: {e}")
