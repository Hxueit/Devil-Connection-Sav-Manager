"""运行时修改标签页：启动/停止游戏、显示连接状态，以及控制台、变量编辑、杂项功能的入口

状态轮询：每隔几秒在后台线程检查一次调试端口（service.poll_status），
结果回到主线程后更新界面；按钮、控制台等都只读取缓存的状态，不会阻塞界面。
"""
import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

import customtkinter as ctk
import tkinter as tk
from tkinter import font as tkfont

try:
    import keyboard
except ImportError:
    keyboard = None

from src.modules.runtime_modify.cache_clean_dialog import CacheCleanDialog
from src.modules.runtime_modify.console import DevToolsConsoleWindow
from src.modules.runtime_modify.dialogs import RuntimeDialog, RuntimeMiscDialog, set_textbox_text
from src.modules.runtime_modify.service import (
    DEFAULT_PORT,
    KAG_STAT_JS_PATH,
    MAX_PORT,
    MIN_PORT,
    SF_JS_PATH,
    GameNotConnectedError,
    LaunchError,
    MarkReadRefusedError,
    RuntimeModifyService,
    assign_json_variable,
    check_port_available,
    describe_changes,
    fetch_ws_url,
    get_game_exe_path,
    inject_and_save_sf,
    mark_current_label_read,
    read_json_variable,
)
from src.modules.save_analysis.sf.save_file_viewer import DEFAULT_SF_COLLAPSED_FIELDS, SaveFileViewer, ViewerTexts
from src.utils.background import run_in_background
from src.utils.styles import Colors, get_cjk_font, white_button
from src.utils.ui_utils import showerror_relative, showinfo_relative

logger = logging.getLogger(__name__)

STATUS_POLL_MS = 2000           # 游戏运行时的状态检查间隔
STATUS_POLL_IDLE_MS = 5000      # 游戏未运行时检查得慢一些
HOTKEY_CHECK_MS = 100

# kag.stat 编辑器里默认折叠的大字段
DEFAULT_KAG_STAT_COLLAPSED_FIELDS = [
    "map_label", "charas", "map_keyframe", "stack", "popopo", "map_macro", "fuki", "three",
]

# 变量编辑器的「保存」是注入游戏内存，提示文字与保存文件不同
SF_EDITOR_TEXTS = ViewerTexts(
    save_button="runtime_modify_sf_save_inject_button",
    confirm_save="runtime_modify_sf_confirm_inject",
    save_success="runtime_modify_sf_inject_success",
    save_failed="runtime_modify_sf_inject_failed",
    load_failed="runtime_modify_sf_read_failed",
)
KAG_STAT_EDITOR_TEXTS = ViewerTexts(
    save_button="runtime_modify_sf_save_inject_button",
    confirm_save="runtime_modify_kag_stat_confirm_inject",
    save_success="runtime_modify_sf_inject_success",
    save_failed="runtime_modify_kag_stat_inject_failed",
    load_failed="runtime_modify_kag_stat_read_failed",
)

# 强制快进被游戏拒绝的原因（MarkReadRefusedError.code）-> 翻译键；其余原因显示通用错误
MARK_READ_REFUSED_MESSAGES = {
    "game_not_using_read_record": "runtime_modify_mark_read_no_record",
    "not_in_any_label": "runtime_modify_mark_read_no_label",
}


