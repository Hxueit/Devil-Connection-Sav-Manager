"""备份/还原标签页

创建备份、显示备份列表，以及还原、删除、重命名备份。
耗时的估算、打包和还原都在后台线程执行，期间禁用按钮，避免重复点击。
"""
import logging
import re
import tkinter as tk
from pathlib import Path
from tkinter import Entry, Scrollbar, Toplevel, ttk
from typing import Callable, Optional

from src.modules.backup import backups
from src.utils.background import run_in_background
from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import set_window_icon, showerror_relative, showinfo_relative

logger = logging.getLogger(__name__)

PROGRESS_POLL_MS = 100
INVALID_FILENAME_CHARS = '<>:"/\\|?*'


class BackupRestoreTab:
    """备份还原标签页

    on_restore_start / on_restore_done(success) 让主窗口在还原期间暂停存档监控，
    并在还原后刷新其他标签页。
    """

    def __init__(
        self,
        parent: tk.Widget,
        root: tk.Tk,
        storage_dir: str,
        t: Callable[..., str],
        on_restore_start: Optional[Callable[[], None]] = None,
        on_restore_done: Optional[Callable[[bool], None]] = None,
    ) -> None:
        self.root = root
        self.storage_dir = Path(storage_dir)
        self.t = t
        self.on_restore_start = on_restore_start
        self.on_restore_done = on_restore_done

        self.selected_backup_path: Optional[Path] = None
        self._busy = False
        self._progress = (0, 1)  # 后台线程写入 (current, total)，主线程定时读取

        # 所有控件都放在自己的容器里，销毁时不影响父容器中的其他控件
        self.frame = tk.Frame(parent, bg=Colors.LIGHT_GRAY)
        self.frame.pack(fill="both", expand=True)
        self._create_backup_section()
        self._create_restore_section()
        self.refresh_backup_list()

    # ---------- 界面 ----------

    def _create_backup_section(self) -> None:
        backup_frame = tk.Frame(self.frame, bg=Colors.LIGHT_GRAY)
        backup_frame.pack(pady=15, fill="x")

        self.backup_button = ttk.Button(backup_frame, text=self.t("backup_button"), command=self.create_backup)
        self.backup_button.pack(pady=15)

        # 用 Text 而不是 Label，是为了支持 **加粗** 的部分文本
        self.hint_text = tk.Text(
            backup_frame, height=1, width=1, wrap=tk.WORD,
            bg=Colors.LIGHT_GRAY, fg=Colors.TEXT_PRIMARY, font=get_cjk_font(10),
            relief=tk.FLAT, borderwidth=0, padx=10, pady=5, cursor="arrow",
        )
        self.hint_text.tag_configure("bold", font=get_cjk_font(10, "bold"))
        self.hint_text.tag_configure("center", justify="center")
        self.hint_text.pack(pady=(0, 10), fill="x")
        self.hint_text.bind("<Configure>", lambda e: self._fit_hint_height())
        self._update_hint_text()

        self.backup_progress = ttk.Progressbar(backup_frame, mode="determinate", length=300)
        self.backup_progress_label = tk.Label(backup_frame, text="", bg=Colors.LIGHT_GRAY, fg=Colors.TEXT_MUTED)

    def _update_hint_text(self) -> None:
        """显示备份位置提示，** 之间的文字加粗"""
        self.hint_text.config(state=tk.NORMAL)
        self.hint_text.delete("1.0", tk.END)
        for part in re.split(r"(\*\*.*?\*\*)", self.t("backup_location_hint")):
            if part.startswith("**") and part.endswith("**"):
                self.hint_text.insert(tk.END, part[2:-2], ("bold", "center"))
            else:
                self.hint_text.insert(tk.END, part, "center")
        self.hint_text.config(state=tk.DISABLED)
        self._fit_hint_height()

    def _fit_hint_height(self) -> None:
        """让 Text 的高度等于自动换行后的实际行数"""
        lines = self.hint_text.count("1.0", "end", "displaylines")
        if lines:
            self.hint_text.config(height=max(1, lines[0] if isinstance(lines, tuple) else lines))

    def _create_restore_section(self) -> None:
        restore_frame = tk.Frame(self.frame, bg=Colors.LIGHT_GRAY)
        restore_frame.pack(fill="both", expand=True, padx=10, pady=5)

        header = tk.Frame(restore_frame, bg=Colors.LIGHT_GRAY)
        header.pack(fill="x", pady=4)
        self.backup_list_title = tk.Label(
            header, text=self.t("backup_list_title"), font=get_cjk_font(12, "bold"),
            fg=Colors.TEXT_PRIMARY, bg=Colors.LIGHT_GRAY,
        )
        self.backup_list_title.pack(side="left", padx=5)
        self.refresh_button = ttk.Button(header, text=self.t("refresh"), command=self.refresh_backup_list)
        self.refresh_button.pack(side="right", padx=5)

        list_container = tk.Frame(restore_frame, bg=Colors.LIGHT_GRAY)
        list_container.pack(fill="both", expand=True)
        scrollbar = Scrollbar(list_container, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        ttk.Style(self.root).configure("Backup.Treeview", rowheight=26, padding=(0, 6))
        self.backup_tree = ttk.Treeview(
            list_container, columns=("timestamp", "filename", "size", "status"), show="headings",
            height=18, yscrollcommand=scrollbar.set, style="Backup.Treeview",
        )
        for column, width in (("timestamp", 180), ("filename", 250), ("size", 100), ("status", 150)):
            self.backup_tree.column(column, width=width)
        self._update_tree_headings()
        scrollbar.config(command=self.backup_tree.yview)
        self.backup_tree.pack(side="left", fill="both", expand=True)
        self.backup_tree.bind("<<TreeviewSelect>>", self.on_backup_select)

        # 选中备份后才显示的操作按钮
        button_area = tk.Frame(restore_frame, bg=Colors.LIGHT_GRAY)
        button_area.pack(pady=10)
        self.restore_button = ttk.Button(button_area, text=self.t("restore_button"), command=self.restore_backup)
        self.delete_button = ttk.Button(button_area, text=self.t("delete_backup_button"), command=self.delete_backup)
        self.rename_button = ttk.Button(button_area, text=self.t("rename_backup_button"), command=self.rename_backup)
        self.action_buttons = (self.restore_button, self.delete_button, self.rename_button)

    def _update_tree_headings(self) -> None:
        self.backup_tree.heading("timestamp", text=self.t("backup_timestamp"))
        self.backup_tree.heading("filename", text=self.t("backup_filename"))
        self.backup_tree.heading("size", text=self.t("backup_size"))
        self.backup_tree.heading("status", text=self.t("backup_status"))

    def _show_action_buttons(self, visible: bool) -> None:
        for button in self.action_buttons:
            if visible:
                button.pack(side="left", padx=5)
            else:
                button.pack_forget()

    def _set_busy(self, busy: bool) -> None:
        """后台任务运行期间禁用所有按钮"""
        self._busy = busy
        state = "disabled" if busy else "!disabled"
        for button in (self.backup_button, self.refresh_button) + self.action_buttons:
            button.state([state])

    def _ask_yesno(self, title: str, message: str) -> bool:
        """确认对话框（按钮文字使用当前语言）"""
        popup = self._make_popup(title, "400x250")
        tk.Label(
            popup, text=message, wraplength=350, justify="left", font=get_cjk_font(10),
            fg=Colors.TEXT_PRIMARY, bg=Colors.WHITE,
        ).pack(pady=20, padx=20)
        confirmed = self._add_dialog_buttons(popup)
        self.root.wait_window(popup)
        return confirmed()

    def _make_popup(self, title: str, geometry: str) -> Toplevel:
        popup = Toplevel(self.root)
        popup.title(title)
        popup.geometry(geometry)
        popup.configure(bg=Colors.WHITE)
        popup.transient(self.root)
        popup.grab_set()
        set_window_icon(popup)
        return popup

    def _add_dialog_buttons(self, popup: Toplevel, on_yes: Optional[Callable[[], None]] = None):
        """添加 是/否 按钮（回车/Esc 同效），返回一个查询是否点了「是」的函数"""
        result = {"yes": False}

        def yes():
            if on_yes:
                on_yes()
            result["yes"] = True
            popup.destroy()

        button_frame = tk.Frame(popup, bg=Colors.WHITE)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text=self.t("yes_button"), command=yes).pack(side="left", padx=10)
        ttk.Button(button_frame, text=self.t("no_button"), command=popup.destroy).pack(side="right", padx=10)
        popup.bind("<Return>", lambda e: yes())
        popup.bind("<Escape>", lambda e: popup.destroy())
        return lambda: result["yes"]

    def _show_error(self, key: str, error: Optional[BaseException] = None) -> None:
        message = self.t(key)
        if error is not None:
            message += f"\n\n{error}"
        showerror_relative(self.root, self.t("error"), message)

    # ---------- 创建备份 ----------

    def create_backup(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        run_in_background(self.frame, lambda: backups.estimate_compressed_size(self.storage_dir), self._on_estimated)

    def _on_estimated(self, estimated_size: Optional[int], error: Optional[BaseException]) -> None:
        if error is not None:
            self._set_busy(False)
            self._show_error("backup_estimate_failed")
            return
        size_text = backups.format_size(estimated_size)
        if not self._ask_yesno(self.t("backup_confirm_title"), self.t("backup_confirm_text", size=size_text)):
            self._set_busy(False)
            return

        self._progress = (0, 1)
        self.backup_progress["value"] = 0
        self.backup_progress_label.config(text="0%")
        self.backup_progress.pack(pady=5)
        self.backup_progress_label.pack(pady=2)

        def report_progress(current: int, total: int) -> None:
            self._progress = (current, total)  # 在后台线程执行，只记录，不碰界面

        run_in_background(
            self.frame, lambda: backups.create_backup(self.storage_dir, report_progress), self._on_backup_done
        )
        self._poll_progress()

    def _poll_progress(self) -> None:
        if not self._busy:
            return
        current, total = self._progress
        percent = int(current / total * 100)
        self.backup_progress["value"] = percent
        self.backup_progress_label.config(text=f"{percent}% ({current}/{total})" if current else "0%")
        self.frame.after(PROGRESS_POLL_MS, self._poll_progress)

    def _on_backup_done(self, backup_path: Optional[Path], error: Optional[BaseException]) -> None:
        self.backup_progress.pack_forget()
        self.backup_progress_label.pack_forget()
        self._set_busy(False)
        if error is not None:
            self._show_error("backup_failed", error)
        else:
            showinfo_relative(
                self.root,
                self.t("backup_success_title"),
                self.t(
                    "backup_success_text",
                    filename=backup_path.name,
                    size=backups.format_size(backup_path.stat().st_size),
                    path=str(backup_path),
                ),
            )
        self.refresh_backup_list()

    # ---------- 备份列表 ----------

    def refresh_backup_list(self) -> None:
        self.backup_tree.delete(*self.backup_tree.get_children())
        for info in backups.scan_backups(backups.get_backup_dir(self.storage_dir)):
            timestamp = info.timestamp.strftime(backups.TIMESTAMP_FORMAT) if info.timestamp else ""
            status = "" if info.has_info else self.t("no_info_file")
            self.backup_tree.insert(
                "", tk.END, values=(timestamp, info.zip_path.name, backups.format_size(info.file_size), status),
                tags=(str(info.zip_path),),
            )
        self._sync_selection()

    def on_backup_select(self, event=None) -> None:
        self._sync_selection()

    def _sync_selection(self) -> None:
        selected = self.backup_tree.selection()
        tags = self.backup_tree.item(selected[0], "tags") if selected else ()
        self.selected_backup_path = Path(tags[0]) if tags else None
        self._show_action_buttons(self.selected_backup_path is not None)

    # ---------- 删除 / 重命名 ----------

    def delete_backup(self) -> None:
        path = self.selected_backup_path
        if not path or self._busy:
            return
        if not self._ask_yesno(
            self.t("delete_backup_confirm_title"), self.t("delete_backup_confirm_text", filename=path.name)
        ):
            return
        try:
            backups.delete_backup(path)
        except OSError as e:
            logger.error(f"删除备份失败: {path}, 错误: {e}")
            self._show_error("delete_backup_failed", e)
            return
        showinfo_relative(self.root, self.t("success"), self.t("delete_backup_success"))
        self.refresh_backup_list()

    def rename_backup(self) -> None:
        path = self.selected_backup_path
        if not path or self._busy:
            return
        new_name = self._ask_new_name(path)
        if new_name is None:
            return
        new_name = new_name.strip()
        if not new_name:
            showerror_relative(self.root, self.t("error"), self.t("rename_backup_empty"))
            return
        if any(char in new_name for char in INVALID_FILENAME_CHARS):
            showerror_relative(self.root, self.t("error"), self.t("rename_backup_invalid_chars"))
            return
        try:
            new_path = backups.rename_backup(path, new_name)
        except OSError as e:
            logger.error(f"重命名备份失败: {path}, 错误: {e}")
            self._show_error("rename_backup_failed", e)
            return
        showinfo_relative(
            self.root,
            self.t("success"),
            self.t("rename_backup_success", old_filename=path.name, new_filename=new_path.name),
        )
        self.refresh_backup_list()

    def _ask_new_name(self, path: Path) -> Optional[str]:
        """弹出重命名输入框，取消时返回 None"""
        popup = self._make_popup(self.t("rename_backup_title"), "450x250")
        tk.Label(
            popup, text=self.t("rename_backup_prompt", filename=path.name), wraplength=400, justify="left",
            font=get_cjk_font(10), fg=Colors.TEXT_PRIMARY, bg=Colors.WHITE,
        ).pack(pady=10, padx=20)
        entry_frame = tk.Frame(popup, bg=Colors.WHITE)
        entry_frame.pack(pady=10, padx=20, fill="x")
        entry = Entry(entry_frame, width=40)
        entry.pack(side="left", fill="x", expand=True)
        entry.insert(0, path.stem)
        entry.select_range(0, tk.END)
        entry.focus()

        typed = {}
        confirmed = self._add_dialog_buttons(popup, on_yes=lambda: typed.setdefault("name", entry.get()))
        self.root.wait_window(popup)
        return typed.get("name") if confirmed() else None

    # ---------- 还原 ----------

    def restore_backup(self) -> None:
        path = self.selected_backup_path
        if not path or self._busy:
            return
        if not self._ask_yesno(self.t("restore_confirm_title"), self.t("restore_confirm_text")):
            return
        missing = backups.missing_required_files(path)
        if missing and not self._ask_yesno(
            self.t("restore_missing_files_title"), self.t("restore_missing_files_text", files=", ".join(missing))
        ):
            return

        self._set_busy(True)
        if self.on_restore_start:
            self.on_restore_start()
        run_in_background(self.frame, lambda: backups.restore_backup(path, self.storage_dir), self._on_restore_done)

    def _on_restore_done(self, _result, error: Optional[BaseException]) -> None:
        self._set_busy(False)
        if error is not None:
            self._show_error("restore_failed", error)
        else:
            showinfo_relative(self.root, self.t("success"), self.t("restore_success"))
        if self.on_restore_done:
            self.on_restore_done(error is None)

    # ---------- 语言 ----------

    def update_ui_texts(self) -> None:
        self._update_hint_text()
        self.backup_button.config(text=self.t("backup_button"))
        self.backup_list_title.config(text=self.t("backup_list_title"))
        self.refresh_button.config(text=self.t("refresh"))
        self._update_tree_headings()
        self.restore_button.config(text=self.t("restore_button"))
        self.delete_button.config(text=self.t("delete_backup_button"))
        self.rename_button.config(text=self.t("rename_backup_button"))
        self.refresh_backup_list()  # 「无 INFO 文件」状态列也需要翻译
