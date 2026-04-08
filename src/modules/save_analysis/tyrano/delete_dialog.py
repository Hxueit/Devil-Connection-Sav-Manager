"""Tyrano存档删除对话框

提供分页式存档删除功能，支持清空为空存档或移除槽位两种模式"""

import hashlib
import logging
import threading
import tkinter as tk
from typing import Dict, Any, Optional, List, Callable, Tuple, Set, Final, TYPE_CHECKING

import customtkinter as ctk
from PIL import Image

if TYPE_CHECKING:
    from src.modules.save_analysis.tyrano.analyzer import TyranoAnalyzer

from src.modules.save_analysis.tyrano.constants import (
    TYRANO_ROWS_PER_PAGE,
    TYRANO_SAVES_PER_PAGE,
)
from src.modules.save_analysis.tyrano.image_cache import ImageCache
from src.modules.save_analysis.tyrano.image_utils import (
    decode_image_data,
    create_placeholder_image,
    create_status_circle_image,
    ASPECT_RATIO_4_3,
)
from src.utils.ui_utils import (
    showwarning_relative,
    showinfo_relative,
    askyesno_relative,
    set_window_icon,
)

logger = logging.getLogger(__name__)

SEPARATOR_WIDTH: Final[int] = 3
PADDING_SMALL: Final[int] = 5
PADDING_MEDIUM: Final[int] = 10
CORNER_RADIUS: Final[int] = 8
FONT_SIZE_SMALL: Final[int] = 10
FONT_SIZE_MEDIUM: Final[int] = 12
BUTTON_WIDTH: Final[int] = 60
BUTTON_HEIGHT: Final[int] = 30
PAGE_INFO_WIDTH: Final[int] = 60
ENTRY_WIDTH: Final[int] = 80
MIN_CONTAINER_SIZE: Final[int] = 1
DEFAULT_CONTAINER_WIDTH: Final[int] = 300
DEFAULT_CONTAINER_HEIGHT: Final[int] = 150

LABEL_PADDING_X: Final[int] = 10
LABEL_PADDING_Y: Final[int] = 10
THUMBNAIL_HEIGHT_RATIO: Final[float] = 0.85
THUMBNAIL_MAX_WIDTH_RATIO: Final[float] = 0.35
THUMBNAIL_MIN_SIZE: Final[int] = 80
DEFAULT_THUMBNAIL_SIZE: Final[Tuple[int, int]] = (120, 90)
SLOT_FONT_SIZE: Final[int] = 10
SLOT_CORNER_RADIUS: Final[int] = 8
SLOT_BORDER_WIDTH: Final[int] = 2
DATE_COLOR: Final[str] = "#000000"
SUBTITLE_COLOR: Final[str] = "#2EA6B6"
CIRCLE_DIAMETER_DEFAULT: Final[int] = 15
CIRCLE_PADDING: Final[int] = 2

SELECTED_BG_COLOR: Final[str] = "#FFE0E0"
SELECTED_BORDER_COLOR: Final[str] = "#FF6B6B"
CONFIRM_PREVIEW_COUNT: Final[int] = 5

DELETE_MODE_CLEAR: Final[str] = "clear"
DELETE_MODE_REMOVE: Final[str] = "remove"


