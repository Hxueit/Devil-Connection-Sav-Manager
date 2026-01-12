"""对话框组件模块

提供截图管理相关的对话框功能，包括添加、替换、导出等对话框
"""

import json
import logging
import urllib.parse
import base64
import tempfile
import threading
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Callable, Any
import tkinter as tk
from tkinter import filedialog, messagebox, Toplevel, Label, Entry
from tkinter import ttk
from PIL import Image, ImageTk, UnidentifiedImageError

from src.modules.screenshot.constants import (
    VALID_IMAGE_EXTENSIONS, GALLERY_OPERATION_ADD, GALLERY_OPERATION_REPLACE
)
from src.modules.common.image_operations import ImageExportHelper, ImageReplaceHelper
from src.utils.ui_utils import (
    showinfo_relative, showwarning_relative, showerror_relative, askyesno_relative
)
from src.utils.styles import Colors

logger = logging.getLogger(__name__)

# 常量定义
DATE_FORMAT = '%Y/%m/%d %H:%M:%S'
ASPECT_RATIO_TOLERANCE = 30
ASPECT_RATIO = 4 / 3
PREVIEW_SIZE = (400, 300)
EXPORT_QUALITY = 95
DEFAULT_WINDOW_HEIGHT = 300
WARNING_HEIGHT_INCREMENT = 80

# 文件类型配置
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


