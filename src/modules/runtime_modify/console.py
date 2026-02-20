"""DevTools 控制台窗口

提供独立的控制台窗口，允许用户直接向游戏运行时发送 JavaScript 命令。
"""
import asyncio
import json
import logging
import threading
from typing import Optional, Dict, Any, Callable, List, Tuple

import customtkinter as ctk
import tkinter as tk

from src.modules.runtime_modify.service import RuntimeModifyService
from src.modules.runtime_modify.console_constants import MAX_HISTORY, SHORTCUT_COMMANDS
from src.modules.runtime_modify.quick_save_reader import load_quick_save_info, format_quick_save_info
from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import set_window_icon
from src.modules.others.utils import center_window

logger = logging.getLogger(__name__)


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
        on_close_callback: Optional[Callable[[], None]] = None,
        storage_dir: Optional[str] = None
    ) -> None:
        """初始化控制台窗口
        
        Args:
            parent_window: 父窗口
            service: RuntimeModifyService 实例
            get_ws_url: 获取当前 WebSocket URL 的回调函数
            translations: 翻译字典
            current_language: 当前语言
            on_close_callback: 窗口关闭时的回调函数
            storage_dir: 存储目录路径
        """
        super().__init__(parent_window)
        
        self.service = service
        self.get_ws_url = get_ws_url
        self.translations = translations
        self.current_language = current_language
        self.on_close_callback = on_close_callback
        self.storage_dir = storage_dir
        
        self._command_history: List[str] = []
        self._history_index: int = -1
        self._current_input: str = ""
        
        self.output_textbox: Optional[ctk.CTkTextbox] = None
        self._tk_textbox: Optional[tk.Text] = None
        self.input_entry: Optional[ctk.CTkTextbox] = None
        self._tk_input: Optional[tk.Text] = None
        self.send_button: Optional[ctk.CTkButton] = None
        self.shortcut_button: Optional[ctk.CTkButton] = None
        self.disabled_hint_label: Optional[ctk.CTkLabel] = None
        self._shortcut_popup: Optional[ctk.CTkToplevel] = None
        
        self.is_executing = False
        self._executor: Optional[threading.Thread] = None
        
        self._configure_window()
        self._init_ui()
        
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)
        
        self.after(50, lambda: set_window_icon(self))
        self.after(200, lambda: set_window_icon(self))
    
    def _configure_window(self) -> None:
        """配置窗口属性"""
        self.title(self.t("runtime_modify_console_title"))
        self.geometry("800x600")
        self.minsize(600, 400)
        self.transient(self.master)
        
        center_window(self)
        self.after(0, self._raise_to_front)

    def _raise_to_front(self) -> None:
        """将窗口提升到前台"""
        if self.winfo_exists():
            self.lift()
            self.focus_force()
    
    def t(self, key: str, **kwargs: Any) -> str:
        """翻译函数
        
        Args:
            key: 翻译键
            **kwargs: 格式化参数
            
        Returns:
            翻译后的文本
        """
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
        main_container = ctk.CTkFrame(self, fg_color=Colors.WHITE)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
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
        
        self._tk_textbox = getattr(self.output_textbox, "_textbox", self.output_textbox)
        
        # 绑定点击事件，点击输出区域时聚焦到输入框
        self.output_textbox.bind("<Button-1>", self._on_output_clicked)
        if self._tk_textbox and self._tk_textbox is not self.output_textbox:
            self._tk_textbox.bind("<Button-1>", self._on_output_clicked)
        
        self._tk_textbox.tag_config("cmd", foreground="#6B7280")
        self._tk_textbox.tag_config("result", foreground="#059669")
        self._tk_textbox.tag_config("error", foreground="#DC2626")
        self._tk_textbox.tag_config("undefined", foreground="#9CA3AF")
        
        self.disabled_hint_label = ctk.CTkLabel(
            main_container,
            text=self.t("runtime_modify_console_disabled_hint"),
            font=get_cjk_font(9),
            text_color=Colors.TEXT_SECONDARY,
            wraplength=600
        )
        self.disabled_hint_label.pack(anchor="w", pady=(0, 10))
        self.disabled_hint_label.pack_forget()
        
        input_container = ctk.CTkFrame(main_container, fg_color=Colors.WHITE)
        input_container.pack(fill="x", pady=(0, 0))
        
        self.input_entry = ctk.CTkTextbox(
            input_container,
            font=get_cjk_font(10, "monospace"),
            fg_color=Colors.WHITE,
            text_color=Colors.TEXT_PRIMARY,
            border_color=Colors.GRAY,
            border_width=1,
            corner_radius=8,
            wrap="word",
            height=35
        )
        self.input_entry.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        # 获取底层 tk.Text 用于事件绑定
        self._tk_input = getattr(self.input_entry, "_textbox", self.input_entry)
        
        # Enter 发送，Shift+Enter 换行
        self._tk_input.bind("<Return>", lambda e: self._on_return_key())
        self._tk_input.bind("<Shift-Return>", lambda e: None)  # 允许默认换行行为
        self._tk_input.bind("<Up>", lambda e: self._on_up_key())
        self._tk_input.bind("<Down>", lambda e: self._on_down_key())
        
        self.bind("<Control-l>", lambda e: self._on_clear_clicked())
        
        button_container = ctk.CTkFrame(input_container, fg_color=Colors.WHITE)
        button_container.pack(side="right")
        
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
        
        self.shortcut_button = ctk.CTkButton(
            button_container,
            text=self.t("runtime_modify_console_shortcut_button"),
            command=self._on_shortcut_clicked,
            corner_radius=8,
            fg_color=Colors.WHITE,
            hover_color=Colors.LIGHT_GRAY,
            border_width=1,
            border_color=Colors.GRAY,
            text_color=Colors.TEXT_PRIMARY,
            font=get_cjk_font(10),
            width=80
        )
        self.shortcut_button.pack(side="left")
    
    def _on_output_clicked(self, _event: Optional[tk.Event] = None) -> Optional[str]:
        """输出区域点击回调"""
        if not self.output_textbox or not self.input_entry:
            return None
        
        content = self.output_textbox.get("1.0", "end-1c").strip()
        if not content:
            self._focus_input_for_editing()
            return "break"

        return None

    def _focus_input_for_editing(self) -> None:
        """将焦点设置到输入框可编辑区域并定位光标"""
        if self.input_entry and self.input_entry.winfo_exists():
            try:
                self.input_entry.configure(state="normal")
            except (tk.TclError, AttributeError, ValueError):
                pass

        if self._tk_input and self._tk_input.winfo_exists():
            try:
                if str(self._tk_input.cget("state")) != str(tk.NORMAL):
                    self._tk_input.configure(state=tk.NORMAL)
            except (tk.TclError, AttributeError):
                pass

        if self.winfo_exists():
            try:
                self.focus_force()
            except (tk.TclError, AttributeError):
                pass

        if self._tk_input and self._tk_input.winfo_exists():
            try:
                self._tk_input.focus_force()
                self._tk_input.mark_set(tk.INSERT, "end-1c")
                self._tk_input.see(tk.INSERT)
                return
            except (tk.TclError, AttributeError):
                pass

        if self.input_entry and self.input_entry.winfo_exists():
            try:
                self.input_entry.focus_set()
            except (tk.TclError, AttributeError):
                pass
    
    def _get_input_text(self) -> str:
        """获取输入框文本
        
        Returns:
            输入框中的文本内容
        """
        if not self.input_entry:
            return ""
        return self.input_entry.get("1.0", "end-1c")
    
    def _clear_input(self) -> None:
        """清空输入框"""
        if self.input_entry and self.input_entry.winfo_exists():
            self.input_entry.delete("1.0", "end")
    
    def _set_input_text(self, text: str) -> None:
        """设置输入框文本
        
        Args:
            text: 要设置的文本内容
        """
        if self.input_entry and self.input_entry.winfo_exists():
            self._focus_input_for_editing()
            self.input_entry.delete("1.0", "end")
            self.input_entry.insert("1.0", text)
            self.input_entry.see("end")
    
    def _on_return_key(self) -> str:
        """处理 Enter 键事件（发送命令）"""
        if not self.is_executing:
            self._on_send_clicked()
        return "break"
    
    def _on_up_key(self) -> str:
        """处理 Up 键事件"""
        if not self._tk_input:
            return "break"
        
        # 检查光标是否在第一行
        cursor_pos = self._tk_input.index(tk.INSERT)
        line_num = int(cursor_pos.split('.')[0])
        
        if line_num == 1:
            self._navigate_history(up=True)
            return "break"
        
        return None
    
    def _on_down_key(self) -> str:
        """处理 Down 键事件"""
        if not self._tk_input:
            return "break"
        
        # 检查光标是否在最后一行
        cursor_pos = self._tk_input.index(tk.INSERT)
        total_lines = int(self._tk_input.index("end-1c").split('.')[0])
        line_num = int(cursor_pos.split('.')[0])
        
        if line_num == total_lines:
            self._navigate_history(up=False)
            return "break"
        
        return None
    
    def _navigate_history(self, up: bool) -> None:
        """导航命令历史
        
        Args:
            up: True 表示向上，False 表示向下
        """
        if not self.input_entry or not self._command_history:
            return
        
        if up:
            if self._history_index == -1:
                self._current_input = self._get_input_text()
                self._history_index = len(self._command_history) - 1
            else:
                if self._history_index > 0:
                    self._history_index -= 1
                else:
                    return
            
            command = self._command_history[self._history_index]
            self._set_input_text(command)
        else:
            if self._history_index == -1:
                return
            
            if self._history_index < len(self._command_history) - 1:
                self._history_index += 1
                command = self._command_history[self._history_index]
                self._set_input_text(command)
            else:
                self._history_index = -1
                if self._current_input:
                    self._set_input_text(self._current_input)
                    self._current_input = ""
                else:
                    self._clear_input()
    
    def _add_to_history(self, command: str) -> None:
        """添加命令到历史记录
        
        Args:
            command: 要添加的命令
        """
        if not command.strip():
            return
        
        if self._command_history and self._command_history[-1] == command:
            self._history_index = -1
            return
        
        self._command_history.append(command)
        
        if len(self._command_history) > MAX_HISTORY:
            self._command_history.pop(0)
        
        self._history_index = -1
        self._current_input = ""
    
    def _on_send_clicked(self) -> None:
        """发送按钮点击回调"""
        if self.is_executing or not self.input_entry:
            return
        
        command = self._get_input_text().strip()
        if not command:
            return
        
        self._add_to_history(command)
        self._clear_input()
        self._execute_command(command)
    
    def _on_clear_clicked(self) -> None:
        """清空输出区域"""
        if self.output_textbox and self.output_textbox.winfo_exists():
            self.output_textbox.configure(state="normal")
            self.output_textbox.delete("1.0", "end")
            self.output_textbox.configure(state="disabled")
    
    def _on_window_close(self) -> None:
        """窗口关闭事件处理"""
        self._destroy_shortcut_popup()

        if self.on_close_callback:
            try:
                self.on_close_callback()
            except Exception as e:
                logger.debug(f"Error in close callback: {e}")
        
        self.destroy()
    
    def _execute_command(self, command: str) -> None:
        """执行命令
        
        Args:
            command: JavaScript 命令字符串
        """
        if self.is_executing:
            return
        
        self._append_output(
            self.t("runtime_modify_console_command_prefix") + command,
            "cmd"
        )
        
        ws_url = self.get_ws_url()
        if not ws_url:
            self._append_output(
                self.t("runtime_modify_console_error_prefix") + 
                self.t("runtime_modify_console_no_connection"),
                "error"
            )
            return
        
        self.is_executing = True
        if self.send_button and self.send_button.winfo_exists():
            self.send_button.configure(state="disabled")
        
        def run_in_thread() -> None:
            """在后台线程中运行异步代码"""
            loop: Optional[asyncio.AbstractEventLoop] = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                result, error = loop.run_until_complete(
                    self.service.eval_expr(ws_url, command)
                )
                
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
        """命令执行完成回调
        
        Args:
            result: 执行结果
            error: 错误信息
        """
        self.is_executing = False
        if self.send_button and self.send_button.winfo_exists():
            self.send_button.configure(state="normal")
        
        if error is not None:
            error_message = error.get("message", str(error))
            self._append_output(
                self.t("runtime_modify_console_error_prefix") + error_message,
                "error"
            )
        else:
            result_str = self._format_result(result)
            output_type = "undefined" if result is None else "result"
            self._append_output(
                self.t("runtime_modify_console_result_prefix") + result_str,
                output_type
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
            return json.dumps(result)
        elif isinstance(result, (dict, list)):
            try:
                return json.dumps(result, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                return str(result)
        else:
            return str(result)
    
    def _append_output(self, text: str, output_type: str = "result") -> None:
        """追加输出到控制台
        
        Args:
            text: 要追加的文本
            output_type: 输出类型
        """
        if not self.output_textbox or not self.output_textbox.winfo_exists():
            return
        
        try:
            self.output_textbox.configure(state="normal")
            
            start_index = self.output_textbox.index("end-1c")
            self.output_textbox.insert("end", text + "\n")
            
            if self._tk_textbox and output_type in ("cmd", "result", "error", "undefined"):
                end_index = self.output_textbox.index("end-1c")
                self._tk_textbox.tag_add(output_type, start_index, end_index)
            
            self.output_textbox.configure(state="disabled")
            self.output_textbox.see("end")
        except (tk.TclError, AttributeError):
            pass
    
    def set_enabled(self, enabled: bool) -> None:
        """设置控制台启用/禁用状态
        
        Args:
            enabled: 是否启用
        """
        if self.input_entry and self.input_entry.winfo_exists():
            self.input_entry.configure(state="normal" if enabled else "disabled")
        
        if self.send_button and self.send_button.winfo_exists():
            self.send_button.configure(state="normal" if enabled else "disabled")
        
        if self.shortcut_button and self.shortcut_button.winfo_exists():
            self.shortcut_button.configure(state="normal" if enabled else "disabled")

        if not enabled:
            self._destroy_shortcut_popup()
        
        if self.disabled_hint_label and self.disabled_hint_label.winfo_exists():
            if enabled:
                self.disabled_hint_label.pack_forget()
            else:
                input_container = self.input_entry.master if (self.input_entry and self.input_entry.winfo_exists()) else None
                if input_container:
                    self.disabled_hint_label.pack(anchor="w", pady=(0, 10), before=input_container)
                else:
                    self.disabled_hint_label.pack(anchor="w", pady=(0, 10))
    
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
        
        self.title(self.t("runtime_modify_console_title"))
        
        # CTkTextbox 不支持 placeholder_text，跳过
        
        if self.send_button and self.send_button.winfo_exists():
            self.send_button.configure(
                text=self.t("runtime_modify_console_send_button")
            )
        
        if self.shortcut_button and self.shortcut_button.winfo_exists():
            self.shortcut_button.configure(
                text=self.t("runtime_modify_console_shortcut_button")
            )

        self._destroy_shortcut_popup()
        
        if self.disabled_hint_label and self.disabled_hint_label.winfo_exists():
            self.disabled_hint_label.configure(
                text=self.t("runtime_modify_console_disabled_hint")
            )
    
    def _on_shortcut_clicked(self) -> None:
        """快捷指令按钮点击回调"""
        if self._shortcut_popup and self._shortcut_popup.winfo_exists():
            self._destroy_shortcut_popup()
            return

        self._create_shortcut_popup()

    def _destroy_shortcut_popup(self) -> None:
        """销毁快捷指令弹层"""
        popup = self._shortcut_popup
        self._shortcut_popup = None
        if not popup:
            return

        try:
            if popup.winfo_exists():
                popup.destroy()
        except (tk.TclError, AttributeError):
            pass

    def _get_shortcut_popup_position(self, width: int, height: int) -> Optional[Tuple[int, int]]:
        """计算快捷指令弹层位置"""
        if not self.shortcut_button or not self.shortcut_button.winfo_exists():
            return None

        self.update_idletasks()
        btn_x = self.shortcut_button.winfo_rootx()
        btn_y = self.shortcut_button.winfo_rooty()
        btn_h = self.shortcut_button.winfo_height()

        x = btn_x
        y = btn_y + btn_h + 6

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        margin = 8

        if x + width > screen_w - margin:
            x = max(margin, screen_w - width - margin)

        if y + height > screen_h - margin:
            y = max(margin, btn_y - height - 6)

        return x, y

    def _create_shortcut_popup(self) -> None:
        """创建快捷指令弹层"""
        if not self.shortcut_button or not self.shortcut_button.winfo_exists():
            return

        self._destroy_shortcut_popup()

        popup = ctk.CTkToplevel(self)
        popup.overrideredirect(True)
        popup.transient(self)
        try:
            popup.attributes("-topmost", True)
        except (tk.TclError, AttributeError):
            pass
        popup.configure(fg_color=Colors.WHITE)

        panel = ctk.CTkFrame(
            popup,
            fg_color=Colors.WHITE,
            border_width=1,
            border_color=Colors.GRAY,
            corner_radius=10
        )
        panel.pack(fill="both", expand=True)

        slot_data = load_quick_save_info(self.storage_dir)
        quick_save_info = format_quick_save_info(slot_data, self.t) if slot_data else None

        for translation_key, command in SHORTCUT_COMMANDS:
            row_button = ctk.CTkButton(
                panel,
                text=self.t(translation_key),
                anchor="w",
                width=260,
                height=34,
                corner_radius=7,
                fg_color=Colors.WHITE,
                hover_color=Colors.LIGHT_GRAY,
                border_width=0,
                text_color=Colors.TEXT_PRIMARY,
                font=get_cjk_font(10)
            )
            row_button.pack(fill="x", padx=6, pady=(6, 0))
            row_button.bind(
                "<ButtonRelease-1>",
                lambda event, cmd=command: self._on_shortcut_item_clicked(event, cmd),
            )

            if translation_key == "runtime_modify_console_cmd_set_quick_save":
                info_text = quick_save_info if quick_save_info else self.t("runtime_modify_console_no_quick_save")
                info_label = ctk.CTkLabel(
                    panel,
                    text=info_text,
                    anchor="w",
                    justify="left",
                    font=get_cjk_font(9),
                    text_color=Colors.TEXT_SECONDARY
                )
                info_label.pack(fill="x", padx=12, pady=(4, 2))

                separator = ctk.CTkFrame(
                    panel,
                    fg_color=Colors.GRAY,
                    height=1,
                    corner_radius=0
                )
                separator.pack(fill="x", padx=8, pady=(2, 0))

        hint_label = ctk.CTkLabel(
            panel,
            text=self.t("runtime_modify_console_shortcut_hint"),
            anchor="w",
            justify="left",
            font=get_cjk_font(8),
            text_color=Colors.TEXT_DISABLED
        )
        hint_label.pack(fill="x", padx=12, pady=(6, 0))
        hint_clear_label = ctk.CTkLabel(
            panel,
            text=self.t("runtime_modify_console_shortcut_hint_clear"),
            anchor="w",
            justify="left",
            font=get_cjk_font(8),
            text_color=Colors.TEXT_DISABLED
        )
        hint_clear_label.pack(fill="x", padx=12, pady=(2, 8))

        panel.update_idletasks()
        popup_width = max(260, panel.winfo_reqwidth())
        popup_height = panel.winfo_reqheight()
        position = self._get_shortcut_popup_position(popup_width, popup_height)
        if position is None:
            popup.destroy()
            return

        x, y = position
        try:
            popup.geometry(f"{popup_width}x{popup_height}+{x}+{y}")
            popup.focus_force()
        except (tk.TclError, AttributeError):
            popup.destroy()
            return

        popup.bind("<Escape>", lambda _e: self._destroy_shortcut_popup())
        popup.bind("<FocusOut>", lambda _e: self.after(10, self._destroy_shortcut_popup))

        self._shortcut_popup = popup

    def _on_shortcut_item_clicked(self, event: tk.Event, command: str) -> str:
        """快捷指令项点击回调，支持 Shift+点击直接执行"""
        execute_immediately = bool(event.state & 0x0001)
        self._on_shortcut_command_selected(command, execute_immediately=execute_immediately)
        return "break"

    def _on_shortcut_command_selected(self, command: str, execute_immediately: bool = False) -> None:
        """快捷指令选中回调

        Args:
            command: 要执行的命令
            execute_immediately: 是否立即发送执行
        """
        self._destroy_shortcut_popup()
        self.after(1, lambda: self._apply_shortcut_command(command, execute_immediately))

    def _apply_shortcut_command(self, command: str, execute_immediately: bool) -> None:
        """在弹层销毁后应用快捷指令到输入框"""
        if not self.input_entry:
            return

        self._set_input_text(command)
        self.after_idle(self._focus_input_for_editing)
        self.after(30, self._focus_input_for_editing)
        if execute_immediately:
            self.after(0, self._on_send_clicked)
