"""运行时修改标签页 UI。"""
import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, Callable, Tuple

import customtkinter as ctk
import tkinter as tk

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False
    keyboard = None

from src.modules.runtime_modify.config import RuntimeModifyConfig
from src.modules.runtime_modify.service import RuntimeModifyService
from src.modules.runtime_modify.state import RuntimeModifyState
from src.modules.runtime_modify.ui_builder import RuntimeModifyUIBuilder
from src.modules.runtime_modify.status_checker import StatusChecker
from src.modules.runtime_modify.utils import (
    check_port_available,
    get_game_exe_path,
    validate_port
)
from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import (
    showerror_relative,
    showinfo_relative
)

logger = logging.getLogger(__name__)

# kag.stat 编辑查看器默认折叠的字段名
DEFAULT_KAG_STAT_COLLAPSED_FIELDS = [
    "map_label",
    "charas",
    "map_keyframe",
    "stack",
    "popopo",
    "map_macro",
    "fuki",
    "three"
]


class RuntimeModifyTab:
    """运行时修改标签页 - 负责端口配置、启动/停止游戏、状态展示及各类编辑/控制台入口。"""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        storage_dir: Optional[str],
        translations: Dict[str, Dict[str, str]],
        current_language: str,
        root: ctk.CTk
    ) -> None:
        """初始化标签页，绑定存储目录、翻译、语言与根窗口，创建服务与状态并构建 UI。"""
        self.parent = parent
        self.storage_dir = Path(storage_dir) if storage_dir else None
        self.translations = translations
        self.current_language = current_language
        self.root = root
        
        self.service = RuntimeModifyService()
        
        if self.storage_dir:
            game_exe_path = get_game_exe_path(str(self.storage_dir))
            if game_exe_path:
                self.service.game_exe_path = game_exe_path
        
        self.state = RuntimeModifyState()
        
        self.port_entry: Optional[ctk.CTkEntry] = None
        self.port_status_label: Optional[ctk.CTkLabel] = None
        self.launch_button: Optional[ctk.CTkButton] = None
        self.stop_button: Optional[ctk.CTkButton] = None
        self.sf_edit_button: Optional[ctk.CTkButton] = None
        self.tyrano_edit_button: Optional[ctk.CTkButton] = None
        self.misc_button: Optional[ctk.CTkButton] = None
        self.game_status_label: Optional[ctk.CTkLabel] = None
        self.hook_status_label: Optional[ctk.CTkLabel] = None
        self.status_text: Optional[ctk.CTkTextbox] = None
        self.console_window: Optional[Any] = None
        self.misc_dialog: Optional[Any] = None
        self.cache_clean_dialog: Optional[Any] = None
        self.open_console_button: Optional[ctk.CTkButton] = None
        self.description_label: Optional[ctk.CTkLabel] = None
        self.what_is_this_label: Optional[tk.Label] = None
        self.description_container: Optional[ctk.CTkFrame] = None
        self._description_expanded: bool = False
        self._hotkey_registered: bool = False
        
        self._init_ui()
        self._init_status_checker()
    
    def t(self, key: str, **kwargs: Any) -> str:
        """根据当前语言获取翻译文本，支持 format 占位符。"""
        text = self.translations.get(self.current_language, {}).get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError):
                logger.debug(f"Translation format error for key '{key}'")
                return text
        return text
    
    def _clear_ui_references(self) -> None:
        """清空所有 UI 组件引用，用于语言切换时重建界面。"""
        self.port_entry = None
        self.port_status_label = None
        self.launch_button = None
        self.stop_button = None
        self.sf_edit_button = None
        self.tyrano_edit_button = None
        self.misc_button = None
        self.game_status_label = None
        self.hook_status_label = None
        self.status_text = None
        self.open_console_button = None
        self.description_label = None
        self.what_is_this_label = None
        self.description_container = None
        self._description_expanded = False
    
    def _init_ui(self) -> None:
        """使用 UIBuilder 构建标签页 UI 并绑定各回调。"""
        ui_builder = RuntimeModifyUIBuilder(self.parent, self.t)
        ui_components = ui_builder.build(
            on_port_changed=self._on_port_changed,
            on_check_port=self._check_port_status,
            on_launch_clicked=self._on_launch_clicked,
            on_stop_clicked=self._on_stop_clicked,
            on_sf_edit_clicked=self._on_sf_edit_clicked,
            on_tyrano_edit_clicked=self._on_tyrano_edit_clicked,
            on_misc_clicked=self._on_misc_clicked,
            on_open_console_clicked=self._on_open_console_clicked,
            on_toggle_description=self._toggle_description,
            update_status=self._update_status,
            update_hook_status=self._update_hook_status
        )
        
        self.port_entry = ui_components.get("port_entry")
        self.port_status_label = ui_components.get("port_status_label")
        self.launch_button = ui_components.get("launch_button")
        self.stop_button = ui_components.get("stop_button")
        self.sf_edit_button = ui_components.get("sf_edit_button")
        self.tyrano_edit_button = ui_components.get("tyrano_edit_button")
        self.misc_button = ui_components.get("misc_button")
        self.game_status_label = ui_components.get("game_status_label")
        self.hook_status_label = ui_components.get("hook_status_label")
        self.status_text = ui_components.get("status_text")
        
        self._bind_hotkey()
        self.open_console_button = ui_components.get("open_console_button")
        self.description_label = ui_components.get("description_label")
        self.what_is_this_label = ui_components.get("what_is_this_label")
        self.description_container = ui_components.get("description_container")
        self._description_expanded = ui_components.get("_description_expanded", False)
    
    def _init_status_checker(self) -> None:
        """创建并启动状态检查器，定时更新游戏与 Hook 状态。"""
        self.status_checker = StatusChecker(
            service=self.service,
            state=self.state,
            root=self.root,
            get_port_entry=lambda: self.port_entry,
            on_game_status_updated=self._on_game_status_updated,
            on_hook_status_updated=self._on_hook_status_updated,
            on_ws_url_updated=lambda port: None
        )
        self.status_checker.start()
    
    def _bind_hotkey(self) -> None:
        """注册全局热键 Alt+S（强制快进），不可用时回退到窗口级热键。"""
        def on_hotkey() -> None:
            if self._is_game_running() and self.state.hook_enabled:
                self.root.after(0, self._on_force_fast_forward_clicked)
        
        if KEYBOARD_AVAILABLE:
            try:
                keyboard.add_hotkey("alt+s", on_hotkey)
                self._hotkey_registered = True
                logger.info("Global hotkey Alt+S registered successfully")
            except Exception as e:
                logger.warning(f"Failed to register global hotkey: {e}, falling back to window-level hotkey")
                self._fallback_bind_hotkey()
        else:
            logger.warning("keyboard library not available, using window-level hotkey")
            self._fallback_bind_hotkey()
    
    def _fallback_bind_hotkey(self) -> None:
        """在根窗口上绑定 Alt+S 作为强制快进热键的回退方案。"""
        def on_hotkey(event) -> None:
            if self._is_game_running() and self.state.hook_enabled:
                self._on_force_fast_forward_clicked()
            return "break"
        
        self.root.bind("<Alt-s>", on_hotkey)
        self.root.bind("<Alt-S>", on_hotkey)
    
    def _toggle_description(self) -> None:
        """切换「这是什么」下方说明文字的显示/隐藏。"""
        if not self.description_label or not self.what_is_this_label:
            return
        
        if not self.description_label.winfo_exists():
            return
        
        self._description_expanded = not self._description_expanded
        
        if self._description_expanded:
            self.description_label.pack(anchor="w", pady=(0, 0))
        else:
            self.description_label.pack_forget()
    
    def _on_open_console_clicked(self) -> None:
        """打开开发者工具控制台窗口的回调。"""
        self._open_console_window()
    
    def _open_console_window(self) -> None:
        """若控制台已存在则激活，否则创建新控制台窗口。"""
        from src.modules.runtime_modify.console import DevToolsConsoleWindow
        
        if self.console_window and self.console_window.winfo_exists():
            if self._raise_window(self.console_window):
                return
            self.console_window = None
        
        self._create_console_window()
    
    def _raise_window(self, window: tk.Toplevel) -> bool:
        """将指定 Toplevel 置顶、获得焦点并取消最小化，失败返回 False。"""
        if not window or not window.winfo_exists():
            return False
        
        try:
            window.lift()
            window.focus_force()
            window.deiconify()
            return True
        except (tk.TclError, AttributeError):
            return False
    
    def _create_console_window(self) -> None:
        """创建 DevTools 控制台窗口并按其可用状态设置。"""
        from src.modules.runtime_modify.console import DevToolsConsoleWindow
        
        self.console_window = DevToolsConsoleWindow(
            self.root,
            self.service,
            self._get_current_ws_url,
            self.translations,
            self.current_language,
            on_close_callback=self._on_console_window_close,
            storage_dir=str(self.storage_dir) if self.storage_dir else None
        )
        
        is_running = self._is_game_running()
        hook_enabled = self.state.hook_enabled
        self.console_window.set_enabled(is_running and hook_enabled)
    
    def _on_console_window_close(self) -> None:
        """控制台关闭时清空其引用。"""
        self.console_window = None
    
    def _get_current_ws_url(self) -> Optional[str]:
        """返回当前可用的 WebSocket URL（游戏运行且已连接时）。"""
        if self.state.cached_ws_url and self.service.is_game_running():
            return self.state.cached_ws_url
        return None
    
    def _is_game_running(self) -> bool:
        """根据状态或进程判断游戏是否在运行。"""
        return (
            self.state.cached_game_running is True or
            (self.state.cached_game_running is None and self.service.game_process is not None)
        )
    
    def _on_port_changed(self) -> None:
        """端口输入变化时清空端口状态标签。"""
        if self.port_status_label:
            self.port_status_label.configure(text="")
    
    def _validate_port_input(self) -> Tuple[Optional[int], Optional[str]]:
        """校验端口输入，返回 (端口, 错误信息)，无误时错误为 None。"""
        if not self.port_entry:
            return None, self.t("runtime_modify_port_required")
        
        port_str = self.port_entry.get().strip()
        if not port_str:
            return None, self.t("runtime_modify_port_required")
        
        try:
            port = int(port_str)
        except ValueError:
            return None, self.t("runtime_modify_error_port_must_be_integer")
        
        is_valid, error = validate_port(port)
        if not is_valid:
            if error and "range" in error.lower():
                return None, self.t(
                    "runtime_modify_error_port_out_of_range",
                    min_port=RuntimeModifyConfig.MIN_PORT,
                    max_port=RuntimeModifyConfig.MAX_PORT
                )
            return None, error or self.t("runtime_modify_port_invalid")
        
        return port, None
    
    def _check_port_status(self) -> None:
        """检查端口是否可用并更新端口状态标签。"""
        if not self.port_entry or not self.port_status_label:
            return
        
        port, error = self._validate_port_input()
        if error:
            self.port_status_label.configure(
                text=error,
                text_color=Colors.TEXT_WARNING_ORANGE
            )
            return
        
        if port is None:
            return
        
        is_available = check_port_available(port)
        status_text = (
            self.t("runtime_modify_port_available")
            if is_available
            else self.t("runtime_modify_port_in_use")
        )
        status_color = (
            Colors.TEXT_SUCCESS
            if is_available
            else Colors.TEXT_WARNING_ORANGE
        )
        
        self.port_status_label.configure(
            text=status_text,
            text_color=status_color
        )
    
    def _on_launch_clicked(self) -> None:
        """校验端口与游戏路径后异步启动游戏。"""
        if self.state.is_launching:
            return
        
        port, error = self._validate_port_input()
        if error:
            showerror_relative(self.root, self.t("error"), error)
            return
        
        if port is None:
            return
        
        if not check_port_available(port):
            showerror_relative(
                self.root,
                self.t("error"),
                self.t("runtime_modify_port_in_use")
            )
            return
        
        game_exe_path = get_game_exe_path(
            str(self.storage_dir) if self.storage_dir else None
        )
        if not game_exe_path:
            showerror_relative(
                self.root,
                self.t("error"),
                self.t("runtime_modify_game_not_found")
            )
            return
        
        self._launch_game_async(game_exe_path, port)
    
    def _on_stop_clicked(self) -> None:
        """在后台检查游戏是否运行后执行停止逻辑。"""
        if self.state.executor:
            future = self.state.executor.submit(self.service.is_game_running)
            future.add_done_callback(
                lambda f: self.root.after(0, lambda: self._on_stop_clicked_after_check(f.result()))
            )
        else:
            self._on_stop_clicked_after_check(False)
    
    def _on_stop_clicked_after_check(self, is_running: bool) -> None:
        """确认游戏在运行后停止进程并更新状态与 Hook。"""
        if not is_running:
            return
        
        try:
            self.service.stop_game()
            self._update_status(self.t("runtime_modify_game_stopped"))
            self.state.cached_game_running = False
            self.state.last_game_status_check = 0.0
            self.state.cached_ws_url = None
            self.status_checker.check_game_status_async()
            self._update_hook_status(False)
        except Exception as e:
            logger.exception("Error stopping game")
            error_msg = self.t(
                "runtime_modify_error_stop_game_failed",
                error=str(e)
            )
            showerror_relative(self.root, self.t("error"), error_msg)
    
    def _launch_game_async(self, exe_path: Path, port: int) -> None:
        """在后台线程中异步启动游戏并测试 CDP 连接，完成后回调主线程。"""
        if self.state.is_launching:
            return
        
        self.state.is_launching = True
        self.launch_button.configure(
            state="disabled",
            text=self.t("runtime_modify_launching")
        )
        self._update_status(self.t("runtime_modify_status_launching"))
        
        def run_in_thread() -> None:
            loop: Optional[asyncio.AbstractEventLoop] = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                success, error, extra = loop.run_until_complete(
                    self.service.launch_and_test(exe_path, port)
                )
                self.root.after(
                    0,
                    lambda: self._on_launch_complete(success, error, extra)
                )
            except Exception as e:
                logger.exception("Error launching game")
                error_msg = self.t(
                    "runtime_modify_error_launch_failed",
                    error=str(e)
                )
                self.root.after(
                    0,
                    lambda: self._on_launch_complete(False, error_msg, None)
                )
            finally:
                if loop:
                    self._cleanup_event_loop(loop)
        
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
    
    def _cleanup_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """取消未完成任务并关闭 asyncio 事件循环。"""
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
    
    def _format_status_details(self, extra: Dict[str, Any]) -> str:
        """将启动结果 extra 格式化为多行状态详情字符串。"""
        details = []
        
        launch_mode = extra.get("launch_mode")
        if isinstance(launch_mode, str):
            if launch_mode == "steam":
                launch_mode_text = self.t("runtime_modify_launch_mode_steam")
            elif launch_mode == "direct":
                launch_mode_text = self.t("runtime_modify_launch_mode_direct")
            else:
                launch_mode_text = launch_mode
            details.append(
                f"{self.t('runtime_modify_status_detail_launch_mode')}: {launch_mode_text}"
            )
        
        if "target_title" in extra:
            details.append(
                f"{self.t('runtime_modify_status_detail_title')}: {extra['target_title']}"
            )
        if "inspector_url" in extra:
            details.append(
                f"{self.t('runtime_modify_status_detail_url')}: {extra['inspector_url']}"
            )
        elif "target_url" in extra:
            details.append(
                f"{self.t('runtime_modify_status_detail_url')}: {extra['target_url']}"
            )
        if "tyrano_type" in extra:
            details.append(
                f"{self.t('runtime_modify_status_detail_tyrano_type')}: {extra['tyrano_type']}"
            )
        
        return "\n".join(details) if details else ""
    
    def _on_launch_complete(
        self,
        success: bool,
        error: Optional[str],
        extra: Optional[Dict[str, Any]]
    ) -> None:
        """启动完成回调：更新按钮与状态，成功则提示并缓存 ws_url，失败则弹窗。"""
        self.state.is_launching = False
        self.launch_button.configure(
            state="normal",
            text=self.t("runtime_modify_launch_button")
        )
        
        self.status_checker.check_game_status_async()
        self._update_hook_status(success)
        
        if success:
            if extra and "ws_url" in extra:
                self.state.cached_ws_url = extra["ws_url"]
            else:
                port, _ = self._validate_port_input()
                if port:
                    self.status_checker.update_cached_ws_url(port)
            status_msg = self.t("runtime_modify_connection_success")
            if extra:
                details = self._format_status_details(extra)
                if details:
                    status_msg += "\n\n" + details
            
            self._update_status(status_msg)
            showinfo_relative(
                self.root,
                self.t("success"),
                self.t("runtime_modify_connection_success")
            )
        else:
            is_pending_cdp = bool(extra and extra.get("pending_cdp"))
            base_msg = (
                self.t("runtime_modify_error_game_not_ready")
                if is_pending_cdp
                else (error or self.t("runtime_modify_connection_failed"))
            )
            error_msg = base_msg
            if extra:
                details = self._format_status_details(extra)
                if details:
                    error_msg += "\n\n" + details
            
            self._update_status(error_msg)
            if not is_pending_cdp:
                showerror_relative(self.root, self.t("error"), error_msg)
    
    def _update_status(self, message: str) -> None:
        """更新状态文本框内容。"""
        if not self.status_text:
            return
        
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", message)
        self.status_text.configure(state="disabled")
    
    def _on_game_status_updated(self, is_running: bool) -> None:
        """游戏状态更新回调，刷新游戏状态 UI。"""
        self._update_game_status_ui(is_running)
    
    def _update_game_status_ui(self, is_running: bool) -> None:
        """根据是否运行更新游戏状态标签与停止按钮可用性。"""
        if not self.game_status_label:
            return
        
        if is_running:
            self.game_status_label.configure(
                text=self.t("runtime_modify_game_running"),
                text_color=Colors.TEXT_SUCCESS
            )
            if self.stop_button:
                self.stop_button.configure(state="normal")
        else:
            self.game_status_label.configure(
                text=self.t("runtime_modify_game_stopped"),
                text_color=Colors.TEXT_SECONDARY
            )
            if self.stop_button:
                self.stop_button.configure(state="disabled")
            if self.state.hook_enabled:
                self._update_hook_status(False)
        
        self._update_sf_edit_button_state()
        self._update_force_fast_forward_button_state()
    
    def _update_hook_status(self, is_enabled: Optional[bool] = None) -> None:
        """更新 Hook 状态并刷新相关按钮与控制台可用性。"""
        if is_enabled is not None:
            self.state.hook_enabled = is_enabled
        
        if not self.hook_status_label or not self.hook_status_label.winfo_exists():
            return
        
        if self.state.hook_enabled:
            self.hook_status_label.configure(
                text=self.t("runtime_modify_hook_enabled"),
                text_color=Colors.TEXT_SUCCESS
            )
        else:
            self.hook_status_label.configure(
                text=self.t("runtime_modify_hook_disabled"),
                text_color=Colors.TEXT_SECONDARY
            )
        
        self._update_sf_edit_button_state()
        self._update_console_state()
        self._update_force_fast_forward_button_state()
    
    def _on_hook_status_updated(self, is_enabled: bool) -> None:
        """Hook 状态更新回调。"""
        self._update_hook_status(is_enabled)
    
    def _update_console_state(self) -> None:
        """根据游戏与 Hook 状态设置控制台窗口是否可用。"""
        if not self.console_window:
            return
        
        if not self.console_window.winfo_exists():
            self.console_window = None
            return
        
        is_running = self._is_game_running()
        hook_enabled = self.state.hook_enabled
        
        if self.console_window and self.console_window.winfo_exists():
            try:
                self.console_window.set_enabled(is_running and hook_enabled)
            except (tk.TclError, AttributeError):
                self.console_window = None
    
    def _update_force_fast_forward_button_state(self) -> None:
        """刷新杂项对话框内强制快进按钮的可用状态。"""
        self._refresh_misc_dialog_state()
    
    def _on_force_fast_forward_clicked(self) -> None:
        """触发强制快进（将当前标签标记为已读）的回调。"""
        self._apply_fast_forward_async()
    
    def _apply_fast_forward_async(self) -> None:
        """在后台线程中通过 WebSocket 注入强制快进脚本。"""
        def run_in_thread() -> None:
            loop: Optional[asyncio.AbstractEventLoop] = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                ws_url = self._get_current_ws_url()
                if ws_url is None:
                    self.root.after(0, lambda: self._on_fast_forward_applied(False, "websocket_not_available"))
                    return
                
                success, error = loop.run_until_complete(
                    self.service.inject_fast_forward_script(ws_url)
                )
                
                if success:
                    self.root.after(0, lambda: self._on_fast_forward_applied(True))
                else:
                    error_msg = error or "Unknown error"
                    self.root.after(0, lambda: self._on_fast_forward_applied(False, error_msg))
                    
            except Exception as unexpected_err:
                logger.exception("Unexpected error applying fast forward")
                self.root.after(0, lambda: self._on_fast_forward_applied(False, str(unexpected_err)))
            finally:
                if loop:
                    self._cleanup_event_loop(loop)
        
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
    
    def _on_fast_forward_applied(self, success: bool, error: Optional[str] = None) -> None:
        """强制快进执行完成回调：成功则记日志，失败则根据错误码弹窗提示。"""
        if success:
            logger.info("Label marked as read successfully")
        else:
            error_msg = error or ""
            logger.error(f"Failed to mark as read: {error_msg}")
            
            if "game_not_using_read_record" in error_msg:
                error_display = self.t("runtime_modify_mark_read_no_record")
            elif "not_in_any_label" in error_msg:
                error_display = self.t("runtime_modify_mark_read_no_label")
            elif "websocket_not_available" in error_msg:
                error_display = self.t("runtime_modify_mark_read_websocket_error")
            else:
                error_display = self.t("runtime_modify_mark_read_failed", error=error_msg)
            
            showerror_relative(
                self.root,
                self.t("error"),
                error_display
            )
    
    def _get_button_state(self, button: Optional[ctk.CTkButton]) -> Optional[str]:
        """获取按钮的 state（normal/disabled），无效时返回 None。"""
        if not button:
            return None
        
        if not button.winfo_exists():
            return None
        
        try:
            return button.cget("state")
        except (tk.TclError, AttributeError):
            return None
    
    def _update_button_state_if_changed(
        self,
        button: Optional[ctk.CTkButton],
        new_state: str
    ) -> bool:
        """仅当按钮当前 state 与目标不同时更新并返回 True。"""
        if not button:
            return False
        
        current_state = self._get_button_state(button)
        if current_state == new_state:
            return False
        
        button.configure(state=new_state)
        return True
    
    def _update_sf_edit_button_state(self) -> None:
        """根据游戏与 Hook 状态更新 sf/tyrano/杂项按钮及控制台可用性。"""
        if not self.sf_edit_button:
            return
        
        is_running = self._is_game_running()
        hook_enabled = self.state.hook_enabled
        new_state = "normal" if (is_running and hook_enabled) else "disabled"
        
        self._update_button_state_if_changed(self.sf_edit_button, new_state)
        
        self._update_tyrano_edit_button_state()
        self._update_misc_button_state()
        self._update_console_state()
    
    def _update_tyrano_edit_button_state(self) -> None:
        """根据游戏与 Hook 状态更新 Tyrano（kag.stat）编辑按钮。"""
        if not self.tyrano_edit_button:
            return
        
        is_running = self._is_game_running()
        hook_enabled = self.state.hook_enabled
        new_state = "normal" if (is_running and hook_enabled) else "disabled"
        
        self._update_button_state_if_changed(self.tyrano_edit_button, new_state)
    
    def _update_misc_button_state(self) -> None:
        """根据游戏与 Hook 状态更新杂项按钮。"""
        if not self.misc_button:
            return
        
        is_running = self._is_game_running()
        hook_enabled = self.state.hook_enabled
        new_state = "normal" if (is_running and hook_enabled) else "disabled"
        
        self._update_button_state_if_changed(self.misc_button, new_state)
    
    def _is_runtime_actions_available(self) -> bool:
        """当前是否可执行运行时操作（游戏运行且 Hook 已启用）。"""
        return self._is_game_running() and self.state.hook_enabled

    def _on_tyrano_edit_clicked(self) -> None:
        """点击 kag.stat 编辑时校验端口与游戏运行后异步打开 kag.stat 查看器。"""
        if not self.port_entry:
            return
        
        port, error = self._validate_port_input()
        if error:
            showerror_relative(self.root, self.t("error"), error)
            return
        
        if port is None:
            return
        
        if not self.service.is_game_running():
            showerror_relative(
                self.root,
                self.t("error"),
                self.t("runtime_modify_sf_game_not_running")
            )
            return
        
        self._open_kag_stat_edit_viewer_async(port)
    
    def _open_kag_stat_edit_viewer_async(self, port: int) -> None:
        """在后台线程获取 ws_url 与 kag.stat 数据后打开编辑查看器。"""
        def run_in_thread() -> None:
            loop: Optional[asyncio.AbstractEventLoop] = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                ws_url, _ = loop.run_until_complete(self.service.fetch_ws_url(port))
                if ws_url is None:
                    self._show_connection_error()
                    return
                
                kag_stat_data, read_error = loop.run_until_complete(
                    self.service.read_tyrano_kag_stat(ws_url)
                )
                
                if read_error:
                    self._show_kag_stat_read_error(read_error)
                    return
                
                if kag_stat_data is None:
                    empty_error = self.t("runtime_modify_kag_stat_read_failed").format(error="Empty data")
                    self._show_kag_stat_read_error(empty_error)
                    return
                
                self.root.after(0, lambda: self._create_kag_stat_viewer(ws_url, kag_stat_data))
                
            except (ValueError, TypeError) as validation_err:
                logger.exception("Validation error opening kag.stat edit viewer")
                self._show_kag_stat_read_error(str(validation_err))
            except Exception as unexpected_err:
                logger.exception("Unexpected error opening kag.stat edit viewer")
                self._show_kag_stat_read_error(str(unexpected_err))
            finally:
                if loop:
                    self._cleanup_event_loop(loop)
        
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
    
    def _show_kag_stat_read_error(self, error: str) -> None:
        """在主线程弹窗显示 kag.stat 读取错误。"""
        if not error:
            error = "Unknown error"
        
        logger.error(f"Failed to read kag.stat: {error}")
        self.root.after(0, lambda: showerror_relative(
            self.root,
            self.t("error"),
            self.t("runtime_modify_kag_stat_read_failed").format(error=error)
        ))
    
    def _create_kag_stat_viewer(self, ws_url: str, kag_stat_data: Dict[str, Any]) -> None:
        """创建并打开 kag.stat 运行时编辑查看器窗口。"""
        from src.modules.save_analysis.sf.save_file_viewer import ViewerConfig, SaveFileViewer
        
        viewer_config = ViewerConfig(
            ws_url=ws_url,
            service=self.service,
            enable_edit_by_default=True,
            save_button_text="runtime_modify_sf_save_inject_button",
            show_enable_edit_checkbox=False,
            show_collapse_checkbox=True,
            show_hint_label=True,
            title_key="runtime_modify_kag_stat_edit_title",
            inject_method="kag_stat",
            collapsed_fields=DEFAULT_KAG_STAT_COLLAPSED_FIELDS
        )
        
        SaveFileViewer.open_or_focus(
            viewer_id="runtime_kag_stat",
            window=self.root,
            storage_dir=str(self.storage_dir) if self.storage_dir else "",
            save_data=kag_stat_data,
            t_func=self.t,
            on_close_callback=None,
            mode="runtime",
            viewer_config=viewer_config
        )
    
    def _refresh_misc_dialog_state(self) -> None:
        """若杂项对话框存在则刷新其按钮可用状态。"""
        if not self.misc_dialog:
            return
        if not self.misc_dialog.winfo_exists():
            self.misc_dialog = None
            return
        try:
            self.misc_dialog.refresh_button_states()
        except (tk.TclError, AttributeError):
            self.misc_dialog = None

    def _on_misc_clicked(self) -> None:
        """打开杂项对话框的回调。"""
        self._open_misc_dialog()

    def _open_misc_dialog(self) -> None:
        """若杂项对话框已存在则激活并刷新，否则创建并显示。"""
        from src.modules.runtime_modify.runtime_misc_dialog import RuntimeMiscDialog

        if self.misc_dialog and self.misc_dialog.winfo_exists():
            if self._raise_window(self.misc_dialog):
                self._refresh_misc_dialog_state()
                return
            self.misc_dialog = None

        self.misc_dialog = RuntimeMiscDialog(
            self.root,
            self.translations,
            self.current_language,
            on_force_fast_forward_clicked=self._on_force_fast_forward_clicked,
            on_cache_clean_clicked=self._open_cache_clean_dialog,
            is_feature_enabled=self._is_runtime_actions_available
        )
        self._refresh_misc_dialog_state()
    
    def _open_cache_clean_dialog(self) -> None:
        """若缓存清理对话框已存在则激活，否则创建。"""
        from src.modules.runtime_modify.cache_clean_dialog import CacheCleanDialog
        
        if self.cache_clean_dialog and self.cache_clean_dialog.winfo_exists():
            if self._raise_window(self.cache_clean_dialog):
                return
            self.cache_clean_dialog = None
        
        self._create_cache_clean_dialog()
    
    def _create_cache_clean_dialog(self) -> None:
        """创建缓存清理对话框并保存引用。"""
        from src.modules.runtime_modify.cache_clean_dialog import CacheCleanDialog
        
        self.cache_clean_dialog = CacheCleanDialog(
            self.root,
            self.service,
            self._get_current_ws_url,
            self.translations,
            self.current_language
        )
    
    def _on_cache_clean_dialog_close(self) -> None:
        """缓存清理对话框关闭时清空引用。"""
        self.cache_clean_dialog = None
    
    def _on_sf_edit_clicked(self) -> None:
        """点击 sf 编辑时校验端口与游戏运行后异步打开 sf 查看器。"""
        if not self.port_entry:
            return
        
        port, error = self._validate_port_input()
        if error:
            showerror_relative(self.root, self.t("error"), error)
            return
        
        if port is None:
            return
        
        if not self.service.is_game_running():
            showerror_relative(
                self.root,
                self.t("error"),
                self.t("runtime_modify_sf_game_not_running")
            )
            return
        
        self._open_sf_edit_viewer_async(port)
    
    def _open_sf_edit_viewer_async(self, port: int) -> None:
        """在后台线程获取 ws_url 与 sf 数据后打开 sf 编辑查看器。"""
        def run_in_thread() -> None:
            loop: Optional[asyncio.AbstractEventLoop] = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                ws_url, _ = loop.run_until_complete(self.service.fetch_ws_url(port))
                if ws_url is None:
                    self._show_connection_error()
                    return
                
                sf_data, read_error = loop.run_until_complete(
                    self.service.read_tyrano_variable_sf(ws_url)
                )
                
                if read_error:
                    self._show_read_error(read_error)
                    return
                
                if sf_data is None:
                    empty_error = self.t("runtime_modify_sf_error_empty_data")
                    self._show_read_error(empty_error)
                    return
                
                self.root.after(0, lambda: self._create_sf_viewer(ws_url, sf_data))
                
            except (ValueError, TypeError) as validation_err:
                logger.exception("Validation error opening sf edit viewer")
                self._show_read_error(str(validation_err))
            except Exception as unexpected_err:
                logger.exception("Unexpected error opening sf edit viewer")
                self._show_read_error(str(unexpected_err))
            finally:
                if loop:
                    self._cleanup_event_loop(loop)
        
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
    
    def _show_connection_error(self) -> None:
        """在主线程弹窗显示连接失败/游戏未运行错误。"""
        self.root.after(0, lambda: showerror_relative(
            self.root,
            self.t("error"),
            self.t("runtime_modify_sf_game_not_running")
        ))
    
    def _show_read_error(self, error: str) -> None:
        """在主线程弹窗显示 sf 读取失败错误。"""
        self.root.after(0, lambda: showerror_relative(
            self.root,
            self.t("error"),
            self.t("runtime_modify_sf_read_failed").format(error=error)
        ))
    
    def _create_sf_viewer(self, ws_url: str, sf_data: Dict[str, Any]) -> None:
        """创建并打开 sf 运行时编辑查看器窗口。"""
        from src.modules.save_analysis.sf.save_file_viewer import ViewerConfig, SaveFileViewer, DEFAULT_SF_COLLAPSED_FIELDS
        
        viewer_config = ViewerConfig(
            ws_url=ws_url,
            service=self.service,
            enable_edit_by_default=True,
            save_button_text="runtime_modify_sf_save_inject_button",
            show_enable_edit_checkbox=False,
            collapsed_fields=DEFAULT_SF_COLLAPSED_FIELDS
        )
        
        SaveFileViewer.open_or_focus(
            viewer_id="runtime_sf",
            window=self.root,
            storage_dir=str(self.storage_dir) if self.storage_dir else "",
            save_data=sf_data,
            t_func=self.t,
            on_close_callback=None,
            mode="runtime",
            viewer_config=viewer_config
        )
    
    def cleanup(self) -> None:
        """关闭时停止状态检查、注销热键、停止游戏与线程池，并销毁杂项对话框。"""
        self.state.is_closing = True

        if self.misc_dialog and self.misc_dialog.winfo_exists():
            try:
                self.misc_dialog.destroy()
            except (tk.TclError, AttributeError):
                pass
            finally:
                self.misc_dialog = None
        
        if hasattr(self, 'status_checker'):
            self.status_checker.stop()
        
        if self._hotkey_registered and KEYBOARD_AVAILABLE:
            try:
                keyboard.unhook_all_hotkeys()
                self._hotkey_registered = False
                logger.info("Global hotkey unregistered")
            except Exception as e:
                logger.debug(f"Error unregistering hotkey: {e}")
        
        if self.service.game_process is not None:
            try:
                self.service.stop_game()
                logger.info("Game process stopped during cleanup")
            except Exception as e:
                logger.debug(f"Error stopping game during cleanup: {e}")
        
        if self.state.executor:
            try:
                self.state.executor.shutdown(wait=False, cancel_futures=True)
            except Exception as e:
                logger.debug(f"Error shutting down executor: {e}")
            finally:
                self.state.executor = None
    
    def set_storage_dir(self, storage_dir: Optional[str]) -> None:
        """设置存储目录并更新服务的游戏 exe 路径。"""
        self.storage_dir = Path(storage_dir) if storage_dir else None
        if self.storage_dir:
            game_exe_path = get_game_exe_path(str(self.storage_dir))
            if game_exe_path:
                self.service.game_exe_path = game_exe_path
    
    def update_language(self, language: str) -> None:
        """切换语言时重建 UI 并更新已打开的子窗口（控制台、杂项、缓存清理）语言。"""
        if not isinstance(language, str) or not language:
            logger.warning(f"Invalid language code: {language}")
            return
        
        if language not in self.translations:
            logger.warning(f"Unsupported language: {language}")
            return
        
        self.current_language = language
        
        try:
            if hasattr(self, 'status_checker'):
                self.status_checker.stop()
            
            self._clear_ui_references()
            
            for widget in self.parent.winfo_children():
                widget.destroy()
            self._init_ui()
            self._init_status_checker()
            
            if self.console_window and self.console_window.winfo_exists():
                try:
                    self.console_window.update_language(language)
                except (tk.TclError, AttributeError):
                    self.console_window = None

            if self.misc_dialog and self.misc_dialog.winfo_exists():
                try:
                    self.misc_dialog.update_language(language)
                    self.misc_dialog.refresh_button_states()
                except (tk.TclError, AttributeError):
                    self.misc_dialog = None
            
            if self.cache_clean_dialog and self.cache_clean_dialog.winfo_exists():
                try:
                    self.cache_clean_dialog.update_language(language)
                except (tk.TclError, AttributeError):
                    self.cache_clean_dialog = None
        except Exception as e:
            logger.exception("Error updating language")
            raise


