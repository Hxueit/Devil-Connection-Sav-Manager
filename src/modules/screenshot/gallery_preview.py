"""画廊预览组件

提供截图画廊预览窗口功能，支持分页显示和大小调整
"""

import logging
import os
import json
import urllib.parse
import base64
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Tuple, List, Callable, Any
import tkinter as tk
from tkinter import Entry, Toplevel
from tkinter import ttk
from PIL import Image
from PIL import ImageTk

from src.modules.screenshot.constants import (
    GALLERY_SIZE_PRESETS, GALLERY_ROWS_PER_PAGE, GALLERY_COLS_PER_PAGE,
    GALLERY_IMAGES_PER_PAGE, GALLERY_OPERATION_ADD, GALLERY_OPERATION_REPLACE
)
from src.utils.ui_utils import showwarning_relative, restore_and_activate_window

logger = logging.getLogger(__name__)


class GalleryWindowState:
    """画廊窗口状态数据类"""
    
    def __init__(self, window: Toplevel):
        self.window = window
        self.page_frames: Dict[int, tk.Frame] = {}
        self.placeholders: Dict[str, Tuple[tk.Frame, tk.Label, tk.Frame]] = {}
        self.image_refs: List[ImageTk.PhotoImage] = []
        self.loaded_pages: set[int] = set()
        self.position_frames: Dict[int, tk.Frame] = {}
        self.current_page: Optional[tk.IntVar] = None
        self.image_ids: List[str] = []
        self.total_images: int = 0
        self.total_pages: int = 0
        self.get_current_config: Optional[Callable[[], Dict[str, Any]]] = None
        self.show_page_func: Optional[Callable[[int], None]] = None
        self.load_page_images_func: Optional[Callable[[int, bool], None]] = None
        self.update_navigation_func: Optional[Callable[[], None]] = None


