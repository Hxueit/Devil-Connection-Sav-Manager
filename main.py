import tkinter as tk
from tkinter import filedialog, messagebox, Listbox, Scrollbar, Toplevel, Entry, Button, Label
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
import sv_ttk
import locale
from translations import TRANSLATIONS

class SavTool:
    def __init__(self, root):
        self.root = root
        self.translations = TRANSLATIONS
        self.current_language = self.detect_system_language()
        self.root.title(self.t("window_title"))
        self.root.geometry("800x550")
        
        # 应用 sun valley 亮色主题
        sv_ttk.set_theme("light")

        # 创建菜单栏
        self.menubar = tk.Menu(root)
        root.config(menu=self.menubar)
        
        # Directory 菜单（软编码，根据语言决定）
        self.directory_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label=self.t("directory_menu"), menu=self.directory_menu)
        self.directory_menu.add_command(label=self.t("browse_dir"), command=self.select_dir)
        
        # Language 菜单
        self.language_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Language", menu=self.language_menu)
        self.language_var = tk.StringVar(value=self.current_language)
        self.language_menu.add_radiobutton(label="中文", variable=self.language_var, 
                                           value="zh_CN", command=lambda: self.change_language("zh_CN"))
        self.language_menu.add_radiobutton(label="English", variable=self.language_var, 
                                          value="en_US", command=lambda: self.change_language("en_US"))
        
        # Help 菜单
        help_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Help", command=self.show_help)

        # 提示标签（当没有选择目录时显示）
        self.hint_label = tk.Label(root, text=self.t("select_dir_hint"), 
                                   fg="#D554BC", font=("Arial", 10))
        self.hint_label.pack(pady=10)

        # 截图列表
        list_header_frame = tk.Frame(root)
        list_header_frame.pack(pady=5, fill="x")
        list_header_frame.columnconfigure(0, weight=1)  
        list_header_frame.columnconfigure(2, weight=1)  
        
        left_spacer = tk.Frame(list_header_frame)
        left_spacer.grid(row=0, column=0, sticky="ew")
        
        # 左侧：标题（全选复选框会在Treeview的header中）
        left_header = tk.Frame(list_header_frame)
        left_header.grid(row=0, column=1)
        self.list_label = ttk.Label(left_header, text=self.t("screenshot_list"))
        self.list_label.pack(side="left", padx=5)
        
        # 右侧区域
        right_area = tk.Frame(list_header_frame)
        right_area.grid(row=0, column=2, sticky="ew")
        right_area.columnconfigure(0, weight=1) 
        
        right_spacer = tk.Frame(right_area)
        right_spacer.grid(row=0, column=0, sticky="ew")
        
        # 右侧按钮区域
        button_container = tk.Frame(right_area)
        button_container.grid(row=0, column=1, sticky="e")
        ttk.Button(button_container, text=self.t("refresh"), command=self.load_screenshots, width=3).pack(side="left", padx=2)
        self.sort_asc_button = ttk.Button(button_container, text=self.t("sort_asc"), command=self.sort_ascending)
        self.sort_asc_button.pack(side="left", padx=2)
        self.sort_desc_button = ttk.Button(button_container, text=self.t("sort_desc"), command=self.sort_descending)
        self.sort_desc_button.pack(side="left", padx=2)
        
        # 创建包含预览和列表的容器
        list_frame = tk.Frame(root)
        list_frame.pack(pady=5)
        
        # 预览区域（左侧）
        preview_frame = tk.Frame(list_frame)
        preview_frame.pack(side="left", padx=5)
        self.preview_label_text = ttk.Label(preview_frame, text=self.t("preview"), font=("Arial", 10))
        self.preview_label_text.pack()

        # 限制预览Label的大小
        preview_container = tk.Frame(preview_frame, width=160, height=120, bg="lightgray", relief="sunken")
        preview_container.pack()
        preview_container.pack_propagate(False) 
        self.preview_label = Label(preview_container, bg="lightgray")
        self.preview_label.pack(fill="both", expand=True)
        self.preview_photo = None
        
        # 导出图片按钮（初始隐藏）
        self.export_button = ttk.Button(preview_frame, text=self.t("export_image"), command=self.export_image)
        self.export_button.pack(pady=5)
        self.export_button.pack_forget()
        
        # 批量导出图片按钮（初始隐藏）
        self.batch_export_button = ttk.Button(preview_frame, text=self.t("batch_export"), command=self.batch_export_images)
        self.batch_export_button.pack(pady=5)
        self.batch_export_button.pack_forget() 
        
        # 列表区域（右侧）
        list_right_frame = tk.Frame(list_frame)
        list_right_frame.pack(side="right")
        
        # 使用Treeview替代Listbox，支持复选框
        tree_frame = tk.Frame(list_right_frame)
        tree_frame.pack(side="left", fill="both", expand=True)
        
        scrollbar = Scrollbar(tree_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        
        # 使用两列：select列用于复选框，info列用于信息
        self.tree = ttk.Treeview(tree_frame, columns=("select", "info"), show="headings", height=15)
        # 隐藏#0列（tree列）
        self.tree.heading("#0", text="", anchor="w")
        self.tree.column("#0", width=0, stretch=False, minwidth=0)
        
        # 复选框列（标题是全选复选框）
        self.tree.heading("select", text="☐", anchor="center", command=self.toggle_select_all)
        self.tree.column("select", width=40, stretch=False, anchor="center")
        
        # 信息列
        self.tree.heading("info", text=self.t("list_header"), anchor="w")
        self.tree.column("info", width=600, stretch=True)
        
        # 配置tag样式用于显示带颜色的箭头指示器，使用tag_configure来设置不同tag的颜色
        self.tree.tag_configure("DragIndicatorUp", foreground="#85A9A5")
        self.tree.tag_configure("DragIndicatorDown", foreground="#D06CAA")
        self.tree.tag_configure("NewIndicator", foreground="#FED491")
        self.tree.tag_configure("ReplaceIndicator", foreground="#BDC9B2")
        
        scrollbar.config(command=self.tree.yview)
        self.tree.config(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        
        # 存储复选框状态 {item_id: BooleanVar}
        self.checkbox_vars = {}
        
        # 绑定选择事件（用于预览）
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        
        # 拖拽相关变量
        self.drag_start_item = None
        self.drag_start_y = None
        self.is_dragging = False
        
        # 箭头指示器相关变量
        self.drag_indicators = []  # 存储当前显示的指示器信息 [(item_id, original_text, after_id), ...]
        
        # 新截图和替换截图的标记相关变量
        self.status_indicators = []  # 存储当前显示的状态指示器信息 [(item_id, original_text, after_id, indicator_type), ...]
        
        # 绑定事件：统一处理点击事件，先检查复选框，再处理拖拽
        self.tree.bind('<Button-1>', self.on_button1_click)
        self.tree.bind('<B1-Motion>', self.on_drag_motion)
        self.tree.bind('<ButtonRelease-1>', self.on_drag_end)

        # 操作按钮
        button_frame = ttk.Frame(root)
        button_frame.pack(pady=5)
        self.add_button = ttk.Button(button_frame, text=self.t("add_new"), command=self.add_new)
        self.add_button.pack(side='left', padx=5)
        self.replace_button = ttk.Button(button_frame, text=self.t("replace_selected"), command=self.replace_selected)
        self.replace_button.pack(side='left', padx=5)
        self.delete_button = ttk.Button(button_frame, text=self.t("delete_selected"), command=self.delete_selected)
        self.delete_button.pack(side='left', padx=5)

        self.storage_dir = None
        self.ids_data = []
        self.all_ids_data = []
        self.sav_pairs = {}  # {id: (main_sav, thumb_sav)}
    
    def detect_system_language(self):
        """检测系统语言并返回支持的语言代码"""
        try:
            # 尝试获取当前locale
            system_locale, _ = locale.getlocale()
            
            # 如果失败，尝试从环境变量获取
            if not system_locale:
                system_locale = os.environ.get('LANG') or os.environ.get('LC_ALL')
            
            # 如果还是失败，尝试获取系统默认locale（兼容旧方法）
            if not system_locale:
                try:
                    # 尝试设置默认locale然后获取
                    locale.setlocale(locale.LC_ALL, '')
                    system_locale, _ = locale.getlocale()
                except:
                    pass
            
            if system_locale:
                # 转换为小写
                locale_lower = system_locale.lower()
                
                # 检查是否是中文（支持多种中文locale格式：zh_CN, zh_TW, zh_HK等）
                if locale_lower.startswith('zh'):
                    return "zh_CN"
                # 其他语言支持暂无
            
            # 如果检测不到，失败，或不在支持列表中，默认英语
            return "en_US"
        except Exception:
            return "en_US"
    
    def t(self, key, **kwargs):
        """翻译函数，支持格式化字符串"""
        text = self.translations[self.current_language].get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text
    
    def change_language(self, lang):
        """切换语言"""
        self.current_language = lang
        self.language_var.set(lang)  # 更新菜单栏中的语言选项状态
        self.update_ui_texts()
        # 注意：菜单栏是硬编码的，不需要更新文本
    
    def ask_yesno(self, title, message, icon='question'):
        """自定义确认对话框，使用翻译的按钮文本"""
        popup = Toplevel(self.root)
        popup.title(title)
        popup.geometry("400x150")
        popup.transient(self.root)
        popup.grab_set()
        
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
    
    def show_help(self):
        """显示帮助窗口，展示README.md内容"""
        help_window = Toplevel(self.root)
        help_window.title("Help")
        help_window.geometry("800x600")
        
        # 创建滚动文本框
        text_frame = tk.Frame(help_window)
        text_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        scrollbar = Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")
        
        text_widget = tk.Text(text_frame, wrap="word", yscrollcommand=scrollbar.set, 
                             font=("Consolas", 10), bg="white", fg="black")
        text_widget.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=text_widget.yview)
        
        # 读取并显示README.md
        try:
            # 获取项目根目录
            script_dir = os.path.dirname(os.path.abspath(__file__))
            readme_path = os.path.join(script_dir, "README.md")
            if os.path.exists(readme_path):
                with open(readme_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                text_widget.insert("1.0", content)
            else:
                text_widget.insert("1.0", "README.md file not found.")
        except Exception as e:
            text_widget.insert("1.0", f"Error reading README.md: {str(e)}")
        
        text_widget.config(state="disabled")  # 设置为只读
        
        # 关闭按钮
        button_frame = tk.Frame(help_window)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="Close", command=help_window.destroy).pack()
    
    def update_ui_texts(self):
        """更新所有UI文本"""
        # 更新窗口标题
        self.root.title(self.t("window_title"))
        
        # 更新Directory菜单
        # 更新菜单项标签
        self.directory_menu.delete(0, tk.END)
        self.directory_menu.add_command(label=self.t("browse_dir"), command=self.select_dir)
        # 更新菜单栏标签 - 必须删除并重新插入才能更新标签
        try:
            # 查找所有Directory菜单的索引（可能有多个旧的）
            indices_to_delete = []
            try:
                menu_count = self.menubar.index(tk.END)
                if menu_count is not None:
                    menu_count = menu_count + 1  # index返回的是最后一个索引，+1得到数量
                    # 遍历所有菜单项，找到所有Directory菜单
                    for i in range(menu_count):
                        try:
                            # 检查这个菜单项是否是我们要找的Directory菜单
                            menu_obj = self.menubar.entrycget(i, "menu")
                            # 比较菜单对象的字符串表示
                            if str(menu_obj) == str(self.directory_menu):
                                indices_to_delete.append(i)
                        except:
                            continue
            except:
                pass
            
            # 从后往前删除，避免索引变化的问题
            indices_to_delete.sort(reverse=True)
            for idx in indices_to_delete:
                try:
                    self.menubar.delete(idx)
                except:
                    pass
            
            # 重新插入Directory菜单到第一个位置
            self.menubar.insert_cascade(0, label=self.t("directory_menu"), menu=self.directory_menu)
        except Exception as e:
            # 如果失败，尝试entryconfig
            try:
                self.menubar.entryconfig(0, label=self.t("directory_menu"))
            except:
                pass
        
        # 更新提示标签
        self.hint_label.config(text=self.t("select_dir_hint"))
        # 根据是否选择目录来显示/隐藏提示
        if self.storage_dir:
            self.hint_label.pack_forget()
        else:
            self.hint_label.pack(pady=10)
        
        # 更新列表相关
        self.list_label.config(text=self.t("screenshot_list"))
        self.preview_label_text.config(text=self.t("preview"))
        self.tree.heading("info", text=self.t("list_header"))
        
        # 更新按钮
        self.sort_asc_button.config(text=self.t("sort_asc"))
        self.sort_desc_button.config(text=self.t("sort_desc"))
        self.add_button.config(text=self.t("add_new"))
        self.replace_button.config(text=self.t("replace_selected"))
        self.delete_button.config(text=self.t("delete_selected"))
        self.export_button.config(text=self.t("export_image"))
        self.batch_export_button.config(text=self.t("batch_export"))
        
        # 重新加载列表以更新显示文本
        if self.storage_dir:
            self.load_screenshots()

    def select_dir(self):
        dir_path = filedialog.askdirectory()
        # 支持Windows和Unix路径分隔符
        if dir_path and (dir_path.endswith('/_storage') or dir_path.endswith('\\_storage')):
            self.storage_dir = dir_path
            # 隐藏提示标签
            self.hint_label.pack_forget()
            self.load_screenshots()
            # 更新批量导出按钮状态
            self.update_batch_export_button()
        else:
            messagebox.showerror(self.t("error"), self.t("dir_error"))

    def load_screenshots(self):
        if not self.storage_dir:
            return

        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')

        if not (os.path.exists(ids_path) and os.path.exists(all_ids_path)):
            messagebox.showerror(self.t("error"), self.t("missing_files"))
            return

        # 加载 ids 和 all_ids
        self.ids_data = self.load_and_decode(ids_path)
        self.all_ids_data = self.load_and_decode(all_ids_path)

        # 扫描 sav 对
        self.sav_pairs = {}
        for file in os.listdir(self.storage_dir):
            if file.startswith('DevilConnection_photo_') and file.endswith('.sav'):
                base_name = file.rsplit('.sav', 1)[0] 
                parts = base_name.split('_')
                if len(parts) == 3:  
                    id_str = parts[2]
                    if id_str not in self.sav_pairs:
                        self.sav_pairs[id_str] = [None, None]
                    self.sav_pairs[id_str][0] = file
                elif len(parts) == 4 and parts[3] == 'thumb': 
                    id_str = parts[2]
                    if id_str not in self.sav_pairs:
                        self.sav_pairs[id_str] = [None, None]
                    self.sav_pairs[id_str][1] = file

        # 更新列表
        # 清除所有状态指示器的定时器
        for item_id, original_text, after_id, indicator_type in self.status_indicators:
            try:
                if after_id:
                    self.root.after_cancel(after_id)
            except:
                pass
        self.status_indicators.clear()
        
        # 清除所有项目
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.checkbox_vars.clear()
        
        # 添加复选框和项目
        for item in self.ids_data:
            id_str = item['id']
            date_str = item['date']
            main_file = self.sav_pairs.get(id_str, [None, None])[0] or self.t("missing_main_file")
            display = f"{id_str} - {main_file} - {date_str}"
            
            # 创建复选框变量
            var = tk.BooleanVar()
            var.trace('w', lambda *args, v=var, iid=id_str: self.on_checkbox_change(v, iid))
            
            # 插入Treeview项目（select列显示复选框，info列显示信息）
            item_id = self.tree.insert("", tk.END, text="", values=("", display), tags=(id_str,))
            self.checkbox_vars[item_id] = (var, id_str)
            
            # 更新复选框显示
            self.update_checkbox_display(item_id)
        
        # 更新全选标题显示
        self.update_select_all_header()

    def sort_ascending(self):
        """按时间正序排序"""
        if not self.storage_dir:
            messagebox.showerror(self.t("error"), self.t("select_dir_first"))
            return
        
        # 确认对话框
        result = self.ask_yesno(
            self.t("confirm_sort"),
            self.t("sort_warning"),
            icon='warning'
        )
        
        if not result:
            return
        
        # 按时间正序排序
        self.ids_data.sort(key=lambda x: datetime.strptime(x['date'], '%Y/%m/%d %H:%M:%S'), reverse=False)
        
        # 更新all_ids_data的顺序
        self.all_ids_data = [item['id'] for item in self.ids_data]
        
        # 保存到文件
        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
        self.encode_and_save(self.ids_data, ids_path)
        self.encode_and_save(self.all_ids_data, all_ids_path)
        
        # 重新加载列表以更新显示
        self.load_screenshots()
        
        messagebox.showinfo(self.t("success"), self.t("sort_asc_success"))

    def sort_descending(self):
        """按时间倒序排序"""
        if not self.storage_dir:
            messagebox.showerror(self.t("error"), self.t("select_dir_first"))
            return
        
        # 确认对话框
        result = self.ask_yesno(
            self.t("confirm_sort"),
            self.t("sort_warning"),
            icon='warning'
        )
        
        if not result:
            return
        
        # 按时间倒序排序
        self.ids_data.sort(key=lambda x: datetime.strptime(x['date'], '%Y/%m/%d %H:%M:%S'), reverse=True)
        
        # 更新all_ids_data的顺序
        self.all_ids_data = [item['id'] for item in self.ids_data]
        
        # 保存到文件
        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
        self.encode_and_save(self.ids_data, ids_path)
        self.encode_and_save(self.all_ids_data, all_ids_path)
        
        # 重新加载列表以更新显示
        self.load_screenshots()
        
        messagebox.showinfo(self.t("success"), self.t("sort_desc_success"))

    def update_checkbox_display(self, item_id):
        """更新复选框显示"""
        if item_id in self.checkbox_vars:
            var, id_str = self.checkbox_vars[item_id]
            checkbox_text = "☑" if var.get() else "☐"
            # 更新select列的值
            current_values = list(self.tree.item(item_id, "values"))
            if len(current_values) >= 2:
                current_values[0] = checkbox_text
                self.tree.item(item_id, values=tuple(current_values))
    
    def on_checkbox_change(self, var, id_str):
        """复选框状态变化时的处理"""
        # 更新显示
        for item_id, (v, iid) in self.checkbox_vars.items():
            if iid == id_str:
                self.update_checkbox_display(item_id)
                break
        
        # 更新全选复选框状态
        self.update_select_all_state()
        
        # 更新按钮状态
        self.update_button_states()
        
        # 更新批量导出按钮显示
        self.update_batch_export_button()
    
    def update_select_all_state(self):
        """更新全选复选框状态"""
        # 更新标题显示
        self.update_select_all_header()
    
    def toggle_select_all(self):
        """全选/取消全选"""
        # 检查当前是否全选
        if not self.checkbox_vars:
            return
        
        all_selected = all(var.get() for var, _ in self.checkbox_vars.values())
        select_all = not all_selected  # 切换状态
        
        for var, _ in self.checkbox_vars.values():
            var.set(select_all)
        # 更新所有复选框显示
        for item_id in self.checkbox_vars.keys():
            self.update_checkbox_display(item_id)
        # 更新标题显示
        self.update_select_all_header()
        self.update_button_states()
        self.update_batch_export_button()
    
    def update_select_all_header(self):
        """更新全选标题显示"""
        if not self.checkbox_vars:
            self.tree.heading("select", text="☐", anchor="center", command=self.toggle_select_all)
            return
        
        all_selected = all(var.get() for var, _ in self.checkbox_vars.values())
        checkbox_text = "☑" if all_selected else "☐"
        self.tree.heading("select", text=checkbox_text, anchor="center", command=self.toggle_select_all)
    
    def get_selected_ids(self):
        """获取所有选中的ID列表"""
        selected_ids = []
        for var, id_str in self.checkbox_vars.values():
            if var.get():
                selected_ids.append(id_str)
        return selected_ids
    
    def get_selected_count(self):
        """获取选中的数量"""
        return len(self.get_selected_ids())
    
    def update_button_states(self):
        """更新按钮状态"""
        selected_count = self.get_selected_count()
        # 如果选择了大于等于2个，禁用替换按钮
        if selected_count >= 2:
            self.replace_button.config(state="disabled")
        else:
            self.replace_button.config(state="normal")
    
    def update_batch_export_button(self):
        """更新批量导出按钮显示"""
        if not self.storage_dir:
            self.batch_export_button.pack_forget()
            return
        
        selected_count = self.get_selected_count()
        if selected_count > 0:
            self.batch_export_button.pack(pady=5)
        else:
            self.batch_export_button.pack_forget()
    
    def on_tree_select(self, event):
        """处理Treeview选择事件，显示预览"""
        selected = self.tree.selection()
        if not selected:
            # 清空预览
            self.preview_label.config(image='', bg="lightgray")
            self.preview_photo = None
            # 隐藏导出按钮
            self.export_button.pack_forget()
            return
        
        item_id = selected[0]
        if item_id in self.checkbox_vars:
            _, id_str = self.checkbox_vars[item_id]
            self.show_preview(id_str)
            # 显示导出按钮
            self.export_button.pack(pady=5)
    
    def on_button1_click(self, event):
        """统一处理Button-1点击事件：先检查复选框，再处理拖拽"""
        region = self.tree.identify_region(event.x, event.y)
        
        # 检查是否是复选框点击
        if region == "cell":
            column = self.tree.identify_column(event.x)  # 只传x坐标
            # 检查是否是select列（复选框列）
            # ***即使#0列被隐藏，仍然存在，所以select列是#1*** ★
            # 为了兼容性，也检查x坐标范围（select列宽度是40）
            if column == "#1" or (event.x < 40 and event.x > 0):
                item_id = self.tree.identify_row(event.y)
                if item_id and item_id in self.checkbox_vars:
                    var, _ = self.checkbox_vars[item_id]
                    var.set(not var.get())
                    # 阻止后续事件处理（包括拖拽和选择）
                    return "break"
        elif region == "heading":
            column = self.tree.identify_column(event.x)
            if column == "#1" or (event.x < 40 and event.x > 0): 
                # toggle_select_all 已经在 heading 的 command 中处理了
                # 不返回 "break"，让 command 回调正常执行
                # 但阻止拖拽
                self.drag_start_item = None
                return
        
        # 如果不是复选框点击，则处理拖拽
        # 获取鼠标点击位置对应的列表项
        item = self.tree.identify_row(event.y)
        if item:
            self.drag_start_item = item
            self.drag_start_y = event.y
            self.is_dragging = False

    def on_drag_motion(self, event):
        """拖拽过程中，检测是否真的在拖拽"""
        if self.drag_start_item is not None:
            # 检测鼠标是否移动了至少5像素
            if abs(event.y - self.drag_start_y) > 5:
                self.is_dragging = True
                # 获取当前鼠标位置对应的列表项（用于视觉反馈，但不做高亮处理）
                # Treeview的set方法只能设置列值，不能设置自定义属性
                # 如果需要高亮效果，可以使用tags和样式，但会增加复杂度
                # 这里暂时移除高亮功能，因为拖拽功能本身已经正常工作

    def on_drag_end(self, event):
        """结束拖拽，移动项目并保存顺序"""
        if self.drag_start_item is None:
            return
        
        # 如果没有真正拖拽（只是单击），不执行移动操作
        if not self.is_dragging:
            self.drag_start_item = None
            self.drag_start_y = None
            self.is_dragging = False
            return
        
        # 获取目标位置
        end_item = self.tree.identify_row(event.y)
        
        if not end_item or end_item == self.drag_start_item:
            self.drag_start_item = None
            self.drag_start_y = None
            self.is_dragging = False
            return
        
        # 获取起始和目标索引
        children = list(self.tree.get_children())
        start_index = children.index(self.drag_start_item)
        end_index = children.index(end_item)
        
        # 清除之前的箭头指示器
        self.clear_drag_indicators()
        
        # 移动Treeview中的项目
        item_values = self.tree.item(self.drag_start_item)
        moved_item_id = item_values['tags'][0] if item_values['tags'] else None
        
        # 获取目标位置原来的item ID（用于显示箭头）
        target_original_id = None
        if end_item:
            target_item_values = self.tree.item(end_item)
            target_original_id = target_item_values['tags'][0] if target_item_values['tags'] else None
        
        # 保存复选框状态和值
        checkbox_data = None
        checkbox_text = ""
        if self.drag_start_item in self.checkbox_vars:
            checkbox_data = self.checkbox_vars.pop(self.drag_start_item)
            var, _ = checkbox_data
            checkbox_text = "☑" if var.get() else "☐"
        
        # 保存当前值
        current_values = list(item_values['values'])
        
        # 删除项目
        self.tree.delete(self.drag_start_item)
        
        # 重新获取children列表（因为删除了一个项目，索引会变化）
        children = list(self.tree.get_children())
        
        # 重新插入到目标位置
        # 注意：删除后，如果向下移动，end_index需要减1（因为删除了start_index的项目）
        if end_index > start_index:
            # 向下移动：删除后，目标位置索引减1
            insert_index = end_index - 1
            if insert_index < 0:
                insert_index = 0
            if insert_index < len(children):
                # 在指定位置之前插入
                new_item = self.tree.insert("", insert_index, text=item_values['text'], values=tuple(current_values), tags=item_values['tags'])
            else:
                # 插入到末尾
                new_item = self.tree.insert("", tk.END, text=item_values['text'], values=tuple(current_values), tags=item_values['tags'])
        else:
            # 向上移动：目标位置不变
            if end_index < len(children):
                new_item = self.tree.insert("", end_index, text=item_values['text'], values=tuple(current_values), tags=item_values['tags'])
            else:
                new_item = self.tree.insert("", tk.END, text=item_values['text'], values=tuple(current_values), tags=item_values['tags'])
        
        # 恢复复选框状态
        if checkbox_data:
            self.checkbox_vars[new_item] = checkbox_data
            self.update_checkbox_display(new_item)
        
        # 同步更新ids_data和all_ids_data的顺序
        moved_item = self.ids_data.pop(start_index)
        self.ids_data.insert(end_index, moved_item)
        
        # 更新all_ids_data的顺序
        new_all_ids_order = [item['id'] for item in self.ids_data]
        self.all_ids_data = new_all_ids_order
        
        # 保存更新后的顺序到文件
        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
        self.encode_and_save(self.ids_data, ids_path)
        self.encode_and_save(self.all_ids_data, all_ids_path)
        
        # 保存移动的item的ID（用于重新加载后恢复选择）
        moved_id = moved_item_id  
        
        # 记录移动方向（用于显示箭头指示器）
        is_moving_down = end_index > start_index
        
        # 计算填补被移动项原位置的项的ID（用于显示箭头）
        # 当向下移动时，start_index+1位置的项会向上移动到start_index位置（填补空位）
        # 当向上移动时，start_index-1位置的项会向下移动到start_index位置（填补空位）
        # 注意：这个项在移动后位于start_index位置（被移动项的原位置）
        affected_item_id = None
        if is_moving_down and start_index + 1 < len(children):
            # 向下移动：start_index+1位置的项会向上移动到start_index位置
            affected_item = children[start_index + 1]
            affected_item_values = self.tree.item(affected_item)
            affected_item_id = affected_item_values['tags'][0] if affected_item_values['tags'] else None
        elif not is_moving_down and start_index > 0:
            # 向上移动：start_index-1位置的项会向下移动到start_index位置
            affected_item = children[start_index - 1]
            affected_item_values = self.tree.item(affected_item)
            affected_item_id = affected_item_values['tags'][0] if affected_item_values['tags'] else None
        
        # 重新加载列表以更新显示
        self.load_screenshots()
        
        # 恢复选择：根据ID找到新的item
        moved_item = None
        if moved_id:
            children = list(self.tree.get_children())
            for tree_item_id in children:
                item_tags = self.tree.item(tree_item_id, "tags")
                if item_tags and item_tags[0] == moved_id:
                    moved_item = tree_item_id
                    self.tree.selection_set(tree_item_id)
                    # 滚动到选中项
                    self.tree.see(tree_item_id)
                    break
        
        # 显示箭头指示器
        # 移动后，被移动的项位于end_index位置，填补原位置的项位于start_index位置
        children = list(self.tree.get_children())
        
        if moved_item:
            # 被移动的项：向下移动显示↓↓↓（绿色），向上移动显示↑↑↑（粉色）
            self.show_drag_indicator_on_item(moved_item, not is_moving_down)
        
        if start_index < len(children):
            item_at_start_pos = children[start_index]
            item_tags = self.tree.item(item_at_start_pos, "tags")
            # 确保不是被移动的项本身
            if item_tags and item_tags[0] != moved_id:
                self.show_drag_indicator_on_item(item_at_start_pos, is_moving_down)
        
        self.drag_start_item = None
        self.drag_start_y = None
        self.is_dragging = False
    
    def clear_drag_indicators(self):
        """清除所有箭头指示器"""
        for item_id, original_text, after_id in self.drag_indicators:
            try:
                # 取消定时器
                if after_id:
                    self.root.after_cancel(after_id)
                # 恢复原始文本
                if self.tree.exists(item_id):
                    current_values = list(self.tree.item(item_id, "values"))
                    if len(current_values) >= 2:
                        # 移除箭头前缀，恢复原始文本
                        info_text = current_values[1]
                        # 移除箭头前缀（↑↑↑或↓↓↓）
                        if info_text.startswith("↑↑↑"):
                            info_text = info_text[3:].lstrip()
                        elif info_text.startswith("↓↓↓"):
                            info_text = info_text[3:].lstrip()
                        current_values[1] = info_text
                        self.tree.item(item_id, values=tuple(current_values))
                        # 移除tag
                        current_tags = list(self.tree.item(item_id, "tags"))
                        if "DragIndicatorUp" in current_tags:
                            current_tags.remove("DragIndicatorUp")
                        if "DragIndicatorDown" in current_tags:
                            current_tags.remove("DragIndicatorDown")
                        self.tree.item(item_id, tags=tuple(current_tags))
            except:
                pass
        self.drag_indicators.clear()
    
    def show_drag_indicator_on_item(self, item_id, show_up_arrows):
        """在指定item的名字前显示箭头指示器"""
        if not self.tree.exists(item_id):
            return
        
        # 获取当前值
        current_values = list(self.tree.item(item_id, "values"))
        if len(current_values) < 2:
            return
        
        original_text = current_values[1]  # 保存原始文本
        
        # 确定箭头符号和颜色
        if show_up_arrows:
            # 显示↑↑↑（粉色 #D06CAA）
            arrow_prefix = "↑↑↑"
            style_tag = "DragIndicatorDown" 
        else:
            # 显示↓↓↓（绿色 #85A9A5）
            arrow_prefix = "↓↓↓"
            style_tag = "DragIndicatorUp" 
        
        # 在名字前添加箭头
        new_text = f"{arrow_prefix} {original_text}"
        current_values[1] = new_text
        
        # 更新item
        current_tags = list(self.tree.item(item_id, "tags"))
        if style_tag not in current_tags:
            current_tags.append(style_tag)
        self.tree.item(item_id, values=tuple(current_values), tags=tuple(current_tags))
        
        # 设置15秒后自动清除
        def remove_indicator():
            try:
                if self.tree.exists(item_id):
                    current_values = list(self.tree.item(item_id, "values"))
                    if len(current_values) >= 2:
                        info_text = current_values[1]
                        # 移除箭头前缀
                        if info_text.startswith("↑↑↑"):
                            info_text = info_text[3:].lstrip()
                        elif info_text.startswith("↓↓↓"):
                            info_text = info_text[3:].lstrip()
                        current_values[1] = info_text
                        self.tree.item(item_id, values=tuple(current_values))
                        # 移除tag
                        current_tags = list(self.tree.item(item_id, "tags"))
                        if "DragIndicatorUp" in current_tags:
                            current_tags.remove("DragIndicatorUp")
                        if "DragIndicatorDown" in current_tags:
                            current_tags.remove("DragIndicatorDown")
                        self.tree.item(item_id, tags=tuple(current_tags))
                # 从列表中移除
                self.drag_indicators = [(iid, orig, aid) for iid, orig, aid in self.drag_indicators if iid != item_id]
            except:
                pass
        
        after_id = self.root.after(15000, remove_indicator)  # 15秒后移除
        
        # 记录指示器信息
        self.drag_indicators.append((item_id, original_text, after_id))

    def show_status_indicator(self, id_str, is_new=True):
        """在指定ID的截图名称前显示状态指示器（新截图或替换截图）"""
        # 找到对应的item_id
        item_id = None
        for tree_item_id in self.tree.get_children():
            item_tags = self.tree.item(tree_item_id, "tags")
            if item_tags and item_tags[0] == id_str:
                item_id = tree_item_id
                break
        
        if not item_id or not self.tree.exists(item_id):
            return
        
        # 获取当前值
        current_values = list(self.tree.item(item_id, "values"))
        if len(current_values) < 2:
            return
        
        original_text = current_values[1]  # 保存原始文本
        
        # 确定标记符号和颜色tag
        if is_new:
            # 新截图：显示"⚝ "
            indicator_prefix = "⚝ "
            style_tag = "NewIndicator"
        else:
            # 替换截图：显示"✧ "
            indicator_prefix = "✧ "
            style_tag = "ReplaceIndicator"
        
        # 检查是否已经有标记（避免重复添加）
        info_text = current_values[1]
        if info_text.startswith("⚝ ") or info_text.startswith("✧ "):
            # 如果已经有标记，先移除
            if info_text.startswith("⚝ "):
                info_text = info_text[2:].lstrip()
            elif info_text.startswith("✧ "):
                info_text = info_text[2:].lstrip()
            original_text = info_text
        
        # 在名字前添加标记
        new_text = f"{indicator_prefix}{original_text}"
        current_values[1] = new_text
        
        # 更新item
        current_tags = list(self.tree.item(item_id, "tags"))
        if style_tag not in current_tags:
            current_tags.append(style_tag)
        self.tree.item(item_id, values=tuple(current_values), tags=tuple(current_tags))
        
        # 设置15秒后自动清除
        def remove_indicator():
            try:
                if self.tree.exists(item_id):
                    current_values = list(self.tree.item(item_id, "values"))
                    if len(current_values) >= 2:
                        info_text = current_values[1]
                        # 移除标记前缀
                        if info_text.startswith("⚝ "):
                            info_text = info_text[2:].lstrip()
                        elif info_text.startswith("✧ "):
                            info_text = info_text[2:].lstrip()
                        current_values[1] = info_text
                        self.tree.item(item_id, values=tuple(current_values))
                        # 移除tag
                        current_tags = list(self.tree.item(item_id, "tags"))
                        if "NewIndicator" in current_tags:
                            current_tags.remove("NewIndicator")
                        if "ReplaceIndicator" in current_tags:
                            current_tags.remove("ReplaceIndicator")
                        self.tree.item(item_id, tags=tuple(current_tags))
                # 从列表中移除
                self.status_indicators = [(iid, orig, aid, itype) for iid, orig, aid, itype in self.status_indicators if iid != item_id]
            except:
                pass
        
        after_id = self.root.after(15000, remove_indicator)  # 15秒后移除
        
        # 记录指示器信息
        self.status_indicators.append((item_id, original_text, after_id, "new" if is_new else "replace"))

    def show_preview(self, id_str):
        """显示指定ID的预览图片"""
        if not self.storage_dir or id_str not in self.sav_pairs:
            self.preview_label.config(image='', bg="lightgray")
            self.preview_photo = None
            return
        
        main_file = self.sav_pairs[id_str][0]
        if not main_file:
            self.preview_label.config(image='', bg="lightgray", text=self.t("file_missing_text"))
            self.preview_photo = None
            return
        
        main_sav = os.path.join(self.storage_dir, main_file)
        if not os.path.exists(main_sav):
            self.preview_label.config(image='', bg="lightgray", text=self.t("file_not_exist_text"))
            self.preview_photo = None
            return
        
        temp_png = None
        try:
            # 解码主 .sav 获取 PNG 数据
            with open(main_sav, 'r', encoding='utf-8') as f:
                encoded = f.read().strip()
            unquoted = urllib.parse.unquote(encoded)
            data_uri = json.loads(unquoted)
            b64_part = data_uri.split(';base64,', 1)[1]
            img_data = base64.b64decode(b64_part)
            
            # 保存到临时 PNG 文件
            temp_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
            with open(temp_png, 'wb') as f:
                f.write(img_data)
            
            # 加载图片
            img = Image.open(temp_png)
            # 拉伸到4:3比例(实际游戏内显示也会拉成这样)
            preview_img = img.resize((160, 120), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(preview_img)
            
            # 更新预览Label
            self.preview_label.config(image=photo, bg="white", text="")
            self.preview_photo = photo 
            
            img.close()
        except Exception as e:
            # 出错时显示错误信息
            self.preview_label.config(image='', bg="lightgray", text=self.t("preview_failed"))
            self.preview_photo = None
        finally:
            # 清理临时文件
            if temp_png and os.path.exists(temp_png):
                try:
                    os.remove(temp_png)
                except:
                    pass

    def load_and_decode(self, sav_path):
        with open(sav_path, 'r', encoding='utf-8') as f:
            encoded = f.read().strip()
        unquoted = urllib.parse.unquote(encoded)
        return json.loads(unquoted)

    def encode_and_save(self, data, sav_path):
        json_str = json.dumps(data)
        encoded = urllib.parse.quote(json_str)
        with open(sav_path, 'w', encoding='utf-8') as f:
            f.write(encoded)

    def replace_selected(self):
        # 获取选中的ID（通过Treeview选择或复选框）
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror(self.t("error"), self.t("select_screenshot"))
            return
        
        item_id = selected[0]
        if item_id not in self.checkbox_vars:
            messagebox.showerror(self.t("error"), self.t("invalid_selection"))
            return
        
        _, id_str = self.checkbox_vars[item_id]

        if id_str not in self.sav_pairs or self.sav_pairs[id_str][0] is None or self.sav_pairs[id_str][1] is None:
            messagebox.showerror(self.t("error"), self.t("file_missing"))
            return

        new_png = filedialog.askopenfilename(title=self.t("select_new_image"))
        if not new_png:
            return

        # 检查文件扩展名
        valid_image_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tiff', '.tif', '.ico'}
        file_ext = os.path.splitext(new_png)[1].lower()
        filename = os.path.basename(new_png)
        is_valid_image = file_ext in valid_image_extensions

        main_sav = os.path.join(self.storage_dir, self.sav_pairs[id_str][0])
        thumb_sav = os.path.join(self.storage_dir, self.sav_pairs[id_str][1])
        
        confirmed = False
        
        # 解码主 .sav 获取 PNG 数据
        with open(main_sav, 'r', encoding='utf-8') as f:
            encoded = f.read().strip()
        unquoted = urllib.parse.unquote(encoded)
        data_uri = json.loads(unquoted)
        b64_part = data_uri.split(';base64,', 1)[1]
        img_data = base64.b64decode(b64_part)

        # 保存到临时 PNG 文件
        temp_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
        with open(temp_png, 'wb') as f:
            f.write(img_data)

        # 确认替换窗口
        popup = Toplevel(self.root)
        popup.title(self.t("replace_warning"))
        
        # 如果不是常规图片格式，在窗口顶端显示警告
        if not is_valid_image:
            warning_label = tk.Label(popup, text=self.t("file_extension_warning", filename=filename), 
                                    fg="#FF57FD", font=("Arial", 10), wraplength=600, justify="left")
            warning_label.pack(pady=5, padx=10, anchor="w")
        
        ttk.Label(popup, text=self.t("replace_confirm_text"), font=("Arial", 12)).pack(pady=10)
        
        # 图片对比区域
        image_frame = tk.Frame(popup)
        image_frame.pack(pady=10)
        
        # 原图片（左侧）
        orig_img = Image.open(temp_png)
        orig_preview = orig_img.resize((400, 300), Image.Resampling.LANCZOS)  
        orig_photo = ImageTk.PhotoImage(orig_preview)
        orig_label = Label(image_frame, image=orig_photo)  # 显示图片的Label保持tk.Label
        orig_label.pack(side="left", padx=10)
        popup.orig_photo = orig_photo 
        orig_img.close()
        
        ttk.Label(image_frame, text="→", font=("Arial", 24)).pack(side="left", padx=10)
        
        # 新图片（右侧）
        try:
            new_img = Image.open(new_png)
            new_preview = new_img.resize((400, 300), Image.Resampling.LANCZOS) 
            new_photo = ImageTk.PhotoImage(new_preview)
            new_label = Label(image_frame, image=new_photo)  # 显示图片的Label保持tk.Label
            new_label.pack(side="left", padx=10)
            popup.new_photo = new_photo 
            new_img.close()
        except Exception as e:
            # 如果无法打开图片，显示错误信息
            error_label = Label(image_frame, text=self.t("preview_failed"), fg="red", font=("Arial", 12))
            error_label.pack(side="left", padx=10)
            popup.new_photo = None

        ttk.Label(popup, text=self.t("replace_confirm_question")).pack(pady=10)

        def yes():
            popup.destroy()
            nonlocal confirmed
            confirmed = True 
            self.replace_sav(main_sav, thumb_sav, new_png) 

        def no():
            popup.destroy()
            return  

        ttk.Button(popup, text=self.t("replace_yes"), command=yes).pack(side="left", padx=10)
        ttk.Button(popup, text=self.t("replace_no"), command=no).pack(side="right", padx=10)
        popup.grab_set()
        self.root.wait_window(popup)
        os.remove(temp_png)  # 无论如何清理
        if not confirmed:
            return
        self.replace_sav(main_sav, thumb_sav, new_png)
        messagebox.showinfo(self.t("success"), self.t("replace_success", id=id_str))
        self.load_screenshots()
        self.show_status_indicator(id_str, is_new=False)

    def replace_sav(self, main_sav, thumb_sav, new_png):
        temp_thumb = None
        try:
            # 提取原thumb尺寸
            with open(thumb_sav, 'r', encoding='utf-8') as f:
                encoded = f.read().strip()
            unquoted = urllib.parse.unquote(encoded)
            data_uri = json.loads(unquoted)
            b64_part = data_uri.split(';base64,', 1)[1]
            img_data = base64.b64decode(b64_part)
            temp_thumb = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False).name
            with open(temp_thumb, 'wb') as f:
                f.write(img_data)
            thumb_orig = Image.open(temp_thumb)
            thumb_size = thumb_orig.size
            thumb_orig.close()  

            # 新主sav (PNG)
            with open(new_png, 'rb') as f:
                png_b64 = base64.b64encode(f.read()).decode('utf-8')
            new_main_uri = f"data:image/png;base64,{png_b64}"
            new_main_json = json.dumps(new_main_uri)
            new_main_encoded = urllib.parse.quote(new_main_json)
            with open(main_sav, 'w', encoding='utf-8') as f:
                f.write(new_main_encoded)

            # 新thumb JPEG
            main_img = Image.open(new_png)
            new_thumb = main_img.resize(thumb_size, Image.Resampling.LANCZOS)
            new_thumb = new_thumb.convert('RGB')
            new_thumb.save(temp_thumb, 'JPEG', quality=90, optimize=True)
            main_img.close()  # 显式关闭图像对象，释放文件句柄
            with open(temp_thumb, 'rb') as f:
                jpeg_b64 = base64.b64encode(f.read()).decode('utf-8')
            new_thumb_uri = f"data:image/jpeg;base64,{jpeg_b64}"
            new_thumb_json = json.dumps(new_thumb_uri)
            new_thumb_encoded = urllib.parse.quote(new_thumb_json)
            with open(thumb_sav, 'w', encoding='utf-8') as f:
                f.write(new_thumb_encoded)
        finally:
            if temp_thumb and os.path.exists(temp_thumb):
                try:
                    os.remove(temp_thumb)
                except:
                    pass

    def add_new(self):
        # 检查是否已选择目录
        if not self.storage_dir:
            messagebox.showwarning(self.t("warning"), self.t("select_dir_hint"))
            return
        
        new_png = filedialog.askopenfilename(title=self.t("select_new_png"))
        if not new_png:
            return

        # 检查文件扩展名
        valid_image_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tiff', '.tif', '.ico'}
        file_ext = os.path.splitext(new_png)[1].lower()
        filename = os.path.basename(new_png)
        is_valid_image = file_ext in valid_image_extensions

        # 弹出窗口输入 ID 和 date
        popup = Toplevel(self.root)
        popup.title(self.t("add_new_title"))
        popup.geometry("400x200")

        # 如果不是常规图片格式，在窗口顶端显示警告
        if not is_valid_image:
            warning_label = tk.Label(popup, text=self.t("file_extension_warning", filename=filename), 
                                    fg="#FF57FD", font=("Arial", 10), wraplength=380, justify="left")
            warning_label.pack(pady=5, padx=10, anchor="w")

        ttk.Label(popup, text=self.t("id_label")).pack(pady=5)
        id_entry = ttk.Entry(popup, width=50)
        id_entry.pack()

        ttk.Label(popup, text=self.t("date_label")).pack(pady=5)
        date_entry = ttk.Entry(popup, width=50)
        date_entry.pack()

        def confirm():
            new_id = id_entry.get().strip() or ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            new_date = date_entry.get().strip() or datetime.now().strftime('%Y/%m/%d %H:%M:%S')

            try:
                # 验证 date 格式
                datetime.strptime(new_date, '%Y/%m/%d %H:%M:%S')
            except ValueError:
                messagebox.showerror(self.t("error"), self.t("invalid_date_format"))
                return

            if new_id in self.sav_pairs:
                messagebox.showerror(self.t("error"), self.t("id_exists"))
                return

            # 更新ids
            self.ids_data.append({"id": new_id, "date": new_date})
            ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
            self.encode_and_save(self.ids_data, ids_path)

            # 更新all_ids
            self.all_ids_data.append(new_id)
            all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
            self.encode_and_save(self.all_ids_data, all_ids_path)

            # 生成新sav对
            main_sav_name = f'DevilConnection_photo_{new_id}.sav'
            thumb_sav_name = f'DevilConnection_photo_{new_id}_thumb.sav'
            main_sav = os.path.join(self.storage_dir, main_sav_name)
            thumb_sav = os.path.join(self.storage_dir, thumb_sav_name)
            thumb_size = (1280, 960)
            valid_thumb_found = False
            for pair in self.sav_pairs.values():
                if pair[1] is not None:
                    first_thumb = os.path.join(self.storage_dir, pair[1])
                    with open(first_thumb, 'r', encoding='utf-8') as f:
                        encoded = f.read().strip()
                    unquoted = urllib.parse.unquote(encoded)
                    data_uri = json.loads(unquoted)
                    b64_part = data_uri.split(';base64,', 1)[1]
                    img_data = base64.b64decode(b64_part)
                    temp_thumb_size = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False).name
                    with open(temp_thumb_size, 'wb') as f:
                        f.write(img_data)
                    thumb_orig = Image.open(temp_thumb_size)
                    thumb_size = thumb_orig.size
                    thumb_orig.close() 
                    os.remove(temp_thumb_size)
                    valid_thumb_found = True
                    break

            # 生成文件
            temp_thumb = None
            try:
                # 新主sav (PNG)
                with open(new_png, 'rb') as f:
                    png_b64 = base64.b64encode(f.read()).decode('utf-8')
                new_main_uri = f"data:image/png;base64,{png_b64}"
                new_main_json = json.dumps(new_main_uri)
                new_main_encoded = urllib.parse.quote(new_main_json)
                with open(main_sav, 'w', encoding='utf-8') as f:
                    f.write(new_main_encoded)

                # 新thumb JPEG
                try:
                    main_img = Image.open(new_png)
                    new_thumb = main_img.resize(thumb_size, Image.Resampling.LANCZOS)
                    new_thumb = new_thumb.convert('RGB')
                    main_img.close() 
                    temp_thumb = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False).name
                    new_thumb.save(temp_thumb, 'JPEG', quality=90, optimize=True)
                except Exception as e:
                    messagebox.showerror(self.t("error"), self.t("preview_failed") + f": {str(e)}")
                    return
                with open(temp_thumb, 'rb') as f:
                    jpeg_b64 = base64.b64encode(f.read()).decode('utf-8')
                new_thumb_uri = f"data:image/jpeg;base64,{jpeg_b64}"
                new_thumb_json = json.dumps(new_thumb_uri)
                new_thumb_encoded = urllib.parse.quote(new_thumb_json)
                with open(thumb_sav, 'w', encoding='utf-8') as f:
                    f.write(new_thumb_encoded)
            finally:
                if temp_thumb and os.path.exists(temp_thumb):
                    try:
                        os.remove(temp_thumb)
                    except:
                        pass

            popup.destroy()
            messagebox.showinfo(self.t("success"), self.t("add_success", id=new_id))
            # 取消所有选择
            for var, _ in self.checkbox_vars.values():
                var.set(False)
            for item_id in self.checkbox_vars.keys():
                self.update_checkbox_display(item_id)
            self.update_select_all_header()
            self.update_button_states()
            self.update_batch_export_button()
            self.load_screenshots()
            self.show_status_indicator(new_id, is_new=True)

        ttk.Button(popup, text=self.t("confirm"), command=confirm).pack(pady=20)
        
    def delete_selected(self):
        # 获取所有选中的ID（通过复选框）
        selected_ids = self.get_selected_ids()
        if not selected_ids:
            messagebox.showerror(self.t("error"), self.t("delete_select_error"))
            return
        
        # 确认删除对话框
        if len(selected_ids) == 1:
            confirm_msg = self.t("delete_confirm_single", id=selected_ids[0])
        else:
            ids_str = ', '.join(selected_ids[:5]) + ('...' if len(selected_ids) > 5 else '')
            confirm_msg = self.t("delete_confirm_multiple", count=len(selected_ids), ids=ids_str)
        
        popup = Toplevel(self.root)
        popup.title(self.t("delete_confirm"))
        ttk.Label(popup, text=confirm_msg).pack(pady=10)

        confirmed = False

        def yes():
            nonlocal confirmed
            confirmed = True
            popup.destroy()

        def no():
            popup.destroy()

        ttk.Button(popup, text=self.t("delete_ok"), command=yes).pack(side="left", padx=10)
        ttk.Button(popup, text=self.t("delete_cancel"), command=no).pack(side="right", padx=10)

        popup.grab_set()
        self.root.wait_window(popup)

        if not confirmed:
            return

        # 删除所有选中的截图
        deleted_count = 0
        for id_str in selected_ids:
            # 删除文件（如果存在）
            pair = self.sav_pairs.get(id_str, [None, None])
            main_path = os.path.join(self.storage_dir, pair[0]) if pair[0] else None
            thumb_path = os.path.join(self.storage_dir, pair[1]) if pair[1] else None
            if main_path and os.path.exists(main_path):
                try:
                    os.remove(main_path)
                    deleted_count += 1
                except:
                    pass
            if thumb_path and os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except:
                    pass

            # 从索引移除
            self.ids_data = [item for item in self.ids_data if item['id'] != id_str]
            self.all_ids_data = [item for item in self.all_ids_data if item != id_str]

            # 移除本地缓存（如果存在）
            if id_str in self.sav_pairs:
                del self.sav_pairs[id_str]

        # 保存更新
        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        self.encode_and_save(self.ids_data, ids_path)
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
        self.encode_and_save(self.all_ids_data, all_ids_path)

        if deleted_count > 0:
            messagebox.showinfo(self.t("success"), self.t("delete_success", count=deleted_count))
        else:
            messagebox.showwarning(self.t("warning"), self.t("delete_warning"))
        
        # 取消所有选择
        for var, _ in self.checkbox_vars.values():
            var.set(False)
        self.update_select_all_header()
        self.update_button_states()
        self.update_batch_export_button()
        self.load_screenshots()
    
    def export_image(self):
        """导出选中的截图"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror(self.t("error"), self.t("select_screenshot"))
            return
        
        item_id = selected[0]
        if item_id not in self.checkbox_vars:
            messagebox.showerror(self.t("error"), self.t("invalid_selection"))
            return
        
        _, id_str = self.checkbox_vars[item_id]
        
        if not self.storage_dir or id_str not in self.sav_pairs:
            messagebox.showerror(self.t("error"), self.t("file_not_found"))
            return
        
        main_file = self.sav_pairs[id_str][0]
        if not main_file:
            messagebox.showerror(self.t("error"), self.t("file_missing_text"))
            return
        
        main_sav = os.path.join(self.storage_dir, main_file)
        if not os.path.exists(main_sav):
            messagebox.showerror(self.t("error"), self.t("file_not_exist"))
            return
        
        # 解码图片数据
        try:
            with open(main_sav, 'r', encoding='utf-8') as f:
                encoded = f.read().strip()
            unquoted = urllib.parse.unquote(encoded)
            data_uri = json.loads(unquoted)
            b64_part = data_uri.split(';base64,', 1)[1]
            img_data = base64.b64decode(b64_part)
            
            # 保存到临时PNG文件
            temp_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
            with open(temp_png, 'wb') as f:
                f.write(img_data)
            
            # 打开图片
            img = Image.open(temp_png)
            
            # 弹出格式选择对话框
            format_window = Toplevel(self.root)
            format_window.title(self.t("select_export_format"))
            format_window.geometry("300x150")
            
            selected_format = tk.StringVar(value="png")
            
            ttk.Label(format_window, text=self.t("select_image_format")).pack(pady=10)
            format_frame = tk.Frame(format_window)
            format_frame.pack(pady=10)
            
            ttk.Radiobutton(format_frame, text="PNG", variable=selected_format, value="png").pack(side="left", padx=10)
            ttk.Radiobutton(format_frame, text="JPEG", variable=selected_format, value="jpeg").pack(side="left", padx=10)
            ttk.Radiobutton(format_frame, text="WebP", variable=selected_format, value="webp").pack(side="left", padx=10)
            
            def confirm_export():
                nonlocal img, temp_png
                format_window.destroy()
                format = selected_format.get()
                
                # 获取原始文件名（不含.sav后缀）
                base_name = os.path.splitext(main_file)[0]
                
                # 根据格式设置文件扩展名和保存选项
                if format == "png":
                    filetypes = [("PNG files", "*.png"), ("All files", "*.*")]
                    default_ext = ".png"
                    default_filename = base_name + ".png"
                elif format == "jpeg":
                    filetypes = [("JPEG files", "*.jpg"), ("All files", "*.*")]
                    default_ext = ".jpg"
                    default_filename = base_name + ".jpg"
                else:  # webp
                    filetypes = [("WebP files", "*.webp"), ("All files", "*.*")]
                    default_ext = ".webp"
                    default_filename = base_name + ".webp"
                
                # 弹出保存对话框
                save_path = filedialog.asksaveasfilename(
                    title=self.t("save_image"),
                    defaultextension=default_ext,
                    filetypes=filetypes,
                    initialfile=default_filename
                )
                
                if not save_path:
                    img.close()
                    os.remove(temp_png)
                    return
                
                try:
                    # 根据格式保存图片
                    if format == "png":
                        img.save(save_path, "PNG")
                    elif format == "jpeg":
                        # JPEG需要RGB模式
                        if img.mode != "RGB":
                            img = img.convert("RGB")
                        img.save(save_path, "JPEG", quality=95)
                    else:  # webp
                        img.save(save_path, "WebP", quality=95)
                    
                    messagebox.showinfo(self.t("success"), self.t("export_success", path=save_path))
                except Exception as e:
                    messagebox.showerror(self.t("error"), self.t("save_failed", error=str(e)))
                finally:
                    img.close()
                    if os.path.exists(temp_png):
                        os.remove(temp_png)
            
            def on_close():
                """窗口关闭时的清理函数"""
                nonlocal img, temp_png
                try:
                    img.close()
                except:
                    pass
                try:
                    if os.path.exists(temp_png):
                        os.remove(temp_png)
                except:
                    pass
                format_window.destroy()
            
            ttk.Button(format_window, text=self.t("delete_ok"), command=confirm_export).pack(pady=10)
            format_window.protocol("WM_DELETE_WINDOW", on_close)
            format_window.grab_set()
            
        except Exception as e:
            messagebox.showerror(self.t("error"), self.t("export_failed") + f": {str(e)}")
    
    def batch_export_images(self):
        """批量导出选中的截图到ZIP文件"""
        selected_ids = self.get_selected_ids()
        if not selected_ids:
            messagebox.showerror(self.t("error"), self.t("batch_export_error"))
            return
        
        if not self.storage_dir:
            messagebox.showerror(self.t("error"), self.t("select_dir_first"))
            return
        
        # 弹出格式选择对话框
        format_window = Toplevel(self.root)
        format_window.title(self.t("select_export_format"))
        format_window.geometry("300x150")
        
        selected_format = tk.StringVar(value="png")
        
        ttk.Label(format_window, text=self.t("select_image_format")).pack(pady=10)
        format_frame = tk.Frame(format_window)
        format_frame.pack(pady=10)
        
        ttk.Radiobutton(format_frame, text="PNG", variable=selected_format, value="png").pack(side="left", padx=10)
        ttk.Radiobutton(format_frame, text="JPEG", variable=selected_format, value="jpeg").pack(side="left", padx=10)
        ttk.Radiobutton(format_frame, text="WebP", variable=selected_format, value="webp").pack(side="left", padx=10)
        
        def confirm_batch_export():
            format_window.destroy()
            format = selected_format.get()
            
            # 根据格式设置文件扩展名
            if format == "png":
                default_ext = ".png"
                file_ext = "png"
            elif format == "jpeg":
                default_ext = ".jpg"
                file_ext = "jpg"
            else:  # webp
                default_ext = ".webp"
                file_ext = "webp"
            
            # 弹出保存对话框
            save_path = filedialog.asksaveasfilename(
                title=self.t("save_zip"),
                defaultextension=".zip",
                filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
                initialfile="DevilConnectionSSPack.zip"
            )
            
            if not save_path:
                return
            
            try:
                # 创建临时目录存放图片
                temp_dir = tempfile.mkdtemp()
                exported_count = 0
                failed_count = 0
                
                # 导出每张图片
                for id_str in selected_ids:
                    if id_str not in self.sav_pairs:
                        failed_count += 1
                        continue
                    
                    main_file = self.sav_pairs[id_str][0]
                    if not main_file:
                        failed_count += 1
                        continue
                    
                    main_sav = os.path.join(self.storage_dir, main_file)
                    if not os.path.exists(main_sav):
                        failed_count += 1
                        continue
                    
                    try:
                        # 解码图片数据
                        with open(main_sav, 'r', encoding='utf-8') as f:
                            encoded = f.read().strip()
                        unquoted = urllib.parse.unquote(encoded)
                        data_uri = json.loads(unquoted)
                        b64_part = data_uri.split(';base64,', 1)[1]
                        img_data = base64.b64decode(b64_part)
                        
                        # 保存到临时PNG文件
                        temp_png = os.path.join(temp_dir, f"{id_str}.png")
                        with open(temp_png, 'wb') as f:
                            f.write(img_data)
                        
                        # 打开图片并转换格式
                        img = Image.open(temp_png)
                        
                        # 根据格式保存
                        output_filename = f"{id_str}.{file_ext}"
                        output_path = os.path.join(temp_dir, output_filename)
                        
                        if format == "png":
                            img.save(output_path, "PNG")
                        elif format == "jpeg":
                            if img.mode != "RGB":
                                img = img.convert("RGB")
                            img.save(output_path, "JPEG", quality=95)
                        else:  # webp
                            img.save(output_path, "WebP", quality=95)
                        
                        img.close()
                        os.remove(temp_png)  # 删除临时PNG
                        exported_count += 1
                    except Exception as e:
                        failed_count += 1
                        continue
                
                # 创建ZIP文件
                if exported_count > 0:
                    with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for filename in os.listdir(temp_dir):
                            file_path = os.path.join(temp_dir, filename)
                            if os.path.isfile(file_path):
                                zipf.write(file_path, filename)
                    
                    # 清理临时目录
                    shutil.rmtree(temp_dir)
                    
                    success_msg = self.t("batch_export_success", count=exported_count)
                    if failed_count > 0:
                        success_msg += "\n" + self.t("batch_export_failed", count=failed_count)
                    messagebox.showinfo(self.t("success"), success_msg)
                else:
                    # 清理临时目录
                    shutil.rmtree(temp_dir)
                    messagebox.showerror(self.t("error"), self.t("batch_export_error_all"))
                    
            except Exception as e:
                messagebox.showerror(self.t("error"), self.t("batch_export_fail", error=str(e)))
        
        ttk.Button(format_window, text=self.t("delete_ok"), command=confirm_batch_export).pack(pady=10)
        format_window.grab_set()
        

if __name__ == "__main__":
    root = tk.Tk()
    app = SavTool(root)
    root.mainloop()