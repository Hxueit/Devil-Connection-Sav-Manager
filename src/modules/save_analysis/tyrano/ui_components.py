"""Tyrano存档分析UI组件

提供存档槽显示和翻页导航UI组件
"""

import logging
import base64
import hashlib
import os
import tkinter as tk
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from typing import Dict, Any, Optional, Callable, List, Tuple, Final, TYPE_CHECKING

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

if TYPE_CHECKING:
    from src.modules.save_analysis.tyrano.analyzer import TyranoAnalyzer

from src.modules.save_analysis.tyrano.constants import (
    TYRANO_ROWS_PER_PAGE,
    TYRANO_SAVES_PER_PAGE,
)
from src.utils.ui_utils import showwarning_relative

logger = logging.getLogger(__name__)

# 常量定义
_BASE64_SEPARATOR: Final[str] = ';base64,'
_ASPECT_RATIO_4_3: Final[float] = 4.0 / 3.0
_MIN_CONTAINER_SIZE: Final[int] = 1
_DEFAULT_CONTAINER_WIDTH: Final[int] = 300
_DEFAULT_CONTAINER_HEIGHT: Final[int] = 150
_TITLE_FIELD_KEY: Final[str] = 'title'
_IMGDATA_FIELD_KEY: Final[str] = 'img_data'
_L1_CACHE_MAX_SIZE: Final[int] = 50
_L2_CACHE_MAX_SIZE: Final[int] = 100
_DEFAULT_FONT_SIZE: Final[int] = 12


class ImageCache:
    """双层图片缓存（L1原始图片 + L2缩略图，LRU策略）"""
    
    def __init__(self, l1_max_size: int = _L1_CACHE_MAX_SIZE, l2_max_size: int = _L2_CACHE_MAX_SIZE) -> None:
        """初始化双层缓存
        
        Args:
            l1_max_size: L1缓存最大容量
            l2_max_size: L2缓存最大容量
        """
        if l1_max_size <= 0 or l2_max_size <= 0:
            raise ValueError("Cache size must be positive")
        
        self._l1_cache: OrderedDict[str, Image.Image] = OrderedDict()
        self._l1_max_size: int = l1_max_size
        self._l2_cache: OrderedDict[Tuple[str, Tuple[int, int]], Image.Image] = OrderedDict()
        self._l2_max_size: int = l2_max_size
    
    def get_original(self, img_hash: str) -> Optional[Image.Image]:
        """从L1缓存获取原始图片
        
        Args:
            img_hash: 图片数据的MD5哈希值
            
        Returns:
            缓存的原始PIL Image对象，如果不存在返回None
        """
        if not img_hash:
            return None
        
        image = self._l1_cache.get(img_hash)
        if image is not None:
            self._l1_cache.move_to_end(img_hash)
            return image
        return None
    
    def put_original(self, img_hash: str, image: Image.Image) -> None:
        """存入L1缓存（原始图片）
        
        Args:
            img_hash: 图片数据的MD5哈希值
            image: 原始PIL Image对象
        """
        if not img_hash or image is None:
            return
        
        if img_hash in self._l1_cache:
            self._l1_cache.move_to_end(img_hash)
            return
        
        if len(self._l1_cache) >= self._l1_max_size:
            self._l1_cache.popitem(last=False)
        
        self._l1_cache[img_hash] = image
    
    def get_thumbnail(self, img_hash: str, size: Tuple[int, int]) -> Optional[Image.Image]:
        """从L2缓存获取缩略图
        
        Args:
            img_hash: 图片数据的MD5哈希值
            size: 缩略图尺寸
            
        Returns:
            缓存的缩略图PIL Image对象，如果不存在返回None
        """
        if not img_hash or not size or size[0] <= 0 or size[1] <= 0:
            return None
        
        key = (img_hash, size)
        thumbnail = self._l2_cache.get(key)
        if thumbnail is not None:
            self._l2_cache.move_to_end(key)
            return thumbnail
        return None
    
    def put_thumbnail(self, img_hash: str, size: Tuple[int, int], image: Image.Image) -> None:
        """存入L2缓存（缩略图）
        
        Args:
            img_hash: 图片数据的MD5哈希值
            size: 缩略图尺寸
            image: 缩略图PIL Image对象
        """
        if not img_hash or not size or size[0] <= 0 or size[1] <= 0 or image is None:
            return
        
        key = (img_hash, size)
        
        if key in self._l2_cache:
            self._l2_cache.move_to_end(key)
            return
        
        if len(self._l2_cache) >= self._l2_max_size:
            self._l2_cache.popitem(last=False)
        
        self._l2_cache[key] = image
    
    def clear(self) -> None:
        """清空所有缓存"""
        self._l1_cache.clear()
        self._l2_cache.clear()


