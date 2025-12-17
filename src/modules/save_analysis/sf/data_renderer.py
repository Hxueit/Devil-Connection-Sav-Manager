"""数据渲染模块

负责根据配置渲染存档数据到UI组件。
包含section渲染、增量更新和完整渲染逻辑。
"""

import tkinter as tk
from tkinter import ttk
from typing import Dict, Any, Optional, Callable, List, Tuple
from src.utils.styles import get_cjk_font, Colors

from .widget_manager import WidgetManager
from .ui_components import (
    create_section,
    create_section_with_button,
    add_info_line,
    add_list_info,
    add_info_line_with_tooltip
)
from .save_data_service import format_field_value
from .config import get_field_configs_with_callbacks


# 常量定义
FANATIC_ROUTE_TEXT_COLOR = "#8b0000"
HINT_WRAPLENGTH_RATIO = 0.85
DEFAULT_SECTION_ORDER = [
    "endings_statistics",
    "stickers_statistics",
    "characters_statistics",
    "omakes_statistics",
    "game_statistics",
    "character_info",
    "other_info"
]


class DataRenderer:
    """负责数据渲染的类"""
    
    def __init__(
        self,
        widget_manager: WidgetManager,
        cached_width: int,
        translation_func: Callable[[str], str],
        get_field_configs_func: Optional[Callable] = None
    ):
        """初始化数据渲染器
        
        Args:
            widget_manager: widget管理器实例
            cached_width: 缓存的宽度值
            translation_func: 翻译函数
            get_field_configs_func: 获取字段配置的函数（可选）
        """
        self.widget_manager = widget_manager
        self.cached_width = cached_width
        self.translation_func = translation_func
        self._get_field_configs = get_field_configs_func or get_field_configs_with_callbacks
    
    def render_section(
        self,
        section_key: str,
        parent: tk.Widget,
        save_data: Dict[str, Any],
        computed_data: Optional[Dict[str, Any]] = None,
        is_fanatic_route: bool = False
    ) -> Optional[tk.Frame]:
        """根据配置渲染一个section及其所有字段
        
        Args:
            section_key: section的键名
            parent: 父容器
            save_data: 存档数据
            computed_data: 计算后的共享数据
            is_fanatic_route: 是否为狂信徒路线
            
        Returns:
            创建的section容器，如果失败则返回None
        """
        if parent is None or not parent.winfo_exists():
            return None
        
        configs = self._get_field_configs()
        config = configs.get(section_key)
        if not config:
            return None
        
        computed_data = computed_data or {}
        
        text_color = config.get("text_color")
        if section_key == "fanatic_related" and is_fanatic_route:
            text_color = FANATIC_ROUTE_TEXT_COLOR
        
        try:
            if config["section_type"] == "section_with_button":
                button_command = None
                if "button_command_factory" in config:
                    button_command = config["button_command_factory"](save_data, computed_data)
                
                section = create_section_with_button(
                    parent,
                    self.translation_func(config["title_key"]),
                    self.translation_func(config.get("button_text_key", "view_requirements")),
                    self.widget_manager,
                    self.cached_width,
                    button_command,
                    config["title_key"],
                    config.get("button_text_key")
                )
            else:
                section = create_section(
                    parent,
                    self.translation_func(config["title_key"]),
                    self.widget_manager,
                    self.cached_width,
                    config.get("bg_color"),
                    text_color,
                    config["title_key"]
                )
            
            if section is None or not section.winfo_exists():
                return None
                
        except (KeyError, AttributeError, tk.TclError) as e:
            # 记录错误但不中断整个渲染流程
            return None
        
        self.widget_manager.register_section(section_key, section)
        
        fields_rendered = 0
        for field_config in config.get("fields", []):
            try:
                value = format_field_value(
                    field_config, 
                    save_data, 
                    computed_data, 
                    self.translation_func
                )
                field_text_color = field_config.get("text_color")
                if field_text_color is None:
                    field_text_color = text_color
                
                widget_key = field_config.get("widget_key")
                
                if field_config.get("is_dynamic"):
                    if field_config.get("is_list"):
                        if value:
                            add_list_info(
                                section, 
                                self.translation_func(field_config["label_key"]), 
                                value,
                                self.cached_width,
                                self.translation_func
                            )
                            self.widget_manager.register_dynamic_widget(widget_key, {
                                'section': section,
                                'label': self.translation_func(field_config["label_key"]),
                                'data_key': widget_key,
                                'is_list': True
                            })
                        else:
                            add_info_line(
                                section, 
                                self.translation_func(field_config["label_key"]), 
                                self.translation_func("none"), 
                                self.widget_manager,
                                self.cached_width,
                                self.translation_func,
                                None, 
                                widget_key
                            )
                            self.widget_manager.register_dynamic_widget(widget_key, {
                                'section': section,
                                'label': self.translation_func(field_config["label_key"]),
                                'data_key': widget_key,
                                'is_list': False
                            })
                    else:
                        add_info_line(
                            section, 
                            self.translation_func(field_config["label_key"]), 
                            value, 
                            self.widget_manager,
                            self.cached_width,
                            self.translation_func,
                            field_config.get("var_name"), 
                            widget_key, 
                            field_text_color
                        )
                        self.widget_manager.register_dynamic_widget(widget_key, {
                            'section': section,
                            'label': self.translation_func(field_config["label_key"]),
                            'data_key': widget_key
                        })
                elif field_config.get("has_tooltip"):
                    tooltip_key = field_config.get("tooltip_key")
                    tooltip_text = self.translation_func(tooltip_key) if tooltip_key else ""
                    if not tooltip_text and field_config.get("tooltip_optional"):
                        add_info_line(
                            section, 
                            self.translation_func(field_config["label_key"]), 
                            value, 
                            self.widget_manager,
                            self.cached_width,
                            self.translation_func,
                            field_config.get("var_name"), 
                            widget_key, 
                            field_text_color
                        )
                        fields_rendered += 1
                        continue
                    
                    add_info_line_with_tooltip(
                        section,
                        self.translation_func(field_config["label_key"]),
                        value,
                        tooltip_text,
                        self.widget_manager,
                        self.cached_width,
                        self.translation_func,
                        field_config.get("var_name"),
                        widget_key,
                        field_text_color
                    )
                elif field_config.get("is_list"):
                    add_list_info(
                        section, 
                        self.translation_func(field_config["label_key"]), 
                        value,
                        self.cached_width,
                        self.translation_func
                    )
                else:
                    add_info_line(
                        section,
                        self.translation_func(field_config["label_key"]),
                        value,
                        self.widget_manager,
                        self.cached_width,
                        self.translation_func,
                        field_config.get("var_name"),
                        widget_key,
                        field_text_color
                    )
                fields_rendered += 1
            except (KeyError, AttributeError, ValueError) as e:
                # 跳过有问题的字段，继续渲染其他字段
                continue
        
        # 添加提示标签
        if config.get("has_hint"):
            hint_key = config.get("hint_key")
            if hint_key:
                try:
                    hint_label = ttk.Label(
                        section, 
                        text=self.translation_func(hint_key), 
                        font=get_cjk_font(9), 
                        foreground="gray",
                        wraplength=int(self.cached_width * HINT_WRAPLENGTH_RATIO),
                        justify="left"
                    )
                    hint_label.pack(anchor="w", padx=5, pady=(5, 0))
                    self.widget_manager.register_hint_label({
                        'label': hint_label,
                        'text_key': hint_key
                    })
                except (AttributeError, tk.TclError):
                    pass
        
        return section
    
    def render_all_sections(
        self,
        parent: tk.Widget,
        save_data: Dict[str, Any],
        computed_data: Dict[str, Any],
        is_fanatic_route: bool
    ) -> int:
        """渲染所有section
        
        Args:
            parent: 父容器
            save_data: 存档数据
            computed_data: 计算后的共享数据
            is_fanatic_route: 是否为狂信徒路线
            
        Returns:
            成功渲染的section数量
        """
        section_order: List[Tuple[str, bool] | str] = [
            ("fanatic_related", is_fanatic_route),
            *DEFAULT_SECTION_ORDER,
            ("fanatic_related", not is_fanatic_route)
        ]
        
        rendered_count = 0
        for section_item in section_order:
            try:
                if isinstance(section_item, tuple):
                    section_key, condition = section_item
                    if condition:
                        section = self.render_section(
                            section_key, 
                            parent, 
                            save_data, 
                            computed_data, 
                            is_fanatic_route
                        )
                        if section:
                            rendered_count += 1
                else:
                    section = self.render_section(
                        section_item, 
                        parent, 
                        save_data, 
                        computed_data, 
                        is_fanatic_route
                    )
                    if section:
                        rendered_count += 1
            except Exception:
                # 单个section渲染失败不影响其他section
                continue
        
        return rendered_count
    
    def update_incremental(
        self,
        save_data: Dict[str, Any],
        computed_data: Dict[str, Any],
        is_fanatic_route: bool,
        scrollable_frame: tk.Widget,
        is_initialized_ref: Dict[str, bool]
    ) -> bool:
        """增量更新存档信息（不销毁重建widget）
        
        Args:
            save_data: 存档数据
            computed_data: 计算后的共享数据
            is_fanatic_route: 是否为狂信徒路线
            scrollable_frame: 可滚动frame
            is_initialized_ref: 初始化状态引用字典
            
        Returns:
            如果更新成功返回True，否则返回False（需要完整重建）
        """
        if not self.widget_manager._widget_map:
            is_initialized_ref['value'] = False
            return False
        
        # 检查第一个widget是否有效
        first_key = next(iter(self.widget_manager._widget_map), None)
        if first_key:
            widget_info = self.widget_manager.get_widget(first_key)
            if widget_info:
                value_widget = widget_info.get('value_widget')
                if not value_widget or not value_widget.winfo_exists():
                    is_initialized_ref['value'] = False
                    return False
        
        # 更新狂信徒section的颜色
        if is_fanatic_route:
            fanatic_section = self.widget_manager.get_section("fanatic_related")
            if not fanatic_section or not fanatic_section.winfo_exists():
                is_initialized_ref['value'] = False
                return False
            
            self._update_fanatic_section_colors(fanatic_section, scrollable_frame)
        
        # 更新动态widget
        self._update_dynamic_widgets(computed_data)
        
        # 更新所有字段
        configs = self._get_field_configs()
        self._update_all_fields(configs, save_data, computed_data, is_fanatic_route, is_initialized_ref)
        
        return True
    
    def _update_fanatic_section_colors(
        self,
        fanatic_section: tk.Widget,
        scrollable_frame: tk.Widget
    ) -> None:
        """更新狂信徒section的颜色"""
        section_frame = getattr(fanatic_section, '_section_frame', None)
        if not section_frame or not section_frame.winfo_exists():
            return
        
        section_frame.config(bg=Colors.WHITE)
        
        title_widget_info = self.widget_manager.get_section_title("fanatic_related")
        if title_widget_info:
            title_label = title_widget_info.get('title_label')
            if title_label and title_label.winfo_exists():
                title_label.config(foreground=FANATIC_ROUTE_TEXT_COLOR)
        
        configs = self._get_field_configs()
        fanatic_config = configs.get("fanatic_related", {})
        fanatic_widget_keys = [
            field.get("widget_key") 
            for field in fanatic_config.get("fields", [])
            if field.get("widget_key")
        ]
        
        for widget_key in fanatic_widget_keys:
            widget_info = self.widget_manager.get_widget(widget_key)
            if widget_info:
                value_widget = widget_info.get('value_widget')
                label_widget = widget_info.get('label_widget')
                if value_widget and value_widget.winfo_exists():
                    value_widget.config(foreground=FANATIC_ROUTE_TEXT_COLOR)
                if label_widget and label_widget.winfo_exists():
                    label_widget.config(foreground=FANATIC_ROUTE_TEXT_COLOR)
        
        # 递归更新所有Label的颜色
        self._update_widget_colors_recursive(fanatic_section, FANATIC_ROUTE_TEXT_COLOR)
        
        # 调整section位置
        if scrollable_frame and scrollable_frame.winfo_exists():
            children = list(scrollable_frame.winfo_children())
            if children and children[0] != section_frame:
                section_frame.pack_forget()
                if children:
                    section_frame.pack(fill="x", padx=10, pady=5, before=children[0])
                else:
                    section_frame.pack(fill="x", padx=10, pady=5)
    
    def _update_widget_colors_recursive(self, widget: tk.Widget, color: str) -> None:
        """递归更新widget中所有Label的文字颜色"""
        if isinstance(widget, (tk.Label, ttk.Label)):
            if not isinstance(widget.master, (tk.Button, ttk.Button)):
                widget.config(foreground=color)
        elif isinstance(widget, tk.Frame):
            for child in widget.winfo_children():
                self._update_widget_colors_recursive(child, color)
    
    def _update_dynamic_widgets(self, computed_data: Dict[str, Any]) -> None:
        """更新动态widget"""
        if "missing_characters" in self.widget_manager._dynamic_widgets:
            widget_info = self.widget_manager.get_dynamic_widget("missing_characters")
            if widget_info:
                section = widget_info.get('section')
                if section and section.winfo_exists():
                    missing_characters = computed_data.get("missing_characters", [])
                    if widget_info.get('is_list'):
                        # 清理旧的列表widget
                        for child in section.winfo_children():
                            if hasattr(child, 'items_data'):
                                child.destroy()
                    
                    if missing_characters:
                        add_list_info(
                            section, 
                            self.translation_func("missing_characters"), 
                            missing_characters,
                            self.cached_width,
                            self.translation_func
                        )
                        widget_info['is_list'] = True
                    else:
                        add_info_line(
                            section, 
                            self.translation_func("missing_characters"), 
                            self.translation_func("none"), 
                            self.widget_manager,
                            self.cached_width,
                            self.translation_func,
                            None, 
                            "missing_characters"
                        )
                        widget_info['is_list'] = False
    
    def _update_all_fields(
        self,
        configs: Dict[str, Any],
        save_data: Dict[str, Any],
        computed_data: Dict[str, Any],
        is_fanatic_route: bool,
        is_initialized_ref: Dict[str, bool]
    ) -> None:
        """更新所有字段的值"""
        # 更新非狂信徒section的字段
        for section_key, section_config in configs.items():
            if section_key == "fanatic_related":
                continue
            
            for field_config in section_config.get("fields", []):
                widget_key = field_config.get("widget_key")
                if not widget_key:
                    continue
                
                value = format_field_value(
                    field_config, 
                    save_data, 
                    computed_data, 
                    self.translation_func
                )
                
                if field_config.get("is_dynamic") and field_config.get("is_list"):
                    continue
                
                if field_config.get("has_tooltip"):
                    tooltip_key = field_config.get("tooltip_key")
                    tooltip_text = self.translation_func(tooltip_key) if tooltip_key else ""
                    if not tooltip_text and field_config.get("tooltip_optional"):
                        add_info_line(
                            None,
                            self.translation_func(field_config["label_key"]),
                            value,
                            self.widget_manager,
                            self.cached_width,
                            self.translation_func,
                            field_config.get("var_name"),
                            widget_key,
                            None,
                            is_initialized_ref
                        )
                        continue
                    
                    add_info_line_with_tooltip(
                        None,
                        self.translation_func(field_config["label_key"]),
                        value,
                        tooltip_text,
                        self.widget_manager,
                        self.cached_width,
                        self.translation_func,
                        field_config.get("var_name"),
                        widget_key,
                        None,
                        is_initialized_ref
                    )
                else:
                    add_info_line(
                        None,
                        self.translation_func(field_config["label_key"]),
                        value,
                        self.widget_manager,
                        self.cached_width,
                        self.translation_func,
                        field_config.get("var_name"),
                        widget_key,
                        None,
                        is_initialized_ref
                    )
        
        # 更新狂信徒section的字段（如果不是狂信徒路线）
        if not is_fanatic_route:
            fanatic_config = configs.get("fanatic_related", {})
            for field_config in fanatic_config.get("fields", []):
                widget_key = field_config.get("widget_key")
                if not widget_key:
                    continue
                
                value = format_field_value(
                    field_config, 
                    save_data, 
                    computed_data, 
                    self.translation_func
                )
                
                if field_config.get("has_tooltip"):
                    tooltip_text = self.translation_func(field_config.get("tooltip_key", ""))
                    add_info_line_with_tooltip(
                        None,
                        self.translation_func(field_config["label_key"]),
                        value,
                        tooltip_text,
                        self.widget_manager,
                        self.cached_width,
                        self.translation_func,
                        field_config.get("var_name"),
                        widget_key,
                        None,
                        is_initialized_ref
                    )
                else:
                    add_info_line(
                        None,
                        self.translation_func(field_config["label_key"]),
                        value,
                        self.widget_manager,
                        self.cached_width,
                        self.translation_func,
                        field_config.get("var_name"),
                        widget_key,
                        None,
                        is_initialized_ref
                    )

