"""DevTools 控制台窗口

提供独立的控制台窗口，允许用户直接向游戏运行时发送 JavaScript 命令。
"""
import asyncio
import json
import logging
import threading
from typing import Optional, Dict, Any, Callable, List

import customtkinter as ctk
import tkinter as tk

from src.modules.runtime_modify.service import RuntimeModifyService
from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import set_window_icon
from src.modules.others.utils import center_window

logger = logging.getLogger(__name__)

# 命令历史最大数量
_MAX_HISTORY = 100


class DevToolsConsoleWindow(ctk.CTkToplevel):
    """DevTools 控制台窗口
    
    提供交互式控制台界面，允许用户执行 JavaScript 命令并查看结果。
    """
    
    def __init__(
        self,
        parent_window: ctk.CTk,
        service: RuntimeModifyService,
        get_ws_url: Callable[[], Optional[str]],
        translations: Dict[str, Dict[str, str]],
        current_language: str,
        on_close_callback: Optional[Callable[[], None]] = None
    ) -> None:
        """初始化控制台窗口
        
        Args:
            parent_window: 父窗口
            service: RuntimeModifyService 实例
            get_ws_url: 获取当前 WebSocket URL 的回调函数
            translations: 翻译字典
            current_language: 当前语言
            on_close_callback: 窗口关闭时的回调函数（用于清理引用）
        """
        super().__init__(parent_window)
        
        self.service = service
        self.get_ws_url = get_ws_url
        self.translations = translations
        self.current_language = current_language
        self.on_close_callback = on_close_callback
        
        # 命令历史
        self._command_history: List[str] = []
        self._history_index: int = -1  # -1 表示在最新位置
        self._current_input: str = ""  # 保存当前输入，用于 ↓ 键恢复
        
        # UI组件
        self.output_textbox: Optional[ctk.CTkTextbox] = None
        self.input_entry: Optional[ctk.CTkEntry] = None
        self.send_button: Optional[ctk.CTkButton] = None
        self.clear_button: Optional[ctk.CTkButton] = None
        self.disabled_hint_label: Optional[ctk.CTkLabel] = None
        
        # 状态
        self.is_executing = False
        self._executor: Optional[threading.Thread] = None
        
        # 配置窗口
        self._configure_window()
        self._init_ui()
        
        # 绑定窗口关闭事件
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)
        
        # 设置窗口图标（延迟设置，确保在 CTkToplevel 初始化完成后）
        # CTkToplevel 可能会在显示时重置图标，所以需要多次设置
        self.after(50, lambda: set_window_icon(self))
        self.after(200, lambda: set_window_icon(self))
    
    def _configure_window(self) -> None:
        """配置窗口属性"""
        self.title(self.t("runtime_modify_console_title"))
        self.geometry("800x600")
        self.minsize(600, 400)
        self.transient(self.master)
        
        # 居中显示
        center_window(self)
        self.after(0, self._raise_to_front)

    def _raise_to_front(self) -> None:
        try:
            if not self.winfo_exists():
                return
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass
    
    def t(self, key: str, **kwargs: Any) -> str:
        """翻译函数"""
        text = self.translations.get(self.current_language, {}).get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError):
                logger.debug(f"Translation format error for key '{key}'")
                return text
        return text
    
    def _init_ui(self) -> None:
        """初始化UI"""
        # 主容器
        main_container = ctk.CTkFrame(self, fg_color=Colors.WHITE)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 输出区域
        self.output_textbox = ctk.CTkTextbox(
            main_container,
            font=get_cjk_font(10, "monospace"),
            fg_color=Colors.LIGHT_GRAY,
            text_color=Colors.TEXT_PRIMARY,
            border_color=Colors.GRAY,
            border_width=1,
            corner_radius=8,
            wrap="word"
        )
        self.output_textbox.pack(fill="both", expand=True, pady=(0, 10))
        self.output_textbox.configure(state="disabled")
        
        # 禁用提示（初始隐藏）
        self.disabled_hint_label = ctk.CTkLabel(
            main_container,
            text=self.t("runtime_modify_console_disabled_hint"),
            font=get_cjk_font(9),
            text_color=Colors.TEXT_SECONDARY,
            wraplength=600
        )
        self.disabled_hint_label.pack(anchor="w", pady=(0, 10))
        self.disabled_hint_label.pack_forget()
        
        # 输入区域容器
        input_container = ctk.CTkFrame(main_container, fg_color=Colors.WHITE)
        input_container.pack(fill="x", pady=(0, 0))
        
        # 输入框
        self.input_entry = ctk.CTkEntry(
            input_container,
            placeholder_text=self.t("runtime_modify_console_input_placeholder"),
            font=get_cjk_font(10, "monospace"),
            fg_color=Colors.WHITE,
            text_color=Colors.TEXT_PRIMARY,
            border_color=Colors.GRAY,
            corner_radius=8
        )
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.input_entry.bind("<Return>", lambda e: self._on_send_clicked())
        # 只绑定 Up 和 Down 键，避免绑定所有 KeyPress 导致的问题
        self.input_entry.bind("<Up>", lambda e: self._on_up_key())
        self.input_entry.bind("<Down>", lambda e: self._on_down_key())
        
        # 按钮容器
        button_container = ctk.CTkFrame(input_container, fg_color=Colors.WHITE)
        button_container.pack(side="right")
        
        # 发送按钮
        self.send_button = ctk.CTkButton(
            button_container,
            text=self.t("runtime_modify_console_send_button"),
            command=self._on_send_clicked,
            corner_radius=8,
            fg_color=Colors.WHITE,
            hover_color=Colors.LIGHT_GRAY,
            border_width=1,
            border_color=Colors.GRAY,
            text_color=Colors.TEXT_PRIMARY,
            font=get_cjk_font(10),
            width=80
        )
        self.send_button.pack(side="left", padx=(0, 5))
        
        # 清空按钮
        self.clear_button = ctk.CTkButton(
            button_container,
            text=self.t("runtime_modify_console_clear_button"),
            command=self._on_clear_clicked,
            corner_radius=8,
            fg_color=Colors.WHITE,
            hover_color=Colors.LIGHT_GRAY,
            border_width=1,
            border_color=Colors.GRAY,
            text_color=Colors.TEXT_PRIMARY,
            font=get_cjk_font(10),
            width=80
        )
        self.clear_button.pack(side="left")
    
    def _on_up_key(self) -> str:
        """处理 Up 键事件"""
        self._navigate_history(up=True)
        return "break"  # 阻止默认行为
    
    def _on_down_key(self) -> str:
        """处理 Down 键事件"""
        self._navigate_history(up=False)
        return "break"  # 阻止默认行为
    
    def _navigate_history(self, up: bool) -> None:
        """导航命令历史
        
        Args:
            up: True 表示向上（更旧的命令），False 表示向下（更新的命令）
        """
        if not self.input_entry:
            return
        
        if not self._command_history:
            return
        
        if up:
            # 向上导航
            if self._history_index == -1:
                # 从最新位置开始，保存当前输入
                self._current_input = self.input_entry.get()
                self._history_index = len(self._command_history) - 1
            else:
                # 继续向上
                if self._history_index > 0:
                    self._history_index -= 1
                else:
                    # 已经在最旧的位置
                    return
            
            # 显示历史命令
            command = self._command_history[self._history_index]
            self.input_entry.delete(0, "end")
            self.input_entry.insert(0, command)
        else:
            # 向下导航
            if self._history_index == -1:
                # 已经在最新位置
                return
            
            if self._history_index < len(self._command_history) - 1:
                # 继续向下
                self._history_index += 1
                command = self._command_history[self._history_index]
                self.input_entry.delete(0, "end")
                self.input_entry.insert(0, command)
            else:
                # 到达最新位置，恢复当前输入
                self._history_index = -1
                self.input_entry.delete(0, "end")
                if self._current_input:
                    self.input_entry.insert(0, self._current_input)
                    self._current_input = ""
    
    def _add_to_history(self, command: str) -> None:
        """添加命令到历史记录
        
        Args:
            command: 要添加的命令
        """
        if not command.strip():
            return
        
        # 如果与最后一条命令相同，不重复添加
        if self._command_history and self._command_history[-1] == command:
            self._history_index = -1
            return
        
        # 添加到历史
        self._command_history.append(command)
        
        # 限制历史长度
        if len(self._command_history) > _MAX_HISTORY:
            self._command_history.pop(0)
        
        # 重置索引到最新位置
        self._history_index = -1
        self._current_input = ""
    
    def _on_send_clicked(self) -> None:
        """发送按钮点击回调"""
        if self.is_executing:
            return
        
        if not self.input_entry:
            return
        
        command = self.input_entry.get().strip()
        if not command:
            return
        
        # 添加到历史记录
        self._add_to_history(command)
        
        # 清空输入框
        self.input_entry.delete(0, "end")
        
        # 执行命令
        self._execute_command(command)
    
    def _on_clear_clicked(self) -> None:
        """清空历史按钮点击回调"""
        if not self.output_textbox:
            return
        
        self.output_textbox.configure(state="normal")
        self.output_textbox.delete("1.0", "end")
        self.output_textbox.configure(state="disabled")
    
    def _on_window_close(self) -> None:
        """窗口关闭事件处理"""
        # 调用回调函数清理引用
        if self.on_close_callback:
            try:
                self.on_close_callback()
            except Exception as e:
                logger.debug(f"Error in close callback: {e}")
        
        # 销毁窗口
        self.destroy()
    
    def _execute_command(self, command: str) -> None:
        """执行命令
        
        Args:
            command: JavaScript 命令字符串
        """
        if self.is_executing:
            return
        
        # 显示命令
        self._append_output(
            self.t("runtime_modify_console_command_prefix") + command
        )
        
        # 获取 ws_url
        ws_url = self.get_ws_url()
        if not ws_url:
            self._append_output(
                self.t("runtime_modify_console_error_prefix") + 
                self.t("runtime_modify_console_no_connection"),
                is_error=True
            )
            return
        
        # 设置执行状态
        self.is_executing = True
        if self.send_button:
            self.send_button.configure(state="disabled")
        
        # 在后台线程中执行
        def run_in_thread() -> None:
            """在后台线程中运行异步代码"""
            loop: Optional[asyncio.AbstractEventLoop] = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                result, error = loop.run_until_complete(
                    self.service.eval_expr(ws_url, command)
                )
                
                # 在主线程中更新UI
                self.after(0, lambda: self._on_command_complete(result, error))
            except Exception as e:
                logger.exception("Error executing command")
                error_msg = {"message": f"Execution failed: {e}"}
                self.after(0, lambda: self._on_command_complete(None, error_msg))
            finally:
                if loop:
                    try:
                        pending_tasks = asyncio.all_tasks(loop)
                        if pending_tasks:
                            for task in pending_tasks:
                                task.cancel()
                            loop.run_until_complete(
                                asyncio.gather(*pending_tasks, return_exceptions=True)
                            )
                        loop.close()
                    except Exception as e:
                        logger.debug(f"Error cleaning up event loop: {e}")
        
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
        self._executor = thread
    
    def _on_command_complete(
        self,
        result: Any,
        error: Optional[Dict[str, Any]]
    ) -> None:
        """命令执行完成回调（在主线程执行）
        
        Args:
            result: 执行结果
            error: 错误信息（如果有）
        """
        self.is_executing = False
        if self.send_button and self.send_button.winfo_exists():
            try:
                self.send_button.configure(state="normal")
            except (tk.TclError, AttributeError):
                pass
        
        if error is not None:
            # 显示错误
            error_message = error.get("message", str(error))
            self._append_output(
                self.t("runtime_modify_console_error_prefix") + error_message,
                is_error=True
            )
        else:
            # 显示结果
            result_str = self._format_result(result)
            self._append_output(
                self.t("runtime_modify_console_result_prefix") + result_str
            )
    
    def _format_result(self, result: Any) -> str:
        """格式化执行结果
        
        Args:
            result: 执行结果
            
        Returns:
            格式化后的字符串
        """
        if result is None:
            return "undefined"
        elif isinstance(result, str):
            # 字符串需要加引号
            return json.dumps(result)
        elif isinstance(result, (dict, list)):
            # 对象和数组使用 JSON 格式化
            try:
                return json.dumps(result, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                return str(result)
        else:
            return str(result)
    
    def _append_output(self, text: str, is_error: bool = False) -> None:
        """追加输出到控制台
        
        Args:
            text: 要追加的文本
            is_error: 是否为错误信息
        """
        if not self.output_textbox or not self.output_textbox.winfo_exists():
            return
        
        try:
            self.output_textbox.configure(state="normal")
            self.output_textbox.insert("end", text + "\n")
            self.output_textbox.configure(state="disabled")
            # 滚动到底部
            self.output_textbox.see("end")
        except (tk.TclError, AttributeError):
            pass
    
    def set_enabled(self, enabled: bool) -> None:
        """设置控制台启用/禁用状态
        
        Args:
            enabled: 是否启用
        """
        # 检查 widget 是否仍然存在（可能已被销毁）
        if self.input_entry and self.input_entry.winfo_exists():
            try:
                self.input_entry.configure(state="normal" if enabled else "disabled")
            except (tk.TclError, AttributeError):
                pass
        
        if self.send_button and self.send_button.winfo_exists():
            try:
                self.send_button.configure(state="normal" if enabled else "disabled")
            except (tk.TclError, AttributeError):
                pass
        
        if self.clear_button and self.clear_button.winfo_exists():
            try:
                self.clear_button.configure(state="normal" if enabled else "disabled")
            except (tk.TclError, AttributeError):
                pass
        
        # 显示/隐藏禁用提示
        if self.disabled_hint_label and self.disabled_hint_label.winfo_exists():
            try:
                if enabled:
                    self.disabled_hint_label.pack_forget()
                else:
                    # 找到输入容器的父容器
                    input_container = self.input_entry.master if (self.input_entry and self.input_entry.winfo_exists()) else None
                    if input_container:
                        self.disabled_hint_label.pack(anchor="w", pady=(0, 10), before=input_container)
                    else:
                        self.disabled_hint_label.pack(anchor="w", pady=(0, 10))
            except (tk.TclError, AttributeError):
                pass
    
    def update_language(self, language: str) -> None:
        """更新语言
        
        Args:
            language: 新的语言代码
        """
        if not isinstance(language, str) or not language:
            logger.warning(f"Invalid language code: {language}")
            return
        
        if language not in self.translations:
            logger.warning(f"Unsupported language: {language}")
            return
        
        self.current_language = language
        
        # 更新窗口标题
        self.title(self.t("runtime_modify_console_title"))
        
        # 更新UI文本
        if self.input_entry and self.input_entry.winfo_exists():
            try:
                self.input_entry.configure(
                    placeholder_text=self.t("runtime_modify_console_input_placeholder")
                )
            except (tk.TclError, AttributeError):
                pass
        
        if self.send_button and self.send_button.winfo_exists():
            try:
                self.send_button.configure(
                    text=self.t("runtime_modify_console_send_button")
                )
            except (tk.TclError, AttributeError):
                pass
        
        if self.clear_button and self.clear_button.winfo_exists():
            try:
                self.clear_button.configure(
                    text=self.t("runtime_modify_console_clear_button")
                )
            except (tk.TclError, AttributeError):
                pass
        
        if self.disabled_hint_label and self.disabled_hint_label.winfo_exists():
            try:
                self.disabled_hint_label.configure(
                    text=self.t("runtime_modify_console_disabled_hint")
                )
            except (tk.TclError, AttributeError):
                pass
