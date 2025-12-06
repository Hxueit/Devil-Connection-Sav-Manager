import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import os
import json
import urllib.parse
import urllib.request
import urllib.error
import zlib
import threading
import webbrowser
from styles import get_cjk_font, Colors


class OthersTab:
    """其他功能标签页"""
    
    def __init__(self, parent, storage_dir, translations, current_language, main_app):
        """
        初始化其他功能标签页
        
        Args:
            parent: 父容器（Frame）
            storage_dir: 存储目录路径
            translations: 翻译字典
            current_language: 当前语言
            main_app: 主应用实例（用于访问toast相关功能）
        """
        self.parent = parent
        self.storage_dir = storage_dir
        self.translations = translations
        self.current_language = current_language
        self.main_app = main_app
        
        # 从主应用同步默认设置
        if hasattr(main_app, 'toast_enabled'):
            self.toast_enabled = main_app.toast_enabled
        else:
            self.toast_enabled = True  # 默认开启toast
        
        if hasattr(main_app, 'toast_ignore_record'):
            self.toast_ignore_record = main_app.toast_ignore_record
        else:
            self.toast_ignore_record = "record, initialVars"  # 默认不监听的变量（逗号分割）
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI"""
        # 创建主容器
        main_container = tk.Frame(self.parent, bg=Colors.WHITE)
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 创建滚动区域
        canvas = tk.Canvas(main_container, bg=Colors.WHITE, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=Colors.WHITE)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 绑定鼠标滚轮
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 创建按钮容器
        button_frame = tk.Frame(scrollable_frame, bg=Colors.WHITE)
        button_frame.pack(fill="x", pady=10)
        
        # 1. 开启toast功能
        toast_frame = tk.Frame(button_frame, bg=Colors.WHITE)
        toast_frame.pack(fill="x", pady=10)
        
        self.toast_var = tk.BooleanVar(value=self.toast_enabled)
        toast_checkbox = ttk.Checkbutton(
            toast_frame,
            text=self.t("enable_toast"),
            variable=self.toast_var,
            command=self._on_toast_toggle,
            style="TCheckbutton"
        )
        toast_checkbox.pack(anchor="w")
        
        # 2. toast不监听的变量（逗号分割）
        ignore_vars_frame = tk.Frame(button_frame, bg=Colors.WHITE)
        ignore_vars_frame.pack(fill="x", pady=10)
        
        # 标签
        ignore_vars_label = tk.Label(
            ignore_vars_frame,
            text=self.t("toast_ignore_vars_label"),
            font=get_cjk_font(10),
            bg=Colors.WHITE,
            anchor="w"
        )
        ignore_vars_label.pack(anchor="w", pady=(0, 5))
        
        # 输入框
        self.ignore_vars_var = tk.StringVar(value=self.toast_ignore_record)
        self.ignore_vars_entry = tk.Entry(
            ignore_vars_frame,
            textvariable=self.ignore_vars_var,
            font=get_cjk_font(10),
            width=50
        )
        self.ignore_vars_entry.pack(fill="x", anchor="w")
        self.ignore_vars_entry.bind("<KeyRelease>", lambda e: self._on_ignore_vars_change())
        
        # 提示文本
        ignore_vars_hint = tk.Label(
            ignore_vars_frame,
            text=self.t("toast_ignore_vars_hint"),
            font=get_cjk_font(9),
            bg=Colors.WHITE,
            fg=Colors.TEXT_SECONDARY,
            anchor="w"
        )
        ignore_vars_hint.pack(anchor="w", pady=(3, 0))
        
        # 根据toast_enabled状态设置输入框的可用性
        self._update_ignore_vars_entry_state()
        
        # 3. 解码并导出tyrano_data.sav
        export_button = ttk.Button(
            button_frame,
            text=self.t("export_tyrano_data"),
            command=self._export_tyrano_data
        )
        export_button.pack(fill="x", pady=10)
        
        # 4. 导入、编码并保存tyrano_data.sav
        import_button = ttk.Button(
            button_frame,
            text=self.t("import_tyrano_data"),
            command=self._import_tyrano_data
        )
        import_button.pack(fill="x", pady=10)
        
        # 5. 检查更新（放在最下面）
        check_update_button = ttk.Button(
            button_frame,
            text=self.t("check_for_updates"),
            command=self._check_for_updates
        )
        check_update_button.pack(fill="x", pady=10)
    
    def t(self, key, **kwargs):
        """翻译函数"""
        text = self.translations[self.current_language].get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text
    
    def _on_toast_toggle(self):
        """toast功能开关回调"""
        self.toast_enabled = self.toast_var.get()
        # 通知主应用更新toast状态
        self.main_app.toast_enabled = self.toast_enabled
        # 更新ignore_vars_entry的状态
        self._update_ignore_vars_entry_state()
    
    def _update_ignore_vars_entry_state(self):
        """更新ignore_vars_entry的可用状态"""
        if hasattr(self, 'ignore_vars_entry'):
            if self.toast_enabled:
                self.ignore_vars_entry.config(state="normal")
            else:
                self.ignore_vars_entry.config(state="disabled")
    
    def _calculate_crc32_with_progress(self, new_data, tyrano_path):
        """带进度条的CRC32计算"""
        # 创建进度条窗口
        progress_window = tk.Toplevel(self.parent)
        progress_window.title(self.t("calculating_crc32"))
        progress_window.geometry("400x120")
        progress_window.transient(self.parent)
        progress_window.grab_set()
        progress_window.resizable(False, False)
        
        # 居中显示
        progress_window.update_idletasks()
        x = (progress_window.winfo_screenwidth() // 2) - (progress_window.winfo_width() // 2)
        y = (progress_window.winfo_screenheight() // 2) - (progress_window.winfo_height() // 2)
        progress_window.geometry(f"+{x}+{y}")
        
        # 创建标签和进度条
        label = tk.Label(
            progress_window,
            text=self.t("calculating_crc32_progress"),
            font=get_cjk_font(10),
            bg=Colors.WHITE
        )
        label.pack(pady=20)
        
        progress_bar = ttk.Progressbar(
            progress_window,
            mode='indeterminate',
            length=300
        )
        progress_bar.pack(pady=10)
        progress_bar.start(10)  # 开始动画
        
        # 结果存储
        result = [None]
        error_occurred = [False]
        calculation_done = [False]
        
        def calculate_crc32():
            """在后台线程中计算CRC32"""
            try:
                # 计算新文件的CRC32
                json_str = json.dumps(new_data, ensure_ascii=False, sort_keys=True)
                new_crc32 = zlib.crc32(json_str.encode('utf-8')) & 0xffffffff
                
                # 如果现有文件存在，计算其CRC32
                existing_crc32 = None
                if os.path.exists(tyrano_path):
                    try:
                        with open(tyrano_path, 'r', encoding='utf-8') as f:
                            encoded = f.read().strip()
                        unquoted = urllib.parse.unquote(encoded)
                        existing_data = json.loads(unquoted)
                        existing_json_str = json.dumps(existing_data, ensure_ascii=False, sort_keys=True)
                        existing_crc32 = zlib.crc32(existing_json_str.encode('utf-8')) & 0xffffffff
                    except Exception:
                        # 如果读取现有文件失败，继续流程
                        pass
                
                result[0] = (new_crc32, existing_crc32)
            except Exception as e:
                error_occurred[0] = True
                result[0] = str(e)
            finally:
                calculation_done[0] = True
        
        def check_calculation_done():
            """在主线程中检查计算是否完成"""
            if calculation_done[0]:
                # 计算完成，关闭进度条窗口
                try:
                    progress_bar.stop()
                    progress_window.destroy()
                except:
                    pass
            else:
                # 继续检查
                progress_window.after(50, check_calculation_done)
        
        # 启动后台线程
        thread = threading.Thread(target=calculate_crc32, daemon=True)
        thread.start()
        
        # 开始检查计算是否完成
        progress_window.after(50, check_calculation_done)
        
        # 等待窗口关闭（用户看到进度条）
        progress_window.wait_window()
        
        # 等待线程完成（确保计算完成）
        thread.join(timeout=30)  # 最多等待30秒
        
        # 如果有错误，显示错误信息
        if error_occurred[0]:
            messagebox.showerror(self.t("error"), self.t("crc32_calculation_failed", error=result[0]))
            return None
        
        return result[0]
    
    def _on_ignore_vars_change(self):
        """忽略变量输入框变化回调"""
        self.toast_ignore_record = self.ignore_vars_var.get()
        # 通知主应用更新忽略变量列表
        self.main_app.toast_ignore_record = self.toast_ignore_record
    
    def _export_tyrano_data(self):
        """解码并导出tyrano_data.sav"""
        if not self.storage_dir:
            messagebox.showerror(self.t("error"), self.t("select_dir_hint"))
            return
        
        tyrano_path = os.path.join(self.storage_dir, 'DevilConnection_tyrano_data.sav')
        if not os.path.exists(tyrano_path):
            messagebox.showerror(self.t("error"), self.t("tyrano_file_not_found"))
            return
        
        try:
            # 读取并解码文件
            with open(tyrano_path, 'r', encoding='utf-8') as f:
                encoded = f.read().strip()
            
            unquoted = urllib.parse.unquote(encoded)
            data = json.loads(unquoted)
            
            # 选择保存位置
            file_path = filedialog.asksaveasfilename(
                title=self.t("save_file"),
                defaultextension=".json",
                initialfile="DevilConnection_tyrano_data.json",
                filetypes=[(self.t("json_files"), "*.json"), (self.t("all_files"), "*.*")]
            )
            
            if not file_path:
                return
            
            # 保存JSON文件（使用ensure_ascii=False以支持中文等字符，indent=2使格式更易读）
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            messagebox.showinfo(self.t("success"), self.t("export_tyrano_success", path=file_path))
        
        except Exception as e:
            messagebox.showerror(self.t("error"), self.t("export_tyrano_failed", error=str(e)))
    
    def _import_tyrano_data(self):
        """导入、编码并保存tyrano_data.sav"""
        if not self.storage_dir:
            messagebox.showerror(self.t("error"), self.t("select_dir_hint"))
            return
        
        tyrano_path = os.path.join(self.storage_dir, 'DevilConnection_tyrano_data.sav')
        
        # 先选择JSON文件
        file_path = filedialog.askopenfilename(
            title=self.t("select_json_file"),
            filetypes=[(self.t("json_files"), "*.json"), (self.t("all_files"), "*.*")]
        )
        
        if not file_path:
            return
        
        # 检测文件是否是JSON格式
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            messagebox.showerror(
                self.t("error"),
                self.t("json_format_error_detail", error=str(e))
            )
            return
        except Exception as e:
            messagebox.showerror(self.t("error"), self.t("import_tyrano_failed", error=str(e)))
            return
        
        # 第一次确认（包含CRC32校验）
        # 显示进度条并计算CRC32
        result = self._calculate_crc32_with_progress(data, tyrano_path)
        if result is None:
            # 用户取消了操作或发生错误
            return
        
        new_crc32, existing_crc32 = result
        
        # 如果CRC32相同，提示无差异
        if existing_crc32 is not None and new_crc32 == existing_crc32:
            messagebox.showinfo(self.t("info"), self.t("tyrano_no_changes"))
            return
        
        # 第一次确认
        if not messagebox.askyesno(
            self.t("warning"),
            self.t("import_tyrano_confirm_1")
        ):
            return
        
        # 第二次确认
        if not messagebox.askyesno(
            self.t("warning"),
            self.t("import_tyrano_confirm_2")
        ):
            return
        
        try:
            # 编码并保存
            json_str = json.dumps(data, ensure_ascii=False)
            encoded = urllib.parse.quote(json_str)
            
            with open(tyrano_path, 'w', encoding='utf-8') as f:
                f.write(encoded)
            
            messagebox.showinfo(self.t("success"), self.t("import_tyrano_success"))
        
        except Exception as e:
            messagebox.showerror(self.t("error"), self.t("import_tyrano_failed", error=str(e)))
    
    def set_storage_dir(self, storage_dir):
        """设置存储目录"""
        self.storage_dir = storage_dir
    
    def _check_for_updates(self):
        """检查GitHub更新"""
        # 在后台线程中执行，避免阻塞UI
        threading.Thread(target=self._check_updates_thread, daemon=True).start()
    
    def _check_updates_thread(self):
        """在后台线程中检查更新"""
        try:
            from backup_restore import VERSION
            
            # 访问GitHub API
            url = "https://api.github.com/repos/Hxueit/Devil-Connection-Sav-Manager/releases/latest"
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Devil-Connection-Sav-Manager')
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                latest_version = data['tag_name']  # 已经是 "vX.Y.Z" 格式
                release_url = data['html_url']
                published_at = data.get('published_at', '')
                
                # 格式化发布时间
                release_date = ""
                if published_at:
                    try:
                        # GitHub API 返回的是 ISO 8601 格式e.g.: "2024-01-01T12:00:00Z"
                        # 提取日期和时间部分
                        date_str = published_at.split('T')[0]  # 获取日期部分 "2024-01-01"
                        time_str = published_at.split('T')[1] if 'T' in published_at else "00:00:00"
                        # 移除时区标识（Z, +00:00等）和毫秒
                        time_str = time_str.split('Z')[0].split('+')[0].split('-')[0].split('.')[0]
                        release_date = f"{date_str} {time_str}"
                    except Exception:
                        # 如果解析失败，至少显示日期部分
                        release_date = published_at[:10] if len(published_at) >= 10 else published_at
                
                # 比较版本
                if self._compare_versions(VERSION, latest_version) < 0:
                    # 有新版本
                    self.parent.after(0, lambda: self._show_update_available(
                        VERSION, latest_version, release_url
                    ))
                else:
                    # 已是最新版本
                    self.parent.after(0, lambda: self._show_no_update(
                        VERSION, latest_version, release_date
                    ))
        except urllib.error.URLError as e:
            self.parent.after(0, lambda: messagebox.showerror(
                self.t("error"), 
                self.t("update_check_failed", error=f"网络错误: {str(e)}")
            ))
        except Exception as e:
            self.parent.after(0, lambda: messagebox.showerror(
                self.t("error"), 
                self.t("update_check_failed", error=str(e))
            ))
    
    def _compare_versions(self, v1, v2):
        """比较版本号，返回-1/0/1
        -1: v1 < v2
        0: v1 == v2
        1: v1 > v2
        """
        # 移除 'v' 前缀（如果有）
        v1_clean = v1.lstrip('v')
        v2_clean = v2.lstrip('v')
        
        # 分割版本号
        try:
            parts1 = [int(x) for x in v1_clean.split('.')]
            parts2 = [int(x) for x in v2_clean.split('.')]
        except ValueError:
            # 如果版本号格式不正确，使用字符串比较
            return -1 if v1_clean < v2_clean else (1 if v1_clean > v2_clean else 0)
        
        # 比较每个部分
        max_len = max(len(parts1), len(parts2))
        parts1.extend([0] * (max_len - len(parts1)))
        parts2.extend([0] * (max_len - len(parts2)))
        
        for p1, p2 in zip(parts1, parts2):
            if p1 < p2:
                return -1
            elif p1 > p2:
                return 1
        return 0
    
    def _show_no_update(self, current, latest, release_date):
        """显示无更新对话框（显示详细信息）"""
        msg = self.t("already_latest_version", version=current)
        msg += f"\n\n{self.t('latest_version_info')}: {latest}"
        if release_date:
            msg += f"\n{self.t('release_date')}: {release_date}"
        
        messagebox.showinfo(self.t("no_update"), msg)
    
    def _show_update_available(self, current, latest, url):
        """显示更新可用对话框"""
        msg = self.t("update_available", current=current, latest=latest)
        
        result = messagebox.askyesno(
            self.t("update_available_title"), 
            msg
        )
        if result:
            webbrowser.open(url)
    
    def update_language(self, language):
        """更新语言"""
        self.current_language = language
        # 重新创建UI
        for widget in self.parent.winfo_children():
            widget.destroy()
        self._init_ui()

