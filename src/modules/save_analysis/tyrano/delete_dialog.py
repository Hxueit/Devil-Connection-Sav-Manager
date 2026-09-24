"""删除存档对话框：分页显示存档槽，点击选中后可以「清空为空存档」或「删除槽位（后续存档前移）」"""

import logging
import tkinter as tk
from typing import TYPE_CHECKING, List, Optional, Set

import customtkinter as ctk

from src.modules.save_analysis.tyrano.analyzer import describe_slot, is_empty_save
from src.modules.save_analysis.tyrano.constants import TYRANO_SAVES_PER_PAGE
from src.modules.save_analysis.tyrano.image_utils import slot_thumbnail
from src.modules.save_analysis.tyrano.save_slot import (
    SlotCard,
    build_slot_grid,
    button_style,
    create_dialog,
    slot_size_for_area,
)
from src.utils.background import run_in_background
from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import askyesno_relative, showinfo_relative, showwarning_relative

if TYPE_CHECKING:
    from src.modules.save_analysis.tyrano.save_viewer import TyranoSaveViewer

logger = logging.getLogger(__name__)

SELECTED_BG_COLOR = "#FFE0E0"
SELECTED_BORDER_COLOR = "#FF6B6B"
CONFIRM_PREVIEW_COUNT = 5   # 确认框中最多列出几个要删除的存档
MODE_CLEAR = "clear"
MODE_REMOVE = "remove"


