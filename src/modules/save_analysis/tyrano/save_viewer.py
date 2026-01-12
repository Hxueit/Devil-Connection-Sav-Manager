"""存档查看器主UI模块

提供Tyrano存档查看器的主UI类，包括分页显示、图片加载和导航功能
"""

import json
import logging
import threading
import tkinter as tk
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import filedialog
from typing import Dict, Any, Optional, Callable, List, Tuple, Final, TYPE_CHECKING

import customtkinter as ctk
from PIL import Image

if TYPE_CHECKING:
    from src.modules.save_analysis.tyrano.analyzer import TyranoAnalyzer

from src.modules.save_analysis.tyrano.constants import (
    TYRANO_ROWS_PER_PAGE,
    TYRANO_SAVES_PER_PAGE,
)
from src.modules.save_analysis.tyrano.image_cache import ImageCache
from src.modules.save_analysis.tyrano.save_slot import (
    TyranoSaveSlot,
    IMGDATA_FIELD_KEY,
    DEFAULT_THUMBNAIL_SIZE,
    LABEL_PADDING_X,
    LABEL_PADDING_Y,
    THUMBNAIL_HEIGHT_RATIO,
    THUMBNAIL_MAX_WIDTH_RATIO,
    THUMBNAIL_MIN_SIZE,
)
from src.modules.save_analysis.tyrano.image_utils import decode_image_data, ASPECT_RATIO_4_3
from src.utils.ui_utils import (
    showwarning_relative,
    showinfo_relative,
    showerror_relative,
    askyesno_relative
)

logger = logging.getLogger(__name__)

RESIZE_DEBOUNCE_MS: Final[int] = 200
PAGE_SWITCH_DEBOUNCE_MS: Final[int] = 150
BUTTON_WIDTH: Final[int] = 60
BUTTON_HEIGHT: Final[int] = 30
ENTRY_WIDTH: Final[int] = 80
PAGE_INFO_WIDTH: Final[int] = 60
CORNER_RADIUS: Final[int] = 8
FONT_SIZE_SMALL: Final[int] = 10
FONT_SIZE_MEDIUM: Final[int] = 12
PADDING_SMALL: Final[int] = 5
PADDING_MEDIUM: Final[int] = 10
SEPARATOR_WIDTH: Final[int] = 3
MIN_PAGE_NUMBER: Final[int] = 1
EMPTY_PAGE_TEXT: Final[str] = "0/0"
MIN_CONTAINER_SIZE: Final[int] = 1
DEFAULT_CONTAINER_WIDTH: Final[int] = 300
DEFAULT_CONTAINER_HEIGHT: Final[int] = 150


