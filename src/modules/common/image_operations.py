"""通用图片操作模块

提供图片导出和替换功能的通用实现，供截图管理和Tyrano存档管理复用
"""

import base64
import logging
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Optional, Union, Callable, Any, Tuple, List
import tkinter as tk
from tkinter import filedialog, Toplevel, Label
from tkinter import ttk
from PIL import Image, ImageTk, UnidentifiedImageError

from src.utils.ui_utils import (
    showinfo_relative,
    showwarning_relative,
    showerror_relative
)
from src.utils.styles import Colors

try:
    from src.modules.save_analysis.tyrano.image_utils import decode_image_data
except ImportError:
    def decode_image_data(image_data: str) -> Optional[Image.Image]:
        """解码base64图片数据（本地实现）"""
        if not isinstance(image_data, str) or not image_data.startswith("data:"):
            return None
        
        sep_pos = image_data.find(",")
        if sep_pos == -1:
            return None
        
        base64_part = image_data[sep_pos + 1:]
        if not base64_part:
            return None
        
        try:
            image_bytes = base64.b64decode(base64_part, validate=True)
            if not image_bytes:
                return None
            
            with BytesIO(image_bytes) as buffer:
                image = Image.open(buffer)
                return image.copy()
        except (ValueError, base64.binascii.Error, UnidentifiedImageError, OSError, IOError):
            return None

logger = logging.getLogger(__name__)

PREVIEW_SIZE: Tuple[int, int] = (400, 300)
EXPORT_QUALITY: int = 95

IMAGE_FILE_TYPES = [
    ("Image files", "*.png *.jpg *.jpeg *.gif *.apng"),
    ("PNG files", "*.png"),
    ("GIF files", "*.gif"),
    ("APNG files", "*.apng"),
    ("All files", "*.*")
]

EXPORT_FORMAT_CONFIG = {
    "png": {
        "filetypes": [("PNG files", "*.png"), ("All files", "*.*")],
        "extension": ".png",
        "save_format": "PNG"
    },
    "jpeg": {
        "filetypes": [("JPEG files", "*.jpg"), ("All files", "*.*")],
        "extension": ".jpg",
        "save_format": "JPEG",
        "requires_rgb": True
    },
    "webp": {
        "filetypes": [("WebP files", "*.webp"), ("All files", "*.*")],
        "extension": ".webp",
        "save_format": "WebP"
    }
}


