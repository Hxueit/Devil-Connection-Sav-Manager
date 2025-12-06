import os
import json
import urllib.parse
import base64
import tempfile
from datetime import datetime
from PIL import Image
from PIL import ImageTk
import random
import string
import tkinter as tk
from tkinter import filedialog, messagebox, Scrollbar, Toplevel, Label, Entry, simpledialog
from tkinter import ttk
import zipfile
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

# I really should have used rust。

class ScreenshotManager:
    """截图数据管理类"""
    
    def __init__(self, storage_dir=None):
        self.storage_dir = storage_dir
        self.ids_data = []
        self.all_ids_data = []
        self.sav_pairs = {}
        self._file_list_cache = None
        self._file_list_cache_time = 0
        self._file_list_cache_ttl = 5
    
    def set_storage_dir(self, storage_dir):
        """设置存储目录"""
        self.storage_dir = storage_dir
        self._file_list_cache = None
    
    def load_and_decode(self, sav_path):
        """加载并解码sav文件"""
        with open(sav_path, 'r', encoding='utf-8') as f:
            encoded = f.read().strip()
        unquoted = urllib.parse.unquote(encoded)
        return json.loads(unquoted)

    def encode_and_save(self, data, sav_path):
        """编码并保存数据到sav文件"""
        json_str = json.dumps(data)
        encoded = urllib.parse.quote(json_str)
        with open(sav_path, 'w', encoding='utf-8') as f:
            f.write(encoded)
    
    def scan_sav_files(self):
        """扫描存储目录中的截图文件"""
        import time
        current_time = time.time()
        
        if (self._file_list_cache is None or 
            current_time - self._file_list_cache_time > self._file_list_cache_ttl or
            self._file_list_cache[0] != self.storage_dir):
            self.sav_pairs = {}
            try:
                file_list = os.listdir(self.storage_dir)
                for file in file_list:
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
                
                self._file_list_cache = (self.storage_dir, self.sav_pairs.copy())
                self._file_list_cache_time = current_time
            except OSError:
                self.sav_pairs = {}
                self._file_list_cache = None
        else:
            _, self.sav_pairs = self._file_list_cache
            self.sav_pairs = self.sav_pairs.copy()
        
        return self.sav_pairs
    
    def load_screenshots(self):
        """加载截图索引数据"""
        if not self.storage_dir:
            return False
        
        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
        
        if not (os.path.exists(ids_path) and os.path.exists(all_ids_path)):
            return False
        
        self.ids_data = self.load_and_decode(ids_path)
        self.all_ids_data = self.load_and_decode(all_ids_path)
        self.scan_sav_files()
        return True
    
    def save_screenshots(self):
        """保存截图索引数据"""
        if not self.storage_dir:
            return False
        
        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
        
        self.encode_and_save(self.ids_data, ids_path)
        self.encode_and_save(self.all_ids_data, all_ids_path)
        return True
    
    def sort_by_date(self, ascending=True):
        """按日期排序"""
        self.ids_data.sort(
            key=lambda x: datetime.strptime(x['date'], '%Y/%m/%d %H:%M:%S'),
            reverse=not ascending
        )
        self.all_ids_data = [item['id'] for item in self.ids_data]
        self.save_screenshots()
    
    def move_item(self, from_index, to_index):
        """移动截图位置"""
        if from_index == to_index:
            return
        moved_item = self.ids_data.pop(from_index)
        self.ids_data.insert(to_index, moved_item)
        self.all_ids_data = [item['id'] for item in self.ids_data]
        self.save_screenshots()
    
    def add_screenshot(self, new_id, new_date, new_png_path):
        """添加新截图"""
        if new_id in self.sav_pairs:
            return False, "ID已存在"
        
        # 更新索引
        self.ids_data.append({"id": new_id, "date": new_date})
        self.all_ids_data.append(new_id)
        self.save_screenshots()
        
        # 生成文件
        main_sav_name = f'DevilConnection_photo_{new_id}.sav'
        thumb_sav_name = f'DevilConnection_photo_{new_id}_thumb.sav'
        main_sav = os.path.join(self.storage_dir, main_sav_name)
        thumb_sav = os.path.join(self.storage_dir, thumb_sav_name)
        
        # 获取缩略图尺寸
        thumb_size = self._get_thumb_size()
        
        # 生成主sav (PNG)
        with open(new_png_path, 'rb') as f:
            png_b64 = base64.b64encode(f.read()).decode('utf-8')
        new_main_uri = f"data:image/png;base64,{png_b64}"
        new_main_json = json.dumps(new_main_uri)
        new_main_encoded = urllib.parse.quote(new_main_json)
        with open(main_sav, 'w', encoding='utf-8') as f:
            f.write(new_main_encoded)
        
        # 生成缩略图
        self._create_thumbnail(new_png_path, thumb_sav, thumb_size)
        
        # 更新缓存
        self._file_list_cache = None
        self.scan_sav_files()
        
        return True, "添加成功"
    
    def _get_thumb_size(self):
        """获取缩略图尺寸（从现有文件推断）"""
        thumb_size = (1280, 960)
        for pair in self.sav_pairs.values():
            if pair[1] is not None:
                first_thumb = os.path.join(self.storage_dir, pair[1])
                try:
                    with open(first_thumb, 'r', encoding='utf-8') as f:
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
                    os.remove(temp_thumb)
                    break
                except:
                    pass
        return thumb_size
    
    def _create_thumbnail(self, source_path, thumb_sav_path, thumb_size):
        """创建缩略图"""
        temp_thumb = None
        try:
            main_img = Image.open(source_path)
            new_thumb = main_img.resize(thumb_size, Image.Resampling.BILINEAR)
            new_thumb = new_thumb.convert('RGB')
            temp_thumb = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False).name
            new_thumb.save(temp_thumb, 'JPEG', quality=90, optimize=True)
            main_img.close()
            new_thumb.close()
            
            with open(temp_thumb, 'rb') as f:
                jpeg_b64 = base64.b64encode(f.read()).decode('utf-8')
            new_thumb_uri = f"data:image/jpeg;base64,{jpeg_b64}"
            new_thumb_json = json.dumps(new_thumb_uri)
            new_thumb_encoded = urllib.parse.quote(new_thumb_json)
            with open(thumb_sav_path, 'w', encoding='utf-8') as f:
                f.write(new_thumb_encoded)
        finally:
            if temp_thumb and os.path.exists(temp_thumb):
                try:
                    os.remove(temp_thumb)
                except:
                    pass
    
    def replace_screenshot(self, id_str, new_png_path):
        """替换截图"""
        if id_str not in self.sav_pairs:
            return False, "截图不存在"
        
        pair = self.sav_pairs[id_str]
        if pair[0] is None or pair[1] is None:
            return False, "文件缺失"
        
        main_sav = os.path.join(self.storage_dir, pair[0])
        thumb_sav = os.path.join(self.storage_dir, pair[1])
        
        # 获取原缩略图尺寸
        thumb_size = self._get_thumb_size_from_file(thumb_sav)
        
        # 更新主sav
        with open(new_png_path, 'rb') as f:
            png_b64 = base64.b64encode(f.read()).decode('utf-8')
        new_main_uri = f"data:image/png;base64,{png_b64}"
        new_main_json = json.dumps(new_main_uri)
        new_main_encoded = urllib.parse.quote(new_main_json)
        with open(main_sav, 'w', encoding='utf-8') as f:
            f.write(new_main_encoded)
        
        # 更新缩略图
        self._create_thumbnail(new_png_path, thumb_sav, thumb_size)
        
        return True, "替换成功"
    
    def _get_thumb_size_from_file(self, thumb_sav):
        """从缩略图文件获取尺寸"""
        temp_thumb = None
        try:
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
            size = thumb_orig.size
            thumb_orig.close()
            return size
        except:
            return (1280, 960)
        finally:
            if temp_thumb and os.path.exists(temp_thumb):
                try:
                    os.remove(temp_thumb)
                except:
                    pass
    
    def delete_screenshots(self, id_list):
        """删除截图"""
        deleted_count = 0
        for id_str in id_list:
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
            
            self.ids_data = [item for item in self.ids_data if item['id'] != id_str]
            self.all_ids_data = [item for item in self.all_ids_data if item != id_str]
            
            if id_str in self.sav_pairs:
                del self.sav_pairs[id_str]
        
        self.save_screenshots()
        self._file_list_cache = None
        
        return deleted_count
    
    def get_image_data(self, id_str):
        """获取截图的图片数据"""
        if id_str not in self.sav_pairs:
            return None
        
        main_file = self.sav_pairs[id_str][0]
        if not main_file:
            return None
        
        main_sav = os.path.join(self.storage_dir, main_file)
        if not os.path.exists(main_sav):
            return None
        
        try:
            with open(main_sav, 'r', encoding='utf-8') as f:
                encoded = f.read().strip()
            unquoted = urllib.parse.unquote(encoded)
            data_uri = json.loads(unquoted)
            b64_part = data_uri.split(';base64,', 1)[1]
            return base64.b64decode(b64_part)
        except:
            return None
    
    def generate_id(self):
        """生成随机ID"""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    
    def get_current_datetime(self):
        """获取当前时间字符串"""
        return datetime.now().strftime('%Y/%m/%d %H:%M:%S')


