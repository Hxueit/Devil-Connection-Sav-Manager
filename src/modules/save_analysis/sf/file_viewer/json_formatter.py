"""JSON 格式化器

负责 JSON 数据的格式化、折叠字段处理和嵌套字段解析。
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from .config import SINGLE_LINE_LIST_FIELDS

logger = logging.getLogger(__name__)


class JSONFormatter:
    """JSON 格式化器，处理自定义格式化和字段折叠"""
    
    def __init__(self, collapsed_fields: List[str], translate_func: Callable[[str], str]):
        """初始化格式化器
        
        Args:
            collapsed_fields: 要折叠的字段列表
            translate_func: 翻译函数
        """
        self.collapsed_fields = collapsed_fields
        self.t = translate_func
    
    def format_display_data(self, save_data: Dict[str, Any]) -> str:
        """格式化显示数据，应用折叠字段
        
        Args:
            save_data: 存档数据字典
            
        Returns:
            格式化后的 JSON 字符串
        """
        if not isinstance(save_data, dict):
            logger.warning("save_data is not a dict, using default JSON formatting")
            return json.dumps(save_data, ensure_ascii=False, indent=2)
        
        collapsed_fields_map = self._collect_collapsed_fields(save_data)
        display_data = self._deep_copy_data(save_data)
        collapsed_text = self.t("collapsed_field_text")
        
        for field_key in collapsed_fields_map.keys():
            if "." in field_key:
                self._replace_nested_field(display_data, field_key, collapsed_text)
            else:
                if field_key in display_data:
                    display_data[field_key] = collapsed_text
        
        return self._format_json_custom(display_data)
    
    def restore_collapsed_fields(
        self,
        edited_data: Dict[str, Any],
        original_data: Dict[str, Any],
        disable_collapse: bool = False
    ) -> None:
        """恢复被折叠的字段值
        
        Args:
            edited_data: 编辑后的数据
            original_data: 原始数据
            disable_collapse: 是否禁用折叠（如果为 True，则不恢复）
        """
        if disable_collapse or not isinstance(original_data, dict):
            return
        
        collapsed_text = self.t("collapsed_field_text")
        
        for field_path in self.collapsed_fields:
            if "." in field_path:
                self._restore_nested_collapsed_field(
                    edited_data, original_data, field_path, collapsed_text
                )
            else:
                if (field_path in edited_data and
                    isinstance(edited_data[field_path], str) and
                    edited_data[field_path] == collapsed_text and
                    field_path in original_data):
                    edited_data[field_path] = original_data[field_path]
    
    def _collect_collapsed_fields(self, save_data: Dict[str, Any]) -> Dict[str, Any]:
        """收集需要折叠的字段
        
        Args:
            save_data: 存档数据字典
            
        Returns:
            字段路径到字段值的映射字典
        """
        if not isinstance(save_data, dict):
            return {}
        
        collapsed_fields: Dict[str, Any] = {}
        fields_to_collapse = set(self.collapsed_fields)
        
        for field_path in fields_to_collapse:
            if "." in field_path:
                field_value = self._resolve_nested_field(save_data, field_path)
                if field_value is not None:
                    collapsed_fields[field_path] = field_value
            elif field_path in save_data:
                collapsed_fields[field_path] = save_data[field_path]
        
        return collapsed_fields
    
    def _resolve_nested_field(self, data: Dict[str, Any], field_path: str) -> Optional[Any]:
        """解析嵌套字段路径并返回字段值
        
        Args:
            data: 数据字典
            field_path: 字段路径，如 "stat.map_label"
            
        Returns:
            字段值，如果路径不存在则返回 None
        """
        if not isinstance(data, dict):
            return None
        
        path_parts = field_path.split(".")
        if len(path_parts) < 2:
            return None
        
        current_obj = data
        for part in path_parts[:-1]:
            if not isinstance(current_obj, dict) or part not in current_obj:
                return None
            current_obj = current_obj[part]
        
        if isinstance(current_obj, dict) and path_parts[-1] in current_obj:
            return current_obj[path_parts[-1]]
        
        return None
    
    def _replace_nested_field(
        self,
        data: Dict[str, Any],
        field_key: str,
        replacement: str
    ) -> None:
        """替换嵌套字段值
        
        Args:
            data: 数据字典
            field_key: 字段键（支持点号分隔的嵌套路径）
            replacement: 替换值
        """
        if not isinstance(data, dict):
            return
        
        key_parts = field_key.split(".")
        if len(key_parts) < 2:
            return
        
        nested_obj = data
        for part in key_parts[:-1]:
            if not isinstance(nested_obj, dict) or part not in nested_obj:
                return
            nested_obj = nested_obj[part]
        
        if isinstance(nested_obj, dict) and key_parts[-1] in nested_obj:
            nested_obj[key_parts[-1]] = replacement
    
    def _restore_nested_collapsed_field(
        self,
        edited_data: Dict[str, Any],
        original_data: Dict[str, Any],
        field_path: str,
        collapsed_text: str
    ) -> None:
        """恢复嵌套的折叠字段值
        
        Args:
            edited_data: 编辑后的数据
            original_data: 原始数据
            field_path: 字段路径，如 "stat.map_label"
            collapsed_text: 折叠文本占位符
        """
        if not isinstance(original_data, dict):
            return
        
        path_parts = field_path.split(".")
        if len(path_parts) < 2:
            return
        
        original_value = self._resolve_nested_field(original_data, field_path)
        if original_value is None:
            return
        
        current_edited = edited_data
        for part in path_parts[:-1]:
            if not isinstance(current_edited, dict) or part not in current_edited:
                return
            current_edited = current_edited[part]
        
        if not isinstance(current_edited, dict):
            return
        
        last_part = path_parts[-1]
        if (last_part in current_edited and
            isinstance(current_edited[last_part], str) and
            current_edited[last_part] == collapsed_text):
            current_edited[last_part] = original_value
    
    def _format_json_custom(self, obj: Any, indent: int = 0) -> str:
        """自定义 JSON 格式化，列表字段在一行内显示
        
        Args:
            obj: 要格式化的对象
            indent: 当前缩进级别
            
        Returns:
            格式化后的 JSON 字符串
        """
        indent_str = "  " * indent
        
        if isinstance(obj, dict):
            items = []
            for key, value in obj.items():
                if key in SINGLE_LINE_LIST_FIELDS and isinstance(value, list):
                    value_str = json.dumps(value, ensure_ascii=False)
                elif isinstance(value, (dict, list)):
                    value_str = self._format_json_custom(value, indent + 1)
                else:
                    value_str = json.dumps(value, ensure_ascii=False)
                items.append(f'"{key}": {value_str}')
            
            item_separator = ",\n" + indent_str + "  "
            return f"{{\n{indent_str}  {item_separator.join(items)}\n{indent_str}}}"
        elif isinstance(obj, list):
            formatted_items = [
                self._format_json_custom(item, indent + 1) if isinstance(item, (dict, list))
                else json.dumps(item, ensure_ascii=False)
                for item in obj
            ]
            item_separator = ",\n" + indent_str + "  "
            return f"[\n{indent_str}  {item_separator.join(formatted_items)}\n{indent_str}]"
        else:
            return json.dumps(obj, ensure_ascii=False)
    
    @staticmethod
    def _deep_copy_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """深拷贝数据
        
        Args:
            data: 要拷贝的数据字典
            
        Returns:
            深拷贝后的数据字典
        """
        return json.loads(json.dumps(data))
