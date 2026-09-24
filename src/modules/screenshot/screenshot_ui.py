"""截图管理标签页

左边是选中截图的预览，右边是截图列表（与游戏画廊顺序一致，每 12 张一页，
每页分左右两个半页）。勾选「开启修改」后才能新增/替换/删除/排序/拖拽。
"""

import logging
from io import BytesIO
from typing import Callable, Dict, List, Optional, Set

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

from src.modules.common.draggable_list import TreeDragReorder
from src.modules.screenshot import screenshot_dialogs as dialogs
from src.modules.screenshot.gallery_preview import GalleryPreview
from src.modules.screenshot.screenshot_manager import ScreenshotManager, read_image_file
from src.utils.hint_animation import HintAnimation
from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import askyesno_relative, showerror_relative, showinfo_relative, showwarning_relative

logger = logging.getLogger(__name__)

# 「开启修改」复选框的 ttk 样式名
CHECKBOX_STYLE_NORMAL = "Screenshot.TCheckbutton"
CHECKBOX_STYLE_HINT = "ScreenshotHint.TCheckbutton"

PREVIEW_SIZE = (240, 180)
PER_PAGE = 12
PER_HALF_PAGE = 6
CHECKED, UNCHECKED = "☑", "☐"
MARK_DURATION_MS = 15000
# 列表行前的临时标记：(前缀, 文字颜色)
MARKS = {
    "new": ("⚝ ", "#FED491"),       # 刚新增
    "replaced": ("✧ ", "#BDC9B2"),  # 刚替换
    "up": ("↑↑↑ ", "#D06CAA"),      # 拖拽后上移了
    "down": ("↓↓↓ ", "#85A9A5"),    # 拖拽后下移了
}


