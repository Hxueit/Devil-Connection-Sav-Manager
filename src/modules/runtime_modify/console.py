"""DevTools 控制台窗口：向运行中的游戏发送 JavaScript 并显示结果"""
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import customtkinter as ctk
import tkinter as tk

from src.modules.runtime_modify.dialogs import RuntimeDialog, create_standard_button
from src.modules.runtime_modify.service import evaluate
from src.modules.save_analysis.tyrano.constants import TYRANO_QUICK_SAVE_FILENAME
from src.utils.background import run_in_background
from src.utils.sav_io import read_sav
from src.utils.styles import Colors, get_cjk_font


MAX_HISTORY = 100

# 快捷指令：(翻译键, JS 命令)
SHORTCUT_COMMANDS = [
    ("runtime_modify_console_cmd_display_save", "TYRANO.kag.menu.displaySavePage()"),
    ("runtime_modify_console_cmd_display_load", "TYRANO.kag.menu.displayLoadPage()"),
    ("runtime_modify_console_cmd_display_log", "TYRANO.kag.menu.displayLog()"),
    ("runtime_modify_console_cmd_set_quick_save", "TYRANO.kag.menu.setQuickSave()"),
    ("runtime_modify_console_cmd_load_quick_save", "TYRANO.kag.menu.loadQuickSave()"),
    ("runtime_modify_console_cmd_take_photo",
     "TYRANO.kag.ftag.startTag('sleepgame', { storage: 'photo.ks', next: false })"),
]


def _load_quick_save_slot(storage_dir: Optional[str]) -> Optional[Dict[str, Any]]:
    """读取快速存档，返回其中的存档槽数据；没有或无法读取时返回 None"""
    if not storage_dir:
        return None
    try:
        save = read_sav(Path(storage_dir) / TYRANO_QUICK_SAVE_FILENAME)
    except (OSError, ValueError):
        return None
    if not isinstance(save, dict):
        return None
    slots = save.get("data")
    if isinstance(slots, list) and slots and isinstance(slots[0], dict):
        return slots[0]
    if "stat" in save or "save_date" in save:
        return save
    return None


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def describe_quick_save(slot: Optional[Dict[str, Any]], t: Callable[..., str]) -> str:
    """把快速存档槽概括成一行：第几天 · ●●○ · 保存时间 · 副标题"""
    if not slot:
        return t("runtime_modify_console_no_quick_save")

    stat = slot.get("stat")
    f = stat.get("f") if isinstance(stat, dict) else None
    if not isinstance(f, dict):
        f = {}

    # 尾声阶段用 day_epilogue 计天（非 0 时有效），否则用 day
    epilogue_day = _to_int(f.get("day_epilogue"))
    is_epilogue = bool(epilogue_day)
    day = epilogue_day if is_epilogue else _to_int(f.get("day"))

    parts = []
    if day is not None:
        if is_epilogue:
            parts.append(t("tyrano_epilogue_day_label").format(day=day))
        else:
            parts.append(t("tyrano_day_label").format(day=day))
            # finished 每天占 3 格，记录当天完成了哪些事件
            finished = f.get("finished")
            done = len(finished[day * 3:day * 3 + 3]) if isinstance(finished, list) and day >= 0 else 0
            parts.append("".join("●" if i < done else "○" for i in range(3)))
    if slot.get("save_date") is not None:
        parts.append(str(slot["save_date"]))
    if slot.get("subtitle") and slot.get("subtitleText"):
        parts.append(str(slot["subtitleText"]))

    return " · ".join(parts) if parts else t("runtime_modify_console_no_quick_save")


def format_result(result: Any) -> str:
    """按浏览器控制台的习惯显示结果：字符串带引号，对象缩进显示"""
    if result is None:
        return "undefined"
    if isinstance(result, str):
        return json.dumps(result)
    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False, indent=2)
    return str(result)


