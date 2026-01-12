"""Tyrano存档重排序对话框

提供存档重排序功能的对话框界面
"""

import logging
from typing import Dict, Any, Optional, List, Callable, TYPE_CHECKING
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

if TYPE_CHECKING:
    from src.modules.save_analysis.tyrano.analyzer import TyranoAnalyzer

from src.modules.common.draggable_list import DraggableList
from src.utils.ui_utils import (
    showinfo_relative,
    showwarning_relative,
    askyesno_relative,
    set_window_icon
)

logger = logging.getLogger(__name__)

SUBTITLE_COLOR: str = "#2EA6B6"


class TyranoReorderDialog:
    """Tyrano存档重排序对话框"""
    
    def __init__(
        self,
        parent: tk.Widget,
        root: tk.Tk,
        analyzer: "TyranoAnalyzer",
        translation_func: Callable[[str], str],
        get_cjk_font_func: Callable[[int], Any],
        colors_class: type,
        on_save_callback: Optional[Callable[[], None]] = None
    ) -> None:
        """初始化重排序对话框
        
        Args:
            parent: 父窗口
            root: 根窗口
            analyzer: TyranoAnalyzer实例
            translation_func: 翻译函数
            get_cjk_font_func: 字体获取函数
            colors_class: 颜色常量类
            on_save_callback: 保存后的回调函数
        """
        self.parent = parent
        self.root = root
        self.analyzer = analyzer
        self.translate = translation_func
        self.get_cjk_font = get_cjk_font_func
        self.Colors = colors_class
        self.on_save_callback = on_save_callback
        
        # 对话框窗口
        self.dialog: Optional[ctk.CTkToplevel] = None
        
        # 数据状态
        self._original_order: List[int] = []
        self._current_order: List[int] = []
        self._save_slots: List[Optional[Dict[str, Any]]] = []
        
        # UI组件
        self.draggable_list: Optional[DraggableList] = None
        self.preview_button: Optional[ctk.CTkButton] = None
        self.save_button: Optional[ctk.CTkButton] = None
        
        self._create_dialog()
    
    def _create_dialog(self) -> None:
        """创建对话框窗口"""
        self.dialog = ctk.CTkToplevel(self.root)
        self.dialog.title(self.translate("tyrano_reorder_title"))
        self.dialog.geometry("450x600")
        self.dialog.transient(self.root)
        
        # 设置窗口图标（延迟设置，确保在 CTkToplevel 初始化完成后）
        # CTkToplevel 可能会在显示时重置图标，所以需要多次设置
        self.dialog.after(50, lambda: set_window_icon(self.dialog))
        self.dialog.after(200, lambda: set_window_icon(self.dialog))
        
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        
        main_frame = ctk.CTkFrame(self.dialog, fg_color=self.Colors.WHITE)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self._load_data()
        
        list_frame = ctk.CTkFrame(main_frame, fg_color=self.Colors.WHITE)
        list_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        self.draggable_list = DraggableList(
            parent=list_frame,
            root=self.root,
            data_items=self._save_slots,
            format_item=self._format_save_item,
            on_order_changed=self._on_order_changed,
            get_cjk_font=self.get_cjk_font,
            colors_class=self.Colors,
            translation_func=self.translate
        )
        
        button_frame = ctk.CTkFrame(main_frame, fg_color=self.Colors.WHITE)
        button_frame.pack(side="bottom", fill="x", pady=(10, 0))
        
        self.preview_button = ctk.CTkButton(
            button_frame,
            text=self.translate("tyrano_reorder_preview"),
            command=self._show_preview,
            width=120,
            height=35,
            corner_radius=8,
            fg_color=self.Colors.WHITE,
            hover_color=self.Colors.LIGHT_GRAY,
            border_width=1,
            border_color=self.Colors.GRAY,
            text_color=self.Colors.TEXT_PRIMARY,
            font=self.get_cjk_font(12)
        )
        self.preview_button.pack(side="left", padx=(0, 10))
        
        self.save_button = ctk.CTkButton(
            button_frame,
            text=self.translate("tyrano_reorder_save"),
            command=self._save_order,
            width=120,
            height=35,
            corner_radius=8,
            fg_color=self.Colors.WHITE,
            hover_color=self.Colors.LIGHT_GRAY,
            border_width=1,
            border_color=self.Colors.GRAY,
            text_color=self.Colors.TEXT_PRIMARY,
            font=self.get_cjk_font(12)
        )
        self.save_button.pack(side="right")
    
    def _load_data(self) -> None:
        """加载存档数据"""
        self._save_slots = self.analyzer.save_slots.copy() if self.analyzer.save_slots else []
        self._original_order = list(range(len(self._save_slots)))
        self._current_order = self._original_order.copy()
    
    def _extract_save_info(self, slot_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """提取存档信息"""
        if not slot_data:
            return {
                'day_value': None,
                'is_epilogue': False,
                'finished_count': 0,
                'save_date': None,
                'subtitle_text': None
            }
        
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
                day_epilogue_value = int(day_epilogue)
                if day_epilogue_value != 0:
                    day_value = day_epilogue_value
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
            start_index = day_value * 3
            day_finished = finished[start_index:start_index + 3] if start_index < len(finished) else []
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
        
        return {
            'day_value': day_value,
            'is_epilogue': is_epilogue,
            'finished_count': finished_count,
            'save_date': save_date,
            'subtitle_text': subtitle_text
        }
    
    def _format_save_item(self, slot_data: Optional[Dict[str, Any]], index: int) -> str:
        """格式化存档项显示文本"""
        if not slot_data:
            return self.translate("tyrano_no_save")
        
        info = self._extract_save_info(slot_data)
        parts = []
        
        if info['day_value'] is not None:
            if info['is_epilogue']:
                day_text = self.translate("tyrano_epilogue_day_label").format(day=info['day_value'])
            else:
                day_text = self.translate("tyrano_day_label").format(day=info['day_value'])
            parts.append(day_text)
        else:
            parts.append("")
        
        if not info['is_epilogue'] and info['day_value'] is not None:
            circles = "".join("●" if i < info['finished_count'] else "○" for i in range(3))
            parts.append(circles)
        else:
            parts.append("")
        
        parts.append(info['save_date'] if info['save_date'] else "")
        parts.append(info['subtitle_text'] if info['subtitle_text'] else "")
        
        result = " · ".join(p for p in parts if p)
        return self.translate("tyrano_no_save") if not result or result.strip() == "" else result
    
    def _on_order_changed(self, new_order: List[int]) -> None:
        """顺序改变回调"""
        self._current_order = new_order
    
    def _check_dirty(self) -> bool:
        """检查是否有未保存的更改"""
        return self._original_order != self._current_order
    
    def _on_close(self) -> None:
        """关闭对话框事件处理"""
        if self._check_dirty():
            result = askyesno_relative(
                self.dialog,
                self.translate("warning"),
                self.translate("unsaved_changes_warning")
            )
            if not result:
                return
        
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.destroy()
    
    def _show_preview(self) -> None:
        """显示预览窗口"""
        from src.modules.save_analysis.tyrano.preview_dialog import TyranoPreviewDialog
        
        changed_pages = self._calculate_changed_pages()
        
        if not changed_pages:
            showinfo_relative(
                self.dialog,
                self.translate("info"),
                self.translate("tyrano_reorder_preview_empty")
            )
            return
        
        TyranoPreviewDialog(
            self.dialog,
            self._save_slots,
            self._original_order,
            self._current_order,
            changed_pages,
            self.translate,
            self.get_cjk_font,
            self.Colors
        )
    
    def _calculate_changed_pages(self) -> List[int]:
        """计算发生变动的页面"""
        from src.modules.save_analysis.tyrano.constants import TYRANO_SAVES_PER_PAGE
        
        changed_pages = []
        total_pages = (len(self._save_slots) + TYRANO_SAVES_PER_PAGE - 1) // TYRANO_SAVES_PER_PAGE
        
        for page_num in range(total_pages):
            start = page_num * TYRANO_SAVES_PER_PAGE
            end = start + TYRANO_SAVES_PER_PAGE
            
            original_page = self._original_order[start:end]
            new_page = self._current_order[start:end]
            
            if original_page != new_page:
                changed_pages.append(page_num + 1)
        
        return changed_pages
    
    def _save_order(self) -> None:
        """保存重排序结果"""
        if not self._check_dirty():
            showinfo_relative(
                self.dialog,
                self.translate("info"),
                self.translate("tyrano_reorder_no_changes")
            )
            return
        
        # 确认对话框
        result = askyesno_relative(
            self.dialog,
            self.translate("tyrano_reorder_save_confirm_title"),
            self.translate("tyrano_reorder_save_confirm_text")
        )
        
        if not result:
            return
        
        try:
            if self.analyzer.reorder_slots(self._current_order):
                showinfo_relative(
                    self.dialog,
                    self.translate("info"),
                    self.translate("tyrano_reorder_save_success")
                )
                
                self._original_order = self._current_order.copy()
                
                if self.on_save_callback:
                    self.on_save_callback()
                
                if self.dialog and self.dialog.winfo_exists():
                    self.dialog.destroy()
            else:
                showwarning_relative(
                    self.dialog,
                    self.translate("error"),
                    self.translate("tyrano_reorder_save_failed")
                )
        except Exception as e:
            logger.error("Failed to save reorder: %s", e, exc_info=True)
            showwarning_relative(
                self.dialog,
                self.translate("error"),
                self.translate("tyrano_reorder_save_failed")
            )

