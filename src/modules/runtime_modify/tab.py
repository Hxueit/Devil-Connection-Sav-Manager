"""运行时修改标签页UI

负责渲染运行时修改标签页的UI界面，处理用户交互事件。
业务逻辑已委托给相应的服务模块。
"""
import asyncio
import logging
import threading
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

DEFAULT_KAG_STAT_COLLAPSED_FIELDS = [
    "map_label",
    "charas",
    "map_keyframe",
    "stack",
    "popopo",
    "map_macro",
    "fuki"
]


class RuntimeModifyTab:
    """运行时修改标签页"""
    
    def __init__(
        self,
        parent: ctk.CTkFrame,
        storage_dir: Optional[str],
        translations: Dict[str, Dict[str, str]],
        current_language: str,
        root: ctk.CTk
    ) -> None:
        """初始化运行时修改标签页
        
        Args:
            parent: 父容器
            storage_dir: 存储目录路径
            translations: 翻译字典
            current_language: 当前语言代码
            root: 根窗口，用于异步操作后的UI更新
        """
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
        self.cache_clean_button: Optional[ctk.CTkButton] = None
        self.game_status_label: Optional[ctk.CTkLabel] = None
        self.hook_status_label: Optional[ctk.CTkLabel] = None
        self.force_fast_forward_button: Optional[ctk.CTkButton] = None
        self.status_text: Optional[ctk.CTkTextbox] = None
        self.console_window: Optional[Any] = None
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
        """获取翻译文本
        
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
    
    def _clear_ui_references(self) -> None:
        """清除所有UI组件引用
        
        在销毁UI组件之前调用，防止回调函数尝试操作已销毁的widget
        """
        self.port_entry = None
        self.port_status_label = None
        self.launch_button = None
        self.stop_button = None
        self.sf_edit_button = None
        self.tyrano_edit_button = None
        self.cache_clean_button = None
        self.game_status_label = None
        self.hook_status_label = None
        self.force_fast_forward_button = None
        self.force_fast_forward_hint = None
        self.status_text = None
        self.open_console_button = None
        self.description_label = None
        self.what_is_this_label = None
        self.description_container = None
        self._description_expanded = False
    
    def _init_ui(self) -> None:
        """初始化UI组件"""
        ui_builder = RuntimeModifyUIBuilder(self.parent, self.t)
        ui_components = ui_builder.build(
            on_port_changed=self._on_port_changed,
            on_check_port=self._check_port_status,
            on_launch_clicked=self._on_launch_clicked,
            on_stop_clicked=self._on_stop_clicked,
            on_sf_edit_clicked=self._on_sf_edit_clicked,
            on_tyrano_edit_clicked=self._on_tyrano_edit_clicked,
            on_cache_clean_clicked=self._on_cache_clean_clicked,
            on_open_console_clicked=self._on_open_console_clicked,
            on_toggle_description=self._toggle_description,
            update_status=self._update_status,
            update_hook_status=self._update_hook_status,
            on_force_fast_forward_clicked=self._on_force_fast_forward_clicked
        )
        
        self.port_entry = ui_components.get("port_entry")
        self.port_status_label = ui_components.get("port_status_label")
        self.launch_button = ui_components.get("launch_button")
        self.stop_button = ui_components.get("stop_button")
        self.sf_edit_button = ui_components.get("sf_edit_button")
        self.tyrano_edit_button = ui_components.get("tyrano_edit_button")
        self.cache_clean_button = ui_components.get("cache_clean_button")
        self.game_status_label = ui_components.get("game_status_label")
        self.hook_status_label = ui_components.get("hook_status_label")
        self.force_fast_forward_button = ui_components.get("force_fast_forward_button")
        self.force_fast_forward_hint = ui_components.get("force_fast_forward_hint")
        self.status_text = ui_components.get("status_text")
        
        self._bind_hotkey()
        self.open_console_button = ui_components.get("open_console_button")
        self.description_label = ui_components.get("description_label")
        self.what_is_this_label = ui_components.get("what_is_this_label")
        self.description_container = ui_components.get("description_container")
        self._description_expanded = ui_components.get("_description_expanded", False)
    
    def _init_status_checker(self) -> None:
        """初始化状态检查器"""
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
        """绑定Alt+S全局快捷键"""
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
        """回退到窗口级快捷键绑定"""
        def on_hotkey(event) -> None:
            if self._is_game_running() and self.state.hook_enabled:
                self._on_force_fast_forward_clicked()
            return "break"
        
        self.root.bind("<Alt-s>", on_hotkey)
        self.root.bind("<Alt-S>", on_hotkey)
    
    def _toggle_description(self) -> None:
        """切换描述文字的显示/隐藏状态"""
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
        """打开控制台按钮点击回调"""
        self._open_console_window()
    
    def _open_console_window(self) -> None:
        """打开控制台窗口（单例模式）"""
        from src.modules.runtime_modify.console import DevToolsConsoleWindow
        
        if self.console_window and self.console_window.winfo_exists():
            if self._raise_window(self.console_window):
                return
            self.console_window = None
        
        self._create_console_window()
    
    def _raise_window(self, window: tk.Toplevel) -> bool:
        """提升窗口到前台
        
        Args:
            window: 要提升的窗口
            
        Returns:
            是否成功提升
        """
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
        """创建控制台窗口"""
        from src.modules.runtime_modify.console import DevToolsConsoleWindow
        
        self.console_window = DevToolsConsoleWindow(
            self.root,
            self.service,
            self._get_current_ws_url,
            self.translations,
            self.current_language,
            on_close_callback=self._on_console_window_close
        )
        
        is_running = self._is_game_running()
        hook_enabled = self.state.hook_enabled
        self.console_window.set_enabled(is_running and hook_enabled)
    
    def _on_console_window_close(self) -> None:
        """控制台窗口关闭回调"""
        self.console_window = None
    
    def _get_current_ws_url(self) -> Optional[str]:
        """获取当前WebSocket URL（同步方法，返回缓存值）
        
        Returns:
            WebSocket URL或None
        """
        if self.state.cached_ws_url and self.service.is_game_running():
            return self.state.cached_ws_url
        return None
    
    def _is_game_running(self) -> bool:
        """检查游戏是否在运行
        
        Returns:
            游戏是否在运行
        """
        return (
            self.state.cached_game_running is True or
            (self.state.cached_game_running is None and self.service.game_process is not None)
        )
    
    def _on_port_changed(self) -> None:
        """端口输入变化回调"""
        if self.port_status_label:
            self.port_status_label.configure(text="")
    
    def _validate_port_input(self) -> Tuple[Optional[int], Optional[str]]:
        """验证端口输入
        
        Returns:
            (端口号, 错误信息)，验证失败时返回(None, 错误信息)
        """
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
        """检查端口状态并更新UI"""
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
        """启动按钮点击回调"""
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
        """关闭游戏按钮回调"""
        if self.state.executor:
            future = self.state.executor.submit(self.service.is_game_running)
            future.add_done_callback(
                lambda f: self.root.after(0, lambda: self._on_stop_clicked_after_check(f.result()))
            )
        else:
            self._on_stop_clicked_after_check(False)
    
    def _on_stop_clicked_after_check(self, is_running: bool) -> None:
        """关闭游戏按钮回调（检查后）"""
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
        """异步启动游戏并测试连接"""
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
        """清理asyncio事件循环"""
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
        """格式化状态详细信息
        
        Args:
            extra: 额外信息字典
            
        Returns:
            格式化后的详细信息字符串
        """
        details = []
        
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
        """启动完成回调"""
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
            error_msg = error or self.t("runtime_modify_connection_failed")
            self._update_status(error_msg)
            showerror_relative(self.root, self.t("error"), error_msg)
    
    def _update_status(self, message: str) -> None:
        """更新状态显示"""
        if not self.status_text:
            return
        
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", message)
        self.status_text.configure(state="disabled")
    
    def _on_game_status_updated(self, is_running: bool) -> None:
        """游戏状态更新回调（由StatusChecker调用）"""
        self._update_game_status_ui(is_running)
    
    def _update_game_status_ui(self, is_running: bool) -> None:
        """更新游戏状态UI（在主线程执行）"""
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
        """更新Hook状态显示"""
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
        """Hook状态更新回调（由StatusChecker调用）"""
        self._update_hook_status(is_enabled)
    
    def _update_console_state(self) -> None:
        """更新控制台启用/禁用状态"""
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
        """更新强制快进按钮的启用状态"""
        if not self.force_fast_forward_button or not self.force_fast_forward_button.winfo_exists():
            return
        
        is_running = self._is_game_running()
        hook_enabled = self.state.hook_enabled
        new_state = "normal" if (is_running and hook_enabled) else "disabled"
        
        if self.force_fast_forward_button.cget("state") != new_state:
            self.force_fast_forward_button.configure(state=new_state)
    
    def _on_force_fast_forward_clicked(self) -> None:
        """强制快进按钮点击回调"""
        self._apply_fast_forward_async()
    
    def _apply_fast_forward_async(self) -> None:
        """异步标记当前label为已读"""
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
                    error_msg = error or "未知错误"
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
        """标记已读完成回调
        
        Args:
            success: 是否成功
            error: 错误信息
        """
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
        """获取按钮当前状态
        
        Args:
            button: 按钮组件
            
        Returns:
            按钮状态字符串或None
        """
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
        """更新按钮状态（仅在状态变化时）
        
        Args:
            button: 按钮组件
            new_state: 新状态
            
        Returns:
            是否进行了更新
        """
        if not button:
            return False
        
        current_state = self._get_button_state(button)
        if current_state == new_state:
            return False
        
        button.configure(state=new_state)
        return True
    
    def _update_sf_edit_button_state(self) -> None:
        """更新sf存档修改按钮的启用状态"""
        if not self.sf_edit_button:
            return
        
        is_running = self._is_game_running()
        hook_enabled = self.state.hook_enabled
        new_state = "normal" if (is_running and hook_enabled) else "disabled"
        
        updated = self._update_button_state_if_changed(self.sf_edit_button, new_state)
        
        self._update_tyrano_edit_button_state()
        self._update_cache_clean_button_state()
        self._update_console_state()
    
    def _update_tyrano_edit_button_state(self) -> None:
        """更新Tyrano内存变量修改按钮的启用状态"""
        if not self.tyrano_edit_button:
            return
        
        is_running = self._is_game_running()
        hook_enabled = self.state.hook_enabled
        new_state = "normal" if (is_running and hook_enabled) else "disabled"
        
        self._update_button_state_if_changed(self.tyrano_edit_button, new_state)
    
    def _update_cache_clean_button_state(self) -> None:
        """更新清理缓存按钮的启用状态"""
        if not self.cache_clean_button:
            return
        
        is_running = self._is_game_running()
        hook_enabled = self.state.hook_enabled
        new_state = "normal" if (is_running and hook_enabled) else "disabled"
        
        self._update_button_state_if_changed(self.cache_clean_button, new_state)
    
    def _on_tyrano_edit_clicked(self) -> None:
        """Tyrano kag.stat状态修改按钮点击回调"""
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
        """异步打开kag.stat编辑窗口"""
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
        """显示kag.stat读取错误
        
        Args:
            error: 错误消息
        """
        if not error:
            error = "Unknown error"
        
        logger.error(f"Failed to read kag.stat: {error}")
        self.root.after(0, lambda: showerror_relative(
            self.root,
            self.t("error"),
            self.t("runtime_modify_kag_stat_read_failed").format(error=error)
        ))
    
    def _create_kag_stat_viewer(self, ws_url: str, kag_stat_data: Dict[str, Any]) -> None:
        """创建kag.stat查看器窗口"""
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
        
        SaveFileViewer(
            self.root,
            str(self.storage_dir) if self.storage_dir else "",
            kag_stat_data,
            self.t,
            None,
            mode="runtime",
            viewer_config=viewer_config
        )
    
    def _on_cache_clean_clicked(self) -> None:
        """清理缓存按钮点击回调"""
        self._open_cache_clean_dialog()
    
    def _open_cache_clean_dialog(self) -> None:
        """打开缓存清理弹窗（单例模式）"""
        from src.modules.runtime_modify.cache_clean_dialog import CacheCleanDialog
        
        if self.cache_clean_dialog and self.cache_clean_dialog.winfo_exists():
            if self._raise_window(self.cache_clean_dialog):
                return
            self.cache_clean_dialog = None
        
        self._create_cache_clean_dialog()
    
    def _create_cache_clean_dialog(self) -> None:
        """创建缓存清理弹窗"""
        from src.modules.runtime_modify.cache_clean_dialog import CacheCleanDialog
        
        self.cache_clean_dialog = CacheCleanDialog(
            self.root,
            self.service,
            self._get_current_ws_url,
            self.translations,
            self.current_language
        )
    
    def _on_cache_clean_dialog_close(self) -> None:
        """缓存清理弹窗关闭回调"""
        self.cache_clean_dialog = None
    
    def _on_sf_edit_clicked(self) -> None:
        """sf存档修改按钮点击回调"""
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
        """异步打开sf存档编辑窗口"""
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
        """显示连接错误"""
        self.root.after(0, lambda: showerror_relative(
            self.root,
            self.t("error"),
            self.t("runtime_modify_sf_game_not_running")
        ))
    
    def _show_read_error(self, error: str) -> None:
        """显示读取错误
        
        Args:
            error: 错误消息
        """
        self.root.after(0, lambda: showerror_relative(
            self.root,
            self.t("error"),
            self.t("runtime_modify_sf_read_failed").format(error=error)
        ))
    
    def _create_sf_viewer(self, ws_url: str, sf_data: Dict[str, Any]) -> None:
        """创建sf存档查看器窗口"""
        from src.modules.save_analysis.sf.save_file_viewer import ViewerConfig, SaveFileViewer, DEFAULT_SF_COLLAPSED_FIELDS
        
        viewer_config = ViewerConfig(
            ws_url=ws_url,
            service=self.service,
            enable_edit_by_default=True,
            save_button_text="runtime_modify_sf_save_inject_button",
            show_enable_edit_checkbox=False,
            collapsed_fields=DEFAULT_SF_COLLAPSED_FIELDS
        )
        
        SaveFileViewer(
            self.root,
            str(self.storage_dir) if self.storage_dir else "",
            sf_data,
            self.t,
            None,
            mode="runtime",
            viewer_config=viewer_config
        )
    
    def cleanup(self) -> None:
        """清理资源"""
        self.state.is_closing = True
        
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
        """设置存储目录
        
        Args:
            storage_dir: 存储目录路径
        """
        self.storage_dir = Path(storage_dir) if storage_dir else None
        if self.storage_dir:
            game_exe_path = get_game_exe_path(str(self.storage_dir))
            if game_exe_path:
                self.service.game_exe_path = game_exe_path
    
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
            
            if self.cache_clean_dialog and self.cache_clean_dialog.winfo_exists():
                try:
                    self.cache_clean_dialog.update_language(language)
                except (tk.TclError, AttributeError):
                    self.cache_clean_dialog = None
        except Exception as e:
            logger.exception("Error updating language")
            raise