class DevToolsConsoleWindow(RuntimeDialog):
    """交互式 JS 控制台：Enter 发送，Shift+Enter 换行，上下键翻历史，Ctrl+L 清屏"""

    def __init__(
        self,
        parent: tk.Misc,
        t: Callable[..., str],
        get_ws_url: Callable[[], Optional[str]],
        storage_dir: Optional[str],
        on_close: Callable[[], None],
    ) -> None:
        super().__init__(parent, t, "runtime_modify_console_title", "800x600", (600, 400))
        self.get_ws_url = get_ws_url
        self.storage_dir = storage_dir
        self.on_close = on_close

        self._history: List[str] = []
        self._history_index = -1        # -1 表示没有在翻历史
        self._draft = ""                # 开始翻历史前输入框里的内容
        self._is_executing = False
        self._shortcut_popup: Optional[ctk.CTkToplevel] = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

    def _build_ui(self) -> None:
        container = ctk.CTkFrame(self, fg_color=Colors.WHITE)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        self.output_textbox = ctk.CTkTextbox(
            container,
            font=get_cjk_font(10),
            fg_color=Colors.LIGHT_GRAY,
            text_color=Colors.TEXT_PRIMARY,
            border_color=Colors.GRAY,
            border_width=1,
            corner_radius=8,
            wrap="word",
        )
        self.output_textbox.pack(fill="both", expand=True, pady=(0, 10))
        self.output_textbox.configure(state="disabled")
        self.output_textbox.bind("<Button-1>", self._on_output_clicked)
        self.output_textbox.tag_config("cmd", foreground="#6B7280")
        self.output_textbox.tag_config("result", foreground="#059669")
        self.output_textbox.tag_config("error", foreground="#DC2626")
        self.output_textbox.tag_config("undefined", foreground="#9CA3AF")

        self.disabled_hint_label = ctk.CTkLabel(
            container,
            text=self.t("runtime_modify_console_disabled_hint"),
            font=get_cjk_font(9),
            text_color=Colors.TEXT_SECONDARY,
            wraplength=600,
        )

        self.input_container = ctk.CTkFrame(container, fg_color=Colors.WHITE)
        self.input_container.pack(fill="x")

        self.input_entry = ctk.CTkTextbox(
            self.input_container,
            font=get_cjk_font(10),
            fg_color=Colors.WHITE,
            text_color=Colors.TEXT_PRIMARY,
            border_color=Colors.GRAY,
            border_width=1,
            corner_radius=8,
            wrap="word",
            height=35,
        )
        self.input_entry.pack(side="left", fill="both", expand=True, padx=(0, 5))
        # 按键要绑定在 CTkTextbox 内部的 tk.Text 上，才能用 "break" 阻止默认行为
        self._tk_input: tk.Text = self.input_entry._textbox
        self._tk_input.bind("<Return>", self._on_return_key)
        self._tk_input.bind("<Shift-Return>", lambda e: None)   # 保持默认的换行
        self._tk_input.bind("<Up>", self._on_up_key)
        self._tk_input.bind("<Down>", self._on_down_key)
        self.bind("<Control-l>", lambda e: self._clear_output())

        buttons = ctk.CTkFrame(self.input_container, fg_color=Colors.WHITE)
        buttons.pack(side="right")
        self.send_button = create_standard_button(
            buttons, self.t("runtime_modify_console_send_button"), self._on_send_clicked, width=80)
        self.send_button.pack(side="left", padx=(0, 5))
        self.shortcut_button = create_standard_button(
            buttons, self.t("runtime_modify_console_shortcut_button"), self._toggle_shortcut_popup, width=80)
        self.shortcut_button.pack(side="left")

    # ------------------------------------------------------------ 输入与历史

    def _on_output_clicked(self, _event: tk.Event) -> Optional[str]:
        # 输出区为空时点击直接跳到输入框；有内容时保留默认行为以便选择复制
        if not self.output_textbox.get("1.0", "end-1c").strip():
            self._focus_input()
            return "break"
        return None

    def _focus_input(self) -> None:
        try:
            self.focus_force()
            self._tk_input.focus_force()
            self._tk_input.mark_set(tk.INSERT, "end-1c")
            self._tk_input.see(tk.INSERT)
        except tk.TclError:
            pass

    def _get_input(self) -> str:
        return self.input_entry.get("1.0", "end-1c")

    def _set_input(self, text: str) -> None:
        self._focus_input()
        self.input_entry.delete("1.0", "end")
        self.input_entry.insert("1.0", text)
        self.input_entry.see("end")

    def _on_return_key(self, _event: tk.Event) -> str:
        self._on_send_clicked()
        return "break"

    def _on_up_key(self, _event: tk.Event) -> Optional[str]:
        # 光标在第一行时才翻历史，否则让光标正常上移
        if self._tk_input.index(tk.INSERT).split(".")[0] != "1":
            return None
        if not self._history:
            return "break"
        if self._history_index == -1:
            self._draft = self._get_input()
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        else:
            return "break"
        self._set_input(self._history[self._history_index])
        return "break"

    def _on_down_key(self, _event: tk.Event) -> Optional[str]:
        # 光标在最后一行时才翻历史
        if self._tk_input.index(tk.INSERT).split(".")[0] != self._tk_input.index("end-1c").split(".")[0]:
            return None
        if self._history_index == -1:
            return "break"
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._set_input(self._history[self._history_index])
        else:
            self._history_index = -1
            self._set_input(self._draft)
            self._draft = ""
        return "break"

    def _add_to_history(self, command: str) -> None:
        if not self._history or self._history[-1] != command:
            self._history.append(command)
            del self._history[:-MAX_HISTORY]
            self._draft = ""
        self._history_index = -1

    # ------------------------------------------------------------ 执行

    def _on_send_clicked(self) -> None:
        if self._is_executing:
            return
        command = self._get_input().strip()
        if not command:
            return
        self._add_to_history(command)
        self.input_entry.delete("1.0", "end")

        self._append_output(self.t("runtime_modify_console_command_prefix") + command, "cmd")
        ws_url = self.get_ws_url()
        if not ws_url:
            self._append_output(
                self.t("runtime_modify_console_error_prefix") + self.t("runtime_modify_console_no_connection"),
                "error",
            )
            return

        self._is_executing = True
        self.send_button.configure(state="disabled")
        run_in_background(self, lambda: evaluate(ws_url, command), self._on_command_done)

    def _on_command_done(self, outcome: Any, exc: Optional[BaseException]) -> None:
        self._is_executing = False
        self.send_button.configure(state="normal")
        result, error = outcome if exc is None else (None, str(exc))
        if error is not None:
            self._append_output(self.t("runtime_modify_console_error_prefix") + error, "error")
        else:
            self._append_output(
                self.t("runtime_modify_console_result_prefix") + format_result(result),
                "undefined" if result is None else "result",
            )

    def _append_output(self, text: str, tag: str) -> None:
        self.output_textbox.configure(state="normal")
        start = self.output_textbox.index("end-1c")
        self.output_textbox.insert("end", text + "\n")
        self.output_textbox.tag_add(tag, start, "end-1c")
        self.output_textbox.configure(state="disabled")
        self.output_textbox.see("end")

    def _clear_output(self) -> None:
        self.output_textbox.configure(state="normal")
        self.output_textbox.delete("1.0", "end")
        self.output_textbox.configure(state="disabled")

    def _on_window_close(self) -> None:
        self._destroy_shortcut_popup()
        self.on_close()
        self.destroy()

    def set_enabled(self, enabled: bool) -> None:
        """游戏未连接时禁用输入并显示提示"""
        state = "normal" if enabled else "disabled"
        self.input_entry.configure(state=state)
        self.send_button.configure(state=state)
        self.shortcut_button.configure(state=state)
        if enabled:
            self.disabled_hint_label.pack_forget()
        else:
            self._destroy_shortcut_popup()
            self.disabled_hint_label.pack(anchor="w", pady=(0, 10), before=self.input_container)

    def update_language(self) -> None:
        super().update_language()
        self.send_button.configure(text=self.t("runtime_modify_console_send_button"))
        self.shortcut_button.configure(text=self.t("runtime_modify_console_shortcut_button"))
        self.disabled_hint_label.configure(text=self.t("runtime_modify_console_disabled_hint"))
        self._destroy_shortcut_popup()

    # ------------------------------------------------------------ 快捷指令弹层

    def _toggle_shortcut_popup(self) -> None:
        if self._shortcut_popup is not None:
            self._destroy_shortcut_popup()
        else:
            self._create_shortcut_popup()

    def _destroy_shortcut_popup(self) -> None:
        popup, self._shortcut_popup = self._shortcut_popup, None
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass

    def _create_shortcut_popup(self) -> None:
        popup = ctk.CTkToplevel(self)
        popup.overrideredirect(True)
        popup.transient(self)
        popup.attributes("-topmost", True)
        popup.configure(fg_color=Colors.WHITE)

        panel = ctk.CTkFrame(popup, fg_color=Colors.WHITE, border_width=1, border_color=Colors.GRAY, corner_radius=10)
        panel.pack(fill="both", expand=True)

        for key, command in SHORTCUT_COMMANDS:
            row = ctk.CTkButton(
                panel,
                text=self.t(key),
                anchor="w",
                width=260,
                height=34,
                corner_radius=7,
                fg_color=Colors.WHITE,
                hover_color=Colors.LIGHT_GRAY,
                border_width=0,
                text_color=Colors.TEXT_PRIMARY,
                font=get_cjk_font(10),
            )
            row.pack(fill="x", padx=6, pady=(6, 0))
            row.bind("<ButtonRelease-1>", lambda event, cmd=command: self._on_shortcut_selected(event, cmd))

            if key == "runtime_modify_console_cmd_set_quick_save":
                # 在「快速存档」下面显示当前快速存档的内容，方便判断是否要覆盖
                info = describe_quick_save(_load_quick_save_slot(self.storage_dir), self.t)
                ctk.CTkLabel(
                    panel, text=info, anchor="w", justify="left",
                    font=get_cjk_font(9), text_color=Colors.TEXT_SECONDARY,
                ).pack(fill="x", padx=12, pady=(4, 2))
                ctk.CTkFrame(panel, fg_color=Colors.GRAY, height=1, corner_radius=0).pack(fill="x", padx=8, pady=(2, 0))

        for key, pady in (("runtime_modify_console_shortcut_hint", (6, 0)),
                          ("runtime_modify_console_shortcut_hint_clear", (2, 8))):
            ctk.CTkLabel(
                panel, text=self.t(key), anchor="w", justify="left",
                font=get_cjk_font(8), text_color=Colors.TEXT_DISABLED,
            ).pack(fill="x", padx=12, pady=pady)

        # 放在按钮下方，超出屏幕时向左/向上挪
        self.update_idletasks()
        width = max(260, panel.winfo_reqwidth())
        height = panel.winfo_reqheight()
        button_x = self.shortcut_button.winfo_rootx()
        button_y = self.shortcut_button.winfo_rooty()
        margin = 8
        x, y = button_x, button_y + self.shortcut_button.winfo_height() + 6
        if x + width > self.winfo_screenwidth() - margin:
            x = max(margin, self.winfo_screenwidth() - width - margin)
        if y + height > self.winfo_screenheight() - margin:
            y = max(margin, button_y - height - 6)
        popup.geometry(f"{width}x{height}+{x}+{y}")
        popup.focus_force()

        popup.bind("<Escape>", lambda _e: self._destroy_shortcut_popup())
        popup.bind("<FocusOut>", lambda _e: self.after(10, self._destroy_shortcut_popup))
        self._shortcut_popup = popup

    def _on_shortcut_selected(self, event: tk.Event, command: str) -> str:
        """填入快捷指令；按住 Shift 点击则直接执行"""
        execute = bool(event.state & 0x0001)
        self._destroy_shortcut_popup()
        # 等弹层销毁、焦点回到主窗口后再填入
        self.after(1, lambda: self._apply_shortcut(command, execute))
        return "break"

    def _apply_shortcut(self, command: str, execute: bool) -> None:
        self._set_input(command)
        self.after_idle(self._focus_input)
        self.after(30, self._focus_input)
        if execute:
            self.after(0, self._on_send_clicked)
