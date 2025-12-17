"""存档数据服务模块

提供存档文件的加载、解析、计算和格式化功能。
此模块不依赖任何UI框架，只处理纯业务逻辑。
"""

import json
import urllib.parse
import os
from typing import Dict, Any, Optional, Callable


def load_save_file(storage_dir: str) -> Optional[Dict[str, Any]]:
    """加载并解码存档文件
    
    Args:
        storage_dir: 存档文件所在目录
        
    Returns:
        解析后的存档数据字典，如果文件不存在或解析失败则返回None
    """
    sf_path = os.path.join(storage_dir, 'DevilConnection_sf.sav')
    if not os.path.exists(sf_path):
        return None
    
    try:
        with open(sf_path, 'r', encoding='utf-8') as f:
            encoded = f.read().strip()
        unquoted = urllib.parse.unquote(encoded)
        return json.loads(unquoted)
    except Exception:
        return None


def get_nested_value(save_data: Dict[str, Any], data_path: Optional[str]) -> Any:
    """从save_data中提取嵌套值，支持 'memory.name' 格式
    
    Args:
        save_data: 存档数据字典
        data_path: 数据路径，支持点号分隔的嵌套路径
        
    Returns:
        提取的值，如果路径不存在则返回None
    """
    if data_path is None:
        return None
    parts = data_path.split('.')
    value = save_data
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
        if value is None:
            return None
    return value


def compute_shared_data(save_data: Dict[str, Any], total_omakes: list, 
                       total_gallery: list, total_ng_scene: list) -> Dict[str, Any]:
    """计算所有section共享的数据，避免重复计算
    
    Args:
        save_data: 存档数据字典
        total_omakes: 所有omakes ID列表
        total_gallery: 所有gallery ID列表
        total_ng_scene: 所有ng_scene ID列表
        
    Returns:
        包含所有共享计算数据的字典，包括：
        - memory: 角色记忆数据
        - is_fanatic_route: 是否为狂信徒路线
        - endings: 所有结局集合
        - collected_endings: 已收集结局集合
        - missing_endings: 缺失结局列表
        - stickers: 所有贴纸集合
        - collected_stickers: 已收集贴纸列表
        - missing_stickers: 缺失贴纸列表
        - characters: 所有角色集合
        - collected_characters: 已收集角色集合
        - missing_characters: 缺失角色列表
        - collected_omakes: 已收集omakes集合
        - total_omakes_set: 所有omakes集合
        - missing_omakes: 缺失omakes列表
        - total_gallery_set: 所有gallery集合
        - total_ng_scene_set: 所有ng_scene集合
    """
    memory = save_data.get("memory", {})
    kill = save_data.get("kill", None)
    killed = save_data.get("killed", None)
    
    is_fanatic_route = (
        (kill is not None and kill == 1) or
        (killed is not None and killed == 1)
    )
    
    # 结局相关
    endings = set(save_data.get("endings", []))
    collected_endings = set(save_data.get("collectedEndings", []))
    missing_endings = sorted(endings - collected_endings, key=lambda x: int(x) if x.isdigit() else 999)
    
    # 贴纸相关
    stickers = set(save_data.get("sticker", []))
    all_sticker_ids = set(range(1, 82)) | set(range(83, 134))
    missing_stickers = sorted(all_sticker_ids - stickers)
    collected_stickers = sorted(stickers)
    
    # 角色相关
    characters = set(c for c in save_data.get("characters", []) if c and c.strip())
    collected_characters = set(c for c in save_data.get("collectedCharacters", []) if c and c.strip())
    missing_characters = sorted(characters - collected_characters)
    
    # 额外内容相关
    collected_omakes = set(save_data.get("omakes", []))
    total_omakes_set = set(total_omakes)
    missing_omakes = sorted(total_omakes_set - collected_omakes, key=lambda x: int(x) if x.isdigit() else 999)
    
    total_gallery_set = set(total_gallery)
    total_ng_scene_set = set(total_ng_scene)
    
    return {
        "memory": memory,
        "is_fanatic_route": is_fanatic_route,
        "endings": endings,
        "collected_endings": collected_endings,
        "missing_endings": missing_endings,
        "stickers": stickers,
        "collected_stickers": collected_stickers,
        "missing_stickers": missing_stickers,
        "characters": characters,
        "collected_characters": collected_characters,
        "missing_characters": missing_characters,
        "collected_omakes": collected_omakes,
        "total_omakes_set": total_omakes_set,
        "missing_omakes": missing_omakes,
        "total_gallery_set": total_gallery_set,
        "total_ng_scene_set": total_ng_scene_set
    }


def format_field_value(field_config: Dict[str, Any], save_data: Dict[str, Any], 
                       computed_data: Optional[Dict[str, Any]] = None,
                       t_func: Optional[Callable[[str], str]] = None) -> Any:
    """格式化字段值，支持计算字段和格式化函数
    
    Args:
        field_config: 字段配置字典
        save_data: 存档数据
        computed_data: 计算后的共享数据
        t_func: 翻译函数（可选）
        
    Returns:
        格式化后的字段值
    """
    formatter = field_config.get("formatter")
    
    if field_config.get("is_computed"):
        # 计算字段：formatter接收 save_data 和 computed_data
        if formatter:
            try:
                # 检查formatter的参数数量
                import inspect
                sig = inspect.signature(formatter)
                param_count = len(sig.parameters)
                
                if param_count == 0:
                    return formatter()
                elif param_count == 1:
                    # 只接收 computed_data
                    return formatter(computed_data or {})
                elif param_count == 2:
                    # 接收 save_data 和 computed_data
                    return formatter(save_data, computed_data or {})
                else:
                    # 传递 t_func 作为第三个参数
                    return formatter(save_data, computed_data or {}, t_func)
            except Exception as e:
                # 如果formatter调用失败，尝试其他方式
                try:
                    return formatter(computed_data or {}, t_func)
                except:
                    try:
                        return formatter(computed_data or {})
                    except:
                        return str(e)
        return None
    else:
        # 普通字段：先提取值，再格式化
        value = get_nested_value(save_data, field_config.get("data_path"))
        if formatter:
            try:
                # 检查formatter的参数数量
                import inspect
                sig = inspect.signature(formatter)
                param_count = len(sig.parameters)
                
                if param_count == 0:
                    return formatter()
                elif param_count == 1:
                    # formatter接收原始值
                    return formatter(value)
                else:
                    # 传递 t_func 作为第二个参数
                    return formatter(value, t_func)
            except Exception as e:
                return str(value) if value is not None else ""
        else:
            return value if value is not None else ""