class ImageExportHelper:
    """图片导出助手类"""
    
    def __init__(
        self,
        root_window: tk.Widget,
        translate_func: Callable[[str], str],
        get_cjk_font_func: Callable[[int], Any],
        colors_class: type,
        set_window_icon_func: Optional[Callable[[Toplevel], None]] = None
    ) -> None:
        """初始化导出助手
        
        Args:
            root_window: 根窗口
            translate_func: 翻译函数
            get_cjk_font_func: 字体获取函数
            colors_class: 颜色常量类
            set_window_icon_func: 窗口图标设置函数（可选）
        """
        self.root = root_window
        self.t = translate_func
        self.get_cjk_font = get_cjk_font_func
        self.Colors = colors_class
        self.set_window_icon = set_window_icon_func or (lambda x: None)
    
    def show_format_dialog(
        self,
        image_data: Union[bytes, Image.Image],
        default_filename: str,
        on_export_callback: Optional[Callable[[str], None]] = None
    ) -> None:
        """显示格式选择对话框并执行导出
        
        Args:
            image_data: 图片数据（bytes或PIL.Image）
            default_filename: 默认文件名（不含扩展名）
            on_export_callback: 导出成功后的回调函数（可选）
        """
        format_dialog = self._create_format_selection_dialog()
        format_var = tk.StringVar(value="png")
        self._create_format_radio_buttons(format_dialog, format_var)
        
        def confirm_export() -> None:
            format_choice = format_var.get()
            format_dialog.destroy()
            self._perform_export(image_data, default_filename, format_choice, on_export_callback)
        
        self._create_dialog_buttons(format_dialog, confirm_export)
    
    def _create_format_selection_dialog(self) -> Toplevel:
        """创建格式选择对话框"""
        dialog = Toplevel(self.root)
        dialog.title(self.t("select_export_format"))
        dialog.geometry("300x200")
        dialog.configure(bg=self.Colors.WHITE)
        self._set_window_icon_with_retry(dialog)
        dialog.transient(self.root)
        dialog.grab_set()
        
        format_label = tk.Label(
            dialog,
            text=self.t("select_image_format"),
            font=self.get_cjk_font(10),
            fg=self.Colors.TEXT_PRIMARY,
            bg=self.Colors.WHITE
        )
        format_label.pack(pady=10)
        
        return dialog
    
    def _set_window_icon_with_retry(self, dialog: Toplevel) -> None:
        """设置窗口图标（带重试机制）"""
        self.set_window_icon(dialog)
        dialog.after(50, lambda: self.set_window_icon(dialog))
        dialog.after(200, lambda: self.set_window_icon(dialog))
    
    def _create_format_radio_buttons(
        self,
        dialog: Toplevel,
        format_var: tk.StringVar
    ) -> None:
        """创建格式单选按钮"""
        format_frame = ttk.Frame(dialog, style="White.TFrame")
        format_frame.pack(pady=10)
        
        for format_name in EXPORT_FORMAT_CONFIG.keys():
            ttk.Radiobutton(
                format_frame,
                text=format_name.upper(),
                variable=format_var,
                value=format_name
            ).pack(side='left', padx=10)
    
    def _create_dialog_buttons(
        self,
        dialog: Toplevel,
        confirm_callback: Callable[[], None]
    ) -> None:
        """创建对话框按钮"""
        button_frame = tk.Frame(dialog, bg=self.Colors.WHITE)
        button_frame.pack(pady=20)
        
        def cancel() -> None:
            dialog.destroy()
        
        ttk.Button(
            button_frame,
            text=self.t("confirm"),
            command=confirm_callback
        ).pack(side="left", padx=10)
        
        ttk.Button(
            button_frame,
            text=self.t("cancel"),
            command=cancel
        ).pack(side="right", padx=10)
        
        dialog.bind('<Return>', lambda e: confirm_callback())
        dialog.bind('<Escape>', lambda e: cancel())
    
    def _perform_export(
        self,
        image_data: Union[bytes, Image.Image],
        default_filename: str,
        format_choice: str,
        on_export_callback: Optional[Callable[[str], None]] = None
    ) -> None:
        """执行导出操作
        
        Args:
            image_data: 图片数据（bytes或PIL.Image）
            default_filename: 默认文件名（不含扩展名）
            format_choice: 格式选择
            on_export_callback: 导出成功后的回调函数（可选）
        """
        if format_choice not in EXPORT_FORMAT_CONFIG:
            showerror_relative(self.root, self.t("error"), self.t("invalid_format"))
            return
        
        format_config = EXPORT_FORMAT_CONFIG[format_choice]
        save_path = filedialog.asksaveasfilename(
            title=self.t("save_image"),
            defaultextension=format_config["extension"],
            filetypes=format_config["filetypes"],
            initialfile=f"{default_filename}{format_config['extension']}"
        )
        
        if not save_path:
            return
        
        temp_png_path: Optional[Path] = None
        try:
            if isinstance(image_data, bytes):
                temp_png_path = Path(tempfile.NamedTemporaryFile(suffix='.png', delete=False).name)
                temp_png_path.write_bytes(image_data)
                img = Image.open(temp_png_path)
            else:
                img = image_data
            
            if format_config.get("requires_rgb", False) and img.mode != "RGB":
                img = img.convert("RGB")
            
            save_kwargs = {"format": format_config["save_format"]}
            if format_choice != "png":
                save_kwargs["quality"] = EXPORT_QUALITY
            
            img.save(save_path, **save_kwargs)
            
            showinfo_relative(
                self.root,
                self.t("success"),
                self.t("export_success").format(path=save_path)
            )
            
            if on_export_callback:
                on_export_callback(save_path)
                
        except (OSError, IOError, UnidentifiedImageError, ValueError) as e:
            logger.error(f"Failed to export image: {e}", exc_info=True)
            showerror_relative(
                self.root,
                self.t("error"),
                f"{self.t('export_failed')}: {str(e)}"
            )
        finally:
            if temp_png_path and temp_png_path.exists():
                try:
                    temp_png_path.unlink()
                except OSError as e:
                    logger.debug(f"Failed to remove temp file {temp_png_path}: {e}")


