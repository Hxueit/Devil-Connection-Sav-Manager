"""存档槽UI组件模块

提供单个存档槽的UI显示和交互功能
"""

import hashlib
import json
import logging
import re
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog
from typing import Dict, Any, Optional, Callable, Tuple, Final

import customtkinter as ctk
from PIL import Image

from src.modules.save_analysis.tyrano.image_cache import ImageCache
from src.modules.save_analysis.tyrano.image_utils import (
    decode_image_data,
    create_placeholder_image,
    create_status_circle_image,
    ASPECT_RATIO_4_3,
)

logger = logging.getLogger(__name__)

IMGDATA_FIELD_KEY: Final[str] = 'img_data'
LABEL_PADDING_X: Final[int] = 10
LABEL_PADDING_Y: Final[int] = 10
FONT_SIZE: Final[int] = 10
CORNER_RADIUS: Final[int] = 8
BORDER_WIDTH: Final[int] = 2
THUMBNAIL_HEIGHT_RATIO: Final[float] = 0.85
THUMBNAIL_MAX_WIDTH_RATIO: Final[float] = 0.35
THUMBNAIL_MIN_SIZE: Final[int] = 80
DEFAULT_THUMBNAIL_SIZE: Final[Tuple[int, int]] = (120, 90)
PLACEHOLDER_COLOR: Final[str] = 'lightgray'
TEXT_COLOR_GRAY: Final[str] = 'gray'
CIRCLE_DIAMETER_MIN: Final[int] = 12
CIRCLE_DIAMETER_MAX: Final[int] = 18
CIRCLE_DIAMETER_DEFAULT: Final[int] = 15
CIRCLE_WIDTH_RATIO: Final[float] = 0.10
CIRCLE_PADDING: Final[int] = 2
DATE_COLOR: Final[str] = "#000000"
SUBTITLE_COLOR: Final[str] = "#2EA6B6"
BUTTON_WIDTH: Final[int] = 30
BUTTON_HEIGHT: Final[int] = 20
BUTTON_FONT_SIZE: Final[int] = 9
BUTTON_PADDING: Final[int] = 2


