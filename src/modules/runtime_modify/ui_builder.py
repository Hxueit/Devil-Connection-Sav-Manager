"""运行时修改UI构建器

负责创建运行时修改标签页的所有UI组件。
"""

import logging
from typing import Dict, Any, Callable, Optional

import customtkinter as ctk
import tkinter as tk
from tkinter import font as tkfont

from src.modules.runtime_modify.config import RuntimeModifyConfig
from src.utils.styles import Colors, get_cjk_font

logger = logging.getLogger(__name__)


class RuntimeModifyUIBuilder:
    """运行时修改UI构建器 - 负责创建所有UI组件"""
    
    def __init__(
        self,
        parent: ctk.CTkFrame,
        t_func: Callable[[str], Any]
    ) -> None:
        """初始化UI构建器
        
        Args:
            parent: 父容器
            t_func: 翻译函数
        """
        self.parent = parent
        self.t = t_func
        self._description_expanded: bool = False
    
    def create_standard_button(
        self,
        parent: ctk.CTkFrame,
        text: str,
        command: Callable[[], None]
    ) -> ctk.CTkButton:
        """创建标准样式的按钮（与"检查更新"相同样式）"""
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            corner_radius=8,
            fg_color=Colors.WHITE,
            hover_color=Colors.LIGHT_GRAY,
            border_width=1,
            border_color=Colors.GRAY,
            text_color=Colors.TEXT_PRIMARY,
            font=get_cjk_font(10)
        )
    
    def build(
        self,
        on_port_changed: Callable[[], None],
        on_check_port: Callable[[], None],
        on_launch_clicked: Callable[[], None],
        on_stop_clicked: Callable[[], None],
        on_sf_edit_clicked: Callable[[], None],
        on_tyrano_edit_clicked: Callable[[], None],
        on_cache_clean_clicked: Callable[[], None],
        on_open_console_clicked: Callable[[], None],
        on_toggle_description: Callable[[], None],
        update_status: Callable[[str], None],
        update_hook_status: Callable[[Optional[bool]], None],
        on_force_fast_forward_clicked: Optional[Callable[[], None]] = None
    ) -> Dict[str, Any]:
        """构建所有UI组件
        
        Args:
            on_port_changed: 端口输入变化回调
            on_check_port: 检查端口状态回调
            on_launch_clicked: 启动按钮点击回调
            on_stop_clicked: 停止按钮点击回调
            on_sf_edit_clicked: sf编辑按钮点击回调
            on_tyrano_edit_clicked: tyrano编辑按钮点击回调
            on_cache_clean_clicked: 清理缓存按钮点击回调
            on_open_console_clicked: 打开控制台按钮点击回调
            on_toggle_description: 切换描述回调
            update_status: 更新状态文本回调
            update_hook_status: 更新Hook状态回调
            on_force_fast_forward_clicked: 强制启用快进按钮点击回调
            
        Returns:
            包含所有UI组件引用的字典
        """
        main_container = ctk.CTkFrame(self.parent, fg_color=Colors.WHITE)
        main_container.pack(fill="both", expand=True, padx=0, pady=20)
        
        content_frame = ctk.CTkFrame(
            main_container,
            fg_color=Colors.WHITE,
            border_width=0
        )
        content_frame.pack(fill="both", expand=True)
        
        # 创建各个区域
        description_section = self.create_description_section(
            content_frame, on_toggle_description
        )
        config_section = self.create_config_section(
            content_frame, on_port_changed, on_check_port
        )
        action_section = self.create_action_section(
            content_frame,
            on_launch_clicked,
            on_stop_clicked,
            update_hook_status,
            on_force_fast_forward_clicked
        )
        status_section = self.create_status_section(
            content_frame,
            on_open_console_clicked,
            on_sf_edit_clicked,
            on_tyrano_edit_clicked,
            on_cache_clean_clicked,
            update_status
        )
        
        # 合并所有组件引用
        ui_components = {
            **description_section,
            **config_section,
            **action_section,
            **status_section,
        }
        
        return ui_components
    
    def create_description_section(
        self,
        parent: ctk.CTkFrame,
        on_toggle_description: Callable[[], None]
    ) -> Dict[str, Any]:
        """创建说明文字区域（可折叠）
        
        Args:
            parent: 父容器
            on_toggle_description: 切换描述回调
            
        Returns:
            包含描述相关组件的字典
        """
        description_container = ctk.CTkFrame(
            parent,
            fg_color=Colors.WHITE,
            border_width=0
        )
        description_container.pack(anchor="w", fill="x", pady=(0, 15))
        
        # "这是什么"标签（带下划线，可点击）
        base_font = get_cjk_font(10)
        if not isinstance(base_font, tuple) or len(base_font) < 2:
            logger.warning("Invalid font specification from get_cjk_font")
            base_font = ("Microsoft YaHei", 10)
        
        font_kwargs: Dict[str, Any] = {
            "family": base_font[0],
            "size": base_font[1],
            "underline": True
        }
        if len(base_font) > 2 and base_font[2] == "bold":
            font_kwargs["weight"] = "bold"
        font_obj = tkfont.Font(**font_kwargs)
        
        what_is_this_label = tk.Label(
            description_container,
            text=self.t("runtime_modify_what_is_this"),
            font=font_obj,
            fg=Colors.TEXT_PRIMARY,
            bg=Colors.WHITE,
            cursor="hand2",
            anchor="w"
        )
        what_is_this_label.pack(anchor="w", pady=(0, 5))
        what_is_this_label.bind("<Button-1>", lambda e: on_toggle_description())
        
        # 描述文字标签（默认隐藏）
        description_label = ctk.CTkLabel(
            description_container,
            text=self.t("runtime_modify_description"),
            font=get_cjk_font(11),
            text_color=Colors.TEXT_PRIMARY,
            justify="left",
            wraplength=700,
            anchor="w"
        )
        description_label.pack_forget()
        
        return {
            "description_container": description_container,
            "what_is_this_label": what_is_this_label,
            "description_label": description_label,
            "_description_expanded": False,
        }
    
    def create_config_section(
        self,
        parent: ctk.CTkFrame,
        on_port_changed: Callable[[], None],
        on_check_port: Callable[[], None]
    ) -> Dict[str, Any]:
        """创建配置区域
        
        Args:
            parent: 父容器
            on_port_changed: 端口输入变化回调
            on_check_port: 检查端口状态回调
            
        Returns:
            包含配置相关组件的字典
        """
        port_row = ctk.CTkFrame(parent, fg_color=Colors.WHITE)
        port_row.pack(fill="x", pady=(0, 10))
        
        port_label = ctk.CTkLabel(
            port_row,
            text=self.t("runtime_modify_port_label"),
            font=get_cjk_font(11),
            text_color=Colors.TEXT_PRIMARY
        )
        port_label.pack(side="left")
        
        port_entry = ctk.CTkEntry(
            port_row,
            placeholder_text=str(RuntimeModifyConfig.DEFAULT_PORT),
            font=get_cjk_font(11),
            width=100,
            corner_radius=8,
            fg_color=Colors.WHITE,
            text_color=Colors.TEXT_PRIMARY,
            border_color=Colors.GRAY
        )
        port_entry.pack(side="left", padx=(5, 10))
        port_entry.insert(0, str(RuntimeModifyConfig.DEFAULT_PORT))
        port_entry.bind("<KeyRelease>", lambda e: on_port_changed())
        
        check_port_btn = ctk.CTkButton(
            port_row,
            text=self.t("runtime_modify_check_port"),
            command=on_check_port,
            corner_radius=8,
            fg_color=Colors.WHITE,
            hover_color=Colors.LIGHT_GRAY,
            border_width=1,
            border_color=Colors.GRAY,
            text_color=Colors.TEXT_PRIMARY,
            font=get_cjk_font(9),
            width=80,
            height=28
        )
        check_port_btn.pack(side="left", padx=(0, 10))
        
        port_status_label = ctk.CTkLabel(
            port_row,
            text="",
            font=get_cjk_font(10),
            text_color=Colors.TEXT_SECONDARY
        )
        port_status_label.pack(side="left")
        
        port_hint = ctk.CTkLabel(
            parent,
            text=self.t("runtime_modify_port_hint"),
            font=get_cjk_font(9),
            text_color=Colors.TEXT_SECONDARY
        )
        port_hint.pack(anchor="w", pady=(0, 15))
        
        return {
            "port_entry": port_entry,
            "port_status_label": port_status_label,
        }
    
    def create_action_section(
        self,
        parent: ctk.CTkFrame,
        on_launch_clicked: Callable[[], None],
        on_stop_clicked: Callable[[], None],
        update_hook_status: Callable[[Optional[bool]], None],
        on_force_fast_forward_clicked: Optional[Callable[[], None]] = None
    ) -> Dict[str, Any]:
        """创建操作区域
        
        Args:
            parent: 父容器
            on_launch_clicked: 启动按钮点击回调
            on_stop_clicked: 停止按钮点击回调
            update_hook_status: 更新Hook状态回调
            on_force_fast_forward_clicked: 强制启用快进按钮点击回调
            
        Returns:
            包含操作相关组件的字典
        """
        btn_row = ctk.CTkFrame(parent, fg_color=Colors.WHITE)
        btn_row.pack(fill="x", pady=(0, 10))
        
        launch_button = self.create_standard_button(
            btn_row,
            self.t("runtime_modify_launch_button"),
            on_launch_clicked
        )
        launch_button.pack(side="left", padx=(0, 10))
        
        stop_button = self.create_standard_button(
            btn_row,
            self.t("runtime_modify_stop_server"),
            on_stop_clicked
        )
        stop_button.pack(side="left", padx=(0, 10))
        stop_button.configure(state="disabled")
        
        game_status_label = ctk.CTkLabel(
            btn_row,
            text=self.t("runtime_modify_game_stopped"),
            font=get_cjk_font(10),
            text_color=Colors.TEXT_SECONDARY
        )
        game_status_label.pack(side="left", padx=(10, 0))
        
        hook_status_label = ctk.CTkLabel(
            btn_row,
            text=self.t("runtime_modify_hook_disabled"),
            font=get_cjk_font(10),
            text_color=Colors.TEXT_SECONDARY
        )
        hook_status_label.pack(side="left", padx=(10, 0))
        
        force_fast_forward_button = ctk.CTkButton(
            btn_row,
            text=self.t("runtime_modify_force_fast_forward"),
            command=on_force_fast_forward_clicked if on_force_fast_forward_clicked else None,
            corner_radius=8,
            fg_color=Colors.WHITE,
            hover_color=Colors.LIGHT_GRAY,
            border_width=1,
            border_color=Colors.GRAY,
            text_color=Colors.TEXT_PRIMARY,
            font=get_cjk_font(9),
            width=100,
            height=28,
            state="disabled"
        )
        force_fast_forward_button.pack(side="right", padx=(10, 0))
        
        hint_label = ctk.CTkLabel(
            btn_row,
            text=self.t("runtime_modify_force_fast_forward_hint"),
            font=get_cjk_font(8),
            text_color=Colors.TEXT_SECONDARY
        )
        hint_label.pack(side="right", padx=(5, 0))
        
        return {
            "launch_button": launch_button,
            "stop_button": stop_button,
            "game_status_label": game_status_label,
            "hook_status_label": hook_status_label,
            "force_fast_forward_button": force_fast_forward_button,
            "force_fast_forward_hint": hint_label,
        }
    
    def create_status_section(
        self,
        parent: ctk.CTkFrame,
        on_open_console_clicked: Callable[[], None],
        on_sf_edit_clicked: Callable[[], None],
        on_tyrano_edit_clicked: Callable[[], None],
        on_cache_clean_clicked: Callable[[], None],
        update_status: Callable[[str], None]
    ) -> Dict[str, Any]:
        """创建状态显示区域
        
        Args:
            parent: 父容器
            on_open_console_clicked: 打开控制台按钮点击回调
            on_sf_edit_clicked: sf编辑按钮点击回调
            on_tyrano_edit_clicked: tyrano编辑按钮点击回调
            on_cache_clean_clicked: 清理缓存按钮点击回调
            update_status: 更新状态文本回调
            
        Returns:
            包含状态相关组件的字典
        """
        status_title = ctk.CTkLabel(
            parent,
            text=self.t("runtime_modify_status_title"),
            font=get_cjk_font(11, "bold"),
            text_color=Colors.TEXT_PRIMARY
        )
        status_title.pack(anchor="w", pady=(10, 5))
        
        status_text = ctk.CTkTextbox(
            parent,
            height=120,
            font=get_cjk_font(10),
            fg_color=Colors.LIGHT_GRAY,
            text_color=Colors.TEXT_PRIMARY,
            border_color=Colors.GRAY,
            border_width=1,
            corner_radius=8,
            wrap="word"
        )
        status_text.pack(fill="both", expand=True)
        status_text.configure(state="disabled")
        
        update_status(self.t("runtime_modify_status_ready"))
        
        # 按钮行：打开控制台、sf内存变量修改、Tyrano内存变量修改、清理缓存
        button_row = ctk.CTkFrame(parent, fg_color=Colors.WHITE)
        button_row.pack(anchor="w", pady=(10, 0), fill="x")
        
        open_console_button = self.create_standard_button(
            button_row,
            self.t("runtime_modify_open_console_button"),
            on_open_console_clicked
        )
        open_console_button.pack(side="left")
        
        # 竖线分割（高度与按钮相同）
        separator1 = ctk.CTkFrame(button_row, width=1, height=28, fg_color=Colors.GRAY)
        separator1.pack(side="left", padx=(10, 10))
        separator1.pack_propagate(False)
        
        sf_edit_button = self.create_standard_button(
            button_row,
            self.t("runtime_modify_sf_edit_button"),
            on_sf_edit_clicked
        )
        sf_edit_button.pack(side="left")
        sf_edit_button.configure(state="disabled")
        
        # sf和tyrano按钮之间没有竖线
        
        tyrano_edit_button = self.create_standard_button(
            button_row,
            self.t("runtime_modify_tyrano_edit_button"),
            on_tyrano_edit_clicked
        )
        tyrano_edit_button.pack(side="left", padx=(10, 0))
        tyrano_edit_button.configure(state="disabled")
        
        # 竖线分割（高度与按钮相同）
        separator2 = ctk.CTkFrame(button_row, width=1, height=28, fg_color=Colors.GRAY)
        separator2.pack(side="left", padx=(10, 10))
        separator2.pack_propagate(False)
        
        cache_clean_button = self.create_standard_button(
            button_row,
            self.t("cache_clean_button"),
            on_cache_clean_clicked
        )
        cache_clean_button.pack(side="left")
        cache_clean_button.configure(state="disabled")
        
        return {
            "status_text": status_text,
            "open_console_button": open_console_button,
            "sf_edit_button": sf_edit_button,
            "tyrano_edit_button": tyrano_edit_button,
            "cache_clean_button": cache_clean_button,
        }