class ScreenshotManagerUI:
    """截图管理UI类，负责截图管理的所有UI界面和工作逻辑"""
    
    def __init__(self, parent_frame, root, storage_dir, translations, current_language, t_func):
        """
        初始化截图管理UI
        
        Args:
            parent_frame: 父框架（screenshot_frame）
            root: 根窗口
            storage_dir: 存储目录
            translations: 翻译字典
            current_language: 当前语言
            t_func: 翻译函数
        """
        self.parent_frame = parent_frame
        self.root = root
        self.storage_dir = storage_dir
        self.translations = translations
        self.current_language = current_language
        self.t = t_func
        
        # 导入样式相关函数
        from styles import get_cjk_font, Colors
        from utils import set_window_icon
        self.get_cjk_font = get_cjk_font
        self.Colors = Colors
        self.set_window_icon = set_window_icon
        
        # 截图管理器实例（处理数据操作）
        self.screenshot_manager = ScreenshotManager()
        
        # 初始化UI
        self._init_ui()
        
        # 如果已有存储目录，加载截图
        if self.storage_dir:
            self.screenshot_manager.set_storage_dir(self.storage_dir)
            self.load_screenshots(silent=True)
    
    def _init_ui(self):
        """初始化UI界面"""
        # 提示标签
        self.hint_label = tk.Label(self.parent_frame, text=self.t("select_dir_hint"), 
                                   fg="#D554BC", font=self.get_cjk_font(10))
        # 只有在 storage_dir 为 None 时才显示提示标签
        if not self.storage_dir:
            self.hint_label.pack(pady=10)
        
        # 成功标签
        self.success_label = tk.Label(self.parent_frame, text="", 
                                      fg="#6DB8AC", font=self.get_cjk_font(10))
        self.success_label_timer = None
        
        # 截图列表头部
        list_header_frame = tk.Frame(self.parent_frame)
        list_header_frame.pack(pady=5, fill="x")
        list_header_frame.columnconfigure(0, weight=1)  
        list_header_frame.columnconfigure(2, weight=1)  
        
        left_spacer = tk.Frame(list_header_frame)
        left_spacer.grid(row=0, column=0, sticky="ew")
        
        # 左侧：标题
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
        list_frame = tk.Frame(self.parent_frame)
        list_frame.pack(pady=5)
        
        # 预览区域（左侧）
        preview_frame = tk.Frame(list_frame, bg=self.Colors.WHITE)
        preview_frame.pack(side="left", padx=5)
        self.preview_label_text = tk.Label(preview_frame, text=self.t("preview"), 
                                          font=self.get_cjk_font(10), bg=self.Colors.WHITE)
        self.preview_label_text.pack()
        
        # 限制预览Label的大小
        preview_container = tk.Frame(preview_frame, width=160, height=120, 
                                    bg=self.Colors.PREVIEW_BG, relief="sunken")
        preview_container.pack()
        preview_container.pack_propagate(False) 
        # 预览 Label
        self.preview_label = Label(preview_container, bg=self.Colors.PREVIEW_BG)
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
        
        # 使用Treeview支持复选框
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
        
        # 配置tag样式
        self.tree.tag_configure("DragIndicatorUp", foreground="#85A9A5")
        self.tree.tag_configure("DragIndicatorDown", foreground="#D06CAA")
        self.tree.tag_configure("NewIndicator", foreground="#FED491")
        self.tree.tag_configure("ReplaceIndicator", foreground="#BDC9B2")
        self.tree.tag_configure("PageHeaderLeft", foreground="#D26FAB", font=self.get_cjk_font(10, "bold"))
        self.tree.tag_configure("PageHeaderRight", foreground="#85A9A5", font=self.get_cjk_font(10, "bold"))
        self.tree.tag_configure("Dragging", background="#E3F2FD", foreground="#1976D2")
        
        scrollbar.config(command=self.tree.yview)
        self.tree.config(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        
        # 创建拖动指示线
        self.drag_indicator_line = tk.Frame(tree_frame, bg="black", height=3)
        self.drag_indicator_line.place_forget()
        
        # 存储复选框状态
        self.checkbox_vars = {}
        
        # 绑定选择事件（用于预览）
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        
        # 拖拽相关变量
        self.drag_start_item = None
        self.drag_start_y = None
        self.is_dragging = False
        self.drag_target_item = None
        self.current_indicator_target = None
        self.current_indicator_position = None
        
        # 箭头指示器相关变量
        self.drag_indicators = []
        
        # 新截图和替换截图的标记相关变量
        self.status_indicators = []
        
        # 绑定事件：统一处理点击事件，先检查复选框，再处理拖拽
        self.tree.bind('<Button-1>', self.on_button1_click)
        self.tree.bind('<B1-Motion>', self.on_drag_motion)
        self.tree.bind('<ButtonRelease-1>', self.on_drag_end)
        
        # 操作按钮
        button_frame = ttk.Frame(self.parent_frame)
        button_frame.pack(pady=5)
        self.add_button = ttk.Button(button_frame, text=self.t("add_new"), command=self.add_new)
        self.add_button.pack(side='left', padx=5)
        self.replace_button = ttk.Button(button_frame, text=self.t("replace_selected"), command=self.replace_selected)
        self.replace_button.pack(side='left', padx=5)
        self.delete_button = ttk.Button(button_frame, text=self.t("delete_selected"), command=self.delete_selected)
        self.delete_button.pack(side='left', padx=5)
        self.gallery_preview_button = ttk.Button(button_frame, text=self.t("gallery_preview"), command=self.show_gallery_preview)
        self.gallery_preview_button.pack(side='left', padx=5)
        
        # 添加图片缓存字典
        self.image_cache = {}
        self.cache_lock = threading.Lock()
    
    def set_storage_dir(self, storage_dir):
        """设置存储目录"""
        self.storage_dir = storage_dir
        if self.storage_dir:
            self.screenshot_manager.set_storage_dir(self.storage_dir)
            self.hint_label.pack_forget()
        else:
            self.hint_label.pack(pady=10)
    
    def update_ui_texts(self):
        """更新UI文本"""
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
    
    def load_screenshots(self, silent=False):
        """加载截图列表"""
        if not self.storage_dir:
            return
        
        # 设置screenshot_manager的存储目录并加载数据
        self.screenshot_manager.set_storage_dir(self.storage_dir)
        
        if not self.screenshot_manager.load_screenshots():
            if not silent:
                messagebox.showerror(self.t("error"), self.t("missing_files"))
            return
        
        # 隐藏提示标签（因为已经成功加载）
        self.hint_label.pack_forget()
        
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
        
        # 添加复选框和项目，每6个截图插入一个标题行
        screenshot_count = 0
        page_number = 1
        
        for idx, item in enumerate(self.screenshot_manager.ids_data):
            # 每12个截图的开始插入"页面X ←"标题行
            if screenshot_count % 12 == 0:
                page_text_left = f"{self.t('page')} {page_number} ←"
                header_item_id_left = self.tree.insert("", tk.END, text="",
                                                      values=("", page_text_left),
                                                      tags=("PageHeaderLeft",))
            
            id_str = item['id']
            date_str = item['date']
            main_file = self.screenshot_manager.sav_pairs.get(id_str, [None, None])[0] or self.t("missing_main_file")
            display = f"{id_str} - {main_file} - {date_str}"
            
            # 创建复选框变量
            var = tk.BooleanVar()
            var.trace('w', lambda *args, v=var, iid=id_str: self.on_checkbox_change(v, iid))
            
            # 插入Treeview项目
            item_id = self.tree.insert("", tk.END, text="", values=("", display), tags=(id_str,))
            self.checkbox_vars[item_id] = (var, id_str)
            
            # 更新复选框显示
            self.update_checkbox_display(item_id)
            
            screenshot_count += 1
            
            # 每6个截图后插入"页面X →"标题行
            if screenshot_count % 6 == 0 and screenshot_count % 12 != 0:
                page_text_right = f"{self.t('page')} {page_number} →"
                header_item_id_right = self.tree.insert("", tk.END, text="", 
                                                       values=("", page_text_right), 
                                                       tags=("PageHeaderRight",))
            
            # 每12个截图后，页面号递增
            if screenshot_count % 12 == 0:
                page_number += 1
        
        # 更新全选标题显示
        self.update_select_all_header()
    
    def sort_ascending(self):
        """按时间正序排序"""
        if not self.storage_dir:
            messagebox.showerror(self.t("error"), self.t("select_dir_hint"))
            return
        
        # 确认对话框
        result = messagebox.askyesno(
            self.t("confirm_sort"),
            self.t("sort_warning"),
            icon='warning'
        )
        
        if not result:
            return
        
        # 委托给screenshot_manager排序
        self.screenshot_manager.sort_by_date(ascending=True)
        
        # 重新加载列表以更新显示
        self.load_screenshots()
        
        messagebox.showinfo(self.t("success"), self.t("sort_asc_success"))
    
    def sort_descending(self):
        """按时间倒序排序"""
        if not self.storage_dir:
            messagebox.showerror(self.t("error"), self.t("select_dir_hint"))
            return
        
        # 确认对话框
        result = messagebox.askyesno(
            self.t("confirm_sort"),
            self.t("sort_warning"),
            icon='warning'
        )
        
        if not result:
            return
        
        # 委托给screenshot_manager排序
        self.screenshot_manager.sort_by_date(ascending=False)
        
        # 重新加载列表以更新显示
        self.load_screenshots()
        
        messagebox.showinfo(self.t("success"), self.t("sort_desc_success"))
    
    def update_checkbox_display(self, item_id):
        """更新复选框显示"""
        if item_id in self.checkbox_vars:
            var, id_str = self.checkbox_vars[item_id]
            checkbox_text = "☑" if var.get() else "☐"
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
        self.update_select_all_header()
    
    def toggle_select_all(self):
        """全选/取消全选"""
        if not self.checkbox_vars:
            return
        
        all_selected = all(var.get() for var, _ in self.checkbox_vars.values())
        select_all = not all_selected
        
        for var, _ in self.checkbox_vars.values():
            var.set(select_all)
        for item_id in self.checkbox_vars.keys():
            self.update_checkbox_display(item_id)
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
        # 替换功能不依赖复选框状态，所以不需要禁用替换按钮
        pass
    
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
            self.preview_label.config(image='', bg="lightgray")
            self.preview_photo = None
            self.export_button.pack_forget()
            return
        
        item_id = selected[0]
        item_tags = self.tree.item(item_id, "tags")
        if item_tags and ("PageHeaderLeft" in item_tags or "PageHeaderRight" in item_tags):
            self.tree.selection_remove(item_id)
            return
        
        if item_id in self.checkbox_vars:
            _, id_str = self.checkbox_vars[item_id]
            self.show_preview(id_str)
            self.export_button.pack(pady=5)
    
    def on_button1_click(self, event):
        """统一处理Button-1点击事件：先检查复选框，再处理拖拽"""
        region = self.tree.identify_region(event.x, event.y)
        
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == "#1" or (event.x < 40 and event.x > 0):
                item_id = self.tree.identify_row(event.y)
                if item_id:
                    item_tags = self.tree.item(item_id, "tags")
                    if item_tags and ("PageHeaderLeft" in item_tags or "PageHeaderRight" in item_tags):
                        return "break"
                    if item_id in self.checkbox_vars:
                        var, _ = self.checkbox_vars[item_id]
                        var.set(not var.get())
                        return "break"
        elif region == "heading":
            column = self.tree.identify_column(event.x)
            if column == "#1" or (event.x < 40 and event.x > 0):
                self.drag_start_item = None
                self.drag_target_item = None
                return
        
        item = self.tree.identify_row(event.y)
        if item:
            item_tags = self.tree.item(item, "tags")
            if item_tags and ("PageHeaderLeft" in item_tags or "PageHeaderRight" in item_tags):
                self.drag_start_item = None
                self.drag_target_item = None
                return
            self.drag_start_item = item
            self.drag_start_y = event.y
            self.drag_target_item = None
            self.is_dragging = False
    
    def on_drag_motion(self, event):
        """拖拽过程中，检测是否真的在拖拽，并显示视觉反馈"""
        if self.drag_start_item is None:
            return
        
        if abs(event.y - self.drag_start_y) > 5:
            self.is_dragging = True
            
            if self.tree.exists(self.drag_start_item):
                current_tags = list(self.tree.item(self.drag_start_item, "tags"))
                if "Dragging" not in current_tags:
                    current_tags.append("Dragging")
                    self.tree.item(self.drag_start_item, tags=tuple(current_tags))
            
            target_item = self.tree.identify_row(event.y)
            self.drag_target_item = target_item
            
            children = list(self.tree.get_children())
            if self.drag_start_item in children and target_item in children:
                start_index = children.index(self.drag_start_item)
                target_index = children.index(target_item)
                is_dragging_down = target_index > start_index
            else:
                if self.tree.exists(self.drag_start_item):
                    start_bbox = self.tree.bbox(self.drag_start_item)
                    if start_bbox:
                        is_dragging_down = event.y > start_bbox[1] + start_bbox[3] / 2
                    else:
                        is_dragging_down = True
                else:
                    is_dragging_down = True
            
            if target_item and target_item != self.drag_start_item:
                target_tags = self.tree.item(target_item, "tags")
                if target_tags and ("PageHeaderLeft" in target_tags or "PageHeaderRight" in target_tags):
                    self.drag_target_item = None
                    self.drag_indicator_line.place_forget()
                    self.current_indicator_target = None
                    self.current_indicator_position = None
                else:
                    self.show_drag_indicator_line(target_item, is_dragging_down)
            else:
                self.drag_target_item = None
                self.drag_indicator_line.place_forget()
                self.current_indicator_target = None
                self.current_indicator_position = None
    
    def show_drag_indicator_line(self, target_item, is_dragging_down):
        """显示拖动指示线"""
        if not self.tree.exists(target_item):
            self.drag_indicator_line.place_forget()
            self.current_indicator_target = None
            self.current_indicator_position = None
            return
        
        self.drag_indicator_line.place_forget()
        
        bbox = self.tree.bbox(target_item)
        if not bbox:
            self.current_indicator_target = None
            self.current_indicator_position = None
            return
        
        x, y, width, height = bbox
        tree_x = self.tree.winfo_x()
        tree_y = self.tree.winfo_y()
        
        if is_dragging_down:
            line_y = tree_y + y + height
        else:
            line_y = tree_y + y
        
        if (self.current_indicator_target == target_item and 
            self.current_indicator_position == line_y):
            tree_width = self.tree.winfo_width()
            self.drag_indicator_line.place(x=tree_x, y=line_y, width=tree_width, height=3)
            self.drag_indicator_line.lift()
            return
        
        self.current_indicator_target = target_item
        self.current_indicator_position = line_y
        tree_width = self.tree.winfo_width()
        self.drag_indicator_line.place(x=tree_x, y=line_y, width=tree_width, height=3)
        self.drag_indicator_line.lift()
    
    def on_drag_end(self, event):
        """结束拖拽，移动项目并保存顺序"""
        if self.drag_start_item and self.tree.exists(self.drag_start_item):
            start_tags = list(self.tree.item(self.drag_start_item, "tags"))
            if "Dragging" in start_tags:
                start_tags.remove("Dragging")
                self.tree.item(self.drag_start_item, tags=tuple(start_tags))
        
        self.drag_indicator_line.place_forget()
        self.current_indicator_target = None
        self.current_indicator_position = None
        
        if self.drag_start_item is None:
            self.drag_target_item = None
            return
        
        if not self.is_dragging:
            self.drag_start_item = None
            self.drag_start_y = None
            self.drag_target_item = None
            self.is_dragging = False
            return
        
        end_item = self.drag_target_item if self.drag_target_item else self.tree.identify_row(event.y)
        
        if not end_item or end_item == self.drag_start_item:
            self.drag_start_item = None
            self.drag_start_y = None
            self.drag_target_item = None
            self.is_dragging = False
            return
        
        start_tags = self.tree.item(self.drag_start_item, "tags")
        end_tags = self.tree.item(end_item, "tags")
        if (start_tags and ("PageHeaderLeft" in start_tags or "PageHeaderRight" in start_tags)) or \
           (end_tags and ("PageHeaderLeft" in end_tags or "PageHeaderRight" in end_tags)):
            self.drag_start_item = None
            self.drag_start_y = None
            self.drag_target_item = None
            self.is_dragging = False
            return
        
        children = list(self.tree.get_children())
        
        def get_data_index(tree_index):
            data_index = 0
            for i in range(tree_index):
                item_id = children[i]
                item_tags = self.tree.item(item_id, "tags")
                if item_tags and ("PageHeaderLeft" not in item_tags and "PageHeaderRight" not in item_tags):
                    data_index += 1
            return data_index
        
        start_tree_index = children.index(self.drag_start_item)
        end_tree_index = children.index(end_item)
        start_index = get_data_index(start_tree_index)
        end_index = get_data_index(end_tree_index)
        
        self.clear_drag_indicators()
        
        item_values = self.tree.item(self.drag_start_item)
        moved_item_id = item_values['tags'][0] if item_values['tags'] else None
        
        checkbox_data = None
        if self.drag_start_item in self.checkbox_vars:
            checkbox_data = self.checkbox_vars.pop(self.drag_start_item)
        
        current_values = list(item_values['values'])
        self.tree.delete(self.drag_start_item)
        children = list(self.tree.get_children())
        
        if end_tree_index > start_tree_index:
            insert_index = end_tree_index
            if insert_index < 0:
                insert_index = 0
            if insert_index <= len(children):
                new_item = self.tree.insert("", insert_index, text=item_values['text'], values=tuple(current_values), tags=item_values['tags'])
            else:
                new_item = self.tree.insert("", tk.END, text=item_values['text'], values=tuple(current_values), tags=item_values['tags'])
        else:
            if end_tree_index <= len(children):
                new_item = self.tree.insert("", end_tree_index, text=item_values['text'], values=tuple(current_values), tags=item_values['tags'])
            else:
                new_item = self.tree.insert("", tk.END, text=item_values['text'], values=tuple(current_values), tags=item_values['tags'])
        
        if checkbox_data:
            self.checkbox_vars[new_item] = checkbox_data
            self.update_checkbox_display(new_item)
        
        self.screenshot_manager.move_item(start_index, end_index)
        moved_id = moved_item_id
        is_moving_down = end_index > start_index
        
        def get_tree_index(data_index):
            tree_index = 0
            data_count = 0
            for i, item_id in enumerate(children):
                item_tags = self.tree.item(item_id, "tags")
                if item_tags and ("PageHeaderLeft" not in item_tags and "PageHeaderRight" not in item_tags):
                    if data_count == data_index:
                        return i
                    data_count += 1
            return len(children)
        
        self.load_screenshots()
        
        moved_item = None
        if moved_id:
            children = list(self.tree.get_children())
            for tree_item_id in children:
                item_tags = self.tree.item(tree_item_id, "tags")
                if item_tags and item_tags[0] == moved_id:
                    moved_item = tree_item_id
                    self.tree.selection_set(tree_item_id)
                    self.tree.see(tree_item_id)
                    break
        
        children = list(self.tree.get_children())
        
        if moved_item:
            self.show_drag_indicator_on_item(moved_item, not is_moving_down)
        
        def get_tree_index_after_reload(data_index):
            tree_index = 0
            data_count = 0
            for i, item_id in enumerate(children):
                item_tags = self.tree.item(item_id, "tags")
                if item_tags and ("PageHeaderLeft" not in item_tags and "PageHeaderRight" not in item_tags):
                    if data_count == data_index:
                        return i
                    data_count += 1
            return len(children)
        
        start_tree_idx_after_reload = get_tree_index_after_reload(start_index)
        if start_tree_idx_after_reload < len(children):
            item_at_start_pos = children[start_tree_idx_after_reload]
            item_tags = self.tree.item(item_at_start_pos, "tags")
            if item_tags and item_tags[0] != moved_id:
                self.show_drag_indicator_on_item(item_at_start_pos, is_moving_down)
        
        self.drag_start_item = None
        self.drag_start_y = None
        self.drag_target_item = None
        self.is_dragging = False
    
    def clear_drag_indicators(self):
        """清除所有箭头指示器"""
        for item_id, original_text, after_id in self.drag_indicators:
            try:
                if after_id:
                    self.root.after_cancel(after_id)
                if self.tree.exists(item_id):
                    current_values = list(self.tree.item(item_id, "values"))
                    if len(current_values) >= 2:
                        info_text = current_values[1]
                        if info_text.startswith("↑↑↑"):
                            info_text = info_text[3:].lstrip()
                        elif info_text.startswith("↓↓↓"):
                            info_text = info_text[3:].lstrip()
                        current_values[1] = info_text
                        self.tree.item(item_id, values=tuple(current_values))
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
        
        current_values = list(self.tree.item(item_id, "values"))
        if len(current_values) < 2:
            return
        
        original_text = current_values[1]
        
        if show_up_arrows:
            arrow_prefix = "↑↑↑"
            style_tag = "DragIndicatorDown"
        else:
            arrow_prefix = "↓↓↓"
            style_tag = "DragIndicatorUp"
        
        new_text = f"{arrow_prefix} {original_text}"
        current_values[1] = new_text
        
        current_tags = list(self.tree.item(item_id, "tags"))
        if style_tag not in current_tags:
            current_tags.append(style_tag)
        self.tree.item(item_id, values=tuple(current_values), tags=tuple(current_tags))
        
        def remove_indicator():
            try:
                if self.tree.exists(item_id):
                    current_values = list(self.tree.item(item_id, "values"))
                    if len(current_values) >= 2:
                        info_text = current_values[1]
                        if info_text.startswith("↑↑↑"):
                            info_text = info_text[3:].lstrip()
                        elif info_text.startswith("↓↓↓"):
                            info_text = info_text[3:].lstrip()
                        current_values[1] = info_text
                        self.tree.item(item_id, values=tuple(current_values))
                        current_tags = list(self.tree.item(item_id, "tags"))
                        if "DragIndicatorUp" in current_tags:
                            current_tags.remove("DragIndicatorUp")
                        if "DragIndicatorDown" in current_tags:
                            current_tags.remove("DragIndicatorDown")
                        self.tree.item(item_id, tags=tuple(current_tags))
                self.drag_indicators = [(iid, orig, aid) for iid, orig, aid in self.drag_indicators if iid != item_id]
            except:
                pass
        
        after_id = self.root.after(15000, remove_indicator)
        self.drag_indicators.append((item_id, original_text, after_id))
    
    def show_status_indicator(self, id_str, is_new=True):
        """在指定ID的截图名称前显示状态指示器（新截图或替换截图）"""
        item_id = None
        for tree_item_id in self.tree.get_children():
            item_tags = self.tree.item(tree_item_id, "tags")
            if item_tags and item_tags[0] == id_str:
                item_id = tree_item_id
                break
        
        if not item_id or not self.tree.exists(item_id):
            return
        
        current_values = list(self.tree.item(item_id, "values"))
        if len(current_values) < 2:
            return
        
        original_text = current_values[1]
        
        if is_new:
            indicator_prefix = "⚝ "
            style_tag = "NewIndicator"
        else:
            indicator_prefix = "✧ "
            style_tag = "ReplaceIndicator"
        
        info_text = current_values[1]
        if info_text.startswith("⚝ ") or info_text.startswith("✧ "):
            if info_text.startswith("⚝ "):
                info_text = info_text[2:].lstrip()
            elif info_text.startswith("✧ "):
                info_text = info_text[2:].lstrip()
            original_text = info_text
        
        new_text = f"{indicator_prefix}{original_text}"
        current_values[1] = new_text
        
        current_tags = list(self.tree.item(item_id, "tags"))
        if style_tag not in current_tags:
            current_tags.append(style_tag)
        self.tree.item(item_id, values=tuple(current_values), tags=tuple(current_tags))
        
        def remove_indicator():
            try:
                if self.tree.exists(item_id):
                    current_values = list(self.tree.item(item_id, "values"))
                    if len(current_values) >= 2:
                        info_text = current_values[1]
                        if info_text.startswith("⚝ "):
                            info_text = info_text[2:].lstrip()
                        elif info_text.startswith("✧ "):
                            info_text = info_text[2:].lstrip()
                        current_values[1] = info_text
                        self.tree.item(item_id, values=tuple(current_values))
                        current_tags = list(self.tree.item(item_id, "tags"))
                        if "NewIndicator" in current_tags:
                            current_tags.remove("NewIndicator")
                        if "ReplaceIndicator" in current_tags:
                            current_tags.remove("ReplaceIndicator")
                        self.tree.item(item_id, tags=tuple(current_tags))
                self.status_indicators = [(iid, orig, aid, itype) for iid, orig, aid, itype in self.status_indicators if iid != item_id]
            except:
                pass
        
        after_id = self.root.after(15000, remove_indicator)
        self.status_indicators.append((item_id, original_text, after_id, "new" if is_new else "replace"))
    
    def show_preview(self, id_str):
        """显示指定ID的预览图片"""
        if not self.storage_dir or id_str not in self.screenshot_manager.sav_pairs:
            self.preview_label.config(image='', bg="lightgray")
            self.preview_photo = None
            return
        
        main_file = self.screenshot_manager.sav_pairs[id_str][0]
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
            with open(main_sav, 'r', encoding='utf-8') as f:
                encoded = f.read().strip()
            unquoted = urllib.parse.unquote(encoded)
            data_uri = json.loads(unquoted)
            b64_part = data_uri.split(';base64,', 1)[1]
            img_data = base64.b64decode(b64_part)
            
            temp_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
            with open(temp_png, 'wb') as f:
                f.write(img_data)
            
            img = Image.open(temp_png)
            try:
                preview_img = img.resize((160, 120), Image.Resampling.BILINEAR)
                photo = ImageTk.PhotoImage(preview_img)
                
                self.preview_label.config(image=photo, bg=self.Colors.WHITE, text="")
                self.preview_photo = photo
            finally:
                img.close()
                preview_img.close()
        except Exception as e:
            self.preview_label.config(image='', bg="lightgray", text=self.t("preview_failed"))
            self.preview_photo = None
        finally:
            if temp_png and os.path.exists(temp_png):
                try:
                    os.remove(temp_png)
                except:
                    pass
    
    def show_gallery_preview(self):
        """显示画廊预览窗口，按照特定方式排列图片（分页显示）"""
        if not self.storage_dir or not self.screenshot_manager.ids_data:
            messagebox.showerror(self.t("error"), self.t("select_dir_hint"))
            return
        
        gallery_window = Toplevel(self.root)
        gallery_window.title(self.t("gallery_preview"))
        gallery_window.geometry("800x600")
        
        self.set_window_icon(gallery_window)
        
        # 主容器
        main_container = tk.Frame(gallery_window, bg=self.Colors.WHITE)
        main_container.pack(fill="both", expand=True)
        
        # 图片显示区域
        image_frame = tk.Frame(main_container, bg=self.Colors.WHITE)
        image_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        image_ids = [item['id'] for item in self.screenshot_manager.ids_data]
        total_images = len(image_ids)
        
        rows_per_page = 3
        cols_per_page = 4
        images_per_page = rows_per_page * cols_per_page
        total_pages = (total_images + images_per_page - 1) // images_per_page if total_images > 0 else 1
        
        # 当前页码（从1开始）
        current_page = tk.IntVar(value=1)
        
        # 存储每页的框架和占位符
        gallery_window.page_frames = {}
        gallery_window.placeholders = {}
        gallery_window.image_refs = []
        gallery_window.loaded_pages = set()  # 记录已加载的页面
        
        def create_page_frame(page_num):
            """创建指定页面的框架"""
            page_frame = tk.Frame(image_frame, bg=self.Colors.WHITE)
            page_frame.place(x=0, y=0, relwidth=1, relheight=1)
            
            for row in range(rows_per_page):
                row_frame = tk.Frame(page_frame, bg=self.Colors.WHITE)
                row_frame.pack(side="top", pady=5)
                
                for col in range(cols_per_page):
                    image_idx = (page_num - 1) * images_per_page + row + col * rows_per_page
                    
                    col_frame = tk.Frame(row_frame, bg=self.Colors.WHITE)
                    col_frame.pack(side="left", padx=5)
                    
                    if image_idx < total_images:
                        id_str = image_ids[image_idx]
                        placeholder_container, placeholder_label = self.create_placeholder(col_frame)
                        gallery_window.placeholders[id_str] = (placeholder_container, placeholder_label, col_frame)
                    else:
                        placeholder_container = tk.Frame(col_frame, bg="lightgray", width=150, height=112)
                        placeholder_container.pack()
                        placeholder_container.pack_propagate(False)
                        placeholder_label = tk.Label(placeholder_container, text=self.t("not_available"), 
                                                    bg="lightgray", fg="gray", font=self.get_cjk_font(14, "bold"),
                                                    anchor="center", justify="center")
                        placeholder_label.place(relx=0.5, rely=0.5, anchor="center")
                        placeholder_id_label = tk.Label(col_frame, text="", bg=self.Colors.WHITE, font=self.get_cjk_font(8))
                        placeholder_id_label.pack()
                    
                    if col == 1:
                        separator = tk.Frame(row_frame, width=3, bg="gray", relief="sunken")
                        separator.pack(side="left", fill="y", padx=5)
            
            return page_frame
        
        def load_page_images(page_num):
            """加载指定页面的图片"""
            if page_num in gallery_window.loaded_pages:
                return  # 已经加载过
            
            start_idx = (page_num - 1) * images_per_page
            end_idx = min(start_idx + images_per_page, total_images)
            page_image_ids = image_ids[start_idx:end_idx]
            
            if not page_image_ids:
                return
            
            gallery_window.loaded_pages.add(page_num)
            self.load_gallery_images_async(gallery_window, page_image_ids)
        
        def show_page(page_num):
            """显示指定页面"""
            if page_num < 1 or page_num > total_pages:
                return
            
            # 隐藏所有页面
            for frame in gallery_window.page_frames.values():
                frame.place_forget()
            
            # 创建或显示目标页面
            if page_num not in gallery_window.page_frames:
                gallery_window.page_frames[page_num] = create_page_frame(page_num)
            
            gallery_window.page_frames[page_num].place(x=0, y=0, relwidth=1, relheight=1)
            current_page.set(page_num)
            
            # 加载该页图片
            load_page_images(page_num)
            
            # 更新导航栏
            update_navigation()
        
        def update_navigation():
            """更新导航栏显示"""
            page_info_label.config(text=f"{current_page.get()}/{total_pages}")
            prev_button.config(state="normal" if current_page.get() > 1 else "disabled")
            next_button.config(state="normal" if current_page.get() < total_pages else "disabled")
        
        def go_to_prev_page():
            """上一页"""
            if current_page.get() > 1:
                show_page(current_page.get() - 1)
        
        def go_to_next_page():
            """下一页"""
            if current_page.get() < total_pages:
                show_page(current_page.get() + 1)
        
        def jump_to_page():
            """跳转到指定页面"""
            try:
                target_page = int(jump_entry.get())
                if 1 <= target_page <= total_pages:
                    show_page(target_page)
                    jump_entry.delete(0, tk.END)
                else:
                    messagebox.showwarning(self.t("warning"), 
                                         self.t("invalid_page_number").format(min=1, max=total_pages),
                                         parent=gallery_window)
            except ValueError:
                messagebox.showwarning(self.t("warning"), self.t("invalid_page_input"),
                                     parent=gallery_window)
        
        # 底部导航栏
        nav_frame = tk.Frame(main_container, bg=self.Colors.WHITE)
        nav_frame.pack(side="bottom", fill="x", pady=10)
        
        # 创建居中容器
        nav_center_frame = tk.Frame(nav_frame, bg=self.Colors.WHITE)
        nav_center_frame.pack(anchor="center")
        
        # 上一页按钮
        prev_button = ttk.Button(nav_center_frame, text=self.t("prev_page"), command=go_to_prev_page)
        prev_button.pack(side="left", padx=5)
        
        # 页面信息
        page_info_label = tk.Label(nav_center_frame, text="1/1", font=self.get_cjk_font(12), bg=self.Colors.WHITE)
        page_info_label.pack(side="left", padx=10)
        
        # 下一页按钮
        next_button = ttk.Button(nav_center_frame, text=self.t("next_page"), command=go_to_next_page)
        next_button.pack(side="left", padx=5)
        
        # 跳转输入区域
        jump_frame = tk.Frame(nav_center_frame, bg=self.Colors.WHITE)
        jump_frame.pack(side="left", padx=20)
        
        jump_label = tk.Label(jump_frame, text=self.t("jump_to_page"), font=self.get_cjk_font(10), bg=self.Colors.WHITE)
        jump_label.pack(side="left", padx=5)
        
        jump_entry = Entry(jump_frame, width=10)
        jump_entry.pack(side="left", padx=5)
        jump_entry.bind('<Return>', lambda e: jump_to_page())
        
        jump_button = ttk.Button(jump_frame, text=self.t("jump"), command=jump_to_page)
        jump_button.pack(side="left", padx=5)
        
        def on_window_close():
            gallery_window.destroy()
        
        gallery_window.protocol("WM_DELETE_WINDOW", on_window_close)
        
        # 显示第一页
        show_page(1)
    
    def create_placeholder(self, parent_frame):
        """创建加载中的占位符"""
        placeholder_container = tk.Frame(parent_frame, bg="lightgray", width=150, height=112)
        placeholder_container.pack()
        placeholder_container.pack_propagate(False)
        
        placeholder_label = tk.Label(placeholder_container, text=self.t("loading"), 
                                    bg="lightgray", fg="gray", font=self.get_cjk_font(10),
                                    anchor="center", justify="center")
        placeholder_label.place(relx=0.5, rely=0.5, anchor="center")
        
        placeholder_id_label = tk.Label(parent_frame, text="", bg=self.Colors.WHITE, font=self.get_cjk_font(8))
        placeholder_id_label.pack()
        
        return placeholder_container, placeholder_label
    
    def load_gallery_images_async(self, gallery_window, image_ids):
        """异步加载指定图片列表"""
        def load_single_image(id_str):
            with self.cache_lock:
                if id_str in self.image_cache:
                    cached_img = self.image_cache[id_str]
                    if isinstance(cached_img, Image.Image):
                        return id_str, cached_img
            
            if id_str not in self.screenshot_manager.sav_pairs:
                return id_str, None
            
            thumb_file = self.screenshot_manager.sav_pairs[id_str][1]
            main_file = self.screenshot_manager.sav_pairs[id_str][0]
            
            sav_file = None
            if thumb_file:
                thumb_path = os.path.join(self.storage_dir, thumb_file)
                if os.path.exists(thumb_path):
                    sav_file = thumb_path
            
            if not sav_file and main_file:
                main_path = os.path.join(self.storage_dir, main_file)
                if os.path.exists(main_path):
                    sav_file = main_path
            
            if not sav_file:
                return id_str, None
            
            try:
                with open(sav_file, 'r', encoding='utf-8') as f:
                    encoded = f.read().strip()
                unquoted = urllib.parse.unquote(encoded)
                data_uri = json.loads(unquoted)
                b64_part = data_uri.split(';base64,', 1)[1]
                img_data = base64.b64decode(b64_part)
                
                img = Image.open(BytesIO(img_data))
                try:
                    preview_img = img.resize((150, 112), Image.Resampling.BILINEAR)
                    with self.cache_lock:
                        self.image_cache[id_str] = preview_img.copy()
                    return id_str, preview_img
                finally:
                    img.close()
            except Exception as e:
                return id_str, None
        
        def update_image(id_str, pil_image):
            if id_str not in gallery_window.placeholders:
                return
            
            placeholder_container, placeholder_label, col_frame = gallery_window.placeholders[id_str]
            
            if pil_image is None:
                placeholder_label.config(text=self.t("preview_failed"), bg="lightgray", fg="red")
                return
            
            try:
                photo = ImageTk.PhotoImage(pil_image)
                gallery_window.image_refs.append(photo)
                placeholder_container.destroy()
                img_label = tk.Label(col_frame, image=photo, bg=self.Colors.WHITE, text=id_str, 
                                    compound="top", font=self.get_cjk_font(8))
                img_label.pack()
            except Exception as e:
                placeholder_label.config(text=self.t("preview_failed"), bg="lightgray", fg="red")
        
        def process_results():
            if not image_ids:
                return
            max_workers = min(8, len(image_ids))
            executor = ThreadPoolExecutor(max_workers=max_workers)
            
            try:
                future_to_id = {executor.submit(load_single_image, id_str): id_str 
                                for id_str in image_ids}
                
                for future in as_completed(future_to_id):
                    try:
                        id_str, pil_image = future.result()
                        gallery_window.after(0, update_image, id_str, pil_image)
                    except Exception as e:
                        pass
            finally:
                executor.shutdown(wait=False)
        
        thread = threading.Thread(target=process_results, daemon=True)
        thread.start()
    
    def replace_selected(self):
        """替换选中的截图（使用Treeview的选中项，不是复选框）"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning(self.t("warning"), self.t("select_screenshot"))
            return
        
        item_id = selected[0]
        if item_id not in self.checkbox_vars:
            messagebox.showerror(self.t("error"), self.t("invalid_selection"))
            return
        
        _, id_str = self.checkbox_vars[item_id]
        
        # 检查文件是否存在
        pair = self.screenshot_manager.sav_pairs.get(id_str, [None, None])
        if pair[0] is None or pair[1] is None:
            messagebox.showerror(self.t("error"), self.t("file_missing"))
            return
        
        main_sav = os.path.join(self.storage_dir, pair[0])
        thumb_sav = os.path.join(self.storage_dir, pair[1])
        
        if not os.path.exists(main_sav) or not os.path.exists(thumb_sav):
            messagebox.showerror(self.t("error"), self.t("file_not_exist"))
            return
        
        # 选择新图片文件
        new_png_path = filedialog.askopenfilename(
            title=self.t("select_new_image"),
            filetypes=[("Image files", "*.png *.jpg *.jpeg"), ("PNG files", "*.png"), ("All files", "*.*")]
        )
        
        if not new_png_path:
            return
        
        # 检查文件扩展名
        valid_image_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tiff', '.tif', '.ico'}
        file_ext = os.path.splitext(new_png_path)[1].lower()
        filename = os.path.basename(new_png_path)
        is_valid_image = file_ext in valid_image_extensions
        
        # 解码主 .sav 获取原PNG数据
        temp_png = None
        try:
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
        except Exception as e:
            messagebox.showerror(self.t("error"), self.t("file_not_found"))
            return
        
        # 确认替换窗口（带预览）
        popup = Toplevel(self.root)
        popup.title(self.t("replace_warning"))
        popup.geometry("900x500")
        self.set_window_icon(popup)
        popup.transient(self.root)
        popup.grab_set()
        
        # 如果不是常规图片格式，在窗口顶端显示警告
        if not is_valid_image:
            warning_label = tk.Label(popup, text=self.t("file_extension_warning", filename=filename), 
                                    fg="#FF57FD", font=self.get_cjk_font(10), wraplength=600, justify="left")
            warning_label.pack(pady=5, padx=10, anchor="w")
        
        ttk.Label(popup, text=self.t("replace_confirm_text"), font=self.get_cjk_font(12)).pack(pady=10)
        
        # 图片对比区域
        image_frame = tk.Frame(popup)
        image_frame.pack(pady=10)
        
        # 原图片（左侧）
        orig_img = None
        orig_photo = None
        try:
            orig_img = Image.open(temp_png)
            # 使用BILINEAR而不是LANCZOS，速度更快，预览质量足够
            orig_preview = orig_img.resize((400, 300), Image.Resampling.BILINEAR)
            orig_photo = ImageTk.PhotoImage(orig_preview)
            orig_label = Label(image_frame, image=orig_photo)
            orig_label.pack(side="left", padx=10)
            popup.orig_photo = orig_photo  # 保持引用
        except Exception as e:
            error_label = Label(image_frame, text=self.t("preview_failed"), fg="red", font=self.get_cjk_font(12))
            error_label.pack(side="left", padx=10)
            popup.orig_photo = None
        finally:
            if orig_img:
                orig_img.close()
                if 'orig_preview' in locals():
                    orig_preview.close()
        
        # 箭头
        ttk.Label(image_frame, text="→", font=self.get_cjk_font(24)).pack(side="left", padx=10)
        
        # 新图片（右侧）
        new_img = None
        new_photo = None
        try:
            new_img = Image.open(new_png_path)
            # 使用BILINEAR而不是LANCZOS，速度更快，预览质量足够
            new_preview = new_img.resize((400, 300), Image.Resampling.BILINEAR)
            new_photo = ImageTk.PhotoImage(new_preview)
            new_label = Label(image_frame, image=new_photo)
            new_label.pack(side="left", padx=10)
            popup.new_photo = new_photo  # 保持引用
        except Exception as e:
            error_label = Label(image_frame, text=self.t("preview_failed"), fg="red", font=self.get_cjk_font(12))
            error_label.pack(side="left", padx=10)
            popup.new_photo = None
        finally:
            if new_img:
                new_img.close()
                if 'new_preview' in locals():
                    new_preview.close()
        
        ttk.Label(popup, text=self.t("replace_confirm_question")).pack(pady=10)
        
        confirmed = False
        
        def yes():
            nonlocal confirmed
            confirmed = True
            popup.destroy()
        
        def no():
            popup.destroy()
        
        button_frame = tk.Frame(popup)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text=self.t("replace_yes"), command=yes).pack(side="left", padx=10)
        ttk.Button(button_frame, text=self.t("replace_no"), command=no).pack(side="right", padx=10)
        
        # 绑定回车键和ESC键
        popup.bind('<Return>', lambda e: yes())
        popup.bind('<Escape>', lambda e: no())
        
        # 等待窗口关闭
        self.root.wait_window(popup)
        
        # 清理临时文件
        if temp_png and os.path.exists(temp_png):
            try:
                os.remove(temp_png)
            except:
                pass
        
        if not confirmed:
            return
        
        # 执行替换
        success, message = self.replace_sav(main_sav, thumb_sav, new_png_path)
        
        if success:
            messagebox.showinfo(self.t("success"), self.t("replace_success").format(id=id_str))
            self.load_screenshots()
            self.show_status_indicator(id_str, is_new=False)
        else:
            messagebox.showerror(self.t("error"), message)
    
    def replace_sav(self, main_sav, thumb_sav, new_png):
        """替换sav文件"""
        try:
            success, message = self.screenshot_manager.replace_screenshot(
                os.path.basename(main_sav).replace('DevilConnection_photo_', '').replace('.sav', ''),
                new_png
            )
            return success, message
        except Exception as e:
            return False, str(e)
    
    def add_new(self):
        """添加新截图"""
        # 先选择图片文件
        new_png_path = filedialog.askopenfilename(
            title=self.t("select_new_png"),
            filetypes=[("Image files", "*.png *.jpg *.jpeg"), ("PNG files", "*.png"), ("All files", "*.*")]
        )
        
        if not new_png_path:
            return
        
        # 检查文件扩展名
        filename = os.path.basename(new_png_path)
        ext = os.path.splitext(filename)[1].lower()
        is_valid_image = ext in ['.png', '.jpg', '.jpeg']
        
        # 检测图片分辨率是否为4:3
        is_4_3_ratio = False
        try:
            if is_valid_image:
                img = Image.open(new_png_path)
                try:
                    width, height = img.size
                    aspect_ratio = width / height
                    # 检查是否是4:3比例（容错±30像素）
                    expected_height = width * 3 / 4
                    if abs(height - expected_height) <= 30:
                        is_4_3_ratio = True
                finally:
                    img.close()
        except Exception:
            pass
        
        # 创建对话框窗口
        dialog = Toplevel(self.root)
        dialog.title(self.t("add_new_title"))
        # 根据是否有警告消息调整窗口高度
        window_height = 180
        if not is_valid_image:
            window_height += 80
        if not is_4_3_ratio and is_valid_image:
            window_height += 80
        dialog.geometry(f"400x{window_height}")
        self.set_window_icon(dialog)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 如果不是常规图片格式，在窗口顶端显示警告
        if not is_valid_image:
            warning_label = tk.Label(dialog, text=self.t("file_extension_warning", filename=filename), 
                                    fg="#FF57FD", font=self.get_cjk_font(10), wraplength=380, justify="left")
            warning_label.pack(pady=5, padx=10, anchor="w")
        
        # 如果图片分辨率不是4:3或检测不出，显示警告（用#83A9A3颜色）
        if not is_4_3_ratio and is_valid_image:
            aspect_warning_label = tk.Label(dialog, text=self.t("aspect_ratio_warning"), 
                                           fg="#83A9A3", font=self.get_cjk_font(10), wraplength=380, justify="left")
            aspect_warning_label.pack(pady=5, padx=10, anchor="w")
        
        # ID输入框（标签和输入框换行）
        id_frame = ttk.Frame(dialog)
        id_frame.pack(pady=10, padx=20, fill='x')
        ttk.Label(id_frame, text=self.t("id_label")).pack(anchor='w')
        id_entry = Entry(id_frame, width=40)
        id_entry.pack(fill='x', pady=(5, 0))
        
        # 日期输入框（标签和输入框换行）
        date_frame = ttk.Frame(dialog)
        date_frame.pack(pady=10, padx=20, fill='x')
        ttk.Label(date_frame, text=self.t("date_label")).pack(anchor='w')
        date_entry = Entry(date_frame, width=40)
        date_entry.pack(fill='x', pady=(5, 0))
        
        # 确认按钮
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        
        def confirm_add():
            new_id = id_entry.get().strip()
            date_str = date_entry.get().strip()
            
            # 生成随机ID（如果为空）
            if not new_id:
                new_id = self.screenshot_manager.generate_id()
            
            # 检查ID是否已存在
            if new_id in self.screenshot_manager.sav_pairs:
                messagebox.showerror(self.t("error"), self.t("id_exists"))
                return
            
            # 处理日期
            if not date_str:
                date_str = self.screenshot_manager.get_current_datetime()
            else:
                try:
                    datetime.strptime(date_str, '%Y/%m/%d %H:%M:%S')
                except ValueError:
                    messagebox.showerror(self.t("error"), self.t("invalid_date_format"))
                    return
            
            # 如果不是常规图片格式，再次确认
            if not is_valid_image:
                result = messagebox.askyesno(
                    self.t("warning"),
                    self.t("file_extension_warning").format(filename=filename)
                )
                if not result:
                    dialog.destroy()
                    return
            
            # 添加截图
            success, message = self.screenshot_manager.add_screenshot(new_id, date_str, new_png_path)
            
            if success:
                messagebox.showinfo(self.t("success"), self.t("add_success").format(id=new_id))
                self.load_screenshots()
                self.show_status_indicator(new_id, is_new=True)
            else:
                messagebox.showerror(self.t("error"), message)
            
            dialog.destroy()
        
        ttk.Button(button_frame, text=self.t("confirm"), command=confirm_add).pack(side='left', padx=5)
        ttk.Button(button_frame, text=self.t("delete_cancel"), command=dialog.destroy).pack(side='left', padx=5)
        
        # 绑定回车键
        id_entry.bind('<Return>', lambda e: confirm_add())
        date_entry.bind('<Return>', lambda e: confirm_add())
        id_entry.focus()
    
    def delete_selected(self):
        """删除选中的截图"""
        selected_ids = self.get_selected_ids()
        
        if not selected_ids:
            messagebox.showwarning(self.t("warning"), self.t("delete_select_error"))
            return
        
        # 确认删除
        if len(selected_ids) == 1:
            confirm_msg = self.t("delete_confirm_single").format(id=selected_ids[0])
        else:
            ids_str = ", ".join(selected_ids)
            confirm_msg = self.t("delete_confirm_multiple").format(count=len(selected_ids), ids=ids_str)
        
        result = messagebox.askyesno(self.t("delete_confirm"), confirm_msg)
        
        if not result:
            return
        
        # 执行删除
        deleted_count = self.screenshot_manager.delete_screenshots(selected_ids)
        
        if deleted_count > 0:
            messagebox.showinfo(self.t("success"), self.t("delete_success").format(count=deleted_count))
            self.load_screenshots()
        else:
            messagebox.showwarning(self.t("warning"), self.t("delete_warning"))
    
    def export_image(self):
        """导出当前选中的图片"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning(self.t("warning"), self.t("select_screenshot"))
            return
        
        item_id = selected[0]
        if item_id not in self.checkbox_vars:
            messagebox.showerror(self.t("error"), self.t("invalid_selection"))
            return
        
        _, id_str = self.checkbox_vars[item_id]
        
        # 获取图片数据
        image_data = self.screenshot_manager.get_image_data(id_str)
        if not image_data:
            messagebox.showerror(self.t("error"), self.t("file_not_found"))
            return
        
        # 先选择格式
        format_dialog = Toplevel(self.root)
        format_dialog.title(self.t("select_export_format"))
        format_dialog.geometry("300x150")
        self.set_window_icon(format_dialog)
        format_dialog.transient(self.root)
        format_dialog.grab_set()
        
        format_var = tk.StringVar(value="png")
        
        ttk.Label(format_dialog, text=self.t("select_image_format")).pack(pady=10)
        
        format_frame = ttk.Frame(format_dialog)
        format_frame.pack(pady=10)
        ttk.Radiobutton(format_frame, text="PNG", variable=format_var, value="png").pack(side='left', padx=10)
        ttk.Radiobutton(format_frame, text="JPEG", variable=format_var, value="jpeg").pack(side='left', padx=10)
        ttk.Radiobutton(format_frame, text="WebP", variable=format_var, value="webp").pack(side='left', padx=10)
        
        def confirm_export():
            format_choice = format_var.get()
            format_dialog.destroy()
            
            # 根据格式设置文件扩展名
            if format_choice == "png":
                filetypes = [("PNG files", "*.png"), ("All files", "*.*")]
                defaultextension = ".png"
                default_filename = f"{id_str}.png"
            elif format_choice == "jpeg":
                filetypes = [("JPEG files", "*.jpg"), ("All files", "*.*")]
                defaultextension = ".jpg"
                default_filename = f"{id_str}.jpg"
            else:  # webp
                filetypes = [("WebP files", "*.webp"), ("All files", "*.*")]
                defaultextension = ".webp"
                default_filename = f"{id_str}.webp"
            
            # 选择保存位置
            save_path = filedialog.asksaveasfilename(
                title=self.t("save_image"),
                defaultextension=defaultextension,
                filetypes=filetypes,
                initialfile=default_filename
            )
            
            if not save_path:
                return
            
            try:
                # 保存临时PNG文件
                temp_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
                with open(temp_png, 'wb') as f:
                    f.write(image_data)
                
                # 打开图片并转换格式
                img = Image.open(temp_png)
                try:
                    if format_choice == "png":
                        img.save(save_path, "PNG")
                    elif format_choice == "jpeg":
                        if img.mode != "RGB":
                            img = img.convert("RGB")
                        img.save(save_path, "JPEG", quality=95)
                    else:  # webp
                        img.save(save_path, "WebP", quality=95)
                    messagebox.showinfo(self.t("success"), self.t("export_success").format(path=save_path))
                finally:
                    img.close()
                    # 清理临时文件
                    if os.path.exists(temp_png):
                        try:
                            os.remove(temp_png)
                        except:
                            pass
            except Exception as e:
                messagebox.showerror(self.t("error"), self.t("export_failed") + f": {str(e)}")
        
        button_frame = ttk.Frame(format_dialog)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text=self.t("confirm"), command=confirm_export).pack(side='left', padx=5)
        ttk.Button(button_frame, text=self.t("delete_cancel"), command=format_dialog.destroy).pack(side='left', padx=5)
    
    def batch_export_images(self):
        """批量导出图片到ZIP文件"""
        selected_ids = self.get_selected_ids()
        
        if not selected_ids:
            messagebox.showwarning(self.t("warning"), self.t("select_screenshot"))
            return
        
        # 先选择格式
        format_dialog = Toplevel(self.root)
        format_dialog.title(self.t("select_export_format"))
        format_dialog.geometry("300x150")
        self.set_window_icon(format_dialog)
        format_dialog.transient(self.root)
        format_dialog.grab_set()
        
        format_var = tk.StringVar(value="png")
        
        ttk.Label(format_dialog, text=self.t("select_image_format")).pack(pady=10)
        
        format_frame = ttk.Frame(format_dialog)
        format_frame.pack(pady=10)
        ttk.Radiobutton(format_frame, text="PNG", variable=format_var, value="png").pack(side='left', padx=10)
        ttk.Radiobutton(format_frame, text="JPEG", variable=format_var, value="jpeg").pack(side='left', padx=10)
        ttk.Radiobutton(format_frame, text="WebP", variable=format_var, value="webp").pack(side='left', padx=10)
        
        def confirm_batch_export():
            format_choice = format_var.get()
            format_dialog.destroy()
            
            # 选择ZIP保存位置
            save_path = filedialog.asksaveasfilename(
                title=self.t("save_zip"),
                defaultextension=".zip",
                filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
                initialfile="DevilConnectionSSPack.zip"
            )
            
            if not save_path:
                return
            
            # 创建进度条窗口
            progress_window = Toplevel(self.root)
            progress_window.title(self.t("batch_export_progress"))
            progress_window.geometry("450x200")
            self.set_window_icon(progress_window)
            progress_window.transient(self.root)
            progress_window.grab_set()
            
            # 禁用关闭按钮
            progress_window.protocol("WM_DELETE_WINDOW", lambda: None)
            
            # 进度条标签
            progress_label = tk.Label(progress_window, text=self.t("exporting_images"), 
                                     font=self.get_cjk_font(10), bg=self.Colors.WHITE)
            progress_label.pack(pady=10)
            
            # 进度条
            progress_bar = ttk.Progressbar(progress_window, length=350, mode='determinate')
            progress_bar.pack(pady=10, padx=20, fill="x")
            progress_bar['maximum'] = len(selected_ids)
            progress_bar['value'] = 0
            
            # 状态标签
            status_label = tk.Label(progress_window, text="0/{}".format(len(selected_ids)), 
                                   font=self.get_cjk_font(9), bg=self.Colors.WHITE)
            status_label.pack(pady=5)
            
            # 成功信息标签（初始隐藏）
            success_label = tk.Label(progress_window, text="", font=self.get_cjk_font(10), 
                                    bg=self.Colors.WHITE, fg="green")
            
            # 关闭按钮（初始隐藏）
            close_button = ttk.Button(progress_window, text=self.t("close"), 
                                     command=progress_window.destroy)
            
            def update_progress(current, total, exported, failed):
                """更新进度条"""
                progress_bar['value'] = current
                status_label.config(text=f"{current}/{total}")
                progress_window.update_idletasks()
            
            def show_success(exported_count, failed_count):
                """显示成功信息"""
                progress_bar.pack_forget()
                status_label.pack_forget()
                progress_label.config(text="")
                
                success_msg = self.t("batch_export_success", count=exported_count) if "batch_export_success" in self.translations.get(self.current_language, {}) else f"成功导出 {exported_count} 张图片到ZIP文件！"
                if failed_count > 0:
                    failed_msg = self.t("batch_export_failed", count=failed_count) if "batch_export_failed" in self.translations.get(self.current_language, {}) else f"失败: {failed_count} 张"
                    success_msg += "\n" + failed_msg
                
                success_label.config(text=success_msg)
                success_label.pack(pady=20)
                close_button.pack(pady=10)
                
                # 允许关闭窗口
                progress_window.protocol("WM_DELETE_WINDOW", progress_window.destroy)
            
            def show_error(error_msg):
                """显示错误信息"""
                progress_bar.pack_forget()
                status_label.pack_forget()
                progress_label.config(text="", fg="red")
                progress_label.config(text=error_msg, fg="red")
                close_button.pack(pady=10)
                progress_window.protocol("WM_DELETE_WINDOW", progress_window.destroy)
            
            def export_in_thread():
                """在后台线程中执行导出"""
                try:
                    exported_count = 0
                    failed_count = 0
                    current = 0
                    
                    with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for idx, id_str in enumerate(selected_ids):
                            image_data = self.screenshot_manager.get_image_data(id_str)
                            if image_data:
                                try:
                                    # 保存临时PNG文件
                                    temp_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
                                    with open(temp_png, 'wb') as f:
                                        f.write(image_data)
                                    
                                    # 打开图片并转换格式
                                    img = Image.open(temp_png)
                                    try:
                                        # 根据格式转换并保存到内存
                                        output = BytesIO()
                                        if format_choice == "png":
                                            img.save(output, "PNG")
                                            ext = ".png"
                                        elif format_choice == "jpeg":
                                            if img.mode != "RGB":
                                                img = img.convert("RGB")
                                            img.save(output, "JPEG", quality=95)
                                            ext = ".jpg"
                                        else:  # webp
                                            img.save(output, "WebP", quality=95)
                                            ext = ".webp"
                                        
                                        # 写入ZIP文件
                                        zipf.writestr(f"{id_str}{ext}", output.getvalue())
                                        exported_count += 1
                                    finally:
                                        img.close()
                                        # 清理临时文件
                                        if os.path.exists(temp_png):
                                            try:
                                                os.remove(temp_png)
                                            except:
                                                pass
                                except Exception as e:
                                    failed_count += 1
                            else:
                                failed_count += 1
                            
                            current = idx + 1
                            # 更新进度条
                            progress_window.after(0, update_progress, current, len(selected_ids), exported_count, failed_count)
                    
                    # 显示成功信息
                    if exported_count > 0:
                        progress_window.after(0, show_success, exported_count, failed_count)
                    else:
                        error_msg = self.t("batch_export_error_all") if "batch_export_error_all" in self.translations.get(self.current_language, {}) else "没有成功导出任何图片！"
                        progress_window.after(0, show_error, error_msg)
                except Exception as e:
                    error_msg = self.t("export_failed") + f": {str(e)}"
                    progress_window.after(0, show_error, error_msg)
            
            # 在后台线程中执行导出
            thread = threading.Thread(target=export_in_thread, daemon=True)
            thread.start()
        
        button_frame = ttk.Frame(format_dialog)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text=self.t("confirm"), command=confirm_batch_export).pack(side='left', padx=5)
        ttk.Button(button_frame, text=self.t("delete_cancel"), command=format_dialog.destroy).pack(side='left', padx=5)