class ScreenshotManagerUI:
    """截图管理标签页"""

    def __init__(self, parent_frame: tk.Frame, root: tk.Tk, storage_dir: Optional[str],
                 t_func: Callable[..., str]) -> None:
        self.parent_frame = parent_frame
        self.root = root
        self.storage_dir = storage_dir
        self.t = t_func
        self.manager = ScreenshotManager(t_func=t_func)
        self.gallery = GalleryPreview(root, self.manager, t_func)
        self.edit_enabled = False

        self.checked: Set[str] = set()            # 勾选的截图ID
        self._id_by_item: Dict[str, str] = {}     # Treeview 行 -> 截图ID（页眉行不在里面）
        self._item_by_id: Dict[str, str] = {}
        self._row_text: Dict[str, str] = {}       # 截图ID -> 不带标记的行文字
        self._mark_timers: Dict[str, str] = {}    # 截图ID -> 清除标记的 after id
        self._preview_photo: Optional[ImageTk.PhotoImage] = None

        self._build_ui()
        self.tree.bind('<<TreeviewSelect>>', self._on_tree_select)
        # 必须在 TreeDragReorder 之前绑定：点复选框时返回 "break"，不会开始拖拽
        self.tree.bind('<Button-1>', self._on_tree_click)
        TreeDragReorder(self.tree, lambda item: item in self._id_by_item, self._on_drop,
                        can_drag=lambda: self.edit_enabled)
        self._hint = HintAnimation(root, self.enable_edit_checkbox, CHECKBOX_STYLE_NORMAL, CHECKBOX_STYLE_HINT)
        self._set_edit_mode(False)

        if storage_dir:
            self.manager.set_storage_dir(storage_dir)
            self.load_screenshots(silent=True)

    # ---------- 界面搭建 ----------

    def _build_ui(self) -> None:
        bg = Colors.LIGHT_GRAY
        self.hint_label = tk.Label(self.parent_frame, text=self.t("select_dir_hint"), fg=Colors.TEXT_HIGHLIGHT,
                                   font=get_cjk_font(10), bg=bg)
        if not self.storage_dir:
            self.hint_label.pack(pady=15)

        # 标题行：标题居中，按钮靠右
        header = tk.Frame(self.parent_frame, bg=bg)
        header.pack(pady=8, fill="x")
        header.columnconfigure(0, weight=1)
        header.columnconfigure(2, weight=1)
        tk.Frame(header, bg=bg).grid(row=0, column=0, sticky="ew")
        title_frame = tk.Frame(header, bg=bg)
        title_frame.grid(row=0, column=1)
        self.list_label = tk.Label(title_frame, text=self.t("screenshot_list"), font=get_cjk_font(10),
                                   fg=Colors.TEXT_PRIMARY, bg=bg)
        self.list_label.pack(side="left", padx=5)
        right_area = tk.Frame(header, bg=bg)
        right_area.grid(row=0, column=2, sticky="ew")
        right_area.columnconfigure(0, weight=1)
        tk.Frame(right_area, bg=bg).grid(row=0, column=0, sticky="ew")
        buttons = tk.Frame(right_area, bg=bg)
        buttons.grid(row=0, column=1, sticky="e")

        ttk.Button(buttons, text=self.t("refresh"), command=self.load_screenshots, width=3).pack(side="left", padx=2)
        self.sort_asc_button = ttk.Button(buttons, text=self.t("sort_asc"), command=lambda: self._sort(True))
        self.sort_asc_button.pack(side="left", padx=2)
        self.sort_desc_button = ttk.Button(buttons, text=self.t("sort_desc"), command=lambda: self._sort(False))
        self.sort_desc_button.pack(side="left", padx=2)

        # 复选框外面包一层 Frame，HintAnimation 通过改变它的 padx 做抖动
        ttk.Style(self.root).configure(CHECKBOX_STYLE_NORMAL, background=bg)
        wrapper = tk.Frame(buttons, bg=bg)
        wrapper.pack(side="left", padx=5)
        self.edit_var = tk.BooleanVar(value=False)
        self.enable_edit_checkbox = ttk.Checkbutton(
            wrapper, text=self.t("enable_edit"), variable=self.edit_var, style=CHECKBOX_STYLE_NORMAL,
            command=lambda: self._set_edit_mode(self.edit_var.get()))
        self.enable_edit_checkbox.pack()
        self.enable_edit_checkbox.wrapper = wrapper
        self.enable_edit_checkbox._original_pack_info = {'padx': 5}

        # 列表区域：左边预览，右边列表
        list_frame = tk.Frame(self.parent_frame, bg=bg)
        list_frame.pack(fill="both", expand=True, pady=8)
        self.preview_frame = tk.Frame(list_frame, bg=bg)
        self.preview_frame.pack(side="left", padx=5)
        self.preview_label_text = tk.Label(self.preview_frame, text=self.t("preview"), font=get_cjk_font(10), bg=bg)
        self.preview_label_text.pack()
        preview_box = tk.Frame(self.preview_frame, width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1],
                               bg=Colors.PREVIEW_BG, relief="sunken")
        preview_box.pack()
        preview_box.pack_propagate(False)
        self.preview_label = tk.Label(preview_box, bg=Colors.PREVIEW_BG)
        self.preview_label.pack(fill="both", expand=True)
        # 导出按钮只在有选中项时显示
        self.export_button = ttk.Button(self.preview_frame, text=self.t("export_image"), command=self.export_image)
        self.batch_export_button = ttk.Button(self.preview_frame, text=self.t("batch_export"),
                                              command=self.batch_export_images)

        list_right = tk.Frame(list_frame)
        list_right.pack(side="right", fill="both", expand=True)
        tree_frame = tk.Frame(list_right)
        tree_frame.pack(side="left", fill="both", expand=True)
        scrollbar = tk.Scrollbar(tree_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        ttk.Style(self.root).configure("Screenshot.Treeview", rowheight=26, padding=(0, 6))
        self.tree = ttk.Treeview(tree_frame, columns=("select", "info"), show="headings", height=20,
                                 style="Screenshot.Treeview", yscrollcommand=scrollbar.set)
        self.tree.heading("select", text=UNCHECKED, anchor="center", command=self._toggle_select_all)
        self.tree.column("select", width=40, stretch=False, anchor="center")
        self.tree.heading("info", text=self.t("list_header"), anchor="w")
        self.tree.column("info", width=800, stretch=True)
        self.tree.tag_configure("PageHeaderLeft", foreground="#D26FAB", font=get_cjk_font(10, "bold"))
        self.tree.tag_configure("PageHeaderRight", foreground="#85A9A5", font=get_cjk_font(10, "bold"))
        for kind, (_, color) in MARKS.items():
            self.tree.tag_configure(f"mark_{kind}", foreground=color)
        scrollbar.config(command=self.tree.yview)
        self.tree.pack(side="left", fill="both", expand=True)

        # 操作按钮
        button_frame = ttk.Frame(self.parent_frame)
        button_frame.pack(pady=5)
        self.add_button = ttk.Button(button_frame, text=self.t("add_new"), command=self.add_new)
        self.replace_button = ttk.Button(button_frame, text=self.t("replace_selected"), command=self.replace_selected)
        self.delete_button = ttk.Button(button_frame, text=self.t("delete_selected"), command=self.delete_selected)
        self.gallery_preview_button = ttk.Button(button_frame, text=self.t("gallery_preview"), command=self.gallery.show)
        for button in (self.add_button, self.replace_button, self.delete_button, self.gallery_preview_button):
            button.pack(side='left', padx=5)

        self._edit_buttons = (self.add_button, self.replace_button, self.delete_button,
                              self.sort_asc_button, self.sort_desc_button)
        for button in self._edit_buttons:
            button.bind('<Button-1>', self._on_edit_button_click, add='+')

    def update_ui_texts(self) -> None:
        self.hint_label.config(text=self.t("select_dir_hint"))
        self.list_label.config(text=self.t("screenshot_list"))
        self.preview_label_text.config(text=self.t("preview"))
        self.tree.heading("info", text=self.t("list_header"))
        self.sort_asc_button.config(text=self.t("sort_asc"))
        self.sort_desc_button.config(text=self.t("sort_desc"))
        self.add_button.config(text=self.t("add_new"))
        self.replace_button.config(text=self.t("replace_selected"))
        self.delete_button.config(text=self.t("delete_selected"))
        self.gallery_preview_button.config(text=self.t("gallery_preview"))
        self.export_button.config(text=self.t("export_image"))
        self.batch_export_button.config(text=self.t("batch_export"))
        self.enable_edit_checkbox.config(text=self.t("enable_edit"))

    # ---------- 编辑模式 ----------

    def _set_edit_mode(self, enabled: bool) -> None:
        self.edit_enabled = enabled
        self.edit_var.set(enabled)
        for button in self._edit_buttons:
            button.config(state="normal" if enabled else "disabled")

    def _on_edit_button_click(self, event: tk.Event) -> Optional[str]:
        """点了被禁用的修改按钮时，让「开启修改」复选框闪一下提示用户"""
        if event.widget.instate(['disabled']):
            self._hint.trigger()
            return "break"
        return None

    # ---------- 列表 ----------

    def set_storage_dir(self, storage_dir: Optional[str]) -> None:
        self.storage_dir = storage_dir
        self.checked.clear()
        if storage_dir:
            self.manager.set_storage_dir(storage_dir)
            self.hint_label.pack_forget()
        else:
            self.hint_label.pack(pady=10)

    def load_screenshots(self, silent: bool = False) -> None:
        """重新读取截图并刷新列表和画廊（silent 时出错不弹窗）"""
        if not self.storage_dir:
            return
        self.manager.set_storage_dir(self.storage_dir)
        if not self.manager.load_screenshots():
            if not silent:
                showerror_relative(self.root, self.t("error"), self.t("missing_files"))
            return
        self.hint_label.pack_forget()
        self._render_list()
        self._on_checked_changed()
        self.gallery.refresh()

    def _render_list(self) -> None:
        for timer in self._mark_timers.values():
            self.root.after_cancel(timer)
        self._mark_timers.clear()
        self.tree.delete(*self.tree.get_children())
        self._id_by_item.clear()
        self._item_by_id.clear()
        self._row_text.clear()

        existing_ids = set()
        for n, item in enumerate(self.manager.ids_data):
            page = n // PER_PAGE + 1
            if n % PER_PAGE == 0:
                self.tree.insert("", tk.END, values=("", f"{self.t('page')} {page} ←"), tags=("PageHeaderLeft",))

            screenshot_id = item.get('id', '')
            main_file = self.manager.sav_pairs.get(screenshot_id, [None, None])[0] or self.t("missing_main_file")
            text = f"{screenshot_id} - {main_file} - {item.get('date', '')}"
            row = self.tree.insert("", tk.END, values=(CHECKED if screenshot_id in self.checked else UNCHECKED, text))
            self._id_by_item[row] = screenshot_id
            self._item_by_id[screenshot_id] = row
            self._row_text[screenshot_id] = text
            existing_ids.add(screenshot_id)

            if n % PER_PAGE == PER_HALF_PAGE - 1:
                self.tree.insert("", tk.END, values=("", f"{self.t('page')} {page} →"), tags=("PageHeaderRight",))
        # 重新加载后保留仍然存在的截图的勾选状态
        self.checked &= existing_ids

    def _mark_row(self, screenshot_id: str, kind: str) -> None:
        """在行前显示一个临时标记（15 秒后消失）"""
        row = self._item_by_id.get(screenshot_id)
        if not row:
            return
        self.tree.set(row, "info", MARKS[kind][0] + self._row_text[screenshot_id])
        self.tree.item(row, tags=(f"mark_{kind}",))
        old_timer = self._mark_timers.pop(screenshot_id, None)
        if old_timer:
            self.root.after_cancel(old_timer)
        self._mark_timers[screenshot_id] = self.root.after(MARK_DURATION_MS, lambda: self._unmark_row(screenshot_id))

    def _unmark_row(self, screenshot_id: str) -> None:
        self._mark_timers.pop(screenshot_id, None)
        row = self._item_by_id.get(screenshot_id)
        if row and self.tree.exists(row):
            self.tree.set(row, "info", self._row_text[screenshot_id])
            self.tree.item(row, tags=())

    def _on_tree_click(self, event: tk.Event) -> Optional[str]:
        """点击复选框列时切换勾选"""
        if self.tree.identify_region(event.x, event.y) != "cell" or self.tree.identify_column(event.x) != "#1":
            return None
        screenshot_id = self._id_by_item.get(self.tree.identify_row(event.y))
        if screenshot_id is None:
            return None
        self.checked.symmetric_difference_update({screenshot_id})
        self.tree.set(self._item_by_id[screenshot_id], "select",
                      CHECKED if screenshot_id in self.checked else UNCHECKED)
        self._on_checked_changed()
        return "break"

    def _toggle_select_all(self) -> None:
        if not self._id_by_item:
            return
        select_all = len(self.checked) < len(self._id_by_item)
        self.checked = set(self._item_by_id) if select_all else set()
        mark = CHECKED if select_all else UNCHECKED
        for row in self._id_by_item:
            self.tree.set(row, "select", mark)
        self._on_checked_changed()

    def _on_checked_changed(self) -> None:
        all_checked = bool(self._id_by_item) and len(self.checked) == len(self._id_by_item)
        self.tree.heading("select", text=CHECKED if all_checked else UNCHECKED)
        if self.checked and self.storage_dir:
            self.batch_export_button.pack(pady=5)
        else:
            self.batch_export_button.pack_forget()

    def _checked_ids(self) -> List[str]:
        """勾选的截图ID，按列表顺序"""
        return [item['id'] for item in self.manager.ids_data if item.get('id') in self.checked]

    def _selected_id(self) -> Optional[str]:
        """当前选中（高亮）行的截图ID；没选中时提示并返回 None"""
        selection = self.tree.selection()
        if not selection:
            showwarning_relative(self.root, self.t("warning"), self.t("select_screenshot"))
            return None
        screenshot_id = self._id_by_item.get(selection[0])
        if screenshot_id is None:
            showerror_relative(self.root, self.t("error"), self.t("invalid_selection"))
        return screenshot_id

    def _on_drop(self, from_index: int, to_index: int) -> None:
        """拖拽排序：保存新顺序，并用箭头标出移动的截图和被挤开的截图"""
        moved_id = self.manager.ids_data[from_index]['id']
        try:
            self.manager.move_item(from_index, to_index)
        except OSError as e:
            showerror_relative(self.root, self.t("error"), self.t("save_failed", error=str(e)))
            return
        self.load_screenshots()
        moving_down = to_index > from_index
        row = self._item_by_id.get(moved_id)
        if row:
            self.tree.selection_set(row)
            self.tree.see(row)
        self._mark_row(moved_id, "down" if moving_down else "up")
        self._mark_row(self.manager.ids_data[from_index]['id'], "up" if moving_down else "down")

    # ---------- 预览 ----------

    def _on_tree_select(self, event: tk.Event) -> None:
        selection = self.tree.selection()
        if not selection:
            self._set_preview(None)
            self.export_button.pack_forget()
            return
        screenshot_id = self._id_by_item.get(selection[0])
        if screenshot_id is None:  # 页眉行不能选中
            self.tree.selection_remove(selection[0])
            return
        self._show_preview(screenshot_id)
        self.export_button.pack(pady=5)

    def _set_preview(self, photo: Optional[ImageTk.PhotoImage], error_text: str = "") -> None:
        self._preview_photo = photo
        self.preview_label.config(image=photo or '', text=error_text, bg=Colors.WHITE if photo else "lightgray")

    def _show_preview(self, screenshot_id: str) -> None:
        path = self.manager.file_path(screenshot_id)
        if path is None:
            self._set_preview(None, self.t("file_missing_text"))
            return
        if not path.exists():
            self._set_preview(None, self.t("file_not_exist_text"))
            return
        data = read_image_file(path)
        try:
            if data is None:
                raise ValueError("image not readable")
            with Image.open(BytesIO(data)) as img:
                photo = ImageTk.PhotoImage(img.resize(PREVIEW_SIZE, Image.Resampling.LANCZOS))
        except (OSError, ValueError) as e:
            logger.debug(f"Failed to preview {screenshot_id}: {e}")
            self._set_preview(None, self.t("preview_failed"))
            return
        self._set_preview(photo)

    # ---------- 按钮操作 ----------

    def _sort(self, ascending: bool) -> None:
        if not self.storage_dir:
            showerror_relative(self.root, self.t("error"), self.t("select_dir_hint"))
            return
        if not askyesno_relative(self.root, self.t("confirm_sort"), self.t("sort_warning"), icon='warning'):
            return
        try:
            self.manager.sort_by_date(ascending=ascending)
        except (OSError, ValueError, KeyError) as e:
            logger.error(f"Failed to sort screenshots: {e}", exc_info=True)
            showerror_relative(self.root, self.t("error"), self.t("save_failed", error=str(e)))
            return
        self.load_screenshots()
        showinfo_relative(self.root, self.t("success"), self.t("sort_asc_success" if ascending else "sort_desc_success"))

    def add_new(self) -> None:
        def on_added(screenshot_id: str) -> None:
            self.load_screenshots()
            self._mark_row(screenshot_id, "new")

        dialogs.show_add_dialog(self.root, self.manager, self.t, on_added)

    def replace_selected(self) -> None:
        screenshot_id = self._selected_id()
        if screenshot_id is None:
            return

        def on_replaced(screenshot_id: str) -> None:
            self.load_screenshots()
            self._mark_row(screenshot_id, "replaced")

        dialogs.show_replace_dialog(self.root, self.manager, self.t, screenshot_id, on_replaced)

    def delete_selected(self) -> None:
        selected_ids = self._checked_ids()
        if not selected_ids:
            showwarning_relative(self.root, self.t("warning"), self.t("delete_select_error"))
            return
        if len(selected_ids) == 1:
            message = self.t("delete_confirm_single").format(id=selected_ids[0])
        else:
            message = self.t("delete_confirm_multiple").format(count=len(selected_ids), ids=", ".join(selected_ids))
        if not askyesno_relative(self.root, self.t("delete_confirm"), message):
            return

        try:
            failed_files = self.manager.delete_screenshots(selected_ids)
        except OSError as e:
            logger.error(f"Failed to delete screenshots: {e}", exc_info=True)
            showerror_relative(self.root, self.t("error"), self.t("save_failed", error=str(e)))
            return
        self.load_screenshots()
        if failed_files:
            showwarning_relative(self.root, self.t("warning"),
                                 self.t("file_operation_failed", error=", ".join(failed_files)))
        else:
            showinfo_relative(self.root, self.t("success"), self.t("delete_success").format(count=len(selected_ids)))

    def export_image(self) -> None:
        screenshot_id = self._selected_id()
        if screenshot_id is not None:
            dialogs.export_screenshot(self.root, self.manager, self.t, screenshot_id)

    def batch_export_images(self) -> None:
        selected_ids = self._checked_ids()
        if not selected_ids:
            showwarning_relative(self.root, self.t("warning"), self.t("select_screenshot"))
            return
        dialogs.batch_export(self.root, self.manager, self.t, selected_ids)
