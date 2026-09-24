"""屏幕右下角的 Toast 通知（存档变量变化提示等）

多个 Toast 自下而上堆叠；点击 Toast 会将其固定（不再自动消失），点 × 关闭。
淡入淡出只在 Windows 上生效（依赖窗口 -alpha 属性）。
"""

import ctypes
import logging
import platform
import tkinter as tk
from typing import List, Optional, Tuple

import customtkinter as ctk

from src.utils.styles import Colors, get_cjk_font

logger = logging.getLogger(__name__)

_USE_ALPHA = platform.system() == "Windows"

WIDTH = 280
SPACING = 10          # Toast 之间的垂直间距
MARGIN_RIGHT = 150    # 距工作区右边缘
MARGIN_LEFT = 12
MARGIN_BOTTOM = 12
MIN_WIDTH = 50
MIN_HEIGHT = 60
MAX_HEIGHT_RATIO = 0.8

# 按字符数估算换行后的高度（Text 控件在显示前无法可靠给出换行后的高度）
TEXT_PADDING = 30
CHAR_WIDTH = 7
LINE_HEIGHT = 18
MIN_CONTENT_HEIGHT = 30
TOP_BAR_HEIGHT = 19
BOTTOM_PADDING = 8

ALPHA = 0.85
FLASH_ALPHA = 0.95
FLASH_MS = 200
FRAME_MS = 16

CLOSE_COLOR = "#666666"
CLOSE_HOVER_COLOR = "#ff6b6b"
PIN_COLOR = "#888888"
GREEN = "#4ade80"
RED = "#f87171"


def _work_area(widget: tk.Misc) -> Tuple[int, int, int, int]:
    """可用工作区 (left, top, right, bottom)；Windows 上排除任务栏"""
    if _USE_ALPHA:
        try:
            from ctypes import wintypes
            rect = wintypes.RECT()
            SPI_GETWORKAREA = 0x0030
            if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
                return rect.left, rect.top, rect.right, rect.bottom
        except (OSError, AttributeError, ImportError) as e:
            logger.debug(f"Failed to get Windows work area: {e}")
    return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight()


