"""其他模块共用的小工具"""
import tkinter as tk


def center_window(window: tk.Toplevel) -> None:
    """把窗口移到屏幕中央（窗口尺寸需已确定）"""
    window.update_idletasks()
    width, height = window.winfo_width(), window.winfo_height()
    if width <= 0 or height <= 0:
        return
    x = max(0, (window.winfo_screenwidth() - width) // 2)
    y = max(0, (window.winfo_screenheight() - height) // 2)
    window.geometry(f"+{x}+{y}")
