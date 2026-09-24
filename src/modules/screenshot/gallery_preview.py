"""画廊预览窗口

按游戏内画廊的排列方式分页显示截图：每页 3 行 × 4 列，
按列填充（先填满第一列的 3 张再到下一列），第 2、3 列之间是左右半页的分隔线。
"""

import logging
from collections import OrderedDict
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Tuple

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

from src.modules.screenshot.screenshot_manager import ScreenshotManager, read_image_file
from src.utils.background import run_in_background
from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import restore_and_activate_window, set_window_icon, showerror_relative, showwarning_relative

logger = logging.getLogger(__name__)

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


def load_thumbnail(path: Path, size: Tuple[int, int]) -> Optional[Image.Image]:
    """读取并缩放一张截图（在后台线程执行）"""
    data = read_image_file(path)
    if data is None:
        return None
    with Image.open(BytesIO(data)) as img:
        return img.resize(size, Image.Resampling.BILINEAR)


class GalleryPreview:
    """画廊预览窗口（同一时间只有一个）"""

    def __init__(self, root: tk.Misc, screenshot_manager: ScreenshotManager, t_func) -> None:
        self.root = root
        self.manager = screenshot_manager
        self.t = t_func
        self.window: Optional[tk.Toplevel] = None
        self.page = 1
        self.size_mode = DEFAULT_SIZE_MODE
        self.image_ids: List[str] = []
        self._cache: "OrderedDict[Tuple[str, int], ImageTk.PhotoImage]" = OrderedDict()
        self._page_token = 0  # 每次重建页面加一，用来丢弃旧页面迟到的加载结果
        self.page_area: Optional[tk.Frame] = None
        self.page_frame: Optional[tk.Frame] = None

    @property
    def image_size(self) -> Tuple[int, int]:
        return SIZE_PRESETS[self.size_mode][0]

    @property
    def total_pages(self) -> int:
        return max(1, (len(self.image_ids) + PER_PAGE - 1) // PER_PAGE)

    def _is_open(self) -> bool:
        try:
            return self.window is not None and bool(self.window.winfo_exists())
        except tk.TclError:
            return False

    # ---------- 窗口 ----------

    def show(self) -> None:
        """打开画廊窗口；已经打开时把它提到前面"""
        if not self.manager.storage_dir or not self.manager.ids_data:
            showerror_relative(self.root, self.t("error"), self.t("select_dir_hint"))
            return
        if self._is_open() and restore_and_activate_window(self.window):
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
                                 self.t("invalid_page_number").format(min=1, max=self.total_pages))

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
        if not self._is_open():
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
        if self.page_frame is not None:
            self.page_frame.destroy()
        self.page_frame = tk.Frame(self.page_area, bg=Colors.WHITE)
        self.page_frame.place(x=0, y=0, relwidth=1, relheight=1)

        width, height = self.image_size
        first = (self.page - 1) * PER_PAGE
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
                path = self._image_path(screenshot_id) if screenshot_id else None
                # 缓存键带上文件修改时间，图片被替换后自然失效
                key = self._cache_key(path)
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
                    self._load_async(cell, label, screenshot_id, key)
                elif screenshot_id:
                    label.config(text=self.t("preview_failed"), fg="red")
        self._update_navigation()

    @staticmethod
    def _cache_key(path: Optional[Path]) -> Optional[Tuple[str, int]]:
        try:
            return (str(path), path.stat().st_mtime_ns) if path else None
        except OSError:
            return None

    def _update_navigation(self) -> None:
        self.page_label.config(text=f"{self.page}/{self.total_pages}")
        self.prev_button.config(state="normal" if self.page > 1 else "disabled")
        self.next_button.config(state="normal" if self.page < self.total_pages else "disabled")

    def _load_async(self, cell: tk.Frame, label: tk.Label, screenshot_id: str, key: Tuple[str, int]) -> None:
        token, size = self._page_token, self.image_size

        def done(image: Optional[Image.Image], error: Optional[BaseException]) -> None:
            if token != self._page_token or not self._is_open():
                return  # 页面已经换了
            if image is None:
                label.config(text=self.t("preview_failed"), fg="red")
                return
            photo = ImageTk.PhotoImage(image)
            self._cache[key] = photo
            while len(self._cache) > MAX_CACHED_IMAGES:
                self._cache.popitem(last=False)
            for widget in cell.winfo_children():
                widget.destroy()
            self._show_image(cell, screenshot_id, photo)

        run_in_background(self.window, lambda: load_thumbnail(Path(key[0]), size), done)

    def _show_image(self, cell: tk.Frame, screenshot_id: str, photo: ImageTk.PhotoImage) -> None:
        label = tk.Label(cell, image=photo, bg=Colors.WHITE, text=screenshot_id, compound="top",
                         font=get_cjk_font(8))
        label.image = photo  # 保持引用，否则图片会被回收
        label.pack()
