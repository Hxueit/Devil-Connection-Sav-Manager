"""加载中文字动画："加载中..." -> "加载中." -> "加载中.." 循环"""

import tkinter as tk
from typing import Callable, List, Optional

DOTS = ["...", ".", ".."]


class LoadingAnimationController:
    def __init__(self, root_widget: tk.Misc, interval_ms: int = 500):
        self.root = root_widget
        self.interval_ms = interval_ms
        self.translate_func: Optional[Callable[[str], str]] = None
        self._labels: List[tk.Widget] = []
        self._job: Optional[str] = None
        self._running = False
        self._dots_index = 0
        self._base_text = "Loading"

    def set_translate_func(self, translate_func: Optional[Callable[[str], str]]) -> None:
        self.translate_func = translate_func

    def start(self, target_labels: List[tk.Widget]) -> None:
        """在这些标签上开始动画（已在运行时忽略）"""
        if self._running:
            return
        self._running = True
        self._labels = [label for label in target_labels if label is not None]
        self._dots_index = 0
        # 每次启动时重新取翻译，以反映语言切换；去掉译文末尾自带的点
        self._base_text = self.translate_func("loading").rstrip(".") if self.translate_func else "Loading"
        self._update_frame()

    def _update_frame(self) -> None:
        self._job = None
        if not self._running:
            return
        text = self._base_text + DOTS[self._dots_index]
        alive = []
        for label in self._labels:
            try:
                if label.winfo_exists():
                    label.configure(text=text)
                    alive.append(label)
            except tk.TclError:
                pass
        self._labels = alive
        if not alive:
            self.stop()
            return
        self._dots_index = (self._dots_index + 1) % len(DOTS)
        self._job = self.root.after(self.interval_ms, self._update_frame)

    def stop(self) -> None:
        self._running = False
        if self._job:
            try:
                self.root.after_cancel(self._job)
            except (tk.TclError, ValueError):
                pass
            self._job = None
        self._labels = []