class TyranoSaveSlot:
    """存档槽UI组件"""
    
    def __init__(
        self,
        parent: ctk.CTkFrame,
        slot_data: Optional[Dict[str, Any]],
        slot_index: int,
        translation_func: Callable[[str], str],
        get_cjk_font_func: Callable[[int], Any],
        colors_class: type,
        on_click: Optional[Callable[[int], None]] = None,
        root_window: Optional[tk.Widget] = None,
        storage_dir: Optional[str] = None
    ) -> None:
        """初始化存档槽
        
        Raises:
            ValueError: 当slot_index小于0时
        """
        if slot_index < 0:
            raise ValueError(f"slot_index must be non-negative, got {slot_index}")
        
        self.parent: ctk.CTkFrame = parent
        self.slot_data: Optional[Dict[str, Any]] = slot_data
        self.slot_index: int = slot_index
        self.translate: Callable[[str], str] = translation_func
        self.get_cjk_font: Callable[[int], Any] = get_cjk_font_func
        self.Colors: type = colors_class
        self.on_click: Optional[Callable[[int], None]] = on_click
        self.root_window: Optional[tk.Widget] = root_window
        self.storage_dir: Optional[str] = storage_dir
        self.container: Optional[ctk.CTkFrame] = None
        self._image_label: Optional[ctk.CTkLabel] = None
        self._prepared_ctk_image: Optional[ctk.CTkImage] = None
        self._image_hash: Optional[str] = None
        self._text_frame: Optional[ctk.CTkFrame] = None
        self._text_label: Optional[ctk.CTkTextbox] = None
        self._info_panel_created: bool = False
        self._button_frame: Optional[ctk.CTkFrame] = None
    
    def _is_empty_save(self) -> bool:
        """判断存档是否为空存档（NO SAVE类型）"""
        if not self.slot_data:
            return True
        
        title = self.slot_data.get('title', '')
        save_date = self.slot_data.get('save_date', '')
        img_data = self.slot_data.get(IMGDATA_FIELD_KEY, '')
        stat = self.slot_data.get('stat', {})
        
        is_no_save = (
            title == "NO SAVE" or
            (save_date == "" and img_data == "" and isinstance(stat, dict) and len(stat) == 0)
        )
        
        return is_no_save
    
    def _extract_save_info(self) -> Dict[str, Any]:
        """提取存档信息"""
        if not self.slot_data:
            return {
                'day_value': None,
                'is_epilogue': False,
                'finished_count': 0,
                'save_date': None,
                'subtitle_text': None
            }
        
        stat = self.slot_data.get('stat', {})
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
        
        save_date = self.slot_data.get('save_date')
        save_date = str(save_date) if save_date is not None else None
        
        subtitle = self.slot_data.get('subtitle')
        subtitle_text = self.slot_data.get('subtitleText')
        subtitle_text = str(subtitle_text) if (subtitle and subtitle_text) else None
        
        return {
            'day_value': day_value,
            'is_epilogue': is_epilogue,
            'finished_count': finished_count,
            'save_date': save_date,
            'subtitle_text': subtitle_text
        }
    
    def _get_image_hash(self) -> Optional[str]:
        """获取image_data的hash"""
        if self._image_hash is not None:
            return self._image_hash
        
        if not self.slot_data:
            return None
        
        image_data = self.slot_data.get(IMGDATA_FIELD_KEY)
        if not image_data:
            return None
        
        md5_hash = hashlib.md5()
        md5_hash.update(image_data.encode('utf-8'))
        self._image_hash = md5_hash.hexdigest()
        return self._image_hash
    
    def _normalize_container_size(
        self,
        container_width: int,
        container_height: int
    ) -> Tuple[int, int]:
        """规范化容器尺寸"""
        if container_width <= 0 or container_height <= 0:
            return DEFAULT_THUMBNAIL_SIZE
        return (container_width, container_height)
    
    def _calculate_available_size(
        self,
        container_width: int,
        container_height: int
    ) -> Tuple[int, int]:
        """计算可用尺寸（考虑内边距和比例限制）"""
        max_width = int(container_width * THUMBNAIL_MAX_WIDTH_RATIO) - LABEL_PADDING_X * 2
        max_height = int(container_height * THUMBNAIL_HEIGHT_RATIO) - LABEL_PADDING_Y * 2
        
        available_width = max(max_width, THUMBNAIL_MIN_SIZE)
        available_height = max(max_height, THUMBNAIL_MIN_SIZE)
        
        return (available_width, available_height)
    
    def _get_aspect_ratio(
        self,
        original_image: Optional[Image.Image],
        aspect_ratio: Optional[float]
    ) -> float:
        """获取宽高比"""
        if original_image:
            orig_width, orig_height = original_image.size
            if orig_height == 0:
                logger.warning("Original image has zero height, using default aspect ratio")
                return ASPECT_RATIO_4_3
            return orig_width / orig_height
        
        if aspect_ratio is not None:
            return aspect_ratio
        
        return ASPECT_RATIO_4_3
    
    def _calculate_fitted_size(
        self,
        available_width: int,
        available_height: int,
        aspect_ratio: float
    ) -> Tuple[int, int]:
        """计算适配尺寸（保持宽高比，确保完整显示）"""
        width_by_height = available_height * aspect_ratio
        height_by_width = available_width / aspect_ratio
        
        if width_by_height <= available_width:
            return (int(width_by_height), available_height)
        return (available_width, int(height_by_width))
    
    def _calculate_thumbnail_size(
        self,
        container_width: int,
        container_height: int,
        original_image: Optional[Image.Image] = None,
        aspect_ratio: Optional[float] = None
    ) -> Tuple[int, int]:
        """计算缩略图尺寸，确保图片完整显示在框内"""
        normalized_width, normalized_height = self._normalize_container_size(
            container_width,
            container_height
        )
        
        available_width, available_height = self._calculate_available_size(
            normalized_width,
            normalized_height
        )
        
        ratio = self._get_aspect_ratio(original_image, aspect_ratio)
        
        return self._calculate_fitted_size(available_width, available_height, ratio)
    
    def _create_widget(self) -> None:
        """创建存档槽UI组件"""
        self.container = ctk.CTkFrame(
            self.parent,
            fg_color=self.Colors.LIGHT_GRAY,
            corner_radius=CORNER_RADIUS,
            border_width=BORDER_WIDTH,
            border_color=self.Colors.GRAY
        )
        
        if not self._is_empty_save() and self.slot_data:
            self._create_action_buttons()
        
        content_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=LABEL_PADDING_X, pady=LABEL_PADDING_Y)
        
        image_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        image_frame.pack(side="left", fill="y", padx=(0, LABEL_PADDING_X))
        
        image_inner_frame = ctk.CTkFrame(image_frame, fg_color="transparent")
        image_inner_frame.pack(expand=True, fill="both")
        
        self._image_label = ctk.CTkLabel(
            image_inner_frame,
            text="",
            fg_color="transparent",
            width=DEFAULT_THUMBNAIL_SIZE[0],
            height=DEFAULT_THUMBNAIL_SIZE[1]
        )
        self._image_label.pack(fill="none")
        
        self._text_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        self._text_frame.pack(side="right", fill="both", expand=True)
        
        self._text_label = None
        
        self._bind_click_handlers()
    
    def _process_thumbnail_from_cache(
        self,
        img_hash: str,
        thumb_size: Tuple[int, int],
        cache: Optional[ImageCache]
    ) -> Optional[Image.Image]:
        """从缓存获取缩略图"""
        if cache:
            return cache.get_thumbnail(img_hash, thumb_size)
        return None
    
    def _process_original_image(
        self,
        img_hash: str,
        cache: Optional[ImageCache]
    ) -> Optional[Image.Image]:
        """处理原始图片（从缓存或解码）"""
        if cache:
            cached_original = cache.get_original(img_hash)
            if cached_original:
                return cached_original
        
        image_data = self.slot_data.get(IMGDATA_FIELD_KEY) if self.slot_data else None
        if not image_data:
            return None
        
        decoded_image = decode_image_data(image_data)
        
        if decoded_image and cache:
            cache.put_original(img_hash, decoded_image)
        
        return decoded_image
    
    def _get_placeholder_with_cache(
        self,
        thumb_size: Tuple[int, int],
        placeholder_text: str,
        placeholder_cache: Optional[Dict[Tuple[Tuple[int, int], str], Image.Image]]
    ) -> Image.Image:
        """获取占位图（带缓存）"""
        placeholder_key = (thumb_size, placeholder_text)
        if placeholder_cache and placeholder_key in placeholder_cache:
            return placeholder_cache[placeholder_key]
        
        display_image = create_placeholder_image(thumb_size, placeholder_text)
        
        if placeholder_cache is not None:
            placeholder_cache[placeholder_key] = display_image
        
        return display_image
    
    def _process_image_worker(
        self,
        image_data: Optional[str],
        container_width: int,
        container_height: int,
        cache: Optional[ImageCache] = None,
        placeholder_cache: Optional[Dict[Tuple[Tuple[int, int], str], Image.Image]] = None
    ) -> Tuple[Optional[Image.Image], Optional[str]]:
        """在工作线程中处理图片"""
        img_hash = self._get_image_hash()
        if not img_hash:
            thumb_size = self._calculate_thumbnail_size(container_width, container_height)
            placeholder_text = self.translate("tyrano_no_imgdata")
            display_image = self._get_placeholder_with_cache(thumb_size, placeholder_text, placeholder_cache)
            return display_image, placeholder_text
        
        original_image = self._process_original_image(img_hash, cache)
        
        if original_image is None:
            thumb_size = self._calculate_thumbnail_size(container_width, container_height)
            placeholder_text = self.translate("tyrano_image_decode_failed")
            display_image = self._get_placeholder_with_cache(thumb_size, placeholder_text, placeholder_cache)
            return display_image, placeholder_text
        
        thumb_size = self._calculate_thumbnail_size(container_width, container_height, original_image)
        
        cached_thumbnail = self._process_thumbnail_from_cache(img_hash, thumb_size, cache)
        if cached_thumbnail:
            return cached_thumbnail, None
        
        thumbnail = original_image.resize(thumb_size, Image.Resampling.BILINEAR)
        
        if cache:
            cache.put_thumbnail(img_hash, thumb_size, thumbnail)
        
        return thumbnail, None
    
    def _bind_click_handlers(self, label: Optional[tk.Widget] = None) -> None:
        """绑定点击事件处理器"""
        if not self.on_click or not self.container:
            return
        
        def handle_click(event: tk.Event) -> None:
            """处理点击事件"""
            if self.on_click:
                self.on_click(self.slot_index)
        
        self.container.bind("<Button-1>", handle_click)
        if label:
            label.bind("<Button-1>", handle_click)
        if self._text_frame:
            self._text_frame.bind("<Button-1>", handle_click)
    
    def _create_info_panel(self, circle_cache: Optional[Dict[Tuple[int, bool], Image.Image]] = None) -> None:
        """创建右侧信息面板"""
        if not self._text_frame or self._info_panel_created:
            return
        
        is_empty_slot = self.slot_data is None or self._is_empty_save()
        info = self._extract_save_info()
        
        if is_empty_slot:
            no_save_label = ctk.CTkLabel(
                self._text_frame,
                text=self.translate("tyrano_no_save"),
                font=self.get_cjk_font(FONT_SIZE),
                text_color=self.Colors.TEXT_PRIMARY,
                fg_color="transparent",
                anchor="w"
            )
            no_save_label.pack(side="top", anchor="w", pady=(0, 5))
            self._bind_click_handlers(no_save_label)
            self._info_panel_created = True
            return
        
        if info['day_value'] is not None:
            if info['is_epilogue']:
                day_text = self.translate("tyrano_epilogue_day_label").format(day=info['day_value'])
            else:
                day_text = self.translate("tyrano_day_label").format(day=info['day_value'])
        else:
            day_text = ""
        
        if day_text:
            day_label = ctk.CTkLabel(
                self._text_frame,
                text=day_text,
                font=self.get_cjk_font(FONT_SIZE),
                text_color=self.Colors.TEXT_PRIMARY,
                fg_color="transparent",
                anchor="w"
            )
            day_label.pack(side="top", anchor="w", pady=(0, 5))
            self._bind_click_handlers(day_label)
        
        if not info['is_epilogue']:
            circles_frame = ctk.CTkFrame(self._text_frame, fg_color="transparent")
            circles_frame.pack(side="top", anchor="w", pady=(0, 5))
            
            try:
                container_width = self._text_frame.winfo_width()
                if container_width > 0:
                    circle_diameter = max(
                        CIRCLE_DIAMETER_MIN,
                        min(CIRCLE_DIAMETER_MAX, int(container_width * CIRCLE_WIDTH_RATIO))
                    )
                else:
                    circle_diameter = CIRCLE_DIAMETER_DEFAULT
            except (tk.TclError, AttributeError):
                circle_diameter = CIRCLE_DIAMETER_DEFAULT
            
            finished_count = info['finished_count']
            for i in range(3):
                is_active = i < finished_count
                
                circle_img = create_status_circle_image(circle_diameter, is_active, circle_cache)
                
                ctk_circle_img = ctk.CTkImage(
                    light_image=circle_img,
                    dark_image=circle_img,
                    size=(circle_diameter + CIRCLE_PADDING, circle_diameter + CIRCLE_PADDING)
                )
                
                circle_label = ctk.CTkLabel(
                    circles_frame,
                    image=ctk_circle_img,
                    text="",
                    fg_color="transparent"
                )
                circle_label.pack(side="left", padx=5)
                self._bind_click_handlers(circle_label)
        
        if info['save_date']:
            date_label = ctk.CTkLabel(
                self._text_frame,
                text=info['save_date'],
                font=self.get_cjk_font(FONT_SIZE),
                text_color=DATE_COLOR,
                fg_color="transparent",
                anchor="w"
            )
            date_label.pack(side="top", anchor="w", pady=(0, 5))
            self._bind_click_handlers(date_label)
        
        if info['subtitle_text']:
            subtitle_label = ctk.CTkLabel(
                self._text_frame,
                text=info['subtitle_text'],
                font=self.get_cjk_font(FONT_SIZE),
                text_color=SUBTITLE_COLOR,
                fg_color="transparent",
                anchor="w"
            )
            subtitle_label.pack(side="top", anchor="w")
            self._bind_click_handlers(subtitle_label)
        
        self._info_panel_created = True
    
    def get_container(self) -> Optional[ctk.CTkFrame]:
        """获取容器组件"""
        return self.container
    
    def update_slot_data(self, new_slot_data: Optional[Dict[str, Any]], new_index: int) -> None:
        """更新存档槽数据（用于UI组件复用）"""
        self.slot_data = new_slot_data
        self.slot_index = new_index
        self._image_hash = None
        self._prepared_ctk_image = None
        self._info_panel_created = False
        
        if self.container and self.container.winfo_exists():
            if self._button_frame and self._button_frame.winfo_exists():
                self._button_frame.destroy()
                self._button_frame = None
            
            if not self._is_empty_save() and self.slot_data:
                self._create_action_buttons()
        
        if self._text_frame and self._text_frame.winfo_exists():
            for widget in self._text_frame.winfo_children():
                widget.destroy()
    
    def get_image_hash(self) -> Optional[str]:
        """获取图片哈希值（公开方法，供外部调用）"""
        return self._get_image_hash()
    
    def _create_action_buttons(self) -> None:
        """创建操作按钮（修改和导出）"""
        if not self.container:
            return
        
        self._button_frame = ctk.CTkFrame(
            self.container,
            fg_color="transparent"
        )
        self._button_frame.place(relx=1.0, rely=0.0, anchor="ne", x=-BUTTON_PADDING, y=BUTTON_PADDING)
        
        edit_button = ctk.CTkButton(
            self._button_frame,
            text=self.translate("tyrano_slot_edit_button"),
            width=BUTTON_WIDTH,
            height=BUTTON_HEIGHT,
            font=self.get_cjk_font(BUTTON_FONT_SIZE),
            fg_color=self.Colors.WHITE,
            hover_color=self.Colors.LIGHT_GRAY,
            text_color=self.Colors.TEXT_PRIMARY,
            border_width=1,
            border_color=self.Colors.GRAY,
            corner_radius=4,
            command=self._on_edit_click
        )
        edit_button.pack(side="left", padx=2)
        
        export_button = ctk.CTkButton(
            self._button_frame,
            text=self.translate("tyrano_slot_export_button"),
            width=BUTTON_WIDTH,
            height=BUTTON_HEIGHT,
            font=self.get_cjk_font(BUTTON_FONT_SIZE),
            fg_color=self.Colors.WHITE,
            hover_color=self.Colors.LIGHT_GRAY,
            text_color=self.Colors.TEXT_PRIMARY,
            border_width=1,
            border_color=self.Colors.GRAY,
            corner_radius=4,
            command=self._on_export_click
        )
        export_button.pack(side="left", padx=2)
    
    def _on_edit_click(self) -> None:
        """修改按钮点击事件"""
        if not self.slot_data or self._is_empty_save():
            from src.utils.ui_utils import showwarning_relative
            showwarning_relative(
                self.root_window if self.root_window else self.parent,
                self.translate("warning"),
                self.translate("tyrano_slot_no_data")
            )
            return
        
        if not self.root_window:
            logger.warning("root_window not provided, cannot open editor")
            return
        
        from src.modules.save_analysis.sf.save_file_viewer import SaveFileViewer, ViewerConfig
        
        title = self._generate_edit_title()
        
        collapsed_fields = [
            "stat.map_label",
            "stat.charas",
            "stat.map_keyframe",
            "stat.stack",
            "stat.popopo",
            "stat.map_macro",
            "stat.fuki"
        ]
        
        viewer_config = ViewerConfig(
            enable_edit_by_default=True,
            show_enable_edit_checkbox=False,
            show_collapse_checkbox=True,
            show_hint_label=True,
            title_key="save_file_viewer_title",
            collapsed_fields=collapsed_fields
        )
        
        viewer = SaveFileViewer(
            self.root_window,
            self.storage_dir or "",
            self.slot_data,
            self.translate,
            None,
            mode="file",
            viewer_config=viewer_config
        )
        
        if (hasattr(viewer, 'viewer_window') and
            viewer.viewer_window and
            viewer.viewer_window.winfo_exists()):
            viewer.viewer_window.title(title)
    
    def _on_export_click(self) -> None:
        """导出按钮点击事件"""
        if not self.slot_data or self._is_empty_save():
            from src.utils.ui_utils import showwarning_relative
            showwarning_relative(
                self.root_window if self.root_window else self.parent,
                self.translate("warning"),
                self.translate("tyrano_slot_no_data")
            )
            return
        
        if not self.root_window:
            logger.warning("root_window not provided, cannot export")
            return
        
        default_filename = self._generate_export_filename()
        
        file_path = filedialog.asksaveasfilename(
            parent=self.root_window,
            title=self.translate("tyrano_slot_export_dialog_title"),
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=default_filename
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.slot_data, f, ensure_ascii=False, indent=2)
            
            from src.utils.ui_utils import showinfo_relative
            showinfo_relative(
                self.root_window,
                self.translate("success"),
                self.translate("tyrano_export_success").format(path=file_path)
            )
        except Exception as e:
            logger.error(f"Failed to export save slot: {e}", exc_info=True)
            from src.utils.ui_utils import showerror_relative
            showerror_relative(
                self.root_window,
                self.translate("error"),
                self.translate("tyrano_export_failed").format(error=str(e))
            )
    
    def _generate_edit_title(self) -> str:
        """生成编辑窗口标题
        
        格式: "存档：{day}日目_{circles}_{date}_{subtitle}"
        circles: ●=实心(已完成), ○=空心(未完成)
        """
        info = self._extract_save_info()
        
        save_prefix = self.translate("tyrano_slot_edit_title_prefix")
        
        day_value = info.get('day_value')
        if day_value is not None:
            if info.get('is_epilogue', False):
                day_str = self.translate("tyrano_epilogue_day_label").format(day=day_value)
            else:
                day_str = self.translate("tyrano_day_label").format(day=day_value)
        else:
            day_str = self.translate("tyrano_day_label").format(day=0)
        
        finished_count = info.get('finished_count', 0)
        if not info.get('is_epilogue', False) and info.get('day_value') is not None:
            circles = "".join("●" if i < finished_count else "○" for i in range(3))
        else:
            circles = "○○○"
        
        save_date = info.get('save_date')
        date_str = ""
        if save_date:
            for fmt in ["%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%Y-%m-%d"]:
                try:
                    date_input = save_date.split()[0] if ' ' in save_date else save_date
                    dt = datetime.strptime(date_input, fmt)
                    date_str = dt.strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            
            if not date_str:
                date_str = save_date.split()[0].replace("/", "-") if save_date else ""
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")
        
        subtitle_text = info.get('subtitle_text')
        subtitle_str = subtitle_text if subtitle_text else ""
        
        parts = [day_str, circles, date_str]
        if subtitle_str:
            parts.append(subtitle_str)
        
        return f"{save_prefix}：{'_'.join(parts)}"
    
    def _generate_export_filename(self) -> str:
        """生成导出文件名
        
        格式: "{day}日目_{circles}_{date}_{subtitle}.json"
        circles: X=实心(已完成), O=空心(未完成)
        """
        info = self._extract_save_info()
        
        day_value = info.get('day_value')
        if day_value is not None:
            if info.get('is_epilogue', False):
                day_str = f"{day_value}日目"
            else:
                day_str = f"{day_value}日目"
        else:
            day_str = "0日目"
        
        finished_count = info.get('finished_count', 0)
        circles = "".join("X" if i < finished_count else "O" for i in range(3))
        
        save_date = info.get('save_date')
        date_str = ""
        if save_date:
            for fmt in ["%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%Y-%m-%d"]:
                try:
                    date_input = save_date.split()[0] if ' ' in save_date else save_date
                    dt = datetime.strptime(date_input, fmt)
                    date_str = dt.strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            
            if not date_str:
                date_str = save_date.split()[0].replace("/", "-") if save_date else ""
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")
        
        subtitle_text = info.get('subtitle_text')
        subtitle_str = ""
        if subtitle_text:
            subtitle_str = re.sub(r'[<>:"/\\|?*]', '_', subtitle_text)
        
        parts = [day_str, circles, date_str]
        if subtitle_str:
            parts.append(subtitle_str)
        
        filename = "_".join(parts) + ".json"
        return re.sub(r'[<>:"/\\|?*]', '_', filename)
