"""存档槽卡片和 Tyrano 标签页共用的界面小部件

- PageNavBar：翻页导航栏
- SlotCard：只负责显示（缩略图 + 天数/完成圆点/日期/副标题），删除对话框直接使用
- TyranoSaveSlot：主界面用的卡片，多了「修改」「导出」按钮，点击缩略图打开图片详情
"""

import json
import logging
import re
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

import customtkinter as ctk
from PIL import Image

from src.modules.common.image_operations import ImageExportHelper, ImageReplaceHelper
from src.modules.save_analysis.sf.save_file_viewer import SaveFileViewer
from src.modules.save_analysis.tyrano.analyzer import (
    day_text,
    describe_slot,
    extract_save_info,
    is_empty_save,
    step_page,
)
from src.modules.save_analysis.tyrano.constants import TYRANO_ROWS_PER_PAGE
from src.modules.save_analysis.tyrano.image_utils import (
    DEFAULT_THUMBNAIL_SIZE,
    create_status_circle_image,
    decode_image_data,
)
from src.utils.images import image_to_data_uri, is_image_file
from src.utils.styles import Colors, get_cjk_font, white_button
from src.utils.ui_utils import (
    create_dialog, showerror_relative, showinfo_relative, showwarning_relative,
)

if TYPE_CHECKING:
    from src.modules.save_analysis.tyrano.save_viewer import TyranoSaveViewer

logger = logging.getLogger(__name__)

DATE_COLOR = "#000000"
SUBTITLE_COLOR = "#2EA6B6"

# 在 JSON 编辑器里默认折叠的字段（内容很长且一般不需要改）
TYRANO_COLLAPSED_FIELDS = [
    "stat.map_label", "stat.charas", "stat.map_keyframe", "stat.stack",
    "stat.popopo", "stat.map_macro", "stat.fuki", "three",
]

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


class PageNavBar:
    """「上一页 / 下一页 / 当前页 / 跳转到第 N 页」导航栏，主界面和删除对话框共用

    导航栏只算出要去的页码，然后调用 on_page_change(页码)；
    使用者翻好页后再调用 show(当前页, 总页数) 更新页码显示。
    """

    def __init__(self, parent: tk.Misc, t: Callable[..., str], on_page_change: Callable[[int], None]) -> None:
        self.t = t
        self._on_page_change = on_page_change
        self._page = 0
        self._total = 0

        self.frame = ctk.CTkFrame(parent, fg_color=Colors.WHITE)
        self.frame.pack(anchor="center")
        self.prev_button = white_button(self.frame, t("prev_page"), lambda: self._step(-1), width=60, height=30)
        self.prev_button.pack(side="left", padx=5)
        self.next_button = white_button(self.frame, t("next_page"), lambda: self._step(1), width=60, height=30)
        self.next_button.pack(side="left", padx=5)
        self.page_label = ctk.CTkLabel(self.frame, text="1/1", font=get_cjk_font(12), fg_color="transparent",
                                       text_color=Colors.TEXT_PRIMARY, width=60, anchor="center")
        self.page_label.pack(side="left", padx=10)

        jump_frame = ctk.CTkFrame(self.frame, fg_color=Colors.WHITE)
        jump_frame.pack(side="left", padx=20)
        self.jump_label = ctk.CTkLabel(jump_frame, text=t("jump_to_page"), font=get_cjk_font(10),
                                       fg_color="transparent", text_color=Colors.TEXT_PRIMARY)
        self.jump_label.pack(side="left", padx=5)
        self.jump_entry = ctk.CTkEntry(jump_frame, width=80, height=30, corner_radius=8, fg_color=Colors.WHITE,
                                       text_color=Colors.TEXT_PRIMARY, border_color=Colors.GRAY,
                                       font=get_cjk_font(10))
        self.jump_entry.pack(side="left", padx=5)
        self.jump_entry.bind("<Return>", lambda e: self._jump())
        self.jump_button = white_button(jump_frame, t("jump"), self._jump, width=60, height=30)
        self.jump_button.pack(side="left", padx=5)

    def show(self, page: int, total: int) -> None:
        self._page, self._total = page, total
        self.page_label.configure(text=f"{page}/{total}")
        state = "normal" if total > 0 else "disabled"
        self.prev_button.configure(state=state)
        self.next_button.configure(state=state)

    def update_texts(self) -> None:
        """切换语言后更新文字"""
        for widget, key in ((self.prev_button, "prev_page"), (self.next_button, "next_page"),
                            (self.jump_label, "jump_to_page"), (self.jump_button, "jump")):
            widget.configure(text=self.t(key))

    def _step(self, delta: int) -> None:
        if self._total > 0:
            self._on_page_change(step_page(self._page, self._total, delta))

    def _jump(self) -> None:
        text = self.jump_entry.get().strip()
        if not text:
            return
        window = self.frame.winfo_toplevel()
        try:
            page = int(text)
        except ValueError:
            showwarning_relative(window, self.t("warning"), self.t("invalid_page_input"))
            return
        if not 1 <= page <= self._total:
            showwarning_relative(window, self.t("warning"),
                                 self.t("invalid_page_number", min=1, max=max(self._total, 1)))
            return
        self.jump_entry.delete(0, "end")
        self._on_page_change(page)


