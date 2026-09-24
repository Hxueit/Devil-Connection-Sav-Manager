"""提示动画：用户尝试禁用的操作时，让"开启修改"复选框变色并左右抖动"""

import time
import tkinter as tk
from tkinter import ttk

from src.utils.styles import Colors

SHAKE_OFFSETS = [4, -4, 3, -3, 2, -2, 1, -1, 0]  # 逐渐减弱的 padx 偏移
SHAKE_STEP_MS = 25
COLOR_RESTORE_MS = 300
DEBOUNCE_MS = 500


class HintAnimation:
    """让复选框变成橙色并左右抖动一下

    抖动是通过改变 wrapper（包着复选框、用 pack 布局的 Frame）的 padx 实现的，
    padx 是 wrapper 原本的左右边距。
    """

    def __init__(self, root: tk.Misc, target_widget: ttk.Checkbutton, wrapper: tk.Frame,
                 normal_style: str, hint_style: str, padx: int = 5) -> None:
        self.root = root
        self.target_widget = target_widget
        self.wrapper = wrapper
        self.normal_style = normal_style
        self.hint_style = hint_style
        self.padx = padx
        self._last_trigger = 0.0

    def trigger(self) -> None:
        """播放动画；DEBOUNCE_MS 内重复触发会被忽略"""
        now = time.monotonic() * 1000
        if now - self._last_trigger < DEBOUNCE_MS:
            return
        self._last_trigger = now

        ttk.Style(self.root).configure(self.hint_style, background=self._parent_bg(),
                                       foreground=Colors.TEXT_WARNING_ORANGE)
        self.target_widget.config(style=self.hint_style)
        self._shake(self.padx, 0)

    def _parent_bg(self) -> str:
        try:
            return self.target_widget.master.cget("bg") or Colors.LIGHT_GRAY
        except (tk.TclError, AttributeError):
            return Colors.LIGHT_GRAY

    def _shake(self, padx: int, step: int) -> None:
        if not self.wrapper.winfo_exists():  # 窗口已在动画期间关闭
            return
        if step < len(SHAKE_OFFSETS):
            self.wrapper.pack_configure(padx=max(0, padx + SHAKE_OFFSETS[step]))
            self.root.after(SHAKE_STEP_MS, self._shake, padx, step + 1)
            return
        self.wrapper.pack_configure(padx=padx)
        self.root.after(COLOR_RESTORE_MS, lambda: self.target_widget.config(style=self.normal_style))
