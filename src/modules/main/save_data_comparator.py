"""存档数据比较器模块

负责比较存档数据的变化，支持深度比较和类型转换处理。
"""
import json
import logging
from typing import Any, List, Set, Dict, Union

logger = logging.getLogger(__name__)


class SaveDataComparator:
    """存档数据比较器类"""
    
    FLOAT_EPSILON = 1e-10
    
    def __init__(self, ignored_vars: str = ""):
        """初始化数据比较器
        
        Args:
            ignored_vars: 忽略的变量列表（逗号分隔）
        """
        self.ignored_vars: Set[str] = set()
        self.set_ignored_vars(ignored_vars)
    
    def set_ignored_vars(self, ignored_vars: str) -> None:
        """设置忽略的变量列表
        
        Args:
            ignored_vars: 忽略的变量列表（逗号分隔）
        """
        if not ignored_vars or not isinstance(ignored_vars, str):
            self.ignored_vars = set()
            return
        
        self.ignored_vars = {
            var.strip() 
            for var in ignored_vars.split(",") 
            if var and var.strip()
        }
    
    def deep_compare(self, old_data: Dict[str, Any], new_data: Dict[str, Any], prefix: str = "") -> List[str]:
        """深度比较数据，找出所有差异
        
        Args:
            old_data: 旧数据
            new_data: 新数据
            prefix: 键前缀
            
        Returns:
            变更列表
        """
        if not isinstance(old_data, dict):
            old_data = {}
        if not isinstance(new_data, dict):
            new_data = {}
        
        changes: List[str] = []
        all_keys = set(old_data.keys()) | set(new_data.keys())
        
        for key in all_keys:
            full_key = f"{prefix}.{key}" if prefix else key
            
            if self._should_ignore(full_key, key):
                continue
            
            old_value = old_data.get(key)
            new_value = new_data.get(key)
            
            if key not in new_data:
                changes.append(f"-{full_key}")
            elif key not in old_data:
                changes.extend(self._handle_new_key(full_key, new_value))
            else:
                changes.extend(self._compare_values(full_key, old_value, new_value))
        
        return changes
    
    def _handle_new_key(self, full_key: str, new_value: Any) -> List[str]:
        """处理新增的键
        
        Args:
            full_key: 完整键名
            new_value: 新值
            
        Returns:
            变更列表
        """
        if isinstance(new_value, dict):
            return self.deep_compare({}, new_value, full_key)
        return [f"+{full_key} = {self._format_value(new_value)}"]
    
    def _compare_values(self, full_key: str, old_value: Any, new_value: Any) -> List[str]:
        """比较两个值
        
        Args:
            full_key: 完整键名
            old_value: 旧值
            new_value: 新值
            
        Returns:
            变更列表
        """
        if self._values_equal(old_value, new_value):
            return self._handle_type_change(full_key, old_value, new_value)
        
        if isinstance(old_value, dict) and isinstance(new_value, dict):
            return self.deep_compare(old_value, new_value, full_key)
        
        if isinstance(old_value, list) and isinstance(new_value, list):
            return self._compare_lists(full_key, old_value, new_value)
        
        return [f"{full_key} {self._format_value(old_value)}→{self._format_value(new_value)}"]
    
    def _handle_type_change(self, full_key: str, old_value: Any, new_value: Any) -> List[str]:
        """处理类型变化但值相同的情况
        
        Args:
            full_key: 完整键名
            old_value: 旧值
            new_value: 新值
            
        Returns:
            变更列表
        """
        if type(old_value) == type(new_value):
            return []
        
        if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)):
            if abs(float(old_value) - float(new_value)) < self.FLOAT_EPSILON:
                return [
                    f"{full_key} {self._format_value(old_value)} "
                    f"({type(old_value).__name__})→{self._format_value(new_value)} "
                    f"({type(new_value).__name__})"
                ]
        
        return []
    
    def _should_ignore(self, full_key: str, key: str) -> bool:
        """判断是否应该忽略该变量
        
        Args:
            full_key: 完整键名
            key: 键名
            
        Returns:
            是否应该忽略
        """
        if not self.ignored_vars:
            return False
        
        if key in self.ignored_vars or full_key in self.ignored_vars:
            return True
        
        return any(
            full_key == ignored_var or full_key.startswith(f"{ignored_var}.")
            for ignored_var in self.ignored_vars
        )
    
    def _values_equal(self, old_val: Any, new_val: Any) -> bool:
        """比较两个值是否相等（处理类型转换问题）
        
        Args:
            old_val: 旧值
            new_val: 新值
            
        Returns:
            是否相等
        """
        if old_val is None and new_val is None:
            return True
        if old_val is None or new_val is None:
            return False
        
        if type(old_val) == type(new_val):
            return self._compare_same_type(old_val, new_val)
        
        if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
            return self._compare_numbers(old_val, new_val)
        
        if isinstance(old_val, bool) and isinstance(new_val, (int, float)):
            return old_val == (new_val != 0)
        if isinstance(new_val, bool) and isinstance(old_val, (int, float)):
            return new_val == (old_val != 0)
        
        if isinstance(old_val, str) and isinstance(new_val, str):
            return old_val.strip() == new_val.strip()
        
        if not isinstance(old_val, (dict, list)) and not isinstance(new_val, (dict, list)):
            return str(old_val) == str(new_val)
        
        return False
    
    def _compare_same_type(self, old_val: Any, new_val: Any) -> bool:
        """比较相同类型的值"""
        if isinstance(old_val, (list, dict)):
            return old_val == new_val
        return old_val == new_val
    
    def _compare_numbers(self, old_val: Union[float, int], new_val: Union[float, int]) -> bool:
        """比较数字值
        
        Args:
            old_val: 旧数值
            new_val: 新数值
            
        Returns:
            是否相等
        """
        if isinstance(old_val, bool) or isinstance(new_val, bool):
            return False
        
        if isinstance(old_val, int) and isinstance(new_val, int):
            return old_val == new_val
        
        try:
            old_float = float(old_val)
            new_float = float(new_val)
        except (ValueError, TypeError):
            return False
        
        old_is_int = isinstance(old_val, int) or (isinstance(old_val, float) and old_val.is_integer())
        new_is_int = isinstance(new_val, int) or (isinstance(new_val, float) and new_val.is_integer())
        
        if old_is_int and new_is_int:
            return int(old_float) == int(new_float)
        
        return abs(old_float - new_float) < self.FLOAT_EPSILON
    
    def _compare_lists(self, key: str, old_list: List[Any], new_list: List[Any]) -> List[str]:
        """比较两个列表的差异（支持包含不可哈希元素的列表）
        
        Args:
            key: 键名
            old_list: 旧列表
            new_list: 新列表
            
        Returns:
            变更列表
        """
        changes: List[str] = []
        
        old_set = self._list_to_comparable_set(old_list)
        new_set = self._list_to_comparable_set(new_list)
        
        for item in new_list:
            if not self._item_in_comparable_set(item, old_set):
                changes.append(f"{key}.append({self._format_value(item)})")
        
        for item in old_list:
            if not self._item_in_comparable_set(item, new_set):
                changes.append(f"{key}.remove({self._format_value(item)})")
        
        return changes
    
    def _list_to_comparable_set(self, lst: List[Any]) -> set[str]:
        """将列表转换为可比较的字符串集合
        
        Args:
            lst: 列表
            
        Returns:
            字符串集合
        """
        return {self._make_comparable(item) for item in lst}
    
    def _make_comparable(self, item: Any) -> str:
        """将元素转换为可用于比较的形式
        
        Args:
            item: 元素
            
        Returns:
            可比较的字符串
        """
        if isinstance(item, (list, dict)):
            try:
                return json.dumps(item, sort_keys=True, ensure_ascii=False)
            except (TypeError, ValueError):
                return str(item)
        return str(item)
    
    def _item_in_comparable_set(self, item: Any, comparable_set: set[str]) -> bool:
        """检查元素是否在可比较集合中
        
        Args:
            item: 元素
            comparable_set: 可比较集合
            
        Returns:
            是否在集合中
        """
        return self._make_comparable(item) in comparable_set
    
    def _format_value(self, value: Any) -> str:
        """格式化值用于显示
        
        Args:
            value: 要格式化的值
            
        Returns:
            格式化后的字符串
        """
        if isinstance(value, (dict, list)):
            return str(value)
        elif isinstance(value, str):
            return f'"{value}"'
        elif isinstance(value, float):
            if value.is_integer():
                return str(int(value))
            return str(value)
        elif isinstance(value, bool):
            return str(value)
        else:
            return str(value)

