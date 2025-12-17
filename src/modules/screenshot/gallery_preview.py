"""画廊预览组件

提供截图画廊预览窗口功能，支持分页显示和大小调整
"""

import os
import json
import urllib.parse
import base64
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import tkinter as tk
from tkinter import Entry, Toplevel
from tkinter import ttk
from PIL import Image
from PIL import ImageTk
from src.modules.screenshot.constants import (
    GALLERY_SIZE_PRESETS, GALLERY_ROWS_PER_PAGE, GALLERY_COLS_PER_PAGE,
    GALLERY_IMAGES_PER_PAGE
)
from src.utils.ui_utils import showwarning_relative


class GalleryPreview:
    """画廊预览窗口管理类"""
    
    def __init__(self, root, storage_dir, screenshot_manager, t_func, get_cjk_font, Colors, set_window_icon):
        """初始化画廊预览
        
        Args:
            root: 根窗口
            storage_dir: 存储目录
            screenshot_manager: 截图管理器实例
            t_func: 翻译函数
            get_cjk_font: 字体获取函数
            Colors: 颜色常量类
            set_window_icon: 窗口图标设置函数
        """
        self.root = root
        self.storage_dir = storage_dir
        self.screenshot_manager = screenshot_manager
        self.t = t_func
        self.get_cjk_font = get_cjk_font
        self.Colors = Colors
        self.set_window_icon = set_window_icon
    
    def show_gallery_preview(self):
        """显示画廊预览窗口，按照特定方式排列图片（分页显示）"""
        if not self.storage_dir or not self.screenshot_manager.ids_data:
            from src.utils.ui_utils import showerror_relative
            showerror_relative(self.root, self.t("error"), self.t("select_dir_hint"))
            return
        
        gallery_window = Toplevel(self.root)
        gallery_window.title(self.t("gallery_preview"))
        
        current_size_mode = tk.IntVar(value=2)
        
        def get_current_config():
            return GALLERY_SIZE_PRESETS[current_size_mode.get()]
        
        gallery_window.geometry(get_current_config()['window_size'])
        
        self.set_window_icon(gallery_window)
        
        main_container = tk.Frame(gallery_window, bg=self.Colors.WHITE)
        main_container.pack(fill="both", expand=True)
        
        image_frame = tk.Frame(main_container, bg=self.Colors.WHITE)
        image_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        image_ids = [item['id'] for item in self.screenshot_manager.ids_data]
        total_images = len(image_ids)
        
        total_pages = (total_images + GALLERY_IMAGES_PER_PAGE - 1) // GALLERY_IMAGES_PER_PAGE if total_images > 0 else 1
        
        current_page = tk.IntVar(value=1)
        
        gallery_window.page_frames = {}
        gallery_window.placeholders = {}
        gallery_window.image_refs = []
        gallery_window.loaded_pages = set()
        
        def create_page_frame(page_num):
            """创建指定页面的框架"""
            config = get_current_config()
            placeholder_size = config['placeholder_size']
            
            page_frame = tk.Frame(image_frame, bg=self.Colors.WHITE)
            page_frame.place(x=0, y=0, relwidth=1, relheight=1)
            
            for row in range(GALLERY_ROWS_PER_PAGE):
                row_frame = tk.Frame(page_frame, bg=self.Colors.WHITE)
                row_frame.pack(side="top", pady=5)
                
                for col in range(GALLERY_COLS_PER_PAGE):
                    image_idx = (page_num - 1) * GALLERY_IMAGES_PER_PAGE + row + col * GALLERY_ROWS_PER_PAGE
                    
                    col_frame = tk.Frame(row_frame, bg=self.Colors.WHITE)
                    col_frame.pack(side="left", padx=5)
                    
                    if image_idx < total_images:
                        id_str = image_ids[image_idx]
                        placeholder_container, placeholder_label = self.create_placeholder(col_frame, placeholder_size)
                        gallery_window.placeholders[id_str] = (placeholder_container, placeholder_label, col_frame)
                    else:
                        placeholder_container = tk.Frame(col_frame, bg="lightgray", width=placeholder_size[0], height=placeholder_size[1])
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
        
        def load_page_images(page_num, force_reload=False):
            """加载指定页面的图片
            
            Args:
                page_num: 页码
                force_reload: 是否强制重新加载，默认为False
            """
            if not force_reload and page_num in gallery_window.loaded_pages:
                return
            
            start_idx = (page_num - 1) * GALLERY_IMAGES_PER_PAGE
            end_idx = min(start_idx + GALLERY_IMAGES_PER_PAGE, total_images)
            page_image_ids = image_ids[start_idx:end_idx]
            
            if not page_image_ids:
                return
            
            config = get_current_config()
            image_size = config['image_size']
            
            gallery_window.loaded_pages.add(page_num)
            self.load_gallery_images_async(gallery_window, page_image_ids, image_size)
        
        def show_page(page_num):
            """显示指定页面
            
            Args:
                page_num: 页码
            """
            if page_num < 1 or page_num > total_pages:
                return
            
            for frame in gallery_window.page_frames.values():
                frame.place_forget()
            
            if page_num not in gallery_window.page_frames:
                gallery_window.page_frames[page_num] = create_page_frame(page_num)
            
            gallery_window.page_frames[page_num].place(x=0, y=0, relwidth=1, relheight=1)
            current_page.set(page_num)
            
            load_page_images(page_num)
            update_navigation()
        
        def update_navigation():
            """更新导航栏显示"""
            page_info_label.config(text=f"{current_page.get()}/{total_pages}")
            prev_button.config(state="normal" if current_page.get() > 1 else "disabled")
            next_button.config(state="normal" if current_page.get() < total_pages else "disabled")
        
        def go_to_prev_page():
            """跳转到上一页"""
            if current_page.get() > 1:
                show_page(current_page.get() - 1)
        
        def go_to_next_page():
            """跳转到下一页"""
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
                    showwarning_relative(self.root, self.t("warning"), 
                                         self.t("invalid_page_number").format(min=1, max=total_pages),
                                         parent=gallery_window)
            except ValueError:
                showwarning_relative(self.root, self.t("warning"), self.t("invalid_page_input"),
                                     parent=gallery_window)
        
        nav_frame = tk.Frame(main_container, bg=self.Colors.WHITE)
        nav_frame.pack(side="bottom", fill="x", pady=10)
        
        nav_center_frame = tk.Frame(nav_frame, bg=self.Colors.WHITE)
        nav_center_frame.pack(anchor="center")
        
        prev_button = ttk.Button(nav_center_frame, text=self.t("prev_page"), command=go_to_prev_page)
        prev_button.pack(side="left", padx=5)
        
        page_info_label = tk.Label(nav_center_frame, text="1/1", font=self.get_cjk_font(12), bg=self.Colors.WHITE)
        page_info_label.pack(side="left", padx=10)
        
        next_button = ttk.Button(nav_center_frame, text=self.t("next_page"), command=go_to_next_page)
        next_button.pack(side="left", padx=5)
        
        jump_frame = tk.Frame(nav_center_frame, bg=self.Colors.WHITE)
        jump_frame.pack(side="left", padx=20)
        
        jump_label = tk.Label(jump_frame, text=self.t("jump_to_page"), font=self.get_cjk_font(10), bg=self.Colors.WHITE)
        jump_label.pack(side="left", padx=5)
        
        jump_entry = Entry(jump_frame, width=10)
        jump_entry.pack(side="left", padx=5)
        jump_entry.bind('<Return>', lambda e: jump_to_page())
        
        jump_button = ttk.Button(jump_frame, text=self.t("jump"), command=jump_to_page)
        jump_button.pack(side="left", padx=5)
        
        def change_size_mode(direction):
            """切换大小档位
            
            Args:
                direction: -1表示减小，1表示增大
            """
            current = current_size_mode.get()
            max_size = len(GALLERY_SIZE_PRESETS) - 1
            
            if direction == -1:
                if current > 0:
                    new_mode = current - 1
                else:
                    return
            else:
                if current < max_size:
                    new_mode = current + 1
                else:
                    return
            
            if current_size_mode.get() == new_mode:
                return
            
            current_size_mode.set(new_mode)
            config = get_current_config()
            
            gallery_window.geometry(config['window_size'])
            
            gallery_window.loaded_pages.clear()
            gallery_window.image_refs.clear()
            gallery_window.placeholders.clear()
            
            for frame in gallery_window.page_frames.values():
                if frame and frame.winfo_exists():
                    try:
                        frame.destroy()
                    except (tk.TclError, AttributeError):
                        pass
            gallery_window.page_frames.clear()
            
            total_pages = (total_images + GALLERY_IMAGES_PER_PAGE - 1) // GALLERY_IMAGES_PER_PAGE if total_images > 0 else 1
            
            if current_page.get() > total_pages:
                current_page.set(total_pages)
            if current_page.get() < 1:
                current_page.set(1)
            
            if current_page.get() not in gallery_window.page_frames:
                gallery_window.page_frames[current_page.get()] = create_page_frame(current_page.get())
            
            gallery_window.page_frames[current_page.get()].place(x=0, y=0, relwidth=1, relheight=1)
            
            load_page_images(current_page.get(), force_reload=True)
            
            update_navigation()
        
        size_control_frame = tk.Frame(main_container, bg=self.Colors.WHITE)
        size_control_frame.place(relx=1.0, rely=0.0, anchor="ne", x=-5, y=5)
        
        small_button_style = ttk.Style()
        small_font = self.get_cjk_font(8)
        small_button_style.configure("Small.TButton", 
                                     font=small_font,
                                     padding=[1, 2]) 
        
        size_minus_btn = ttk.Button(size_control_frame, text="-", width=2, 
                                    style="Small.TButton",
                                    command=lambda: change_size_mode(-1))
        size_minus_btn.pack(side="left", padx=0)
        
        size_plus_btn = ttk.Button(size_control_frame, text="+", width=2,
                                   style="Small.TButton",
                                   command=lambda: change_size_mode(1))
        size_plus_btn.pack(side="left", padx=0)
        
        def on_window_close():
            gallery_window.destroy()
        
        gallery_window.protocol("WM_DELETE_WINDOW", on_window_close)
        
        show_page(1)
    
    def create_placeholder(self, parent_frame, size=(150, 112)):
        """创建加载中的占位符"""
        placeholder_container = tk.Frame(parent_frame, bg="lightgray", width=size[0], height=size[1])
        placeholder_container.pack()
        placeholder_container.pack_propagate(False)
        
        placeholder_label = tk.Label(placeholder_container, text=self.t("loading"), 
                                    bg="lightgray", fg="gray", font=self.get_cjk_font(10),
                                    anchor="center", justify="center")
        placeholder_label.place(relx=0.5, rely=0.5, anchor="center")
        
        placeholder_id_label = tk.Label(parent_frame, text="", bg=self.Colors.WHITE, font=self.get_cjk_font(8))
        placeholder_id_label.pack()
        
        return placeholder_container, placeholder_label
    
    def load_gallery_images_async(self, gallery_window, image_ids, image_size=(150, 112)):
        """异步加载指定图片列表"""
        def load_single_image(id_str):
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
                    preview_img = img.resize(image_size, Image.Resampling.BILINEAR)
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

