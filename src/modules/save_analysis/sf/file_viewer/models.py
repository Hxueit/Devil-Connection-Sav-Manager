"""文件查看器数据模型

定义文件查看器使用的数据结构和配置类。
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ViewerConfig:
    """查看器配置类，适用于 file 和 runtime 模式
    
    Attributes:
        ws_url: WebSocket URL（运行时模式使用）
        service: 运行时服务实例（运行时模式使用）
        inject_method: 注入方法，"sf" 或 "kag_stat"
        enable_edit_by_default: 是否默认启用编辑模式
        save_button_text: 保存按钮文本的翻译键
        show_enable_edit_checkbox: 是否显示启用编辑复选框
        show_collapse_checkbox: 是否显示折叠复选框
        show_hint_label: 是否显示提示标签
        title_key: 窗口标题的翻译键
        collapsed_fields: 要折叠的字段列表
        custom_load_func: 自定义加载函数（可选）
        custom_save_func: 自定义保存函数（可选）
        on_save_callback: 保存成功后的回调函数（可选）
    """
    ws_url: Optional[str] = None
    service: Optional[Any] = None
    inject_method: str = "sf"
    enable_edit_by_default: bool = False
    save_button_text: str = "save_file"
    show_enable_edit_checkbox: bool = False
    show_collapse_checkbox: bool = False
    show_hint_label: bool = False
    title_key: str = "save_file_viewer_title"
    collapsed_fields: List[str] = field(default_factory=list)
    custom_load_func: Optional[Callable[[], Optional[Dict[str, Any]]]] = None
    custom_save_func: Optional[Callable[[Dict[str, Any]], bool]] = None
    on_save_callback: Optional[Callable[[Dict[str, Any]], None]] = None