class ImageReplaceHelper:
    """图片替换助手类"""
    
    def __init__(
        self,
        root_window: tk.Widget,
        translate_func: Callable[[str], str],
        get_cjk_font_func: Callable[[int], Any],
        colors_class: type,
        set_window_icon_func: Optional[Callable[[Toplevel], None]] = None
    ) -> None:
        """初始化替换助手
        
        Args:
            root_window: 根窗口
            translate_func: 翻译函数
            get_cjk_font_func: 字体获取函数
            colors_class: 颜色常量类
            set_window_icon_func: 窗口图标设置函数（可选）
        """
        self.root = root_window
        self.t = translate_func
        self.get_cjk_font = get_cjk_font_func
        self.Colors = colors_class
        self.set_window_icon = set_window_icon_func or (lambda x: None)
        self._photo_refs: List[ImageTk.PhotoImage] = []
    
    def show_replace_flow(
        self,
        original_image: Union[str, Path, Image.Image, bytes],
        on_confirm_callback: Callable[[Path], None],
        is_valid_image_check: Optional[Callable[[Path], bool]] = None
    ) -> None:
        """显示完整的替换流程（文件选择 -> 确认对话框 -> 回调）
        
        Args:
            original_image: 原始图片（路径字符串、Path对象、PIL.Image或bytes）
            on_confirm_callback: 确认替换后的回调函数，接收新图片路径
            is_valid_image_check: 验证图片是否有效的函数（可选）
        """
        new_image_path = self.select_new_image()
        if not new_image_path:
            return
        
        is_valid_image = True
        if is_valid_image_check:
            is_valid_image = is_valid_image_check(new_image_path)
        
        confirmed = self.show_replace_confirmation(
            original_image,
            new_image_path,
            is_valid_image
        )
        
        if confirmed:
            on_confirm_callback(new_image_path)
    
    def select_new_image(self) -> Optional[Path]:
        """打开文件选择对话框选择新图片
        
        Returns:
            选中的图片路径，如果取消则返回None
        """
        new_image_path = filedialog.askopenfilename(
            title=self.t("select_new_image"),
            filetypes=IMAGE_FILE_TYPES
        )
        
        if not new_image_path:
            return None
        
        return Path(new_image_path)
    
    def show_replace_confirmation(
        self,
        original_image: Union[str, Path, Image.Image, bytes],
        new_image_path: Path,
        is_valid_image: bool = True
    ) -> bool:
        """显示替换确认对话框
        
        Args:
            original_image: 原始图片（路径字符串、Path对象、PIL.Image或bytes）
            new_image_path: 新图片路径
            is_valid_image: 是否为有效图片
            
        Returns:
            如果用户确认返回True，否则返回False
        """
        self._photo_refs.clear()
        
        popup = self._create_base_dialog(
            self.t("replace_warning"),
            width=900,
            height=500
        )
        
        if not is_valid_image:
            warning_label = tk.Label(
                popup,
                text=self.t("file_extension_warning", filename=new_image_path.name),
                fg=Colors.TEXT_WARNING_PINK,
                font=self.get_cjk_font(10),
                wraplength=600,
                justify="left",
                bg=self.Colors.WHITE
            )
            warning_label.pack(pady=5, padx=10, anchor="w")
        
        confirm_label = tk.Label(
            popup,
            text=self.t("replace_confirm_text"),
            font=self.get_cjk_font(12),
            fg=self.Colors.TEXT_PRIMARY,
            bg=self.Colors.WHITE
        )
        confirm_label.pack(pady=10)
        
        image_frame = tk.Frame(popup, bg=self.Colors.WHITE)
        image_frame.pack(pady=10)
        
        self._display_image_preview(image_frame, original_image, "orig_photo")
        self._display_arrow_label(image_frame)
        self._display_image_preview(image_frame, str(new_image_path), "new_photo")
        
        question_label = tk.Label(
            popup,
            text=self.t("replace_confirm_question"),
            font=self.get_cjk_font(10),
            fg=self.Colors.TEXT_PRIMARY,
            bg=self.Colors.WHITE
        )
        question_label.pack(pady=10)
        
        confirmed = False
        
        def confirm_replace() -> None:
            nonlocal confirmed
            confirmed = True
            popup.destroy()
        
        def cancel_replace() -> None:
            popup.destroy()
        
        button_frame = tk.Frame(popup, bg=self.Colors.WHITE)
        button_frame.pack(pady=10)
        
        ttk.Button(
            button_frame,
            text=self.t("replace_yes"),
            command=confirm_replace
        ).pack(side="left", padx=10)
        
        ttk.Button(
            button_frame,
            text=self.t("replace_no"),
            command=cancel_replace
        ).pack(side="right", padx=10)
        
        popup.bind('<Return>', lambda e: confirm_replace())
        popup.bind('<Escape>', lambda e: cancel_replace())
        
        self.root.wait_window(popup)
        return confirmed
    
    def _create_base_dialog(self, title: str, width: int, height: int) -> Toplevel:
        """创建基础对话框"""
        dialog = Toplevel(self.root)
        dialog.title(title)
        dialog.geometry(f"{width}x{height}")
        dialog.configure(bg=self.Colors.WHITE)
        self._set_window_icon_with_retry(dialog)
        dialog.transient(self.root)
        dialog.grab_set()
        return dialog
    
    def _set_window_icon_with_retry(self, dialog: Toplevel) -> None:
        """设置窗口图标（带重试机制）"""
        self.set_window_icon(dialog)
        dialog.after(50, lambda: self.set_window_icon(dialog))
        dialog.after(200, lambda: self.set_window_icon(dialog))
    
    def _display_image_preview(
        self,
        parent_frame: tk.Frame,
        image_source: Union[str, Path, Image.Image, bytes],
        attribute_name: str
    ) -> None:
        """显示图片预览
        
        Args:
            parent_frame: 父框架
            image_source: 图片源（路径字符串、Path对象、PIL.Image、bytes或data URI字符串）
            attribute_name: 属性名称（未使用，保留以兼容现有调用）
        """
        try:
            img = self._load_image_from_source(image_source)
            preview_img = img.resize(PREVIEW_SIZE, Image.Resampling.BILINEAR)
            photo = ImageTk.PhotoImage(preview_img)
            
            label = Label(parent_frame, image=photo, bg=self.Colors.WHITE)
            label.pack(side="left", padx=10)
            
            self._photo_refs.append(photo)
        except (OSError, IOError, UnidentifiedImageError, ValueError) as e:
            logger.debug(f"Failed to display image preview: {e}")
            error_label = Label(
                parent_frame,
                text=self.t("preview_failed"),
                fg="red",
                font=self.get_cjk_font(12),
                bg=self.Colors.WHITE
            )
            error_label.pack(side="left", padx=10)
    
    def _load_image_from_source(
        self,
        image_source: Union[str, Path, Image.Image, bytes]
    ) -> Image.Image:
        """从不同来源加载图片
        
        Args:
            image_source: 图片源
            
        Returns:
            PIL Image对象
            
        Raises:
            ValueError: 不支持的图片源类型或解码失败
            OSError: 文件读取错误
            UnidentifiedImageError: 无法识别的图片格式
        """
        if isinstance(image_source, str):
            if image_source.startswith("data:"):
                img = decode_image_data(image_source)
                if img is None:
                    raise ValueError("Failed to decode data URI image")
                return img
            else:
                return Image.open(image_source)
        elif isinstance(image_source, Path):
            return Image.open(image_source)
        elif isinstance(image_source, Image.Image):
            return image_source
        elif isinstance(image_source, bytes):
            return Image.open(BytesIO(image_source))
        else:
            raise ValueError(f"Unsupported image source type: {type(image_source)}")
    
    def _display_arrow_label(self, parent_frame: tk.Frame) -> None:
        """显示箭头标签"""
        arrow_label = tk.Label(
            parent_frame,
            text="→",
            font=self.get_cjk_font(24),
            fg=self.Colors.TEXT_PRIMARY,
            bg=self.Colors.WHITE
        )
        arrow_label.pack(side="left", padx=10)
