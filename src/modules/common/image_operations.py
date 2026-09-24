"""图片导出 / 替换对话框

截图管理和 Tyrano 存档管理共用：
    ImageExportHelper   选择格式 -> 选择保存位置 -> 导出单张图片
    ImageReplaceHelper  选择新图片 -> 新旧对比确认 -> 回调
"""

import logging
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, List, Optional, Union

import tkinter as tk
from tkinter import filedialog, ttk
from PIL import Image, ImageTk

from src.utils.images import IMAGE_FILE_TYPES, ImageSource, open_image
from src.utils.ui_utils import showerror_relative, showinfo_relative

logger = logging.getLogger(__name__)

EXPORT_QUALITY = 95
REPLACE_PREVIEW_SIZE = (400, 300)

# 导出格式 -> (扩展名, Pillow 格式名, 文件类型过滤)
EXPORT_FORMATS = {
    "png": (".png", "PNG", [("PNG files", "*.png"), ("All files", "*.*")]),
    "jpeg": (".jpg", "JPEG", [("JPEG files", "*.jpg"), ("All files", "*.*")]),
    "webp": (".webp", "WebP", [("WebP files", "*.webp"), ("All files", "*.*")]),
}

def convert_image(img: Image.Image, format_choice: str) -> bytes:
    """把图片转成指定导出格式（png/jpeg/webp）的字节"""
    save_format = EXPORT_FORMATS[format_choice][1]
    if save_format == "JPEG" and img.mode != "RGB":
        img = img.convert("RGB")
    buffer = BytesIO()
    if save_format == "PNG":
        img.save(buffer, save_format)
    else:
        img.save(buffer, save_format, quality=EXPORT_QUALITY)
    return buffer.getvalue()


def apply_modal_grab_safely(dialog: tk.Toplevel, retry_count: int = 12, delay_ms: int = 30) -> None:
    """设置模态 grab；窗口还没显示出来时 grab_set 会报错，稍后重试"""
    try:
        dialog.deiconify()
        dialog.update_idletasks()
    except tk.TclError:
        pass

    def try_grab(remaining: int) -> None:
        if remaining <= 0 or not dialog.winfo_exists():
            return
        try:
            dialog.grab_set()
        except tk.TclError:
            dialog.after(delay_ms, lambda: try_grab(remaining - 1))

    try_grab(retry_count)


class _DialogBase:
    def __init__(self, root_window: tk.Misc, translate_func: Callable[..., str],
                 get_cjk_font_func: Callable[..., Any], colors_class: type,
                 set_window_icon_func: Optional[Callable[[tk.Toplevel], None]] = None) -> None:
        self.root = root_window
        self.t = translate_func
        self.get_cjk_font = get_cjk_font_func
        self.Colors = colors_class
        self.set_window_icon = set_window_icon_func or (lambda window: None)

    def _create_dialog(self, title: str, geometry: str) -> tk.Toplevel:
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry(geometry)
        dialog.configure(bg=self.Colors.WHITE)
        # 某些平台（以及 CTk 窗口）会在显示后重置图标，所以多设几次
        self.set_window_icon(dialog)
        dialog.after(50, lambda: self.set_window_icon(dialog))
        dialog.after(200, lambda: self.set_window_icon(dialog))
        dialog.transient(self.root)
        apply_modal_grab_safely(dialog)
        return dialog

    def _label(self, parent: tk.Misc, text: str, size: int = 10, **kwargs) -> tk.Label:
        options = dict(font=self.get_cjk_font(size), fg=self.Colors.TEXT_PRIMARY, bg=self.Colors.WHITE)
        options.update(kwargs)
        return tk.Label(parent, text=text, **options)


