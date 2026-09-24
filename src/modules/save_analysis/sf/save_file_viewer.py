"""存档查看/编辑窗口

以 JSON 文本显示存档内容，支持折叠大字段、搜索、复制、编辑后保存。
窗口本身不知道数据存在哪里：调用方传入 load() 和 save(data) 两个函数。
- sf 存档分析页的「查看存档文件」：读写 DevilConnection_sf.sav
- tyrano 存档槽 / 自动存档：读写对应的存档槽或文件
- 运行时修改页（runtime=True）：通过 CDP 读写游戏内存中的 sf 或 kag.stat
"""

import copy
import json
import logging
import re
import tkinter as tk
from dataclasses import dataclass
from tkinter import Scrollbar, ttk
from typing import Any, Callable, Dict, Iterable, List, Optional

from src.utils.background import run_in_background
from src.utils.hint_animation import HintAnimation
from src.utils.styles import Colors, get_cjk_font, get_mono_font
from src.utils.ui_utils import (
    askyesno_relative,
    restore_and_activate_window,
    set_window_icon,
    showerror_relative,
    showinfo_relative,
    showwarning_relative,
)

from .viewer_json import format_display_data, restore_collapsed_fields

logger = logging.getLogger(__name__)

# 「开启修改」复选框的 ttk 样式名（ttk 样式是全局的，名字不能和截图页的重复）
CHECKBOX_STYLE_NORMAL = "SfViewer.TCheckbutton"
CHECKBOX_STYLE_HINT = "SfViewerHint.TCheckbutton"

__all__ = ["SaveFileViewer", "ViewerTexts", "DEFAULT_SF_COLLAPSED_FIELDS"]

DEFAULT_SF_COLLAPSED_FIELDS: List[str] = ["record", "_tap_effect", "initialVars"]

