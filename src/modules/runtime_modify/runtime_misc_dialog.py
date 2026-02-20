"""运行时修改 - 杂项弹窗。"""

from typing import Any, Callable, Dict

import customtkinter as ctk
import tkinter as tk

from src.modules.others.utils import center_window
from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import set_window_icon


class RuntimeMiscDialog(ctk.CTkToplevel):
    """承载运行时修改的杂项功能入口。"""

    def __init__(
        self,
        parent_window: ctk.CTk,
        translations: Dict[str, Dict[str, str]],
        current_language: str,
        on_force_fast_forward_clicked: Callable[[], None],
        on_cache_clean_clicked: Callable[[], None],
        is_feature_enabled: Callable[[], bool]
    ) -> None:
        super().__init__(parent_window)

        self.translations = translations
        self.current_language = current_language
        self._on_force_fast_forward_clicked = on_force_fast_forward_clicked
        self._on_cache_clean_clicked = on_cache_clean_clicked
        self._is_feature_enabled = is_feature_enabled

        self.force_fast_forward_button: ctk.CTkButton
        self.force_fast_forward_hint_label: ctk.CTkLabel
        self.cache_clean_button: ctk.CTkButton

        self._configure_window()
        self._init_ui()
        self.refresh_button_states()
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        self.after(50, lambda: set_window_icon(self))
        self.after(200, lambda: set_window_icon(self))

    def t(self, key: str, **kwargs: Any) -> str:
        text = self.translations.get(self.current_language, {}).get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError):
                return text
        return text

    def _configure_window(self) -> None:
        self.title(self.t("runtime_modify_misc_dialog_title"))
        self.geometry("460x250")
        self.minsize(420, 220)
        self.transient(self.master)
        center_window(self)
        self.after(0, self._raise_to_front)

    def _raise_to_front(self) -> None:
        try:
            if not self.winfo_exists():
                return
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass

    def _init_ui(self) -> None:
        main_container = ctk.CTkFrame(self, fg_color=Colors.WHITE)
        main_container.pack(fill="both", expand=True, padx=12, pady=12)

        list_frame = ctk.CTkFrame(main_container, fg_color=Colors.WHITE)
        list_frame.pack(fill="both", expand=True)

        fast_forward_frame = ctk.CTkFrame(list_frame, fg_color=Colors.WHITE)
        fast_forward_frame.pack(fill="x", pady=(0, 12))

        self.force_fast_forward_button = ctk.CTkButton(
            fast_forward_frame,
            text=self.t("runtime_modify_force_fast_forward"),
            command=self._on_force_fast_forward_clicked,
            corner_radius=8,
            fg_color=Colors.WHITE,
            hover_color=Colors.LIGHT_GRAY,
            border_width=1,
            border_color=Colors.GRAY,
            text_color=Colors.TEXT_PRIMARY,
            font=get_cjk_font(11),
            height=32
        )
        self.force_fast_forward_button.pack(fill="x")

        self.force_fast_forward_hint_label = ctk.CTkLabel(
            fast_forward_frame,
            text=self.t("runtime_modify_force_fast_forward_hint"),
            font=get_cjk_font(9),
            text_color=Colors.TEXT_SECONDARY,
            anchor="w"
        )
        self.force_fast_forward_hint_label.pack(anchor="w", padx=(8, 0), pady=(2, 0))

        self.cache_clean_button = ctk.CTkButton(
            list_frame,
            text=self.t("cache_clean_button"),
            command=self._on_cache_clean_clicked,
            corner_radius=8,
            fg_color=Colors.WHITE,
            hover_color=Colors.LIGHT_GRAY,
            border_width=1,
            border_color=Colors.GRAY,
            text_color=Colors.TEXT_PRIMARY,
            font=get_cjk_font(11),
            height=32
        )
        self.cache_clean_button.pack(fill="x")

    def refresh_button_states(self) -> None:
        if not self.winfo_exists():
            return
        state = "normal" if self._is_feature_enabled() else "disabled"
        self.force_fast_forward_button.configure(state=state)
        self.cache_clean_button.configure(state=state)

    def update_language(self, language: str) -> None:
        if not isinstance(language, str) or not language:
            return
        if language not in self.translations:
            return

        self.current_language = language
        self.title(self.t("runtime_modify_misc_dialog_title"))
        self.force_fast_forward_button.configure(text=self.t("runtime_modify_force_fast_forward"))
        self.force_fast_forward_hint_label.configure(text=self.t("runtime_modify_force_fast_forward_hint"))
        self.cache_clean_button.configure(text=self.t("cache_clean_button"))

    def _on_window_close(self) -> None:
        self.destroy()
