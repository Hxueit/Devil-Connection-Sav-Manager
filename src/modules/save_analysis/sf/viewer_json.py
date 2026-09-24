"""存档查看器的 JSON 显示格式（不涉及界面）

- 收藏类列表（结局、贴纸……）保持在一行内，其余按 2 空格缩进展开
- 体积很大的字段（如 record）可以「折叠」：显示时替换成一段占位文字，
  保存时再把仍是占位文字的字段换回原值
"""

import json
from typing import Any, Dict, Iterable, Optional, Tuple

SINGLE_LINE_LIST_FIELDS = frozenset([
    "endings", "collectedEndings", "omakes", "characters",
    "collectedCharacters", "sticker", "gallery", "ngScene",
])


def format_json(obj: Any, indent: int = 0) -> str:
    """类似 json.dumps(indent=2)，但 SINGLE_LINE_LIST_FIELDS 中的列表写在一行"""
    if not isinstance(obj, (dict, list)):
        return json.dumps(obj, ensure_ascii=False)
    pad = "  " * indent
    if isinstance(obj, dict):
        parts = []
        for key, value in obj.items():
            if key in SINGLE_LINE_LIST_FIELDS and isinstance(value, list):
                value_str = json.dumps(value, ensure_ascii=False)
            else:
                value_str = format_json(value, indent + 1)
            parts.append(f"{json.dumps(key, ensure_ascii=False)}: {value_str}")
        opening, closing = "{", "}"
    else:
        parts = [format_json(item, indent + 1) for item in obj]
        opening, closing = "[", "]"
    separator = ",\n" + pad + "  "
    return f"{opening}\n{pad}  {separator.join(parts)}\n{pad}{closing}"


def _locate(data: Any, path: str) -> Optional[Tuple[Dict[str, Any], str]]:
    """找到 'stat.map_label' 这类路径的 (所在字典, 键名)，路径不存在返回 None"""
    *parents, last = path.split(".")
    for part in parents:
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    if isinstance(data, dict) and last in data:
        return data, last
    return None


def format_display_data(save_data: Any, collapsed_fields: Iterable[str], placeholder: str) -> str:
    """生成查看器中显示的文本：折叠字段替换为 placeholder"""
    if not isinstance(save_data, dict):
        return json.dumps(save_data, ensure_ascii=False, indent=2)
    display = json.loads(json.dumps(save_data))
    for path in collapsed_fields:
        found = _locate(display, path)
        # 嵌套字段值为 null 时不折叠（顶层字段则总是折叠），与 restore_collapsed_fields 对应
        if found and ("." not in path or found[0][found[1]] is not None):
            container, key = found
            container[key] = placeholder
    return format_json(display)


def restore_collapsed_fields(edited: Dict[str, Any], original: Any, collapsed_fields: Iterable[str],
                             placeholder: str) -> None:
    """把 edited 中仍是 placeholder 的折叠字段换回 original 中的值（原地修改）"""
    if not isinstance(original, dict):
        return
    for path in collapsed_fields:
        target = _locate(edited, path)
        source = _locate(original, path)
        if not target or not source:
            continue
        container, key = target
        original_value = source[0][source[1]]
        if container[key] == placeholder and ("." not in path or original_value is not None):
            container[key] = original_value
