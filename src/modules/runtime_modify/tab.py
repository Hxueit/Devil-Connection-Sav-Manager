"""运行时修改标签页：启动/停止游戏、显示连接状态，以及控制台、变量编辑、杂项功能的入口

状态轮询：每隔几秒在后台线程检查一次调试端口（service.poll_status），
结果回到主线程后更新界面；按钮、控制台等都只读取缓存的状态，不会阻塞界面。
"""
import logging
import threading
from typing import Any, Dict, Optional, Tuple

import customtkinter as ctk
import tkinter as tk
from tkinter import font as tkfont

try:
    import keyboard
except ImportError:
    keyboard = None

from src.modules.runtime_modify.cache_clean_dialog import CacheCleanDialog
from src.modules.runtime_modify.console import DevToolsConsoleWindow
from src.modules.runtime_modify.dialogs import RuntimeMiscDialog, create_standard_button
from src.modules.runtime_modify.service import (
    DEFAULT_PORT,
    MAX_PORT,
    MIN_PORT,
    RuntimeModifyService,
    check_port_available,
    fetch_ws_url,
    get_game_exe_path,
    read_json_variable,
)
from src.utils.background import run_in_background
from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import restore_and_activate_window, showerror_relative, showinfo_relative

logger = logging.getLogger(__name__)

STATUS_POLL_MS = 2000           # 游戏运行时的状态检查间隔
STATUS_POLL_IDLE_MS = 5000      # 游戏未运行时检查得慢一些
HOTKEY_CHECK_MS = 100

# kag.stat 编辑器里默认折叠的大字段
DEFAULT_KAG_STAT_COLLAPSED_FIELDS = [
    "map_label", "charas", "map_keyframe", "stack", "popopo", "map_macro", "fuki", "three",
]


def _window_alive(window: Optional[tk.Misc]) -> bool:
    try:
        return window is not None and bool(window.winfo_exists())
    except tk.TclError:
        return False


