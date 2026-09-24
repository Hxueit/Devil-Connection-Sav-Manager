"""存档重排序对话框（拖拽排序），以及保存前查看各页变化的预览窗口"""

import logging
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

import customtkinter as ctk
from PIL import Image

from src.modules.common.draggable_list import DraggableList
from src.modules.save_analysis.tyrano.analyzer import describe_slot
from src.modules.save_analysis.tyrano.constants import TYRANO_SAVES_PER_PAGE
from src.modules.save_analysis.tyrano.image_utils import create_placeholder_image
from src.utils.images import decode_image_data
from src.utils.styles import Colors, get_cjk_font, white_button
from src.utils.ui_utils import (
    askyesno_relative, bind_mousewheel, create_dialog, showinfo_relative, showwarning_relative,
)

if TYPE_CHECKING:
    from src.modules.save_analysis.tyrano.save_viewer import TyranoSaveViewer

logger = logging.getLogger(__name__)

PREVIEW_THUMB_SIZE = (80, 60)


class TyranoReorderDialog:
    """拖拽调整存档顺序，确认后写回存档文件"""

    def __init__(self, viewer: "TyranoSaveViewer") -> None:
        self.viewer = viewer
        self.t = t = viewer.t
        self._slots = list(viewer.analyzer.save_slots)
        self._original_order = list(range(len(self._slots)))
        self._current_order = list(self._original_order)

        self.dialog = create_dialog(viewer.root_window, t("tyrano_reorder_title"), "450x600",
                                    modal=False, use_ctk=True)
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)

        main_frame = ctk.CTkFrame(self.dialog, fg_color=Colors.WHITE)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        list_frame = ctk.CTkFrame(main_frame, fg_color=Colors.WHITE)
        list_frame.pack(fill="both", expand=True, pady=(0, 10))
        self.draggable_list = DraggableList(
            parent=list_frame,
            root=viewer.root_window,
            data_items=self._slots,
            format_item=lambda slot, index: describe_slot(slot, t) or t("tyrano_no_save"),
            on_order_changed=self._on_order_changed,
            t=t,
        )

        button_frame = ctk.CTkFrame(main_frame, fg_color=Colors.WHITE)
        button_frame.pack(side="bottom", fill="x", pady=(10, 0))
        white_button(button_frame, t("tyrano_reorder_preview"), self._show_preview,
                     width=120, height=35, font=get_cjk_font(12)).pack(side="left", padx=(0, 10))
        white_button(button_frame, t("tyrano_reorder_save"), self._save_order,
                     width=120, height=35, font=get_cjk_font(12)).pack(side="right")

    def _on_order_changed(self, new_order: List[int]) -> None:
        self._current_order = new_order

    def _is_dirty(self) -> bool:
        return self._current_order != self._original_order

    def _on_close(self) -> None:
        if self._is_dirty() and not askyesno_relative(self.dialog, self.t("warning"),
                                                      self.t("unsaved_changes_warning")):
            return
        self.dialog.destroy()

    def _changed_pages(self) -> List[int]:
        """顺序有变化的页码（从 1 开始）"""
        pages = []
        for start in range(0, len(self._slots), TYRANO_SAVES_PER_PAGE):
            end = start + TYRANO_SAVES_PER_PAGE
            if self._original_order[start:end] != self._current_order[start:end]:
                pages.append(start // TYRANO_SAVES_PER_PAGE + 1)
        return pages

    def _show_preview(self) -> None:
        changed_pages = self._changed_pages()
        if not changed_pages:
            showinfo_relative(self.dialog, self.t("info"), self.t("tyrano_reorder_preview_empty"))
            return
        show_reorder_preview(self.dialog, self._slots, self._original_order, self._current_order,
                             changed_pages, self.t)

    def _save_order(self) -> None:
        t = self.t
        if not self._is_dirty():
            showinfo_relative(self.dialog, t("info"), t("tyrano_reorder_no_changes"))
            return
        if not askyesno_relative(self.dialog, t("tyrano_reorder_save_confirm_title"),
                                 t("tyrano_reorder_save_confirm_text")):
            return
        if not self.viewer.analyzer.reorder_slots(self._current_order):
            showwarning_relative(self.dialog, t("error"), t("tyrano_reorder_save_failed"))
            return
        showinfo_relative(self.dialog, t("info"), t("tyrano_reorder_save_success"))
        self.viewer.refresh_display()
        self.dialog.destroy()


def show_reorder_preview(
    master: tk.Misc,
    slots: List[Dict[str, Any]],
    original_order: List[int],
    new_order: List[int],
    changed_pages: List[int],
    t: Callable[..., str],
) -> None:
    """对每个变动的页面，左右并排显示原顺序和新顺序的缩略图"""
    dialog = create_dialog(master, t("tyrano_reorder_preview_title"), "750x600", modal=False, use_ctk=True)
    main_frame = ctk.CTkFrame(dialog, fg_color=Colors.WHITE)
    main_frame.pack(fill="both", expand=True, padx=10, pady=10)

    canvas = tk.Canvas(main_frame, bg=Colors.WHITE, highlightthickness=0)
    scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
    content = ctk.CTkFrame(canvas, fg_color=Colors.WHITE)
    content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=content, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    def thumbnail(slot: Optional[Dict[str, Any]]) -> ctk.CTkImage:
        image: Optional[Image.Image] = None
        if not slot:
            text = t("tyrano_no_save")
        elif not slot.get("img_data"):
            text = t("tyrano_no_image")
        else:
            image = decode_image_data(slot["img_data"])
            text = t("tyrano_image_decode_failed")
        if image is None:
            image = create_placeholder_image(PREVIEW_THUMB_SIZE, text)
        else:
            image.thumbnail(PREVIEW_THUMB_SIZE, Image.Resampling.LANCZOS)
        return ctk.CTkImage(light_image=image, dark_image=image, size=PREVIEW_THUMB_SIZE)

    def order_column(parent: tk.Misc, column: int, title_key: str, order: List[int]) -> None:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=0, column=column, sticky="nsew")
        ctk.CTkLabel(frame, text=t(title_key), font=get_cjk_font(11, "bold"), fg_color="transparent",
                     text_color=Colors.TEXT_SECONDARY).pack(pady=(0, 8))
        grid = ctk.CTkFrame(frame, fg_color="transparent")
        grid.pack()
        for i, slot_index in enumerate(order):
            cell = ctk.CTkFrame(grid, fg_color="transparent")
            cell.grid(row=i // 2, column=i % 2, padx=5, pady=3, sticky="w")
            ctk.CTkLabel(cell, text=f"{i + 1}.", font=get_cjk_font(10), fg_color="transparent",
                         text_color=Colors.TEXT_SECONDARY, width=20).pack(side="left", padx=(0, 5))
            ctk.CTkLabel(cell, text="", image=thumbnail(slots[slot_index]), fg_color="transparent").pack(side="left")

    for page in changed_pages:
        ctk.CTkLabel(content, text=t("tyrano_reorder_page_label", page=page), font=get_cjk_font(14, "bold"),
                     fg_color="transparent", text_color=Colors.TEXT_PRIMARY).pack(anchor="w", pady=(15, 10))
        page_frame = ctk.CTkFrame(content, fg_color=Colors.LIGHT_GRAY, corner_radius=8)
        page_frame.pack(fill="x", pady=(0, 10), padx=5)
        row = ctk.CTkFrame(page_frame, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=10)
        row.grid_columnconfigure(0, weight=1)
        row.grid_columnconfigure(1, weight=0)
        row.grid_columnconfigure(2, weight=1)

        start = (page - 1) * TYRANO_SAVES_PER_PAGE
        end = start + TYRANO_SAVES_PER_PAGE
        order_column(row, 0, "tyrano_reorder_original_order", original_order[start:end])
        ctk.CTkLabel(row, text="→", font=get_cjk_font(24), fg_color="transparent",
                     text_color=Colors.TEXT_SECONDARY).grid(row=0, column=1, padx=15)
        order_column(row, 2, "tyrano_reorder_new_order", new_order[start:end])

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    bind_mousewheel(dialog, lambda direction: canvas.yview_scroll(direction, "units"))
