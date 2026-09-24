"""画廊预览窗口

按游戏内画廊的排列方式分页显示截图：每页 3 行 × 4 列，
按列填充（先填满第一列的 3 张再到下一列），第 2、3 列之间是左右半页的分隔线。
"""

from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

from src.modules.screenshot.screenshot_manager import ScreenshotManager, load_resized_image
from src.utils.background import run_in_background
from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import (
    restore_and_activate_window, set_window_icon, showerror_relative, showwarning_relative, widget_alive,
)

ROWS = 3
COLS = 4
PER_PAGE = ROWS * COLS
# 大小档位：(图片尺寸, 窗口尺寸)
SIZE_PRESETS = [
    ((150, 112), '800x600'),
    ((175, 131), '900x675'),
    ((200, 150), '1000x750'),
    ((250, 187), '1200x900'),
    ((300, 225), '1400x1050'),
]
DEFAULT_SIZE_MODE = 2
MAX_CACHED_IMAGES = 5 * PER_PAGE  # 缓存最近几页的缩略图，翻回去时不用重新解码

# 缓存键：(文件路径, 修改时间)，图片被替换后键就变了，旧缓存自然失效
CacheKey = Tuple[str, int]


class GalleryPreview:
    """画廊预览窗口（同一时间只有一个）"""

    def __init__(self, root: tk.Misc, screenshot_manager: ScreenshotManager, t) -> None:
        self.root = root
        self.manager = screenshot_manager
        self.t = t
        self.window: Optional[tk.Toplevel] = None
        self.page = 1
        self.size_mode = DEFAULT_SIZE_MODE
        self.image_ids: List[str] = []
        self._cache: "OrderedDict[CacheKey, ImageTk.PhotoImage]" = OrderedDict()
        self._page_photos: List[ImageTk.PhotoImage] = []  # 当前页显示的图片，保持引用以免被回收
        self._page_token = 0  # 每次重建页面加一，用来丢弃旧页面迟到的加载结果
        self.page_area: Optional[tk.Frame] = None
        self.page_frame: Optional[tk.Frame] = None

    @property
    def image_size(self) -> Tuple[int, int]:
        return SIZE_PRESETS[self.size_mode][0]

    @property
    def total_pages(self) -> int:
        return max(1, (len(self.image_ids) + PER_PAGE - 1) // PER_PAGE)

    # ---------- 窗口 ----------

    def show(self) -> None:
        """打开画廊窗口；已经打开时把它提到前面"""
        if not self.manager.storage_dir or not self.manager.ids_data:
            showerror_relative(self.root, self.t("error"), self.t("select_dir_hint"))
            return
        if widget_alive(self.window) and restore_and_activate_window(self.window):
            return

        self.page = 1
        self.size_mode = DEFAULT_SIZE_MODE
        self.window = window = tk.Toplevel(self.root)
        window.title(self.t("gallery_preview"))
        window.geometry(SIZE_PRESETS[self.size_mode][1])
        set_window_icon(window)
        window.protocol("WM_DELETE_WINDOW", self._close)

        container = tk.Frame(window, bg=Colors.WHITE)
        container.pack(fill="both", expand=True)

        nav_frame = tk.Frame(container, bg=Colors.WHITE)
        nav_frame.pack(side="bottom", fill="x", pady=10)
        self.page_area = tk.Frame(container, bg=Colors.WHITE)
        self.page_area.pack(fill="both", expand=True, padx=10, pady=10)
        self.page_frame = None
        self._build_navigation(nav_frame)

        size_frame = tk.Frame(container, bg=Colors.WHITE)
        size_frame.place(relx=1.0, rely=0.0, anchor="ne", x=-5, y=5)
        ttk.Style().configure("Small.TButton", font=get_cjk_font(8), padding=[1, 2])
        for text, step in (("-", -1), ("+", 1)):
            ttk.Button(size_frame, text=text, width=2, style="Small.TButton",
                       command=lambda s=step: self._change_size(s)).pack(side="left", padx=0)

        self.refresh()

    def _build_navigation(self, parent: tk.Frame) -> None:
        center = tk.Frame(parent, bg=Colors.WHITE)
        center.pack(anchor="center")

        self.prev_button = ttk.Button(center, text=self.t("prev_page"), command=lambda: self._go_to(self.page - 1))
        self.prev_button.pack(side="left", padx=5)
        self.page_label = tk.Label(center, text="1/1", font=get_cjk_font(12), bg=Colors.WHITE)
        self.page_label.pack(side="left", padx=10)
        self.next_button = ttk.Button(center, text=self.t("next_page"), command=lambda: self._go_to(self.page + 1))
        self.next_button.pack(side="left", padx=5)

        jump_frame = tk.Frame(center, bg=Colors.WHITE)
        jump_frame.pack(side="left", padx=20)
        tk.Label(jump_frame, text=self.t("jump_to_page"), font=get_cjk_font(10),
                 bg=Colors.WHITE).pack(side="left", padx=5)
        self.jump_entry = tk.Entry(jump_frame, width=10)
        self.jump_entry.pack(side="left", padx=5)
        self.jump_entry.bind('<Return>', lambda e: self._jump())
        ttk.Button(jump_frame, text=self.t("jump"), command=self._jump).pack(side="left", padx=5)

    def _close(self) -> None:
        self.window.destroy()
        self.window = None
        self._cache.clear()
        self._page_photos.clear()

    def _go_to(self, page: int) -> None:
        if 1 <= page <= self.total_pages:
            self.page = page
            self._build_page()

    def _jump(self) -> None:
        try:
            page = int(self.jump_entry.get())
        except ValueError:
            showwarning_relative(self.window, self.t("warning"), self.t("invalid_page_input"))
            return
        if 1 <= page <= self.total_pages:
            self._go_to(page)
            self.jump_entry.delete(0, tk.END)
        else:
            showwarning_relative(self.window, self.t("warning"),
                                 self.t("invalid_page_number", min=1, max=self.total_pages))

    def _change_size(self, step: int) -> None:
        new_mode = self.size_mode + step
        if not 0 <= new_mode < len(SIZE_PRESETS):
            return
        self.size_mode = new_mode
        self.window.geometry(SIZE_PRESETS[new_mode][1])
        self._cache.clear()
        self._build_page()

    def refresh(self) -> None:
        """截图列表变化后重建当前页"""
        if not widget_alive(self.window):
            return
        self.image_ids = [item['id'] for item in self.manager.ids_data]
        self.page = min(self.page, self.total_pages)
        self._build_page()

    # ---------- 页面 ----------

    def _image_path(self, screenshot_id: str) -> Optional[Path]:
        # 优先用缩略图，没有时用主图
        return self.manager.file_path(screenshot_id, thumb=True) or self.manager.file_path(screenshot_id)

    def _build_page(self) -> None:
        self._page_token += 1
        self._page_photos.clear()
        if self.page_frame is not None:
            self.page_frame.destroy()
        self.page_frame = tk.Frame(self.page_area, bg=Colors.WHITE)
        self.page_frame.place(x=0, y=0, relwidth=1, relheight=1)

        width, height = self.image_size
        first = (self.page - 1) * PER_PAGE
        to_load: List[Tuple[tk.Frame, tk.Label, str, CacheKey]] = []  # 缓存里没有、需要后台读取的格子
        for row in range(ROWS):
            row_frame = tk.Frame(self.page_frame, bg=Colors.WHITE)
            row_frame.pack(side="top", pady=5)
            for col in range(COLS):
                cell = tk.Frame(row_frame, bg=Colors.WHITE)
                cell.pack(side="left", padx=5)
                if col == 1:
                    tk.Frame(row_frame, width=3, bg="gray", relief="sunken").pack(side="left", fill="y", padx=5)

                index = first + row + col * ROWS
                screenshot_id = self.image_ids[index] if index < len(self.image_ids) else None
                key = self._cache_key(self._image_path(screenshot_id)) if screenshot_id else None
                if key in self._cache:
                    self._cache.move_to_end(key)
                    self._show_image(cell, screenshot_id, self._cache[key])
                    continue

                text, font = ((self.t("loading"), get_cjk_font(10)) if screenshot_id
                              else (self.t("not_available"), get_cjk_font(14, "bold")))
                box = tk.Frame(cell, bg="lightgray", width=width, height=height)
                box.pack()
                box.pack_propagate(False)
                label = tk.Label(box, text=text, bg="lightgray", fg="gray", font=font)
                label.place(relx=0.5, rely=0.5, anchor="center")
                tk.Label(cell, text="", bg=Colors.WHITE, font=get_cjk_font(8)).pack()
                if key:
                    to_load.append((cell, label, screenshot_id, key))
                elif screenshot_id:
                    label.config(text=self.t("preview_failed"), fg="red")
        self._update_navigation()
        if to_load:
            self._load_page_images(to_load)

    @staticmethod
    def _cache_key(path: Optional[Path]) -> Optional[CacheKey]:
        try:
            return (str(path), path.stat().st_mtime_ns) if path else None
        except OSError:
            return None

    def _update_navigation(self) -> None:
        self.page_label.config(text=f"{self.page}/{self.total_pages}")
        self.prev_button.config(state="normal" if self.page > 1 else "disabled")
        self.next_button.config(state="normal" if self.page < self.total_pages else "disabled")

    def _load_page_images(self, to_load: List[Tuple[tk.Frame, tk.Label, str, CacheKey]]) -> None:
        """在一个后台任务里读取整页缺少的缩略图，读完后一起显示"""
        token, size = self._page_token, self.image_size
        keys = [key for _, _, _, key in to_load]

        def work() -> Dict[CacheKey, Optional[Image.Image]]:
            return {key: load_resized_image(Path(key[0]), size) for key in keys}

        def done(images: Optional[Dict[CacheKey, Optional[Image.Image]]], error: Optional[BaseException]) -> None:
            if token != self._page_token or not widget_alive(self.window):
                return  # 页面已经换了
            images = images or {}
            for cell, label, screenshot_id, key in to_load:
                image = images.get(key)
                if image is None:
                    label.config(text=self.t("preview_failed"), fg="red")
                    continue
                photo = ImageTk.PhotoImage(image)
                self._cache[key] = photo
                for widget in cell.winfo_children():
                    widget.destroy()
                self._show_image(cell, screenshot_id, photo)
            while len(self._cache) > MAX_CACHED_IMAGES:
                self._cache.popitem(last=False)

        run_in_background(self.window, work, done)

    def _show_image(self, cell: tk.Frame, screenshot_id: str, photo: ImageTk.PhotoImage) -> None:
        self._page_photos.append(photo)
        tk.Label(cell, image=photo, bg=Colors.WHITE, text=screenshot_id, compound="top",
                 font=get_cjk_font(8)).pack()