def build_slot_grid(parent: tk.Misc) -> List[ctk.CTkFrame]:
    """创建与游戏存档界面一致的两列三行网格，按页内顺序返回 6 个格子（先左列再右列）"""
    grid = ctk.CTkFrame(parent, fg_color=Colors.WHITE)
    grid.pack(fill="both", expand=True, padx=10, pady=5)
    grid.grid_propagate(False)
    grid.grid_columnconfigure(0, weight=1, uniform="column")
    grid.grid_columnconfigure(1, weight=0, minsize=3)
    grid.grid_columnconfigure(2, weight=1, uniform="column")
    for row in range(TYRANO_ROWS_PER_PAGE):
        grid.grid_rowconfigure(row, weight=1)

    separator = tk.Frame(grid, width=3, bg="gray", relief="sunken")
    separator.grid(row=0, column=1, rowspan=TYRANO_ROWS_PER_PAGE, sticky="ns", padx=10)

    cells = []
    for column, padx in ((0, (0, 5)), (2, (5, 0))):
        for row in range(TYRANO_ROWS_PER_PAGE):
            cell = ctk.CTkFrame(grid, fg_color=Colors.WHITE)
            cell.grid(row=row, column=column, sticky="nsew", padx=padx, pady=5)
            cells.append(cell)
    return cells


def slot_size_for_area(width: int, height: int) -> Optional[Tuple[int, int]]:
    """由 build_slot_grid 所在区域的大小算出单个格子的大小；区域还没布局好时返回 None"""
    column_width = (width - 20 - 3 - 20) // 2   # 网格左右边距、分隔线及其两侧边距
    row_height = (height - 10) // TYRANO_ROWS_PER_PAGE
    if column_width > 1 and row_height > 1:
        return (column_width, row_height)
    return None


def _date_for_name(save_date: Optional[str]) -> str:
    """把保存时间转成 YYYY-MM-DD，用在文件名和窗口标题里"""
    if not save_date:
        return datetime.now().strftime("%Y-%m-%d")
    date_part = save_date.split()[0] if save_date.split() else ""
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_part, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_part.replace("/", "-")


class SlotCard:
    """存档槽卡片：左边缩略图，右边天数、完成圆点、保存时间和副标题"""

    def __init__(self, parent: tk.Misc, t: Callable[..., str]) -> None:
        self.t = t
        self.slot_data: Optional[Dict[str, Any]] = None
        self.slot_index = -1
        self._on_click: Optional[Callable[[tk.Event], None]] = None

        self.container = ctk.CTkFrame(parent, fg_color=Colors.LIGHT_GRAY, corner_radius=8,
                                      border_width=2, border_color=Colors.GRAY)
        self.container.pack(fill="both", expand=True)
        content = ctk.CTkFrame(self.container, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=10, pady=10)
        image_frame = ctk.CTkFrame(content, fg_color="transparent")
        image_frame.pack(side="left", fill="y", padx=(0, 10))
        self.image_label = ctk.CTkLabel(image_frame, text="", fg_color="transparent",
                                        width=DEFAULT_THUMBNAIL_SIZE[0], height=DEFAULT_THUMBNAIL_SIZE[1])
        self.image_label.pack(fill="none")
        self.text_frame = ctk.CTkFrame(content, fg_color="transparent")
        self.text_frame.pack(side="right", fill="both", expand=True)
        self._frames = [self.container, content, image_frame, self.image_label, self.text_frame]

    @property
    def is_empty(self) -> bool:
        return is_empty_save(self.slot_data)

    def bind_click(self, callback: Callable[[tk.Event], None]) -> None:
        """点击卡片任意位置都调用 callback"""
        self._on_click = callback
        for widget in self._frames:
            widget.bind("<Button-1>", callback)

    def set_slot(self, slot_data: Optional[Dict[str, Any]], index: int) -> None:
        """换成另一个存档槽的数据；信息面板要等 show_info() 时才重新创建"""
        self.slot_data = slot_data
        self.slot_index = index
        for widget in self.text_frame.winfo_children():
            widget.destroy()

    def show_info(self, circle_diameter: int = 15) -> None:
        """创建右侧信息面板"""
        def add_label(text: str, color: str, pady=(0, 5)) -> None:
            ctk.CTkLabel(self.text_frame, text=text, font=get_cjk_font(10), text_color=color,
                         fg_color="transparent", anchor="w").pack(side="top", anchor="w", pady=pady)

        if self.is_empty:
            add_label(self.t("tyrano_no_save"), Colors.TEXT_PRIMARY)
        else:
            info = extract_save_info(self.slot_data)
            if info.day is not None:
                add_label(day_text(info, self.t), Colors.TEXT_PRIMARY)
            if not info.is_epilogue:
                circles_frame = ctk.CTkFrame(self.text_frame, fg_color="transparent")
                circles_frame.pack(side="top", anchor="w", pady=(0, 5))
                size = (circle_diameter + 2, circle_diameter + 2)
                for i in range(3):
                    circle = create_status_circle_image(circle_diameter, i < info.finished_count)
                    image = ctk.CTkImage(light_image=circle, dark_image=circle, size=size)
                    ctk.CTkLabel(circles_frame, image=image, text="", fg_color="transparent").pack(side="left", padx=5)
            if info.save_date:
                add_label(info.save_date, DATE_COLOR)
            # 没有副标题时也放一个空行，保持各卡片高度一致
            add_label(info.subtitle or " ", SUBTITLE_COLOR if info.subtitle else Colors.LIGHT_GRAY, pady=0)

        if self._on_click:
            self._bind_tree(self.text_frame)

    def _bind_tree(self, widget: tk.Misc) -> None:
        for child in widget.winfo_children():
            child.bind("<Button-1>", self._on_click)
            self._bind_tree(child)

    def set_image(self, image: Image.Image) -> None:
        ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
        self.image_label.configure(image=ctk_image, text="", width=image.width, height=image.height)


