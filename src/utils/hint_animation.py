"""提示动画：用户尝试禁用的操作时，让"开启修改"复选框变色并左右抖动"""

import time
import tkinter as tk
from tkinter import ttk

from src.utils.styles import Colors

SHAKE_OFFSETS = [4, -4, 3, -3, 2, -2, 1, -1, 0]  # 逐渐减弱的 padx 偏移
SHAKE_STEP_MS = 25
COLOR_RESTORE_MS = 300
DEBOUNCE_MS = 500
WRAPPER_PADX = 5  # wrapper 原本的左右边距


class HintAnimation:
    """让复选框变成橙色并左右抖动一下

    抖动是通过改变 wrapper（包着复选框、用 pack 布局的 tk.Frame）的 padx 实现的。
    """

    def __init__(self, root: tk.Misc, target_widget: ttk.Checkbutton, wrapper: tk.Frame,
                 normal_style: str, hint_style: str) -> None:
        self.root = root
        self.target_widget = target_widget
        self.wrapper = wrapper
        self.normal_style = normal_style
        self.hint_style = hint_style
        self._last_trigger = 0.0

    def trigger(self) -> None:
        """播放动画；DEBOUNCE_MS 内重复触发会被忽略"""
        now = time.monotonic() * 1000
        if now - self._last_trigger < DEBOUNCE_MS:
            return
        self._last_trigger = now

        ttk.Style(self.root).configure(self.hint_style, background=self.wrapper.cget("bg"),
                                       foreground=Colors.TEXT_WARNING_ORANGE)
        self.target_widget.config(style=self.hint_style)
        self._shake(0)

    def _shake(self, step: int) -> None:
        if not self.wrapper.winfo_exists():  # 窗口已在动画期间关闭
            return
        if step < len(SHAKE_OFFSETS):
            self.wrapper.pack_configure(padx=WRAPPER_PADX + SHAKE_OFFSETS[step])
            self.root.after(SHAKE_STEP_MS, self._shake, step + 1)
            return
        self.wrapper.pack_configure(padx=WRAPPER_PADX)
        self.root.after(COLOR_RESTORE_MS, self._restore_style)

    def _restore_style(self) -> None:
        if self.target_widget.winfo_exists():
            self.target_widget.config(style=self.normal_style)