class TyranoDeleteDialog:
    """Tyrano存档删除对话框"""

    def __init__(
        self,
        parent: tk.Widget,
        root: tk.Tk,
        analyzer: "TyranoAnalyzer",
        image_cache: Optional[ImageCache],
        translation_func: Callable[[str], str],
        get_cjk_font_func: Callable[[int], Any],
        colors_class: type,
        on_save_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        self.parent = parent
        self.root = root
        self.analyzer = analyzer
        self.image_cache = image_cache
        self.translate = translation_func
        self.get_cjk_font = get_cjk_font_func
        self.Colors = colors_class
        self.on_save_callback = on_save_callback

        self.dialog: Optional[ctk.CTkToplevel] = None
        self._selected_indices: Set[int] = set()
        self._delete_mode = tk.StringVar(value=DELETE_MODE_CLEAR)
        self._current_page: int = 1
        self._total_pages: int = 0

        # 槽位卡片引用
        self._slot_containers: List[Optional[ctk.CTkFrame]] = []
        self._slot_image_labels: List[Optional[ctk.CTkLabel]] = []
        self._slot_global_indices: List[int] = []

        self._slots_frame: Optional[ctk.CTkFrame] = None
        self._main_container: Optional[ctk.CTkFrame] = None
        self._page_info_label: Optional[ctk.CTkLabel] = None
        self._placeholder_cache: Dict[Tuple[Tuple[int, int], str], Image.Image] = {}
        self._circle_cache: Dict[Tuple[int, bool], Image.Image] = {}
        self._is_destroyed = False

        self._create_dialog()

    def _create_dialog(self) -> None:
        """创建对话框窗口"""
        self.dialog = ctk.CTkToplevel(self.root)
        self.dialog.title(self.translate("tyrano_delete_title"))
        self.dialog.geometry("750x580")
        self.dialog.transient(self.root)

        self.dialog.after(50, lambda: set_window_icon(self.dialog))
        self.dialog.after(200, lambda: set_window_icon(self.dialog))
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)

        main_frame = ctk.CTkFrame(self.dialog, fg_color=self.Colors.WHITE)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self._calculate_pagination()

        # 存档槽显示区域
        self._slots_frame = ctk.CTkFrame(main_frame, fg_color=self.Colors.WHITE)
        self._slots_frame.pack(fill="both", expand=True)
        self._slots_frame.pack_propagate(False)

        # 底部控制区
        bottom_frame = ctk.CTkFrame(main_frame, fg_color=self.Colors.WHITE)
        bottom_frame.pack(side="bottom", fill="x", pady=(PADDING_MEDIUM, 0))

        self._create_navigation(bottom_frame)
        self._create_mode_and_action(bottom_frame)

        # 延迟渲染首页
        self.dialog.after(100, self._refresh_display)

    def _calculate_pagination(self) -> None:
        """计算分页"""
        total = len(self.analyzer.save_slots) if self.analyzer.save_slots else 0
        self._total_pages = max(1, (total + TYRANO_SAVES_PER_PAGE - 1) // TYRANO_SAVES_PER_PAGE)
        if self._current_page > self._total_pages:
            self._current_page = self._total_pages

    def _create_navigation(self, parent: ctk.CTkFrame) -> None:
        """创建翻页导航"""
        nav_frame = ctk.CTkFrame(parent, fg_color=self.Colors.WHITE)
        nav_frame.pack(side="top", fill="x", pady=(0, PADDING_SMALL))

        nav_center = ctk.CTkFrame(nav_frame, fg_color=self.Colors.WHITE)
        nav_center.pack(anchor="center")

        btn_cfg = self._get_button_config()

        self._prev_btn = ctk.CTkButton(
            nav_center, text=self.translate("prev_page"),
            command=self._go_prev, **btn_cfg
        )
        self._prev_btn.pack(side="left", padx=PADDING_SMALL)

        self._next_btn = ctk.CTkButton(
            nav_center, text=self.translate("next_page"),
            command=self._go_next, **btn_cfg
        )
        self._next_btn.pack(side="left", padx=PADDING_SMALL)

        self._page_info_label = ctk.CTkLabel(
            nav_center, text="1/1",
            font=self.get_cjk_font(FONT_SIZE_MEDIUM),
            fg_color="transparent", text_color=self.Colors.TEXT_PRIMARY,
            width=PAGE_INFO_WIDTH, anchor="center"
        )
        self._page_info_label.pack(side="left", padx=PADDING_MEDIUM)

        # 跳转
        jump_frame = ctk.CTkFrame(nav_center, fg_color=self.Colors.WHITE)
        jump_frame.pack(side="left", padx=20)

        ctk.CTkLabel(
            jump_frame, text=self.translate("jump_to_page"),
            font=self.get_cjk_font(FONT_SIZE_SMALL),
            fg_color="transparent", text_color=self.Colors.TEXT_PRIMARY
        ).pack(side="left", padx=PADDING_SMALL)

        self._jump_entry = ctk.CTkEntry(
            jump_frame, width=ENTRY_WIDTH, height=BUTTON_HEIGHT,
            corner_radius=CORNER_RADIUS, fg_color=self.Colors.WHITE,
            text_color=self.Colors.TEXT_PRIMARY, border_color=self.Colors.GRAY,
            font=self.get_cjk_font(FONT_SIZE_SMALL)
        )
        self._jump_entry.pack(side="left", padx=PADDING_SMALL)
        self._jump_entry.bind('<Return>', lambda e: self._jump_to_page())

        ctk.CTkButton(
            jump_frame, text=self.translate("jump"),
            command=self._jump_to_page, **btn_cfg
        ).pack(side="left", padx=PADDING_SMALL)

    def _create_mode_and_action(self, parent: ctk.CTkFrame) -> None:
        """创建删除模式选择和操作按钮"""
        action_frame = ctk.CTkFrame(parent, fg_color=self.Colors.WHITE)
        action_frame.pack(side="top", fill="x")

        # 左侧：模式选择
        mode_frame = ctk.CTkFrame(action_frame, fg_color=self.Colors.WHITE)
        mode_frame.pack(side="left")

        ctk.CTkRadioButton(
            mode_frame, text=self.translate("tyrano_delete_mode_clear"),
            variable=self._delete_mode, value=DELETE_MODE_CLEAR,
            font=self.get_cjk_font(FONT_SIZE_SMALL),
            text_color=self.Colors.TEXT_PRIMARY,
            fg_color=self.Colors.GRAY, hover_color=self.Colors.LIGHT_GRAY
        ).pack(side="left", padx=(0, 15))

        ctk.CTkRadioButton(
            mode_frame, text=self.translate("tyrano_delete_mode_remove"),
            variable=self._delete_mode, value=DELETE_MODE_REMOVE,
            font=self.get_cjk_font(FONT_SIZE_SMALL),
            text_color=self.Colors.TEXT_PRIMARY,
            fg_color=self.Colors.GRAY, hover_color=self.Colors.LIGHT_GRAY
        ).pack(side="left")

        # 右侧：删除按钮
        delete_btn = ctk.CTkButton(
            action_frame, text=self.translate("tyrano_delete_button"),
            command=self._on_delete_click,
            width=100, height=35, corner_radius=CORNER_RADIUS,
            fg_color="#FF6B6B", hover_color="#FF4444",
            text_color="white",
            font=self.get_cjk_font(FONT_SIZE_MEDIUM)
        )
        delete_btn.pack(side="right")

    def _get_button_config(self) -> Dict[str, Any]:
        return {
            'width': BUTTON_WIDTH, 'height': BUTTON_HEIGHT,
            'corner_radius': CORNER_RADIUS,
            'fg_color': self.Colors.WHITE, 'hover_color': self.Colors.LIGHT_GRAY,
            'border_width': 1, 'border_color': self.Colors.GRAY,
            'text_color': self.Colors.TEXT_PRIMARY,
            'font': self.get_cjk_font(FONT_SIZE_SMALL)
        }

    # === 分页导航 ===

    def _go_prev(self) -> None:
        self._current_page -= 1
        if self._current_page < 1:
            self._current_page = self._total_pages
        self._refresh_display()

    def _go_next(self) -> None:
        self._current_page += 1
        if self._current_page > self._total_pages:
            self._current_page = 1
        self._refresh_display()

    def _jump_to_page(self) -> None:
        page_input = self._jump_entry.get().strip()
        if not page_input:
            return
        try:
            target = int(page_input)
        except ValueError:
            return
        if 1 <= target <= self._total_pages:
            self._current_page = target
            self._refresh_display()

    def _update_navigation(self) -> None:
        if self._total_pages > 0:
            self._page_info_label.configure(text=f"{self._current_page}/{self._total_pages}")
            state = "normal"
        else:
            self._page_info_label.configure(text="0/0")
            state = "disabled"
        self._prev_btn.configure(state=state)
        self._next_btn.configure(state=state)

    # === 存档槽网格 ===

    def _refresh_display(self) -> None:
        """刷新当前页"""
        if self._is_destroyed:
            return
        self._clear_slots_frame()
        self._create_slots_grid()
        self._update_navigation()

    def _clear_slots_frame(self) -> None:
        if not self._slots_frame:
            return
        for w in self._slots_frame.winfo_children():
            w.destroy()
        self._slot_containers.clear()
        self._slot_image_labels.clear()
        self._slot_global_indices.clear()
        self._main_container = None

    def _get_current_page_slots(self) -> List[Optional[Dict[str, Any]]]:
        """获取当前页的槽位数据"""
        slots = self.analyzer.save_slots or []
        start = (self._current_page - 1) * TYRANO_SAVES_PER_PAGE
        page_slots = slots[start:start + TYRANO_SAVES_PER_PAGE]
        # 补齐到6个
        while len(page_slots) < TYRANO_SAVES_PER_PAGE:
            page_slots.append(None)
        return page_slots

    def _create_slots_grid(self) -> None:
        """创建存档槽网格"""
        page_slots = self._get_current_page_slots()
        base_index = (self._current_page - 1) * TYRANO_SAVES_PER_PAGE

        container = ctk.CTkFrame(self._slots_frame, fg_color=self.Colors.WHITE)
        container.pack(fill="both", expand=True, padx=PADDING_MEDIUM, pady=PADDING_SMALL)
        container.grid_propagate(False)
        self._main_container = container

        container.grid_columnconfigure(0, weight=1, uniform="column")
        container.grid_columnconfigure(1, weight=0, minsize=SEPARATOR_WIDTH)
        container.grid_columnconfigure(2, weight=1, uniform="column")
        for row in range(TYRANO_ROWS_PER_PAGE):
            container.grid_rowconfigure(row, weight=1)

        # 分隔线
        sep = tk.Frame(container, width=SEPARATOR_WIDTH, bg="gray", relief="sunken")
        sep.grid(row=0, column=1, rowspan=TYRANO_ROWS_PER_PAGE, sticky="ns", padx=PADDING_MEDIUM)

        for row in range(TYRANO_ROWS_PER_PAGE):
            left_idx = row
            right_idx = row + TYRANO_ROWS_PER_PAGE

            left_data = page_slots[left_idx] if left_idx < len(page_slots) else None
            right_data = page_slots[right_idx] if right_idx < len(page_slots) else None

            left_frame = ctk.CTkFrame(container, fg_color=self.Colors.WHITE)
            left_frame.grid(row=row, column=0, sticky="nsew", padx=(0, PADDING_SMALL), pady=PADDING_SMALL)

            right_frame = ctk.CTkFrame(container, fg_color=self.Colors.WHITE)
            right_frame.grid(row=row, column=2, sticky="nsew", padx=(PADDING_SMALL, 0), pady=PADDING_SMALL)

            self._create_readonly_slot(left_frame, left_data, base_index + left_idx)
            self._create_readonly_slot(right_frame, right_data, base_index + right_idx)

        # 延迟加载图片
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.after(50, self._load_page_images)

    def _create_readonly_slot(
        self,
        parent: ctk.CTkFrame,
        slot_data: Optional[Dict[str, Any]],
        global_index: int
    ) -> None:
        """创建只读存档槽卡片"""
        total_slots = len(self.analyzer.save_slots) if self.analyzer.save_slots else 0
        is_virtual = global_index >= total_slots

        # 虚拟槽位（补齐用），不可选
        if is_virtual:
            placeholder = ctk.CTkFrame(parent, fg_color=self.Colors.WHITE)
            placeholder.pack(fill="both", expand=True)
            self._slot_containers.append(None)
            self._slot_image_labels.append(None)
            self._slot_global_indices.append(-1)
            return

        is_selected = global_index in self._selected_indices
        is_empty = self._is_empty_save(slot_data)

        bg_color = SELECTED_BG_COLOR if is_selected else self.Colors.LIGHT_GRAY
        border_color = SELECTED_BORDER_COLOR if is_selected else self.Colors.GRAY

        slot_frame = ctk.CTkFrame(
            parent, fg_color=bg_color,
            corner_radius=SLOT_CORNER_RADIUS,
            border_width=SLOT_BORDER_WIDTH,
            border_color=border_color
        )
        slot_frame.pack(fill="both", expand=True)

        idx = len(self._slot_containers)
        self._slot_containers.append(slot_frame)
        self._slot_global_indices.append(global_index)

        content_frame = ctk.CTkFrame(slot_frame, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=LABEL_PADDING_X, pady=LABEL_PADDING_Y)

        # 左侧：图片
        image_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        image_frame.pack(side="left", fill="y", padx=(0, LABEL_PADDING_X))

        image_label = ctk.CTkLabel(
            image_frame, text="", fg_color="transparent",
            width=DEFAULT_THUMBNAIL_SIZE[0], height=DEFAULT_THUMBNAIL_SIZE[1],
            cursor="hand2" if not is_empty else ""
        )
        image_label.pack(fill="none", expand=True)
        self._slot_image_labels.append(image_label)

        # 右侧：信息
        text_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        text_frame.pack(side="right", fill="both", expand=True)

        self._create_info_panel(text_frame, slot_data)

        # 绑定点击事件（空存档也可选中）
        def on_click(e, gi=global_index, si=idx):
            self._toggle_selection(gi, si)

        for widget in [slot_frame, content_frame, image_frame, image_label, text_frame]:
            widget.bind("<Button-1>", on_click)
        # 递归绑定text_frame的子控件
        self._bind_children_click(text_frame, on_click)

    def _bind_children_click(self, widget: tk.Widget, callback: Callable) -> None:
        """递归绑定所有子控件的点击事件"""
        for child in widget.winfo_children():
            child.bind("<Button-1>", callback)
            self._bind_children_click(child, callback)

    def _toggle_selection(self, global_index: int, slot_list_index: int) -> None:
        """切换选中状态"""
        if global_index in self._selected_indices:
            self._selected_indices.discard(global_index)
        else:
            self._selected_indices.add(global_index)
        self._update_slot_appearance(slot_list_index, global_index)

    def _update_slot_appearance(self, slot_list_index: int, global_index: int) -> None:
        """更新槽位外观"""
        if slot_list_index >= len(self._slot_containers):
            return
        container = self._slot_containers[slot_list_index]
        if not container or not container.winfo_exists():
            return

        is_selected = global_index in self._selected_indices
        try:
            container.configure(
                fg_color=SELECTED_BG_COLOR if is_selected else self.Colors.LIGHT_GRAY,
                border_color=SELECTED_BORDER_COLOR if is_selected else self.Colors.GRAY
            )
        except (tk.TclError, AttributeError):
            pass

    # === 信息面板 ===

    def _is_empty_save(self, slot_data: Optional[Dict[str, Any]]) -> bool:
        if not slot_data:
            return True
        title = slot_data.get('title', '')
        save_date = slot_data.get('save_date', '')
        img_data = slot_data.get('img_data', '')
        stat = slot_data.get('stat', {})
        return (
            title == "NO SAVE" or
            (save_date == "" and img_data == "" and isinstance(stat, dict) and len(stat) == 0)
        )

    def _extract_save_info(self, slot_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """提取存档信息"""
        if not slot_data:
            return {'day_value': None, 'is_epilogue': False, 'finished_count': 0,
                    'save_date': None, 'subtitle_text': None}

        stat = slot_data.get('stat', {})
        if not isinstance(stat, dict):
            stat = {}
        f = stat.get('f', {})
        if not isinstance(f, dict):
            f = {}

        day_epilogue = f.get('day_epilogue')
        day = f.get('day')
        day_value = None
        is_epilogue = False

        if day_epilogue is not None:
            try:
                dev = int(day_epilogue)
                if dev != 0:
                    day_value = dev
                    is_epilogue = True
                elif day is not None:
                    day_value = int(day)
            except (ValueError, TypeError):
                pass

        if day_value is None and day is not None:
            try:
                day_value = int(day)
            except (ValueError, TypeError):
                pass

        finished = f.get('finished', [])
        if not isinstance(finished, list):
            finished = []

        if day_value is not None and day_value > 0:
            start = day_value * 3
            day_finished = finished[start:start + 3] if start < len(finished) else []
            finished_count = min(len(day_finished), 3)
        elif day_value == 0:
            day_finished = finished[:3] if finished else []
            finished_count = min(len(day_finished), 3)
        else:
            finished_count = 0

        save_date = slot_data.get('save_date')
        save_date = str(save_date) if save_date is not None else None

        subtitle = slot_data.get('subtitle')
        subtitle_text = slot_data.get('subtitleText')
        subtitle_text = str(subtitle_text) if (subtitle and subtitle_text) else None

        return {'day_value': day_value, 'is_epilogue': is_epilogue,
                'finished_count': finished_count, 'save_date': save_date,
                'subtitle_text': subtitle_text}

    def _format_save_description(self, slot_data: Optional[Dict[str, Any]]) -> str:
        """格式化存档文字描述（用于确认弹窗）"""
        if not slot_data or self._is_empty_save(slot_data):
            return self.translate("tyrano_no_save")

        info = self._extract_save_info(slot_data)
        parts = []

        if info['day_value'] is not None:
            key = "tyrano_epilogue_day_label" if info['is_epilogue'] else "tyrano_day_label"
            parts.append(self.translate(key).format(day=info['day_value']))

        if not info['is_epilogue'] and info['day_value'] is not None:
            circles = "".join("●" if i < info['finished_count'] else "○" for i in range(3))
            parts.append(circles)

        if info['save_date']:
            parts.append(info['save_date'])
        if info['subtitle_text']:
            parts.append(info['subtitle_text'])

        return " · ".join(parts) if parts else self.translate("tyrano_no_save")

    def _create_info_panel(self, text_frame: ctk.CTkFrame, slot_data: Optional[Dict[str, Any]]) -> None:
        """创建信息面板"""
        if not slot_data or self._is_empty_save(slot_data):
            ctk.CTkLabel(
                text_frame, text=self.translate("tyrano_no_save"),
                font=self.get_cjk_font(SLOT_FONT_SIZE),
                text_color=self.Colors.TEXT_PRIMARY,
                fg_color="transparent", anchor="w"
            ).pack(side="top", anchor="w", pady=(0, 5))
            return

        info = self._extract_save_info(slot_data)

        if info['day_value'] is not None:
            if info['is_epilogue']:
                day_text = self.translate("tyrano_epilogue_day_label").format(day=info['day_value'])
            else:
                day_text = self.translate("tyrano_day_label").format(day=info['day_value'])
            ctk.CTkLabel(
                text_frame, text=day_text,
                font=self.get_cjk_font(SLOT_FONT_SIZE),
                text_color=self.Colors.TEXT_PRIMARY,
                fg_color="transparent", anchor="w"
            ).pack(side="top", anchor="w", pady=(0, 5))

        if not info['is_epilogue']:
            circles_frame = ctk.CTkFrame(text_frame, fg_color="transparent")
            circles_frame.pack(side="top", anchor="w", pady=(0, 5))
            for i in range(3):
                is_active = i < info['finished_count']
                circle_img = create_status_circle_image(
                    CIRCLE_DIAMETER_DEFAULT, is_active, self._circle_cache
                )
                ctk_img = ctk.CTkImage(
                    light_image=circle_img, dark_image=circle_img,
                    size=(CIRCLE_DIAMETER_DEFAULT + CIRCLE_PADDING,
                          CIRCLE_DIAMETER_DEFAULT + CIRCLE_PADDING)
                )
                ctk.CTkLabel(
                    circles_frame, image=ctk_img, text="", fg_color="transparent"
                ).pack(side="left", padx=5)

        if info['save_date']:
            ctk.CTkLabel(
                text_frame, text=info['save_date'],
                font=self.get_cjk_font(SLOT_FONT_SIZE),
                text_color=DATE_COLOR, fg_color="transparent", anchor="w"
            ).pack(side="top", anchor="w", pady=(0, 5))

        subtitle_text = info['subtitle_text']
        ctk.CTkLabel(
            text_frame,
            text=subtitle_text if subtitle_text else " ",
            font=self.get_cjk_font(SLOT_FONT_SIZE),
            text_color=SUBTITLE_COLOR if subtitle_text else self.Colors.LIGHT_GRAY,
            fg_color="transparent", anchor="w"
        ).pack(side="top", anchor="w")

    # === 图片加载 ===

    def _load_page_images(self) -> None:
        """加载当前页所有图片"""
        if self._is_destroyed:
            return

        # 等待布局稳定
        if self._slots_frame and self._slots_frame.winfo_exists():
            try:
                self._slots_frame.update_idletasks()
            except (tk.TclError, AttributeError):
                pass

        ref_size = self._calculate_reference_size()
        tasks = self._prepare_image_tasks(ref_size)

        def worker():
            if self._is_destroyed:
                return
            results = self._process_images(tasks)
            if self._is_destroyed:
                return

            def apply():
                if self._is_destroyed:
                    return
                self._apply_image_results(results)

            if self.dialog and self.dialog.winfo_exists():
                try:
                    self.dialog.after(0, apply)
                except (tk.TclError, AttributeError):
                    pass

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _calculate_reference_size(self) -> Tuple[int, int]:
        """计算参考尺寸"""
        if self._slots_frame and self._slots_frame.winfo_exists():
            try:
                w = self._slots_frame.winfo_width()
                h = self._slots_frame.winfo_height()
                if w > MIN_CONTAINER_SIZE and h > MIN_CONTAINER_SIZE:
                    col_w = (w - PADDING_MEDIUM * 2 - SEPARATOR_WIDTH - PADDING_MEDIUM * 2) // 2
                    row_h = (h - PADDING_SMALL * 2) // TYRANO_ROWS_PER_PAGE
                    if col_w > MIN_CONTAINER_SIZE and row_h > MIN_CONTAINER_SIZE:
                        return (col_w, row_h)
            except (tk.TclError, AttributeError):
                pass
        return (DEFAULT_CONTAINER_WIDTH, DEFAULT_CONTAINER_HEIGHT)

    def _calculate_thumbnail_size(
        self, container_width: int, container_height: int,
        original_image: Optional[Image.Image] = None
    ) -> Tuple[int, int]:
        """计算缩略图尺寸"""
        max_w = int(container_width * THUMBNAIL_MAX_WIDTH_RATIO) - LABEL_PADDING_X * 2
        max_h = int(container_height * THUMBNAIL_HEIGHT_RATIO) - LABEL_PADDING_Y * 2
        avail_w = max(max_w, THUMBNAIL_MIN_SIZE)
        avail_h = max(max_h, THUMBNAIL_MIN_SIZE)

        if original_image:
            ow, oh = original_image.size
            ratio = (ow / oh) if oh > 0 else ASPECT_RATIO_4_3
        else:
            ratio = ASPECT_RATIO_4_3

        w_by_h = int(avail_h * ratio)
        if w_by_h <= avail_w:
            return (w_by_h, avail_h)
        return (avail_w, int(avail_w / ratio))

    def _prepare_image_tasks(
        self, ref_size: Tuple[int, int]
    ) -> List[Tuple[int, Optional[str], str, int, int]]:
        """准备图片任务: (list_index, image_data, img_hash, w, h)"""
        tasks = []
        page_slots = self._get_current_page_slots()
        base = (self._current_page - 1) * TYRANO_SAVES_PER_PAGE

        for i, label in enumerate(self._slot_image_labels):
            if label is None:
                continue

            page_idx = self._pool_index_to_page_index(i)
            slot_data = page_slots[page_idx] if page_idx < len(page_slots) else None

            image_data = slot_data.get('img_data', '') if slot_data else ''
            img_hash = ''
            if image_data:
                img_hash = hashlib.md5(image_data.encode('utf-8')).hexdigest()

            tasks.append((i, image_data if image_data else None, img_hash, ref_size[0], ref_size[1]))
        return tasks

    def _pool_index_to_page_index(self, pool_index: int) -> int:
        """widget列表索引→页面槽位索引（与save_viewer保持一致）"""
        row = pool_index // 2
        col = pool_index % 2
        return row + col * TYRANO_ROWS_PER_PAGE

    def _process_images(
        self, tasks: List[Tuple[int, Optional[str], str, int, int]]
    ) -> Dict[int, Tuple[Optional[Image.Image], Optional[str]]]:
        """在工作线程中处理图片"""
        results: Dict[int, Tuple[Optional[Image.Image], Optional[str]]] = {}

        for list_idx, image_data, img_hash, cw, ch in tasks:
            if self._is_destroyed:
                break

            if not img_hash or not image_data:
                thumb_size = self._calculate_thumbnail_size(cw, ch)
                placeholder = self.translate("tyrano_no_imgdata") if not hasattr(self, '_no_imgdata_text') else self.translate("tyrano_no_imgdata")
                pil_img = self._get_placeholder(thumb_size, placeholder)
                results[list_idx] = (pil_img, placeholder)
                continue

            # 尝试从缓存取
            original = None
            if self.image_cache:
                original = self.image_cache.get_original(img_hash)

            if not original:
                original = decode_image_data(image_data)
                if original and self.image_cache:
                    self.image_cache.put_original(img_hash, original)

            if not original:
                thumb_size = self._calculate_thumbnail_size(cw, ch)
                placeholder = self.translate("tyrano_image_decode_failed") if hasattr(self, 'translate') else "?"
                pil_img = self._get_placeholder(thumb_size, placeholder)
                results[list_idx] = (pil_img, placeholder)
                continue

            thumb_size = self._calculate_thumbnail_size(cw, ch, original)

            # L2缓存
            if self.image_cache:
                cached = self.image_cache.get_thumbnail(img_hash, thumb_size)
                if cached:
                    results[list_idx] = (cached, None)
                    continue

            thumbnail = original.resize(thumb_size, Image.Resampling.BILINEAR)
            if self.image_cache:
                self.image_cache.put_thumbnail(img_hash, thumb_size, thumbnail)
            results[list_idx] = (thumbnail, None)

        return results

    def _get_placeholder(self, size: Tuple[int, int], text: str) -> Image.Image:
        key = (size, text)
        if key in self._placeholder_cache:
            return self._placeholder_cache[key]
        img = create_placeholder_image(size, text)
        self._placeholder_cache[key] = img
        return img

    def _apply_image_results(
        self, results: Dict[int, Tuple[Optional[Image.Image], Optional[str]]]
    ) -> None:
        """应用图片到UI"""
        for list_idx, (pil_img, placeholder_text) in results.items():
            if list_idx >= len(self._slot_image_labels):
                continue
            label = self._slot_image_labels[list_idx]
            if not label or not label.winfo_exists():
                continue

            if pil_img and not placeholder_text:
                try:
                    ctk_img = ctk.CTkImage(
                        light_image=pil_img, dark_image=pil_img,
                        size=(pil_img.width, pil_img.height)
                    )
                    label.configure(image=ctk_img, text="")
                except (tk.TclError, AttributeError):
                    pass
            elif pil_img:
                try:
                    ctk_img = ctk.CTkImage(
                        light_image=pil_img, dark_image=pil_img,
                        size=(pil_img.width, pil_img.height)
                    )
                    label.configure(image=ctk_img, text="")
                except (tk.TclError, AttributeError):
                    pass

    # === 删除操作 ===

    def _on_delete_click(self) -> None:
        """删除按钮点击"""
        if not self._selected_indices:
            showwarning_relative(
                self.dialog, self.translate("warning"),
                self.translate("tyrano_delete_none_selected")
            )
            return

        mode = self._delete_mode.get()
        sorted_indices = sorted(self._selected_indices)
        count = len(sorted_indices)

        # 构建确认文本
        slots = self.analyzer.save_slots or []
        preview_items = []
        for i, idx in enumerate(sorted_indices):
            if i >= CONFIRM_PREVIEW_COUNT:
                break
            slot_data = slots[idx] if idx < len(slots) else None
            desc = self._format_save_description(slot_data)
            preview_items.append(f"  #{idx + 1}: {desc}")

        details = "\n".join(preview_items)
        if count > CONFIRM_PREVIEW_COUNT:
            details += self.translate("tyrano_delete_confirm_more").format(count=count)

        if mode == DELETE_MODE_CLEAR:
            msg = self.translate("tyrano_delete_confirm_clear").format(count=count, details=details)
        else:
            msg = self.translate("tyrano_delete_confirm_remove").format(count=count, details=details)

        result = askyesno_relative(
            self.dialog,
            self.translate("tyrano_delete_confirm_title"),
            msg
        )
        if not result:
            return

        self._execute_delete(mode, sorted_indices)

    def _execute_delete(self, mode: str, indices: List[int]) -> None:
        """执行删除"""
        if mode == DELETE_MODE_CLEAR:
            success = self.analyzer.clear_slots(indices)
        else:
            success = self.analyzer.remove_slots(indices)

        if success:
            showinfo_relative(
                self.dialog, self.translate("info"),
                self.translate("tyrano_delete_success").format(count=len(indices))
            )
            self._selected_indices.clear()

            if self.on_save_callback:
                self.on_save_callback()

            # 刷新对话框内数据
            self._calculate_pagination()
            self._refresh_display()
        else:
            showwarning_relative(
                self.dialog, self.translate("error"),
                self.translate("tyrano_delete_failed")
            )

    def _on_close(self) -> None:
        self._is_destroyed = True
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.destroy()
