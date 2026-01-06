"""
备份还原 UI 组件

负责备份还原功能的用户界面，包括：
- 创建备份（带进度显示）
- 备份列表显示和管理
- 还原备份
- 删除和重命名备份

此模块将 UI 逻辑从 main_window.py 中分离出来，遵循单一职责原则。
"""
import logging
import os
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import Entry, Scrollbar, Toplevel, ttk
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, Union

from src.modules.backup.restore import BackupRestore
from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import (
    set_window_icon,
    showerror_relative,
    showinfo_relative,
)

logger = logging.getLogger(__name__)


class BackupRestoreTab:
    """备份还原标签页 UI 组件"""
    
    def __init__(
        self,
        parent: tk.Frame,
        root: tk.Tk,
        storage_dir: Optional[str],
        translations: Dict[str, Dict[str, str]],
        current_language: str,
        translate_func: Callable[..., str],
        on_restore_success: Optional[Callable[[], None]] = None
    ) -> None:
        """
        初始化备份还原标签页
        
        Args:
            parent: 父容器（Frame）
            root: 根窗口（用于对话框）
            storage_dir: 存储目录路径
            translations: 翻译字典
            current_language: 当前语言
            translate_func: 翻译函数
            on_restore_success: 还原成功后的回调函数（用于刷新其他组件）
        """
        self.parent = parent
        self.root = root
        self.storage_dir = Path(storage_dir) if storage_dir else None
        self.translations = translations
        self.current_language = current_language
        self.t = translate_func
        self.on_restore_success = on_restore_success
        
        # 备份管理器实例
        self.backup_restore: Optional[BackupRestore] = None
        
        # UI 组件
        self.backup_button: Optional[ttk.Button] = None
        self.backup_location_hint_text: Optional[tk.Text] = None
        self.backup_progress: Optional[ttk.Progressbar] = None
        self.backup_progress_label: Optional[tk.Label] = None
        self.backup_list_title: Optional[tk.Label] = None
        self.backup_refresh_button: Optional[ttk.Button] = None
        self.backup_tree: Optional[ttk.Treeview] = None
        self.restore_button: Optional[ttk.Button] = None
        self.delete_backup_button: Optional[ttk.Button] = None
        self.rename_backup_button: Optional[ttk.Button] = None
        
        # 状态
        self.selected_backup_path: Optional[str] = None
        
        # 初始化 UI
        self._init_ui()
    
    def _init_ui(self) -> None:
        """初始化 UI 组件"""
        if not self.storage_dir:
            return
        
        # 清除现有组件
        for widget in self.parent.winfo_children():
            widget.destroy()
        
        # 初始化备份管理器
        self.backup_restore = BackupRestore(self.storage_dir)
        
        # 创建备份区域
        self._create_backup_section()
        
        # 创建还原区域
        self._create_restore_section()
        
        # 刷新备份列表
        self.refresh_backup_list()
    
    def _create_backup_section(self) -> None:
        """创建备份区域"""
        backup_frame = tk.Frame(self.parent, bg=Colors.LIGHT_GRAY)
        backup_frame.pack(pady=15, fill="x")
        
        self.backup_button = ttk.Button(
            backup_frame,
            text=self.t("backup_button"),
            command=self.create_backup
        )
        self.backup_button.pack(pady=15)
        
        # 创建提示文本（使用Text widget支持部分文本加粗）
        self.backup_location_hint_text = tk.Text(
            backup_frame,
            height=1,
            wrap=tk.WORD,
            width=80,  # 设置合理的字符宽度，wrap会自动处理换行
            bg=Colors.LIGHT_GRAY,
            fg=Colors.TEXT_PRIMARY,
            font=get_cjk_font(10),
            relief=tk.FLAT,
            borderwidth=0,
            padx=10,
            pady=5,
            cursor="arrow"
        )
        self.backup_location_hint_text.pack(pady=(0, 10), fill="x", expand=False)
        
        # 绑定配置事件，动态调整宽度以适应容器
        def update_text_width(event=None):
            if self.backup_location_hint_text and backup_frame.winfo_width() > 1:
                try:
                    # 获取字体度量
                    font_obj = tkfont.Font(font=get_cjk_font(10))
                    char_width = font_obj.measure("M")
                    if char_width > 0:
                        # 获取父容器宽度，减去左右padding（10*2=20）
                        parent_width = backup_frame.winfo_width()
                        text_width = max(20, (parent_width - 20) // char_width)
                        # 临时启用以获取行数
                        was_disabled = self.backup_location_hint_text.cget("state") == tk.DISABLED
                        if was_disabled:
                            self.backup_location_hint_text.config(state=tk.NORMAL)
                        self.backup_location_hint_text.config(width=text_width)
                        # 更新后重新计算行数并调整高度
                        end_index = self.backup_location_hint_text.index(tk.END)
                        line_count = int(end_index.split('.')[0])
                        self.backup_location_hint_text.config(height=max(1, line_count))
                        if was_disabled:
                            self.backup_location_hint_text.config(state=tk.DISABLED)
                except Exception:
                    pass  # 如果计算失败，使用默认width
        
        backup_frame.bind('<Configure>', update_text_width)
        # 禁用编辑，但保持文本可选择（可选）
        self.backup_location_hint_text.config(state=tk.DISABLED)
        
        # 设置加粗样式
        bold_font = get_cjk_font(10, "bold")
        self.backup_location_hint_text.tag_configure("bold", font=bold_font)
        
        # 更新提示文本
        self._update_backup_hint_text()
        
        self.backup_progress = ttk.Progressbar(
            backup_frame, mode='determinate', length=300
        )
        self.backup_progress.pack(pady=8)
        self.backup_progress.pack_forget()
        
        self.backup_progress_label = tk.Label(
            backup_frame,
            text="",
            bg=Colors.LIGHT_GRAY,
            fg=Colors.TEXT_MUTED
        )
        self.backup_progress_label.pack(pady=4)
        self.backup_progress_label.pack_forget()
    
    def _update_backup_hint_text(self) -> None:
        """更新备份位置提示文本，支持**之间的文本加粗"""
        if not self.backup_location_hint_text:
            return
        
        text = self.t("backup_location_hint")
        
        # 启用编辑以更新内容
        self.backup_location_hint_text.config(state=tk.NORMAL)
        self.backup_location_hint_text.delete(1.0, tk.END)
        
        # 解析文本，找到**之间的内容并加粗
        import re
        parts = re.split(r'(\*\*.*?\*\*)', text)
        
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                # 加粗文本（去掉**标记）
                bold_text = part[2:-2]
                self.backup_location_hint_text.insert(tk.END, bold_text, "bold")
            else:
                # 普通文本
                self.backup_location_hint_text.insert(tk.END, part)
        
        # 设置文本居中
        self.backup_location_hint_text.tag_add("center", 1.0, tk.END)
        self.backup_location_hint_text.tag_configure("center", justify="center")
        
        # 获取实际行数并调整高度
        end_index = self.backup_location_hint_text.index(tk.END)
        line_count = int(end_index.split('.')[0])
        # 设置高度为实际行数，但至少为1行
        self.backup_location_hint_text.config(height=max(1, line_count))
        
        # 禁用编辑
        self.backup_location_hint_text.config(state=tk.DISABLED)
    
    def _create_restore_section(self) -> None:
        """创建还原区域"""
        restore_frame = tk.Frame(self.parent, bg=Colors.LIGHT_GRAY)
        restore_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 标题和刷新按钮
        restore_header = tk.Frame(restore_frame, bg=Colors.LIGHT_GRAY)
        restore_header.pack(fill="x", pady=4)
        
        self.backup_list_title = tk.Label(
            restore_header,
            text=self.t("backup_list_title"),
            font=get_cjk_font(12, "bold"),
            fg=Colors.TEXT_PRIMARY,
            bg=Colors.LIGHT_GRAY
        )
        self.backup_list_title.pack(side="left", padx=5)
        
        self.backup_refresh_button = ttk.Button(
            restore_header,
            text=self.t("refresh"),
            command=self.refresh_backup_list
        )
        self.backup_refresh_button.pack(side="right", padx=5)
        
        # 备份列表
        list_container = tk.Frame(restore_frame, bg=Colors.LIGHT_GRAY)
        list_container.pack(fill="both", expand=True)
        
        restore_scrollbar = Scrollbar(list_container, orient="vertical")
        restore_scrollbar.pack(side="right", fill="y")
        
        backup_tree_style = ttk.Style(self.root)
        backup_tree_style.configure("Backup.Treeview", rowheight=26, padding=(0, 6))
        
        self.backup_tree = ttk.Treeview(
            list_container,
            columns=("timestamp", "filename", "size", "status"),
            show="headings",
            height=18,
            yscrollcommand=restore_scrollbar.set,
            style="Backup.Treeview"
        )
        
        self.backup_tree.heading("timestamp", text=self.t("backup_timestamp"))
        self.backup_tree.column("timestamp", width=180)
        
        self.backup_tree.heading("filename", text=self.t("backup_filename"))
        self.backup_tree.column("filename", width=250)
        
        self.backup_tree.heading("size", text=self.t("backup_size"))
        self.backup_tree.column("size", width=100)
        
        self.backup_tree.heading("status", text=self.t("backup_status"))
        self.backup_tree.column("status", width=150)
        
        restore_scrollbar.config(command=self.backup_tree.yview)
        self.backup_tree.pack(side="left", fill="both", expand=True)
        
        self.backup_tree.bind('<<TreeviewSelect>>', self.on_backup_select)
        
        # 操作按钮区域
        button_area = tk.Frame(restore_frame, bg=Colors.LIGHT_GRAY)
        button_area.pack(pady=10)
        
        self.restore_button = ttk.Button(
            button_area,
            text=self.t("restore_button"),
            command=self.restore_backup
        )
        self.restore_button.pack(side="left", padx=5)
        self.restore_button.pack_forget()
        
        self.delete_backup_button = ttk.Button(
            button_area,
            text=self.t("delete_backup_button"),
            command=self.delete_backup
        )
        self.delete_backup_button.pack(side="left", padx=5)
        self.delete_backup_button.pack_forget()
        
        self.rename_backup_button = ttk.Button(
            button_area,
            text=self.t("rename_backup_button"),
            command=self.rename_backup
        )
        self.rename_backup_button.pack(side="left", padx=5)
        self.rename_backup_button.pack_forget()
    
    def _ask_yesno(self, title: str, message: str, icon: str = 'question') -> bool:
        """
        自定义确认对话框，使用翻译的按钮文本
        
        Args:
            title: 对话框标题
            message: 对话框消息
            icon: 图标类型
            
        Returns:
            用户是否确认
        """
        popup = Toplevel(self.root)
        popup.title(title)
        popup.geometry("400x250")
        popup.configure(bg=Colors.WHITE)
        popup.transient(self.root)
        popup.grab_set()
        
        set_window_icon(popup)
        
        if icon == 'warning':
            popup.iconname('warning')
        
        message_label = tk.Label(
            popup,
            text=message,
            wraplength=350,
            justify="left",
            font=get_cjk_font(10),
            fg=Colors.TEXT_PRIMARY,
            bg=Colors.WHITE
        )
        message_label.pack(pady=20, padx=20)
        
        confirmed = False
        
        def yes():
            nonlocal confirmed
            confirmed = True
            popup.destroy()
        
        def no():
            popup.destroy()
        
        button_frame = tk.Frame(popup, bg=Colors.WHITE)
        button_frame.pack(pady=10)
        
        ttk.Button(
            button_frame,
            text=self.t("yes_button"),
            command=yes
        ).pack(side="left", padx=10)
        
        ttk.Button(
            button_frame,
            text=self.t("no_button"),
            command=no
        ).pack(side="right", padx=10)
        
        popup.bind('<Return>', lambda e: yes())
        popup.bind('<Escape>', lambda e: no())
        
        self.root.wait_window(popup)
        return confirmed
    
    def create_backup(self) -> None:
        """创建备份"""
        if not self.storage_dir or not self.backup_restore:
            showerror_relative(
                self.root,
                self.t("error"),
                self.t("select_dir_hint")
            )
            return
        
        estimated_size = self.backup_restore.estimate_compressed_size(
            self.storage_dir
        )
        if estimated_size is None:
            showerror_relative(
                self.root,
                self.t("error"),
                self.t("backup_estimate_failed")
            )
            return
        
        size_str = self.backup_restore.format_size(estimated_size)
        
        result = self._ask_yesno(
            self.t("backup_confirm_title"),
            self.t("backup_confirm_text", size=size_str),
            icon='question'
        )
        
        if not result:
            return
        
        # 显示进度条
        if self.backup_progress:
            self.backup_progress.pack(pady=5)
        if self.backup_progress_label:
            self.backup_progress_label.pack(pady=2)
            self.backup_progress['value'] = 0
            self.backup_progress_label.config(text="0%")
        self.root.update()
        
        def progress_callback(current: int, total: int) -> None:
            progress = int((current / total) * 100)
            self.root.after(
                0,
                lambda: self._update_backup_progress(progress, current, total)
            )
        
        def backup_thread() -> None:
            try:
                result = self.backup_restore.create_backup(
                    self.storage_dir,
                    progress_callback
                )
                self.root.after(0, lambda: self._backup_completed(result))
            except Exception as e:
                logger.error(f"Error in backup thread: {e}", exc_info=True)
                self.root.after(0, lambda: self._backup_completed(None))
        
        threading.Thread(target=backup_thread, daemon=True).start()
    
    def _update_backup_progress(
        self,
        progress: int,
        current: int,
        total: int
    ) -> None:
        """更新备份进度条"""
        if self.backup_progress:
            self.backup_progress['value'] = progress
        if self.backup_progress_label:
            self.backup_progress_label.config(
                text=f"{progress}% ({current}/{total})"
            )
        self.root.update()
    
    def _backup_completed(self, result: Optional[Tuple[str, int, str]]) -> None:
        """备份完成回调"""
        if self.backup_progress:
            self.backup_progress.pack_forget()
        if self.backup_progress_label:
            self.backup_progress_label.pack_forget()
        
        if result is None:
            showerror_relative(
                self.root,
                self.t("error"),
                self.t("backup_failed")
            )
            return
        
        backup_path, actual_size, abs_path = result
        actual_size_str = self.backup_restore.format_size(actual_size)
        filename = os.path.basename(backup_path)
        success_msg = self.t(
            "backup_success_text",
            filename=filename,
            size=actual_size_str,
            path=abs_path
        )
        showinfo_relative(
            self.root,
            self.t("backup_success_title"),
            success_msg
        )
        
        self.refresh_backup_list()
    
    def refresh_backup_list(self) -> None:
        """刷新备份列表"""
        if not self.backup_restore or not self.backup_tree:
            return
        
        for item in self.backup_tree.get_children():
            self.backup_tree.delete(item)
        
        backup_dir = self.backup_restore.get_backup_dir()
        if not backup_dir:
            return
        
        backups = self.backup_restore.scan_backups(backup_dir)
        
        for zip_path, timestamp, has_info, file_size in backups:
            filename = os.path.basename(zip_path)
            size_str = self.backup_restore.format_size(file_size)
            
            if timestamp:
                timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            else:
                timestamp_str = ""
            
            if has_info:
                status = ""
            else:
                status = self.t("no_info_file")
            
            self.backup_tree.insert(
                "",
                tk.END,
                values=(timestamp_str, filename, size_str, status),
                tags=(zip_path,)
            )
    
    def on_backup_select(self, event: tk.Event) -> None:
        """处理备份列表选择事件"""
        if not self.backup_tree:
            return
        
        selected = self.backup_tree.selection()
        if selected:
            item_id = selected[0]
            tags = self.backup_tree.item(item_id, "tags")
            if tags:
                self.selected_backup_path = tags[0]
                if self.restore_button:
                    self.restore_button.pack(side="left", padx=5)
                if self.delete_backup_button:
                    self.delete_backup_button.pack(side="left", padx=5)
                if self.rename_backup_button:
                    self.rename_backup_button.pack(side="left", padx=5)
        else:
            self.selected_backup_path = None
            if self.restore_button:
                self.restore_button.pack_forget()
            if self.delete_backup_button:
                self.delete_backup_button.pack_forget()
            if self.rename_backup_button:
                self.rename_backup_button.pack_forget()
    
    def delete_backup(self) -> None:
        """删除备份"""
        if not self.selected_backup_path or not self.backup_restore:
            return
        
        filename = os.path.basename(self.selected_backup_path)
        result = self._ask_yesno(
            self.t("delete_backup_confirm_title"),
            self.t("delete_backup_confirm_text", filename=filename),
            icon='warning'
        )
        
        if not result:
            return
        
        success = self.backup_restore.delete_backup(self.selected_backup_path)
        
        if success:
            showinfo_relative(
                self.root,
                self.t("success"),
                self.t("delete_backup_success")
            )
            self.selected_backup_path = None
            if self.restore_button:
                self.restore_button.pack_forget()
            if self.delete_backup_button:
                self.delete_backup_button.pack_forget()
            if self.rename_backup_button:
                self.rename_backup_button.pack_forget()
            self.refresh_backup_list()
        else:
            showerror_relative(
                self.root,
                self.t("error"),
                self.t("delete_backup_failed")
            )
    
    def rename_backup(self) -> None:
        """重命名备份"""
        if not self.selected_backup_path or not self.backup_restore:
            return
        
        current_filename = os.path.basename(self.selected_backup_path)
        current_name_without_ext = os.path.splitext(current_filename)[0]
        
        popup = Toplevel(self.root)
        popup.title(self.t("rename_backup_title"))
        popup.geometry("450x250")
        popup.configure(bg=Colors.WHITE)
        popup.transient(self.root)
        popup.grab_set()
        
        set_window_icon(popup)
        
        new_filename: Optional[str] = None
        
        prompt_text = self.t("rename_backup_prompt", filename=current_filename)
        prompt_label = tk.Label(
            popup,
            text=prompt_text,
            wraplength=400,
            justify="left",
            font=get_cjk_font(10),
            fg=Colors.TEXT_PRIMARY,
            bg=Colors.WHITE
        )
        prompt_label.pack(pady=10, padx=20)
        
        entry_frame = tk.Frame(popup, bg=Colors.WHITE)
        entry_frame.pack(pady=10, padx=20, fill="x")
        
        entry = Entry(entry_frame, width=40)
        entry.pack(side="left", fill="x", expand=True)
        entry.insert(0, current_name_without_ext)
        entry.select_range(0, tk.END)
        entry.focus()
        
        def confirm():
            nonlocal new_filename
            new_filename = entry.get()
            popup.destroy()
        
        def cancel():
            popup.destroy()
        
        button_frame = tk.Frame(popup, bg=Colors.WHITE)
        button_frame.pack(pady=10)
        
        ttk.Button(
            button_frame,
            text=self.t("yes_button"),
            command=confirm
        ).pack(side="left", padx=10)
        
        ttk.Button(
            button_frame,
            text=self.t("no_button"),
            command=cancel
        ).pack(side="right", padx=10)
        
        popup.bind('<Return>', lambda e: confirm())
        popup.bind('<Escape>', lambda e: cancel())
        
        self.root.wait_window(popup)
        
        if not new_filename:
            return
        
        new_filename = new_filename.strip()
        
        if not new_filename:
            showerror_relative(
                self.root,
                self.t("error"),
                self.t("rename_backup_empty")
            )
            return
        
        invalid_chars = '<>:"/\\|?*'
        if any(char in new_filename for char in invalid_chars):
            showerror_relative(
                self.root,
                self.t("error"),
                self.t("rename_backup_invalid_chars")
            )
            return
        
        result = self.backup_restore.rename_backup(
            self.selected_backup_path,
            new_filename
        )
        
        if result:
            new_path, old_filename = result
            showinfo_relative(
                self.root,
                self.t("success"),
                self.t(
                    "rename_backup_success",
                    old_filename=old_filename,
                    new_filename=os.path.basename(new_path)
                )
            )
            self.selected_backup_path = new_path
            self.refresh_backup_list()
        else:
            showerror_relative(
                self.root,
                self.t("error"),
                self.t("rename_backup_failed")
            )
    
    def restore_backup(self) -> None:
        """还原备份"""
        if not self.selected_backup_path or not self.backup_restore:
            return
        
        result = self._ask_yesno(
            self.t("restore_confirm_title"),
            self.t("restore_confirm_text"),
            icon='warning'
        )
        
        if not result:
            return
        
        missing_files = self.backup_restore.check_required_files(
            self.selected_backup_path
        )
        
        if missing_files:
            files_str = ", ".join(missing_files)
            result = self._ask_yesno(
                self.t("restore_missing_files_title"),
                self.t("restore_missing_files_text", files=files_str),
                icon='warning'
            )
            
            if not result:
                return
        
        success = self.backup_restore.restore_backup(
            self.selected_backup_path,
            self.storage_dir
        )
        
        if success:
            showinfo_relative(
                self.root,
                self.t("success"),
                self.t("restore_success")
            )
            # 调用回调函数刷新其他组件
            if self.on_restore_success:
                self.on_restore_success()
        else:
            showerror_relative(
                self.root,
                self.t("error"),
                self.t("restore_failed")
            )
    
    def update_ui_texts(self) -> None:
        """更新所有 UI 文本（用于语言切换）"""
        self._update_backup_hint_text()
        if self.backup_button:
            self.backup_button.config(text=self.t("backup_button"))
        if self.backup_list_title:
            self.backup_list_title.config(text=self.t("backup_list_title"))
        if self.backup_refresh_button:
            self.backup_refresh_button.config(text=self.t("refresh"))
        if self.backup_tree:
            self.backup_tree.heading("timestamp", text=self.t("backup_timestamp"))
            self.backup_tree.heading("filename", text=self.t("backup_filename"))
            self.backup_tree.heading("size", text=self.t("backup_size"))
            self.backup_tree.heading("status", text=self.t("backup_status"))
        if self.restore_button:
            self.restore_button.config(text=self.t("restore_button"))
        if self.delete_backup_button:
            self.delete_backup_button.config(text=self.t("delete_backup_button"))
        if self.rename_backup_button:
            self.rename_backup_button.config(text=self.t("rename_backup_button"))
    
    def update_language(self, new_language: str) -> None:
        """更新语言设置"""
        self.current_language = new_language
        self.update_ui_texts()
    
    def set_storage_dir(self, storage_dir: Optional[str]) -> None:
        """设置存储目录并重新初始化 UI"""
        self.storage_dir = Path(storage_dir) if storage_dir else None
        self._init_ui()

