"""存档查看/编辑窗口

以 JSON 文本显示存档内容，支持折叠大字段、搜索、复制、编辑后保存。
被多处复用：
- sf 存档分析页的「查看存档文件」（mode="file"，写回 DevilConnection_sf.sav）
- tyrano 存档槽 / 自动存档（mode="file"，通过 ViewerConfig.custom_load_func/custom_save_func
  或子类重写 _save_to_file 保存到别的文件）
- 运行时修改页（mode="runtime"，通过 CDP 读写游戏内存中的 sf 或 kag.stat）
"""

import asyncio
import copy
import json
import logging
import re
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import Scrollbar, messagebox, ttk
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

from src.modules.screenshot.animation_constants import CHECKBOX_STYLE_HINT, CHECKBOX_STYLE_NORMAL
from src.utils.background import run_in_background
from src.utils.hint_animation import HintAnimation
from src.utils.sav_io import write_sav
from src.utils.styles import Colors, get_cjk_font, get_mono_font
from src.utils.ui_utils import (
    askyesno_relative,
    restore_and_activate_window,
    set_window_icon,
    showerror_relative,
    showinfo_relative,
    showwarning_relative,
)

from .fields import SF_FILE_NAME, load_save_file
from .viewer_json import format_display_data, restore_collapsed_fields

logger = logging.getLogger(__name__)

__all__ = ["SaveFileViewer", "ViewerConfig", "DEFAULT_SF_COLLAPSED_FIELDS"]

DEFAULT_SF_COLLAPSED_FIELDS: List[str] = ["record", "_tap_effect", "initialVars"]

WINDOW_SIZE = "1200x900"
CLOSE_CALLBACK_DELAY_MS = 100
# 注入后稍等片刻再从游戏读回数据，确保游戏已经处理完写入
REFRESH_AFTER_INJECT_DELAY_MS = 200

# 编辑模式下，光标位于折叠占位文字中时仍允许的按键（只移动光标/复制，不修改文本）
NAVIGATION_KEYS = {
    "Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next",
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Escape",
}

JSON_HIGHLIGHT_PATTERNS = [
    (re.compile(r'"[^"]*"'), "string"),
    (re.compile(r"\b(true|false|null)\b"), "keyword"),
    (re.compile(r"\b\d+\.?\d*\b"), "number"),
    (re.compile(r"[{}[\]]"), "bracket"),
    (re.compile(r"[:,]"), "punctuation"),
]