class RuntimeModifyTab:
    """运行时修改标签页"""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        storage_dir: Optional[str],
        translations: Dict[str, Dict[str, str]],
        current_language: str,
        root: ctk.CTk,
    ) -> None:
        self.parent = parent
        self.storage_dir = storage_dir
        self.translations = translations
        self.current_language = current_language
        self.root = root
        self.service = RuntimeModifyService(get_game_exe_path(storage_dir))

        # 最近一次检查到的状态；「Hook 已启用」即能连上游戏页面（_ws_url 不为 None）
        self._game_running = False
        self._ws_url: Optional[str] = None
        self._is_launching = False
        self._closed = False

        self._poll_job: Optional[str] = None
        self._polling = False
        # 启动/停止完成时会直接设置状态并加一，用来丢弃在那之前发出、结果已过时的轮询
        self._status_generation = 0

        self.console_window: Optional[DevToolsConsoleWindow] = None
        self.misc_dialog: Optional[RuntimeMiscDialog] = None
        self.cache_clean_dialog: Optional[CacheCleanDialog] = None

        self._hotkey_handle: Any = None
        self._hotkey_pressed = threading.Event()
        self._hotkey_job: Optional[str] = None

        self._build_ui()
        self._register_hotkey()
        self._poll_status()

    def t(self, key: str, **kwargs: Any) -> str:
        text = self.translations.get(self.current_language, {}).get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError):
                return text
        return text

    @property
    def _hook_enabled(self) -> bool:
        return self._ws_url is not None

    # ------------------------------------------------------------ 界面

    def _build_ui(self) -> None:
        # 所有控件都放在这个容器里，切换语言时只需销毁它再重建
        self.container = ctk.CTkFrame(self.parent, fg_color=Colors.WHITE)
        self.container.pack(fill="both", expand=True, padx=0, pady=20)
        content = ctk.CTkFrame(self.container, fg_color=Colors.WHITE, border_width=0)
        content.pack(fill="both", expand=True)

        # 「这是什么」：点击展开/收起说明
        description_frame = ctk.CTkFrame(content, fg_color=Colors.WHITE, border_width=0)
        description_frame.pack(anchor="w", fill="x", pady=(0, 15))
        family, size = get_cjk_font(10)[:2]
        # 要保留 Font 对象的引用，否则它被回收时字体会被删除
        self._underline_font = tkfont.Font(family=family, size=size, underline=True)
        what_is_this = tk.Label(
            description_frame,
            text=self.t("runtime_modify_what_is_this"),
            font=self._underline_font,
            fg=Colors.TEXT_PRIMARY,
            bg=Colors.WHITE,
            cursor="hand2",
            anchor="w",
        )
        what_is_this.pack(anchor="w", pady=(0, 5))
        what_is_this.bind("<Button-1>", self._toggle_description)
        self.description_label = ctk.CTkLabel(
            description_frame,
            text=self.t("runtime_modify_description"),
            font=get_cjk_font(11),
            text_color=Colors.TEXT_PRIMARY,
            justify="left",
            wraplength=700,
            anchor="w",
        )
        self._description_expanded = False

        # 端口
        port_row = ctk.CTkFrame(content, fg_color=Colors.WHITE)
        port_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            port_row, text=self.t("runtime_modify_port_label"), font=get_cjk_font(11), text_color=Colors.TEXT_PRIMARY,
        ).pack(side="left")
        self.port_entry = ctk.CTkEntry(
            port_row,
            placeholder_text=str(DEFAULT_PORT),
            font=get_cjk_font(11),
            width=100,
            corner_radius=8,
            fg_color=Colors.WHITE,
            text_color=Colors.TEXT_PRIMARY,
            border_color=Colors.GRAY,
        )
        self.port_entry.pack(side="left", padx=(5, 10))
        self.port_entry.insert(0, str(DEFAULT_PORT))
        self.port_entry.bind("<KeyRelease>", lambda e: self.port_status_label.configure(text=""))
        create_standard_button(
            port_row, self.t("runtime_modify_check_port"), self._on_check_port_clicked,
            font=get_cjk_font(9), width=80, height=28,
        ).pack(side="left", padx=(0, 10))
        self.port_status_label = ctk.CTkLabel(
            port_row, text="", font=get_cjk_font(10), text_color=Colors.TEXT_SECONDARY)
        self.port_status_label.pack(side="left")
        ctk.CTkLabel(
            content, text=self.t("runtime_modify_port_hint"), font=get_cjk_font(9), text_color=Colors.TEXT_SECONDARY,
        ).pack(anchor="w", pady=(0, 15))

        # 启动/停止与状态
        action_row = ctk.CTkFrame(content, fg_color=Colors.WHITE)
        action_row.pack(fill="x", pady=(0, 10))
        self.launch_button = create_standard_button(
            action_row, self.t("runtime_modify_launch_button"), self._on_launch_clicked)
        self.launch_button.pack(side="left", padx=(0, 10))
        self.stop_button = create_standard_button(
            action_row, self.t("runtime_modify_stop_server"), self._on_stop_clicked, state="disabled")
        self.stop_button.pack(side="left", padx=(0, 10))
        self.game_status_label = ctk.CTkLabel(action_row, text="", font=get_cjk_font(10))
        self.game_status_label.pack(side="left", padx=(10, 0))
        self.hook_status_label = ctk.CTkLabel(action_row, text="", font=get_cjk_font(10))
        self.hook_status_label.pack(side="left", padx=(10, 0))

        # 状态详情
        ctk.CTkLabel(
            content, text=self.t("runtime_modify_status_title"), font=get_cjk_font(11, "bold"),
            text_color=Colors.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(10, 5))
        self.status_text = ctk.CTkTextbox(
            content,
            height=120,
            font=get_cjk_font(10),
            fg_color=Colors.LIGHT_GRAY,
            text_color=Colors.TEXT_PRIMARY,
            border_color=Colors.GRAY,
            border_width=1,
            corner_radius=8,
            wrap="word",
        )
        self.status_text.pack(fill="both", expand=True)
        self._set_status_text(self.t("runtime_modify_status_ready"))

        # 功能入口：控制台 | sf 编辑  kag.stat 编辑 | 杂项
        tools_row = ctk.CTkFrame(content, fg_color=Colors.WHITE)
        tools_row.pack(anchor="w", pady=(10, 0), fill="x")
        create_standard_button(
            tools_row, self.t("runtime_modify_open_console_button"), self._open_console,
        ).pack(side="left")
        self._separator(tools_row)
        self.sf_edit_button = create_standard_button(
            tools_row, self.t("runtime_modify_sf_edit_button"), lambda: self._open_variable_editor("sf"),
            state="disabled")
        self.sf_edit_button.pack(side="left")
        self.tyrano_edit_button = create_standard_button(
            tools_row, self.t("runtime_modify_tyrano_edit_button"), lambda: self._open_variable_editor("kag_stat"),
            state="disabled")
        self.tyrano_edit_button.pack(side="left", padx=(10, 0))
        self._separator(tools_row)
        self.misc_button = create_standard_button(
            tools_row, self.t("runtime_modify_misc_button"), self._open_misc_dialog, state="disabled")
        self.misc_button.pack(side="left")

        self._update_status_widgets()

    @staticmethod
    def _separator(parent: tk.Misc) -> None:
        """与按钮等高的竖线"""
        line = ctk.CTkFrame(parent, width=1, height=28, fg_color=Colors.GRAY)
        line.pack(side="left", padx=(10, 10))
        line.pack_propagate(False)

    def _toggle_description(self, _event: Optional[tk.Event] = None) -> None:
        self._description_expanded = not self._description_expanded
        if self._description_expanded:
            self.description_label.pack(anchor="w")
        else:
            self.description_label.pack_forget()

    def _set_status_text(self, message: str) -> None:
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", message)
        self.status_text.configure(state="disabled")

    # ------------------------------------------------------------ 状态

    def _set_game_status(self, running: bool, ws_url: Optional[str]) -> None:
        ws_url = ws_url if running else None
        changed = (running, ws_url is not None) != (self._game_running, self._hook_enabled)
        self._game_running = running
        self._ws_url = ws_url
        if changed:
            self._update_status_widgets()

    def _update_status_widgets(self) -> None:
        """按当前状态刷新标签、按钮以及已打开的弹窗"""
        if self._game_running:
            self.game_status_label.configure(text=self.t("runtime_modify_game_running"), text_color=Colors.TEXT_SUCCESS)
        else:
            self.game_status_label.configure(
                text=self.t("runtime_modify_game_stopped"), text_color=Colors.TEXT_SECONDARY)
        if self._hook_enabled:
            self.hook_status_label.configure(text=self.t("runtime_modify_hook_enabled"), text_color=Colors.TEXT_SUCCESS)
        else:
            self.hook_status_label.configure(
                text=self.t("runtime_modify_hook_disabled"), text_color=Colors.TEXT_SECONDARY)

        self.stop_button.configure(state="normal" if self._game_running else "disabled")
        runtime_state = "normal" if self._hook_enabled else "disabled"
        for button in (self.sf_edit_button, self.tyrano_edit_button, self.misc_button):
            button.configure(state=runtime_state)
        if _window_alive(self.console_window):
            self.console_window.set_enabled(self._hook_enabled)
        if _window_alive(self.misc_dialog):
            self.misc_dialog.set_enabled(self._hook_enabled)

    def _poll_status(self) -> None:
        self._poll_job = None
        if self._closed or self._polling:
            return
        self._polling = True
        port = self._parse_port()[0]
        generation = self._status_generation
        run_in_background(
            self.parent,
            lambda: self.service.poll_status(port),
            lambda result, error: self._on_status_polled(result, error, generation),
        )

    def _on_status_polled(self, result: Optional[Tuple[bool, Optional[str]]], error: Optional[BaseException],
                          generation: int) -> None:
        self._polling = False
        if self._closed:
            return
        if error is None and generation == self._status_generation:
            self._set_game_status(*result)
        delay = STATUS_POLL_MS if self._game_running else STATUS_POLL_IDLE_MS
        self._poll_job = self.parent.after(delay, self._poll_status)

    def _poll_soon(self) -> None:
        """尽快再检查一次状态（若正在检查，它结束后会照常安排下一次）"""
        if self._polling or self._closed:
            return
        if self._poll_job is not None:
            self.parent.after_cancel(self._poll_job)
        self._poll_job = self.parent.after(0, self._poll_status)

    # ------------------------------------------------------------ 端口

    def _parse_port(self) -> Tuple[Optional[int], Optional[str]]:
        """读取端口输入，返回 (端口, 错误提示)"""
        try:
            text = self.port_entry.get().strip()
        except tk.TclError:
            return None, self.t("runtime_modify_port_required")
        if not text:
            return None, self.t("runtime_modify_port_required")
        try:
            port = int(text)
        except ValueError:
            return None, self.t("runtime_modify_error_port_must_be_integer")
        if not MIN_PORT <= port <= MAX_PORT:
            return None, self.t("runtime_modify_error_port_out_of_range", min_port=MIN_PORT, max_port=MAX_PORT)
        return port, None

    def _port_or_show_error(self) -> Optional[int]:
        port, error = self._parse_port()
        if error:
            showerror_relative(self.root, self.t("error"), error)
        return port

    def _on_check_port_clicked(self) -> None:
        port, error = self._parse_port()
        if error:
            self.port_status_label.configure(text=error, text_color=Colors.TEXT_WARNING_ORANGE)
        elif check_port_available(port):
            self.port_status_label.configure(
                text=self.t("runtime_modify_port_available"), text_color=Colors.TEXT_SUCCESS)
        else:
            self.port_status_label.configure(
                text=self.t("runtime_modify_port_in_use"), text_color=Colors.TEXT_WARNING_ORANGE)

    # ------------------------------------------------------------ 启动 / 停止

    def _on_launch_clicked(self) -> None:
        if self._is_launching:
            return
        port = self._port_or_show_error()
        if port is None:
            return
        if not check_port_available(port):
            showerror_relative(self.root, self.t("error"), self.t("runtime_modify_port_in_use"))
            return
        exe_path = get_game_exe_path(self.storage_dir)
        if not exe_path:
            showerror_relative(self.root, self.t("error"), self.t("runtime_modify_game_not_found"))
            return

        self._is_launching = True
        self.launch_button.configure(state="disabled", text=self.t("runtime_modify_launching"))
        self._set_status_text(self.t("runtime_modify_status_launching"))
        run_in_background(self.parent, lambda: self.service.launch_and_test(exe_path, port), self._on_launch_done)

    def _on_launch_done(self, result: Optional[Tuple[bool, Optional[str], Dict[str, Any]]],
                        exc: Optional[BaseException]) -> None:
        if self._closed:
            return
        self._is_launching = False
        self.launch_button.configure(state="normal", text=self.t("runtime_modify_launch_button"))
        if exc is not None:
            success, error, info = False, self.t("runtime_modify_error_launch_failed", error=str(exc)), {}
        else:
            success, error, info = result

        self._status_generation += 1
        self._set_game_status(success or self._game_running, info.get("ws_url") if success else None)
        self._poll_soon()

        details = self._format_launch_details(info)
        if success:
            self._set_status_text(self.t("runtime_modify_connection_success") + details)
            showinfo_relative(self.root, self.t("success"), self.t("runtime_modify_connection_success"))
        elif info.get("pending_cdp"):
            # 游戏还在启动（Steam 较慢），不弹窗，之后的状态轮询会发现它
            self._set_status_text(self.t("runtime_modify_error_game_not_ready") + details)
        else:
            message = (error or self.t("runtime_modify_connection_failed")) + details
            self._set_status_text(message)
            showerror_relative(self.root, self.t("error"), message)

    def _format_launch_details(self, info: Dict[str, Any]) -> str:
        """启动详情（启动方式、页面标题、地址、TYRANO 类型）；没有时返回空字符串"""
        lines = []
        mode = info.get("launch_mode")
        if mode:
            mode_text = {
                "steam": self.t("runtime_modify_launch_mode_steam"),
                "direct": self.t("runtime_modify_launch_mode_direct"),
            }.get(mode, mode)
            lines.append(f"{self.t('runtime_modify_status_detail_launch_mode')}: {mode_text}")
        if "target_title" in info:
            lines.append(f"{self.t('runtime_modify_status_detail_title')}: {info['target_title']}")
        url = info.get("inspector_url", info.get("target_url"))
        if url is not None:
            lines.append(f"{self.t('runtime_modify_status_detail_url')}: {url}")
        if "tyrano_type" in info:
            lines.append(f"{self.t('runtime_modify_status_detail_tyrano_type')}: {info['tyrano_type']}")
        return "\n\n" + "\n".join(lines) if lines else ""

    def _on_stop_clicked(self) -> None:
        port = self._parse_port()[0]
        self.stop_button.configure(state="disabled")
        run_in_background(self.parent, lambda: self.service.stop_game(port), self._on_stop_done)

    def _on_stop_done(self, _result: None, exc: Optional[BaseException]) -> None:
        if self._closed:
            return
        if exc is not None:
            self._update_status_widgets()
            showerror_relative(
                self.root, self.t("error"), self.t("runtime_modify_error_stop_game_failed", error=str(exc)))
            return
        self._set_status_text(self.t("runtime_modify_game_stopped"))
        self._status_generation += 1
        self._set_game_status(False, None)
        self._poll_soon()

    # ------------------------------------------------------------ 变量编辑

    def _open_variable_editor(self, kind: str) -> None:
        """后台读取 sf 或 kag.stat，然后打开可编辑的查看器（保存时注入回游戏）"""
        port = self._port_or_show_error()
        if port is None:
            return
        js_path = "TYRANO.kag.variable.sf" if kind == "sf" else "TYRANO.kag.stat"

        def read() -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
            ws_url = fetch_ws_url(port)
            if ws_url is None:
                return None, None, None
            data, error = read_json_variable(ws_url, js_path)
            return ws_url, data, error

        run_in_background(self.parent, read, lambda result, exc: self._on_variable_read(kind, result, exc))

    def _on_variable_read(self, kind: str, result: Optional[tuple], exc: Optional[BaseException]) -> None:
        if self._closed:
            return
        ws_url, data, error = result if exc is None else ("", None, str(exc))
        if ws_url is None:
            showerror_relative(self.root, self.t("error"), self.t("runtime_modify_sf_game_not_running"))
            return
        if error is not None:
            key = "runtime_modify_sf_read_failed" if kind == "sf" else "runtime_modify_kag_stat_read_failed"
            showerror_relative(self.root, self.t("error"), self.t(key).format(error=error))
            return

        from src.modules.save_analysis.sf.save_file_viewer import (
            DEFAULT_SF_COLLAPSED_FIELDS,
            SaveFileViewer,
            ViewerConfig,
        )
        common = dict(
            ws_url=ws_url,
            service=self.service,
            enable_edit_by_default=True,
            save_button_text="runtime_modify_sf_save_inject_button",
            show_enable_edit_checkbox=False,
        )
        if kind == "sf":
            config = ViewerConfig(collapsed_fields=DEFAULT_SF_COLLAPSED_FIELDS, **common)
        else:
            config = ViewerConfig(
                show_collapse_checkbox=True,
                show_hint_label=True,
                title_key="runtime_modify_kag_stat_edit_title",
                inject_method="kag_stat",
                collapsed_fields=DEFAULT_KAG_STAT_COLLAPSED_FIELDS,
                **common,
            )
        SaveFileViewer.open_or_focus(
            viewer_id="runtime_sf" if kind == "sf" else "runtime_kag_stat",
            window=self.root,
            storage_dir=self.storage_dir or "",
            save_data=data,
            t_func=self.t,
            on_close_callback=None,
            mode="runtime",
            viewer_config=config,
        )

    # ------------------------------------------------------------ 弹窗

    def _open_console(self) -> None:
        if _window_alive(self.console_window):
            restore_and_activate_window(self.console_window)
            return
        self.console_window = DevToolsConsoleWindow(
            self.root, self.t, lambda: self._ws_url, self.storage_dir, on_close=self._on_console_closed)
        self.console_window.set_enabled(self._hook_enabled)

    def _on_console_closed(self) -> None:
        self.console_window = None

    def _open_misc_dialog(self) -> None:
        if _window_alive(self.misc_dialog):
            restore_and_activate_window(self.misc_dialog)
        else:
            self.misc_dialog = RuntimeMiscDialog(
                self.root, self.t, self._force_fast_forward, self._open_cache_clean_dialog)
        self.misc_dialog.set_enabled(self._hook_enabled)

    def _open_cache_clean_dialog(self) -> None:
        if _window_alive(self.cache_clean_dialog):
            restore_and_activate_window(self.cache_clean_dialog)
        else:
            self.cache_clean_dialog = CacheCleanDialog(self.root, self.t, lambda: self._ws_url)

    # ------------------------------------------------------------ 强制快进（Alt+S）

    def _register_hotkey(self) -> None:
        """注册全局热键 Alt+S（游戏窗口在前台时也能用），失败时退回为本程序窗口内的快捷键"""
        if keyboard is not None:
            try:
                # keyboard 在它自己的线程里调用回调，那里不能碰 Tk：只做标记，由 _check_hotkey 在主线程处理
                self._hotkey_handle = keyboard.add_hotkey("alt+s", self._hotkey_pressed.set)
                self._check_hotkey()
                logger.info("Global hotkey Alt+S registered")
                return
            except Exception as e:
                logger.warning(f"Failed to register global hotkey: {e}, falling back to window-level hotkey")
        self.root.bind("<Alt-s>", self._on_window_hotkey)
        self.root.bind("<Alt-S>", self._on_window_hotkey)

    def _check_hotkey(self) -> None:
        if self._closed:
            return
        if self._hotkey_pressed.is_set():
            self._hotkey_pressed.clear()
            if self._hook_enabled:
                self._force_fast_forward()
        self._hotkey_job = self.parent.after(HOTKEY_CHECK_MS, self._check_hotkey)

    def _on_window_hotkey(self, _event: tk.Event) -> str:
        if self._hook_enabled:
            self._force_fast_forward()
        return "break"

    def _unregister_hotkey(self) -> None:
        if self._hotkey_handle is not None:
            try:
                keyboard.remove_hotkey(self._hotkey_handle)
            except (KeyError, ValueError) as e:
                logger.debug(f"Error unregistering hotkey: {e}")
            self._hotkey_handle = None
        else:
            self.root.unbind("<Alt-s>")
            self.root.unbind("<Alt-S>")

    def _force_fast_forward(self) -> None:
        """把当前 label 标记为已读，让游戏允许快进"""
        ws_url = self._ws_url
        if ws_url is None:
            self._on_fast_forward_done((False, "websocket_not_available"), None)
            return
        run_in_background(self.parent, lambda: self.service.mark_current_label_read(ws_url), self._on_fast_forward_done)

    def _on_fast_forward_done(self, result: Optional[Tuple[bool, Optional[str]]], exc: Optional[BaseException]) -> None:
        success, error = result if exc is None else (False, str(exc))
        if success:
            return
        error = error or ""
        logger.error(f"Failed to mark as read: {error}")
        if "game_not_using_read_record" in error:
            message = self.t("runtime_modify_mark_read_no_record")
        elif "not_in_any_label" in error:
            message = self.t("runtime_modify_mark_read_no_label")
        elif "websocket_not_available" in error:
            message = self.t("runtime_modify_mark_read_websocket_error")
        else:
            message = self.t("runtime_modify_mark_read_failed", error=error)
        showerror_relative(self.root, self.t("error"), message)

    # ------------------------------------------------------------ 生命周期

    def cleanup(self, stop_game: bool = True) -> None:
        """停止轮询、注销热键、关闭弹窗；stop_game 为 False 时（切换目录）保留游戏进程"""
        self._closed = True
        for job in (self._poll_job, self._hotkey_job):
            if job is not None:
                try:
                    self.parent.after_cancel(job)
                except tk.TclError:
                    pass
        self._unregister_hotkey()

        for window in (self.console_window, self.misc_dialog, self.cache_clean_dialog):
            if _window_alive(window):
                window.destroy()

        if stop_game and self.service.game_process is not None:
            try:
                self.service.stop_game(self._parse_port()[0])
                logger.info("Game process stopped during cleanup")
            except OSError as e:
                logger.debug(f"Error stopping game during cleanup: {e}")

    def update_language(self, language: str) -> None:
        """切换语言：重建本页界面（保留端口输入），并刷新已打开弹窗的文字"""
        self.current_language = language
        port_text = self.port_entry.get()
        self.container.destroy()
        self._build_ui()
        self.port_entry.delete(0, "end")
        self.port_entry.insert(0, port_text)
        for window in (self.console_window, self.misc_dialog, self.cache_clean_dialog):
            if _window_alive(window):
                window.update_language()