class Toast:
    """通知窗口。外部会用到 window / message / message_text / update_message / reset_timer"""

    _active_toasts: List["Toast"] = []

    def __init__(self, root: ctk.CTk, message: str, duration: int = 10000,
                 fade_in: int = 200, fade_out: int = 200):
        """duration: 淡入完成后停留的毫秒数；fade_in / fade_out: 动画时长（毫秒）"""
        self.root = root
        self.message = message
        self.duration = duration
        self.fade_out = fade_out
        self.window_width = WIDTH
        self.window_height = 0
        self._pinned = False
        self._fading_out = False
        self._close_job: Optional[str] = None  # 停留结束后开始淡出
        self._fade_job: Optional[str] = None   # 渐变动画的下一帧

        self._build_ui()
        self._show_text(message)

        Toast._active_toasts.append(self)
        self._update_size()
        Toast._reposition_toasts()
        self._fade(0.0, ALPHA, fade_in, self._schedule_fade_out)

    # ---------- 界面 ----------

    def _build_ui(self) -> None:
        bg = Colors.TOAST_BG
        self.window = ctk.CTkToplevel(self.root)
        self.window.title("")
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(fg_color=bg)
        self._set_alpha(0.0)

        main = ctk.CTkFrame(self.window, fg_color=bg)
        main.pack(fill="both", expand=True)

        top_bar = ctk.CTkFrame(main, fg_color=bg, height=16)
        top_bar.pack(fill="x", padx=5, pady=(3, 0))
        top_bar.pack_propagate(False)

        self.close_btn = ctk.CTkLabel(top_bar, text="×", font=get_cjk_font(9), text_color=CLOSE_COLOR,
                                      fg_color=bg, cursor="hand2")
        self.close_btn.pack(side="right", padx=2)
        self.close_btn.bind("<Enter>", lambda e: self.close_btn.configure(text_color=CLOSE_HOVER_COLOR))
        self.close_btn.bind("<Leave>", lambda e: self.close_btn.configure(text_color=CLOSE_COLOR))
        self.close_btn.bind("<Button-1>", lambda e: self._close())

        # 固定后才显示
        self.pin_indicator = ctk.CTkLabel(top_bar, text="📌", font=get_cjk_font(8), text_color=PIN_COLOR,
                                          fg_color=bg)

        content = ctk.CTkFrame(main, fg_color=bg)
        content.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        self._textbox = ctk.CTkTextbox(content, font=get_cjk_font(9), text_color=Colors.TOAST_TEXT,
                                       fg_color=bg, border_width=0, corner_radius=0,
                                       activate_scrollbars=False)
        # 对外暴露底层 tk.Text：调用方可直接用 config / tag_configure(font=...) 定制内容
        # （CTkTextbox 不支持 config，也不允许给 tag 设置字体）
        self.message_text = self._textbox._textbox
        self.message_text.configure(wrap="word", state="disabled", cursor="arrow")
        self.message_text.tag_configure("green", foreground=GREEN)
        self.message_text.tag_configure("red", foreground=RED)
        self.message_text.tag_configure("default", foreground=Colors.TOAST_TEXT)
        self._textbox.pack(anchor="nw", fill="both", expand=True)

        for widget in (main, content, self.message_text, top_bar):
            widget.bind("<Button-1>", self._pin)

    def _show_text(self, message: str) -> None:
        """写入消息：行首 +/- 和 .append( / .remove( 分别标绿/标红"""
        text = self.message_text
        text.configure(state="normal")
        text.delete("1.0", "end")
        for i, line in enumerate(message.split("\n")):
            if i > 0:
                text.insert("end", "\n")
            stripped = line.strip()
            if stripped.startswith("+"):
                marker, tag = "+", "green"
            elif stripped.startswith("-"):
                marker, tag = "-", "red"
            elif ".append(" in line:
                marker, tag = ".append(", "green"
            elif ".remove(" in line:
                marker, tag = ".remove(", "red"
            else:
                text.insert("end", line, "default")
                continue
            before, _, after = line.partition(marker)
            text.insert("end", before, "default")
            text.insert("end", marker, tag)
            if after:
                text.insert("end", after, "default")
        text.configure(state="disabled")

    def _window_exists(self) -> bool:
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:
            return False

    # ---------- 尺寸与位置 ----------

    def _update_size(self) -> None:
        """按当前消息估算高度，并据此设置 Text 高度"""
        left, top, right, bottom = _work_area(self.window)
        self.window_width = min(WIDTH, max(MIN_WIDTH, right - left - MARGIN_LEFT - MARGIN_RIGHT))

        chars_per_line = max(1, max(MIN_WIDTH, self.window_width - TEXT_PADDING) // CHAR_WIDTH)
        display_lines = sum(max(1, -(-len(line) // chars_per_line)) for line in self.message.split("\n"))
        content_height = max(display_lines * LINE_HEIGHT, MIN_CONTENT_HEIGHT)

        height = content_height + TOP_BAR_HEIGHT + BOTTOM_PADDING
        self.window_height = max(min(height, int((bottom - top) * MAX_HEIGHT_RATIO)), MIN_HEIGHT)
        self._textbox.configure(height=max(1, content_height // LINE_HEIGHT))

    @staticmethod
    def _reposition_toasts() -> None:
        """移除已关闭的 Toast，其余从工作区右下角开始向上依次堆叠"""
        Toast._active_toasts = [t for t in Toast._active_toasts if t._window_exists()]
        y_offset = 0
        for toast in Toast._active_toasts:
            left, top, right, bottom = _work_area(toast.window)
            w, h = toast.window_width, toast.window_height
            x = max(left, min(right - w - MARGIN_RIGHT, right - w))
            y = max(top, min(bottom - h - y_offset - MARGIN_BOTTOM, bottom - h))
            try:
                toast.window.geometry(f"{w}x{h}+{x}+{y}")
            except tk.TclError as e:
                logger.debug(f"Failed to reposition toast: {e}")
            y_offset += h + SPACING

    # ---------- 外部接口 ----------

    def update_message(self, new_message: str) -> bool:
        """替换消息内容（用于合并同一变量的连续变化）"""
        if not self._window_exists():
            return False
        self.message = new_message
        self._show_text(new_message)
        self._update_size()
        Toast._reposition_toasts()
        return True

    def reset_timer(self) -> bool:
        """重新开始停留计时；正在淡出时恢复显示"""
        if not self._window_exists():
            return False
        if self._pinned:
            return True
        if self._fading_out:
            self._cancel(fade=True)
            self._fading_out = False
            self._set_alpha(ALPHA)
        self._schedule_fade_out()
        return True

    # ---------- 动画与关闭 ----------

    def _set_alpha(self, alpha: float) -> None:
        if _USE_ALPHA:
            try:
                self.window.attributes("-alpha", alpha)
            except tk.TclError as e:
                logger.debug(f"Failed to set alpha: {e}")

    def _cancel(self, close: bool = False, fade: bool = False) -> None:
        if close and self._close_job:
            self.window.after_cancel(self._close_job)
            self._close_job = None
        if fade and self._fade_job:
            self.window.after_cancel(self._fade_job)
            self._fade_job = None

    def _fade(self, start: float, end: float, duration: int, on_done, step: int = 0) -> None:
        """每 FRAME_MS 毫秒把透明度从 start 线性过渡到 end，结束后调用 on_done"""
        self._fade_job = None
        if not self._window_exists():
            return
        steps = max(1, duration // FRAME_MS)
        if step >= steps:
            self._set_alpha(end)
            on_done()
            return
        self._set_alpha(start + (end - start) * step / steps)
        self._fade_job = self.window.after(FRAME_MS, self._fade, start, end, duration, on_done, step + 1)

    def _schedule_fade_out(self) -> None:
        if self._pinned or not self._window_exists():
            return
        self._cancel(close=True)
        self._close_job = self.window.after(self.duration, self._start_fade_out)

    def _start_fade_out(self) -> None:
        self._close_job = None
        if self._pinned or not self._window_exists():
            return
        current = ALPHA
        if _USE_ALPHA:
            try:
                current = float(self.window.attributes("-alpha"))
            except tk.TclError:
                pass
        self._fading_out = True
        self._fade(current, 0.0, self.fade_out, self._close)

    def _pin(self, event=None) -> None:
        """点击 Toast：固定显示并闪一下作为反馈"""
        if self._pinned:
            return
        self._pinned = True
        self._fading_out = False
        self._cancel(close=True, fade=True)
        self.pin_indicator.pack(side="left", padx=2)
        if _USE_ALPHA:
            self._set_alpha(FLASH_ALPHA)
            self._fade_job = self.window.after(FLASH_MS, self._set_alpha, ALPHA)

    def _close(self) -> None:
        if not self._window_exists():
            return
        self._cancel(close=True, fade=True)
        self.window.destroy()
        if self in Toast._active_toasts:
            Toast._active_toasts.remove(self)
        Toast._reposition_toasts()