class GalleryPreview:
    """画廊预览窗口管理类"""
    
    def __init__(
        self,
        root: tk.Tk,
        storage_dir: Optional[str],
        screenshot_manager: Any,
        t_func: Callable[[str], str],
        get_cjk_font: Callable[[int, Optional[str]], Any],
        Colors: Any,
        set_window_icon: Callable[[tk.Toplevel], None]
    ) -> None:
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
        if root is None:
            raise ValueError("root cannot be None")
        if screenshot_manager is None:
            raise ValueError("screenshot_manager cannot be None")
        if t_func is None:
            raise ValueError("t_func cannot be None")
        
        self.root = root
        self.storage_dir = Path(storage_dir) if storage_dir else None
        self.screenshot_manager = screenshot_manager
        self.t = t_func
        self.get_cjk_font = get_cjk_font
        self.Colors = Colors
        self.set_window_icon = set_window_icon
        self.current_gallery_window: Optional[Toplevel] = None
    
    def show_gallery_preview(self) -> None:
        """显示画廊预览窗口，按照特定方式排列图片（分页显示）"""
        if not self.storage_dir or not self.screenshot_manager.ids_data:
            from src.utils.ui_utils import showerror_relative
            showerror_relative(self.root, self.t("error"), self.t("select_dir_hint"))
            return
        
        # 检查是否已有窗口存在
        if self.current_gallery_window is not None:
            try:
                if self.current_gallery_window.winfo_exists():
                    # 窗口存在，尝试恢复并激活
                    if restore_and_activate_window(self.current_gallery_window):
                        # 成功恢复窗口，不创建新窗口
                        return
                    else:
                        # 窗口已销毁但引用还在，清理引用
                        self.current_gallery_window = None
            except (tk.TclError, AttributeError):
                # 窗口已销毁，清理引用
                self.current_gallery_window = None
        
        gallery_window = Toplevel(self.root)
        gallery_window.title(self.t("gallery_preview"))
        
        current_size_mode = tk.IntVar(value=2)
        
        def get_current_config() -> Dict[str, Any]:
            return GALLERY_SIZE_PRESETS[current_size_mode.get()]
        
        gallery_window.geometry(get_current_config()['window_size'])
        self.set_window_icon(gallery_window)
        
        main_container = tk.Frame(gallery_window, bg=self.Colors.WHITE)
        main_container.pack(fill="both", expand=True)
        
        image_frame = tk.Frame(main_container, bg=self.Colors.WHITE)
        image_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        image_ids = [item['id'] for item in self.screenshot_manager.ids_data]
        total_images = len(image_ids)
        total_pages = self._calculate_total_pages(total_images)
        
        current_page = tk.IntVar(value=1)
        state = GalleryWindowState(gallery_window)
        state.current_page = current_page
        state.image_ids = image_ids
        state.total_images = total_images
        state.total_pages = total_pages
        state.get_current_config = get_current_config
        
        def create_page_frame(page_num: int) -> tk.Frame:
            """创建指定页面的框架"""
            config = get_current_config()
            placeholder_size = config['placeholder_size']
            current_image_ids = state.image_ids
            current_total_images = state.total_images
            
            page_frame = tk.Frame(image_frame, bg=self.Colors.WHITE)
            page_frame.place(x=0, y=0, relwidth=1, relheight=1)
            
            for row in range(GALLERY_ROWS_PER_PAGE):
                row_frame = tk.Frame(page_frame, bg=self.Colors.WHITE)
                row_frame.pack(side="top", pady=5)
                
                for col in range(GALLERY_COLS_PER_PAGE):
                    image_idx = (page_num - 1) * GALLERY_IMAGES_PER_PAGE + row + col * GALLERY_ROWS_PER_PAGE
                    
                    col_frame = tk.Frame(row_frame, bg=self.Colors.WHITE)
                    col_frame.pack(side="left", padx=5)
                    
                    state.position_frames[image_idx] = col_frame
                    
                    if image_idx < current_total_images:
                        screenshot_id = current_image_ids[image_idx]
                        placeholder_container, placeholder_label = self.create_placeholder(col_frame, placeholder_size)
                        state.placeholders[screenshot_id] = (placeholder_container, placeholder_label, col_frame)
                    else:
                        self._create_empty_placeholder(col_frame, placeholder_size)
                    
                    if col == 1:
                        separator = tk.Frame(row_frame, width=3, bg="gray", relief="sunken")
                        separator.pack(side="left", fill="y", padx=5)
            
            return page_frame
        
        def load_page_images(page_num: int, force_reload: bool = False) -> None:
            """加载指定页面的图片"""
            start_idx = (page_num - 1) * GALLERY_IMAGES_PER_PAGE
            end_idx = min(start_idx + GALLERY_IMAGES_PER_PAGE, state.total_images)
            page_image_ids = state.image_ids[start_idx:end_idx]
            
            if not page_image_ids:
                return
            
            if not force_reload and page_num in state.loaded_pages:
                has_placeholders = any(
                    screenshot_id in state.placeholders 
                    for screenshot_id in page_image_ids
                )
                if has_placeholders:
                    return
            
            config = get_current_config()
            image_size = config['image_size']
            
            state.loaded_pages.add(page_num)
            self.load_gallery_images_async(gallery_window, page_image_ids, image_size)
        
        def show_page(page_num: int) -> None:
            """显示指定页面"""
            current_total_pages = state.total_pages
            if page_num < 1 or page_num > current_total_pages:
                return
            
            for page_key, frame in list(state.page_frames.items()):
                if frame:
                    try:
                        if frame.winfo_exists():
                            frame.place_forget()
                        else:
                            del state.page_frames[page_key]
                    except (tk.TclError, AttributeError):
                        if page_key in state.page_frames:
                            del state.page_frames[page_key]
            
            if page_num not in state.page_frames:
                state.page_frames[page_num] = create_page_frame(page_num)
            
            frame_to_show = state.page_frames.get(page_num)
            if frame_to_show:
                try:
                    if frame_to_show.winfo_exists():
                        frame_to_show.place(x=0, y=0, relwidth=1, relheight=1)
                except (tk.TclError, AttributeError):
                    state.page_frames[page_num] = create_page_frame(page_num)
                    state.page_frames[page_num].place(x=0, y=0, relwidth=1, relheight=1)
            
            current_page.set(page_num)
            
            load_page_images(page_num)
            update_navigation()
        
        def update_navigation() -> None:
            """更新导航栏显示"""
            current_total_pages = state.total_pages
            page_info_label.config(text=f"{current_page.get()}/{current_total_pages}")
            prev_button.config(state="normal" if current_page.get() > 1 else "disabled")
            next_button.config(state="normal" if current_page.get() < current_total_pages else "disabled")
        
        def go_to_prev_page() -> None:
            """跳转到上一页"""
            if current_page.get() > 1:
                show_page(current_page.get() - 1)
        
        def go_to_next_page() -> None:
            """跳转到下一页"""
            current_total_pages = state.total_pages
            if current_page.get() < current_total_pages:
                show_page(current_page.get() + 1)
        
        def jump_to_page() -> None:
            """跳转到指定页面"""
            try:
                target_page = int(jump_entry.get())
                current_total_pages = state.total_pages
                if 1 <= target_page <= current_total_pages:
                    show_page(target_page)
                    jump_entry.delete(0, tk.END)
                else:
                    showwarning_relative(
                        self.root,
                        self.t("warning"),
                        self.t("invalid_page_number").format(min=1, max=current_total_pages),
                        parent=gallery_window
                    )
            except ValueError:
                showwarning_relative(
                    self.root,
                    self.t("warning"),
                    self.t("invalid_page_input"),
                    parent=gallery_window
                )
        
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
        
        def change_size_mode(direction: int) -> None:
            """切换大小档位"""
            current = current_size_mode.get()
            max_size = len(GALLERY_SIZE_PRESETS) - 1
            
            if direction == -1:
                if current <= 0:
                    return
                new_mode = current - 1
            else:
                if current >= max_size:
                    return
                new_mode = current + 1
            
            if current_size_mode.get() == new_mode:
                return
            
            current_size_mode.set(new_mode)
            config = get_current_config()
            gallery_window.geometry(config['window_size'])
            
            state.loaded_pages.clear()
            state.image_refs.clear()
            state.placeholders.clear()
            
            self._destroy_page_frames(state)
            state.page_frames.clear()
            
            state.image_ids = [item['id'] for item in self.screenshot_manager.ids_data]
            state.total_images = len(state.image_ids)
            state.total_pages = self._calculate_total_pages(state.total_images)
            
            if current_page.get() > state.total_pages:
                current_page.set(state.total_pages)
            if current_page.get() < 1:
                current_page.set(1)
            
            if current_page.get() not in state.page_frames:
                state.page_frames[current_page.get()] = create_page_frame(current_page.get())
            
            state.page_frames[current_page.get()].place(x=0, y=0, relwidth=1, relheight=1)
            load_page_images(current_page.get(), force_reload=True)
            update_navigation()
        
        size_control_frame = tk.Frame(main_container, bg=self.Colors.WHITE)
        size_control_frame.place(relx=1.0, rely=0.0, anchor="ne", x=-5, y=5)
        
        small_button_style = ttk.Style()
        small_font = self.get_cjk_font(8)
        small_button_style.configure("Small.TButton", font=small_font, padding=[1, 2])
        
        size_minus_btn = ttk.Button(
            size_control_frame,
            text="-",
            width=2,
            style="Small.TButton",
            command=lambda: change_size_mode(-1)
        )
        size_minus_btn.pack(side="left", padx=0)
        
        size_plus_btn = ttk.Button(
            size_control_frame,
            text="+",
            width=2,
            style="Small.TButton",
            command=lambda: change_size_mode(1)
        )
        size_plus_btn.pack(side="left", padx=0)
        
        def on_window_close() -> None:
            self.current_gallery_window = None
            gallery_window.destroy()
        
        gallery_window.protocol("WM_DELETE_WINDOW", on_window_close)
        
        state.show_page_func = show_page
        state.load_page_images_func = load_page_images
        state.update_navigation_func = update_navigation
        
        gallery_window._gallery_state = state
        self.current_gallery_window = gallery_window
        
        show_page(1)
    
    def create_placeholder(self, parent_frame: tk.Frame, size: Tuple[int, int] = (150, 112)) -> Tuple[tk.Frame, tk.Label]:
        """创建加载中的占位符"""
        placeholder_container = tk.Frame(parent_frame, bg="lightgray", width=size[0], height=size[1])
        placeholder_container.pack()
        placeholder_container.pack_propagate(False)
        
        placeholder_label = tk.Label(
            placeholder_container,
            text=self.t("loading"),
            bg="lightgray",
            fg="gray",
            font=self.get_cjk_font(10),
            anchor="center",
            justify="center"
        )
        placeholder_label.place(relx=0.5, rely=0.5, anchor="center")
        
        placeholder_id_label = tk.Label(parent_frame, text="", bg=self.Colors.WHITE, font=self.get_cjk_font(8))
        placeholder_id_label.pack()
        
        return placeholder_container, placeholder_label
    
    def _create_empty_placeholder(self, parent_frame: tk.Frame, size: Tuple[int, int]) -> None:
        """创建空占位符（无图片可用）"""
        placeholder_container = tk.Frame(parent_frame, bg="lightgray", width=size[0], height=size[1])
        placeholder_container.pack()
        placeholder_container.pack_propagate(False)
        
        placeholder_label = tk.Label(
            placeholder_container,
            text=self.t("not_available"),
            bg="lightgray",
            fg="gray",
            font=self.get_cjk_font(14, "bold"),
            anchor="center",
            justify="center"
        )
        placeholder_label.place(relx=0.5, rely=0.5, anchor="center")
        
        placeholder_id_label = tk.Label(parent_frame, text="", bg=self.Colors.WHITE, font=self.get_cjk_font(8))
        placeholder_id_label.pack()
    
    def load_gallery_images_async(
        self,
        gallery_window: Toplevel,
        image_ids: List[str],
        image_size: Tuple[int, int] = (150, 112)
    ) -> None:
        """异步加载指定图片列表"""
        def load_single_image(screenshot_id: str) -> Tuple[str, Optional[Image.Image]]:
            """加载单个图片"""
            if screenshot_id not in self.screenshot_manager.sav_pairs:
                return screenshot_id, None
            
            thumb_file, main_file = self.screenshot_manager.sav_pairs[screenshot_id]
            
            sav_file_path = None
            if thumb_file:
                thumb_path = self.storage_dir / thumb_file
                if thumb_path.exists():
                    sav_file_path = thumb_path
            
            if not sav_file_path and main_file:
                main_path = self.storage_dir / main_file
                if main_path.exists():
                    sav_file_path = main_path
            
            if not sav_file_path:
                return screenshot_id, None
            
            try:
                with open(sav_file_path, 'r', encoding='utf-8') as f:
                    encoded = f.read().strip()
                unquoted = urllib.parse.unquote(encoded)
                data_uri = json.loads(unquoted)
                b64_part = data_uri.split(';base64,', 1)[1]
                img_data = base64.b64decode(b64_part)
                
                img = Image.open(BytesIO(img_data))
                try:
                    preview_img = img.resize(image_size, Image.Resampling.BILINEAR)
                    return screenshot_id, preview_img
                finally:
                    img.close()
            except (OSError, json.JSONDecodeError, ValueError, KeyError) as e:
                logger.debug(f"Failed to load image {screenshot_id}: {e}")
                return screenshot_id, None
        
        def update_image(screenshot_id: str, pil_image: Optional[Image.Image]) -> None:
            """更新图片显示
            
            Args:
                screenshot_id: 截图ID
                pil_image: PIL图片对象，如果为None表示加载失败
            """
            state = getattr(gallery_window, '_gallery_state', None)
            if not state or screenshot_id not in state.placeholders:
                return
            
            placeholder_container, placeholder_label, col_frame = state.placeholders[screenshot_id]
            
            if not self._is_frame_valid(col_frame):
                if screenshot_id in state.placeholders:
                    del state.placeholders[screenshot_id]
                return
            
            if pil_image is None:
                if self._is_frame_valid(placeholder_label):
                    try:
                        placeholder_label.config(text=self.t("preview_failed"), bg="lightgray", fg="red")
                    except (tk.TclError, AttributeError) as e:
                        logger.debug(f"Failed to update placeholder label for {screenshot_id}: {e}")
                return
            
            try:
                photo = ImageTk.PhotoImage(pil_image)
                state.image_refs.append(photo)
                placeholder_container.destroy()
                img_label = tk.Label(
                    col_frame,
                    image=photo,
                    bg=self.Colors.WHITE,
                    text=screenshot_id,
                    compound="top",
                    font=self.get_cjk_font(8)
                )
                img_label.pack()
                if screenshot_id in state.placeholders:
                    del state.placeholders[screenshot_id]
            except (tk.TclError, AttributeError) as e:
                logger.debug(f"Failed to update image {screenshot_id}: {e}")
                if self._is_frame_valid(placeholder_label):
                    try:
                        placeholder_label.config(text=self.t("preview_failed"), bg="lightgray", fg="red")
                    except (tk.TclError, AttributeError) as e2:
                        logger.debug(f"Failed to update placeholder label after image update error: {e2}")
        
        def process_results() -> None:
            """处理加载结果"""
            if not image_ids:
                return
            
            max_workers = min(8, len(image_ids))
            executor = ThreadPoolExecutor(max_workers=max_workers)
            
            try:
                future_to_id = {
                    executor.submit(load_single_image, screenshot_id): screenshot_id
                    for screenshot_id in image_ids
                }
                
                for future in as_completed(future_to_id):
                    try:
                        screenshot_id, pil_image = future.result()
                        gallery_window.after(0, update_image, screenshot_id, pil_image)
                    except Exception as e:
                        logger.warning(f"Error processing image load result: {e}")
            finally:
                executor.shutdown(wait=False)
        
        thread = threading.Thread(target=process_results, daemon=True)
        thread.start()
    
    def _is_gallery_window_valid(self) -> bool:
        """检查画廊窗口是否仍然有效
        
        Returns:
            窗口有效返回True，否则返回False
        """
        if not self.current_gallery_window:
            return False
        
        if not hasattr(self.current_gallery_window, 'winfo_exists'):
            self.current_gallery_window = None
            return False
        
        try:
            if not self.current_gallery_window.winfo_exists():
                self.current_gallery_window = None
                return False
        except (tk.TclError, AttributeError) as e:
            logger.debug(f"Gallery window validation failed: {e}")
            self.current_gallery_window = None
            return False
        
        return True
    
    def _is_frame_valid(self, frame: tk.Frame) -> bool:
        """检查框架是否仍然有效
        
        Args:
            frame: 要检查的框架对象
            
        Returns:
            框架有效返回True，否则返回False
        """
        if not frame:
            return False
        
        if not hasattr(frame, 'winfo_exists'):
            return False
        
        try:
            return frame.winfo_exists()
        except (tk.TclError, AttributeError):
            return False
    
    def _clear_loaded_pages_cache(self, state: GalleryWindowState, current_page_only: bool = False) -> None:
        """清除已加载页面的缓存
        
        Args:
            state: 画廊窗口状态对象
            current_page_only: 如果为True，只清除当前页，否则清除所有页
        """
        if current_page_only:
            current_page = state.current_page.get()
            if current_page in state.loaded_pages:
                state.loaded_pages.remove(current_page)
        else:
            state.loaded_pages.clear()
    
    def _get_valid_gallery_state(self) -> Optional[GalleryWindowState]:
        """获取有效的画廊窗口状态
        
        Returns:
            窗口存在且有效时返回状态对象，否则返回None
        """
        if not self._is_gallery_window_valid():
            return None
        
        return getattr(self.current_gallery_window, '_gallery_state', None)
    
    def _update_gallery_state_metadata(self, state: GalleryWindowState) -> None:
        """更新画廊状态元数据
        
        Args:
            state: 画廊窗口状态对象
        """
        state.image_ids = [item['id'] for item in self.screenshot_manager.ids_data]
        state.total_images = len(state.image_ids)
        state.total_pages = self._calculate_total_pages(state.total_images)
    
    def _calculate_page_bounds(self, page_number: int, total_images: int) -> Tuple[int, int]:
        """计算指定页面的索引范围
        
        Args:
            page_number: 页码（从1开始）
            total_images: 总图片数
            
        Returns:
            (起始索引, 结束索引) 元组
        """
        start_idx = (page_number - 1) * GALLERY_IMAGES_PER_PAGE
        end_idx = min(start_idx + GALLERY_IMAGES_PER_PAGE, total_images)
        return start_idx, end_idx
    
    def refresh_current_page_if_needed(self, start_index: int, end_index: int) -> None:
        """检测拖拽操作是否影响当前画廊页面，如果影响则刷新
        
        Args:
            start_index: 拖拽起始索引
            end_index: 拖拽结束索引
        """
        state = self._get_valid_gallery_state()
        if not state:
            return
        
        current_page = state.current_page.get()
        page_start_idx, page_end_idx = self._calculate_page_bounds(current_page, state.total_images)
        
        if self._is_drag_affecting_page(start_index, end_index, page_start_idx, page_end_idx):
            self._incremental_refresh_page(state, start_index, end_index, page_start_idx, page_end_idx)
    
    def refresh_after_add(self, screenshot_id: str) -> None:
        """添加截图后刷新画廊预览
        
        Args:
            screenshot_id: 新添加的截图ID
        """
        state = self._get_valid_gallery_state()
        if not state:
            return
        
        self._update_gallery_state_metadata(state)
        
        try:
            new_index = state.image_ids.index(screenshot_id)
        except ValueError:
            logger.warning(f"Screenshot ID {screenshot_id} not found after add operation")
            self._refresh_current_page(state)
            return
        
        current_page = state.current_page.get()
        page_start_idx, page_end_idx = self._calculate_page_bounds(current_page, state.total_images)
        
        self._clear_loaded_pages_cache(state, current_page_only=False)
        
        if new_index < page_end_idx:
            self._refresh_current_page(state)
        elif state.update_navigation_func:
            state.update_navigation_func()
    
    def refresh_after_delete(self, deleted_ids: List[str]) -> None:
        """删除截图后刷新画廊预览
        
        Args:
            deleted_ids: 被删除的截图ID列表
        """
        if not deleted_ids:
            return
        
        state = self._get_valid_gallery_state()
        if not state:
            return
        
        self._update_gallery_state_metadata(state)
        
        current_page = state.current_page.get()
        
        if current_page > state.total_pages and state.total_pages > 0:
            state.current_page.set(state.total_pages)
            self._clear_loaded_pages_cache(state, current_page_only=False)
            if state.show_page_func:
                state.show_page_func(state.total_pages)
            return
        
        self._clear_loaded_pages_cache(state, current_page_only=False)
        self._refresh_current_page(state)
    
    def refresh_after_replace(self, screenshot_id: str) -> None:
        """替换截图后刷新画廊预览
        
        Args:
            screenshot_id: 被替换的截图ID
        """
        state = self._get_valid_gallery_state()
        if not state:
            return
        
        try:
            replaced_index = state.image_ids.index(screenshot_id)
        except ValueError:
            logger.warning(f"Screenshot ID {screenshot_id} not found after replace operation")
            self._refresh_current_page(state)
            return
        
        current_page = state.current_page.get()
        page_start_idx, page_end_idx = self._calculate_page_bounds(current_page, state.total_images)
        
        if not (page_start_idx <= replaced_index < page_end_idx):
            return
        
        config = state.get_current_config()
        if not config:
            logger.warning("Failed to get gallery config for replace refresh")
            return
        
        image_size = config['image_size']
        placeholder_size = config['placeholder_size']
        
        col_frame = state.position_frames.get(replaced_index)
        if not col_frame:
            logger.debug(f"Position frame not found for index {replaced_index}")
            return
        
        if not self._is_gallery_window_valid():
            return
        
        if not self._is_frame_valid(col_frame):
            logger.debug(f"Position frame at index {replaced_index} is invalid")
            return
        
        current_id = self._find_current_image_id(state, col_frame)
        self._clear_position_content(state, col_frame, current_id)
        placeholder_container, placeholder_label = self.create_placeholder(col_frame, placeholder_size)
        state.placeholders[screenshot_id] = (placeholder_container, placeholder_label, col_frame)
        
        if self._is_gallery_window_valid():
            self._clear_loaded_pages_cache(state, current_page_only=True)
            self.load_gallery_images_async(self.current_gallery_window, [screenshot_id], image_size)
    
    def _is_drag_affecting_page(
        self,
        start_index: int,
        end_index: int,
        page_start_idx: int,
        page_end_idx: int
    ) -> bool:
        """判断拖拽是否影响当前页"""
        if page_start_idx <= start_index < page_end_idx or page_start_idx <= end_index < page_end_idx:
            return True
        
        min_index = min(start_index, end_index)
        max_index = max(start_index, end_index)
        
        if not (max_index < page_start_idx or min_index >= page_end_idx):
            return True
        
        if start_index < page_start_idx and end_index >= page_start_idx:
            return True
        
        if start_index >= page_end_idx and end_index < page_end_idx:
            return True
        
        return False
    
    def _incremental_refresh_page(
        self,
        state: GalleryWindowState,
        start_index: int,
        end_index: int,
        page_start_idx: int,
        page_end_idx: int
    ) -> None:
        """增量刷新画廊页面，只更新受影响的位置
        
        Args:
            state: 画廊窗口状态对象
            start_index: 拖拽起始索引
            end_index: 拖拽结束索引
            page_start_idx: 页面起始索引
            page_end_idx: 页面结束索引
        """
        try:
            if not state.position_frames:
                self._refresh_current_page(state)
                return
            
            self._update_gallery_state_metadata(state)
            
            affected_start = max(page_start_idx, min(start_index, end_index))
            affected_end = min(page_end_idx, max(start_index, end_index) + 1)
            
            if affected_start >= page_end_idx or affected_end <= page_start_idx:
                self._refresh_current_page(state)
                return
            
            affected_count = affected_end - affected_start
            total_positions = page_end_idx - page_start_idx
            if affected_count > total_positions // 2:
                self._refresh_current_page(state)
                return
            
            config = state.get_current_config()
            if not config:
                logger.warning("Failed to get gallery config for incremental refresh")
                self._refresh_current_page(state)
                return
            
            image_size = config['image_size']
            placeholder_size = config['placeholder_size']
            
            positions_to_update = list(range(affected_start, affected_end))
            image_ids_to_load: List[str] = []
            
            for pos in positions_to_update:
                col_frame = state.position_frames.get(pos)
                if not self._is_frame_valid(col_frame):
                    continue
                
                if pos < state.total_images:
                    new_id = state.image_ids[pos]
                    current_id = self._find_current_image_id(state, col_frame)
                    if current_id != new_id:
                        if new_id not in image_ids_to_load:
                            image_ids_to_load.append(new_id)
                        self._clear_position_content(state, col_frame, current_id)
                        placeholder_container, placeholder_label = self.create_placeholder(col_frame, placeholder_size)
                        state.placeholders[new_id] = (placeholder_container, placeholder_label, col_frame)
                else:
                    current_id = self._find_current_image_id(state, col_frame)
                    self._clear_position_content(state, col_frame, current_id)
                    self._create_empty_placeholder(col_frame, placeholder_size)
            
            if image_ids_to_load and self._is_gallery_window_valid():
                self.load_gallery_images_async(self.current_gallery_window, image_ids_to_load, image_size)
            
            if state.update_navigation_func:
                try:
                    state.update_navigation_func()
                except (tk.TclError, AttributeError) as e:
                    logger.debug(f"Failed to call update_navigation_func in incremental refresh: {e}")
                
        except (tk.TclError, AttributeError, KeyError) as e:
            logger.warning(f"Incremental refresh failed, falling back to full refresh: {e}")
            try:
                self._refresh_current_page(state)
            except Exception as fallback_error:
                logger.error(f"Full refresh also failed: {fallback_error}", exc_info=True)
    
    def _find_current_image_id(self, state: GalleryWindowState, col_frame: tk.Frame) -> Optional[str]:
        """查找当前位置显示的图片ID
        
        Args:
            state: 画廊窗口状态对象
            col_frame: 列框架对象
            
        Returns:
            如果找到则返回截图ID，否则返回None
        """
        if not self._is_frame_valid(col_frame):
            return None
        
        for screenshot_id, (_, _, frame) in state.placeholders.items():
            if frame == col_frame:
                return screenshot_id
        
        try:
            for widget in col_frame.winfo_children():
                if isinstance(widget, tk.Label):
                    widget_text = widget.cget("text")
                    if widget_text and widget_text in state.image_ids:
                        return widget_text
        except (tk.TclError, AttributeError) as e:
            logger.debug(f"Failed to find image ID from widgets: {e}")
        
        return None
    
    def _clear_position_content(
        self,
        state: GalleryWindowState,
        col_frame: tk.Frame,
        current_id: Optional[str]
    ) -> None:
        """清除位置内容
        
        Args:
            state: 画廊窗口状态对象
            col_frame: 列框架对象
            current_id: 当前位置的截图ID，如果为None则不清理占位符字典
        """
        if not self._is_frame_valid(col_frame):
            return
        
        try:
            if current_id and current_id in state.placeholders:
                old_placeholder_data = state.placeholders[current_id]
                if old_placeholder_data[2] == col_frame:
                    del state.placeholders[current_id]
            
            for widget in col_frame.winfo_children():
                widget.destroy()
        except (tk.TclError, AttributeError, KeyError) as e:
            logger.debug(f"Error clearing position content: {e}")
    
    def _refresh_current_page(self, state: GalleryWindowState) -> None:
        """刷新当前画廊页面
        
        Args:
            state: 画廊窗口状态对象
        """
        if not self._is_gallery_window_valid():
            return
        
        try:
            current_page = state.current_page.get()
            
            self._clear_loaded_pages_cache(state, current_page_only=True)
            self._update_gallery_state_metadata(state)
            self._clear_all_placeholders(state)
            
            page_start_idx, page_end_idx = self._calculate_page_bounds(current_page, state.total_images)
            for pos in range(page_start_idx, page_end_idx):
                if pos in state.position_frames:
                    del state.position_frames[pos]
            
            self._destroy_page_frames(state)
            if current_page in state.page_frames:
                del state.page_frames[current_page]
            
            if not self._is_gallery_window_valid():
                return
            
            self._call_state_callbacks(state, current_page)
        except (tk.TclError, AttributeError, KeyError) as e:
            logger.warning(f"Failed to refresh current page: {e}")
    
    def _call_state_callbacks(self, state: GalleryWindowState, page_num: int) -> None:
        """调用状态回调函数
        
        Args:
            state: 画廊窗口状态对象
            page_num: 页码
        """
        if state.show_page_func:
            try:
                state.show_page_func(page_num)
            except (tk.TclError, AttributeError) as e:
                logger.debug(f"Failed to call show_page_func: {e}")
                return
        
        if state.update_navigation_func:
            try:
                state.update_navigation_func()
            except (tk.TclError, AttributeError) as e:
                logger.debug(f"Failed to call update_navigation_func: {e}")
    
    def _clear_all_placeholders(self, state: GalleryWindowState) -> None:
        """清除所有占位符
        
        Args:
            state: 画廊窗口状态对象
        """
        for screenshot_id, placeholder_data in list(state.placeholders.items()):
            if placeholder_data:
                _, _, col_frame = placeholder_data
                if self._is_frame_valid(col_frame):
                    try:
                        for widget in col_frame.winfo_children():
                            widget.destroy()
                    except (tk.TclError, AttributeError) as e:
                        logger.debug(f"Failed to destroy widgets in placeholder {screenshot_id}: {e}")
        
        state.placeholders.clear()
    
    def _destroy_page_frames(self, state: GalleryWindowState) -> None:
        """销毁所有页面框架"""
        for page_key, frame in list(state.page_frames.items()):
            if frame:
                try:
                    if frame.winfo_exists():
                        frame.destroy()
                except (tk.TclError, AttributeError):
                    pass
            if page_key in state.page_frames:
                del state.page_frames[page_key]
    
    def _calculate_total_pages(self, total_images: int) -> int:
        """计算总页数"""
        if total_images <= 0:
            return 1
        return (total_images + GALLERY_IMAGES_PER_PAGE - 1) // GALLERY_IMAGES_PER_PAGE
