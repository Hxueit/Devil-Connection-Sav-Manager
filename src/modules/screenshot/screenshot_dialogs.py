"""截图的新增 / 替换 / 导出对话框"""

import logging
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Callable, List

import tkinter as tk
from tkinter import filedialog, ttk
from PIL import Image

from src.modules.common.image_operations import (
    EXPORT_FORMATS, ImageExportHelper, ImageReplaceHelper, apply_modal_grab_safely,
    convert_image,
)
from src.modules.screenshot.screenshot_manager import (
    ScreenshotManager, current_datetime, generate_id, is_valid_date, read_image_file,
)
from src.utils.images import IMAGE_FILE_TYPES, is_image_file
from src.utils.background import run_in_background
from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import askyesno_relative, set_window_icon, showerror_relative, showinfo_relative

logger = logging.getLogger(__name__)

ASPECT_RATIO_TOLERANCE = 30  # 高度与 4:3 的偏差在这么多像素内都算 4:3


def is_4_3(path: Path) -> bool:
    try:
        with Image.open(path) as img:
            width, height = img.size
    except OSError:
        return False
    return abs(height - width * 3 / 4) <= ASPECT_RATIO_TOLERANCE


def _create_dialog(root: tk.Misc, title: str, width: int, height: int) -> tk.Toplevel:
    dialog = tk.Toplevel(root)
    dialog.title(title)
    dialog.geometry(f"{width}x{height}")
    dialog.configure(bg=Colors.WHITE)
    set_window_icon(dialog)
    dialog.transient(root)
    apply_modal_grab_safely(dialog)
    return dialog


def _label(parent: tk.Misc, text: str, size: int = 10, **kwargs) -> tk.Label:
    options = dict(font=get_cjk_font(size), fg=Colors.TEXT_PRIMARY, bg=Colors.WHITE)
    options.update(kwargs)
    return tk.Label(parent, text=text, **options)


def show_add_dialog(root: tk.Misc, manager: ScreenshotManager, t: Callable[..., str],
                    on_added: Callable[[str], None]) -> None:
    """选择图片，填写 ID 和时间后新增截图；成功后调用 on_added(截图ID)"""
    path_str = filedialog.askopenfilename(title=t("select_new_image"), filetypes=IMAGE_FILE_TYPES)
    if not path_str:
        return
    image_path = Path(path_str)
    if not image_path.exists():
        showerror_relative(root, t("error"), t("file_not_exist"))
        return

    is_image = is_image_file(image_path)
    ratio_ok = is_image and is_4_3(image_path)
    height = 300 + (80 if not is_image or not ratio_ok else 0)
    dialog = _create_dialog(root, t("add_new_title"), 400, height)

    if not is_image:
        _label(dialog, t("file_extension_warning", filename=image_path.name), fg=Colors.TEXT_WARNING_PINK,
               wraplength=380, justify="left").pack(pady=5, padx=10, anchor="w")
    elif not ratio_ok:
        _label(dialog, t("aspect_ratio_warning"), fg=Colors.TEXT_WARNING_AQUA,
               wraplength=380, justify="left").pack(pady=5, padx=10, anchor="w")

    entries = []
    for label_key in ("id_label", "date_label"):
        frame = ttk.Frame(dialog, style="White.TFrame")
        frame.pack(pady=10, padx=20, fill='x')
        _label(frame, t(label_key)).pack(anchor='w')
        entry = tk.Entry(frame, width=40)
        entry.pack(fill='x', pady=(5, 0))
        entries.append(entry)
    id_entry, date_entry = entries

    def confirm() -> None:
        screenshot_id = id_entry.get().strip() or generate_id()
        date_string = date_entry.get().strip() or current_datetime()
        if screenshot_id in manager.sav_pairs:
            showerror_relative(root, t("error"), t("id_exists"))
            return
        if not is_valid_date(date_string):
            showerror_relative(root, t("error"), t("invalid_date_format"))
            return
        if not is_image and not askyesno_relative(
                root, t("warning"), t("file_extension_warning").format(filename=image_path.name)):
            dialog.destroy()
            return

        success, message = manager.add_screenshot(screenshot_id, date_string, str(image_path))
        dialog.destroy()
        if success:
            showinfo_relative(root, t("success"), t("add_success").format(id=screenshot_id))
            on_added(screenshot_id)
        else:
            showerror_relative(root, t("error"), message)

    button_frame = ttk.Frame(dialog, style="White.TFrame")
    button_frame.pack(pady=10)
    ttk.Button(button_frame, text=t("confirm"), command=confirm).pack(side='left', padx=5)
    ttk.Button(button_frame, text=t("delete_cancel"), command=dialog.destroy).pack(side='left', padx=5)
    id_entry.focus()