class ImageExportHelper(_DialogBase):
    """选择导出格式并保存图片"""

    def show_format_dialog(self, image_data: Union[bytes, Image.Image], default_filename: str,
                           on_export_callback: Optional[Callable[[str], None]] = None) -> None:
        """选择格式 -> 选择保存路径 -> 导出"""
        self.ask_format(lambda fmt: self._export(image_data, default_filename, fmt, on_export_callback))

    def ask_format(self, on_confirm: Callable[[str], None]) -> None:
        """弹出格式选择对话框，确认后以所选格式（如 "png"）调用 on_confirm"""
        dialog = self._create_dialog(self.t("select_export_format"), "300x200")
        self._label(dialog, self.t("select_image_format")).pack(pady=10)

        format_var = tk.StringVar(value="png")
        format_frame = ttk.Frame(dialog, style="White.TFrame")
        format_frame.pack(pady=10)
        for name in EXPORT_FORMATS:
            ttk.Radiobutton(format_frame, text=name.upper(), variable=format_var, value=name).pack(side='left', padx=10)

        def confirm() -> None:
            choice = format_var.get()
            dialog.destroy()
            on_confirm(choice)

        button_frame = tk.Frame(dialog, bg=self.Colors.WHITE)
        button_frame.pack(pady=20)
        ttk.Button(button_frame, text=self.t("confirm"), command=confirm).pack(side="left", padx=10)
        ttk.Button(button_frame, text=self.t("cancel"), command=dialog.destroy).pack(side="right", padx=10)
        dialog.bind('<Return>', lambda e: confirm())
        dialog.bind('<Escape>', lambda e: dialog.destroy())

    def _export(self, image_data: Union[bytes, Image.Image], default_filename: str, format_choice: str,
                on_export_callback: Optional[Callable[[str], None]]) -> None:
        extension, _, filetypes = EXPORT_FORMATS[format_choice]
        save_path = filedialog.asksaveasfilename(
            title=self.t("save_image"),
            defaultextension=extension,
            filetypes=filetypes,
            initialfile=f"{default_filename}{extension}",
        )
        if not save_path:
            return
        try:
            Path(save_path).write_bytes(convert_image(open_image(image_data), format_choice))
        except (OSError, ValueError) as e:
            logger.error(f"Failed to export image: {e}", exc_info=True)
            showerror_relative(self.root, self.t("error"), f"{self.t('export_failed')}: {e}")
            return
        showinfo_relative(self.root, self.t("success"), self.t("export_success").format(path=save_path))
        if on_export_callback:
            on_export_callback(save_path)


class ImageReplaceHelper(_DialogBase):
    """选择新图片并确认替换"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._photo_refs: List[ImageTk.PhotoImage] = []

    def show_replace_flow(self, original_image: ImageSource, on_confirm_callback: Callable[[Path], None],
                          is_valid_image_check: Optional[Callable[[Path], bool]] = None) -> None:
        """选择新图片 -> 新旧对比确认 -> on_confirm_callback(新图片路径)"""
        new_image_path = self.select_new_image()
        if not new_image_path:
            return
        is_valid_image = is_valid_image_check(new_image_path) if is_valid_image_check else True
        if self.show_replace_confirmation(original_image, new_image_path, is_valid_image):
            on_confirm_callback(new_image_path)

    def select_new_image(self) -> Optional[Path]:
        path = filedialog.askopenfilename(title=self.t("select_new_image"), filetypes=IMAGE_FILE_TYPES)
        return Path(path) if path else None

    def show_replace_confirmation(self, original_image: ImageSource, new_image_path: Path,
                                  is_valid_image: bool = True) -> bool:
        """显示新旧图片对比，等待用户确认；确认返回 True"""
        self._photo_refs.clear()
        popup = self._create_dialog(self.t("replace_warning"), "900x500")

        if not is_valid_image:
            self._label(popup, self.t("file_extension_warning", filename=new_image_path.name),
                        fg=self.Colors.TEXT_WARNING_PINK, wraplength=600, justify="left",
                        ).pack(pady=5, padx=10, anchor="w")
        self._label(popup, self.t("replace_confirm_text"), size=12).pack(pady=10)

        image_frame = tk.Frame(popup, bg=self.Colors.WHITE)
        image_frame.pack(pady=10)
        self._add_preview(image_frame, original_image)
        self._label(image_frame, "→", size=24).pack(side="left", padx=10)
        self._add_preview(image_frame, new_image_path)

        self._label(popup, self.t("replace_confirm_question")).pack(pady=10)

        confirmed = False

        def confirm() -> None:
            nonlocal confirmed
            confirmed = True
            popup.destroy()

        button_frame = tk.Frame(popup, bg=self.Colors.WHITE)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text=self.t("replace_yes"), command=confirm).pack(side="left", padx=10)
        ttk.Button(button_frame, text=self.t("replace_no"), command=popup.destroy).pack(side="right", padx=10)
        popup.bind('<Return>', lambda e: confirm())
        popup.bind('<Escape>', lambda e: popup.destroy())

        self.root.wait_window(popup)
        return confirmed

    def _add_preview(self, parent: tk.Frame, source: ImageSource) -> None:
        try:
            preview = open_image(source).resize(REPLACE_PREVIEW_SIZE, Image.Resampling.BILINEAR)
        except (OSError, ValueError) as e:
            logger.debug(f"Failed to display image preview: {e}")
            self._label(parent, self.t("preview_failed"), size=12, fg="red").pack(side="left", padx=10)
            return
        photo = ImageTk.PhotoImage(preview)
        self._photo_refs.append(photo)
        tk.Label(parent, image=photo, bg=self.Colors.WHITE).pack(side="left", padx=10)