class TyranoDeleteDialog:
    """删除存档对话框"""

    def __init__(self, viewer: "TyranoSaveViewer") -> None:
        self.viewer = viewer
        self.analyzer = viewer.analyzer
        self.translate = t = viewer.translate
        self._selected: Set[int] = set()
        self._current_page = 1
        self._load_id = 0

        self.dialog = create_dialog(viewer.root_window, t("tyrano_delete_title"), "750x580")
        self.dialog.protocol("WM_DELETE_WINDOW", self.dialog.destroy)
        self._delete_mode = tk.StringVar(master=self.dialog, value=MODE_CLEAR)

        main_frame = ctk.CTkFrame(self.dialog, fg_color=Colors.WHITE)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self._slots_frame = ctk.CTkFrame(main_frame, fg_color=Colors.WHITE)
        self._slots_frame.pack(fill="both", expand=True)
        self._slots_frame.pack_propagate(False)
        bottom = ctk.CTkFrame(main_frame, fg_color=Colors.WHITE)
        bottom.pack(side="bottom", fill="x", pady=(10, 0))

        # 翻页
        nav = ctk.CTkFrame(bottom, fg_color=Colors.WHITE)
        nav.pack(side="top", fill="x", pady=(0, 5))
        center = ctk.CTkFrame(nav, fg_color=Colors.WHITE)
        center.pack(anchor="center")
        self._prev_btn = ctk.CTkButton(center, text=t("prev_page"), command=self._go_prev, **button_style())
        self._prev_btn.pack(side="left", padx=5)
        self._next_btn = ctk.CTkButton(center, text=t("next_page"), command=self._go_next, **button_style())
        self._next_btn.pack(side="left", padx=5)
        self._page_label = ctk.CTkLabel(center, text="1/1", font=get_cjk_font(12), fg_color="transparent",
                                        text_color=Colors.TEXT_PRIMARY, width=60, anchor="center")
        self._page_label.pack(side="left", padx=10)
        jump_frame = ctk.CTkFrame(center, fg_color=Colors.WHITE)
        jump_frame.pack(side="left", padx=20)
        ctk.CTkLabel(jump_frame, text=t("jump_to_page"), font=get_cjk_font(10), fg_color="transparent",
                     text_color=Colors.TEXT_PRIMARY).pack(side="left", padx=5)
        self._jump_entry = ctk.CTkEntry(jump_frame, width=80, height=30, corner_radius=8, fg_color=Colors.WHITE,
                                        text_color=Colors.TEXT_PRIMARY, border_color=Colors.GRAY,
                                        font=get_cjk_font(10))
        self._jump_entry.pack(side="left", padx=5)
        self._jump_entry.bind("<Return>", lambda e: self._jump_to_page())
        ctk.CTkButton(jump_frame, text=t("jump"), command=self._jump_to_page, **button_style()).pack(side="left", padx=5)

        # 删除模式 + 删除按钮
        action = ctk.CTkFrame(bottom, fg_color=Colors.WHITE)
        action.pack(side="top", fill="x")
        mode_frame = ctk.CTkFrame(action, fg_color=Colors.WHITE)
        mode_frame.pack(side="left")
        for key, value, padx in (("tyrano_delete_mode_clear", MODE_CLEAR, (0, 15)),
                                 ("tyrano_delete_mode_remove", MODE_REMOVE, 0)):
            ctk.CTkRadioButton(mode_frame, text=t(key), variable=self._delete_mode, value=value,
                               font=get_cjk_font(10), text_color=Colors.TEXT_PRIMARY,
                               fg_color=Colors.GRAY, hover_color=Colors.LIGHT_GRAY).pack(side="left", padx=padx)
        ctk.CTkButton(action, text=t("tyrano_delete_button"), command=self._on_delete_click,
                      width=100, height=35, corner_radius=8, fg_color="#FF6B6B", hover_color="#FF4444",
                      text_color="white", font=get_cjk_font(12)).pack(side="right")

        # 存档槽网格：6 张卡片，翻页时复用
        self._cards: List[SlotCard] = []
        for cell in build_slot_grid(self._slots_frame):
            card = SlotCard(cell, t)
            card.image_label.pack_configure(expand=True)   # 缩略图在卡片中垂直居中
            card.bind_click(lambda e, c=card: self._toggle_selection(c))
            self._cards.append(card)

        # 等窗口布局完成后再渲染首页，缩略图才能按实际大小生成
        self.dialog.after(100, self._refresh_display)

    @property
    def _total_pages(self) -> int:
        return max(1, (len(self.analyzer.save_slots) + TYRANO_SAVES_PER_PAGE - 1) // TYRANO_SAVES_PER_PAGE)

    # --- 翻页 ---

    def _go_prev(self) -> None:
        self._current_page = self._current_page - 1 if self._current_page > 1 else self._total_pages
        self._refresh_display()

    def _go_next(self) -> None:
        self._current_page = self._current_page + 1 if self._current_page < self._total_pages else 1
        self._refresh_display()

    def _jump_to_page(self) -> None:
        try:
            page = int(self._jump_entry.get().strip())
        except ValueError:
            return
        if 1 <= page <= self._total_pages:
            self._current_page = page
            self._refresh_display()

    # --- 显示 ---

    def _refresh_display(self) -> None:
        if not self.dialog.winfo_exists():
            return
        self._current_page = min(self._current_page, self._total_pages)
        self._page_label.configure(text=f"{self._current_page}/{self._total_pages}")

        slots = self.analyzer.save_slots
        first = (self._current_page - 1) * TYRANO_SAVES_PER_PAGE
        for pos, card in enumerate(self._cards):
            index = first + pos
            if index >= len(slots):
                # 最后一页不足 6 个时，多出的位置留空
                card.container.pack_forget()
                card.set_slot(None, -1)
                continue
            card.container.pack(fill="both", expand=True)
            card.set_slot(slots[index], index)
            card.image_label.configure(cursor="" if card.is_empty else "hand2")
            card.show_info()
            self._update_card_color(card)
        self._load_page_images()

    def _load_page_images(self) -> None:
        if not self.dialog.winfo_exists():
            return
        self._load_id += 1
        load_id = self._load_id
        self._slots_frame.update_idletasks()
        slot_size = slot_size_for_area(self._slots_frame.winfo_width(), self._slots_frame.winfo_height()) \
            or (300, 150)
        cards = [card for card in self._cards if card.slot_index >= 0]
        image_datas = [card.slot_data.get("img_data") for card in cards]
        no_image_text = self.translate("tyrano_no_imgdata")
        failed_text = self.translate("tyrano_image_decode_failed")
        cache = self.viewer.image_cache

        def work() -> list:
            return [slot_thumbnail(data, slot_size, cache, no_image_text, failed_text) for data in image_datas]

        def done(thumbnails: Optional[list], error: Optional[BaseException]) -> None:
            if error is None and load_id == self._load_id:
                for card, thumbnail in zip(cards, thumbnails):
                    card.set_image(thumbnail)

        run_in_background(self.dialog, work, done)

    # --- 选择 ---

    def _toggle_selection(self, card: SlotCard) -> None:
        if card.slot_index < 0:
            return
        self._selected ^= {card.slot_index}
        self._update_card_color(card)

    def _update_card_color(self, card: SlotCard) -> None:
        selected = card.slot_index in self._selected
        card.container.configure(fg_color=SELECTED_BG_COLOR if selected else Colors.LIGHT_GRAY,
                                 border_color=SELECTED_BORDER_COLOR if selected else Colors.GRAY)

    # --- 删除 ---

    def _on_delete_click(self) -> None:
        t = self.translate
        if not self._selected:
            showwarning_relative(self.dialog, t("warning"), t("tyrano_delete_none_selected"))
            return

        indices = sorted(self._selected)
        slots = self.analyzer.save_slots
        lines = []
        for index in indices[:CONFIRM_PREVIEW_COUNT]:
            slot = slots[index] if index < len(slots) else None
            description = "" if is_empty_save(slot) else describe_slot(slot, t)
            lines.append(f"  #{index + 1}: {description or t('tyrano_no_save')}")
        details = "\n".join(lines)
        if len(indices) > CONFIRM_PREVIEW_COUNT:
            details += t("tyrano_delete_confirm_more").format(count=len(indices))

        mode = self._delete_mode.get()
        key = "tyrano_delete_confirm_clear" if mode == MODE_CLEAR else "tyrano_delete_confirm_remove"
        if not askyesno_relative(self.dialog, t("tyrano_delete_confirm_title"),
                                 t(key).format(count=len(indices), details=details)):
            return

        if mode == MODE_CLEAR:
            success = self.analyzer.clear_slots(indices)
        else:
            success = self.analyzer.remove_slots(indices)
        if not success:
            showwarning_relative(self.dialog, t("error"), t("tyrano_delete_failed"))
            return

        showinfo_relative(self.dialog, t("info"), t("tyrano_delete_success").format(count=len(indices)))
        self._selected.clear()
        self.viewer.refresh()
        self._refresh_display()