class RuntimeModifyTab:
    """运行时修改标签页"""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        root: ctk.CTk,
        storage_dir: Optional[str],
        t: Callable[..., str],
    ) -> None:
        self.parent = parent
        self.storage_dir = storage_dir
        self.t = t  # 翻译函数，总是返回当前语言的文字
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
        white_button(
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
        self.launch_button = white_button(
            action_row, self.t("runtime_modify_launch_button"), self._on_launch_clicked)
        self.launch_button.pack(side="left", padx=(0, 10))
        self.stop_button = white_button(
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
        set_textbox_text(self.status_text, self.t("runtime_modify_status_ready"))

        # 功能入口：控制台 | sf 编辑  kag.stat 编辑 | 杂项
        tools_row = ctk.CTkFrame(content, fg_color=Colors.WHITE)
        tools_row.pack(anchor="w", pady=(10, 0), fill="x")
        white_button(
            tools_row, self.t("runtime_modify_open_console_button"), self._open_console,
        ).pack(side="left")
        self._separator(tools_row)
        self.sf_edit_button = white_button(
            tools_row, self.t("runtime_modify_sf_edit_button"), lambda: self._open_variable_editor("sf"),
            state="disabled")
        self.sf_edit_button.pack(side="left")
        self.kag_stat_edit_button = white_button(
            tools_row, self.t("runtime_modify_tyrano_edit_button"), lambda: self._open_variable_editor("kag_stat"),
            state="disabled")
        self.kag_stat_edit_button.pack(side="left", padx=(10, 0))
        self._separator(tools_row)
        self.misc_button = white_button(
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
        for button in (self.sf_edit_button, self.kag_stat_edit_button, self.misc_button):
            button.configure(state=runtime_state)
        for dialog in (self.console_window, self.misc_dialog):
            if dialog is not None and dialog.is_open():
                dialog.set_enabled(self._hook_enabled)

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
        set_textbox_text(self.status_text, self.t("runtime_modify_status_launching"))
        run_in_background(self.parent, lambda: self.service.launch_and_test(exe_path, port), self._on_launch_done)

    def _on_launch_done(self, info: Optional[Dict[str, Any]], error: Optional[BaseException]) -> None:
        if self._closed:
            return
        self._is_launching = False
        self.launch_button.configure(state="normal", text=self.t("runtime_modify_launch_button"))

        self._status_generation += 1
        if error is None:
            self._set_game_status(True, info["ws_url"])
        else:
            self._set_game_status(self._game_running, None)
        self._poll_soon()

        if error is None:
            set_textbox_text(self.status_text,
                             self.t("runtime_modify_connection_success") + self._format_launch_details(info))
            showinfo_relative(self.root, self.t("success"), self.t("runtime_modify_connection_success"))
            return
        if isinstance(error, LaunchError):
            details = self._format_launch_details(error.info)
            if error.still_starting:
                # 游戏还在启动（Steam 较慢），不弹窗，之后的状态轮询会发现它
                set_textbox_text(self.status_text, self.t("runtime_modify_error_game_not_ready") + details)
                return
            message = (str(error) or self.t("runtime_modify_connection_failed")) + details
        else:
            message = self.t("runtime_modify_error_launch_failed", error=str(error))
        set_textbox_text(self.status_text, message)
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
        set_textbox_text(self.status_text, self.t("runtime_modify_game_stopped"))
        self._status_generation += 1
        self._set_game_status(False, None)
        self._poll_soon()

    # ------------------------------------------------------------ 变量编辑

    def _open_variable_editor(self, kind: str) -> None:
        """后台读取 sf 或 kag.stat，然后打开可编辑的查看器（保存时注入回游戏）"""
        port = self._port_or_show_error()
        if port is None:
            return
        js_path = SF_JS_PATH if kind == "sf" else KAG_STAT_JS_PATH

        def read() -> Tuple[str, Dict[str, Any]]:
            ws_url = fetch_ws_url(port)
            if ws_url is None:
                raise GameNotConnectedError(f"No game page on port {port}")
            return ws_url, read_json_variable(ws_url, js_path)

        run_in_background(self.parent, read, lambda result, error: self._on_variable_read(kind, result, error))

    def _on_variable_read(self, kind: str, result: Optional[Tuple[str, Dict[str, Any]]],
                          error: Optional[BaseException]) -> None:
        if self._closed:
            return
        if isinstance(error, GameNotConnectedError):
            showerror_relative(self.root, self.t("error"), self.t("runtime_modify_sf_game_not_running"))
            return
        texts = SF_EDITOR_TEXTS if kind == "sf" else KAG_STAT_EDITOR_TEXTS
        if error is not None:
            showerror_relative(self.root, self.t("error"), self.t(texts.load_failed, error=str(error)))
            return

        ws_url, data = result
        if kind == "sf":
            SaveFileViewer.open_or_focus(
                viewer_id="runtime_sf",
                parent=self.root,
                t=self.t,
                data=data,
                title=self.t("save_file_viewer_title"),
                load=lambda: read_json_variable(ws_url, SF_JS_PATH),
                save=lambda edited: inject_and_save_sf(ws_url, edited),
                texts=texts,
                collapsed_fields=DEFAULT_SF_COLLAPSED_FIELDS,
                runtime=True,
                # 打开编辑器之后游戏可能又改了 sf（如解锁了结局），注入前让用户确认
                find_outside_changes=lambda original: describe_changes(
                    original, read_json_variable(ws_url, SF_JS_PATH)),
            )
        else:
            SaveFileViewer.open_or_focus(
                viewer_id="runtime_kag_stat",
                parent=self.root,
                t=self.t,
                data=data,
                title=self.t("runtime_modify_kag_stat_edit_title"),
                load=lambda: read_json_variable(ws_url, KAG_STAT_JS_PATH),
                save=lambda edited: assign_json_variable(ws_url, KAG_STAT_JS_PATH, edited),
                texts=texts,
                collapsed_fields=DEFAULT_KAG_STAT_COLLAPSED_FIELDS,
                show_collapse_toggle=True,
                runtime=True,
            )

    # ------------------------------------------------------------ 弹窗

    def _open_dialogs(self) -> List[RuntimeDialog]:
        dialogs = (self.console_window, self.misc_dialog, self.cache_clean_dialog)
        return [dialog for dialog in dialogs if dialog is not None and dialog.is_open()]

    def _open_console(self) -> None:
        if self.console_window is not None and self.console_window.is_open():
            self.console_window.show()
            return
        self.console_window = DevToolsConsoleWindow(
            self.root, self.t, lambda: self._ws_url, self.storage_dir, on_close=self._on_console_closed)
        self.console_window.set_enabled(self._hook_enabled)

    def _on_console_closed(self) -> None:
        self.console_window = None

    def _open_misc_dialog(self) -> None:
        if self.misc_dialog is not None and self.misc_dialog.is_open():
            self.misc_dialog.show()
        else:
            self.misc_dialog = RuntimeMiscDialog(
                self.root, self.t, self._force_fast_forward, self._open_cache_clean_dialog)
        self.misc_dialog.set_enabled(self._hook_enabled)

    def _open_cache_clean_dialog(self) -> None:
        if self.cache_clean_dialog is not None and self.cache_clean_dialog.is_open():
            self.cache_clean_dialog.show()
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
            showerror_relative(self.root, self.t("error"), self.t("runtime_modify_mark_read_websocket_error"))
            return
        run_in_background(self.parent, lambda: mark_current_label_read(ws_url), self._on_fast_forward_done)

    def _on_fast_forward_done(self, _result: None, error: Optional[BaseException]) -> None:
        if error is None:
            return
        logger.error(f"Failed to mark as read: {error}")
        if isinstance(error, MarkReadRefusedError) and error.code in MARK_READ_REFUSED_MESSAGES:
            message = self.t(MARK_READ_REFUSED_MESSAGES[error.code])
        else:
            message = self.t("runtime_modify_mark_read_failed", error=str(error))
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

        for dialog in self._open_dialogs():
            dialog.close()

        if stop_game and self.service.game_process is not None:
            try:
                self.service.stop_game(self._parse_port()[0])
                logger.info("Game process stopped during cleanup")
            except OSError as e:
                logger.debug(f"Error stopping game during cleanup: {e}")

    def update_language(self) -> None:
        """切换语言：重建本页界面（保留端口输入），并刷新已打开弹窗的文字"""
        port_text = self.port_entry.get()
        self.container.destroy()
        self._build_ui()
        self.port_entry.delete(0, "end")
        self.port_entry.insert(0, port_text)
        for dialog in self._open_dialogs():
            dialog.update_language()
