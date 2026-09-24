"""运行时修改页的弹出窗口：公共基类和「杂项」窗口"""
from typing import Callable

import customtkinter as ctk
import tkinter as tk

from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import center_window, set_window_icon


def create_standard_button(parent: tk.Misc, text: str, command: Callable[[], None], **kwargs) -> ctk.CTkButton:
    """白底灰边的标准按钮（与「检查更新」相同样式）"""
    options = dict(
        corner_radius=8,
        fg_color=Colors.WHITE,
        hover_color=Colors.LIGHT_GRAY,
        border_width=1,
        border_color=Colors.GRAY,
        text_color=Colors.TEXT_PRIMARY,
        font=get_cjk_font(10),
    )
    options.update(kwargs)
    return ctk.CTkButton(parent, text=text, command=command, **options)


class RuntimeDialog(ctk.CTkToplevel):
    """运行时修改页弹窗的公共部分：标题、尺寸、居中、置顶、图标

    t 是标签页的翻译函数，语言切换后调用 update_language() 刷新文字。
    """

    def __init__(self, parent: tk.Misc, t: Callable[..., str], title_key: str, size: str, min_size: tuple) -> None:
        super().__init__(parent)
        self.t = t
        self._title_key = title_key
        self.title(t(title_key))
        self.geometry(size)
        self.minsize(*min_size)
        self.transient(parent)
        center_window(self)
        self.after(0, self._raise_to_front)
        # CTkToplevel 创建后会自己改一次图标，所以延迟设置两次
        self.after(50, lambda: set_window_icon(self))
        self.after(200, lambda: set_window_icon(self))

    def _raise_to_front(self) -> None:
        try:
            if self.winfo_exists():
                self.lift()
                self.focus_force()
        except tk.TclError:
            pass

    def update_language(self) -> None:
        self.title(self.t(self._title_key))


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

        outer = ctk.CTkFrame(self, fg_color=Colors.WHITE)
        outer.pack(fill="both", expand=True, padx=12, pady=12)
        container = ctk.CTkFrame(outer, fg_color=Colors.WHITE)
        container.pack(fill="both", expand=True)

        fast_forward_frame = ctk.CTkFrame(container, fg_color=Colors.WHITE)
        fast_forward_frame.pack(fill="x", pady=(0, 12))

        self.force_fast_forward_button = create_standard_button(
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

        self.cache_clean_button = create_standard_button(
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