@dataclass
class ViewerConfig:
    """查看器配置

    Attributes:
        ws_url / service: 运行时模式使用的 CDP 地址和 RuntimeModifyService
        inject_method: 运行时模式读写的对象，"sf" 或 "kag_stat"
        collapsed_fields: 默认折叠的字段路径（支持 "stat.map_label" 这样的嵌套路径）
        custom_load_func: 文件模式下「刷新/开启编辑」时重新加载数据；不填则读取 sf 存档
        custom_save_func: 文件模式下的保存函数，返回是否成功；不填则写入 sf 存档
        on_save_callback: 保存成功后调用，参数为保存的数据
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


# viewer_id -> 已打开的查看器；同一份数据只开一个窗口
_open_viewers: Dict[str, "SaveFileViewer"] = {}


def apply_json_syntax_highlight(text_widget: tk.Text, content: str) -> None:
    """按行用正则给 JSON 文本上色（每种颜色一次 tag_add 调用，减少 Tcl 往返）"""
    ranges: Dict[str, List[str]] = {tag: [] for _, tag in JSON_HIGHLIGHT_PATTERNS}
    for line_no, line in enumerate(content.split("\n"), start=1):
        for pattern, tag in JSON_HIGHLIGHT_PATTERNS:
            for match in pattern.finditer(line):
                ranges[tag] += [f"{line_no}.{match.start()}", f"{line_no}.{match.end()}"]
    for tag, indices in ranges.items():
        text_widget.tag_remove(tag, "1.0", "end")
        if indices:
            text_widget.tag_add(tag, *indices)


class SaveFileViewer:
    """存档查看/编辑窗口"""

    @classmethod
    def open_or_focus(cls, viewer_id: str, **kwargs: Any) -> "SaveFileViewer":
        """打开新窗口；同一 viewer_id 的窗口已存在时只把它提到前面（不刷新，以免覆盖未保存的编辑）"""
        existing = _open_viewers.get(viewer_id)
        if existing is not None and existing.viewer_window.winfo_exists():
            restore_and_activate_window(existing.viewer_window)
            return existing
        viewer = cls(**kwargs, _viewer_id=viewer_id)
        _open_viewers[viewer_id] = viewer
        return viewer

    def __init__(
        self,
        window: tk.Widget,
        storage_dir: str,
        save_data: Dict[str, Any],
        t_func: Callable[[str], str],
        on_close_callback: Optional[Callable[[], None]] = None,
        mode: Literal["file", "runtime"] = "file",
        viewer_config: Optional[ViewerConfig] = None,
        _viewer_id: Optional[str] = None,
    ) -> None:
        """
        Args:
            window: 任意所属控件，用来找到主窗口
            on_close_callback: 关闭窗口时调用（仅当这次打开期间保存过数据）
        """
        self._viewer_id = _viewer_id
        self.window = window
        self.storage_dir = storage_dir
        self.save_data = save_data
        # 运行时模式注入前用它检测游戏里的数据是否在打开后被改过
        self.original_save_data = self._deep_copy_data(save_data)
        self.t = t_func
        self.on_close_callback = on_close_callback
        self.mode = mode
        self.viewer_config = viewer_config or ViewerConfig()
        self._data_was_saved = False
        self._baseline = ""          # 最近一次渲染的文本，用来判断是否有未保存的修改
        self._line_count = 0
        self._search_term = ""
        self._search_index = -1
        self.save_button: Optional[ttk.Button] = None
        self._hint_animation: Optional[HintAnimation] = None

        self.viewer_window = tk.Toplevel(window.nametowidget("."))
        self.viewer_window.title(self.t(self.viewer_config.title_key))
        self.viewer_window.geometry(WINDOW_SIZE)
        self.viewer_window.configure(bg=Colors.MODAL_BG)
        set_window_icon(self.viewer_window)
        self.viewer_window.bind("<Destroy>", self._on_destroy)
        self.viewer_window.protocol("WM_DELETE_WINDOW", self._on_close)

        self.disable_collapse_var = tk.BooleanVar(value=False)
        self.enable_edit_var = tk.BooleanVar(value=self.viewer_config.enable_edit_by_default)
        self._build_ui()
        self._render()

    @staticmethod
    def _deep_copy_data(data: Dict[str, Any]) -> Dict[str, Any]:
        return copy.deepcopy(data)

    # ---------------------------------------------------------------- 界面

    def _build_ui(self) -> None:
        self._setup_styles()
        main_frame = tk.Frame(self.viewer_window, bg=Colors.MODAL_BG)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)

        if self.viewer_config.show_hint_label:
            hint_frame = tk.Frame(main_frame, bg=Colors.MODAL_BG)
            hint_frame.pack(fill="x", pady=(0, 10))
            ttk.Label(hint_frame, text=self.t("viewer_hint_text"), font=get_cjk_font(9), wraplength=850,
                      justify="left", style="Modal.TLabel").pack(anchor="w", padx=5)

        toolbar = tk.Frame(main_frame, bg=Colors.MODAL_BG)
        toolbar.pack(fill="x", pady=(0, 5))
        self._build_toolbar(toolbar)
        self._build_text_area(main_frame)

    def _setup_styles(self) -> None:
        style = ttk.Style(self.viewer_window)
        style.configure("Modal.TLabel", background=Colors.MODAL_BG, foreground="gray", borderwidth=0,
                        relief="flat")
        style.map("Modal.TLabel", background=[("active", Colors.MODAL_BG), ("!active", Colors.MODAL_BG)])
        style.configure("Modal.TCheckbutton", background=Colors.MODAL_BG, foreground=Colors.TEXT_PRIMARY,
                        borderwidth=0, relief="flat")
        style.map("Modal.TCheckbutton", background=[
            ("active", Colors.MODAL_BG), ("!active", Colors.MODAL_BG), ("selected", Colors.MODAL_BG)])
        style.configure(CHECKBOX_STYLE_NORMAL, background=Colors.MODAL_BG)
        style.configure(CHECKBOX_STYLE_HINT, background=Colors.MODAL_BG, foreground="#FF6B35")

    def _build_toolbar(self, toolbar: tk.Frame) -> None:
        if self.viewer_config.show_collapse_checkbox:
            ttk.Checkbutton(toolbar, text=self.t("disable_collapse_horizontal"), variable=self.disable_collapse_var,
                            command=self._on_collapse_toggled, style="Modal.TCheckbutton").pack(side="left", padx=5)

        search_frame = tk.Frame(toolbar, bg=Colors.MODAL_BG)
        search_frame.pack(side="left", padx=5)
        self.search_entry = ttk.Entry(search_frame, width=20)
        self.search_entry.pack(side="left", padx=2)
        self.search_entry.bind("<Return>", self._on_search_enter)
        self.search_results_label = ttk.Label(search_frame, text="", style="Modal.TLabel")
        self.search_results_label.pack(side="left", padx=2)
        ttk.Button(search_frame, text="↓", width=3, command=self._find).pack(side="left", padx=2)
        ttk.Button(search_frame, text="↑", width=3,
                   command=lambda: self._find(backwards=True)).pack(side="left", padx=2)
        for sequence in ("<Control-f>", "<Control-F>"):
            self.viewer_window.bind(sequence, self._focus_search)

        ttk.Button(toolbar, text=self.t("copy_to_clipboard"), command=self._copy_to_clipboard).pack(
            side="left", padx=5)

        toolbar_right = tk.Frame(toolbar, bg=Colors.MODAL_BG)
        toolbar_right.pack(side="right", padx=5)
        ttk.Button(toolbar_right, text=self.t("refresh"), command=self._on_refresh_clicked).pack(side="right", padx=5)

        if self.viewer_config.show_enable_edit_checkbox:
            wrapper = tk.Frame(toolbar_right, bg=Colors.MODAL_BG)
            wrapper.pack(side="right", padx=5)
            checkbox = ttk.Checkbutton(wrapper, text=self.t("enable_edit"), variable=self.enable_edit_var,
                                       command=self._on_edit_toggled, style=CHECKBOX_STYLE_NORMAL)
            checkbox.pack()
            # HintAnimation 通过这两个属性找到要抖动的外层 Frame 和它原来的边距
            checkbox.wrapper = wrapper
            toolbar_right.update_idletasks()
            checkbox._original_pack_info = wrapper.pack_info()
            self._hint_animation = HintAnimation(self.viewer_window, checkbox, CHECKBOX_STYLE_NORMAL,
                                                 CHECKBOX_STYLE_HINT)

        self.save_button = ttk.Button(toolbar_right, text=self.t(self.viewer_config.save_button_text),
                                      command=self._on_save_clicked)
        self.save_button.pack(side="right", padx=5)

    def _build_text_area(self, parent: tk.Frame) -> None:
        text_frame = tk.Frame(parent)
        text_frame.pack(fill="both", expand=True)
        mono_font = get_mono_font(10)

        self.line_numbers = tk.Text(text_frame, font=mono_font, bg=Colors.CODE_GUTTER_BG, fg=Colors.TEXT_MUTED,
                                    width=4, padx=5, pady=2, state="disabled", wrap="none",
                                    highlightthickness=0, borderwidth=0)
        self.line_numbers.pack(side="left", fill="y")

        text_container = tk.Frame(text_frame)
        text_container.pack(side="left", fill="both", expand=True)
        v_scrollbar = Scrollbar(text_container, orient="vertical")
        v_scrollbar.pack(side="right", fill="y")
        h_scrollbar = Scrollbar(text_container, orient="horizontal")
        h_scrollbar.pack(side="bottom", fill="x")

        def on_yscroll(first: str, last: str) -> None:
            # 文本每次滚动（滚轮、键盘、拖动滚动条）都会调用这里，顺便同步行号
            v_scrollbar.set(first, last)
            self.line_numbers.yview_moveto(first)

        self.text_widget = tk.Text(text_container, font=mono_font, bg=Colors.CODE_BG, fg=Colors.TEXT_DARK,
                                   yscrollcommand=on_yscroll, xscrollcommand=h_scrollbar.set, wrap="none",
                                   tabs=("2c", "4c", "6c", "8c", "10c", "12c", "14c", "16c"))
        self.text_widget.pack(side="left", fill="both", expand=True)
        v_scrollbar.config(command=self.text_widget.yview)
        h_scrollbar.config(command=self.text_widget.xview)

        tw = self.text_widget
        tw.tag_config("string", foreground="#008000", font=mono_font)
        tw.tag_config("keyword", foreground="#0000FF", font=mono_font)
        tw.tag_config("number", foreground="#FF0000", font=mono_font)
        tw.tag_config("bracket", foreground="#000000", font=(mono_font[0], mono_font[1], "bold"))
        tw.tag_config("punctuation", foreground=Colors.TEXT_MUTED, font=mono_font)
        tw.tag_config("search_highlight", background="yellow")
        tw.bind("<KeyPress>", self._on_key_press)
        tw.bind("<KeyRelease>", lambda e: self._update_line_numbers())

    # ---------------------------------------------------------------- 显示

    def _get_text(self) -> str:
        return self.text_widget.get("1.0", "end-1c")

    def _render(self) -> None:
        """按当前数据和折叠设置重新生成文本；之后的修改都相对于这次渲染的内容判断"""
        scroll_position = self.text_widget.yview()[0]
        self._clear_search()
        if self.disable_collapse_var.get():
            content = json.dumps(self.save_data, ensure_ascii=False, indent=2)
        else:
            content = format_display_data(self.save_data, self.viewer_config.collapsed_fields,
                                          self.t("collapsed_field_text"))
        self.text_widget.config(state="normal")
        self.text_widget.delete("1.0", "end")
        self.text_widget.insert("1.0", content)
        apply_json_syntax_highlight(self.text_widget, content)
        self._baseline = content
        self._update_line_numbers()
        self._apply_edit_state()
        self.viewer_window.after_idle(lambda: self.text_widget.yview_moveto(scroll_position))

    def _apply_edit_state(self) -> None:
        state = "normal" if self.enable_edit_var.get() else "disabled"
        self.text_widget.config(state=state)
        if self.save_button is not None:
            self.save_button.config(state=state)

    def _update_line_numbers(self) -> None:
        line_count = int(self.text_widget.index("end-1c").split(".")[0])
        if line_count == self._line_count:
            return
        self._line_count = line_count
        self.line_numbers.config(state="normal")
        self.line_numbers.delete("1.0", "end")
        self.line_numbers.insert("end", "\n".join(str(i) for i in range(1, line_count + 1)) + "\n")
        self.line_numbers.config(state="disabled")
        self.line_numbers.yview_moveto(self.text_widget.yview()[0])

    def _copy_to_clipboard(self) -> None:
        self.viewer_window.clipboard_clear()
        self.viewer_window.clipboard_append(self._get_text())

    # ---------------------------------------------------------------- 编辑

    def _has_unsaved_changes(self) -> bool:
        return self.enable_edit_var.get() and self._get_text() != self._baseline

    def _confirm_discard_changes(self) -> bool:
        return askyesno_relative(self.viewer_window, self.t("refresh_confirm_title"),
                                 self.t("unsaved_changes_warning"))

    def _on_key_press(self, event: tk.Event) -> Optional[str]:
        is_ctrl_c = bool(event.state & 0x4) and event.keysym.lower() == "c"
        if not self.enable_edit_var.get():
            if is_ctrl_c:
                return None
            # 只读时想删除选中内容，提示用户先勾选「启用编辑」
            if (self._hint_animation and event.keysym in ("Delete", "BackSpace")
                    and self.text_widget.tag_ranges("sel")):
                self._hint_animation.trigger()
            return "break"
        if is_ctrl_c or event.keysym in NAVIGATION_KEYS:
            return None
        index = "insert-1c" if event.keysym == "BackSpace" else "insert"
        if self._in_collapsed_placeholder(index):
            showwarning_relative(self.viewer_window, self.t("cannot_edit_collapsed"),
                                 self.t("cannot_edit_collapsed_detail"))
            return "break"
        return None

    def _in_collapsed_placeholder(self, index: str) -> bool:
        """index 是否位于折叠占位文字内（改动占位文字会导致保存时无法还原原值）"""
        if self.disable_collapse_var.get():
            return False
        tw = self.text_widget
        placeholder = self.t("collapsed_field_text")
        line_end = tw.index(f"{index} lineend")
        start = tw.search(placeholder, f"{index} linestart", line_end, exact=True)
        while start:
            end = f"{start}+{len(placeholder)}c"
            if tw.compare(start, "<=", index) and tw.compare(index, "<", end):
                return True
            start = tw.search(placeholder, end, line_end, exact=True)
        return False

    def _on_collapse_toggled(self) -> None:
        if self._has_unsaved_changes() and not self._confirm_discard_changes():
            self.disable_collapse_var.set(not self.disable_collapse_var.get())
            return
        self._render()

    def _on_edit_toggled(self) -> None:
        # Checkbutton 的 command 在变量切换之后才调用：此时 False 表示正在关闭编辑
        # （不能用 _has_unsaved_changes()，它在编辑关闭时总是返回 False）
        if not self.enable_edit_var.get() and self._get_text() != self._baseline:
            if not self._confirm_discard_changes():
                self.enable_edit_var.set(True)
                return
        if self.mode == "file":
            # 重新读取文件，避免在过期的数据上编辑
            data = self._load_file_data()
            if data is None:
                self.enable_edit_var.set(False)
                self._apply_edit_state()
                return
            self._set_data(data)
        self._render()

    def _set_data(self, data: Dict[str, Any]) -> None:
        self.save_data = data
        self.original_save_data = self._deep_copy_data(data)

    def _on_refresh_clicked(self) -> None:
        if self._has_unsaved_changes() and not self._confirm_discard_changes():
            return
        if self.mode == "runtime":
            self._refresh_from_runtime()
            return
        data = self._load_file_data()
        if data is not None:
            self._set_data(data)
            self._render()

    def _load_file_data(self) -> Optional[Dict[str, Any]]:
        load_func = self.viewer_config.custom_load_func
        try:
            if load_func is not None:
                return load_func()
            return load_save_file(self.storage_dir)
        except FileNotFoundError:
            showerror_relative(self.viewer_window, self.t("error"), self.t("save_file_not_found"))
        except Exception as e:
            logger.error("Failed to load save data: %s", e, exc_info=True)
            name = SF_FILE_NAME if load_func is None else ""
            showerror_relative(self.viewer_window, self.t("error"), f"{name} {e}".strip())
        return None

    def _on_save_clicked(self) -> None:
        content = self._get_text()
        try:
            edited_data = json.loads(content)
        except json.JSONDecodeError as e:
            showerror_relative(self.viewer_window, self.t("json_format_error"),
                               self.t("json_format_error_detail").format(error=str(e)))
            return
        if not self.disable_collapse_var.get() and isinstance(edited_data, dict):
            restore_collapsed_fields(edited_data, self.save_data, self.viewer_config.collapsed_fields,
                                     self.t("collapsed_field_text"))
        if self.mode == "runtime":
            self._save_to_runtime(edited_data)
        else:
            # 参数形式为兼容 tyrano 自动存档查看器（AutoSaveFileViewer）对本方法的重写
            self._save_to_file(edited_data, content, self.enable_edit_var, self.text_widget,
                               self._render, self._get_text)

    def _save_to_file(self, edited_data: Dict[str, Any], content: str, enable_edit_var: tk.BooleanVar,
                      text_widget: tk.Text, update_display: Callable[[], None],
                      get_current_text_content: Callable[[], str]) -> None:
        """确认后保存到文件；子类可重写以保存到别处"""
        if not messagebox.askyesno(self.t("save_confirm_title"), self.t("save_confirm_text"),
                                   parent=self.viewer_window):
            return
        try:
            if self.viewer_config.custom_save_func is not None:
                if not self.viewer_config.custom_save_func(edited_data):
                    showerror_relative(self.viewer_window, self.t("error"),
                                       self.t("save_file_failed").format(error="保存失败"))
                    return
            else:
                write_sav(Path(self.storage_dir) / SF_FILE_NAME, edited_data)
        except Exception as e:
            logger.error("Failed to save: %s", e, exc_info=True)
            showerror_relative(self.viewer_window, self.t("error"), self.t("save_file_failed").format(error=str(e)))
            return

        self._set_data(edited_data)
        self._data_was_saved = True
        showinfo_relative(self.viewer_window, self.t("success"), self.t("save_success"))
        update_display()
        self._call_on_save(edited_data)

    def _call_on_save(self, edited_data: Dict[str, Any]) -> None:
        if self.viewer_config.on_save_callback:
            try:
                self.viewer_config.on_save_callback(edited_data)
            except Exception as e:
                logger.error("on_save_callback failed: %s", e, exc_info=True)

    # ---------------------------------------------------------------- 运行时模式

    def _run_async(self, coroutine_func: Callable[[], Any], on_done: Callable[[Any, Optional[str]], None]) -> None:
        """在后台线程执行返回 (结果, 错误信息) 的协程，完成后在主线程调用 on_done(结果, 错误信息)"""
        def done(result: Optional[Tuple[Any, Optional[str]]], error: Optional[BaseException]) -> None:
            if error is not None:
                on_done(None, str(error))
            else:
                on_done(*result)

        run_in_background(self.viewer_window, lambda: asyncio.run(coroutine_func()), done)

    def _runtime_target(self) -> Optional[Tuple[Any, str, bool]]:
        """返回 (service, ws_url, 是否为 kag.stat)；游戏未连接时弹窗并返回 None"""
        config = self.viewer_config
        if config.service is None or config.ws_url is None:
            showerror_relative(self.viewer_window, self.t("error"), self.t("runtime_modify_sf_game_not_running"))
            return None
        return config.service, config.ws_url, config.inject_method == "kag_stat"

    def _read_runtime(self, on_data: Callable[[Optional[Dict[str, Any]], Optional[str]], None]) -> None:
        config = self.viewer_config
        service = config.service
        read = service.read_tyrano_kag_stat if config.inject_method == "kag_stat" else service.read_tyrano_variable_sf
        self._run_async(lambda: read(config.ws_url), on_data)

    def _refresh_from_runtime(self) -> None:
        target = self._runtime_target()
        if target is None:
            return
        is_kag = target[2]

        def on_data(data: Optional[Dict[str, Any]], error: Optional[str]) -> None:
            if error is None and data is None:
                if not is_kag:
                    showerror_relative(self.viewer_window, self.t("error"),
                                       self.t("runtime_modify_sf_error_empty_data"))
                    return
                error = "Empty data"
            if error is not None:
                key = "runtime_modify_kag_stat_read_failed" if is_kag else "runtime_modify_sf_read_failed"
                showerror_relative(self.viewer_window, self.t("error"), self.t(key).format(error=error))
                return
            self._set_data(data)
            self._render()

        self._read_runtime(on_data)

    def _save_to_runtime(self, edited_data: Dict[str, Any]) -> None:
        """注入到游戏内存。取消或失败时保留用户的编辑内容（仍视为未保存）"""
        target = self._runtime_target()
        if target is None:
            return
        service, ws_url, is_kag = target
        confirm_key = "runtime_modify_kag_stat_confirm_inject" if is_kag else "runtime_modify_sf_confirm_inject"
        if not messagebox.askyesno(self.t("save_confirm_title"), self.t(confirm_key), parent=self.viewer_window):
            return

        def on_injected(success: bool, error: Optional[str]) -> None:
            if not success:
                if is_kag:
                    message = self.t("runtime_modify_kag_stat_inject_failed").format(error=error or "Unknown error")
                else:
                    message = self.t("runtime_modify_sf_inject_failed").format(
                        error=error or self.t("runtime_modify_sf_error_unknown"))
                showerror_relative(self.viewer_window, self.t("error"), message)
                return
            self._call_on_save(edited_data)
            showinfo_relative(self.viewer_window, self.t("success"), self.t("runtime_modify_sf_inject_success"))
            self._set_data(edited_data)
            self._data_was_saved = True
            self._render()
            self.viewer_window.after(REFRESH_AFTER_INJECT_DELAY_MS, reread)

        def reread() -> None:
            if self.viewer_window.winfo_exists():
                self._read_runtime(on_reread)

        def on_reread(data: Optional[Dict[str, Any]], error: Optional[str]) -> None:
            # 读回游戏处理后的数据；用户已经开始新的编辑时不覆盖
            if error is not None:
                logger.warning("Failed to refresh after inject: %s", error)
            elif data is not None and not self._has_unsaved_changes():
                self._set_data(data)
                self._render()

        def on_checked(has_changes: bool, changes: Any) -> None:
            if isinstance(changes, str):  # 检测过程出错，changes 是错误信息
                on_injected(False, changes)
                return
            if has_changes and not messagebox.askyesno(
                    self.t("warning"),
                    self.t("runtime_modify_sf_changes_detected").format(changes=changes.get("changes_text", "")),
                    parent=self.viewer_window):
                return
            self._run_async(lambda: service.inject_and_save_sf(ws_url, edited_data), on_injected)

        if is_kag:
            self._run_async(lambda: service.inject_kag_stat(ws_url, edited_data), on_injected)
        else:
            # 先确认游戏里的数据在打开编辑器之后没有被游戏改过，否则提示用户
            self._run_async(lambda: service.check_sf_changes(ws_url, self.original_save_data), on_checked)

    # ---------------------------------------------------------------- 搜索

    def _focus_search(self, event: Optional[tk.Event] = None) -> str:
        self.search_entry.focus()
        self.search_entry.select_range(0, "end")
        return "break"

    def _on_search_enter(self, event: tk.Event) -> str:
        self._find(backwards=bool(event.state & 0x1))  # Shift+Enter 向上查找
        return "break"

    def _clear_search(self) -> None:
        self.text_widget.tag_remove("search_highlight", "1.0", "end")
        self._search_index = -1
        self.search_results_label.config(text="")

    def _find(self, backwards: bool = False) -> None:
        """高亮所有匹配（不区分大小写）并跳到下一个/上一个"""
        term = self.search_entry.get().strip()
        if not term:
            self.search_results_label.config(text="")
            return
        if term != self._search_term:
            self._search_term = term
            self._search_index = -1

        tw = self.text_widget
        tw.tag_remove("search_highlight", "1.0", "end")
        matches = []
        start = tw.search(term, "1.0", "end", nocase=True)
        while start:
            matches.append(start)
            end = f"{start}+{len(term)}c"
            tw.tag_add("search_highlight", start, end)
            start = tw.search(term, end, "end", nocase=True)
        if not matches:
            self.search_results_label.config(text=self.t("search_not_found"))
            return

        if self._search_index == -1:
            self._search_index = len(matches) - 1 if backwards else 0
        else:
            self._search_index = (self._search_index + (-1 if backwards else 1)) % len(matches)
        position = matches[self._search_index]
        tw.see(position)
        tw.mark_set("insert", position)
        self.search_results_label.config(text=f"{self._search_index + 1}/{len(matches)}")

    # ---------------------------------------------------------------- 关闭

    def _on_close(self) -> None:
        if self._has_unsaved_changes() and not self._confirm_discard_changes():
            return
        root = self.viewer_window.nametowidget(".")
        self.viewer_window.destroy()
        if self.on_close_callback and self._data_was_saved:
            root.after(CLOSE_CALLBACK_DELAY_MS, self.on_close_callback)

    def _on_destroy(self, event: tk.Event) -> None:
        # 子控件销毁时也会触发 <Destroy>，只处理窗口本身
        if event.widget is self.viewer_window and _open_viewers.get(self._viewer_id) is self:
            del _open_viewers[self._viewer_id]
