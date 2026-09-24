"""Tyrano 存档标签页：像游戏里一样分页显示存档槽，并提供导入、删除、重排序、自动存档编辑等入口"""

import json
import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import Any, Callable, List, Optional, Tuple

import customtkinter as ctk

from src.modules.save_analysis.tyrano.analyzer import TyranoAnalyzer, describe_slot
from src.modules.save_analysis.tyrano.auto_saves_dialog import TyranoAutoSavesDialog
from src.modules.save_analysis.tyrano.constants import TYRANO_SAVES_PER_PAGE
from src.modules.save_analysis.tyrano.delete_dialog import TyranoDeleteDialog
from src.modules.save_analysis.tyrano.image_utils import (
    ImageCache,
    create_placeholder_image,
    slot_thumbnail,
    thumbnail_size,
)
from src.modules.save_analysis.tyrano.reorder_dialog import TyranoReorderDialog
from src.modules.save_analysis.tyrano.save_slot import (
    PageNavBar,
    TyranoSaveSlot,
    build_slot_grid,
    slot_size_for_area,
)
from src.utils.background import run_in_background
from src.utils.sav_io import decode_sav
from src.utils.styles import Colors, get_cjk_font, white_button
from src.utils.ui_utils import (
    askyesno_relative, showerror_relative, showinfo_relative, showwarning_relative, widget_alive,
)

logger = logging.getLogger(__name__)

RESIZE_DEBOUNCE_MS = 200
PAGE_SWITCH_DEBOUNCE_MS = 150
DEFAULT_SLOT_SIZE = (300, 150)


