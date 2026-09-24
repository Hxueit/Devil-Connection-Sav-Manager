"""运行时修改页的弹出窗口：公共基类和「杂项」窗口"""
from typing import Callable

import customtkinter as ctk
import tkinter as tk

from src.utils.styles import Colors, get_cjk_font, white_button
from src.utils.ui_utils import center_window, create_dialog, restore_and_activate_window, widget_alive


def set_textbox_text(textbox: ctk.CTkTextbox, text: str) -> None:
    """替换只读文本框的全部内容"""
    textbox.configure(state="normal")
    textbox.delete("1.0", "end")
    textbox.insert("1.0", text)
    textbox.configure(state="disabled")


class RuntimeDialog:
    """运行时修改页弹窗的公共部分：一个非模态的 CTk 窗口（self.window），居中显示

    t 是标签页的翻译函数，语言切换后调用 update_language() 刷新文字。
    """

    def __init__(self, parent: tk.Misc, t: Callable[..., str], title_key: str, size: str, min_size: tuple) -> None:
        self.t = t
        self._title_key = title_key
        self.window = create_dialog(parent, t(title_key), size, modal=False, use_ctk=True)
        self.window.minsize(*min_size)
        center_window(self.window)
        # CTkToplevel 刚创建时可能被主窗口挡住，显示出来后再提到最前
        self.window.after(0, self._raise_to_front)

    def _raise_to_front(self) -> None:
        if self.is_open():
            self.window.lift()
            self.window.focus_force()

    def is_open(self) -> bool:
        return widget_alive(self.window)

    def show(self) -> None:
        """把已打开的窗口还原并提到最前"""
        restore_and_activate_window(self.window)

    def close(self) -> None:
        if self.is_open():
            self.window.destroy()

    def update_language(self) -> None:
        self.window.title(self.t(self._title_key))


class RuntimeMiscDialog(RuntimeDialog):
    """杂项功能入口：强制快进、缓存清理"""

    def __init__(
        self,
        parent: tk.Misc,
        t: Callable[..., str],
        on_force_fast_forward: Callable[[], None],
        on_cache_clean: Callable[[], None],
    ) -> None:
        super().__init__(parent, t, "runtime_modify_misc_dialog_title", "460x250", (420, 220))

        outer = ctk.CTkFrame(self.window, fg_color=Colors.WHITE)
        outer.pack(fill="both", expand=True, padx=12, pady=12)
        container = ctk.CTkFrame(outer, fg_color=Colors.WHITE)
        container.pack(fill="both", expand=True)

        fast_forward_frame = ctk.CTkFrame(container, fg_color=Colors.WHITE)
        fast_forward_frame.pack(fill="x", pady=(0, 12))

        self.force_fast_forward_button = white_button(
            fast_forward_frame, t("runtime_modify_force_fast_forward"), on_force_fast_forward,
            font=get_cjk_font(11), height=32,
        )
        self.force_fast_forward_button.pack(fill="x")

        self.force_fast_forward_hint_label = ctk.CTkLabel(
            fast_forward_frame,
            text=t("runtime_modify_force_fast_forward_hint"),
            font=get_cjk_font(9),
            text_color=Colors.TEXT_SECONDARY,
            anchor="w",
        )
        self.force_fast_forward_hint_label.pack(anchor="w", padx=(8, 0), pady=(2, 0))

        self.cache_clean_button = white_button(
            container, t("cache_clean_button"), on_cache_clean, font=get_cjk_font(11), height=32,
        )
        self.cache_clean_button.pack(fill="x")

    def set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.force_fast_forward_button.configure(state=state)
        self.cache_clean_button.configure(state=state)

    def update_language(self) -> None:
        super().update_language()
        self.force_fast_forward_button.configure(text=self.t("runtime_modify_force_fast_forward"))
        self.force_fast_forward_hint_label.configure(text=self.t("runtime_modify_force_fast_forward_hint"))
        self.cache_clean_button.configure(text=self.t("cache_clean_button"))