class ScreenshotDialogs:
    """截图对话框管理类"""
    
    def __init__(
        self,
        root: tk.Tk,
        storage_dir: Optional[str],
        screenshot_manager: Any,
        t_func: Callable[[str], str],
        get_cjk_font: Callable[[int], Any],
        Colors: Any,
        set_window_icon: Callable[[tk.Toplevel], None],
        translations: Dict[str, Dict[str, str]],
        current_language: str,
        load_screenshots_callback: Callable[[], None],
        show_status_indicator_callback: Callable[[str, bool], None],
        gallery_refresh_callback: Optional[Callable[[str, str], None]] = None
    ) -> None:
        """初始化对话框管理器
        
        Args:
            root: 根窗口
            storage_dir: 存储目录
            screenshot_manager: 截图管理器实例
            t_func: 翻译函数
            get_cjk_font: 字体获取函数
            Colors: 颜色常量类
            set_window_icon: 窗口图标设置函数
            translations: 翻译字典
            current_language: 当前语言
            load_screenshots_callback: 加载截图列表的回调函数
            show_status_indicator_callback: 显示状态指示器的回调函数
            gallery_refresh_callback: 画廊刷新回调函数，接收(operation_type, screenshot_id)参数，可选
        """
        self.root = root
        self.storage_dir = Path(storage_dir) if storage_dir else None
        self.screenshot_manager = screenshot_manager
        self.t = t_func
        self.get_cjk_font = get_cjk_font
        self.Colors = Colors
        self.set_window_icon = set_window_icon
        self.translations = translations
        self.current_language = current_language
        self.load_screenshots_callback = load_screenshots_callback
        self.show_status_indicator_callback = show_status_indicator_callback
        self.gallery_refresh_callback = gallery_refresh_callback
        self._photo_refs: List[ImageTk.PhotoImage] = []
    
    def show_add_dialog(self) -> None:
        """显示添加新截图对话框"""
        image_path = filedialog.askopenfilename(
            title=self.t("select_new_image"),
            filetypes=IMAGE_FILE_TYPES
        )
        
        if not image_path:
            return
        
        image_path_obj = Path(image_path)
        if not image_path_obj.exists():
            showerror_relative(self.root, self.t("error"), self.t("file_not_exist"))
            return
        
        file_extension = image_path_obj.suffix.lower()
        is_valid_image = file_extension in VALID_IMAGE_EXTENSIONS
        is_4_3_ratio = False
        
        if is_valid_image:
            is_4_3_ratio = self._check_aspect_ratio(image_path_obj)
        
        dialog = self._create_base_dialog(
            self.t("add_new_title"),
            width=400,
            height=self._calculate_dialog_height(is_valid_image, is_4_3_ratio)
        )
        
        self._add_warning_labels(dialog, image_path_obj.name, is_valid_image, is_4_3_ratio)
        
        id_entry, date_entry = self._create_input_fields(dialog)
        self._create_dialog_buttons(
            dialog,
            confirm_callback=lambda: self._handle_add_confirm(
                dialog, id_entry, date_entry, image_path_obj, is_valid_image
            )
        )
        
        id_entry.focus()
    
    def _check_aspect_ratio(self, image_path: Path) -> bool:
        """检查图片是否为4:3比例
        
        Args:
            image_path: 图片路径
            
        Returns:
            如果是4:3比例返回True，否则返回False
        """
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                expected_height = width * (1 / ASPECT_RATIO)
                return abs(height - expected_height) <= ASPECT_RATIO_TOLERANCE
        except (OSError, IOError, UnidentifiedImageError) as e:
            logger.debug(f"Failed to check aspect ratio for {image_path}: {e}")
            return False
    
    def _calculate_dialog_height(self, is_valid_image: bool, is_4_3_ratio: bool) -> int:
        """计算对话框高度
        
        Args:
            is_valid_image: 是否为有效图片
            is_4_3_ratio: 是否为4:3比例
            
        Returns:
            对话框高度
        """
        height = DEFAULT_WINDOW_HEIGHT
        if not is_valid_image:
            height += WARNING_HEIGHT_INCREMENT
        if not is_4_3_ratio and is_valid_image:
            height += WARNING_HEIGHT_INCREMENT
        return height
    
    def _create_base_dialog(self, title: str, width: int, height: int) -> Toplevel:
        """创建基础对话框
        
        Args:
            title: 对话框标题
            width: 对话框宽度
            height: 对话框高度
            
        Returns:
            对话框窗口
        """
        dialog = Toplevel(self.root)
        dialog.title(title)
        dialog.geometry(f"{width}x{height}")
        dialog.configure(bg=self.Colors.WHITE)
        self.set_window_icon(dialog)
        dialog.transient(self.root)
        dialog.grab_set()
        return dialog
    
    def _add_warning_labels(
        self,
        dialog: Toplevel,
        filename: str,
        is_valid_image: bool,
        is_4_3_ratio: bool
    ) -> None:
        """添加警告标签
        
        Args:
            dialog: 对话框窗口
            filename: 文件名
            is_valid_image: 是否为有效图片
            is_4_3_ratio: 是否为4:3比例
        """
        if not is_valid_image:
            warning_label = tk.Label(
                dialog,
                text=self.t("file_extension_warning", filename=filename),
                fg=Colors.TEXT_WARNING_PINK,
                font=self.get_cjk_font(10),
                wraplength=380,
                justify="left",
                bg=self.Colors.WHITE
            )
            warning_label.pack(pady=5, padx=10, anchor="w")
        
        if not is_4_3_ratio and is_valid_image:
            aspect_warning_label = tk.Label(
                dialog,
                text=self.t("aspect_ratio_warning"),
                fg=Colors.TEXT_WARNING_AQUA,
                font=self.get_cjk_font(10),
                wraplength=380,
                justify="left",
                bg=self.Colors.WHITE
            )
            aspect_warning_label.pack(pady=5, padx=10, anchor="w")
    
    def _create_input_fields(self, dialog: Toplevel) -> Tuple[Entry, Entry]:
        """创建输入字段
        
        Args:
            dialog: 对话框窗口
            
        Returns:
            (id_entry, date_entry) 元组
        """
        id_frame = ttk.Frame(dialog, style="White.TFrame")
        id_frame.pack(pady=10, padx=20, fill='x')
        id_label = tk.Label(
            id_frame,
            text=self.t("id_label"),
            font=self.get_cjk_font(10),
            fg=self.Colors.TEXT_PRIMARY,
            bg=self.Colors.WHITE
        )
        id_label.pack(anchor='w')
        id_entry = Entry(id_frame, width=40)
        id_entry.pack(fill='x', pady=(5, 0))
        
        date_frame = ttk.Frame(dialog, style="White.TFrame")
        date_frame.pack(pady=10, padx=20, fill='x')
        date_label = tk.Label(
            date_frame,
            text=self.t("date_label"),
            font=self.get_cjk_font(10),
            fg=self.Colors.TEXT_PRIMARY,
            bg=self.Colors.WHITE
        )
        date_label.pack(anchor='w')
        date_entry = Entry(date_frame, width=40)
        date_entry.pack(fill='x', pady=(5, 0))
        
        return id_entry, date_entry
    
    def _create_dialog_buttons(
        self,
        dialog: Toplevel,
        confirm_callback: Callable[[], None]
    ) -> None:
        """创建对话框按钮
        
        Args:
            dialog: 对话框窗口
            confirm_callback: 确认回调函数
        """
        button_frame = ttk.Frame(dialog, style="White.TFrame")
        button_frame.pack(pady=10)
        
        ttk.Button(
            button_frame,
            text=self.t("confirm"),
            command=confirm_callback
        ).pack(side='left', padx=5)
        
        ttk.Button(
            button_frame,
            text=self.t("delete_cancel"),
            command=dialog.destroy
        ).pack(side='left', padx=5)
    
    def _handle_add_confirm(
        self,
        dialog: Toplevel,
        id_entry: Entry,
        date_entry: Entry,
        image_path: Path,
        is_valid_image: bool
    ) -> None:
        """处理添加确认
        
        Args:
            dialog: 对话框窗口
            id_entry: ID输入框
            date_entry: 日期输入框
            image_path: 图片路径
            is_valid_image: 是否为有效图片
        """
        screenshot_id = id_entry.get().strip()
        date_string = date_entry.get().strip()
        
        if not screenshot_id:
            screenshot_id = self.screenshot_manager.generate_id()
        
        if screenshot_id in self.screenshot_manager.sav_pairs:
            showerror_relative(self.root, self.t("error"), self.t("id_exists"))
            return
        
        if not date_string:
            date_string = self.screenshot_manager.get_current_datetime()
        else:
            if not self._validate_date_format(date_string):
                showerror_relative(
                    self.root,
                    self.t("error"),
                    self.t("invalid_date_format")
                )
                return
        
        if not is_valid_image:
            if not askyesno_relative(
                self.root,
                self.t("warning"),
                self.t("file_extension_warning").format(filename=image_path.name)
            ):
                dialog.destroy()
                return
        
        success, message = self.screenshot_manager.add_screenshot(
            screenshot_id,
            date_string,
            str(image_path)
        )
        
        if success:
            showinfo_relative(
                self.root,
                self.t("success"),
                self.t("add_success").format(id=screenshot_id)
            )
            self.load_screenshots_callback()
            self.show_status_indicator_callback(screenshot_id, is_new=True)
            if self.gallery_refresh_callback:
                try:
                    self.gallery_refresh_callback(GALLERY_OPERATION_ADD, screenshot_id)
                except Exception as e:
                    logger.warning(f"Gallery refresh callback failed after add: {e}", exc_info=True)
        else:
            showerror_relative(self.root, self.t("error"), message)
        
        dialog.destroy()
    
    def _validate_date_format(self, date_string: str) -> bool:
        """验证日期格式
        
        Args:
            date_string: 日期字符串
            
        Returns:
            如果格式有效返回True，否则返回False
        """
        try:
            datetime.strptime(date_string, DATE_FORMAT)
            return True
        except ValueError:
            return False
    
    def show_replace_dialog(
        self,
        screenshot_id: str,
        checkbox_vars: Dict[str, Any],
        tree: ttk.Treeview
    ) -> None:
        """显示替换截图对话框
        
        Args:
            screenshot_id: 截图ID
            checkbox_vars: 复选框变量字典
            tree: Treeview组件
        """
        if not self.storage_dir:
            showerror_relative(self.root, self.t("error"), self.t("file_missing"))
            return
        
        file_pair = self.screenshot_manager.sav_pairs.get(screenshot_id, [None, None])
        if file_pair[0] is None or file_pair[1] is None:
            showerror_relative(self.root, self.t("error"), self.t("file_missing"))
            return
        
        main_sav_path = self.storage_dir / file_pair[0]
        thumb_sav_path = self.storage_dir / file_pair[1]
        
        if not main_sav_path.exists() or not thumb_sav_path.exists():
            showerror_relative(self.root, self.t("error"), self.t("file_not_exist"))
            return
        
        temp_png_path = None
        try:
            temp_png_path = self._extract_image_from_sav(main_sav_path)
            if temp_png_path is None:
                messagebox.showerror(self.t("error"), self.t("file_not_found"))
                return
            
            replace_helper = ImageReplaceHelper(
                self.root,
                self.t,
                self.get_cjk_font,
                self.Colors,
                self.set_window_icon
            )
            
            def on_replace_confirm(new_image_path: Path) -> None:
                success, message = self._replace_sav_files(
                    screenshot_id,
                    main_sav_path,
                    thumb_sav_path,
                    new_image_path
                )
                
                if success:
                    showinfo_relative(
                        self.root,
                        self.t("success"),
                        self.t("replace_success").format(id=screenshot_id)
                    )
                    self.load_screenshots_callback()
                    self.show_status_indicator_callback(screenshot_id, is_new=False)
                    if self.gallery_refresh_callback:
                        try:
                            self.gallery_refresh_callback(GALLERY_OPERATION_REPLACE, screenshot_id)
                        except Exception as e:
                            logger.warning(f"Gallery refresh callback failed after replace: {e}", exc_info=True)
                else:
                    showerror_relative(self.root, self.t("error"), message)
            
            replace_helper.show_replace_flow(
                temp_png_path,
                on_replace_confirm,
                lambda path: path.suffix.lower() in VALID_IMAGE_EXTENSIONS
            )
        finally:
            if temp_png_path and Path(temp_png_path).exists():
                try:
                    Path(temp_png_path).unlink()
                except OSError as e:
                    logger.debug(f"Failed to remove temp file {temp_png_path}: {e}")
    
    def _extract_image_from_sav(self, sav_path: Path) -> Optional[str]:
        """从sav文件提取图片到临时文件
        
        Args:
            sav_path: sav文件路径
            
        Returns:
            临时PNG文件路径，失败时返回None
        """
        try:
            encoded_data = sav_path.read_text(encoding='utf-8').strip()
            unquoted_data = urllib.parse.unquote(encoded_data)
            data_uri = json.loads(unquoted_data)
            
            if ';base64,' not in data_uri:
                return None
            
            base64_part = data_uri.split(';base64,', 1)[1]
            image_data = base64.b64decode(base64_part)
            
            temp_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            temp_png.write(image_data)
            temp_png.close()
            
            return temp_png.name
        except (OSError, IOError, json.JSONDecodeError, ValueError, KeyError, base64.binascii.Error) as e:
            logger.error(f"Failed to extract image from sav file {sav_path}: {e}")
            return None
    
    
    def _replace_sav_files(
        self,
        screenshot_id: str,
        main_sav_path: Path,
        thumb_sav_path: Path,
        new_image_path: Path
    ) -> Tuple[bool, str]:
        """替换sav文件
        
        Args:
            screenshot_id: 截图ID
            main_sav_path: 主sav文件路径
            thumb_sav_path: 缩略图sav文件路径
            new_image_path: 新图片路径
            
        Returns:
            (成功标志, 消息字符串) 元组
        """
        try:
            # 从文件名提取ID（移除前缀和后缀）
            success, message = self.screenshot_manager.replace_screenshot(
                screenshot_id,
                str(new_image_path)
            )
            return success, message
        except Exception as e:
            logger.error(f"Failed to replace sav files: {e}", exc_info=True)
            return False, str(e)
    
    def show_export_dialog(self, screenshot_id: str) -> None:
        """显示导出图片对话框
        
        Args:
            screenshot_id: 截图ID
        """
        image_data = self.screenshot_manager.get_image_data(screenshot_id)
        if not image_data:
            messagebox.showerror(self.t("error"), self.t("file_not_found"))
            return
        
        export_helper = ImageExportHelper(
            self.root,
            self.t,
            self.get_cjk_font,
            self.Colors,
            self.set_window_icon
        )
        
        export_helper.show_format_dialog(image_data, screenshot_id)
    
    
    def show_batch_export_dialog(self, selected_ids: List[str]) -> None:
        """显示批量导出对话框
        
        Args:
            selected_ids: 选中的截图ID列表
        """
        if not selected_ids:
            showwarning_relative(
                self.root,
                self.t("warning"),
                self.t("select_screenshot")
            )
            return
        
        format_dialog = self._create_format_selection_dialog()
        format_var = tk.StringVar(value="png")
        self._create_format_radio_buttons(format_dialog, format_var)
        
        def confirm_batch_export() -> None:
            format_choice = format_var.get()
            format_dialog.destroy()
            self._perform_batch_export(selected_ids, format_choice)
        
        self._create_dialog_buttons(format_dialog, confirm_batch_export)
    
    def _perform_batch_export(
        self,
        selected_ids: List[str],
        format_choice: str
    ) -> None:
        """执行批量导出操作
        
        Args:
            selected_ids: 选中的截图ID列表
            format_choice: 格式选择
        """
        if format_choice not in EXPORT_FORMAT_CONFIG:
            showerror_relative(self.root, self.t("error"), self.t("invalid_format"))
            return
        
        save_path = filedialog.asksaveasfilename(
            title=self.t("save_zip"),
            defaultextension=".zip",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
            initialfile="DevilConnectionSSPack.zip"
        )
        
        if not save_path:
            return
        
        progress_window = self._create_progress_window(len(selected_ids))
        progress_bar = progress_window.nametowidget("progress_bar")
        status_label = progress_window.nametowidget("status_label")
        success_label = progress_window.nametowidget("success_label")
        close_button = progress_window.nametowidget("close_button")
        
        def update_progress(current: int, total: int, exported: int, failed: int) -> None:
            """更新进度条"""
            progress_bar['value'] = current
            status_label.config(text=f"{current}/{total}")
            progress_window.update_idletasks()
        
        def show_success(exported_count: int, failed_count: int) -> None:
            """显示成功信息"""
            progress_bar.pack_forget()
            status_label.pack_forget()
            progress_window.nametowidget("progress_label").config(text="")
            
            success_msg = self._get_batch_export_message(exported_count, failed_count)
            success_label.config(text=success_msg)
            success_label.pack(pady=20)
            close_button.pack(pady=10)
            progress_window.protocol("WM_DELETE_WINDOW", progress_window.destroy)
        
        def show_error(error_msg: str) -> None:
            """显示错误信息"""
            progress_bar.pack_forget()
            status_label.pack_forget()
            progress_label = progress_window.nametowidget("progress_label")
            progress_label.config(text=error_msg, fg="red")
            close_button.pack(pady=10)
            progress_window.protocol("WM_DELETE_WINDOW", progress_window.destroy)
        
        def export_in_thread() -> None:
            """在后台线程中执行导出"""
            try:
                exported_count = 0
                failed_count = 0
                
                with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for idx, screenshot_id in enumerate(selected_ids):
                        image_data = self.screenshot_manager.get_image_data(screenshot_id)
                        if image_data:
                            if self._add_image_to_zip(
                                zip_file,
                                screenshot_id,
                                image_data,
                                format_choice
                            ):
                                exported_count += 1
                            else:
                                failed_count += 1
                        else:
                            failed_count += 1
                        
                        current = idx + 1
                        progress_window.after(
                            0,
                            update_progress,
                            current,
                            len(selected_ids),
                            exported_count,
                            failed_count
                        )
                
                if exported_count > 0:
                    progress_window.after(0, show_success, exported_count, failed_count)
                else:
                    error_msg = self._get_batch_export_error_message()
                    progress_window.after(0, show_error, error_msg)
            except Exception as e:
                logger.error(f"Batch export failed: {e}", exc_info=True)
                error_msg = f"{self.t('export_failed')}: {str(e)}"
                progress_window.after(0, show_error, error_msg)
        
        thread = threading.Thread(target=export_in_thread, daemon=True)
        thread.start()
    
    def _create_progress_window(self, total_count: int) -> Toplevel:
        """创建进度窗口
        
        Args:
            total_count: 总数
            
        Returns:
            进度窗口
        """
        progress_window = self._create_base_dialog(
            self.t("batch_export_progress"),
            width=450,
            height=200
        )
        progress_window.protocol("WM_DELETE_WINDOW", lambda: None)
        
        progress_label = tk.Label(
            progress_window,
            text=self.t("exporting_images"),
            font=self.get_cjk_font(10),
            fg=self.Colors.TEXT_PRIMARY,
            bg=self.Colors.WHITE
        )
        progress_label.pack(pady=10)
        progress_label.name = "progress_label"
        
        progress_bar = ttk.Progressbar(progress_window, length=350, mode='determinate')
        progress_bar.pack(pady=10, padx=20, fill="x")
        progress_bar['maximum'] = total_count
        progress_bar['value'] = 0
        progress_bar.name = "progress_bar"
        
        status_label = tk.Label(
            progress_window,
            text=f"0/{total_count}",
            font=self.get_cjk_font(9),
            fg=self.Colors.TEXT_PRIMARY,
            bg=self.Colors.WHITE
        )
        status_label.pack(pady=5)
        status_label.name = "status_label"
        
        success_label = tk.Label(
            progress_window,
            text="",
            font=self.get_cjk_font(10),
            bg=self.Colors.WHITE,
            fg="green"
        )
        success_label.name = "success_label"
        
        close_button = ttk.Button(
            progress_window,
            text=self.t("close"),
            command=progress_window.destroy
        )
        close_button.name = "close_button"
        
        return progress_window
    
    def _add_image_to_zip(
        self,
        zip_file: zipfile.ZipFile,
        screenshot_id: str,
        image_data: bytes,
        format_choice: str
    ) -> bool:
        """将图片添加到ZIP文件
        
        Args:
            zip_file: ZIP文件对象
            screenshot_id: 截图ID
            image_data: 图片数据
            format_choice: 格式选择
            
        Returns:
            如果成功返回True，否则返回False
        """
        if format_choice not in EXPORT_FORMAT_CONFIG:
            return False
        
        format_config = EXPORT_FORMAT_CONFIG[format_choice]
        temp_png_path = None
        
        try:
            temp_png_path = Path(tempfile.NamedTemporaryFile(suffix='.png', delete=False).name)
            temp_png_path.write_bytes(image_data)
            
            with Image.open(temp_png_path) as img:
                output = BytesIO()
                
                if format_config.get("requires_rgb", False) and img.mode != "RGB":
                    img = img.convert("RGB")
                
                img.save(
                    output,
                    format_config["save_format"],
                    quality=EXPORT_QUALITY if format_choice != "png" else None
                )
                
                zip_file.writestr(
                    f"{screenshot_id}{format_config['extension']}",
                    output.getvalue()
                )
            
            return True
        except (OSError, IOError, UnidentifiedImageError, ValueError) as e:
            logger.debug(f"Failed to add image {screenshot_id} to zip: {e}")
            return False
        finally:
            if temp_png_path and temp_png_path.exists():
                try:
                    temp_png_path.unlink()
                except OSError as e:
                    logger.debug(f"Failed to remove temp file {temp_png_path}: {e}")
    
    def _get_batch_export_message(self, exported_count: int, failed_count: int) -> str:
        """获取批量导出消息
        
        Args:
            exported_count: 成功导出数量
            failed_count: 失败数量
            
        Returns:
            消息字符串
        """
        if "batch_export_success" in self.translations.get(self.current_language, {}):
            success_msg = self.t("batch_export_success", count=exported_count)
        else:
            success_msg = f"成功导出 {exported_count} 张图片到ZIP文件！"
        
        if failed_count > 0:
            if "batch_export_failed" in self.translations.get(self.current_language, {}):
                failed_msg = self.t("batch_export_failed", count=failed_count)
            else:
                failed_msg = f"失败: {failed_count} 张"
            success_msg += f"\n{failed_msg}"
        
        return success_msg
    
    def _get_batch_export_error_message(self) -> str:
        """获取批量导出错误消息
        
        Returns:
            错误消息字符串
        """
        if "batch_export_error_all" in self.translations.get(self.current_language, {}):
            return self.t("batch_export_error_all")
        return "没有成功导出任何图片！"