class TyranoSaveSlot:
    """存档槽UI组件"""
    
    _DEFAULT_WRAPLENGTH: Final[int] = 280
    _LABEL_PADDING_X: Final[int] = 10
    _LABEL_PADDING_Y: Final[int] = 10
    _FONT_SIZE: Final[int] = 10
    _CORNER_RADIUS: Final[int] = 8
    _BORDER_WIDTH: Final[int] = 2
    _THUMBNAIL_HEIGHT_RATIO: Final[float] = 0.85
    _THUMBNAIL_MAX_WIDTH_RATIO: Final[float] = 0.35
    _THUMBNAIL_MIN_SIZE: Final[int] = 80
    _DEFAULT_THUMBNAIL_SIZE: Final[Tuple[int, int]] = (120, 90)
    _FONT_SIZE_MIN: Final[int] = 10
    _FONT_SIZE_DIVISOR: Final[int] = 4
    _PLACEHOLDER_COLOR: Final[str] = 'lightgray'
    _TEXT_COLOR_GRAY: Final[str] = 'gray'
    
    def __init__(
        self,
        parent: ctk.CTkFrame,
        slot_data: Optional[Dict[str, Any]],
        slot_index: int,
        translation_func: Callable[[str], str],
        get_cjk_font_func: Callable[[int], Any],
        colors_class: type,
        on_click: Optional[Callable[[int], None]] = None
    ) -> None:
        """初始化存档槽
        
        Args:
            parent: 父容器
            slot_data: 存档槽数据
            slot_index: 存档槽索引
            translation_func: 翻译函数
            get_cjk_font_func: 字体获取函数
            colors_class: 颜色常量类
            on_click: 点击回调函数
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
        self.container: Optional[ctk.CTkFrame] = None
        self._image_label: Optional[ctk.CTkLabel] = None
        self._prepared_ctk_image: Optional[ctk.CTkImage] = None
        self._image_hash: Optional[str] = None
        self._text_frame: Optional[ctk.CTkFrame] = None
        self._text_label: Optional[ctk.CTkTextbox] = None  # 保留用于兼容性
        self._info_panel_created: bool = False  # 标记信息面板是否已创建
    
    def _is_empty_save(self) -> bool:
        """判断存档是否为空存档（NO SAVE类型）
        
        游戏会将形如以下格式的存档识别为空存档：
        {
          "title": "NO SAVE",
          "current_order_index": 0,
          "save_date": "",
          "img_data": "",
          "phase_file": "",
          "stat": {}
        }
        
        Returns:
            如果为空存档返回True，否则返回False
        """
        if not self.slot_data:
            return True
        
        # 检查是否为空存档的特征：
        # 1. title 为 "NO SAVE"
        # 2. save_date 为空字符串
        # 3. img_data 为空字符串
        # 4. stat 为空对象
        title = self.slot_data.get('title', '')
        save_date = self.slot_data.get('save_date', '')
        img_data = self.slot_data.get('img_data', '')
        stat = self.slot_data.get('stat', {})
        
        # 判断是否为空存档
        is_no_save = (
            title == "NO SAVE" or
            (save_date == "" and img_data == "" and isinstance(stat, dict) and len(stat) == 0)
        )
        
        return is_no_save
    
    def _extract_save_info(self) -> Dict[str, Any]:
        """提取存档信息
        
        Returns:
            包含存档信息的字典：
            - day_value: 日目值（int或None）
            - is_epilogue: 是否为后日谈（bool）
            - finished_count: 完成状态数量（0-3）
            - save_date: 存档日期（str或None）
            - subtitle_text: 副标题文本（str或None）
        """
        if not self.slot_data:
            return {
                'day_value': None,
                'is_epilogue': False,
                'finished_count': 0,
                'save_date': None,
                'subtitle_text': None
            }
        
        # 安全访问嵌套字典
        stat = self.slot_data.get('stat', {})
        if not isinstance(stat, dict):
            stat = {}
        
        f = stat.get('f', {})
        if not isinstance(f, dict):
            f = {}
        
        # 提取day和day_epilogue
        day_epilogue = f.get('day_epilogue')
        day = f.get('day')
        
        # 只有当day_epilogue不为0且存在时才使用它，否则使用day
        if day_epilogue is not None:
            try:
                day_epilogue_value = int(day_epilogue)
                # 只有当day_epilogue不为0时才使用
                if day_epilogue_value != 0:
                    day_value = day_epilogue_value
                    is_epilogue = True
                else:
                    # day_epilogue为0，使用day
                    if day is not None:
                        try:
                            day_value = int(day)
                            is_epilogue = False
                        except (ValueError, TypeError):
                            day_value = None
                            is_epilogue = False
                    else:
                        day_value = None
                        is_epilogue = False
            except (ValueError, TypeError):
                # day_epilogue转换失败，使用day
                if day is not None:
                    try:
                        day_value = int(day)
                        is_epilogue = False
                    except (ValueError, TypeError):
                        day_value = None
                        is_epilogue = False
                else:
                    day_value = None
                    is_epilogue = False
        elif day is not None:
            try:
                day_value = int(day)
                is_epilogue = False
            except (ValueError, TypeError):
                day_value = None
                is_epilogue = False
        else:
            day_value = None
            is_epilogue = False
        
        # 提取finished数组，使用finished.slice(day * 3)来判断当天的完成角色数
        finished = f.get('finished', [])
        if not isinstance(finished, list):
            finished = []
        
        # 根据day_value计算当天的完成角色数
        # day为0时不用slice，直接使用前3个元素
        if day_value is not None and day_value > 0:
            start_index = day_value * 3
            # 切片获取当天的3个角色完成状态
            day_finished = finished[start_index:start_index + 3] if start_index < len(finished) else []
            # 计算完成的数量（可能是计算非零/非空元素，或者直接使用长度）
            # 根据"0-3"的描述，应该是切片的长度，但需要确保不超过3
            finished_count = min(len(day_finished), 3)
        elif day_value == 0:
            # day为0时，直接使用前3个元素
            day_finished = finished[:3] if len(finished) > 0 else []
            finished_count = min(len(day_finished), 3)
        else:
            finished_count = 0
        
        # 提取save_date
        save_date = self.slot_data.get('save_date')
        if save_date is not None:
            save_date = str(save_date)
        else:
            save_date = None
        
        # 提取subtitle和subtitleText
        subtitle = self.slot_data.get('subtitle')
        subtitle_text = self.slot_data.get('subtitleText')
        
        # 只有当subtitle不为空且subtitleText不为空时才显示
        if subtitle and subtitle_text:
            subtitle_text = str(subtitle_text)
        else:
            subtitle_text = None
        
        return {
            'day_value': day_value,
            'is_epilogue': is_epilogue,
            'finished_count': finished_count,
            'save_date': save_date,
            'subtitle_text': subtitle_text
        }
    
    def _get_image_hash(self) -> Optional[str]:
        """获取image_data的hash
        
        Returns:
            MD5哈希值，如果没有image_data返回None
        """
        if self._image_hash is not None:
            return self._image_hash
        
        image_data = self.slot_data.get(_IMGDATA_FIELD_KEY) if self.slot_data else None
        if not image_data:
            return None
        
        md5_hash = hashlib.md5()
        md5_hash.update(image_data.encode('utf-8'))
        self._image_hash = md5_hash.hexdigest()
        return self._image_hash
    
    def _extract_base64_data(self, image_data: str) -> Optional[str]:
        """从data URI中提取base64数据部分
        
        Args:
            image_data: base64编码的图片数据（data URI格式）
            
        Returns:
            base64数据字符串，如果格式不正确返回None
        """
        if not isinstance(image_data, str) or not image_data:
            logger.debug("Invalid image_data: not a string or empty")
            return None
        
        sep_pos = image_data.find(_BASE64_SEPARATOR)
        if sep_pos == -1:
            logger.debug("image_data format incorrect: missing base64 separator")
            return None
        
        base64_part = image_data[sep_pos + len(_BASE64_SEPARATOR):]
        if not base64_part:
            logger.debug("Empty base64 data")
            return None
        
        return base64_part
    
    def _decode_base64_to_bytes(self, base64_data: str) -> Optional[bytes]:
        """将base64字符串解码为字节
        
        Args:
            base64_data: base64编码的字符串
            
        Returns:
            解码后的字节数据，失败返回None
        """
        try:
            image_bytes = base64.b64decode(base64_data, validate=True)
            if not image_bytes:
                logger.debug("Decoded image bytes are empty")
                return None
            return image_bytes
        except (ValueError, base64.binascii.Error) as e:
            logger.debug("Base64 decode failed: %s", e, exc_info=True)
            return None
    
    def _load_image_from_bytes(self, image_bytes: bytes) -> Optional[Image.Image]:
        """从字节数据加载PIL Image
        
        Args:
            image_bytes: 图片字节数据
            
        Returns:
            PIL Image对象，失败返回None
        """
        try:
            with BytesIO(image_bytes) as buffer:
                image = Image.open(buffer)
                return image.copy()
        except (UnidentifiedImageError, OSError, IOError) as e:
            logger.debug("Image format parse failed: %s", e, exc_info=True)
            return None
    
    def _decode_image_data(self, image_data: str) -> Optional[Image.Image]:
        """解码base64图片数据
        
        Args:
            image_data: base64编码的图片数据（data URI格式）
            
        Returns:
            PIL Image对象，解码失败返回None
        """
        base64_data = self._extract_base64_data(image_data)
        if not base64_data:
            return None
        
        image_bytes = self._decode_base64_to_bytes(base64_data)
        if not image_bytes:
            return None
        
        return self._load_image_from_bytes(image_bytes)
    
    def _create_placeholder_image(
        self,
        size: Tuple[int, int],
        text: str
    ) -> Image.Image:
        """创建灰色占位图
        
        Args:
            size: 图片尺寸 (width, height)
            text: 占位图文本
            
        Returns:
            PIL Image对象
        """
        if size[0] <= 0 or size[1] <= 0:
            raise ValueError(f"Invalid size: {size}")
        
        display_text = text or ""
        
        placeholder_img = Image.new('RGB', size, color=self._PLACEHOLDER_COLOR)
        draw = ImageDraw.Draw(placeholder_img)
        
        font = self._get_placeholder_font(size, display_text)
        
        bbox = draw.textbbox((0, 0), display_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = (size[0] - text_width) // 2
        text_y = (size[1] - text_height) // 2
        
        draw.text((text_x, text_y), display_text, fill=self._TEXT_COLOR_GRAY, font=font)
        
        return placeholder_img
    
    def _get_placeholder_font(self, size: Tuple[int, int], text: str) -> ImageFont.FreeTypeFont:
        """获取占位图字体
        
        Args:
            size: 图片尺寸
            text: 文本内容
            
        Returns:
            PIL字体对象
        """
        font_candidates = [
            ("arial.ttf", lambda s, t: max(self._FONT_SIZE_MIN, min(
                s[0] // len(t) if t else _DEFAULT_FONT_SIZE,
                s[1] // self._FONT_SIZE_DIVISOR
            ))),
            ("C:/Windows/Fonts/msyh.ttc", lambda s, t: max(self._FONT_SIZE_MIN, s[1] // self._FONT_SIZE_DIVISOR)),
        ]
        
        for font_path, size_calculator in font_candidates:
            try:
                font_size = size_calculator(size, text)
                return ImageFont.truetype(font_path, font_size)
            except (OSError, IOError):
                continue
        
        return ImageFont.load_default()
    
    def _create_status_circle_image(
        self,
        diameter: int,
        is_active: bool,
        circle_cache: Optional[Dict[Tuple[int, bool], Image.Image]] = None
    ) -> Image.Image:
        """创建状态圆圈图片
        
        Args:
            diameter: 圆圈直径（像素）
            is_active: 是否激活状态
            circle_cache: 圆圈图片缓存（可选）
            
        Returns:
            PIL Image对象
        """
        if diameter <= 0:
            raise ValueError(f"Diameter must be positive, got {diameter}")
        
        # 检查缓存
        cache_key = (diameter, is_active)
        if circle_cache and cache_key in circle_cache:
            return circle_cache[cache_key]
        
        # 创建图片，添加一些边距以避免边框被裁剪
        padding = 2
        size = diameter + padding * 2
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # 计算圆心和半径
        center = size // 2
        radius = diameter // 2
        
        # 边框颜色
        border_color = '#E1C183'
        
        if is_active:
            # 激活状态：渐变填充
            # 从 #6BB0A8 到 #E2508D
            start_color = (107, 176, 168)  # #6BB0A8
            end_color = (226, 80, 141)     # #E2508D
            
            # 绘制渐变填充
            for y in range(-radius, radius + 1):
                # 计算当前行的x范围
                x_range = int((radius ** 2 - y ** 2) ** 0.5)
                if x_range <= 0:
                    continue
                
                # 计算渐变比例（从上到下）
                y_pos = y + radius
                progress = y_pos / diameter if diameter > 0 else 0
                progress = max(0, min(1, progress))
                
                # 插值颜色
                r = int(start_color[0] + (end_color[0] - start_color[0]) * progress)
                g = int(start_color[1] + (end_color[1] - start_color[1]) * progress)
                b = int(start_color[2] + (end_color[2] - start_color[2]) * progress)
                color = (r, g, b, 255)
                
                # 绘制这一行的像素
                for x in range(-x_range, x_range + 1):
                    px = center + x
                    py = center + y
                    if 0 <= px < size and 0 <= py < size:
                        # 检查是否在圆内
                        dist_sq = x ** 2 + y ** 2
                        if dist_sq <= radius ** 2:
                            img.putpixel((px, py), color)
        else:
            # 未激活状态：纯色填充 #222536
            fill_color = (34, 37, 54, 255)  # #222536
            
            # 绘制填充圆
            draw.ellipse(
                [center - radius, center - radius, center + radius, center + radius],
                fill=fill_color
            )
        
        # 绘制边框
        border_width = 2
        draw.ellipse(
            [center - radius, center - radius, center + radius, center + radius],
            outline=border_color,
            width=border_width
        )
        
        # 存入缓存
        if circle_cache is not None:
            circle_cache[cache_key] = img
        
        return img
    
    def _normalize_container_size(
        self,
        container_width: int,
        container_height: int
    ) -> Tuple[int, int]:
        """规范化容器尺寸
        
        Args:
            container_width: 容器宽度
            container_height: 容器高度
            
        Returns:
            规范化后的尺寸 (width, height)
        """
        if container_width <= 0 or container_height <= 0:
            return self._DEFAULT_THUMBNAIL_SIZE
        return (container_width, container_height)
    
    def _calculate_available_size(
        self,
        container_width: int,
        container_height: int
    ) -> Tuple[int, int]:
        """计算可用尺寸（考虑内边距和比例限制）
        
        Args:
            container_width: 容器宽度
            container_height: 容器高度
            
        Returns:
            可用尺寸 (width, height)
        """
        max_width = int(container_width * self._THUMBNAIL_MAX_WIDTH_RATIO) - self._LABEL_PADDING_X * 2
        max_height = int(container_height * self._THUMBNAIL_HEIGHT_RATIO) - self._LABEL_PADDING_Y * 2
        
        available_width = max(max_width, self._THUMBNAIL_MIN_SIZE)
        available_height = max(max_height, self._THUMBNAIL_MIN_SIZE)
        
        return (available_width, available_height)
    
    def _get_aspect_ratio(
        self,
        original_image: Optional[Image.Image],
        aspect_ratio: Optional[float]
    ) -> float:
        """获取宽高比
        
        Args:
            original_image: 原始图片对象
            aspect_ratio: 传入的宽高比
            
        Returns:
            宽高比值
        """
        if original_image:
            orig_width, orig_height = original_image.size
            if orig_height == 0:
                logger.warning("Original image has zero height, using default aspect ratio")
                return _ASPECT_RATIO_4_3
            return orig_width / orig_height
        
        if aspect_ratio is not None:
            return aspect_ratio
        
        return _ASPECT_RATIO_4_3
    
    def _calculate_fitted_size(
        self,
        available_width: int,
        available_height: int,
        aspect_ratio: float
    ) -> Tuple[int, int]:
        """计算适配尺寸（保持宽高比，确保完整显示）
        
        Args:
            available_width: 可用宽度
            available_height: 可用高度
            aspect_ratio: 宽高比
            
        Returns:
            适配后的尺寸 (width, height)
        """
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
        """计算缩略图尺寸，确保图片完整显示在框内
        
        Args:
            container_width: 容器宽度
            container_height: 容器高度
            original_image: 原始图片对象（优先使用，用于保持宽高比）
            aspect_ratio: 宽高比（如果original_image为None时使用）
            
        Returns:
            缩略图尺寸 (width, height)
        """
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
        """创建存档槽UI组件（在隐藏状态下创建，避免闪烁）
        
        优化：移除 update_idletasks() 调用，使用预测尺寸
        所有尺寸计算在 _load_all_images() 中统一处理
        """
        self.container = ctk.CTkFrame(
            self.parent,
            fg_color=self.Colors.LIGHT_GRAY,
            corner_radius=self._CORNER_RADIUS,
            border_width=self._BORDER_WIDTH,
            border_color=self.Colors.GRAY
        )
        
        # 移除 update_idletasks() 调用，避免潜在闪烁
        # 尺寸计算将在 _load_all_images() 中使用预测尺寸统一处理
        
        image_data = self.slot_data.get(_IMGDATA_FIELD_KEY) if self.slot_data else None
        
        content_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=self._LABEL_PADDING_X, pady=self._LABEL_PADDING_Y)
        
        image_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        image_frame.pack(side="left", fill="y", padx=(0, self._LABEL_PADDING_X))
        
        image_inner_frame = ctk.CTkFrame(image_frame, fg_color="transparent")
        image_inner_frame.pack(expand=True, fill="both")
        
        # 使用默认尺寸创建label，避免在无原始图片时的不准确计算
        # 后续图片加载时会通过 _load_all_images 更新为正确的尺寸
        # 初始设置为透明背景，避免显示灰色占位符闪烁
        self._image_label = ctk.CTkLabel(
            image_inner_frame,
            text="",
            fg_color="transparent",
            width=self._DEFAULT_THUMBNAIL_SIZE[0],
            height=self._DEFAULT_THUMBNAIL_SIZE[1]
        )
        self._image_label.pack(fill="none")
        
        # 创建文本框架，但延迟创建信息面板（在所有图片加载完成后）
        self._text_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        self._text_frame.pack(side="right", fill="both", expand=True)
        
        # 信息面板将在所有图片成功显示后创建
        self._text_label = None  # 保留用于兼容性，但不再使用
        
        # 绑定点击事件到容器（信息面板创建后也会绑定）
        self._bind_click_handlers()
    
    def _process_thumbnail_from_cache(
        self,
        img_hash: str,
        thumb_size: Tuple[int, int],
        cache: Optional[ImageCache]
    ) -> Optional[Image.Image]:
        """从缓存获取缩略图
        
        Args:
            img_hash: 图片数据的MD5哈希值
            thumb_size: 缩略图尺寸
            cache: 缓存对象
            
        Returns:
            缓存的缩略图，如果不存在返回None
        """
        if cache:
            return cache.get_thumbnail(img_hash, thumb_size)
        return None
    
    def _process_original_image(
        self,
        img_hash: str,
        cache: Optional[ImageCache]
    ) -> Optional[Image.Image]:
        """处理原始图片（从缓存或解码）
        
        Args:
            img_hash: 图片数据的MD5哈希值
            cache: 缓存对象
            
        Returns:
            原始PIL Image对象，失败返回None
        """
        if cache:
            cached_original = cache.get_original(img_hash)
            if cached_original:
                return cached_original
        
        # 需要解码时，才访问image_data
        image_data = self.slot_data.get(_IMGDATA_FIELD_KEY) if self.slot_data else None
        decoded_image = self._decode_image_data(image_data)
        
        if decoded_image and cache:
            cache.put_original(img_hash, decoded_image)
        
        return decoded_image
    
    def _get_placeholder_with_cache(
        self,
        thumb_size: Tuple[int, int],
        placeholder_text: str,
        placeholder_cache: Optional[Dict[Tuple[Tuple[int, int], str], Image.Image]]
    ) -> Image.Image:
        """获取占位图（带缓存）
        
        Args:
            thumb_size: 缩略图尺寸
            placeholder_text: 占位图文本
            placeholder_cache: 占位图缓存
            
        Returns:
            占位图PIL Image对象
        """
        placeholder_key = (thumb_size, placeholder_text)
        if placeholder_cache and placeholder_key in placeholder_cache:
            return placeholder_cache[placeholder_key]
        
        display_image = self._create_placeholder_image(thumb_size, placeholder_text)
        
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
        """在工作线程中处理图片
        
        Args:
            image_data: base64编码的图片数据
            container_width: 容器宽度
            container_height: 容器高度
            cache: 图片缓存对象（可选）
            placeholder_cache: 占位图缓存（可选）
            
        Returns:
            (PIL Image对象, 占位符文本) 元组，如果成功返回 (Image, None)，失败返回 (None, placeholder_text)
        """
        img_hash = self._get_image_hash()
        if not img_hash:
            # 没有图片数据，使用默认尺寸创建占位图
            thumb_size = self._calculate_thumbnail_size(container_width, container_height)
            placeholder_text = self.translate("tyrano_no_imgdata")
            display_image = self._get_placeholder_with_cache(thumb_size, placeholder_text, placeholder_cache)
            return display_image, placeholder_text
        
        # 先解码原始图片，以便基于实际图片计算准确的尺寸
        original_image = self._process_original_image(img_hash, cache)
        
        if original_image is None:
            # 解码失败，使用默认尺寸创建占位图
            thumb_size = self._calculate_thumbnail_size(container_width, container_height)
            placeholder_text = self.translate("tyrano_image_decode_failed")
            display_image = self._get_placeholder_with_cache(thumb_size, placeholder_text, placeholder_cache)
            return display_image, placeholder_text
        
        # 基于原始图片计算准确的缩略图尺寸
        thumb_size = self._calculate_thumbnail_size(container_width, container_height, original_image)
        
        # 用正确的尺寸查缓存（确保缓存键与生成键一致）
        cached_thumbnail = self._process_thumbnail_from_cache(img_hash, thumb_size, cache)
        if cached_thumbnail:
            return cached_thumbnail, None
        
        # 缓存未命中，创建缩略图并存入缓存
        thumbnail = original_image.resize(thumb_size, Image.Resampling.BILINEAR)
        
        if cache:
            cache.put_thumbnail(img_hash, thumb_size, thumbnail)
        
        return thumbnail, None
    
    def _bind_click_handlers(self, label: Optional[tk.Widget] = None) -> None:
        """绑定点击事件处理器
        
        Args:
            label: 标签组件（可选，如果提供则绑定，否则只绑定容器和文本框架）
                  可以是 CTkLabel、CTkTextbox 等任何支持 bind 的组件
        """
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
        """创建右侧信息面板
        
        Args:
            circle_cache: 圆圈图片缓存（可选）
        """
        if not self._text_frame:
            return
        
        if self._info_panel_created:
            # 已经创建过，跳过
            return
        
        # 检查存档是否为空（占位符或NO SAVE类型）
        is_empty_slot = self.slot_data is None or self._is_empty_save()
        
        # 提取存档信息
        info = self._extract_save_info()
        
        # 如果是空存档，显示"无存档"
        if is_empty_slot:
            no_save_label = ctk.CTkLabel(
                self._text_frame,
                text=self.translate("tyrano_no_save"),
                font=self.get_cjk_font(self._FONT_SIZE),
                text_color=self.Colors.TEXT_PRIMARY,
                fg_color="transparent",
                anchor="w"
            )
            no_save_label.pack(side="top", anchor="w", pady=(0, 5))
            self._bind_click_handlers(no_save_label)
            self._info_panel_created = True
            return
        
        # 创建日目标签
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
                font=self.get_cjk_font(self._FONT_SIZE),
                text_color=self.Colors.TEXT_PRIMARY,
                fg_color="transparent",
                anchor="w"
            )
            day_label.pack(side="top", anchor="w", pady=(0, 5))
            self._bind_click_handlers(day_label)
        
        # 只有当不是后日谈时才绘制圆圈
        # 存档为空或后日谈（day_epilogue > 0）时不绘制圆圈
        if not info['is_epilogue']:
            # 创建圆圈容器
            circles_frame = ctk.CTkFrame(self._text_frame, fg_color="transparent")
            circles_frame.pack(side="top", anchor="w", pady=(0, 5))
            
            # 计算圆圈尺寸（基于容器宽度，约为15-20%，放大1.5倍）
            # 尝试获取容器宽度，如果无法获取则使用默认值
            try:
                container_width = self._text_frame.winfo_width()
                if container_width > 0:
                    circle_diameter = max(22, min(37, int(container_width * 0.225)))  # 22-37像素之间（原尺寸的1.5倍）
                else:
                    circle_diameter = 30  # 默认直径（原尺寸的1.5倍）
            except (tk.TclError, AttributeError):
                circle_diameter = 30  # 默认直径（原尺寸的1.5倍）
            
            # 创建三个圆圈
            finished_count = info['finished_count']
            for i in range(3):
                is_active = i < finished_count
                
                # 创建圆圈图片
                circle_img = self._create_status_circle_image(circle_diameter, is_active, circle_cache)
                
                # 转换为CTkImage
                ctk_circle_img = ctk.CTkImage(
                    light_image=circle_img,
                    dark_image=circle_img,
                    size=(circle_diameter + 4, circle_diameter + 4)  # 加上边距
                )
                
                # 创建标签显示圆圈
                circle_label = ctk.CTkLabel(
                    circles_frame,
                    image=ctk_circle_img,
                    text="",
                    fg_color="transparent"
                )
                circle_label.pack(side="left", padx=5)
                self._bind_click_handlers(circle_label)
        
        # 创建日期标签
        if info['save_date']:
            date_label = ctk.CTkLabel(
                self._text_frame,
                text=info['save_date'],
                font=self.get_cjk_font(self._FONT_SIZE),
                text_color="#000000",  # 黑色
                fg_color="transparent",
                anchor="w"
            )
            date_label.pack(side="top", anchor="w", pady=(0, 5))
            self._bind_click_handlers(date_label)
        
        # 创建副标题标签（条件显示）
        if info['subtitle_text']:
            subtitle_label = ctk.CTkLabel(
                self._text_frame,
                text=info['subtitle_text'],
                font=self.get_cjk_font(self._FONT_SIZE),
                text_color="#2EA6B6",  # 指定颜色
                fg_color="transparent",
                anchor="w"
            )
            subtitle_label.pack(side="top", anchor="w")
            self._bind_click_handlers(subtitle_label)
        
        self._info_panel_created = True
    
    def get_container(self) -> Optional[ctk.CTkFrame]:
        """获取容器组件
        
        Returns:
            容器Frame，如果未创建返回None
        """
        return self.container


class TyranoSaveViewer:
    """Tyrano存档查看器主UI类"""
    
    _RESIZE_DEBOUNCE_MS: Final[int] = 200
    _BUTTON_WIDTH: Final[int] = 60
    _BUTTON_HEIGHT: Final[int] = 30
    _ENTRY_WIDTH: Final[int] = 80
    _PAGE_INFO_WIDTH: Final[int] = 60
    _CORNER_RADIUS: Final[int] = 8
    _FONT_SIZE_SMALL: Final[int] = 10
    _FONT_SIZE_MEDIUM: Final[int] = 12
    _PADDING_SMALL: Final[int] = 5
    _PADDING_MEDIUM: Final[int] = 10
    _SEPARATOR_WIDTH: Final[int] = 3
    _MIN_PAGE_NUMBER: Final[int] = 1
    _EMPTY_PAGE_TEXT: Final[str] = "0/0"
    
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
        
        self._create_ui()
        self._refresh_display()
    
    def _create_ui(self) -> None:
        """创建UI布局"""
        main_container = ctk.CTkFrame(self.parent, fg_color=self.Colors.WHITE)
        main_container.pack(fill="both", expand=True, padx=self._PADDING_MEDIUM, pady=self._PADDING_MEDIUM)
        
        self.slots_frame = ctk.CTkFrame(main_container, fg_color=self.Colors.WHITE)
        self.slots_frame.pack(fill="both", expand=True)
        
        self._create_navigation(main_container)
    
    def _create_navigation(self, parent: ctk.CTkFrame) -> None:
        """创建翻页导航栏"""
        nav_frame = ctk.CTkFrame(parent, fg_color=self.Colors.WHITE)
        nav_frame.pack(side="bottom", fill="x", pady=self._PADDING_MEDIUM)
        
        nav_center_frame = ctk.CTkFrame(nav_frame, fg_color=self.Colors.WHITE)
        nav_center_frame.pack(anchor="center")
        
        self._create_page_buttons(nav_center_frame)
        self._create_page_info_label(nav_center_frame)
        self._create_jump_controls(nav_center_frame)
    
    def _create_page_buttons(self, parent: ctk.CTkFrame) -> None:
        """创建翻页按钮
        
        Args:
            parent: 父容器
        """
        button_config = {
            'width': self._BUTTON_WIDTH,
            'height': self._BUTTON_HEIGHT,
            'corner_radius': self._CORNER_RADIUS,
            'fg_color': self.Colors.WHITE,
            'hover_color': self.Colors.LIGHT_GRAY,
            'border_width': 1,
            'border_color': self.Colors.GRAY,
            'text_color': self.Colors.TEXT_PRIMARY,
            'font': self.get_cjk_font(self._FONT_SIZE_SMALL)
        }
        
        self.prev_button = ctk.CTkButton(
            parent,
            text=self.translate("prev_page"),
            command=self._go_to_prev_page,
            **button_config
        )
        self.prev_button.pack(side="left", padx=self._PADDING_SMALL)
        
        self.next_button = ctk.CTkButton(
            parent,
            text=self.translate("next_page"),
            command=self._go_to_next_page,
            **button_config
        )
        self.next_button.pack(side="left", padx=self._PADDING_SMALL)
    
    def _create_page_info_label(self, parent: ctk.CTkFrame) -> None:
        """创建页码显示标签
        
        Args:
            parent: 父容器
        """
        self.page_info_label = ctk.CTkLabel(
            parent,
            text="1/1",
            font=self.get_cjk_font(self._FONT_SIZE_MEDIUM),
            fg_color="transparent",
            text_color=self.Colors.TEXT_PRIMARY,
            width=self._PAGE_INFO_WIDTH,
            anchor="center"
        )
        self.page_info_label.pack(side="left", padx=self._PADDING_MEDIUM)
    
    def _create_jump_controls(self, parent: ctk.CTkFrame) -> None:
        """创建页面跳转控件
        
        Args:
            parent: 父容器
        """
        jump_frame = ctk.CTkFrame(parent, fg_color=self.Colors.WHITE)
        jump_frame.pack(side="left", padx=20)
        
        self.jump_label = ctk.CTkLabel(
            jump_frame,
            text=self.translate("jump_to_page"),
            font=self.get_cjk_font(self._FONT_SIZE_SMALL),
            fg_color="transparent",
            text_color=self.Colors.TEXT_PRIMARY
        )
        self.jump_label.pack(side="left", padx=self._PADDING_SMALL)
        
        self.jump_entry = ctk.CTkEntry(
            jump_frame,
            width=self._ENTRY_WIDTH,
            height=self._BUTTON_HEIGHT,
            corner_radius=self._CORNER_RADIUS,
            fg_color=self.Colors.WHITE,
            text_color=self.Colors.TEXT_PRIMARY,
            border_color=self.Colors.GRAY,
            font=self.get_cjk_font(self._FONT_SIZE_SMALL)
        )
        self.jump_entry.pack(side="left", padx=self._PADDING_SMALL)
        self.jump_entry.bind('<Return>', self._on_jump_entry_return)
        
        self.jump_button = ctk.CTkButton(
            jump_frame,
            text=self.translate("jump"),
            command=self._jump_to_page,
            width=self._BUTTON_WIDTH,
            height=self._BUTTON_HEIGHT,
            corner_radius=self._CORNER_RADIUS,
            fg_color=self.Colors.WHITE,
            hover_color=self.Colors.LIGHT_GRAY,
            border_width=1,
            border_color=self.Colors.GRAY,
            text_color=self.Colors.TEXT_PRIMARY,
            font=self.get_cjk_font(self._FONT_SIZE_SMALL)
        )
        self.jump_button.pack(side="left", padx=self._PADDING_SMALL)
    
    def _on_jump_entry_return(self, event: tk.Event) -> None:
        """跳转输入框回车事件处理
        
        Args:
            event: 事件对象
        """
        self._jump_to_page()
    
    def _clear_slots_frame(self) -> None:
        """清除存档槽显示区域的所有组件"""
        for widget in self.slots_frame.winfo_children():
            widget.destroy()
        self.slot_widgets.clear()
    
    def _setup_grid_container(self) -> ctk.CTkFrame:
        """设置网格布局容器
        
        Returns:
            配置好的主容器Frame
        """
        main_container = ctk.CTkFrame(self.slots_frame, fg_color=self.Colors.WHITE)
        main_container.pack(fill="both", expand=True, padx=self._PADDING_MEDIUM, pady=self._PADDING_SMALL)
        
        main_container.grid_columnconfigure(0, weight=1, uniform="column")
        main_container.grid_columnconfigure(1, weight=0, minsize=self._SEPARATOR_WIDTH)
        main_container.grid_columnconfigure(2, weight=1, uniform="column")
        
        for row in range(TYRANO_ROWS_PER_PAGE):
            main_container.grid_rowconfigure(row, weight=1)
        
        return main_container
    
    def _create_separator(self, parent: ctk.CTkFrame) -> tk.Frame:
        """创建中间分隔线
        
        Args:
            parent: 父容器
            
        Returns:
            分隔线Frame
        """
        separator = tk.Frame(
            parent,
            width=self._SEPARATOR_WIDTH,
            bg="gray",
            relief="sunken"
        )
        separator.grid(row=0, column=1, rowspan=TYRANO_ROWS_PER_PAGE, sticky="ns", padx=self._PADDING_MEDIUM)
        return separator
    
    def _create_slot_widget(
        self,
        parent_frame: ctk.CTkFrame,
        slot_data: Optional[Dict[str, Any]],
        global_index: int
    ) -> ctk.CTkFrame:
        """创建存档槽组件或占位符
        
        Args:
            parent_frame: 父容器Frame
            slot_data: 存档槽数据，None表示空槽
            global_index: 全局索引
            
        Returns:
            组件Frame
        """
        if slot_data is not None:
            return self._create_filled_slot(parent_frame, slot_data, global_index)
        return self._create_empty_slot_placeholder(parent_frame)
    
    def _create_filled_slot(
        self,
        parent_frame: ctk.CTkFrame,
        slot_data: Dict[str, Any],
        global_index: int
    ) -> ctk.CTkFrame:
        """创建有数据的存档槽组件
        
        Args:
            parent_frame: 父容器Frame
            slot_data: 存档槽数据
            global_index: 全局索引
            
        Returns:
            组件Frame
        """
        slot_widget = TyranoSaveSlot(
            parent_frame,
            slot_data,
            global_index,
            self.translate,
            self.get_cjk_font,
            self.Colors,
            self._on_slot_click
        )
        slot_widget._create_widget()
        self.slot_widgets.append(slot_widget)
        
        container = slot_widget.get_container()
        if container:
            container.pack(fill="both", expand=True)
            return container
        
        return parent_frame
    
    def _create_empty_slot_placeholder(self, parent_frame: ctk.CTkFrame) -> ctk.CTkFrame:
        """创建空存档槽占位符
        
        Args:
            parent_frame: 父容器Frame
            
        Returns:
            占位符Frame
        """
        placeholder = ctk.CTkFrame(
            parent_frame,
            fg_color=self.Colors.LIGHT_GRAY,
            corner_radius=self._CORNER_RADIUS
        )
        placeholder.pack(fill="both", expand=True)
        return placeholder
    
    def _create_slots_grid(self) -> None:
        """创建存档槽网格布局（批量预计算模式，避免闪烁）"""
        self._clear_slots_frame()
        
        # 确保slots_frame保持隐藏状态，直到所有计算完成
        if hasattr(self, 'slots_frame') and self.slots_frame.winfo_viewable():
            self.slots_frame.pack_forget()
        
        page_slots = self.analyzer.get_current_page_slots()
        main_container = self._setup_grid_container()
        self._create_separator(main_container)
        
        base_index = (self.analyzer.current_page - self._MIN_PAGE_NUMBER) * TYRANO_SAVES_PER_PAGE
        
        for row in range(TYRANO_ROWS_PER_PAGE):
            self._create_row_slots(main_container, page_slots, base_index, row)
        
        # 所有槽创建完成，但保持隐藏状态
        # 在隐藏状态下完成所有图片处理和UI更新，最后一次性显示
        self._load_all_images()
    
    def _calculate_size_from_parent_container(self) -> Optional[Tuple[int, int]]:
        """从父容器计算尺寸
        
        Returns:
            计算得到的尺寸，如果无法计算返回None
        """
        try:
            parent_container = self.slots_frame.master
            if not parent_container:
                return None
            
            parent_width = parent_container.winfo_width()
            parent_height = parent_container.winfo_height()
            
            if parent_width <= _MIN_CONTAINER_SIZE or parent_height <= _MIN_CONTAINER_SIZE:
                return None
            
            # 减去 padding
            available_width = parent_width - self._PADDING_MEDIUM * 2
            available_height = parent_height - self._PADDING_SMALL * 2
            
            # 网格布局：2列（左右各一列），3行
            column_width = (available_width - self._SEPARATOR_WIDTH - self._PADDING_MEDIUM * 2) // 2
            row_height = available_height // TYRANO_ROWS_PER_PAGE
            
            if column_width > _MIN_CONTAINER_SIZE and row_height > _MIN_CONTAINER_SIZE:
                return (column_width, row_height)
        except (tk.TclError, AttributeError):
            pass
        
        return None
    
    def _calculate_size_from_existing_widgets(self) -> Optional[Tuple[int, int]]:
        """从已创建的容器获取平均尺寸
        
        Returns:
            平均尺寸，如果无法计算返回None
        """
        valid_sizes: List[Tuple[int, int]] = []
        
        for slot_widget in self.slot_widgets:
            if not slot_widget.container:
                continue
            try:
                width = slot_widget.container.winfo_reqwidth()
                height = slot_widget.container.winfo_reqheight()
                if width > _MIN_CONTAINER_SIZE and height > _MIN_CONTAINER_SIZE:
                    valid_sizes.append((width, height))
            except (tk.TclError, AttributeError):
                continue
        
        if not valid_sizes:
            return None
        
        # 计算平均值
        total_width = sum(w for w, _ in valid_sizes)
        total_height = sum(h for _, h in valid_sizes)
        count = len(valid_sizes)
        
        return (total_width // count, total_height // count)
    
    def _calculate_reference_size(self) -> Optional[Tuple[int, int]]:
        """计算参考尺寸（基于布局预测，无需实时测量）
        
        算法：基于父容器尺寸和网格布局配置，预测每个槽的尺寸
        避免临时显示界面导致的闪烁
        
        Returns:
            参考尺寸元组，如果无法计算返回None
        """
        # 方法1：尝试从父容器获取尺寸
        size = self._calculate_size_from_parent_container()
        if size:
            return size
        
        # 方法2：尝试从已创建的容器获取
        size = self._calculate_size_from_existing_widgets()
        if size:
            return size
        
        # 方法3：使用默认尺寸
        return (_DEFAULT_CONTAINER_WIDTH, _DEFAULT_CONTAINER_HEIGHT)
    
    def _get_container_size_for_slot(
        self,
        slot_widget: TyranoSaveSlot,
        reference_size: Optional[Tuple[int, int]]
    ) -> Tuple[int, int]:
        """获取存档槽的容器尺寸
        
        Args:
            slot_widget: 存档槽组件
            reference_size: 参考尺寸（基于布局预测）
            
        Returns:
            容器尺寸 (width, height)
        """
        if reference_size:
            return reference_size
        
        # 备用方案：尝试从容器获取请求尺寸
        if slot_widget.container:
            try:
                width = slot_widget.container.winfo_reqwidth()
                height = slot_widget.container.winfo_reqheight()
                if width > _MIN_CONTAINER_SIZE and height > _MIN_CONTAINER_SIZE:
                    return (width, height)
            except (tk.TclError, AttributeError):
                pass
        
        # 使用默认尺寸
        return (_DEFAULT_CONTAINER_WIDTH, _DEFAULT_CONTAINER_HEIGHT)
    
    def _prepare_image_tasks(self, reference_size: Optional[Tuple[int, int]]) -> List[Tuple[TyranoSaveSlot, Optional[str], int, int]]:
        """准备图片处理任务（使用预测尺寸，无需实时测量）
        
        算法优化：避免调用 update_idletasks() 和实时测量尺寸
        优先使用 reference_size（基于布局预测），避免界面闪烁
        
        Args:
            reference_size: 参考尺寸（基于布局预测）
            
        Returns:
            任务列表，每个任务包含 (slot_widget, image_data, container_width, container_height)
        """
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
                image_data = slot_widget.slot_data.get(_IMGDATA_FIELD_KEY)
            
            tasks.append((slot_widget, image_data, container_width, container_height))
        
        return tasks
    
    def _calculate_max_workers(self, task_count: int) -> int:
        """计算最大工作线程数
        
        Args:
            task_count: 任务数量
            
        Returns:
            最大工作线程数
        """
        if task_count <= 0:
            return 1
        
        cpu_count = os.cpu_count() or 4
        # 限制最大线程数，避免过度并发
        return min(task_count, cpu_count, TYRANO_SAVES_PER_PAGE)
    
    def _handle_image_processing_error(
        self,
        slot_widget: TyranoSaveSlot,
        error: Exception
    ) -> Tuple[None, str]:
        """处理图片处理错误
        
        Args:
            slot_widget: 存档槽组件
            error: 异常对象
            
        Returns:
            (None, placeholder_text) 元组
        """
        logger.error(
            "Failed to process image for slot %d: %s",
            slot_widget.slot_index,
            error,
            exc_info=True
        )
        placeholder_text = slot_widget.translate("tyrano_image_decode_failed")
        return (None, placeholder_text)
    
    def _process_images_parallel(self, tasks: List[Tuple[TyranoSaveSlot, Optional[str], int, int]]) -> Dict[TyranoSaveSlot, Tuple[Optional[Image.Image], Optional[str]]]:
        """并行处理所有图片
        
        Args:
            tasks: 图片处理任务列表
            
        Returns:
            处理结果字典，键为slot_widget，值为(pil_image, placeholder_text)元组
        """
        if not tasks:
            return {}
        
        max_workers = self._calculate_max_workers(len(tasks))
        processed_results: Dict[TyranoSaveSlot, Tuple[Optional[Image.Image], Optional[str]]] = {}
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_slot = {
                executor.submit(
                    slot_widget._process_image_worker,
                    image_data,
                    container_width,
                    container_height,
                    self._image_cache,
                    self._placeholder_cache
                ): slot_widget
                for slot_widget, image_data, container_width, container_height in tasks
            }
            
            for future in as_completed(future_to_slot):
                slot_widget = future_to_slot[future]
                try:
                    pil_image, placeholder_text = future.result()
                    processed_results[slot_widget] = (pil_image, placeholder_text)
                except Exception as e:
                    processed_results[slot_widget] = self._handle_image_processing_error(slot_widget, e)
        
        return processed_results
    
    def _create_ctk_image_from_pil(self, pil_image: Image.Image) -> Optional[ctk.CTkImage]:
        """从PIL Image创建CTkImage
        
        Args:
            pil_image: PIL Image对象
            
        Returns:
            CTkImage对象，失败返回None
        """
        try:
            image_size = (pil_image.width, pil_image.height)
            return ctk.CTkImage(
                light_image=pil_image,
                dark_image=pil_image,
                size=image_size
            )
        except Exception as e:
            logger.debug("Failed to create CTkImage: %s", e, exc_info=True)
            return None
    
    def _determine_placeholder_text(
        self,
        slot_widget: TyranoSaveSlot,
        has_image_data: bool,
        decode_failed: bool
    ) -> str:
        """确定占位符文本
        
        Args:
            slot_widget: 存档槽组件
            has_image_data: 是否有图片数据
            decode_failed: 是否解码失败
            
        Returns:
            占位符文本
        """
        if decode_failed:
            return slot_widget.translate("tyrano_image_decode_failed")
        return slot_widget.translate("tyrano_no_imgdata")
    
    def _create_ui_updates(
        self,
        processed_results: Dict[TyranoSaveSlot, Tuple[Optional[Image.Image], Optional[str]]]
    ) -> List[Tuple[ctk.CTkLabel, Optional[ctk.CTkImage], Optional[str], Optional[Tuple[int, int]]]]:
        """创建UI更新列表
        
        Args:
            processed_results: 图片处理结果
            
        Returns:
            UI更新列表，每个元素为 (label, ctk_image, placeholder_text, image_size)
            image_size: 图片尺寸，用于设置Label的width/height
        """
        updates: List[Tuple[ctk.CTkLabel, Optional[ctk.CTkImage], Optional[str], Optional[Tuple[int, int]]]] = []
        
        for slot_widget in self.slot_widgets:
            if not slot_widget._image_label:
                continue
            
            # 处理未在结果中的情况
            if slot_widget not in processed_results:
                placeholder_text = slot_widget.translate("tyrano_no_imgdata")
                updates.append((slot_widget._image_label, None, placeholder_text, None))
                continue
            
            pil_image, placeholder_text = processed_results[slot_widget]
            image_size = (pil_image.width, pil_image.height) if pil_image else None
            
            # 成功加载图片
            if pil_image and not placeholder_text:
                ctk_image = self._create_ctk_image_from_pil(pil_image)
                if ctk_image:
                    updates.append((slot_widget._image_label, ctk_image, None, image_size))
                else:
                    # CTkImage创建失败，使用占位符
                    placeholder_text = slot_widget.translate("tyrano_image_decode_failed")
                    updates.append((slot_widget._image_label, None, placeholder_text, image_size))
            else:
                # 需要显示占位符
                if not placeholder_text:
                    has_image_data = bool(
                        slot_widget.slot_data and 
                        slot_widget.slot_data.get(_IMGDATA_FIELD_KEY)
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
        """配置标签显示图片
        
        Args:
            label: 标签组件
            ctk_image: CTkImage对象
            image_size: 图片尺寸
        """
        base_config = {
            "image": ctk_image,
            "text": "",
            "fg_color": "transparent"
        }
        
        if image_size:
            base_config["width"] = image_size[0]
            base_config["height"] = image_size[1]
        
        label.configure(**base_config)
    
    def _configure_label_with_placeholder(
        self,
        label: ctk.CTkLabel,
        placeholder_text: str,
        image_size: Optional[Tuple[int, int]]
    ) -> None:
        """配置标签显示占位符
        
        Args:
            label: 标签组件
            placeholder_text: 占位符文本
            image_size: 图片尺寸
        """
        base_config = {
            "image": None,
            "text": placeholder_text,
            "fg_color": TyranoSaveSlot._PLACEHOLDER_COLOR,
            "text_color": TyranoSaveSlot._TEXT_COLOR_GRAY
        }
        
        if image_size:
            base_config["width"] = image_size[0]
            base_config["height"] = image_size[1]
        
        label.configure(**base_config)
    
    def _apply_ui_updates(self, updates: List[Tuple[ctk.CTkLabel, Optional[ctk.CTkImage], Optional[str], Optional[Tuple[int, int]]]]) -> None:
        """批量原子更新UI组件（在隐藏状态下完成，避免闪烁）
        
        算法：由于界面已在隐藏状态，所有更新操作对用户不可见
        批量配置所有Label，确保尺寸匹配，避免显示时的布局抖动
        
        Args:
            updates: UI更新列表，每个元素为 (label, ctk_image, placeholder_text, image_size)
            image_size: 图片尺寸，用于设置Label的width/height
        """
        for label, ctk_image, placeholder_text, image_size in updates:
            if ctk_image:
                self._configure_label_with_image(label, ctk_image, image_size)
            else:
                # placeholder_text应该总是有值（由_create_ui_updates保证）
                display_text = placeholder_text or ""
                self._configure_label_with_placeholder(label, display_text, image_size)
    
    def _load_all_images(self) -> None:
        """批量并行加载所有存档槽的图片（零闪烁策略：完全隐藏状态下完成所有计算）
        
        算法优化：
        1. 保持界面完全隐藏状态
        2. 使用预测尺寸而非实时测量（避免临时显示）
        3. 并行处理所有图片
        4. 批量原子更新所有UI组件
        5. 最后一次性显示完整界面
        """
        # 确保保持隐藏状态（如果已经隐藏则无需操作）
        was_visible = self.slots_frame.winfo_viewable()
        if was_visible:
            self.slots_frame.pack_forget()
        
        # 使用预测尺寸计算（无需临时显示界面）
        # _calculate_reference_size 已优化为基于布局的预测算法
        reference_size = self._calculate_reference_size()
        
        # 在完全隐藏状态下准备图片处理任务
        tasks = self._prepare_image_tasks(reference_size)
        
        # 并行处理所有图片（后台计算，用户不可见）
        processed_results = self._process_images_parallel(tasks)
        
        # 创建UI更新列表（所有更新操作）
        updates = self._create_ui_updates(processed_results)
        
        # 批量原子更新所有UI组件（在隐藏状态下完成，用户不可见）
        self._apply_ui_updates(updates)
        
        # 在隐藏状态下批量创建所有文本标签（避免显示后逐个创建导致的布局抖动）
        # 使用预测尺寸，避免实时测量
        self._create_all_text_labels_hidden(reference_size)
        
        # 在隐藏状态下强制完成所有布局计算（确保所有尺寸已确定）
        # 这样显示时不会再有布局调整
        self.slots_frame.update_idletasks()
        
        # 所有计算和更新完成后，一次性显示界面（用户只看到最终完整结果）
        self.slots_frame.pack(fill="both", expand=True)
        # 使用 update() 确保完整渲染，但此时所有布局已计算完成，不会闪烁
        self.parent.update()
        
        if self._is_first_load:
            self._is_first_load = False
            self.parent.bind("<Configure>", self._on_window_resize)
    
    def _create_all_text_labels_hidden(self, reference_size: Optional[Tuple[int, int]]) -> None:
        """在隐藏状态下批量创建所有信息面板（避免显示后逐个创建导致的闪烁）
        
        Args:
            reference_size: 参考尺寸（保留用于兼容性，但不再需要）
        """
        # 在隐藏状态下批量创建所有信息面板
        # 使用圆圈缓存，避免重复绘制相同尺寸和状态的圆圈
        for slot_widget in self.slot_widgets:
            slot_widget._create_info_panel(self._circle_cache)
    
    def _create_row_slots(
        self,
        main_container: ctk.CTkFrame,
        page_slots: List[Optional[Dict[str, Any]]],
        base_index: int,
        row: int
    ) -> None:
        """创建一行的左右两个存档槽
        
        Args:
            main_container: 主容器
            page_slots: 当前页的存档槽列表
            base_index: 基础索引
            row: 行号
        """
        left_page_index = row
        right_page_index = row + TYRANO_ROWS_PER_PAGE
        
        page_slots_len = len(page_slots)
        left_slot_data = page_slots[left_page_index] if left_page_index < page_slots_len else None
        right_slot_data = page_slots[right_page_index] if right_page_index < page_slots_len else None
        
        left_frame = self._create_column_frame(main_container, row, 0, (0, self._PADDING_SMALL))
        right_frame = self._create_column_frame(main_container, row, 2, (self._PADDING_SMALL, 0))
        
        self._create_slot_widget(left_frame, left_slot_data, base_index + left_page_index)
        self._create_slot_widget(right_frame, right_slot_data, base_index + right_page_index)
    
    def _create_column_frame(
        self,
        parent: ctk.CTkFrame,
        row: int,
        column: int,
        padx: Tuple[int, int]
    ) -> ctk.CTkFrame:
        """创建列容器Frame
        
        Args:
            parent: 父容器
            row: 行号
            column: 列号
            padx: 水平边距
            
        Returns:
            创建的Frame
        """
        column_frame = ctk.CTkFrame(parent, fg_color=self.Colors.WHITE)
        column_frame.grid(row=row, column=column, sticky="nsew", padx=padx, pady=self._PADDING_SMALL)
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
            # 循环翻页模式下，翻页按钮始终可用
            prev_state = "normal"
            next_state = "normal"
        else:
            page_text = self._EMPTY_PAGE_TEXT
            prev_state = "disabled"
            next_state = "disabled"

        self.page_info_label.configure(text=page_text)
        self.prev_button.configure(state=prev_state)
        self.next_button.configure(state=next_state)
    
    def _go_to_prev_page(self) -> None:
        """跳转到上一页"""
        if self.analyzer.go_to_prev_page():
            self._refresh_display()
    
    def _go_to_next_page(self) -> None:
        """跳转到下一页"""
        if self.analyzer.go_to_next_page():
            self._refresh_display()
    
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
        
        # 边界检查：确保页码在有效范围内
        total_pages = self.analyzer.total_pages
        if target_page < self._MIN_PAGE_NUMBER:
            showwarning_relative(
                self.root_window,
                self.translate("warning"),
                self.translate("invalid_page_number").format(
                    min=self._MIN_PAGE_NUMBER,
                    max=total_pages if total_pages > 0 else self._MIN_PAGE_NUMBER
                ),
                parent=self.parent
            )
            return
        
        if total_pages > 0 and target_page > total_pages:
            showwarning_relative(
                self.root_window,
                self.translate("warning"),
                self.translate("invalid_page_number").format(
                    min=self._MIN_PAGE_NUMBER,
                    max=total_pages
                ),
                parent=self.parent
            )
            return
        
        if self.analyzer.set_page(target_page):
            self._refresh_display()
            self.jump_entry.delete(0, "end")
    
    def _on_slot_click(self, slot_index: int) -> None:
        """存档槽点击事件
        
        Args:
            slot_index: 存档槽索引
        """
        logger.debug("Save slot clicked: %d", slot_index)
    
    def _on_window_resize(self, event: Optional[tk.Event] = None) -> None:
        """窗口大小变化时的回调
        
        Args:
            event: 窗口事件（可选）
        """
        if self._resize_timer:
            self.parent.after_cancel(self._resize_timer)
        
        self._resize_timer = self.parent.after(
            self._RESIZE_DEBOUNCE_MS,
            self._refresh_display
        )
    
    def update_ui_texts(self) -> None:
        """更新UI文本（用于语言切换）"""
        # 更新翻页按钮文本
        if hasattr(self, 'prev_button') and self.prev_button.winfo_exists():
            self.prev_button.configure(text=self.translate("prev_page"))
        
        if hasattr(self, 'next_button') and self.next_button.winfo_exists():
            self.next_button.configure(text=self.translate("next_page"))
        
        # 更新跳转控件文本
        if hasattr(self, 'jump_label') and self.jump_label.winfo_exists():
            self.jump_label.configure(text=self.translate("jump_to_page"))
        
        if hasattr(self, 'jump_button') and self.jump_button.winfo_exists():
            self.jump_button.configure(text=self.translate("jump"))
        
        # 刷新显示以更新存档槽中的文本
        self._refresh_display()
    
    def refresh(self) -> None:
        """刷新整个视图"""
        self.analyzer.load_save_file()
        self._refresh_display()
