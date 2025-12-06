import tkinter as tk
from tkinter import filedialog, messagebox, Scrollbar, Toplevel, Entry, Label, simpledialog
from tkinter import ttk
from PIL import Image
from PIL import ImageTk
import base64
import json
import urllib.parse
import os
import random
import string
from datetime import datetime
import tempfile
import zipfile
import shutil
import locale
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import webbrowser
import re
import platform
import hashlib
import traceback
from typing import Optional, Dict, List, Tuple, Any, Set, Union
from translations import TRANSLATIONS
from save_analyzer import SaveAnalyzer
from utils import set_window_icon
from backup_restore import BackupRestore
from toast import Toast
from styles import get_cjk_font, get_parent_bg, init_styles, Colors, Debouncer
from screenshot_manager import ScreenshotManager, ScreenshotManagerUI
from others import OthersTab

# 类型别名定义
PathType = Union[str, bytes, os.PathLike]
JSONType = Union[Dict[str, Any], List[Any], str, int, float, bool, None]

# From the sky bereft of stars

if platform.system() == "Windows":
    try:
        import winreg
    except ImportError:
        winreg = None
else:
    winreg = None

class SavTool:
    def __init__(self, root):
        self.root = root
        self.translations = TRANSLATIONS
        self.current_language = self.detect_system_language()
        self.root.title(self.t("window_title"))
        self.root.geometry("850x600")
        self.root.minsize(750, 600)  # 设置最小窗口大小
        
        # 设置窗口图标
        set_window_icon(self.root)
        
        # 初始化统一样式
        init_styles(self.root)

        # 创建菜单栏
        self._create_menubar()
        
        # 创建主界面
        self._create_main_interface()
        
        # 初始化组件状态
        self._initialize_components()
        
        # 绑定事件
        self._bind_events()
        
        # 默认显示存档分析 tab（索引 0）
        self.notebook.select(0)
    
    def _create_menubar(self) -> None:
        """创建菜单栏"""
        self.menubar = tk.Menu(self.root)
        self.root.config(menu=self.menubar)
        
        # 目录菜单
        self.directory_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label=self.t("directory_menu"), menu=self.directory_menu)
        self.directory_menu.add_command(label=self.t("browse_dir"), command=self.select_dir)
        self.directory_menu.add_command(label=self.t("auto_detect_steam"), command=self.auto_detect_steam)
        
        # 语言菜单
        self.language_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Language", menu=self.language_menu)
        self.language_var = tk.StringVar(value=self.current_language)
        
        language_options = [
            ("日本語", "ja_JP"),
            ("中文", "zh_CN"),
            ("English", "en_US")
        ]
        
        for label, value in language_options:
            self.language_menu.add_radiobutton(
                label=label,
                variable=self.language_var,
                value=value,
                command=lambda v=value: self.change_language(v)
            )
        
        # 帮助菜单
        help_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Help", command=self.show_help)
    
    def _create_main_interface(self) -> None:
        """创建主界面"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=0, pady=0)
        
        # 创建各个标签页的框架
        tab_configs = [
            ("save_analyzer_tab", "analyzer_frame", "analyzer_hint_label"),
            ("screenshot_management_tab", "screenshot_frame", "screenshot_hint_label"),
            ("backup_restore_tab", "backup_restore_frame", "backup_restore_hint_label"),
            ("others_tab", "others_frame", "others_hint_label")
        ]
        
        for tab_text, frame_attr, hint_attr in tab_configs:
            frame = tk.Frame(self.notebook)
            self.notebook.add(frame, text=self.t(tab_text))
            setattr(self, frame_attr, frame)
            
            # 创建提示标签
            hint_label = tk.Label(
                frame,
                text=self.t("select_dir_hint"),
                fg="#D554BC",
                font=get_cjk_font(12)
            )
            hint_label.pack(pady=50)
            setattr(self, hint_attr, hint_label)
    
    def _initialize_components(self) -> None:
        """初始化组件状态"""
        self.save_analyzer: Optional[SaveAnalyzer] = None
        self.backup_restore: Optional[BackupRestore] = None
        self.others_tab: Optional[OthersTab] = None
        self.screenshot_manager_ui: Optional[ScreenshotManagerUI] = None
        
        # 存档文件监控相关
        self.storage_dir: Optional[str] = None
        self.save_file_path: Optional[str] = None
        self.temp_file_path: Optional[str] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.monitor_running: bool = False
        self.active_toasts: List[Toast] = []
        self.variable_change_chains: Dict[str, Dict[str, Any]] = {}
        self.ab_initio_triggered: bool = False
        
        # Toast功能控制
        self.toast_enabled: bool = True
        self.toast_ignore_record: str = "record, initialVars"
    
    def _bind_events(self) -> None:
        """绑定事件"""
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def detect_system_language(self) -> str:
        """检测系统语言并返回支持的语言代码"""
        language_detectors = [
            self._detect_from_locale_getdefaultlocale,
            self._detect_from_environment_vars,
            self._detect_from_locale_getlocale,
            self._detect_from_windows_api,
            self._detect_from_system_locale
        ]
        
        for detector in language_detectors:
            try:
                result = detector()
                if result:
                    return result
            except Exception:
                continue
        
        # 默认返回英语
        return "en_US"
    
    def _detect_from_locale_getdefaultlocale(self) -> Optional[str]:
        """从locale.getdefaultlocale检测语言"""
        try:
            default_locale = locale.getdefaultlocale()
            if default_locale and default_locale[0]:
                language_code = default_locale[0].split('_')[0]
                return self._map_language_code(language_code)
        except Exception:
            pass
        return None
    
    def _detect_from_environment_vars(self) -> Optional[str]:
        """从环境变量检测语言"""
        env_keys = ['APP_LANG', 'SCREENSHOT_TOOL_LANG', 'LANGUAGE', 'LANG', 'LC_ALL', 'LC_MESSAGES']
        
        for env_key in env_keys:
            env_lang = os.environ.get(env_key)
            if env_lang:
                try:
                    # 规范化语言代码
                    normalized_lang = env_lang.strip().replace('-', '_').split('.')[0].lower()
                    return self._map_language_code(normalized_lang)
                except Exception:
                    continue
        return None
    
    def _detect_from_locale_getlocale(self) -> Optional[str]:
        """从locale.getlocale检测语言"""
        try:
            system_locale, _ = locale.getlocale()
            if not system_locale:
                # 尝试设置默认locale后重新获取
                try:
                    locale.setlocale(locale.LC_ALL, '')
                    system_locale, _ = locale.getlocale()
                except Exception:
                    pass
            
            if system_locale:
                locale_lower = system_locale.replace('-', '_').split('.')[0].lower()
                return self._map_language_code(locale_lower)
        except Exception:
            pass
        return None
    
    def _detect_from_windows_api(self) -> Optional[str]:
        """从Windows API检测语言"""
        if platform.system() != "Windows":
            return None
            
        try:
            import ctypes
            windll = ctypes.windll
            GetUserDefaultUILanguage = windll.kernel32.GetUserDefaultUILanguage
            lang_id = GetUserDefaultUILanguage()
            
            # 中文语言ID
            chinese_ids = {0x804, 0x404, 0xc04, 0x1004, 0x1404, 0x7c04}
            # 日文语言ID
            japanese_ids = {0x411, 0x814}
            # 英文语言ID
            english_ids = {0x409, 0x809}
            
            if lang_id in chinese_ids:
                return "zh_CN"
            elif lang_id in japanese_ids:
                return "ja_JP"
            elif lang_id in english_ids:
                return "en_US"
        except Exception:
            pass
        return None
    
    def _detect_from_system_locale(self) -> Optional[str]:
        """从系统locale检测语言"""
        try:
            system_locale = locale.getlocale()[0]
            if system_locale:
                locale_lower = system_locale.replace('-', '_').split('.')[0].lower()
                return self._map_language_code(locale_lower)
        except Exception:
            pass
        return None
    
    def _map_language_code(self, language_code: str) -> Optional[str]:
        """映射语言代码到支持的语言"""
        language_mapping = {
            'zh': 'zh_CN',
            'ja': 'ja_JP',
            'en': 'en_US'
        }
        
        # 检查精确匹配
        if language_code in language_mapping:
            return language_mapping[language_code]
        
        # 检查前缀匹配
        for prefix, lang in language_mapping.items():
            if language_code.startswith(prefix):
                return lang
        
        return None
    
    def t(self, key: str, **kwargs) -> str:
        """翻译函数，支持格式化字符串"""
        try:
            lang_dict = self.translations.get(self.current_language, {})
            text = lang_dict.get(key, key)
            
            if kwargs:
                try:
                    return text.format(**kwargs)
                except (KeyError, ValueError, IndexError):
                    # 格式化失败时返回原始文本
                    return text
            return text
        except Exception:
            # 发生任何异常时返回key本身
            return key
    
    def change_language(self, lang: str) -> None:
        """切换语言"""
        if lang not in self.translations:
            return
            
        self.current_language = lang
        self.language_var.set(lang)
        
        try:
            self.update_ui_texts()
        except Exception as e:
            # 语言切换失败时记录错误但继续运行
            print(f"Language switch error: {e}")
        
        # 更新存档分析器的语言（如果已初始化）
        if self.save_analyzer is not None:
            try:
                self.save_analyzer.current_language = lang
                self.save_analyzer.refresh()
            except Exception as e:
                print(f"Save analyzer language update error: {e}")
    
    def ask_yesno(self, title, message, icon='question'):
        """自定义确认对话框，使用翻译的按钮文本"""
        popup = Toplevel(self.root)
        popup.title(title)
        popup.geometry("400x150")
        popup.transient(self.root)
        popup.grab_set()
        
        # 设置窗口图标
        set_window_icon(popup)
        
        # 设置图标
        if icon == 'warning':
            popup.iconname('warning')
        
        # 显示消息
        ttk.Label(popup, text=message, wraplength=350, justify="left").pack(pady=20, padx=20)
        
        confirmed = False
        
        def yes():
            nonlocal confirmed
            confirmed = True
            popup.destroy()
        
        def no():
            popup.destroy()
        
        # 按钮框架
        button_frame = tk.Frame(popup)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text=self.t("yes_button"), command=yes).pack(side="left", padx=10)
        ttk.Button(button_frame, text=self.t("no_button"), command=no).pack(side="right", padx=10)
        
        # 绑定回车键和ESC键
        popup.bind('<Return>', lambda e: yes())
        popup.bind('<Escape>', lambda e: no())
        
        # 等待窗口关闭
        self.root.wait_window(popup)
        return confirmed
    
    def init_save_analyzer(self):
        """初始化存档分析界面"""
        if not self.storage_dir:
            return
        
        # 清除 analyzer_frame 中的所有子组件（包括提示标签）
        for widget in self.analyzer_frame.winfo_children():
            widget.destroy()
        
        # 创建新的存档分析界面
        self.save_analyzer = SaveAnalyzer(self.analyzer_frame, self.storage_dir, 
                                          self.translations, self.current_language)
    
    def init_others_tab(self):
        """初始化其他功能标签页"""
        if not self.storage_dir:
            return
        
        # 隐藏其他tab的提示标签
        self.others_hint_label.pack_forget()
        # 清除 others_frame 中的所有子组件
        for widget in self.others_frame.winfo_children():
            widget.destroy()
        
        # 创建新的其他功能界面
        self.others_tab = OthersTab(self.others_frame, self.storage_dir, 
                                    self.translations, self.current_language, self)
    
    def init_backup_restore(self):
        """初始化备份/还原界面"""
        if not self.storage_dir:
            return
        
        # 清除 backup_restore_frame 中的所有子组件（包括提示标签）
        for widget in self.backup_restore_frame.winfo_children():
            widget.destroy()
        
        # 创建BackupRestore实例
        self.backup_restore = BackupRestore(self.storage_dir)
        
        # 创建UI布局（上下布局）
        # 上方：备份按钮区域
        backup_frame = tk.Frame(self.backup_restore_frame, bg=Colors.WHITE)
        backup_frame.pack(pady=20, fill="x")
        
        self.backup_button = ttk.Button(backup_frame, text=self.t("backup_button"), 
                                   command=self.create_backup)
        self.backup_button.pack(pady=10)
        
        # 进度条（初始隐藏）
        self.backup_progress = ttk.Progressbar(backup_frame, mode='determinate', length=300)
        self.backup_progress.pack(pady=5)
        self.backup_progress.pack_forget()
        
        # 进度标签（初始隐藏）
        self.backup_progress_label = tk.Label(backup_frame, text="", bg=Colors.WHITE, fg="#666")
        self.backup_progress_label.pack(pady=2)
        self.backup_progress_label.pack_forget()
        
        # 下方：还原列表区域
        restore_frame = tk.Frame(self.backup_restore_frame, bg=Colors.WHITE)
        restore_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 还原列表标题和刷新按钮
        restore_header = tk.Frame(restore_frame, bg=Colors.WHITE)
        restore_header.pack(fill="x", pady=5)
        
        self.backup_list_title = ttk.Label(restore_header, text=self.t("backup_list_title"), 
                                 font=get_cjk_font(12, "bold"))
        self.backup_list_title.pack(side="left", padx=5)
        
        self.backup_refresh_button = ttk.Button(restore_header, text=self.t("refresh"), 
                                    command=self.refresh_backup_list)
        self.backup_refresh_button.pack(side="right", padx=5)
        
        # 创建Treeview显示备份列表
        list_container = tk.Frame(restore_frame, bg=Colors.WHITE)
        list_container.pack(fill="both", expand=True)
        
        restore_scrollbar = Scrollbar(list_container, orient="vertical")
        restore_scrollbar.pack(side="right", fill="y")
        
        self.backup_tree = ttk.Treeview(list_container, 
                                        columns=("timestamp", "filename", "size", "status"), 
                                        show="headings", height=15,
                                        yscrollcommand=restore_scrollbar.set)
        
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
        
        # 绑定选择事件
        self.backup_tree.bind('<<TreeviewSelect>>', self.on_backup_select)
        
        # 按钮区域
        button_area = tk.Frame(restore_frame, bg=Colors.WHITE)
        button_area.pack(pady=10)
        
        # 还原按钮（初始隐藏）
        self.restore_button = ttk.Button(button_area, text=self.t("restore_button"), 
                                         command=self.restore_backup)
        self.restore_button.pack(side="left", padx=5)
        self.restore_button.pack_forget()
        
        # 删除按钮（初始隐藏）
        self.delete_backup_button = ttk.Button(button_area, text=self.t("delete_backup_button"), 
                                                command=self.delete_backup)
        self.delete_backup_button.pack(side="left", padx=5)
        self.delete_backup_button.pack_forget()
        
        # 重命名按钮（初始隐藏）
        self.rename_backup_button = ttk.Button(button_area, text=self.t("rename_backup_button"), 
                                                command=self.rename_backup)
        self.rename_backup_button.pack(side="left", padx=5)
        self.rename_backup_button.pack_forget()
        
        # 存储选中的备份路径
        self.selected_backup_path = None
        
        # 刷新备份列表
        self.refresh_backup_list()
    
    def create_backup(self):
        """创建备份"""
        if not self.storage_dir or not self.backup_restore:
            messagebox.showerror(self.t("error"), self.t("select_dir_hint"))
            return
        
        # 估算压缩后大小
        estimated_size = self.backup_restore.estimate_compressed_size(self.storage_dir)
        if estimated_size is None:
            messagebox.showerror(self.t("error"), self.t("backup_estimate_failed"))
            return
        
        # 格式化大小
        size_str = self.backup_restore.format_size(estimated_size)
        
        # 确认对话框
        result = self.ask_yesno(
            self.t("backup_confirm_title"),
            self.t("backup_confirm_text", size=size_str),
            icon='question'
        )
        
        if not result:
            return
        
        # 显示进度条
        self.backup_progress.pack(pady=5)
        self.backup_progress_label.pack(pady=2)
        self.backup_progress['value'] = 0
        self.backup_progress_label.config(text="0%")
        self.root.update()
        
        # 定义进度回调函数
        def progress_callback(current, total):
            progress = int((current / total) * 100)
            self.root.after(0, lambda: self._update_backup_progress(progress, current, total))
        
        # 在后台线程中执行备份
        def backup_thread():
            try:
                result = self.backup_restore.create_backup(self.storage_dir, progress_callback)
                self.root.after(0, lambda: self._backup_completed(result))
            except Exception as e:
                self.root.after(0, lambda: self._backup_completed(None))
        
        threading.Thread(target=backup_thread, daemon=True).start()
    
    def _update_backup_progress(self, progress, current, total):
        """更新备份进度条"""
        self.backup_progress['value'] = progress
        self.backup_progress_label.config(text=f"{progress}% ({current}/{total})")
        self.root.update()
    
    def _backup_completed(self, result):
        """备份完成回调"""
        # 隐藏进度条
        self.backup_progress.pack_forget()
        self.backup_progress_label.pack_forget()
        
        if result is None:
            messagebox.showerror(self.t("error"), self.t("backup_failed"))
            return
        
        backup_path, actual_size, abs_path = result
        
        # 格式化实际大小
        actual_size_str = self.backup_restore.format_size(actual_size)
        
        # 显示成功消息
        filename = os.path.basename(backup_path)
        success_msg = self.t("backup_success_text", 
                            filename=filename, 
                            size=actual_size_str, 
                            path=abs_path)
        messagebox.showinfo(self.t("backup_success_title"), success_msg)
        
        # 刷新备份列表
        self.refresh_backup_list()
    
    def refresh_backup_list(self):
        """刷新备份列表"""
        if not self.backup_restore:
            return
        
        # 清除现有项目
        for item in self.backup_tree.get_children():
            self.backup_tree.delete(item)
        
        # 获取备份目录
        backup_dir = self.backup_restore.get_backup_dir()
        if not backup_dir:
            return
        
        # 扫描备份
        backups = self.backup_restore.scan_backups(backup_dir)
        
        # 添加到列表
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
            
            self.backup_tree.insert("", tk.END, 
                                   values=(timestamp_str, filename, size_str, status),
                                   tags=(zip_path,))
    
    def on_backup_select(self, event):
        """处理备份列表选择事件"""
        selected = self.backup_tree.selection()
        if selected:
            item_id = selected[0]
            tags = self.backup_tree.item(item_id, "tags")
            if tags:
                self.selected_backup_path = tags[0]
                self.restore_button.pack(side="left", padx=5)
                self.delete_backup_button.pack(side="left", padx=5)
                self.rename_backup_button.pack(side="left", padx=5)
        else:
            self.selected_backup_path = None
            self.restore_button.pack_forget()
            self.delete_backup_button.pack_forget()
            self.rename_backup_button.pack_forget()
    
    def delete_backup(self):
        """删除备份"""
        if not self.selected_backup_path:
            return
        
        if not self.backup_restore:
            return
        
        # 确认删除
        filename = os.path.basename(self.selected_backup_path)
        result = self.ask_yesno(
            self.t("delete_backup_confirm_title"),
            self.t("delete_backup_confirm_text", filename=filename),
            icon='warning'
        )
        
        if not result:
            return
        
        # 执行删除
        success = self.backup_restore.delete_backup(self.selected_backup_path)
        
        if success:
            messagebox.showinfo(self.t("success"), self.t("delete_backup_success"))
            # 清除选择
            self.selected_backup_path = None
            self.restore_button.pack_forget()
            self.delete_backup_button.pack_forget()
            self.rename_backup_button.pack_forget()
            # 刷新备份列表
            self.refresh_backup_list()
        else:
            messagebox.showerror(self.t("error"), self.t("delete_backup_failed"))
    
    def rename_backup(self):
        """重命名备份"""
        if not self.selected_backup_path:
            return
        
        if not self.backup_restore:
            return
        
        # 获取当前文件名（不含扩展名）
        current_filename = os.path.basename(self.selected_backup_path)
        current_name_without_ext = os.path.splitext(current_filename)[0]
        
        # 创建自定义输入对话框
        popup = Toplevel(self.root)
        popup.title(self.t("rename_backup_title"))
        popup.geometry("450x150")
        popup.transient(self.root)
        popup.grab_set()
        
        # 设置窗口图标
        set_window_icon(popup)
        
        new_filename = None
        
        # 显示提示信息
        prompt_text = self.t("rename_backup_prompt", filename=current_filename)
        ttk.Label(popup, text=prompt_text, wraplength=400, justify="left").pack(pady=10, padx=20)
        
        # 创建输入框
        entry_frame = tk.Frame(popup)
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
        
        # 按钮框架
        button_frame = tk.Frame(popup)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text=self.t("yes_button"), command=confirm).pack(side="left", padx=10)
        ttk.Button(button_frame, text=self.t("no_button"), command=cancel).pack(side="right", padx=10)
        
        # 绑定回车键和ESC键
        popup.bind('<Return>', lambda e: confirm())
        popup.bind('<Escape>', lambda e: cancel())
        
        # 等待窗口关闭
        self.root.wait_window(popup)
        
        if not new_filename:
            return
        
        # 去除首尾空格
        new_filename = new_filename.strip()
        
        if not new_filename:
            messagebox.showerror(self.t("error"), self.t("rename_backup_empty"))
            return
        
        # 检查文件名是否包含非法字符
        invalid_chars = '<>:"/\\|?*'
        if any(char in new_filename for char in invalid_chars):
            messagebox.showerror(self.t("error"), self.t("rename_backup_invalid_chars"))
            return
        
        # 执行重命名
        result = self.backup_restore.rename_backup(self.selected_backup_path, new_filename)
        
        if result:
            new_path, old_filename = result
            messagebox.showinfo(self.t("success"), self.t("rename_backup_success", 
                                                         old_filename=old_filename,
                                                         new_filename=os.path.basename(new_path)))
            # 更新选中的备份路径
            self.selected_backup_path = new_path
            # 刷新备份列表
            self.refresh_backup_list()
        else:
            messagebox.showerror(self.t("error"), self.t("rename_backup_failed"))
    
    def restore_backup(self):
        """还原备份"""
        if not self.selected_backup_path:
            return
        
        if not self.backup_restore:
            return
        
        # 第一次确认
        result = self.ask_yesno(
            self.t("restore_confirm_title"),
            self.t("restore_confirm_text"),
            icon='warning'
        )
        
        if not result:
            return
        
        # 检查必需文件
        missing_files = self.backup_restore.check_required_files(self.selected_backup_path)
        
        if missing_files:
            # 第二次确认（如果有缺失文件）
            files_str = ", ".join(missing_files)
            result = self.ask_yesno(
                self.t("restore_missing_files_title"),
                self.t("restore_missing_files_text", files=files_str),
                icon='warning'
            )
            
            if not result:
                return
        
        # 执行还原
        success = self.backup_restore.restore_backup(self.selected_backup_path, self.storage_dir)
        
        if success:
            messagebox.showinfo(self.t("success"), self.t("restore_success"))
            # 刷新其他tab的数据
            if self.storage_dir:
                self.load_screenshots()
                if self.save_analyzer:
                    self.save_analyzer.refresh()
        else:
            messagebox.showerror(self.t("error"), self.t("restore_failed"))
    
    def on_tab_changed(self, event=None):
        """处理 tab 切换事件，切换到存档分析页面时自动刷新"""
        try:
            # 获取当前选中的 tab 索引
            current_tab = self.notebook.index(self.notebook.select())
            # 如果切换到存档分析 tab（索引 0）且 save_analyzer 已初始化
            if current_tab == 0 and self.save_analyzer is not None:
                # 自动刷新存档分析页面
                self.save_analyzer.refresh()
            # 如果切换到备份/还原 tab（索引 2）且 backup_restore 已初始化
            elif current_tab == 2 and self.backup_restore is not None:
                # 刷新备份列表
                self.refresh_backup_list()
        except Exception:
            # 忽略错误，避免影响正常的 tab 切换
            pass
    
    def _start_file_monitor(self):
        """启动存档文件监控"""
        if not self.storage_dir:
            return
        
        # 停止之前的监控（如果存在）
        self._stop_file_monitor()
        
        # 设置存档文件路径和临时文件路径
        self.save_file_path = os.path.join(self.storage_dir, 'DevilConnection_sf.sav')
        self.temp_file_path = os.path.join(self.storage_dir, '.temp_sf.sav')
        
        # 清理可能存在的旧临时文件（防止上次异常退出遗留）
        self._cleanup_temp_file()
        
        # 初始化临时文件：如果不存在或已存在，都尝试写入当前存档内容
        self._initialize_temp_file()
        
        # 启动监控线程
        self.monitor_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def _initialize_temp_file(self):
        """初始化临时文件：读取当前存档并写入临时文件"""
        try:
            # 检查路径有效性
            if not self.save_file_path or not isinstance(self.save_file_path, str):
                return
            
            if not os.path.exists(self.save_file_path):
                # 如果存档文件不存在，删除临时文件（如果存在）
                if self.temp_file_path and isinstance(self.temp_file_path, str) and os.path.exists(self.temp_file_path):
                    try:
                        os.remove(self.temp_file_path)
                    except Exception:
                        pass
                return
            
            # 尝试读取当前存档文件（可能需要重试）
            save_content = None
            for retry in range(5):
                save_content = self._read_file_raw(self.save_file_path)
                if save_content is not None:
                    break
                time.sleep(0.2)
            
            # 如果成功读取，写入临时文件
            if save_content is not None:
                self._write_temp_file(save_content)
        except Exception as e:
            # 捕获初始化过程中的异常
            try:
                import traceback
                print(f"临时文件初始化异常: {e}")
                print(traceback.format_exc())
            except:
                pass
    
    def _read_file_raw(self, file_path: Optional[str]) -> Optional[str]:
        """读取文件的原始内容（未解码的字符串）"""
        if not self._is_valid_file_path(file_path):
            return None
        
        # 尝试多种读取策略
        read_strategies = [
            self._read_utf8_text,
            self._read_binary_decode,
            self._read_with_retry
        ]
        
        for strategy in read_strategies:
            try:
                content = strategy(file_path)
                if content is not None:
                    return content.strip()
            except Exception:
                continue
        
        return None
    
    def _is_valid_file_path(self, file_path: Optional[str]) -> bool:
        """检查文件路径是否有效"""
        if not file_path or not isinstance(file_path, str):
            return False
        
        try:
            return os.path.exists(file_path) and os.path.isfile(file_path)
        except (OSError, TypeError):
            return False
    
    def _read_utf8_text(self, file_path: str) -> Optional[str]:
        """以UTF-8文本模式读取文件"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='strict') as f:
                return f.read()
        except (IOError, OSError, PermissionError, UnicodeDecodeError):
            return None
    
    def _read_binary_decode(self, file_path: str) -> Optional[str]:
        """以二进制模式读取并解码"""
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read()
            return raw_data.decode('utf-8', errors='ignore')
        except (IOError, OSError, PermissionError, UnicodeDecodeError):
            return None
    
    def _read_with_retry(self, file_path: str, max_retries: int = 3) -> Optional[str]:
        """带重试的文件读取"""
        for attempt in range(max_retries):
            try:
                # 先检查文件是否可读
                if not os.access(file_path, os.R_OK):
                    time.sleep(0.1 * (attempt + 1))
                    continue
                
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except (IOError, OSError, PermissionError):
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))
                continue
        return None
    
    def _write_temp_file(self, content: Optional[str]) -> bool:
        """写入临时文件，返回是否成功"""
        if not self._is_valid_temp_file_path() or content is None:
            return False
        
        try:
            # 确保目录存在
            temp_dir = os.path.dirname(self.temp_file_path)
            if temp_dir and not os.path.exists(temp_dir):
                os.makedirs(temp_dir, exist_ok=True)
            
            # 使用原子写入避免文件损坏
            temp_fd, temp_path = tempfile.mkstemp(
                dir=os.path.dirname(self.temp_file_path),
                prefix='.temp_sf_',
                suffix='.sav'
            )
            
            try:
                with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # 原子替换文件
                if os.path.exists(self.temp_file_path):
                    os.replace(temp_path, self.temp_file_path)
                else:
                    os.rename(temp_path, self.temp_file_path)
                
                return True
            except Exception:
                # 清理临时文件
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                return False
        except Exception:
            return False
    
    def _is_valid_temp_file_path(self) -> bool:
        """检查临时文件路径是否有效"""
        return (self.temp_file_path is not None and
                isinstance(self.temp_file_path, str) and
                len(self.temp_file_path) > 0)
    
    def _read_temp_file(self) -> Optional[str]:
        """读取临时文件内容"""
        if not self._is_valid_temp_file_path():
            return None
        
        return self._read_file_raw(self.temp_file_path)
    
    def _get_file_content_hash(self, content: Optional[str]) -> Optional[str]:
        """获取文件内容的哈希值"""
        if content is None:
            return None
        
        try:
            if isinstance(content, str):
                # 使用更快的哈希算法，避免大文件性能问题
                return hashlib.md5(content.encode('utf-8')).hexdigest()
            return None
        except Exception:
            return None
    
    def _stop_file_monitor(self) -> None:
        """停止存档文件监控"""
        self.monitor_running = False
        
        # 优雅停止监控线程
        if self.monitor_thread is not None and self.monitor_thread.is_alive():
            try:
                # 设置超时，避免无限等待
                self.monitor_thread.join(timeout=2.0)
                if self.monitor_thread.is_alive():
                    # 线程未在超时内结束，记录警告
                    print("Warning: Monitor thread did not stop gracefully")
            except Exception as e:
                print(f"Error stopping monitor thread: {e}")
            finally:
                self.monitor_thread = None
        
        # 清理临时文件
        self._cleanup_temp_file()
    
    def _cleanup_temp_file(self) -> None:
        """清理临时文件"""
        if not self._is_valid_temp_file_path():
            return
        
        try:
            if os.path.exists(self.temp_file_path):
                # 尝试多次删除，处理文件锁定问题
                for attempt in range(3):
                    try:
                        os.remove(self.temp_file_path)
                        break  # 删除成功，退出循环
                    except (OSError, PermissionError):
                        if attempt < 2:  # 不是最后一次尝试
                            time.sleep(0.1)
                        continue
        except Exception as e:
            # 记录错误但不中断程序
            print(f"临时文件清理异常: {e}")
    
    def _monitor_loop(self):
        """监控循环（在后台线程中运行）"""
        while self.monitor_running:
            try:
                self._check_file_changes()
                time.sleep(0.3) # 轮询间隔
            except Exception as e:
                # 出错继续监控，但记录异常信息
                try:
                    # 记录异常但不停止监控
                    import traceback
                    print(f"监控线程异常: {e}")
                    print(traceback.format_exc())
                    time.sleep(1)  # 异常后稍作等待再继续
                except:
                    # 如果记录也失败，简单等待后继续
                    time.sleep(1)
    
    def _check_file_changes(self):
        """检查文件是否有变动（通过比较真实文件和临时文件）"""
        try:
            # 添加路径有效性检查
            if not self.storage_dir or not isinstance(self.storage_dir, str):
                return
            
            # 使用更安全的文件存在性检查
            def safe_path_exists(path):
                try:
                    return path and isinstance(path, str) and os.path.exists(path)
                except (OSError, TypeError, ValueError, AttributeError):
                    return False
            
            save_file_exists = safe_path_exists(self.save_file_path)
            temp_file_exists = safe_path_exists(self.temp_file_path)
            storage_dir_exists = safe_path_exists(self.storage_dir)
            
            # 如果两个文件同时消失，检查_storage文件夹是否也消失
            if not save_file_exists and not temp_file_exists:
                if self.storage_dir and not storage_dir_exists:
                    # 文件夹也消失了，则触发弹窗
                    if not self.ab_initio_triggered:
                        self.root.after(0, self._trigger_ab_initio)
                    return
            
            if not save_file_exists:
                return
            
            # 获取当前文件修改时间（用于日志/调试，但不作为跳过检查的依据）
            try:
                current_mtime = os.path.getmtime(self.save_file_path)
            except (OSError, IOError, TypeError, AttributeError):
                current_mtime = 0
            
            # 读取临时文件（应该总是成功，因为是我们自己创建的）
            temp_content = self._read_temp_file()
            if temp_content is None:
                # 如果临时文件不存在，重新初始化
                self._initialize_temp_file()
                return
            
            # 尝试读取真实存档文件（可能需要重试，因为可能被游戏锁定）
            save_content = None
            for retry in range(3):
                save_content = self._read_file_raw(self.save_file_path)
                if save_content is not None:
                    break
                time.sleep(0.1)
            
            # 如果读取失败，跳过本次检查（下次再试）
            if save_content is None:
                return
            
            # 比较两个文件的内容（始终进行哈希比较，不依赖mtime）
            temp_hash = self._get_file_content_hash(temp_content)
            save_hash = self._get_file_content_hash(save_content)
            
            # 如果内容不同，说明文件有变动
            if temp_hash is not None and save_hash is not None and temp_hash != save_hash:
                # 解析两个文件的数据并比较差异
                try:
                    # 解析临时文件数据
                    temp_data = self._parse_save_content(temp_content)
                    # 解析真实文件数据
                    save_data = self._parse_save_content(save_content)
                    
                    if temp_data is not None and save_data is not None:
                        # 直接使用深度比较（更可靠）
                        changes = self._deep_compare_data(temp_data, save_data)
                        
                        if changes and self.toast_enabled:
                            # 使用 after() 安全地更新 UI（tkinter 不是线程安全的）
                            # 使用默认参数避免lambda闭包问题
                            self.root.after(0, lambda c=changes: self._show_change_notification(c))
                        
                        # 无论是否检测到变化，都更新临时文件（因为文件哈希已经不同）
                        self._write_temp_file(save_content)
                    elif temp_data is None or save_data is None:
                        # 如果解析失败，至少更新临时文件内容（避免重复检测）
                        self._write_temp_file(save_content)
                except Exception as e:
                    # 如果解析失败，至少更新临时文件内容
                    self._write_temp_file(save_content)
        except Exception as e:
            # 捕获整个检查过程中的任何异常，防止监控线程崩溃
            try:
                import traceback
                print(f"文件变化检查异常: {e}")
                print(traceback.format_exc())
            except:
                pass
    
    def _parse_save_content(self, content):
        """解析存档文件内容为JSON对象"""
        if not content:
            return None
        
        try:
            unquoted = urllib.parse.unquote(content)
            data = json.loads(unquoted)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        return None
    
    def _trigger_ab_initio(self):
        """触发AB INITIO事件：显示红色toast并将应用变为乱码"""
        if self.ab_initio_triggered:
            return
        
        self.ab_initio_triggered = True
        
        toast_message = "AB INITIO"
        toast = Toast(
            self.root,
            toast_message,
            duration=30000,  # 显示30秒
            fade_in=200,
            fade_out=200
        )
        toast.message_text.config(state="normal")
        toast.message_text.delete("1.0", "end")
        toast.message_text.tag_configure("ab_initio_blue", foreground="#00bfff", font=get_cjk_font(12, "bold"))
        toast.message_text.insert("1.0", toast_message, "ab_initio_blue")
        toast.message_text.config(state="disabled")
        
        self._corrupt_all_text()
    
    def _generate_random_gibberish(self, original_text):
        """动态生成随机乱码文本（英文、中文、日文字符混合）"""
        if not original_text:
            return original_text
        
        # 定义字符集：英文、中文、日文
        english_chars = string.ascii_letters + string.digits + string.punctuation + " "
        chinese_chars = "".join([chr(i) for i in range(0x4e00, 0x9fff)])  # 常用汉字范围
        japanese_chars = "".join([chr(i) for i in range(0x3040, 0x309f)]) + "".join([chr(i) for i in range(0x30a0, 0x30ff)])  # 平假名和片假名
        
        # 混合字符集
        all_chars = english_chars + chinese_chars + japanese_chars
        
        # 生成与原文本长度相同的随机乱码
        result = []
        for char in original_text:
            if char.isspace():
                # 保留空格
                result.append(char)
            else:
                result.append(random.choice(all_chars))
        
        return ''.join(result)
    
    def _corrupt_all_text(self):
        """将整个应用的所有文本永久性变为随机乱码"""
        # 备份/还原相关的翻译键，不进行乱码处理
        backup_restore_keys = {
            "backup_restore_tab", "backup_button", "restore_button",
            "backup_confirm_title", "backup_confirm_text", "backup_success_title",
            "backup_success_text", "restore_confirm_title", "restore_confirm_text",
            "restore_missing_files_title", "restore_missing_files_text", "restore_success",
            "backup_list_title", "backup_timestamp", "backup_filename", "backup_size",
            "backup_status", "no_info_file", "backup_estimate_failed", "backup_failed",
            "restore_failed", "delete_backup_button", "delete_backup_confirm_title",
            "delete_backup_confirm_text", "delete_backup_success", "delete_backup_failed",
            "rename_backup_button", "rename_backup_title", "rename_backup_prompt",
            "rename_backup_empty", "rename_backup_invalid_chars", "rename_backup_success",
            "rename_backup_failed", "yes_button", "no_button"
        }
        
        for lang in self.translations:
            for key in self.translations[lang]:
                # 跳过备份/还原相关的翻译键
                if key not in backup_restore_keys:
                    original_text = self.translations[lang][key]
                    self.translations[lang][key] = self._generate_random_gibberish(original_text)
        
        self.update_ui_texts()
        
        self._corrupt_widget_texts(self.root)
    
    def _corrupt_widget_texts(self, widget):
        """递归更新widget及其子widget的文本为乱码"""
        try:
            # 跳过备份/还原tab，不对其进行乱码处理
            if widget == self.backup_restore_frame:
                return
            
            # 获取widget类型
            widget_type = widget.winfo_class()
            
            # 根据widget类型更新文本
            if widget_type == "Label" or widget_type == "TLabel":
                try:
                    current_text = widget.cget("text")
                    if current_text:
                        widget.config(text=self._generate_random_gibberish(current_text))
                except:
                    pass
            elif widget_type == "Button" or widget_type == "TButton":
                try:
                    current_text = widget.cget("text")
                    if current_text:
                        widget.config(text=self._generate_random_gibberish(current_text))
                except:
                    pass
            elif widget_type == "Menu":
                # Menu需要特殊处理
                try:
                    menu_items = widget.index(tk.END)
                    if menu_items is not None:
                        for i in range(menu_items + 1):
                            try:
                                label = widget.entrycget(i, "label")
                                if label:
                                    widget.entryconfig(i, label=self._generate_random_gibberish(label))
                            except:
                                pass
                except:
                    pass
            elif widget_type == "Treeview":
                # Treeview的列标题
                try:
                    columns = widget.cget("columns")
                    if columns:
                        for col in columns:
                            try:
                                heading_info = widget.heading(col)
                                if heading_info:
                                    heading_text = heading_info.get("text", "")
                                    if heading_text:
                                        widget.heading(col, text=self._generate_random_gibberish(heading_text))
                            except:
                                pass
                    # 也处理#0列
                    try:
                        heading_info = widget.heading("#0")
                        if heading_info:
                            heading_text = heading_info.get("text", "")
                            if heading_text:
                                widget.heading("#0", text=self._generate_random_gibberish(heading_text))
                    except:
                        pass
                except:
                    pass
            
            # 递归处理子widget
            for child in widget.winfo_children():
                self._corrupt_widget_texts(child)
        except:
            pass
    
    def _load_save_file(self) -> Optional[Dict[str, Any]]:
        """加载存档文件（处理文件锁定问题）"""
        if not self._is_valid_file_path(self.save_file_path):
            return None
        
        # 尝试多种读取策略
        read_strategies = [
            self._read_save_file_direct,
            self._read_save_file_binary,
            self._read_save_file_copy
        ]
        
        for strategy in read_strategies:
            try:
                encoded = strategy()
                if encoded:
                    return self._parse_encoded_content(encoded)
            except Exception:
                continue
        
        return None
    
    def _read_save_file_direct(self) -> Optional[str]:
        """直接读取存档文件"""
        try:
            with open(self.save_file_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except (IOError, OSError, PermissionError, UnicodeDecodeError):
            return None
    
    def _read_save_file_binary(self) -> Optional[str]:
        """以二进制模式读取存档文件"""
        try:
            with open(self.save_file_path, 'rb') as f:
                raw_data = f.read()
            return raw_data.decode('utf-8', errors='ignore').strip()
        except (IOError, OSError, PermissionError, UnicodeDecodeError):
            return None
    
    def _read_save_file_copy(self) -> Optional[str]:
        """通过创建副本读取存档文件（Windows特有）"""
        if platform.system() != "Windows":
            return None
        
        try:
            # 创建临时副本
            temp_fd, temp_path = tempfile.mkstemp(suffix='.sav')
            try:
                os.close(temp_fd)
                shutil.copy2(self.save_file_path, temp_path)
                
                with open(temp_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
                    
            finally:
                # 清理临时文件
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
        except Exception:
            return None
    
    def _parse_encoded_content(self, encoded: str) -> Optional[Dict[str, Any]]:
        """解析编码后的内容"""
        if not encoded:
            return None
        
        try:
            unquoted = urllib.parse.unquote(encoded)
            data = json.loads(unquoted)
            
            if isinstance(data, dict):
                return data
            return None
        except (json.JSONDecodeError, ValueError, TypeError):
            return None
    
    def _values_equal(self, old_val: Any, new_val: Any) -> bool:
        """比较两个值是否相等（处理类型转换问题）"""
        # None值处理
        if old_val is None and new_val is None:
            return True
        if old_val is None or new_val is None:
            return False
        
        # 类型相同，直接比较
        if type(old_val) == type(new_val):
            return self._compare_same_type(old_val, new_val)
        
        # 处理数字类型比较
        if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
            return self._compare_numbers(old_val, new_val)
        
        # 处理布尔值比较
        if isinstance(old_val, bool) and isinstance(new_val, (int, float)):
            return old_val == (new_val != 0)
        if isinstance(new_val, bool) and isinstance(old_val, (int, float)):
            return new_val == (old_val != 0)
        
        # 处理字符串比较
        if isinstance(old_val, str) and isinstance(new_val, str):
            return old_val.strip() == new_val.strip()
        
        # 其他情况，转换为字符串比较（排除复杂类型）
        if not isinstance(old_val, (dict, list)) and not isinstance(new_val, (dict, list)):
            return str(old_val) == str(new_val)
        
        return False
    
    def _compare_same_type(self, old_val: Any, new_val: Any) -> bool:
        """比较相同类型的值"""
        if isinstance(old_val, (list, dict)):
            return old_val == new_val
        return old_val == new_val
    
    def _compare_numbers(self, old_val: Union[int, float], new_val: Union[int, float]) -> bool:
        """比较数字值"""
        # 排除布尔值
        if isinstance(old_val, bool) or isinstance(new_val, bool):
            return False
        
        # 整数比较
        if isinstance(old_val, int) and isinstance(new_val, int):
            return old_val == new_val
        
        # 浮点数比较
        old_float = float(old_val)
        new_float = float(new_val)
        
        # 检查是否为整数值
        old_is_int = isinstance(old_val, int) or (isinstance(old_val, float) and old_val.is_integer())
        new_is_int = isinstance(new_val, int) or (isinstance(new_val, float) and new_val.is_integer())
        
        if old_is_int and new_is_int:
            return int(old_float) == int(new_float)
        
        # 浮点数比较（带容差）
        return abs(old_float - new_float) < 1e-10
    
    def _deep_compare_data(self, old_data, new_data, prefix=""):
        """深度比较数据，找出所有差异（使用严格比较）"""
        changes = []
        
        # 需要忽略的字段（这些字段变化频繁但不重要）
        # 根据toast_ignore_record设置解析忽略变量列表
        ignored_vars = set()
        if self.toast_ignore_record and self.toast_ignore_record.strip():
            # 解析逗号分割的字符串，去除空格并过滤空字符串
            ignored_vars = {var.strip() for var in self.toast_ignore_record.split(",") if var.strip()}
        
        # 确保都是字典
        if not isinstance(old_data, dict):
            old_data = {}
        if not isinstance(new_data, dict):
            new_data = {}
        
        # 比较所有字段
        all_keys = set(old_data.keys()) | set(new_data.keys())
        
        for key in all_keys:
            full_key = f"{prefix}.{key}" if prefix else key
            
            # 1. 检查顶层key是否在忽略列表中（精确匹配）
            # 2. 检查完整路径是否在忽略列表中（精确匹配）
            # 3. 检查完整路径是否以某个忽略变量开头（用于忽略整个子树，如"record"会忽略"record.xxx"）
            should_ignore = False
            if ignored_vars:
                if key in ignored_vars or full_key in ignored_vars:
                    should_ignore = True
                else:
                    # 检查full_key是否以某个忽略变量开头（用于忽略整个子树）
                    for ignored_var in ignored_vars:
                        if full_key == ignored_var or full_key.startswith(ignored_var + "."):
                            should_ignore = True
                            break
            
            # 跳过忽略的字段
            if should_ignore:
                continue
            
            old_value = old_data.get(key)
            new_value = new_data.get(key)
            
            # 字段被删除
            if key in old_data and key not in new_data:
                changes.append(f"-{full_key}")
            # 字段被新增
            elif key not in old_data and key in new_data:
                if isinstance(new_value, dict):
                    nested_changes = self._deep_compare_data({}, new_value, full_key)
                    changes.extend(nested_changes)
                else:
                    changes.append(f"+{full_key} = {self._format_value(new_value)}")
            # 字段值发生变化
            else:
                # 先检查值是否相等（使用_values_equal进行智能比较）
                if not self._values_equal(old_value, new_value):
                    if isinstance(old_value, dict) and isinstance(new_value, dict):
                        nested_changes = self._deep_compare_data(old_value, new_value, full_key)
                        changes.extend(nested_changes)
                    elif isinstance(old_value, list) and isinstance(new_value, list):
                        list_changes = self._compare_lists(full_key, old_value, new_value)
                        changes.extend(list_changes)
                    else:
                        # 普通值变化
                        changes.append(f"{full_key} {self._format_value(old_value)}→{self._format_value(new_value)}")
                # 如果值相等但类型不同，也记录变化（可能是游戏写入时的类型变化）
                elif type(old_value) != type(new_value):
                    # 对于数值类型，如果数值相同但类型不同，也记录
                    if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)):
                        if float(old_value) == float(new_value):
                            # 数值相同但类型不同，也记录（比如int(7) vs float(7.0)）
                            changes.append(f"{full_key} {self._format_value(old_value)} ({type(old_value).__name__})→{self._format_value(new_value)} ({type(new_value).__name__})")
        
        return changes
    
    def _compare_save_data(self, old_data, new_data, prefix=""):
        """比较两个存档数据，返回变更列表"""
        changes = []
        
        # 确保都是字典
        if not isinstance(old_data, dict):
            old_data = {}
        if not isinstance(new_data, dict):
            new_data = {}
        
        # 比较所有字段
        all_keys = set(old_data.keys()) | set(new_data.keys())
        
        for key in all_keys:
            # 构建完整键名（支持嵌套）
            full_key = f"{prefix}.{key}" if prefix else key
            
            old_value = old_data.get(key)
            new_value = new_data.get(key)
            
            # 字段被删除
            if key in old_data and key not in new_data:
                changes.append(f"- {full_key}")
            # 字段被新增
            elif key not in old_data and key in new_data:
                if isinstance(new_value, dict):
                    # 如果是字典，递归比较
                    nested_changes = self._compare_save_data({}, new_value, full_key)
                    changes.extend(nested_changes)
                else:
                    changes.append(f"+ {full_key} = {self._format_value(new_value)}")
            # 字段值发生变化
            else:
                # 先使用严格比较（直接 !=）
                if old_value != new_value:
                    # 如果是字典，递归比较
                    if isinstance(old_value, dict) and isinstance(new_value, dict):
                        nested_changes = self._compare_save_data(old_value, new_value, full_key)
                        changes.extend(nested_changes)
                    # 如果是列表，比较列表差异
                    elif isinstance(old_value, list) and isinstance(new_value, list):
                        list_changes = self._compare_lists(full_key, old_value, new_value)
                        changes.extend(list_changes)
                    else:
                        # 普通值变化（使用严格比较，确保所有变化都能检测到）
                        changes.append(f"{full_key} {self._format_value(old_value)}→{self._format_value(new_value)}")
                # 如果严格比较相等，但类型不同，也记录变化（可能是游戏写入时的类型变化）
                elif type(old_value) != type(new_value):
                    # 对于数字类型，如果数值相同但类型不同，也记录
                    if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)):
                        if float(old_value) == float(new_value):
                            # 数值相同但类型不同，也记录（比如int(7) vs float(7.0)）
                            changes.append(f"{full_key} {self._format_value(old_value)} ({type(old_value).__name__})→{self._format_value(new_value)} ({type(new_value).__name__})")
        
        return changes
    
    def _compare_lists(self, key, old_list, new_list):
        """比较两个列表的差异（支持包含不可哈希元素的列表）"""
        changes = []
        
        # 将元素转换为可比较的形式（用于处理嵌套列表/字典）
        def make_comparable(item):
            """将元素转换为可用于比较的形式"""
            if isinstance(item, (list, dict)):
                return json.dumps(item, sort_keys=True, ensure_ascii=False)
            return item
        
        def find_item_in_list(item, lst):
            """检查元素是否在列表中（支持复杂类型）"""
            item_cmp = make_comparable(item)
            for other in lst:
                if make_comparable(other) == item_cmp:
                    return True
            return False
        
        # 查找添加的元素（在new_list中但不在old_list中）
        for item in new_list:
            if not find_item_in_list(item, old_list):
                changes.append(f"{key}.append({self._format_value(item)})")
        
        # 查找移除的元素（在old_list中但不在new_list中）
        for item in old_list:
            if not find_item_in_list(item, new_list):
                changes.append(f"{key}.remove({self._format_value(item)})")
        
        return changes
    
    def _format_value(self, value):
        """格式化值用于显示"""
        if isinstance(value, (dict, list)):
            return str(value)
        elif isinstance(value, str):
            return f'"{value}"'
        elif isinstance(value, float):
            # 如果是浮点数，检查是否为整数
            if value.is_integer():
                return str(int(value))
            return str(value)
        elif isinstance(value, bool):
            return str(value)
        else:
            return str(value)
    
    def _show_change_notification(self, changes):
        """显示存档文件变动通知（支持合并连续变化）"""
        # 解析变化，区分可合并的和不可合并的
        mergeable_changes = {}  # {变量名: (旧值, 新值)}
        other_changes = []
        
        for change in changes:
            # 检测格式：变量名 旧值→新值
            if "→" in change and not change.startswith("+") and not change.startswith("-"):
                # 尝试解析：变量名 旧值→新值
                arrow_pos = change.find("→")
                # 从箭头往前找空格，确定变量名
                prefix = change[:arrow_pos]
                last_space = prefix.rfind(" ")
                if last_space > 0:
                    var_name = prefix[:last_space].strip()
                    old_val = prefix[last_space+1:].strip()
                    new_val = change[arrow_pos+1:].strip()
                    mergeable_changes[var_name] = (old_val, new_val)
                else:
                    other_changes.append(change)
            else:
                other_changes.append(change)
        
        # 处理可合并的变化
        updated_toasts = set()
        new_changes_for_toast = []
        
        for var_name, (old_val, new_val) in mergeable_changes.items():
            if var_name in self.variable_change_chains:
                # 该变量已有活跃的变化链，尝试追加
                chain_info = self.variable_change_chains[var_name]
                toast = chain_info.get("toast")
                if toast and toast.window.winfo_exists():
                    # Toast 仍然存在，追加变化
                    chain_info["chain"].append(new_val)
                    updated_toasts.add(var_name)
                    # 重置定时器
                    toast.reset_timer()
                else:
                    # Toast 已经消失，创建新的变化链
                    self.variable_change_chains[var_name] = {"chain": [old_val, new_val], "toast": None}
                    new_changes_for_toast.append(f"{var_name} {old_val}→{new_val}")
            else:
                # 新的变量变化
                self.variable_change_chains[var_name] = {"chain": [old_val, new_val], "toast": None}
                new_changes_for_toast.append(f"{var_name} {old_val}→{new_val}")
        
        # 更新已有的toast
        for var_name in updated_toasts:
            chain_info = self.variable_change_chains[var_name]
            chain = chain_info["chain"]
            toast = chain_info["toast"]
            if toast and toast.window.winfo_exists():
                # 重建该toast的消息
                chain_str = "→".join(str(v) for v in chain)
                new_line = f"{var_name} {chain_str}"
                # 获取当前消息，更新对应行
                current_msg = toast.message
                lines = current_msg.split("\n")
                updated_lines = []
                found = False
                for line in lines:
                    if line.startswith(var_name + " ") and "→" in line:
                        updated_lines.append(new_line)
                        found = True
                    else:
                        updated_lines.append(line)
                if not found:
                    updated_lines.append(new_line)
                new_msg = "\n".join(updated_lines)
                toast.update_message(new_msg)
        
        # 如果有新的变化或其他变化，创建新的toast
        all_new_changes = new_changes_for_toast + other_changes
        if all_new_changes:
            # 构建消息
            message_lines = [self.t("sf_sav_changes_notification")]
            message_lines.extend(all_new_changes)
            message = "\n".join(message_lines)
            
            # 创建新的通知
            toast = Toast(
                self.root,
                message,
                duration=15000,  # 显示时间
                fade_in=200,     # 淡入
                fade_out=200     # 淡出
            )
            
            # 将新的toast关联到变量变化链
            for var_name in mergeable_changes:
                if var_name not in updated_toasts:
                    if var_name in self.variable_change_chains:
                        self.variable_change_chains[var_name]["toast"] = toast
            
            # 添加到活跃列表
            self.active_toasts.append(toast)
        
        # 清理已经消失的变化链
        to_remove = []
        for var_name, chain_info in self.variable_change_chains.items():
            toast = chain_info.get("toast")
            if toast and not toast.window.winfo_exists():
                to_remove.append(var_name)
        for var_name in to_remove:
            del self.variable_change_chains[var_name]
    
    def on_closing(self):
        """窗口关闭事件处理"""
        # 停止文件监控（会清理临时文件）
        self._stop_file_monitor()
        # 关闭窗口
        self.root.destroy()
    
    def show_save_analyzer(self):
        """切换到存档分析 tab（保留此方法以兼容菜单，但菜单将被移除）"""
        if not self.storage_dir:
            messagebox.showerror(self.t("error"), self.t("select_dir_hint"))
            return
        
        if self.save_analyzer is None:
            self.init_save_analyzer()
        self.notebook.select(0)
    
    def show_help(self):
        """浏览器打开GitHub页面"""
        webbrowser.open("https://github.com/Hxueit/Devil-Connection-Screenshot-Tool")
    
    def update_ui_texts(self):
        """更新所有UI文本"""
        # 更新窗口标题
        self.root.title(self.t("window_title"))
        
        # 更新Directory菜单
        # 更新菜单项标签
        self.directory_menu.delete(0, tk.END)
        self.directory_menu.add_command(label=self.t("browse_dir"), command=self.select_dir)
        self.directory_menu.add_command(label=self.t("auto_detect_steam"), command=self.auto_detect_steam)
        
        # 更新Notebook tab标签
        try:
            self.notebook.tab(0, text=self.t("save_analyzer_tab"))
            self.notebook.tab(1, text=self.t("screenshot_management_tab"))
            self.notebook.tab(2, text=self.t("backup_restore_tab"))
            self.notebook.tab(3, text=self.t("others_tab"))
        except:
            pass
        
        # 更新所有tab的提示标签文本（只有在widget存在且未被销毁时才更新）
        try:
            if hasattr(self, 'analyzer_hint_label') and self.analyzer_hint_label:
                if self.analyzer_hint_label.winfo_exists():
                    self.analyzer_hint_label.config(text=self.t("select_dir_hint"))
        except:
            pass
        try:
            if hasattr(self, 'screenshot_hint_label') and self.screenshot_hint_label:
                if self.screenshot_hint_label.winfo_exists():
                    self.screenshot_hint_label.config(text=self.t("select_dir_hint"))
        except:
            pass
        try:
            if hasattr(self, 'backup_restore_hint_label') and self.backup_restore_hint_label:
                if self.backup_restore_hint_label.winfo_exists():
                    self.backup_restore_hint_label.config(text=self.t("select_dir_hint"))
        except:
            pass
        try:
            if hasattr(self, 'others_hint_label') and self.others_hint_label:
                if self.others_hint_label.winfo_exists():
                    self.others_hint_label.config(text=self.t("select_dir_hint"))
        except:
            pass
        
        # 更新菜单栏标签 - 必须删除并重新插入才能更新标签
        try:
            # 查找所有Directory菜单的索引（可能有多个旧的）
            indices_to_delete = []
            try:
                menu_count = self.menubar.index(tk.END)
                if menu_count is not None:
                    menu_count = menu_count + 1
                    directory_menu_str = str(self.directory_menu)
                    for i in range(menu_count):
                        try:
                            menu_obj = self.menubar.entrycget(i, "menu")
                            if str(menu_obj) == directory_menu_str:
                                indices_to_delete.append(i)
                        except:
                            continue
            except:
                pass
            
            indices_to_delete.sort(reverse=True)  # 从后往前删除，避免索引变化
            for idx in indices_to_delete:
                try:
                    self.menubar.delete(idx)
                except:
                    pass
            
            # 重新插入Directory菜单到第一个位置
            self.menubar.insert_cascade(0, label=self.t("directory_menu"), menu=self.directory_menu)
        except Exception:
            try:
                self.menubar.entryconfig(0, label=self.t("directory_menu"))
            except:
                pass
        
        # 更新截图管理UI文本（如果已初始化）
        if self.screenshot_manager_ui is not None:
            self.screenshot_manager_ui.update_ui_texts()
        
        # 更新备份/还原界面文本（如果已初始化）
        if hasattr(self, 'backup_button') and self.backup_button:
            self.backup_button.config(text=self.t("backup_button"))
        if hasattr(self, 'backup_list_title') and self.backup_list_title:
            self.backup_list_title.config(text=self.t("backup_list_title"))
        if hasattr(self, 'backup_refresh_button') and self.backup_refresh_button:
            self.backup_refresh_button.config(text=self.t("refresh"))
        if hasattr(self, 'backup_tree') and self.backup_tree:
            self.backup_tree.heading("timestamp", text=self.t("backup_timestamp"))
            self.backup_tree.heading("filename", text=self.t("backup_filename"))
            self.backup_tree.heading("size", text=self.t("backup_size"))
            self.backup_tree.heading("status", text=self.t("backup_status"))
        if hasattr(self, 'restore_button') and self.restore_button:
            self.restore_button.config(text=self.t("restore_button"))
        if hasattr(self, 'delete_backup_button') and self.delete_backup_button:
            self.delete_backup_button.config(text=self.t("delete_backup_button"))
        if hasattr(self, 'rename_backup_button') and self.rename_backup_button:
            self.rename_backup_button.config(text=self.t("rename_backup_button"))
        
        if self.storage_dir and self.screenshot_manager_ui is not None:
            self.screenshot_manager_ui.load_screenshots()
        
        # 更新其他功能标签页文本（如果已初始化）
        if self.others_tab is not None:
            self.others_tab.update_language(self.current_language)

    def hide_success_label(self):
        """隐藏成功信息标签"""
        if self.success_label_timer is not None:
            self.root.after_cancel(self.success_label_timer)
            self.success_label_timer = None
        self.success_label.pack_forget()
    
    def select_dir(self):
        dir_path = filedialog.askdirectory()
        if dir_path:
            # 检查是否以_storage结尾，如果不是则显示警告
            if not (dir_path.endswith('/_storage') or dir_path.endswith('\\_storage')):
                messagebox.showwarning(self.t("warning"), self.t("dir_warning"))
            # 无论是否以_storage结尾，都允许继续
            self.storage_dir = dir_path
            # 隐藏截图管理tab的提示标签
            self.screenshot_hint_label.pack_forget()
            # 初始化截图管理UI
            if self.screenshot_manager_ui is None:
                self.screenshot_manager_ui = ScreenshotManagerUI(
                    self.screenshot_frame, self.root, self.storage_dir,
                    self.translations, self.current_language, self.t
                )
            else:
                self.screenshot_manager_ui.set_storage_dir(self.storage_dir)
                self.screenshot_manager_ui.load_screenshots()
            self.init_save_analyzer()
            self.init_backup_restore()
            self.init_others_tab()
            # 启动文件监控
            self._start_file_monitor()
    
    def get_steam_path(self):
        """从Windows注册表获取Steam主路径，如果不是Windows则使用默认路径"""
        if platform.system() == "Windows" and winreg:
            try:
                # 读取Steam注册表路径
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
                steam_path = winreg.QueryValueEx(key, "InstallPath")[0]
                winreg.CloseKey(key)
                return steam_path
            except:
                # 尝试32位注册表
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam")
                    steam_path = winreg.QueryValueEx(key, "InstallPath")[0]
                    winreg.CloseKey(key)
                    return steam_path
                except:
                    pass
        
        # 非Windows系统或注册表读取失败，使用默认路径
        if platform.system() == "Windows":
            return os.path.expanduser(r"C:\Program Files (x86)\Steam")
        elif platform.system() == "Darwin":  # macOS
            return os.path.expanduser("~/Library/Application Support/Steam")
        else:  # Linux
            return os.path.expanduser("~/.steam/steam")
    
    def parse_libraryfolders_vdf(self, vdf_path):
        """解析libraryfolders.vdf文件，返回所有Steam库路径列表"""
        library_paths = []
        
        if not os.path.exists(vdf_path):
            return library_paths
        
        try:
            with open(vdf_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # VDF文件格式：使用引号和制表符
            # 查找所有 "path" 字段的值
            # 格式类似: "path"		"D:\\SteamLibrary" 或 "path"		"/home/user/SteamLibrary"
            # 支持Windows和Unix路径
            pattern = r'"path"\s+"([^"]+)"'
            matches = re.findall(pattern, content)
            
            for match in matches:
                # 处理转义字符（Windows路径中的双反斜杠）
                path = match.replace('\\\\', '\\').replace('\\/', '/')
                # 规范化路径
                path = os.path.normpath(path)
                if os.path.exists(path):
                    library_paths.append(path)
        except Exception as e:
            pass
        
        return library_paths
    
    def get_steam_libraries(self, steam_path):
        """获取所有Steam库路径"""
        libraries = []
        
        # 添加Steam主目录作为第一个库
        if os.path.exists(steam_path):
            libraries.append(steam_path)
        
        # 读取libraryfolders.vdf
        vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
        additional_libraries = self.parse_libraryfolders_vdf(vdf_path)
        
        # 合并并去重
        for lib in additional_libraries:
            if lib not in libraries:
                libraries.append(lib)
        
        return libraries
    
    def parse_appmanifest_acf(self, acf_path):
        """解析appmanifest_3054820.acf文件，获取installdir字段"""
        if not os.path.exists(acf_path):
            return None
        
        try:
            with open(acf_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 查找 "installdir" 字段
            pattern = r'"installdir"\s+"([^"]+)"'
            match = re.search(pattern, content)
            if match:
                return match.group(1)
        except Exception as e:
            pass
        
        return None
    
    def find_game_directory(self, library_path):
        """在指定的Steam库中查找游戏目录"""
        steamapps_common = os.path.join(library_path, "steamapps", "common")
        
        if not os.path.exists(steamapps_common):
            return None
        
        game_folder_name = "でびるコネクショん"
        game_folder_path = os.path.join(steamapps_common, game_folder_name)
        
        if os.path.exists(game_folder_path) and os.path.isdir(game_folder_path):
            return game_folder_path
        
        # 从appmanifest文件获取安装目录
        appmanifest_path = os.path.join(library_path, "steamapps", "appmanifest_3054820.acf")
        installdir = self.parse_appmanifest_acf(appmanifest_path)
        
        if installdir:
            game_folder_path = os.path.join(steamapps_common, installdir)
            if os.path.exists(game_folder_path) and os.path.isdir(game_folder_path):
                return game_folder_path
        
        return None
    
    def auto_detect_steam_storage(self):
        """自动检测Steam游戏目录的_storage文件夹"""
        # 获取Steam主路径
        steam_path = self.get_steam_path()
        
        if not steam_path or not os.path.exists(steam_path):
            return None
        
        # 获取所有Steam库
        libraries = self.get_steam_libraries(steam_path)
        
        # 在每个库中查找游戏
        for library in libraries:
            game_dir = self.find_game_directory(library)
            if game_dir:
                # 检查_storage目录是否存在
                storage_path = os.path.join(game_dir, "_storage")
                if os.path.exists(storage_path) and os.path.isdir(storage_path):
                    return os.path.abspath(storage_path)
        
        return None
    
    def auto_detect_steam(self):
        """自动检测Steam游戏目录并设置"""
        storage_path = self.auto_detect_steam_storage()
        
        if storage_path:
            self.storage_dir = storage_path
            # 隐藏截图管理tab的提示标签
            self.screenshot_hint_label.pack_forget()
            # 初始化截图管理UI
            if self.screenshot_manager_ui is None:
                self.screenshot_manager_ui = ScreenshotManagerUI(
                    self.screenshot_frame, self.root, self.storage_dir,
                    self.translations, self.current_language, self.t
                )
            else:
                self.screenshot_manager_ui.set_storage_dir(self.storage_dir)
                self.screenshot_manager_ui.load_screenshots(silent=True)
            # 初始化存档分析界面
            self.init_save_analyzer()
            # 初始化备份/还原界面
            self.init_backup_restore()
            # 初始化其他功能标签页
            self.init_others_tab()
            # 启动文件监控
            self._start_file_monitor()
        else:
            messagebox.showinfo(self.t("warning"), self.t("steam_detect_not_found"))

if __name__ == "__main__":
    root = tk.Tk()
    app = SavTool(root)
    root.mainloop()