WINDOW_SIZE = "1200x900"
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
class ViewerTexts:
    """随用途变化的文字（都是翻译键）；默认值用于保存到文件"""
    save_button: str = "save_file"
    confirm_save: str = "save_confirm_text"
    save_success: str = "save_success"
    save_failed: str = "save_file_failed"      # 带 {error}
    load_failed: Optional[str] = None          # 带 {error}；None 时直接显示错误信息


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
        viewer = cls(**kwargs)
        _open_viewers[viewer_id] = viewer
        viewer.viewer_window.bind("<Destroy>", lambda event: viewer._on_destroy(event, viewer_id))
        return viewer

    def __init__(
        self,
        parent: tk.Misc,
        t: Callable[..., str],
        data: Dict[str, Any],
        title: str,
        load: Callable[[], Optional[Dict[str, Any]]],
        save: Callable[[Dict[str, Any]], Any],
        texts: Optional[ViewerTexts] = None,
        collapsed_fields: Iterable[str] = (),
        show_collapse_toggle: bool = False,
        edit_checkbox: bool = False,
        runtime: bool = False,
        find_outside_changes: Optional[Callable[[Dict[str, Any]], List[str]]] = None,
        on_saved: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        """
        Args:
            parent: 任意所属控件，用来找到主窗口
            data: 初始显示的数据
            title: 窗口标题（已翻译的文字）
            load: 「刷新」和「启用编辑」时重新读取数据；出错时抛出异常，返回 None 表示数据已不存在（保持现状）
            save: 保存编辑后的数据；出错时抛出异常（返回 False 也视为失败）
            collapsed_fields: 默认折叠的字段路径（支持 "stat.map_label" 这样的嵌套路径）
            show_collapse_toggle: 显示「取消折叠」复选框和说明文字
            edit_checkbox: True 时默认只读，勾选「启用编辑」才能修改；False 时直接可编辑
            runtime: load/save 要和运行中的游戏通信：在后台线程执行，保存后再从游戏读回一次
            find_outside_changes: 保存前检查数据在打开后是否被别处改过，参数是打开时的数据，
                返回差异说明（空列表表示没变）；有差异时让用户确认
            on_saved: 保存成功后调用，参数为保存的数据
        """
        self.t = t
        self.load = load
        self.save = save
        self.texts = texts or ViewerTexts()
        self.collapsed_fields = list(collapsed_fields)
        self.runtime = runtime
        self.find_outside_changes = find_outside_changes
        self.on_saved = on_saved
        self._set_data(data)
        self._baseline = ""          # 最近一次渲染的文本，用来判断是否有未保存的修改
        self._line_count = 0
        self._search_term = ""
        self._search_index = -1
        self._hint_animation: Optional[HintAnimation] = None

        self.viewer_window = tk.Toplevel(parent.nametowidget("."))
        self.viewer_window.title(title)
        self.viewer_window.geometry(WINDOW_SIZE)
        self.viewer_window.configure(bg=Colors.MODAL_BG)
        set_window_icon(self.viewer_window)
        self.viewer_window.protocol("WM_DELETE_WINDOW", self._on_close)

        self.disable_collapse_var = tk.BooleanVar(value=False)
        self.enable_edit_var = tk.BooleanVar(value=not edit_checkbox)
        self._build_ui(show_collapse_toggle, edit_checkbox)
        self._render()

    # ---------------------------------------------------------------- 界面

    def _build_ui(self, show_collapse_toggle: bool, edit_checkbox: bool) -> None:
        self._setup_styles()
        main_frame = tk.Frame(self.viewer_window, bg=Colors.MODAL_BG)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)

        if show_collapse_toggle:
            hint_frame = tk.Frame(main_frame, bg=Colors.MODAL_BG)
            hint_frame.pack(fill="x", pady=(0, 10))
            ttk.Label(hint_frame, text=self.t("viewer_hint_text"), font=get_cjk_font(9), wraplength=850,
                      justify="left", style="Modal.TLabel").pack(anchor="w", padx=5)

        toolbar = tk.Frame(main_frame, bg=Colors.MODAL_BG)
        toolbar.pack(fill="x", pady=(0, 5))
        self._build_toolbar(toolbar, show_collapse_toggle, edit_checkbox)
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

    def _build_toolbar(self, toolbar: tk.Frame, show_collapse_toggle: bool, edit_checkbox: bool) -> None:
        if show_collapse_toggle:
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

        if edit_checkbox:
            wrapper = tk.Frame(toolbar_right, bg=Colors.MODAL_BG)
            wrapper.pack(side="right", padx=5)
            checkbox = ttk.Checkbutton(wrapper, text=self.t("enable_edit"), variable=self.enable_edit_var,
                                       command=self._on_edit_toggled, style=CHECKBOX_STYLE_NORMAL)
            checkbox.pack()
            self._hint_animation = HintAnimation(self.viewer_window, checkbox, wrapper,
                                                 CHECKBOX_STYLE_NORMAL, CHECKBOX_STYLE_HINT)

        self.save_button = ttk.Button(toolbar_right, text=self.t(self.texts.save_button),
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

    def _set_data(self, data: Dict[str, Any]) -> None:
        self.save_data = data
        # 保存前用它检测数据在打开之后是否被别处（游戏）改过
        self.original_save_data = copy.deepcopy(data)

    def _render(self) -> None:
        """按当前数据和折叠设置重新生成文本；之后的修改都相对于这次渲染的内容判断"""
        scroll_position = self.text_widget.yview()[0]
        self._clear_search()
        if self.disable_collapse_var.get():
            content = json.dumps(self.save_data, ensure_ascii=False, indent=2)
        else:
            content = format_display_data(self.save_data, self.collapsed_fields, self.t("collapsed_field_text"))
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
        def back_to_read_only() -> None:
            self.enable_edit_var.set(False)
            self._apply_edit_state()

        # 重新读取，避免在过期的数据上编辑；读不到时退回只读
        self._reload(on_failed=back_to_read_only)

    def _on_refresh_clicked(self) -> None:
        if self._has_unsaved_changes() and not self._confirm_discard_changes():
            return
        self._reload()

    # ---------------------------------------------------------------- 读取 / 保存

    def _call(self, work: Callable[[], Any], on_done: Callable[[Any, Optional[BaseException]], None]) -> None:
        """执行 load/save 等调用方传入的函数，结果交给 on_done(结果, 异常)

        运行时模式要等游戏回复，放到后台线程；读写文件很快，直接执行。
        """
        if self.runtime:
            run_in_background(self.viewer_window, work, on_done)
            return
        try:
            result = work()
        except Exception as e:
            logger.error("Save viewer call failed: %s", e, exc_info=True)
            on_done(None, e)
        else:
            on_done(result, None)

    def _show_load_error(self, error: BaseException) -> None:
        if isinstance(error, FileNotFoundError):
            message = self.t("save_file_not_found")
        elif self.texts.load_failed:
            message = self.t(self.texts.load_failed, error=str(error))
        else:
            message = str(error)
        showerror_relative(self.viewer_window, self.t("error"), message)

    def _reload(self, on_failed: Optional[Callable[[], None]] = None) -> None:
        """重新 load() 并显示；失败（或数据已不存在）时调用 on_failed"""
        def done(data: Optional[Dict[str, Any]], error: Optional[BaseException]) -> None:
            if error is not None:
                self._show_load_error(error)
            if data is None:
                if on_failed is not None:
                    on_failed()
                return
            self._set_data(data)
            self._render()

        self._call(self.load, done)

    def _on_save_clicked(self) -> None:
        try:
            edited_data = json.loads(self._get_text())
        except json.JSONDecodeError as e:
            showerror_relative(self.viewer_window, self.t("json_format_error"),
                               self.t("json_format_error_detail", error=str(e)))
            return
        if not self.disable_collapse_var.get() and isinstance(edited_data, dict):
            restore_collapsed_fields(edited_data, self.save_data, self.collapsed_fields,
                                     self.t("collapsed_field_text"))
        if not askyesno_relative(self.viewer_window, self.t("save_confirm_title"), self.t(self.texts.confirm_save)):
            return
        # 取消或失败时保留用户的编辑内容（仍视为未保存）
        if self.find_outside_changes is None:
            self._save(edited_data)
            return

        original = self.original_save_data

        def on_checked(changes: Optional[List[str]], error: Optional[BaseException]) -> None:
            if error is not None:
                self._show_save_error(error)
                return
            if changes and not askyesno_relative(
                    self.viewer_window, self.t("warning"),
                    self.t("runtime_modify_sf_changes_detected", changes="\n".join(changes))):
                return
            self._save(edited_data)

        self._call(lambda: self.find_outside_changes(original), on_checked)

    def _show_save_error(self, error: BaseException) -> None:
        showerror_relative(self.viewer_window, self.t("error"), self.t(self.texts.save_failed, error=str(error)))

    def _save(self, edited_data: Dict[str, Any]) -> None:
        def done(result: Any, error: Optional[BaseException]) -> None:
            if error is None and result is False:
                error = RuntimeError(self.t("viewer_save_failed_reason"))
            if error is not None:
                self._show_save_error(error)
                return
            self._set_data(edited_data)
            showinfo_relative(self.viewer_window, self.t("success"), self.t(self.texts.save_success))
            self._render()
            if self.on_saved is not None:
                try:
                    self.on_saved(edited_data)
                except Exception as e:
                    logger.error("on_saved callback failed: %s", e, exc_info=True)
            if self.runtime:
                self.viewer_window.after(REFRESH_AFTER_INJECT_DELAY_MS, reread)

        def reread() -> None:
            # 读回游戏处理后的数据；用户已经开始新的编辑时不覆盖
            def on_reread(data: Optional[Dict[str, Any]], error: Optional[BaseException]) -> None:
                if error is not None:
                    logger.warning("Failed to refresh after inject: %s", error)
                elif data is not None and not self._has_unsaved_changes():
                    self._set_data(data)
                    self._render()

            self._call(self.load, on_reread)

        self._call(lambda: self.save(edited_data), done)

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
        self.viewer_window.destroy()

    def _on_destroy(self, event: tk.Event, viewer_id: str) -> None:
        # 子控件销毁时也会触发 <Destroy>，只处理窗口本身
        if event.widget is self.viewer_window and _open_viewers.get(viewer_id) is self:
            del _open_viewers[viewer_id]