def show_replace_dialog(root: tk.Misc, manager: ScreenshotManager, t: Callable[..., str],
                        screenshot_id: str, on_replaced: Callable[[str], None]) -> None:
    """选择新图片替换截图；成功后调用 on_replaced(截图ID)"""
    main_path = manager.file_path(screenshot_id)
    thumb_path = manager.file_path(screenshot_id, thumb=True)
    if not main_path or not thumb_path:
        showerror_relative(root, t("error"), t("file_missing"))
        return
    if not main_path.exists() or not thumb_path.exists():
        showerror_relative(root, t("error"), t("file_not_exist"))
        return
    original = manager.get_image_data(screenshot_id)
    if original is None:
        showerror_relative(root, t("error"), t("file_not_found"))
        return

    def on_confirm(new_image_path: Path) -> None:
        success, message = manager.replace_screenshot(screenshot_id, str(new_image_path))
        if success:
            showinfo_relative(root, t("success"), t("replace_success").format(id=screenshot_id))
            on_replaced(screenshot_id)
        else:
            showerror_relative(root, t("error"), message)

    helper = ImageReplaceHelper(root, t, get_cjk_font, Colors, set_window_icon)
    helper.show_replace_flow(original, on_confirm, is_image_file)


def export_screenshot(root: tk.Misc, manager: ScreenshotManager, t: Callable[..., str], screenshot_id: str) -> None:
    image_data = manager.get_image_data(screenshot_id)
    if not image_data:
        showerror_relative(root, t("error"), t("file_not_found"))
        return
    ImageExportHelper(root, t, get_cjk_font, Colors, set_window_icon).show_format_dialog(image_data, screenshot_id)


def batch_export(root: tk.Misc, manager: ScreenshotManager, t: Callable[..., str], screenshot_ids: List[str]) -> None:
    """选择格式后把多张截图导出到一个 ZIP 文件（后台线程执行，显示进度）"""
    helper = ImageExportHelper(root, t, get_cjk_font, Colors, set_window_icon)
    helper.ask_format(lambda format_choice: _batch_export_to_zip(root, manager, t, screenshot_ids, format_choice))


def _batch_export_to_zip(root: tk.Misc, manager: ScreenshotManager, t: Callable[..., str],
                         screenshot_ids: List[str], format_choice: str) -> None:
    save_path = filedialog.asksaveasfilename(
        title=t("save_zip"),
        defaultextension=".zip",
        filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
        initialfile="DevilConnectionSSPack.zip",
    )
    if not save_path:
        return

    total = len(screenshot_ids)
    # 后台线程需要的文件路径先在主线程取好
    paths = [(screenshot_id, manager.file_path(screenshot_id)) for screenshot_id in screenshot_ids]
    extension = EXPORT_FORMATS[format_choice][0]

    window = _create_dialog(root, t("batch_export_progress"), 450, 200)
    window.protocol("WM_DELETE_WINDOW", lambda: None)  # 导出完成前不允许关闭
    title_label = _label(window, t("exporting_images"))
    title_label.pack(pady=10)
    progress_bar = ttk.Progressbar(window, length=350, mode='determinate', maximum=total, value=0)
    progress_bar.pack(pady=10, padx=20, fill="x")
    status_label = _label(window, f"0/{total}", size=9)
    status_label.pack(pady=5)

    progress = {"done": 0, "finished": False}  # 后台线程只更新计数，界面由主线程定时读取

    def work() -> int:
        exported = 0
        with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for screenshot_id, path in paths:
                data = read_image_file(path) if path else None
                try:
                    if data is None:
                        raise ValueError("image not readable")
                    with Image.open(BytesIO(data)) as img:
                        zip_file.writestr(f"{screenshot_id}{extension}", convert_image(img, format_choice))
                    exported += 1
                except (OSError, ValueError) as e:
                    logger.debug(f"Failed to export {screenshot_id}: {e}")
                progress["done"] += 1
        return exported

    def update_progress() -> None:
        if progress["finished"] or not window.winfo_exists():
            return
        progress_bar['value'] = progress["done"]
        status_label.config(text=f"{progress['done']}/{total}")
        window.after(100, update_progress)

    def done(exported: int, error: BaseException) -> None:
        progress["finished"] = True
        progress_bar.pack_forget()
        status_label.pack_forget()
        if error:
            title_label.config(text=f"{t('export_failed')}: {error}", fg="red")
        elif exported == 0:
            title_label.config(text=t("batch_export_error_all"), fg="red")
        else:
            title_label.config(text="")
            message = t("batch_export_success", count=exported)
            if exported < total:
                message += "\n" + t("batch_export_failed", count=total - exported)
            _label(window, message, fg="green").pack(pady=20)
        ttk.Button(window, text=t("close"), command=window.destroy).pack(pady=10)
        window.protocol("WM_DELETE_WINDOW", window.destroy)

    update_progress()
    run_in_background(window, work, done)