class TyranoSaveViewer:
    """Tyrano存档查看器主UI类"""
    
    def __init__(
        self,
        parent: ctk.CTkFrame,
        analyzer: "TyranoAnalyzer",
        translation_func: Callable[[str], str],
        get_cjk_font_func: Callable[[int], Any],
        colors_class: type,
        root_window: tk.Widget
    ) -> None:
        """初始化查看器
        
        Args:
            parent: 父容器
            analyzer: TyranoAnalyzer实例
            translation_func: 翻译函数
            get_cjk_font_func: 字体获取函数
            colors_class: 颜色常量类
            root_window: 根窗口（用于显示对话框）
        """
        self.parent: ctk.CTkFrame = parent
        self.analyzer: "TyranoAnalyzer" = analyzer
        self.translate: Callable[[str], str] = translation_func
        self.get_cjk_font: Callable[[int], Any] = get_cjk_font_func
        self.Colors: type = colors_class
        self.root_window: tk.Widget = root_window
        
        self.slot_widgets: List[TyranoSaveSlot] = []
        self._resize_timer: Optional[str] = None
        self._is_first_load: bool = True
        self._image_cache: ImageCache = ImageCache()
        self._placeholder_cache: Dict[Tuple[Tuple[int, int], str], Image.Image] = {}
        self._circle_cache: Dict[Tuple[int, bool], Image.Image] = {}
        
        self._main_container: Optional[ctk.CTkFrame] = None
        self._separator: Optional[tk.Frame] = None
        self._slot_widgets_pool: List[TyranoSaveSlot] = []
        self._column_frames: List[ctk.CTkFrame] = []
        self._nav_frame: Optional[ctk.CTkFrame] = None
        
        self._preload_executor: Optional[ThreadPoolExecutor] = None
        self._preload_in_progress = False
        self._prefetch_in_progress = False
        
        self._current_page_load_id = 0
        self._page_switch_timer: Optional[str] = None
        self._is_destroyed = False
        self._post_init_refresh_pending = False
        self._post_init_refresh_attempts = 0
        self._loading_overlay: Optional[ctk.CTkFrame] = None
        self._loading_label: Optional[ctk.CTkLabel] = None
        self._loading_visible = False
        self._last_parent_size: Optional[Tuple[int, int]] = None
        
        self._create_ui()
        self._refresh_display()
        self._schedule_post_init_refresh()
        self._start_background_preload()
    
    def cleanup(self) -> None:
        """清理资源"""
        logger.debug("清理TyranoSaveViewer资源")
        
        self._is_destroyed = True
        self._preload_in_progress = False
        self._current_page_load_id += 1000
        
        self._cancel_timer(self._page_switch_timer)
        self._cancel_timer(self._resize_timer)
        
        if self._preload_executor:
            try:
                self._preload_executor.shutdown(wait=False, cancel_futures=True)
            except (RuntimeError, AttributeError) as e:
                logger.debug("关闭预加载执行器时出错: %s", e)
            finally:
                self._preload_executor = None
        
        self._clear_slot_widgets()
        self._clear_caches()
        self._destroy_loading_overlay()
    
    def _cancel_timer(self, timer_id: Optional[str]) -> None:
        """取消定时器"""
        if not timer_id:
            return
        try:
            if self.parent.winfo_exists():
                self.parent.after_cancel(timer_id)
        except (tk.TclError, ValueError, AttributeError):
            pass
    
    def _clear_slot_widgets(self) -> None:
        """清理存档槽组件引用"""
        for slot_widget in self.slot_widgets:
            if hasattr(slot_widget, '_prepared_ctk_image'):
                slot_widget._prepared_ctk_image = None
            
            if hasattr(slot_widget, '_image_label') and slot_widget._image_label:
                if slot_widget._image_label.winfo_exists():
                    try:
                        slot_widget._image_label.configure(image=None, text="")
                    except (tk.TclError, AttributeError):
                        pass
    
    def _clear_caches(self) -> None:
        """清理缓存"""
        self._image_cache = None
        self._placeholder_cache.clear()
        self._circle_cache.clear()

    def _show_loading_overlay(self) -> None:
        """显示加载遮罩，避免逐步渲染"""
        if self._is_destroyed:
            return
        if not self.slots_frame or not self.slots_frame.winfo_exists():
            return

        if self._loading_overlay and self._loading_overlay.winfo_exists():
            try:
                self._loading_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
                self._loading_overlay.lift()
                if self._loading_label and self._loading_label.winfo_exists():
                    self._loading_label.configure(text=self.translate("loading"))
                self._loading_visible = True
            except (tk.TclError, AttributeError):
                pass
            return

        try:
            overlay = ctk.CTkFrame(self.slots_frame, fg_color=self.Colors.WHITE)
            overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
            label = ctk.CTkLabel(
                overlay,
                text=self.translate("loading"),
                font=self.get_cjk_font(FONT_SIZE_MEDIUM),
                text_color=self.Colors.TEXT_SECONDARY,
                fg_color="transparent"
            )
            label.place(relx=0.5, rely=0.5, anchor="center")
            self._loading_overlay = overlay
            self._loading_label = label
            self._loading_visible = True
        except (tk.TclError, AttributeError):
            pass

    def _hide_loading_overlay(self) -> None:
        """隐藏加载遮罩"""
        if not self._loading_overlay or not self._loading_overlay.winfo_exists():
            self._loading_visible = False
            return
        try:
            self._loading_overlay.place_forget()
        except (tk.TclError, AttributeError):
            pass
        self._loading_visible = False

    def _destroy_loading_overlay(self) -> None:
        """销毁加载遮罩资源"""
        if self._loading_overlay and self._loading_overlay.winfo_exists():
            try:
                self._loading_overlay.destroy()
            except (tk.TclError, AttributeError):
                pass
        self._loading_overlay = None
        self._loading_label = None
        self._loading_visible = False
    
    def _create_ui(self) -> None:
        """创建UI布局"""
        main_container = ctk.CTkFrame(self.parent, fg_color=self.Colors.WHITE)
        main_container.pack(fill="both", expand=True, padx=PADDING_MEDIUM, pady=PADDING_MEDIUM)
        main_container.pack_propagate(False)
        
        self.slots_frame = ctk.CTkFrame(main_container, fg_color=self.Colors.WHITE)
        self.slots_frame.pack(fill="both", expand=True)
        self.slots_frame.pack_propagate(False)
        
        self._create_navigation(main_container)
    
    def _create_navigation(self, parent: ctk.CTkFrame) -> None:
        """创建翻页导航栏"""
        nav_frame = ctk.CTkFrame(parent, fg_color=self.Colors.WHITE)
        nav_frame.pack(side="bottom", fill="x", pady=PADDING_MEDIUM)
        self._nav_frame = nav_frame
        
        nav_center_frame = ctk.CTkFrame(nav_frame, fg_color=self.Colors.WHITE)
        nav_center_frame.pack(anchor="center")
        
        self._create_page_buttons(nav_center_frame)
        self._create_page_info_label(nav_center_frame)
        self._create_jump_controls(nav_center_frame)
        self._create_import_button(nav_frame)
        self._create_refresh_button(nav_frame)
        self._create_reorder_button(nav_frame)
        self._create_auto_saves_button(nav_frame)
    
    def _create_page_buttons(self, parent: ctk.CTkFrame) -> None:
        """创建翻页按钮"""
        button_config = self._get_standard_button_config()
        
        self.prev_button = ctk.CTkButton(
            parent,
            text=self.translate("prev_page"),
            command=self._go_to_prev_page,
            **button_config
        )
        self.prev_button.pack(side="left", padx=PADDING_SMALL)
        
        self.next_button = ctk.CTkButton(
            parent,
            text=self.translate("next_page"),
            command=self._go_to_next_page,
            **button_config
        )
        self.next_button.pack(side="left", padx=PADDING_SMALL)
    
    def _create_page_info_label(self, parent: ctk.CTkFrame) -> None:
        """创建页码显示标签"""
        self.page_info_label = ctk.CTkLabel(
            parent,
            text="1/1",
            font=self.get_cjk_font(FONT_SIZE_MEDIUM),
            fg_color="transparent",
            text_color=self.Colors.TEXT_PRIMARY,
            width=PAGE_INFO_WIDTH,
            anchor="center"
        )
        self.page_info_label.pack(side="left", padx=PADDING_MEDIUM)
    
    def _create_jump_controls(self, parent: ctk.CTkFrame) -> None:
        """创建页面跳转控件"""
        jump_frame = ctk.CTkFrame(parent, fg_color=self.Colors.WHITE)
        jump_frame.pack(side="left", padx=20)
        
        self.jump_label = ctk.CTkLabel(
            jump_frame,
            text=self.translate("jump_to_page"),
            font=self.get_cjk_font(FONT_SIZE_SMALL),
            fg_color="transparent",
            text_color=self.Colors.TEXT_PRIMARY
        )
        self.jump_label.pack(side="left", padx=PADDING_SMALL)
        
        self.jump_entry = ctk.CTkEntry(
            jump_frame,
            width=ENTRY_WIDTH,
            height=BUTTON_HEIGHT,
            corner_radius=CORNER_RADIUS,
            fg_color=self.Colors.WHITE,
            text_color=self.Colors.TEXT_PRIMARY,
            border_color=self.Colors.GRAY,
            font=self.get_cjk_font(FONT_SIZE_SMALL)
        )
        self.jump_entry.pack(side="left", padx=PADDING_SMALL)
        self.jump_entry.bind('<Return>', self._on_jump_entry_return)
        
        self.jump_button = ctk.CTkButton(
            jump_frame,
            text=self.translate("jump"),
            command=self._jump_to_page,
            width=BUTTON_WIDTH,
            height=BUTTON_HEIGHT,
            corner_radius=CORNER_RADIUS,
            fg_color=self.Colors.WHITE,
            hover_color=self.Colors.LIGHT_GRAY,
            border_width=1,
            border_color=self.Colors.GRAY,
            text_color=self.Colors.TEXT_PRIMARY,
            font=self.get_cjk_font(FONT_SIZE_SMALL)
        )
        self.jump_button.pack(side="left", padx=PADDING_SMALL)
    
    def _get_standard_button_config(self) -> Dict[str, Any]:
        """获取标准按钮配置"""
        return {
            'width': BUTTON_WIDTH,
            'height': BUTTON_HEIGHT,
            'corner_radius': CORNER_RADIUS,
            'fg_color': self.Colors.WHITE,
            'hover_color': self.Colors.LIGHT_GRAY,
            'border_width': 1,
            'border_color': self.Colors.GRAY,
            'text_color': self.Colors.TEXT_PRIMARY,
            'font': self.get_cjk_font(FONT_SIZE_SMALL)
        }
    
    def _create_reorder_button(self, parent: ctk.CTkFrame) -> None:
        """创建重排序按钮"""
        self.reorder_button = ctk.CTkButton(
            parent,
            text=self.translate("tyrano_reorder_button"),
            command=self._open_reorder_dialog,
            **self._get_standard_button_config()
        )
        self.reorder_button.pack(side="right", padx=PADDING_SMALL)
    
    def _create_refresh_button(self, parent: ctk.CTkFrame) -> None:
        """创建刷新按钮"""
        self.refresh_button = ctk.CTkButton(
            parent,
            text=self.translate("refresh"),
            command=self.refresh,
            **self._get_standard_button_config()
        )
        self.refresh_button.pack(side="right", padx=PADDING_SMALL)
    
    def _create_auto_saves_button(self, parent: ctk.CTkFrame) -> None:
        """创建自动存档按钮"""
        self.auto_saves_button = ctk.CTkButton(
            parent,
            text=self.translate("tyrano_auto_saves_button"),
            command=self._on_auto_saves_click,
            **self._get_standard_button_config()
        )
        self.auto_saves_button.pack(side="right", padx=PADDING_SMALL)
    
    def _on_auto_saves_click(self) -> None:
        """自动存档按钮点击事件"""
        from src.modules.save_analysis.tyrano.auto_saves_dialog import TyranoAutoSavesDialog
        
        if not hasattr(self.analyzer, 'storage_dir') or not self.analyzer.storage_dir:
            return
        
        storage_dir = str(self.analyzer.storage_dir)
        
        TyranoAutoSavesDialog(
            self.parent,
            self.root_window,
            storage_dir,
            self.translate,
            self.get_cjk_font,
            self.Colors
        )
    
    def _create_import_button(self, parent: ctk.CTkFrame) -> None:
        """创建导入按钮"""
        self.import_button = ctk.CTkButton(
            parent,
            text=self.translate("tyrano_import_button"),
            command=self._on_import_click,
            **self._get_standard_button_config()
        )
        self.import_button.pack(side="left", padx=PADDING_SMALL)
    
    def _open_reorder_dialog(self) -> None:
        """打开重排序对话框"""
        from src.modules.save_analysis.tyrano.reorder_dialog import TyranoReorderDialog
        
        dialog = TyranoReorderDialog(
            self.parent,
            self.root_window,
            self.analyzer,
            self.translate,
            self.get_cjk_font,
            self.Colors,
            on_save_callback=self.refresh
        )
    
    def _try_decode_content(self, content: str) -> Dict[str, Any]:
        """尝试URL解码并解析JSON内容
        
        Args:
            content: 文件内容字符串
            
        Returns:
            解析后的JSON字典
            
        Raises:
            json.JSONDecodeError: 如果无法解析为JSON
        """
        try:
            decoded = urllib.parse.unquote(content)
            return json.loads(decoded)
        except json.JSONDecodeError:
            return json.loads(content)
    
    def _extract_save_info_for_import(self, slot_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """提取存档信息用于导入确认显示
        
        Args:
            slot_data: 存档槽数据字典
            
        Returns:
            包含存档信息的字典
        """
        if not slot_data:
            return {
                'day_value': None,
                'is_epilogue': False,
                'finished_count': 0,
                'save_date': None,
                'subtitle_text': None
            }
        
        stat = slot_data.get('stat', {}) or {}
        if not isinstance(stat, dict):
            stat = {}
        
        f = stat.get('f', {}) or {}
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
    
    def _format_save_item_for_import(self, slot_data: Optional[Dict[str, Any]]) -> str:
        """格式化存档项显示文本用于导入确认
        
        Args:
            slot_data: 存档槽数据字典
            
        Returns:
            格式化后的显示文本
        """
        if not slot_data:
            return ""
        
        info = self._extract_save_info_for_import(slot_data)
        parts = []
        
        if info['day_value'] is not None:
            day_key = "tyrano_epilogue_day_label" if info['is_epilogue'] else "tyrano_day_label"
            day_text = self.translate(day_key).format(day=info['day_value'])
            parts.append(day_text)
        
        if not info['is_epilogue'] and info['day_value'] is not None:
            circles = "".join("●" if i < info['finished_count'] else "○" for i in range(3))
            parts.append(circles)
        
        if info['save_date']:
            parts.append(info['save_date'])
        
        if info['subtitle_text']:
            parts.append(info['subtitle_text'])
        
        return " · ".join(parts) if parts else ""
    
    def _validate_and_format_import_data(self, slot_data: Dict[str, Any]) -> Tuple[bool, str]:
        """验证并格式化导入的存档数据
        
        Args:
            slot_data: 存档槽数据字典
            
        Returns:
            (是否有效, 格式化后的显示文本)
        """
        if not isinstance(slot_data, dict):
            return False, ""
        
        formatted_text = self._format_save_item_for_import(slot_data)
        return True, formatted_text
    
    def _on_import_click(self) -> None:
        """导入按钮点击事件处理"""
        file_path = filedialog.askopenfilename(
            parent=self.root_window,
            title=self.translate("tyrano_import_dialog_title"),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            if not content:
                self._show_import_warning("tyrano_import_invalid_format")
                return
            
            try:
                slot_data = self._try_decode_content(content)
            except json.JSONDecodeError as e:
                logger.error("解析JSON失败: %s", e)
                self._show_import_warning("tyrano_import_invalid_format")
                return
            
            is_valid, formatted_text = self._validate_and_format_import_data(slot_data)
            
            if not is_valid:
                self._show_import_warning("tyrano_import_invalid_format")
                return
            
            file_name = Path(file_path).name
            line_count = len(content.splitlines())
            file_info = self.translate("tyrano_import_file_info").format(
                filename=file_name,
                lines=line_count
            )
            
            if formatted_text:
                confirm_message = self.translate("tyrano_import_confirm").format(
                    file_info=file_info,
                    info=formatted_text
                )
            else:
                confirm_message = self.translate("tyrano_import_confirm_unknown_with_file").format(
                    file_info=file_info
                )
            
            result = askyesno_relative(
                self.root_window,
                self.translate("tyrano_import_dialog_title"),
                confirm_message
            )
            
            if not result:
                return
            
            if self.analyzer.import_slot(slot_data):
                showinfo_relative(
                    self.root_window,
                    self.translate("info"),
                    self.translate("tyrano_import_success")
                )
                self.refresh()
            else:
                self._show_import_error("")
                
        except FileNotFoundError:
            self._show_import_warning("tyrano_import_invalid_format")
        except PermissionError as e:
            self._show_import_error(str(e))
        except Exception as e:
            logger.error("导入存档槽失败: %s", e, exc_info=True)
            self._show_import_error(str(e))
    
    def _show_import_warning(self, message_key: str) -> None:
        """显示导入警告消息
        
        Args:
            message_key: 翻译键
        """
        showwarning_relative(
            self.root_window,
            self.translate("warning"),
            self.translate(message_key)
        )
    
    def _show_import_error(self, error_msg: str) -> None:
        """显示导入错误消息
        
        Args:
            error_msg: 错误消息
        """
        showerror_relative(
            self.root_window,
            self.translate("error"),
            self.translate("tyrano_import_failed").format(error=error_msg)
        )
    
    def _on_jump_entry_return(self, event: tk.Event) -> None:
        """跳转输入框回车事件处理"""
        self._jump_to_page()
    
    def _clear_slots_frame(self) -> None:
        """清除存档槽显示区域的所有组件"""
        for widget in self.slots_frame.winfo_children():
            widget.destroy()
        self.slot_widgets.clear()
        self._slot_widgets_pool.clear()
        self._column_frames.clear()
        self._main_container = None
        self._separator = None
    
    def _setup_grid_container(self) -> ctk.CTkFrame:
        """设置网格布局容器"""
        main_container = ctk.CTkFrame(self.slots_frame, fg_color=self.Colors.WHITE)
        main_container.pack(fill="both", expand=True, padx=PADDING_MEDIUM, pady=PADDING_SMALL)
        main_container.grid_propagate(False)
        
        main_container.grid_columnconfigure(0, weight=1, uniform="column")
        main_container.grid_columnconfigure(1, weight=0, minsize=SEPARATOR_WIDTH)
        main_container.grid_columnconfigure(2, weight=1, uniform="column")
        
        for row in range(TYRANO_ROWS_PER_PAGE):
            main_container.grid_rowconfigure(row, weight=1)
        
        return main_container
    
    def _create_separator(self, parent: ctk.CTkFrame) -> tk.Frame:
        """创建中间分隔线"""
        separator = tk.Frame(
            parent,
            width=SEPARATOR_WIDTH,
            bg="gray",
            relief="sunken"
        )
        separator.grid(row=0, column=1, rowspan=TYRANO_ROWS_PER_PAGE, sticky="ns", padx=PADDING_MEDIUM)
        return separator
    
    def _create_slot_widget(
        self,
        parent_frame: ctk.CTkFrame,
        slot_data: Optional[Dict[str, Any]],
        global_index: int
    ) -> ctk.CTkFrame:
        """创建存档槽组件"""
        return self._create_filled_slot(parent_frame, slot_data, global_index)
    
    def _create_filled_slot(
        self,
        parent_frame: ctk.CTkFrame,
        slot_data: Dict[str, Any],
        global_index: int
    ) -> ctk.CTkFrame:
        """创建有数据的存档槽组件"""
        storage_dir = str(self.analyzer.storage_dir) if hasattr(self.analyzer, 'storage_dir') else ""
        slot_widget = TyranoSaveSlot(
            parent_frame,
            slot_data,
            global_index,
            self.translate,
            self.get_cjk_font,
            self.Colors,
            self._on_slot_click,
            root_window=self.root_window,
            storage_dir=storage_dir,
            on_data_changed=self.refresh
        )
        slot_widget._create_widget()
        self.slot_widgets.append(slot_widget)
        
        if len(self._slot_widgets_pool) < TYRANO_SAVES_PER_PAGE:
            self._slot_widgets_pool.append(slot_widget)
        
        container = slot_widget.get_container()
        if container:
            container.pack(fill="both", expand=True)
            return container
        
        return parent_frame
    
    def _create_slots_grid(self) -> None:
        """创建存档槽网格布局"""
        page_slots = self.analyzer.get_current_page_slots()
        base_index = (self.analyzer.current_page - MIN_PAGE_NUMBER) * TYRANO_SAVES_PER_PAGE
        
        if self._main_container and self._main_container.winfo_exists():
            self._update_slots_with_images(page_slots, base_index)
        else:
            self._main_container = self._setup_grid_container()
            self._separator = self._create_separator(self._main_container)
            
            for row in range(TYRANO_ROWS_PER_PAGE):
                self._create_row_slots(self._main_container, page_slots, base_index, row)
            
            self._load_all_images()
    
    def _pool_index_to_page_index(self, pool_index: int) -> int:
        """将widget池索引转换为页面槽位索引"""
        row = pool_index // 2
        column = pool_index % 2
        return row + column * TYRANO_ROWS_PER_PAGE
    
    def _update_slots_with_images(
        self,
        page_slots: List[Optional[Dict[str, Any]]],
        base_index: int
    ) -> None:
        """更新存档槽数据并加载图片"""
        self._current_page_load_id += 1
        current_load_id = self._current_page_load_id
        
        if len(self._slot_widgets_pool) < TYRANO_SAVES_PER_PAGE:
            logger.warning("存档槽组件池不足，重新创建组件")
            self._clear_slots_frame()
            
            self._main_container = self._setup_grid_container()
            self._separator = self._create_separator(self._main_container)
            
            for row in range(TYRANO_ROWS_PER_PAGE):
                self._create_row_slots(self._main_container, page_slots, base_index, row)
            
            self._load_all_images()
            return
        
        self._ensure_layout_ready()
        reference_size = self._calculate_reference_size()
        self._show_loading_overlay()
        
        for i, slot_widget in enumerate(self._slot_widgets_pool[:TYRANO_SAVES_PER_PAGE]):
            page_index = self._pool_index_to_page_index(i)
            slot_data = page_slots[page_index] if page_index < len(page_slots) else None
            global_index = base_index + page_index
            slot_widget.update_slot_data(slot_data, global_index)
            slot_widget._image_hash = None
            slot_widget._prepared_ctk_image = None
        
        self.slot_widgets = self._slot_widgets_pool[:TYRANO_SAVES_PER_PAGE]
        
        tasks = self._prepare_image_tasks(reference_size)
        
        def process_and_update():
            if self._is_destroyed or current_load_id != self._current_page_load_id:
                return
            
            processed_results = self._process_images_sync(tasks)
            
            if self._is_destroyed or current_load_id != self._current_page_load_id:
                return
            
            def apply_updates():
                if self._is_destroyed or current_load_id != self._current_page_load_id:
                    return
                if not self.parent.winfo_exists():
                    return
                
                try:
                    if not self._should_apply_updates(current_load_id):
                        return
                    
                    updates = self._create_ui_updates(processed_results)
                    
                    if not self._should_apply_updates(current_load_id):
                        return
                    
                    should_repack = False
                    if self.slots_frame.winfo_exists() and not self._loading_visible:
                        self.slots_frame.pack_forget()
                        should_repack = True
                    
                    self._clear_text_frames()
                    
                    if not self._should_apply_updates(current_load_id):
                        return
                    
                    self._create_all_text_labels_hidden(reference_size)
                    self._sync_layout()
                    self._apply_ui_updates(updates)
                    
                    if not self._should_apply_updates(current_load_id):
                        return
                    
                    self._hide_loading_overlay()
                    
                    if should_repack and self.slots_frame.winfo_exists():
                        self.slots_frame.pack(fill="both", expand=True)
                    
                    if self._is_first_load and not self._is_destroyed:
                        self._is_first_load = False
                        if self.parent.winfo_exists():
                            self.parent.bind("<Configure>", self._on_window_resize)

                    self._prefetch_adjacent_pages()
                except (tk.TclError, AttributeError):
                    pass
            
            if not self._is_destroyed and self.parent.winfo_exists():
                try:
                    self.parent.after(0, apply_updates)
                except (tk.TclError, AttributeError):
                    pass
        
        thread = threading.Thread(target=process_and_update, daemon=True)
        thread.start()
    
    def _should_apply_updates(self, load_id: int) -> bool:
        """检查是否应该应用更新"""
        return not self._is_destroyed and self._current_page_load_id == load_id
    
    def _clear_text_frames(self) -> None:
        """清理文本框架"""
        for slot_widget in self.slot_widgets:
            if self._is_destroyed:
                return
            if slot_widget._text_frame and slot_widget._text_frame.winfo_exists():
                for widget in slot_widget._text_frame.winfo_children():
                    widget.destroy()
    
    def _calculate_size_from_parent_container(self) -> Optional[Tuple[int, int]]:
        """从父容器计算尺寸"""
        if not self.slots_frame:
            return None
        
        try:
            frame_width = self.slots_frame.winfo_width()
            frame_height = self.slots_frame.winfo_height()

            if frame_width > MIN_CONTAINER_SIZE and frame_height > MIN_CONTAINER_SIZE:
                parent_width = frame_width
                parent_height = frame_height
            elif self.slots_frame.master:
                parent_width = self.slots_frame.master.winfo_width()
                parent_height = self.slots_frame.master.winfo_height()

                nav_height = 0
                if self._nav_frame and self._nav_frame.winfo_exists():
                    nav_height = self._nav_frame.winfo_height()
                    if nav_height <= MIN_CONTAINER_SIZE:
                        nav_height = self._nav_frame.winfo_reqheight()

                if nav_height > 0:
                    parent_height = max(MIN_CONTAINER_SIZE, parent_height - nav_height - PADDING_MEDIUM * 2)
            else:
                return None
            
            if parent_width <= MIN_CONTAINER_SIZE or parent_height <= MIN_CONTAINER_SIZE:
                return None
            
            available_width = parent_width - PADDING_MEDIUM * 2
            available_height = parent_height - PADDING_SMALL * 2
            
            column_width = (available_width - SEPARATOR_WIDTH - PADDING_MEDIUM * 2) // 2
            row_height = available_height // TYRANO_ROWS_PER_PAGE
            
            if column_width > MIN_CONTAINER_SIZE and row_height > MIN_CONTAINER_SIZE:
                return (column_width, row_height)
        except (tk.TclError, AttributeError):
            pass
        
        return None
    
    def _calculate_size_from_existing_widgets(self) -> Optional[Tuple[int, int]]:
        """从已创建的容器获取平均尺寸"""
        valid_sizes: List[Tuple[int, int]] = []
        
        for slot_widget in self.slot_widgets:
            if not slot_widget.container or not slot_widget.container.winfo_exists():
                continue
            
            try:
                width = slot_widget.container.winfo_reqwidth()
                height = slot_widget.container.winfo_reqheight()
                if width > MIN_CONTAINER_SIZE and height > MIN_CONTAINER_SIZE:
                    valid_sizes.append((width, height))
            except (tk.TclError, AttributeError):
                continue
        
        if not valid_sizes:
            return None
        
        count = len(valid_sizes)
        avg_width = sum(w for w, _ in valid_sizes) // count
        avg_height = sum(h for _, h in valid_sizes) // count
        
        return (avg_width, avg_height)
    
    def _calculate_reference_size(self) -> Optional[Tuple[int, int]]:
        """计算参考尺寸"""
        size = self._calculate_size_from_parent_container()
        if size:
            return size
        
        size = self._calculate_size_from_existing_widgets()
        if size:
            return size
        
        return (DEFAULT_CONTAINER_WIDTH, DEFAULT_CONTAINER_HEIGHT)

    def _calculate_thumbnail_size_for_container(
        self,
        container_width: int,
        container_height: int,
        original_image: Optional[Image.Image] = None,
        aspect_ratio: Optional[float] = None
    ) -> Tuple[int, int]:
        """计算缩略图尺寸（与存档槽一致的规则）"""
        if container_width <= 0 or container_height <= 0:
            return DEFAULT_THUMBNAIL_SIZE

        max_width = int(container_width * THUMBNAIL_MAX_WIDTH_RATIO) - LABEL_PADDING_X * 2
        max_height = int(container_height * THUMBNAIL_HEIGHT_RATIO) - LABEL_PADDING_Y * 2

        available_width = max(max_width, THUMBNAIL_MIN_SIZE)
        available_height = max(max_height, THUMBNAIL_MIN_SIZE)

        if original_image:
            orig_width, orig_height = original_image.size
            ratio = (orig_width / orig_height) if orig_height > 0 else ASPECT_RATIO_4_3
        elif aspect_ratio is not None:
            ratio = aspect_ratio
        else:
            ratio = ASPECT_RATIO_4_3

        width_by_height = int(available_height * ratio)
        height_by_width = int(available_width / ratio)

        if width_by_height <= available_width:
            return (width_by_height, available_height)
        return (available_width, height_by_width)

    def _ensure_layout_ready(self) -> None:
        """确保在读取尺寸前完成几何布局计算"""
        if self._is_destroyed:
            return
        if not self.parent or not self.parent.winfo_exists():
            return
        
        try:
            if (
                self._is_first_load
                or self.parent.winfo_width() <= MIN_CONTAINER_SIZE
                or self.parent.winfo_height() <= MIN_CONTAINER_SIZE
            ):
                self.parent.update_idletasks()
        except (tk.TclError, AttributeError):
            pass

    def _sync_layout(self) -> None:
        """在文本或组件变更后强制更新几何布局"""
        if self._is_destroyed:
            return
        
        try:
            if self.slots_frame and self.slots_frame.winfo_exists():
                self.slots_frame.update_idletasks()
            elif self.parent and self.parent.winfo_exists():
                self.parent.update_idletasks()
        except (tk.TclError, AttributeError):
            pass

    def _schedule_post_init_refresh(self) -> None:
        """在布局映射后刷新一次以修正初始尺寸"""
        if self._is_destroyed or self._post_init_refresh_pending:
            return
        self._post_init_refresh_pending = True
        self._post_init_refresh_attempts = 0
        self._post_init_refresh_step()

    def _post_init_refresh_step(self) -> None:
        """尝试延迟刷新直到组件被映射"""
        if self._is_destroyed:
            self._post_init_refresh_pending = False
            return
        if self._post_init_refresh_attempts >= 5:
            self._post_init_refresh_pending = False
            return
        self._post_init_refresh_attempts += 1

        def _try_refresh() -> None:
            if self._is_destroyed:
                self._post_init_refresh_pending = False
                return
            if not self.parent or not self.parent.winfo_exists():
                self._post_init_refresh_pending = False
                return
            try:
                target_widget = self.slots_frame if self.slots_frame and self.slots_frame.winfo_exists() else self.parent
                if (
                    not target_widget.winfo_ismapped()
                    or target_widget.winfo_width() <= MIN_CONTAINER_SIZE
                    or target_widget.winfo_height() <= MIN_CONTAINER_SIZE
                ):
                    self._post_init_refresh_step()
                    return
            except (tk.TclError, AttributeError):
                self._post_init_refresh_pending = False
                return

            self._ensure_layout_ready()
            self._refresh_display()
            self._post_init_refresh_pending = False

        try:
            if self.parent.winfo_exists():
                self.parent.after(120, _try_refresh)
            else:
                self._post_init_refresh_pending = False
        except (tk.TclError, AttributeError):
            self._post_init_refresh_pending = False
    
    def _get_container_size_for_slot(
        self,
        slot_widget: TyranoSaveSlot,
        reference_size: Optional[Tuple[int, int]]
    ) -> Tuple[int, int]:
        """获取存档槽的容器尺寸"""
        if reference_size:
            return reference_size
        
        if slot_widget.container and slot_widget.container.winfo_exists():
            try:
                width = slot_widget.container.winfo_reqwidth()
                height = slot_widget.container.winfo_reqheight()
                if width > MIN_CONTAINER_SIZE and height > MIN_CONTAINER_SIZE:
                    return (width, height)
            except (tk.TclError, AttributeError):
                pass
        
        return (DEFAULT_CONTAINER_WIDTH, DEFAULT_CONTAINER_HEIGHT)
    
    def _prepare_image_tasks(self, reference_size: Optional[Tuple[int, int]]) -> List[Tuple[TyranoSaveSlot, Optional[str], int, int]]:
        """准备图片处理任务"""
        tasks: List[Tuple[TyranoSaveSlot, Optional[str], int, int]] = []
        
        for slot_widget in self.slot_widgets:
            if not slot_widget._image_label:
                continue
            
            container_width, container_height = self._get_container_size_for_slot(
                slot_widget,
                reference_size
            )
            
            image_data = None
            if slot_widget.slot_data:
                image_data = slot_widget.slot_data.get(IMGDATA_FIELD_KEY)
            
            tasks.append((slot_widget, image_data, container_width, container_height))
        
        return tasks
    
    def _process_images_sync(
        self, 
        tasks: List[Tuple[TyranoSaveSlot, Optional[str], int, int]]
    ) -> Dict[TyranoSaveSlot, Tuple[Optional[Image.Image], Optional[str]]]:
        """同步处理所有图片"""
        if not tasks:
            return {}
        
        processed_results: Dict[TyranoSaveSlot, Tuple[Optional[Image.Image], Optional[str]]] = {}
        
        for slot_widget, image_data, container_width, container_height in tasks:
            try:
                pil_image, placeholder_text = slot_widget._process_image_worker(
                    image_data,
                    container_width,
                    container_height,
                    self._image_cache,
                    self._placeholder_cache
                )
                processed_results[slot_widget] = (pil_image, placeholder_text)
            except (ValueError, OSError, AttributeError) as e:
                logger.debug("处理存档槽 %d 的图片失败: %s", slot_widget.slot_index, e)
                placeholder_text = slot_widget.translate("tyrano_image_decode_failed")
                processed_results[slot_widget] = (None, placeholder_text)
        
        return processed_results
    
    def _create_ctk_image_from_pil(self, pil_image: Image.Image) -> Optional[ctk.CTkImage]:
        """从PIL Image创建CTkImage"""
        if not pil_image:
            return None
        
        try:
            image_size = (pil_image.width, pil_image.height)
            return ctk.CTkImage(
                light_image=pil_image,
                dark_image=pil_image,
                size=image_size
            )
        except (AttributeError, TypeError) as e:
            logger.debug("创建CTkImage失败: %s", e, exc_info=True)
            return None
    
    def _determine_placeholder_text(
        self,
        slot_widget: TyranoSaveSlot,
        has_image_data: bool,
        decode_failed: bool
    ) -> str:
        """确定占位符文本"""
        if decode_failed:
            return slot_widget.translate("tyrano_image_decode_failed")
        return slot_widget.translate("tyrano_no_imgdata")
    
    def _create_ui_updates(
        self,
        processed_results: Dict[TyranoSaveSlot, Tuple[Optional[Image.Image], Optional[str]]]
    ) -> List[Tuple[ctk.CTkLabel, Optional[ctk.CTkImage], Optional[str], Optional[Tuple[int, int]]]]:
        """创建UI更新列表"""
        updates: List[Tuple[ctk.CTkLabel, Optional[ctk.CTkImage], Optional[str], Optional[Tuple[int, int]]]] = []
        
        for slot_widget in self.slot_widgets:
            if not slot_widget._image_label:
                continue
            
            if slot_widget not in processed_results:
                placeholder_text = slot_widget.translate("tyrano_no_imgdata")
                updates.append((slot_widget._image_label, None, placeholder_text, None))
                continue
            
            pil_image, placeholder_text = processed_results[slot_widget]
            image_size = (pil_image.width, pil_image.height) if pil_image else None
            
            if pil_image and not placeholder_text:
                ctk_image = self._create_ctk_image_from_pil(pil_image)
                if ctk_image:
                    updates.append((slot_widget._image_label, ctk_image, None, image_size))
                else:
                    placeholder_text = slot_widget.translate("tyrano_image_decode_failed")
                    updates.append((slot_widget._image_label, None, placeholder_text, image_size))
            else:
                if not placeholder_text:
                    has_image_data = bool(
                        slot_widget.slot_data and 
                        slot_widget.slot_data.get(IMGDATA_FIELD_KEY)
                    )
                    placeholder_text = self._determine_placeholder_text(
                        slot_widget,
                        has_image_data,
                        decode_failed=bool(pil_image is None and has_image_data)
                    )
                updates.append((slot_widget._image_label, None, placeholder_text, image_size))
        
        return updates
    
    def _configure_label_with_image(
        self,
        label: ctk.CTkLabel,
        ctk_image: ctk.CTkImage,
        image_size: Optional[Tuple[int, int]]
    ) -> None:
        """配置标签显示图片"""
        if not label or not label.winfo_exists():
            return
        
        base_config = {
            "image": ctk_image,
            "text": "",
            "fg_color": "transparent"
        }
        
        if image_size:
            base_config["width"] = image_size[0]
            base_config["height"] = image_size[1]
        
        try:
            label.configure(**base_config)
        except (tk.TclError, AttributeError) as e:
            logger.debug("配置标签图片失败: %s", e)
    
    def _get_cached_placeholder_ctk_image(
        self,
        placeholder_size: Tuple[int, int],
        placeholder_text: str
    ) -> ctk.CTkImage:
        """获取缓存的占位图CTkImage对象"""
        from src.modules.save_analysis.tyrano.image_utils import create_placeholder_image
        
        cache_key = (placeholder_size, placeholder_text)
        if cache_key not in self._placeholder_cache:
            placeholder_img = create_placeholder_image(placeholder_size, placeholder_text)
            self._placeholder_cache[cache_key] = placeholder_img
        else:
            placeholder_img = self._placeholder_cache[cache_key]
        
        return ctk.CTkImage(
            light_image=placeholder_img,
            dark_image=placeholder_img,
            size=placeholder_size
        )
    
    def _configure_label_with_placeholder(
        self,
        label: ctk.CTkLabel,
        placeholder_text: str,
        image_size: Optional[Tuple[int, int]]
    ) -> None:
        """配置标签显示占位符"""
        if not label or not label.winfo_exists():
            return
        
        placeholder_size = image_size if image_size else (120, 90)
        placeholder_ctk_img = self._get_cached_placeholder_ctk_image(placeholder_size, placeholder_text)
        
        base_config = {
            "image": placeholder_ctk_img,
            "text": "",
            "fg_color": "transparent"
        }
        
        if image_size:
            base_config["width"] = image_size[0]
            base_config["height"] = image_size[1]
        
        try:
            label.configure(**base_config)
        except (tk.TclError, AttributeError) as e:
            logger.debug("配置标签占位符失败: %s", e)
    
    def _apply_ui_updates(self, updates: List[Tuple[ctk.CTkLabel, Optional[ctk.CTkImage], Optional[str], Optional[Tuple[int, int]]]]) -> None:
        """批量更新UI组件"""
        for label, ctk_image, placeholder_text, image_size in updates:
            if not label or not label.winfo_exists():
                continue
            
            try:
                if ctk_image:
                    self._configure_label_with_image(label, ctk_image, image_size)
                else:
                    display_text = placeholder_text or ""
                    self._configure_label_with_placeholder(label, display_text, image_size)
            except (tk.TclError, AttributeError) as e:
                logger.debug("更新标签失败: %s", e)
                continue
    
    def _load_all_images(self) -> None:
        """批量加载所有存档槽的图片"""
        if not self.slot_widgets:
            return
        
        self._current_page_load_id += 1
        current_load_id = self._current_page_load_id
        
        self._ensure_layout_ready()
        reference_size = self._calculate_reference_size()
        self._show_loading_overlay()
        tasks = self._prepare_image_tasks(reference_size)
        
        def process_and_update():
            if self._is_destroyed or current_load_id != self._current_page_load_id:
                return
            
            processed_results = self._process_images_sync(tasks)
            
            if self._is_destroyed or current_load_id != self._current_page_load_id:
                return
            
            def apply_updates():
                if not self._should_apply_updates(current_load_id):
                    return
                if not self.parent.winfo_exists():
                    return
                
                try:
                    if not self._should_apply_updates(current_load_id):
                        return
                    
                    updates = self._create_ui_updates(processed_results)
                    
                    if not self._should_apply_updates(current_load_id):
                        return
                    
                    self._create_all_text_labels_hidden(reference_size)
                    self._sync_layout()
                    self._apply_ui_updates(updates)
                    self._hide_loading_overlay()
                    
                    if self._is_first_load and not self._is_destroyed:
                        self._is_first_load = False
                        if self.parent.winfo_exists():
                            self.parent.bind("<Configure>", self._on_window_resize)

                    self._prefetch_adjacent_pages()
                except (tk.TclError, AttributeError):
                    pass
            
            if not self._is_destroyed and self.parent.winfo_exists():
                try:
                    self.parent.after(0, apply_updates)
                except (tk.TclError, AttributeError):
                    pass
        
        thread = threading.Thread(target=process_and_update, daemon=True)
        thread.start()
    
    def _create_all_text_labels_hidden(self, reference_size: Optional[Tuple[int, int]]) -> None:
        """批量创建所有信息面板"""
        for slot_widget in self.slot_widgets:
            slot_widget._create_info_panel(self._circle_cache)
    
    def _create_row_slots(
        self,
        main_container: ctk.CTkFrame,
        page_slots: List[Optional[Dict[str, Any]]],
        base_index: int,
        row: int
    ) -> None:
        """创建一行的左右两个存档槽"""
        left_page_index = row
        right_page_index = row + TYRANO_ROWS_PER_PAGE
        
        page_slots_len = len(page_slots)
        left_slot_data = page_slots[left_page_index] if left_page_index < page_slots_len else None
        right_slot_data = page_slots[right_page_index] if right_page_index < page_slots_len else None
        
        left_frame = self._create_column_frame(main_container, row, 0, (0, PADDING_SMALL))
        right_frame = self._create_column_frame(main_container, row, 2, (PADDING_SMALL, 0))
        
        if len(self._column_frames) < (row + 1) * 2:
            self._column_frames.extend([left_frame, right_frame])
        else:
            self._column_frames[row * 2] = left_frame
            self._column_frames[row * 2 + 1] = right_frame
        
        self._create_slot_widget(left_frame, left_slot_data, base_index + left_page_index)
        self._create_slot_widget(right_frame, right_slot_data, base_index + right_page_index)
    
    def _create_column_frame(
        self,
        parent: ctk.CTkFrame,
        row: int,
        column: int,
        padx: Tuple[int, int]
    ) -> ctk.CTkFrame:
        """创建列容器Frame"""
        column_frame = ctk.CTkFrame(parent, fg_color=self.Colors.WHITE)
        column_frame.grid(row=row, column=column, sticky="nsew", padx=padx, pady=PADDING_SMALL)
        return column_frame
    
    def _refresh_display(self) -> None:
        """刷新显示"""
        self._create_slots_grid()
        self._update_navigation()
    
    def _update_navigation(self) -> None:
        """更新导航栏状态"""
        total_pages = self.analyzer.total_pages
        current_page = self.analyzer.current_page

        if total_pages > 0:
            page_text = f"{current_page}/{total_pages}"
            prev_state = "normal"
            next_state = "normal"
        else:
            page_text = EMPTY_PAGE_TEXT
            prev_state = "disabled"
            next_state = "disabled"

        self.page_info_label.configure(text=page_text)
        self.prev_button.configure(state=prev_state)
        self.next_button.configure(state=next_state)
    
    def _go_to_prev_page(self) -> None:
        """跳转到上一页"""
        if self.analyzer.go_to_prev_page():
            self._refresh_display_debounced()
    
    def _go_to_next_page(self) -> None:
        """跳转到下一页"""
        if self.analyzer.go_to_next_page():
            self._refresh_display_debounced()
    
    def _refresh_display_debounced(self) -> None:
        """防抖刷新显示"""
        if not self.parent or not self.parent.winfo_exists():
            return
        
        if self._page_switch_timer:
            try:
                self.parent.after_cancel(self._page_switch_timer)
            except (tk.TclError, ValueError):
                pass
        
        self._page_switch_timer = self.parent.after(
            PAGE_SWITCH_DEBOUNCE_MS,
            self._refresh_display
        )
    
    def _jump_to_page(self) -> None:
        """跳转到指定页面"""
        page_input = self.jump_entry.get().strip()
        if not page_input:
            return
        
        try:
            target_page = int(page_input)
        except ValueError:
            showwarning_relative(
                self.root_window,
                self.translate("warning"),
                self.translate("invalid_page_input"),
                parent=self.parent
            )
            return
        
        total_pages = self.analyzer.total_pages
        if target_page < MIN_PAGE_NUMBER:
            showwarning_relative(
                self.root_window,
                self.translate("warning"),
                self.translate("invalid_page_number").format(
                    min=MIN_PAGE_NUMBER,
                    max=total_pages if total_pages > 0 else MIN_PAGE_NUMBER
                ),
                parent=self.parent
            )
            return
        
        if total_pages > 0 and target_page > total_pages:
            showwarning_relative(
                self.root_window,
                self.translate("warning"),
                self.translate("invalid_page_number").format(
                    min=MIN_PAGE_NUMBER,
                    max=total_pages
                ),
                parent=self.parent
            )
            return
        
        if self.analyzer.set_page(target_page):
            self._refresh_display_debounced()
            self.jump_entry.delete(0, "end")
    
    def _on_slot_click(self, slot_index: int) -> None:
        """存档槽点击事件"""
        logger.debug("存档槽被点击: %d", slot_index)
    
    def _on_window_resize(self, event: Optional[tk.Event] = None) -> None:
        """窗口大小变化时的回调"""
        if not self.parent or not self.parent.winfo_exists():
            return
        
        try:
            current_size = (self.parent.winfo_width(), self.parent.winfo_height())
        except (tk.TclError, AttributeError):
            return

        if self._last_parent_size == current_size:
            return
        
        self._last_parent_size = current_size

        if self._resize_timer and self.parent.winfo_exists():
            try:
                self.parent.after_cancel(self._resize_timer)
            except (tk.TclError, ValueError):
                pass
        
        if self.parent.winfo_exists():
            self._resize_timer = self.parent.after(
                RESIZE_DEBOUNCE_MS,
                self._refresh_display
            )
    
    def update_ui_texts(self) -> None:
        """更新UI文本（用于语言切换）"""
        if hasattr(self, 'prev_button') and self.prev_button.winfo_exists():
            self.prev_button.configure(text=self.translate("prev_page"))
        
        if hasattr(self, 'next_button') and self.next_button.winfo_exists():
            self.next_button.configure(text=self.translate("next_page"))
        
        if hasattr(self, 'jump_label') and self.jump_label.winfo_exists():
            self.jump_label.configure(text=self.translate("jump_to_page"))
        
        if hasattr(self, 'jump_button') and self.jump_button.winfo_exists():
            self.jump_button.configure(text=self.translate("jump"))
        
        if hasattr(self, 'import_button') and self.import_button.winfo_exists():
            self.import_button.configure(text=self.translate("tyrano_import_button"))
        
        if hasattr(self, 'reorder_button') and self.reorder_button.winfo_exists():
            self.reorder_button.configure(text=self.translate("tyrano_reorder_button"))
        
        if hasattr(self, 'refresh_button') and self.refresh_button.winfo_exists():
            self.refresh_button.configure(text=self.translate("refresh"))
        
        if hasattr(self, 'auto_saves_button') and self.auto_saves_button.winfo_exists():
            self.auto_saves_button.configure(text=self.translate("tyrano_auto_saves_button"))

        if self._loading_label and self._loading_label.winfo_exists():
            self._loading_label.configure(text=self.translate("loading"))
        
        self._refresh_display()
    
    def refresh(self) -> None:
        """刷新整个视图"""
        self.analyzer.load_save_file()
        self._refresh_display()
        self._start_background_preload()
    
    def _start_background_preload(self) -> None:
        """启动后台预加载所有缩略图"""
        if self._is_destroyed or self._preload_in_progress:
            return
        self._preload_in_progress = True

        self._ensure_layout_ready()
        reference_size = self._calculate_reference_size()
        container_width, container_height = reference_size

        def preload_worker():
            try:
                if self._is_destroyed or not self.analyzer.save_slots:
                    return
                
                import hashlib
                for slot_data in self.analyzer.save_slots:
                    if self._is_destroyed:
                        return
                    
                    if not slot_data:
                        continue
                    
                    image_data = slot_data.get(IMGDATA_FIELD_KEY)
                    if not image_data:
                        continue
                    
                    img_hash = hashlib.md5(image_data.encode('utf-8')).hexdigest()
                    
                    try:
                        original_image = self._image_cache.get_original(img_hash)
                        if original_image is None:
                            original_image = decode_image_data(image_data)
                            if not original_image:
                                continue
                            self._image_cache.put_original(img_hash, original_image)

                        thumb_size = self._calculate_thumbnail_size_for_container(
                            container_width,
                            container_height,
                            original_image
                        )

                        if self._image_cache.get_thumbnail(img_hash, thumb_size):
                            continue

                        self._preload_single_thumbnail(
                            image_data,
                            img_hash,
                            thumb_size,
                            original_image=original_image
                        )
                    except (ValueError, OSError, AttributeError) as e:
                        logger.debug("预加载缩略图失败: %s", e)
                
            except Exception as e:
                logger.debug("后台预加载失败: %s", e)
            finally:
                self._preload_in_progress = False
        
        thread = threading.Thread(target=preload_worker, daemon=True)
        thread.start()
    
    def _preload_single_thumbnail(
        self,
        image_data: str,
        img_hash: str,
        thumb_size: Tuple[int, int],
        original_image: Optional[Image.Image] = None
    ) -> None:
        """预加载单个缩略图"""
        try:
            if self._image_cache.get_thumbnail(img_hash, thumb_size):
                return
            
            if original_image is None:
                original_image = decode_image_data(image_data)
            if not original_image:
                return
            
            if self._image_cache.get_original(img_hash) is None:
                self._image_cache.put_original(img_hash, original_image)
            thumbnail = original_image.resize(thumb_size, Image.Resampling.BILINEAR)
            self._image_cache.put_thumbnail(img_hash, thumb_size, thumbnail)
            
        except (ValueError, OSError, AttributeError) as e:
            logger.debug("预加载缩略图失败: %s", e)
    
    def _prefetch_adjacent_pages(self) -> None:
        """预取邻近页面的缩略图"""
        if self._is_destroyed or self._prefetch_in_progress:
            return
        if self._preload_in_progress:
            return
        if not self.analyzer or not self.analyzer.save_slots:
            return

        current_page = self.analyzer.current_page
        total_pages = self.analyzer.total_pages
        if current_page < MIN_PAGE_NUMBER or total_pages <= MIN_PAGE_NUMBER:
            return

        pages_to_prefetch: List[int] = []
        if current_page > MIN_PAGE_NUMBER:
            pages_to_prefetch.append(current_page - 1)
        if current_page < total_pages:
            pages_to_prefetch.append(current_page + 1)
        if not pages_to_prefetch:
            return

        self._ensure_layout_ready()
        reference_size = self._calculate_reference_size()
        container_width, container_height = reference_size
        self._prefetch_in_progress = True

        def prefetch_worker() -> None:
            try:
                import hashlib
                slots = self.analyzer.save_slots
                slots_len = len(slots)
                for page in pages_to_prefetch:
                    if self._is_destroyed:
                        return

                    start_index = (page - MIN_PAGE_NUMBER) * TYRANO_SAVES_PER_PAGE
                    if start_index >= slots_len:
                        continue

                    end_index = min(start_index + TYRANO_SAVES_PER_PAGE, slots_len)
                    for slot_data in slots[start_index:end_index]:
                        if self._is_destroyed:
                            return
                        if not slot_data:
                            continue
                        image_data = slot_data.get(IMGDATA_FIELD_KEY)
                        if not image_data:
                            continue

                        img_hash = hashlib.md5(image_data.encode('utf-8')).hexdigest()
                        try:
                            original_image = self._image_cache.get_original(img_hash)
                            if original_image is None:
                                original_image = decode_image_data(image_data)
                                if not original_image:
                                    continue
                                self._image_cache.put_original(img_hash, original_image)

                            thumb_size = self._calculate_thumbnail_size_for_container(
                                container_width,
                                container_height,
                                original_image
                            )

                            if self._image_cache.get_thumbnail(img_hash, thumb_size):
                                continue

                            self._preload_single_thumbnail(
                                image_data,
                                img_hash,
                                thumb_size,
                                original_image=original_image
                            )
                        except (ValueError, OSError, AttributeError) as e:
                            logger.debug("预取缩略图失败: %s", e)
                            continue
            finally:
                self._prefetch_in_progress = False

        thread = threading.Thread(target=prefetch_worker, daemon=True)
        thread.start()
