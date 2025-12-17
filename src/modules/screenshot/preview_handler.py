"""预览处理模块

负责处理截图预览的显示，包括图片解码、缩放和显示。
"""

import os
import json
import urllib.parse
import base64
import tempfile
from typing import Optional, Tuple
from pathlib import Path
import tkinter as tk
from tkinter import Label
from PIL import Image, ImageTk

from src.modules.screenshot.constants import PREVIEW_WIDTH, PREVIEW_HEIGHT


class PreviewHandler:
    """预览处理器
    
    管理截图预览的加载和显示。
    """
    
    def __init__(self, preview_label: Label, root: tk.Tk, 
                 storage_dir: Optional[str], screenshot_manager, 
                 colors, t_func, preview_size: Optional[Tuple[int, int]] = None):
        """初始化预览处理器
        
        Args:
            preview_label: 预览标签组件
            root: 根窗口实例
            storage_dir: 存储目录路径
            screenshot_manager: 截图管理器实例
            colors: 颜色常量类
            t_func: 翻译函数
            preview_size: 预览尺寸，默认为None使用常量值
        """
        self.preview_label = preview_label
        self.root = root
        self.storage_dir = storage_dir
        self.screenshot_manager = screenshot_manager
        self.colors = colors
        self.t = t_func
        self.preview_size = preview_size or (PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self.preview_photo: Optional[ImageTk.PhotoImage] = None
    
    def show_preview(self, id_str: str) -> None:
        """显示指定ID的预览图片
        
        Args:
            id_str: 截图ID字符串
        """
        if not self._validate_preview_request(id_str):
            self._clear_preview()
            return
        
        main_file = self.screenshot_manager.sav_pairs[id_str][0]
        if not main_file:
            self._show_error(self.t("file_missing_text"))
            return
        
        main_sav_path = Path(self.storage_dir) / main_file
        if not main_sav_path.exists():
            self._show_error(self.t("file_not_exist_text"))
            return
        
        self._load_and_display_image(main_sav_path)
    
    def _validate_preview_request(self, id_str: str) -> bool:
        """验证预览请求是否有效
        
        Args:
            id_str: 截图ID字符串
            
        Returns:
            如果有效返回True，否则返回False
        """
        return (self.storage_dir is not None and 
                id_str in self.screenshot_manager.sav_pairs)
    
    def _clear_preview(self) -> None:
        """清除预览显示"""
        self.preview_label.config(image='', bg="lightgray")
        self.preview_photo = None
    
    def _show_error(self, error_text: str) -> None:
        """显示错误信息
        
        Args:
            error_text: 错误文本
        """
        self.preview_label.config(image='', bg="lightgray", text=error_text)
        self.preview_photo = None
    
    def _load_and_display_image(self, sav_path: Path) -> None:
        """加载并显示图片
        
        Args:
            sav_path: sav文件路径
        """
        temp_png_path: Optional[Path] = None
        
        try:
            # 解码sav文件
            img_data = self._decode_sav_file(sav_path)
            if img_data is None:
                self._show_error(self.t("preview_failed"))
                return
            
            # 保存为临时PNG文件
            temp_png_path = Path(tempfile.NamedTemporaryFile(suffix='.png', delete=False).name)
            temp_png_path.write_bytes(img_data)
            
            # 加载并缩放图片
            with Image.open(temp_png_path) as img:
                preview_img = img.resize(self.preview_size, Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(preview_img)
                
                self.preview_label.config(image=photo, bg=self.colors.WHITE, text="")
                self.preview_photo = photo
                
        except (OSError, IOError, json.JSONDecodeError, ValueError) as e:
            # 记录错误但不向用户显示技术细节
            self._show_error(self.t("preview_failed"))
        finally:
            # 清理临时文件
            if temp_png_path and temp_png_path.exists():
                try:
                    temp_png_path.unlink()
                except OSError:
                    pass  # 忽略删除失败，系统会清理临时文件
    
    def _decode_sav_file(self, sav_path: Path) -> Optional[bytes]:
        """解码sav文件为图片数据
        
        Args:
            sav_path: sav文件路径
            
        Returns:
            图片的二进制数据，如果解码失败返回None
        """
        try:
            encoded = sav_path.read_text(encoding='utf-8').strip()
            unquoted = urllib.parse.unquote(encoded)
            data_uri = json.loads(unquoted)
            
            if ';base64,' not in data_uri:
                return None
            
            b64_part = data_uri.split(';base64,', 1)[1]
            return base64.b64decode(b64_part)
        except (OSError, IOError, json.JSONDecodeError, ValueError, base64.binascii.Error):
            return None