class TyranoSaveSlot(SlotCard):
    """主界面的存档槽卡片：右上角有「修改」「导出」按钮，点击缩略图查看/替换/导出图片"""

    def __init__(self, parent: tk.Misc, viewer: "TyranoSaveViewer") -> None:
        super().__init__(parent, viewer.t)
        self.viewer = viewer
        self._button_frame: Optional[ctk.CTkFrame] = None
        self.image_label.configure(cursor="hand2")
        self.image_label.bind("<Button-1>", lambda e: None if self.is_empty else self._show_image_dialog())

    @property
    def root(self) -> tk.Misc:
        return self.viewer.root_window

    def set_slot(self, slot_data: Optional[Dict[str, Any]], index: int) -> None:
        super().set_slot(slot_data, index)
        if self._button_frame is not None:
            self._button_frame.destroy()
            self._button_frame = None
        if not self.is_empty:
            self._create_action_buttons()

    def _create_action_buttons(self) -> None:
        self._button_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        self._button_frame.place(relx=1.0, rely=0.0, anchor="ne", x=-2, y=2)
        for key, command in (("tyrano_slot_edit_button", self._on_edit_click),
                             ("tyrano_slot_export_button", self._on_export_click)):
            white_button(self._button_frame, self.t(key), command, width=30, height=20, corner_radius=4,
                         font=get_cjk_font(9)).pack(side="left", padx=2)

    # --- 修改：用 JSON 编辑器打开这个存档槽 ---

    def _on_edit_click(self) -> None:
        # 记下当前的索引：编辑器不是模态的，期间卡片可能因为翻页换成别的存档槽
        index = self.slot_index
        analyzer = self.viewer.analyzer

        def load_slot() -> Optional[Dict[str, Any]]:
            return analyzer.save_slots[index] if index < len(analyzer.save_slots) else None

        SaveFileViewer.open_or_focus(
            viewer_id=f"tyrano_slot:{analyzer.storage_dir}:{index}",
            parent=self.root,
            t=self.t,
            data=self.slot_data,
            title=self._edit_title(),
            load=load_slot,
            save=lambda edited: analyzer.replace_slot(index, edited),
            collapsed_fields=TYRANO_COLLAPSED_FIELDS,
            show_collapse_toggle=True,
            on_saved=lambda edited: self.viewer.refresh_display(),
        )

    def _edit_title(self) -> str:
        """「存档:3日目_●●○_2024-05-01_副标题」"""
        info = extract_save_info(self.slot_data)
        day = day_text(info, self.t) or self.t("tyrano_day_label", day=0)
        circles = info.circles() if info.day is not None and not info.is_epilogue else "○○○"
        parts = [day, circles, _date_for_name(info.save_date)]
        if info.subtitle:
            parts.append(info.subtitle)
        return f"{self.t('tyrano_slot_edit_title_prefix')}:{'_'.join(parts)}"

    # --- 导出：保存为 JSON 文件（可以在「导入」中重新导入） ---

    def _export_basename(self) -> str:
        """「3日目_XXO_2024-05-01_副标题」（X=已完成，O=未完成）"""
        info = extract_save_info(self.slot_data)
        parts = [f"{info.day if info.day is not None else 0}日目", info.circles("X", "O"),
                 _date_for_name(info.save_date)]
        if info.subtitle:
            parts.append(info.subtitle)
        return _INVALID_FILENAME_CHARS.sub("_", "_".join(parts))

    def _on_export_click(self) -> None:
        file_path = filedialog.asksaveasfilename(
            parent=self.root,
            title=self.t("tyrano_slot_export_dialog_title"),
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=self._export_basename() + ".json",
        )
        if not file_path:
            return
        try:
            Path(file_path).write_text(json.dumps(self.slot_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, TypeError, ValueError) as e:
            logger.error("Failed to export save slot: %s", e, exc_info=True)
            showerror_relative(self.root, self.t("error"), self.t("tyrano_export_failed", error=str(e)))
            return
        showinfo_relative(self.root, self.t("success"), self.t("tyrano_export_success", path=file_path))

    # --- 图片详情对话框：预览、替换、导出 img_data ---

    def _show_image_dialog(self) -> None:
        t = self.t
        index = self.slot_index
        slot_data = self.slot_data
        image_data = slot_data.get("img_data")

        dialog = create_dialog(self.root, t("tyrano_imgdata_dialog_title"), "450x400", use_ctk=True)

        main_frame = ctk.CTkFrame(dialog, fg_color=Colors.LIGHT_GRAY)
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        ctk.CTkLabel(main_frame, text=describe_slot(slot_data, t) or t("tyrano_no_save"), font=get_cjk_font(14),
                     text_color=Colors.TEXT_PRIMARY, fg_color="transparent", anchor="w",
                     ).pack(side="top", anchor="w", pady=(0, 15))
        ctk.CTkLabel(main_frame, text=t("tyrano_imgdata_label"), font=get_cjk_font(12),
                     text_color=Colors.TEXT_PRIMARY, fg_color="transparent", anchor="w",
                     ).pack(side="top", anchor="w", pady=(0, 10))

        preview_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        preview_frame.pack(side="top", fill="both", expand=True, pady=(0, 20))
        image = decode_image_data(image_data) if image_data else None
        if image is not None:
            ratio = min(300 / image.width, 225 / image.height, 1.0)
            preview = image.resize((int(image.width * ratio), int(image.height * ratio)), Image.Resampling.BILINEAR)
            ctk_image = ctk.CTkImage(light_image=preview, dark_image=preview, size=preview.size)
            ctk.CTkLabel(preview_frame, image=ctk_image, text="", fg_color="transparent").pack(expand=True)
        else:
            ctk.CTkLabel(preview_frame, text=t("tyrano_imgdata_no_image"), font=get_cjk_font(12),
                         text_color=Colors.TEXT_PRIMARY, fg_color="transparent").pack(expand=True)

        def on_replace() -> None:
            if not image_data:
                showwarning_relative(dialog, t("warning"), t("tyrano_imgdata_no_image"))
                return
            helper = ImageReplaceHelper(self.root, t)
            helper.show_replace_flow(image_data, replace_image, is_image_file)

        def replace_image(new_image_path: Path) -> None:
            try:
                with Image.open(new_image_path) as new_image:
                    new_image_data = image_to_data_uri(new_image)
            except (OSError, ValueError) as e:
                logger.error("Failed to read replacement image: %s", e, exc_info=True)
                showerror_relative(dialog, t("error"), f"{t('error')}: {e}")
                return
            if not self.viewer.analyzer.replace_slot(index, {**slot_data, "img_data": new_image_data}):
                showerror_relative(dialog, t("error"), t("tyrano_reorder_save_failed"))
                return
            showinfo_relative(dialog, t("success"), t("tyrano_imgdata_replace_success"))
            self.viewer.refresh_display()
            dialog.destroy()

        def on_export() -> None:
            if not image_data:
                showwarning_relative(dialog, t("warning"), t("tyrano_imgdata_no_image"))
                return
            if image is None:
                showerror_relative(dialog, t("error"), t("tyrano_imgdata_no_image"))
                return
            helper = ImageExportHelper(self.root, t)
            helper.show_format_dialog(image, self._export_basename())

        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(side="bottom", fill="x", pady=(10, 0))
        white_button(button_frame, t("tyrano_imgdata_replace"), on_replace,
                     width=60, height=30).pack(side="left", padx=10)
        white_button(button_frame, t("tyrano_imgdata_export"), on_export,
                     width=60, height=30).pack(side="right", padx=10)
