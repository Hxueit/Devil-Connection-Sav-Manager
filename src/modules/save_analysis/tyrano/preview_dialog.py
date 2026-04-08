"""Tyrano存档重排序预览对话框

显示重排序后变动页面的预览（以图片形式展示）
"""

import logging
from typing import Dict, Any, Optional, List, Callable, Tuple
import tkinter as tk
import customtkinter as ctk
from tkinter import ttk
from PIL import Image

from src.modules.save_analysis.tyrano.constants import TYRANO_SAVES_PER_PAGE
from src.modules.save_analysis.tyrano.image_utils import (
    decode_image_data,
    create_placeholder_image
)
from src.utils.ui_utils import set_window_icon

logger = logging.getLogger(__name__)

IMGDATA_FIELD_KEY: str = 'img_data'
PREVIEW_THUMB_WIDTH: int = 80
PREVIEW_THUMB_HEIGHT: int = 60


class TyranoPreviewDialog:
    """Tyrano存档重排序预览对话框"""
    
    def __init__(
        self,
        parent: tk.Widget,
        save_slots: List[Optional[Dict[str, Any]]],
        original_order: List[int],
        new_order: List[int],
        changed_pages: List[int],
        translation_func: Callable[[str], str],
        get_cjk_font_func: Callable[[int], Any],
        colors_class: type
    ) -> None:
        """初始化预览对话框
        
        Args:
            parent: 父窗口（重排序对话框）
            save_slots: 存档槽数据列表
            original_order: 原始顺序
            new_order: 新顺序
            changed_pages: 变动页面列表（从1开始）
            translation_func: 翻译函数
            get_cjk_font_func: 字体获取函数
            colors_class: 颜色常量类
        """
        self.parent = parent
        self.save_slots = save_slots
        self.original_order = original_order
        self.new_order = new_order
        self.changed_pages = changed_pages
        self.translate = translation_func
        self.get_cjk_font = get_cjk_font_func
        self.Colors = colors_class
        
        # 对话框窗口
        self.dialog: Optional[ctk.CTkToplevel] = None
        
        # 缓存CTkImage以防止被垃圾回收
        self._image_refs: List[ctk.CTkImage] = []
        
        self._create_dialog()
    
    def _create_dialog(self) -> None:
        """创建对话框窗口"""
        self.dialog = ctk.CTkToplevel(self.parent)
        self.dialog.title(self.translate("tyrano_reorder_preview_title"))
        self.dialog.geometry("750x600")
        self.dialog.transient(self.parent)
        
        # 设置窗口图标
        set_window_icon(self.dialog)
        
        # 主容器
        main_frame = ctk.CTkFrame(self.dialog, fg_color=self.Colors.WHITE)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 创建可滚动框架
        canvas = tk.Canvas(main_frame, bg=self.Colors.WHITE, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ctk.CTkFrame(canvas, fg_color=self.Colors.WHITE)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        self._canvas = canvas
        
        for page_num in self.changed_pages:
            self._create_page_preview(scrollable_frame, page_num)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self._bind_mousewheel_recursive(self.dialog)
    
    def _on_mousewheel(self, event) -> None:
        """处理鼠标滚轮事件"""
        try:
            if hasattr(self, '_canvas') and self._canvas.winfo_exists():
                self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except tk.TclError:
            pass
    
    def _bind_mousewheel_recursive(self, widget: tk.Widget) -> None:
        """递归绑定鼠标滚轮事件到所有子组件
        
        Args:
            widget: 要绑定的组件
        """
        try:
            widget.bind("<MouseWheel>", self._on_mousewheel)
            for child in widget.winfo_children():
                self._bind_mousewheel_recursive(child)
        except tk.TclError:
            pass
    
    def _get_slot_thumbnail(self, slot_data: Optional[Dict[str, Any]]) -> Optional[ctk.CTkImage]:
        """获取存档槽缩略图
        
        Args:
            slot_data: 存档槽数据
            
        Returns:
            CTkImage 或 None
        """
        if not slot_data:
            return self._create_placeholder_ctk_image(self.translate("tyrano_no_save"))
        
        image_data = slot_data.get(IMGDATA_FIELD_KEY)
        if not image_data:
            return self._create_placeholder_ctk_image(self.translate("tyrano_no_image"))
        
        try:
            pil_image = decode_image_data(image_data)
            if not pil_image:
                return self._create_placeholder_ctk_image(self.translate("tyrano_image_decode_failed"))
            
            pil_image.thumbnail(
                (PREVIEW_THUMB_WIDTH, PREVIEW_THUMB_HEIGHT),
                Image.Resampling.LANCZOS
            )
            
            ctk_image = ctk.CTkImage(
                light_image=pil_image,
                dark_image=pil_image,
                size=(PREVIEW_THUMB_WIDTH, PREVIEW_THUMB_HEIGHT)
            )
            self._image_refs.append(ctk_image)
            return ctk_image
            
        except Exception as e:
            logger.debug("Failed to decode image: %s", e)
            return None
    
    def _create_placeholder_ctk_image(self, text: str) -> Optional[ctk.CTkImage]:
        """创建占位图CTkImage"""
        try:
            placeholder = create_placeholder_image(
                (PREVIEW_THUMB_WIDTH, PREVIEW_THUMB_HEIGHT),
                text
            )
            ctk_image = ctk.CTkImage(
                light_image=placeholder,
                dark_image=placeholder,
                size=(PREVIEW_THUMB_WIDTH, PREVIEW_THUMB_HEIGHT)
            )
            self._image_refs.append(ctk_image)
            return ctk_image
        except Exception as e:
            logger.debug("Failed to create placeholder: %s", e)
            return None
    
    def _create_slot_widget(
        self,
        parent: ctk.CTkFrame,
        slot_idx: int,
        slot_data: Optional[Dict[str, Any]],
        position: int
    ) -> ctk.CTkFrame:
        """创建单个存档槽的预览widget
        
        Args:
            parent: 父容器
            slot_idx: 存档槽在原始数据中的索引
            slot_data: 存档槽数据
            position: 在页面中的位置（1-6）
            
        Returns:
            存档槽预览frame
        """
        slot_frame = ctk.CTkFrame(parent, fg_color="transparent")
        
        pos_label = ctk.CTkLabel(
            slot_frame,
            text=f"{position}.",
            font=self.get_cjk_font(10),
            fg_color="transparent",
            text_color=self.Colors.TEXT_SECONDARY,
            width=20
        )
        pos_label.pack(side="left", padx=(0, 5))
        
        thumbnail = self._get_slot_thumbnail(slot_data)
        if thumbnail:
            img_label = ctk.CTkLabel(
                slot_frame,
                text="",
                image=thumbnail,
                fg_color="transparent"
            )
            img_label.pack(side="left")
        else:
            placeholder_label = ctk.CTkLabel(
                slot_frame,
                text=self.translate("tyrano_no_image"),
                font=self.get_cjk_font(9),
                fg_color=self.Colors.LIGHT_GRAY,
                text_color=self.Colors.TEXT_SECONDARY,
                width=PREVIEW_THUMB_WIDTH,
                height=PREVIEW_THUMB_HEIGHT
            )
            placeholder_label.pack(side="left")
        
        return slot_frame
    
    def _create_page_preview(self, parent: ctk.CTkFrame, page_num: int) -> None:
        """创建单个页面的预览
        
        Args:
            parent: 父容器
            page_num: 页面号（从1开始）
        """
        page_label = ctk.CTkLabel(
            parent,
            text=self.translate("tyrano_reorder_page_label").format(page=page_num),
            font=self.get_cjk_font(14, "bold"),
            fg_color="transparent",
            text_color=self.Colors.TEXT_PRIMARY
        )
        page_label.pack(anchor="w", pady=(15, 10))
        
        page_frame = ctk.CTkFrame(parent, fg_color=self.Colors.LIGHT_GRAY, corner_radius=8)
        page_frame.pack(fill="x", pady=(0, 10), padx=5)
        
        start_index = (page_num - 1) * TYRANO_SAVES_PER_PAGE
        end_index = start_index + TYRANO_SAVES_PER_PAGE
        
        original_page_indices = self.original_order[start_index:end_index]
        new_page_indices = self.new_order[start_index:end_index]
        
        content_frame = ctk.CTkFrame(page_frame, fg_color="transparent")
        content_frame.pack(fill="x", padx=10, pady=10)
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(1, weight=0)
        content_frame.grid_columnconfigure(2, weight=1)
        
        left_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="nsew")
        
        left_label = ctk.CTkLabel(
            left_frame,
            text=self.translate("tyrano_reorder_original_order"),
            font=self.get_cjk_font(11, "bold"),
            fg_color="transparent",
            text_color=self.Colors.TEXT_SECONDARY
        )
        left_label.pack(pady=(0, 8))
        
        left_grid = ctk.CTkFrame(left_frame, fg_color="transparent")
        left_grid.pack()
        
        for i, slot_idx in enumerate(original_page_indices):
            row = i // 2
            col = i % 2
            if slot_idx < len(self.save_slots):
                slot_data = self.save_slots[slot_idx]
                slot_widget = self._create_slot_widget(left_grid, slot_idx, slot_data, i + 1)
                slot_widget.grid(row=row, column=col, padx=5, pady=3, sticky="w")
        
        arrow_label = ctk.CTkLabel(
            content_frame,
            text="→",
            font=self.get_cjk_font(24),
            fg_color="transparent",
            text_color=self.Colors.TEXT_SECONDARY
        )
        arrow_label.grid(row=0, column=1, padx=15)
        
        right_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        right_frame.grid(row=0, column=2, sticky="nsew")
        
        right_label = ctk.CTkLabel(
            right_frame,
            text=self.translate("tyrano_reorder_new_order"),
            font=self.get_cjk_font(11, "bold"),
            fg_color="transparent",
            text_color=self.Colors.TEXT_SECONDARY
        )
        right_label.pack(pady=(0, 8))
        
        right_grid = ctk.CTkFrame(right_frame, fg_color="transparent")
        right_grid.pack()
        
        for i, slot_idx in enumerate(new_page_indices):
            row = i // 2
            col = i % 2
            if slot_idx < len(self.save_slots):
                slot_data = self.save_slots[slot_idx]
                slot_widget = self._create_slot_widget(right_grid, slot_idx, slot_data, i + 1)
                slot_widget.grid(row=row, column=col, padx=5, pady=3, sticky="w")
