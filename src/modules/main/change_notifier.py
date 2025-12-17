"""变更通知管理器模块

负责管理存档文件变更的通知显示，支持合并连续变化。
"""
import logging
import tkinter as tk
from typing import List, Dict, Any, Callable, Optional, Tuple
from src.utils.toast import Toast

logger = logging.getLogger(__name__)


class ChangeNotifier:
    """变更通知管理器类"""
    
    TOAST_DURATION = 15000
    TOAST_FADE_IN = 200
    TOAST_FADE_OUT = 200
    ARROW_SYMBOL = "→"
    
    def __init__(self, root, translate_func: Callable[[str], str]):
        """初始化变更通知管理器
        
        Args:
            root: Tkinter根窗口对象
            translate_func: 翻译函数
        """
        if root is None:
            raise ValueError("root cannot be None")
        if translate_func is None:
            raise ValueError("translate_func cannot be None")
        
        self.root = root
        self.translate = translate_func
        self.active_toasts: List[Toast] = []
        self.variable_change_chains: Dict[str, Dict[str, Any]] = {}
    
    def show_change_notification(self, changes: List[str]) -> None:
        """显示存档文件变动通知（支持合并连续变化）
        
        Args:
            changes: 变更列表
        """
        mergeable_changes, other_changes = self._categorize_changes(changes)
        updated_toasts, new_changes_for_toast = self._process_mergeable_changes(mergeable_changes)
        self._update_existing_toasts(updated_toasts)
        self._create_new_toasts(new_changes_for_toast, other_changes, mergeable_changes, updated_toasts)
        self._cleanup_invalid_chains()
    
    def _categorize_changes(self, changes: List[str]) -> Tuple[Dict[str, Tuple[str, str]], List[str]]:
        """将变更分类为可合并和不可合并的
        
        Args:
            changes: 变更列表
            
        Returns:
            (可合并的变更字典, 其他变更列表)
        """
        if not changes:
            return {}, []
        
        mergeable_changes: Dict[str, Tuple[str, str]] = {}
        other_changes: List[str] = []
        
        for change in changes:
            if not isinstance(change, str) or not change:
                continue
            
            if self.ARROW_SYMBOL in change and not change.startswith(("+", "-")):
                parsed = self._parse_arrow_change(change)
                if parsed:
                    var_name, old_val, new_val = parsed
                    mergeable_changes[var_name] = (old_val, new_val)
                else:
                    other_changes.append(change)
            else:
                other_changes.append(change)
        
        return mergeable_changes, other_changes
    
    def _parse_arrow_change(self, change: str) -> Optional[Tuple[str, str, str]]:
        """解析箭头格式的变更字符串
        
        Args:
            change: 变更字符串，格式为 "var_name old_val→new_val"
            
        Returns:
            (变量名, 旧值, 新值) 元组，解析失败返回None
        """
        arrow_pos = change.find(self.ARROW_SYMBOL)
        if arrow_pos < 0:
            return None
        
        prefix = change[:arrow_pos]
        last_space = prefix.rfind(" ")
        
        if last_space <= 0:
            return None
        
        var_name = prefix[:last_space].strip()
        old_val = prefix[last_space + 1:].strip()
        new_val = change[arrow_pos + len(self.ARROW_SYMBOL):].strip()
        
        if not var_name:
            return None
        
        return var_name, old_val, new_val
    
    def _process_mergeable_changes(
        self, 
        mergeable_changes: Dict[str, Tuple[str, str]]
    ) -> Tuple[set[str], List[str]]:
        """处理可合并的变更
        
        Args:
            mergeable_changes: 可合并的变更字典
            
        Returns:
            (已更新的toast变量名集合, 需要创建新toast的变更列表)
        """
        if not mergeable_changes:
            return set(), []
        
        updated_toasts: set[str] = set()
        new_changes_for_toast: List[str] = []
        
        for var_name, (old_val, new_val) in mergeable_changes.items():
            if not var_name:
                continue
            
            if var_name in self.variable_change_chains:
                chain_info = self.variable_change_chains[var_name]
                toast = chain_info.get("toast")
                
                try:
                    if toast and hasattr(toast, 'window') and toast.window.winfo_exists():
                        chain_info["chain"].append(new_val)
                        updated_toasts.add(var_name)
                        toast.reset_timer()
                    else:
                        self._initialize_new_chain(var_name, old_val, new_val)
                        new_changes_for_toast.append(f"{var_name} {old_val}{self.ARROW_SYMBOL}{new_val}")
                except (AttributeError, tk.TclError) as e:
                    logger.warning(f"Error checking toast window for {var_name}: {e}")
                    self._initialize_new_chain(var_name, old_val, new_val)
                    new_changes_for_toast.append(f"{var_name} {old_val}{self.ARROW_SYMBOL}{new_val}")
            else:
                self._initialize_new_chain(var_name, old_val, new_val)
                new_changes_for_toast.append(f"{var_name} {old_val}{self.ARROW_SYMBOL}{new_val}")
        
        return updated_toasts, new_changes_for_toast
    
    def _initialize_new_chain(self, var_name: str, old_val: str, new_val: str) -> None:
        """初始化新的变更链
        
        Args:
            var_name: 变量名
            old_val: 旧值
            new_val: 新值
        """
        self.variable_change_chains[var_name] = {
            "chain": [old_val, new_val],
            "toast": None
        }
    
    def _update_existing_toasts(self, updated_toasts: set[str]) -> None:
        """更新现有的toast
        
        Args:
            updated_toasts: 已更新的toast变量名集合
        """
        if not updated_toasts:
            return
        
        for var_name in updated_toasts:
            if var_name not in self.variable_change_chains:
                continue
            
            chain_info = self.variable_change_chains[var_name]
            chain = chain_info.get("chain", [])
            toast = chain_info.get("toast")
            
            if not chain:
                continue
            
            try:
                if toast and hasattr(toast, 'window') and toast.window.winfo_exists():
                    chain_str = self.ARROW_SYMBOL.join(str(v) for v in chain)
                    new_line = f"{var_name} {chain_str}"
                    current_msg = getattr(toast, 'message', '')
                    updated_msg = self._update_message_line(current_msg, var_name, new_line)
                    toast.update_message(updated_msg)
            except (AttributeError, tk.TclError) as e:
                logger.warning(f"Error updating toast for {var_name}: {e}")
    
    def _update_message_line(self, current_msg: str, var_name: str, new_line: str) -> str:
        """更新消息中的指定行
        
        Args:
            current_msg: 当前消息
            var_name: 变量名
            new_line: 新行内容
            
        Returns:
            更新后的消息
        """
        if not current_msg:
            return new_line
        
        lines = current_msg.split("\n")
        updated_lines = []
        found = False
        
        for line in lines:
            if line.startswith(f"{var_name} ") and self.ARROW_SYMBOL in line:
                updated_lines.append(new_line)
                found = True
            else:
                updated_lines.append(line)
        
        if not found:
            updated_lines.append(new_line)
        
        return "\n".join(updated_lines)
    
    def _create_new_toasts(
        self,
        new_changes_for_toast: List[str],
        other_changes: List[str],
        mergeable_changes: Dict[str, Tuple[str, str]],
        updated_toasts: set[str]
    ) -> None:
        """创建新的toast
        
        Args:
            new_changes_for_toast: 需要创建新toast的变更列表
            other_changes: 其他变更列表
            mergeable_changes: 可合并的变更字典
            updated_toasts: 已更新的toast变量名集合
        """
        all_new_changes = new_changes_for_toast + other_changes
        if not all_new_changes:
            return
        
        try:
            header = self.translate("sf_sav_changes_notification")
            message_lines = [header] + all_new_changes
            message = "\n".join(message_lines)
            
            toast = Toast(
                self.root,
                message,
                duration=self.TOAST_DURATION,
                fade_in=self.TOAST_FADE_IN,
                fade_out=self.TOAST_FADE_OUT
            )
            
            for var_name in mergeable_changes:
                if var_name not in updated_toasts and var_name in self.variable_change_chains:
                    self.variable_change_chains[var_name]["toast"] = toast
            
            self.active_toasts.append(toast)
        except Exception as e:
            logger.error(f"Error creating toast notification: {e}", exc_info=True)
    
    def _cleanup_invalid_chains(self) -> None:
        """清理无效的变更链"""
        if not self.variable_change_chains:
            return
        
        to_remove = []
        for var_name, chain_info in self.variable_change_chains.items():
            toast = chain_info.get("toast")
            if toast:
                try:
                    if not hasattr(toast, 'window') or not toast.window.winfo_exists():
                        to_remove.append(var_name)
                except (AttributeError, tk.TclError):
                    to_remove.append(var_name)
        
        for var_name in to_remove:
            try:
                del self.variable_change_chains[var_name]
            except KeyError:
                pass