class TyranoSaveViewer:
    """Tyrano 存档标签页

    读取存档文件和生成缩略图都在后台线程进行（存档里嵌着 base64 图片，文件可能很大），
    期间用「加载中」遮罩盖住存档区域。翻页时复用同一组 6 个卡片，缩略图全部生成后
    再一次性更新文字和图片，避免看到逐个刷新的过程。
    """

    def __init__(
        self,
        parent: ctk.CTkFrame,
        root: tk.Misc,
        analyzer: TyranoAnalyzer,
        t: Callable[..., str],
    ) -> None:
        self.parent = parent
        self.root_window = root
        self.analyzer = analyzer
        self.t = t
        self.image_cache = ImageCache()
        self.slot_widgets: List[TyranoSaveSlot] = []

        self._load_id = 0              # 每次加载页面图片时加一，用来丢弃过期的后台结果
        self._destroyed = False
        self._first_page_shown = False  # 第一页显示完成后才开始响应窗口大小变化
        self._prefetching = False
        self._reading_file = False      # 正在后台读取存档文件，这时不能撤掉「加载中」遮罩
        self._page_timer: Optional[str] = None
        self._resize_timer: Optional[str] = None
        self._last_parent_size: Optional[Tuple[int, int]] = None
        self._loading_overlay: Optional[ctk.CTkFrame] = None
        self._loading_label: Optional[ctk.CTkLabel] = None
        self._texts: List[Tuple[Any, str]] = []   # (控件, 翻译键)，切换语言时更新

        self._create_ui()
        if analyzer.save_data is None:
            self.refresh()   # 调用方还没读取存档：在后台读取
        else:
            self.refresh_display()
        self._refresh_when_mapped(attempts_left=5)

    # ------------------------------------------------------------------
    # 界面
    # ------------------------------------------------------------------

    def _create_ui(self) -> None:
        main = ctk.CTkFrame(self.parent, fg_color=Colors.WHITE)
        main.pack(fill="both", expand=True, padx=10, pady=10)
        main.pack_propagate(False)

        self.slots_frame = ctk.CTkFrame(main, fg_color=Colors.WHITE)
        self.slots_frame.pack(fill="both", expand=True)
        self.slots_frame.pack_propagate(False)

        self._nav_frame = nav = ctk.CTkFrame(main, fg_color=Colors.WHITE)
        nav.pack(side="bottom", fill="x", pady=10)
        self.page_bar = PageNavBar(nav, self.t, self._go_to_page)

        self.import_button = self._button(nav, "tyrano_import_button", self._on_import_click, "left")
        self.refresh_button = self._button(nav, "refresh", self.refresh, "right")
        self.delete_button = self._button(nav, "tyrano_delete_button", lambda: TyranoDeleteDialog(self), "right")
        self.reorder_button = self._button(nav, "tyrano_reorder_button", lambda: TyranoReorderDialog(self), "right")
        self.auto_saves_button = self._button(nav, "tyrano_auto_saves_button",
                                              lambda: TyranoAutoSavesDialog(self), "right")

    def _button(self, parent: tk.Misc, text_key: str, command: Callable[[], Any], side: str) -> ctk.CTkButton:
        button = white_button(parent, self.t(text_key), command, width=60, height=30)
        button.pack(side=side, padx=5)
        self._texts.append((button, text_key))
        return button

    def update_language(self) -> None:
        """切换语言后更新文字"""
        for widget, key in self._texts:
            widget.configure(text=self.t(key))
        self.page_bar.update_texts()
        if self._loading_label is not None:
            self._loading_label.configure(text=self.t("loading"))
        self.refresh_display()

    def _show_loading_overlay(self) -> None:
        if self._loading_overlay is None:
            self._loading_overlay = ctk.CTkFrame(self.slots_frame, fg_color=Colors.WHITE)
            self._loading_label = ctk.CTkLabel(self._loading_overlay, text="", font=get_cjk_font(12),
                                               text_color=Colors.TEXT_SECONDARY, fg_color="transparent")
            self._loading_label.place(relx=0.5, rely=0.5, anchor="center")
        self._loading_label.configure(text=self.t("loading"))
        self._loading_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._loading_overlay.lift()

    def _hide_loading_overlay(self) -> None:
        if self._loading_overlay is not None:
            self._loading_overlay.place_forget()

    # ------------------------------------------------------------------
    # 显示当前页
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """在后台重新读取存档文件，读完后刷新显示（回到第一页）"""
        analyzer = self.analyzer
        data_before = analyzer.save_data
        self._reading_file = True
        self._show_loading_overlay()

        def done(save_data: Optional[dict], error: Optional[BaseException]) -> None:
            self._reading_file = False
            if self._destroyed:
                return
            # 读取期间如果导入、删除等操作已经改了数据（它们写文件前会重新读磁盘），
            # 内存里的数据比这次读到的还新，不能用读到的旧数据覆盖
            if error is None and analyzer.save_data is data_before:
                analyzer.set_save_data(save_data)
            self.refresh_display()

        run_in_background(self.parent, analyzer.read_file, done)

    def refresh_display(self) -> None:
        """按内存中的数据重新显示当前页

        修改存档后调用这个就行：analyzer 修改成功后内存和文件是一致的，不用重新读文件。
        """
        if self._destroyed or not widget_alive(self.slots_frame):
            return
        if not self.slot_widgets:
            self.slot_widgets = [TyranoSaveSlot(cell, self) for cell in build_slot_grid(self.slots_frame)]

        page_slots = self.analyzer.get_current_page_slots()
        first_index = max(self.analyzer.current_page - 1, 0) * TYRANO_SAVES_PER_PAGE
        for pos, card in enumerate(self.slot_widgets):
            card.set_slot(page_slots[pos] if pos < len(page_slots) else None, first_index + pos)
        self._load_page_images()
        self.page_bar.show(self.analyzer.current_page, self.analyzer.total_pages)

    def _load_page_images(self) -> None:
        """在后台生成当前页的缩略图，完成后更新卡片"""
        self._load_id += 1
        load_id = self._load_id
        if not self._first_page_shown or self.parent.winfo_width() <= 1:
            # 首次显示时控件还没有真实尺寸，先完成布局计算
            self.parent.update_idletasks()
        slot_size = self._slot_size()
        self._show_loading_overlay()

        image_datas = [(card.slot_data or {}).get("img_data") for card in self.slot_widgets]
        no_image_text = self.t("tyrano_no_imgdata")
        failed_text = self.t("tyrano_image_decode_failed")
        cache = self.image_cache

        def work() -> list:
            return [slot_thumbnail(data, slot_size, cache, no_image_text, failed_text) for data in image_datas]

        def done(thumbnails: Optional[list], error: Optional[BaseException]) -> None:
            if self._destroyed or load_id != self._load_id:
                return   # 已经翻到别的页了
            if error is not None:
                thumbnails = [create_placeholder_image(thumbnail_size(slot_size), failed_text)] * len(image_datas)
            diameter = self._circle_diameter()
            for card, thumbnail in zip(self.slot_widgets, thumbnails):
                card.show_info(diameter)
                card.set_image(thumbnail)
            if not self._reading_file:
                self._hide_loading_overlay()
            if not self._first_page_shown:
                self._first_page_shown = True
                self.parent.bind("<Configure>", self._on_window_resize)
            self._prefetch_adjacent_pages(slot_size)

        run_in_background(self.parent, work, done)

    def _slot_size(self) -> Tuple[int, int]:
        """单个存档槽卡片的大小（用来决定缩略图尺寸）"""
        width, height = self.slots_frame.winfo_width(), self.slots_frame.winfo_height()
        if width <= 1 or height <= 1:
            # 存档区域还没布局：用外层容器减去导航栏来估算
            master = self.slots_frame.master
            nav_height = self._nav_frame.winfo_height()
            if nav_height <= 1:
                nav_height = self._nav_frame.winfo_reqheight()
            width, height = master.winfo_width(), master.winfo_height() - nav_height - 20
        return slot_size_for_area(width, height) or DEFAULT_SLOT_SIZE

    def _circle_diameter(self) -> int:
        """完成状态圆点的直径，随卡片宽度在 12~18 之间变化"""
        width = self.slot_widgets[0].text_frame.winfo_width()
        return max(12, min(18, int(width * 0.10))) if width > 0 else 15

    def _prefetch_adjacent_pages(self, slot_size: Tuple[int, int]) -> None:
        """在后台为前后两页生成缩略图，让翻页更快"""
        page, total = self.analyzer.current_page, self.analyzer.total_pages
        if self._prefetching or page < 1 or total <= 1:
            return
        image_datas = []
        for p in (page - 1, page + 1):
            if 1 <= p <= total:
                page_slots = self.analyzer.save_slots[(p - 1) * TYRANO_SAVES_PER_PAGE:p * TYRANO_SAVES_PER_PAGE]
                image_datas += [slot.get("img_data") for slot in page_slots if slot.get("img_data")]
        if not image_datas:
            return

        cache = self.image_cache
        self._prefetching = True

        def work() -> None:
            for data in image_datas:
                cache.get_thumbnail(data, slot_size)

        def done(_result: Any, _error: Optional[BaseException]) -> None:
            self._prefetching = False

        run_in_background(self.parent, work, done)

    def _refresh_when_mapped(self, attempts_left: int) -> None:
        """创建时标签页可能还没显示出来（尺寸为 1x1），等它显示后按真实尺寸再刷新一次"""
        def check() -> None:
            if self._destroyed or not widget_alive(self.slots_frame):
                return
            frame = self.slots_frame
            if frame.winfo_ismapped() and frame.winfo_width() > 1 and frame.winfo_height() > 1:
                self.refresh_display()
            elif attempts_left > 1:
                self._refresh_when_mapped(attempts_left - 1)

        self.parent.after(120, check)

    def _on_window_resize(self, event: Optional[tk.Event] = None) -> None:
        size = (self.parent.winfo_width(), self.parent.winfo_height())
        if size == self._last_parent_size:
            return
        self._last_parent_size = size
        self._cancel_timer(self._resize_timer)
        self._resize_timer = self.parent.after(RESIZE_DEBOUNCE_MS, self.refresh_display)

    def _cancel_timer(self, timer_id: Optional[str]) -> None:
        if timer_id:
            try:
                self.parent.after_cancel(timer_id)
            except (tk.TclError, ValueError):
                pass

    def cleanup(self) -> None:
        """标签页被销毁前调用：停止定时器，丢弃后台结果，释放缓存"""
        self._destroyed = True
        self._load_id += 1
        self._cancel_timer(self._page_timer)
        self._cancel_timer(self._resize_timer)
        self.image_cache.clear()
        if widget_alive(self._loading_overlay):
            self._loading_overlay.destroy()
        self._loading_overlay = self._loading_label = None

    # ------------------------------------------------------------------
    # 翻页
    # ------------------------------------------------------------------

    def _go_to_page(self, page: int) -> None:
        """翻页；连续点击翻页时只刷新最后一次"""
        self.analyzer.set_page(page)
        self.page_bar.show(self.analyzer.current_page, self.analyzer.total_pages)
        self._cancel_timer(self._page_timer)
        self._page_timer = self.parent.after(PAGE_SWITCH_DEBOUNCE_MS, self.refresh_display)

    # ------------------------------------------------------------------
    # 导入（「导出」按钮在每个存档槽卡片上）
    # ------------------------------------------------------------------

    def _on_import_click(self) -> None:
        t = self.t
        file_path = filedialog.askopenfilename(
            parent=self.root_window,
            title=t("tyrano_import_dialog_title"),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not file_path:
            return

        try:
            content = Path(file_path).read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            showwarning_relative(self.root_window, t("warning"), t("tyrano_import_invalid_format"))
            return
        except (OSError, ValueError) as e:
            showerror_relative(self.root_window, t("error"), t("tyrano_import_failed", error=str(e)))
            return

        # 导出的文件是普通 JSON；也接受 .sav 那样 URL 编码过的 JSON
        try:
            slot_data = json.loads(content)
        except ValueError:
            try:
                slot_data = decode_sav(content)
            except ValueError:
                slot_data = None
        if not isinstance(slot_data, dict):
            showwarning_relative(self.root_window, t("warning"), t("tyrano_import_invalid_format"))
            return

        file_info = t("tyrano_import_file_info", filename=Path(file_path).name, lines=len(content.splitlines()))
        description = describe_slot(slot_data, t)
        if description:
            message = t("tyrano_import_confirm", file_info=file_info, info=description)
        else:
            message = t("tyrano_import_confirm_unknown_with_file", file_info=file_info)
        if not askyesno_relative(self.root_window, t("tyrano_import_dialog_title"), message):
            return

        if self.analyzer.import_slot(slot_data):
            showinfo_relative(self.root_window, t("info"), t("tyrano_import_success"))
            self.refresh_display()
        else:
            showerror_relative(self.root_window, t("error"), t("tyrano_import_failed", error=""))
