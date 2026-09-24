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
    TyranoSaveSlot,
    build_slot_grid,
    button_style,
    slot_size_for_area,
)
from src.utils.background import run_in_background
from src.utils.sav_io import decode_sav
from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import askyesno_relative, showerror_relative, showinfo_relative, showwarning_relative

logger = logging.getLogger(__name__)

RESIZE_DEBOUNCE_MS = 200
PAGE_SWITCH_DEBOUNCE_MS = 150
DEFAULT_SLOT_SIZE = (300, 150)


class TyranoSaveViewer:
    """Tyrano 存档标签页

    翻页时复用同一组 6 个卡片：先在后台线程生成缩略图，完成后再一次性更新文字和图片，
    期间用「加载中」遮罩盖住存档区域，避免看到逐个刷新的过程。
    """

    def __init__(
        self,
        parent: ctk.CTkFrame,
        analyzer: TyranoAnalyzer,
        translation_func: Callable[[str], str],
        root_window: Optional[tk.Misc] = None,
    ) -> None:
        self.parent = parent
        self.analyzer = analyzer
        self.translate = translation_func
        self.root_window = root_window or parent.winfo_toplevel()
        self.image_cache = ImageCache()
        self.slot_widgets: List[TyranoSaveSlot] = []

        self._load_id = 0              # 每次加载页面图片时加一，用来丢弃过期的后台结果
        self._destroyed = False
        self._first_page_shown = False  # 第一页显示完成后才开始响应窗口大小变化
        self._prefetching = False
        self._page_timer: Optional[str] = None
        self._resize_timer: Optional[str] = None
        self._last_parent_size: Optional[Tuple[int, int]] = None
        self._loading_overlay: Optional[ctk.CTkFrame] = None
        self._loading_label: Optional[ctk.CTkLabel] = None
        self._texts: List[Tuple[Any, str]] = []   # (控件, 翻译键)，切换语言时更新

        self._create_ui()
        self._refresh_display()
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
        center = ctk.CTkFrame(nav, fg_color=Colors.WHITE)
        center.pack(anchor="center")

        self.prev_button = self._button(center, "prev_page", self._go_to_prev_page, "left")
        self.next_button = self._button(center, "next_page", self._go_to_next_page, "left")
        self.page_info_label = ctk.CTkLabel(center, text="1/1", font=get_cjk_font(12), fg_color="transparent",
                                            text_color=Colors.TEXT_PRIMARY, width=60, anchor="center")
        self.page_info_label.pack(side="left", padx=10)

        jump_frame = ctk.CTkFrame(center, fg_color=Colors.WHITE)
        jump_frame.pack(side="left", padx=20)
        self.jump_label = ctk.CTkLabel(jump_frame, text=self.translate("jump_to_page"), font=get_cjk_font(10),
                                       fg_color="transparent", text_color=Colors.TEXT_PRIMARY)
        self.jump_label.pack(side="left", padx=5)
        self._texts.append((self.jump_label, "jump_to_page"))
        self.jump_entry = ctk.CTkEntry(jump_frame, width=80, height=30, corner_radius=8, fg_color=Colors.WHITE,
                                       text_color=Colors.TEXT_PRIMARY, border_color=Colors.GRAY,
                                       font=get_cjk_font(10))
        self.jump_entry.pack(side="left", padx=5)
        self.jump_entry.bind("<Return>", lambda e: self._jump_to_page())
        self.jump_button = self._button(jump_frame, "jump", self._jump_to_page, "left")

        self.import_button = self._button(nav, "tyrano_import_button", self._on_import_click, "left")
        self.refresh_button = self._button(nav, "refresh", self.refresh, "right")
        self.delete_button = self._button(nav, "tyrano_delete_button", lambda: TyranoDeleteDialog(self), "right")
        self.reorder_button = self._button(nav, "tyrano_reorder_button", lambda: TyranoReorderDialog(self), "right")
        self.auto_saves_button = self._button(nav, "tyrano_auto_saves_button",
                                              lambda: TyranoAutoSavesDialog(self), "right")

    def _button(self, parent: tk.Misc, text_key: str, command: Callable[[], Any], side: str) -> ctk.CTkButton:
        button = ctk.CTkButton(parent, text=self.translate(text_key), command=command, **button_style())
        button.pack(side=side, padx=5)
        self._texts.append((button, text_key))
        return button

    def update_ui_texts(self) -> None:
        """切换语言后更新文字"""
        for widget, key in self._texts:
            if widget.winfo_exists():
                widget.configure(text=self.translate(key))
        if self._loading_label is not None:
            self._loading_label.configure(text=self.translate("loading"))
        self._refresh_display()

    def _show_loading_overlay(self) -> None:
        if self._loading_overlay is None:
            self._loading_overlay = ctk.CTkFrame(self.slots_frame, fg_color=Colors.WHITE)
            self._loading_label = ctk.CTkLabel(self._loading_overlay, text="", font=get_cjk_font(12),
                                               text_color=Colors.TEXT_SECONDARY, fg_color="transparent")
            self._loading_label.place(relx=0.5, rely=0.5, anchor="center")
        self._loading_label.configure(text=self.translate("loading"))
        self._loading_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._loading_overlay.lift()

    def _hide_loading_overlay(self) -> None:
        if self._loading_overlay is not None:
            self._loading_overlay.place_forget()

    # ------------------------------------------------------------------
    # 显示当前页
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """重新读取存档文件并刷新显示"""
        self.analyzer.load_save_file()
        self._refresh_display()

    def _refresh_display(self) -> None:
        if self._destroyed or not self.slots_frame.winfo_exists():
            return
        if not self.slot_widgets:
            self.slot_widgets = [TyranoSaveSlot(cell, self) for cell in build_slot_grid(self.slots_frame)]

        page_slots = self.analyzer.get_current_page_slots()
        first_index = max(self.analyzer.current_page - 1, 0) * TYRANO_SAVES_PER_PAGE
        for pos, card in enumerate(self.slot_widgets):
            card.set_slot(page_slots[pos] if pos < len(page_slots) else None, first_index + pos)
        self._load_page_images()
        self._update_navigation()

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
        no_image_text = self.translate("tyrano_no_imgdata")
        failed_text = self.translate("tyrano_image_decode_failed")
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
            if self._destroyed or not self.slots_frame.winfo_exists():
                return
            frame = self.slots_frame
            if frame.winfo_ismapped() and frame.winfo_width() > 1 and frame.winfo_height() > 1:
                self._refresh_display()
            elif attempts_left > 1:
                self._refresh_when_mapped(attempts_left - 1)

        self.parent.after(120, check)

    def _on_window_resize(self, event: Optional[tk.Event] = None) -> None:
        size = (self.parent.winfo_width(), self.parent.winfo_height())
        if size == self._last_parent_size:
            return
        self._last_parent_size = size
        self._cancel_timer(self._resize_timer)
        self._resize_timer = self.parent.after(RESIZE_DEBOUNCE_MS, self._refresh_display)

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
        if self._loading_overlay is not None and self._loading_overlay.winfo_exists():
            self._loading_overlay.destroy()
        self._loading_overlay = self._loading_label = None

    # ------------------------------------------------------------------
    # 翻页
    # ------------------------------------------------------------------

    def _update_navigation(self) -> None:
        total = self.analyzer.total_pages
        state = "normal" if total > 0 else "disabled"
        self.page_info_label.configure(text=f"{self.analyzer.current_page}/{total}" if total > 0 else "0/0")
        self.prev_button.configure(state=state)
        self.next_button.configure(state=state)

    def _refresh_display_debounced(self) -> None:
        """连续点击翻页时只刷新最后一次"""
        self._cancel_timer(self._page_timer)
        self._page_timer = self.parent.after(PAGE_SWITCH_DEBOUNCE_MS, self._refresh_display)

    def _go_to_prev_page(self) -> None:
        self.analyzer.go_to_prev_page()
        self._refresh_display_debounced()

    def _go_to_next_page(self) -> None:
        self.analyzer.go_to_next_page()
        self._refresh_display_debounced()

    def _jump_to_page(self) -> None:
        text = self.jump_entry.get().strip()
        if not text:
            return
        try:
            page = int(text)
        except ValueError:
            showwarning_relative(self.root_window, self.translate("warning"), self.translate("invalid_page_input"))
            return
        total = self.analyzer.total_pages
        if page < 1 or (total > 0 and page > total):
            showwarning_relative(self.root_window, self.translate("warning"),
                                 self.translate("invalid_page_number").format(min=1, max=max(total, 1)))
            return
        if self.analyzer.set_page(page):
            self._refresh_display_debounced()
            self.jump_entry.delete(0, "end")

    # ------------------------------------------------------------------
    # 导入（「导出」按钮在每个存档槽卡片上）
    # ------------------------------------------------------------------

    def _on_import_click(self) -> None:
        t = self.translate
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
            showerror_relative(self.root_window, t("error"), t("tyrano_import_failed").format(error=str(e)))
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

        file_info = t("tyrano_import_file_info").format(filename=Path(file_path).name,
                                                        lines=len(content.splitlines()))
        description = describe_slot(slot_data, t)
        if description:
            message = t("tyrano_import_confirm").format(file_info=file_info, info=description)
        else:
            message = t("tyrano_import_confirm_unknown_with_file").format(file_info=file_info)
        if not askyesno_relative(self.root_window, t("tyrano_import_dialog_title"), message):
            return

        if self.analyzer.import_slot(slot_data):
            showinfo_relative(self.root_window, t("info"), t("tyrano_import_success"))
            self.refresh()
        else:
            showerror_relative(self.root_window, t("error"), t("tyrano_import_failed").format(error=""))
