import tkinter as tk
from tkinter import ttk, Scrollbar
import json
import urllib.parse
import os
import platform
from translations import TRANSLATIONS
from utils import set_window_icon, SUMMONER_PIC_BASE64
import re
import base64
import io
from PIL import Image, ImageTk, ImageEnhance
import random

def get_cjk_font(size=10, weight="normal"):
    """
    获取适合中文和日文的字体
    """
    if platform.system() == "Windows":
        font_name = "Microsoft YaHei"
    elif platform.system() == "Darwin":  # macOS
        font_name = "PingFang SC"
    else:  # Linux
        font_name = "Arial"
    
    if weight == "bold":
        return (font_name, size, "bold")
    return (font_name, size)


class SaveAnalyzer:
    def __init__(self, parent, storage_dir, translations, current_language):
        self.parent = parent
        self.storage_dir = storage_dir
        self.translations = translations
        self.current_language = current_language
        
        self.window = parent
        
        # 性能优化：缓存宽度值，使用防抖机制避免频繁更新
        # 获取窗口宽度并计算2/3作为方框宽度
        self.window.update_idletasks()  # 确保窗口已渲染
        window_width = self.window.winfo_width()
        if window_width <= 1:
            # 如果窗口还未完全渲染，使用默认值，稍后会更新
            window_width = 800
        self._cached_width = int(window_width * 2 / 3)
        self._width_update_pending = False
        
        # 创建顶部控制栏
        control_frame = tk.Frame(self.window, bg="white")
        control_frame.pack(fill="x", padx=10, pady=5)
        
        # 显示变量名复选框
        self.show_var_names_var = tk.BooleanVar(value=False)
        show_var_names_checkbox = ttk.Checkbutton(control_frame, 
                                                  text=self.t("show_var_names"),
                                                  variable=self.show_var_names_var,
                                                  command=self.toggle_var_names_display)
        show_var_names_checkbox.pack(side="left", padx=5)
        
        # 存储所有变量名widget的列表
        self.var_name_widgets = []
        
        # 刷新按钮（右上角）
        refresh_button = ttk.Button(control_frame, text=self.t("refresh"), 
                                    command=self.refresh, name="refresh")
        refresh_button.pack(side="right", padx=5)
        
        # 创建主容器Frame，用于放置PanedWindow和滚动条
        main_container = tk.Frame(self.window, bg="white")
        main_container.pack(fill="both", expand=True)
        
        # 创建PanedWindow分割左右区域（隐藏分割线）
        main_paned = tk.PanedWindow(main_container, orient="horizontal", sashwidth=0, bg="white", sashrelief='flat')
        main_paned.pack(side="left", fill="both", expand=True)
        
        # 左侧2/3区域：可滚动的内容区域
        left_frame = tk.Frame(main_paned, bg="white")
        main_paned.add(left_frame, width=800, minsize=400)
        
        # 创建滚动区域
        canvas = tk.Canvas(left_frame, bg="white")
        scrollable_frame = tk.Frame(canvas, bg="white")
        
        # 设置初始宽度，确保方框从一开始就有正确的宽度
        scrollable_frame.config(width=self._cached_width)
        
        # 性能优化：延迟更新scrollregion，使用防抖机制
        self._scroll_update_pending = False
        self._scroll_retry_count = 0  # 重试计数器，避免无限重试
        def update_scrollregion():
            try:
                # 检查canvas和scrollable_frame是否仍然有效
                if not hasattr(self, 'scrollable_canvas') or not self.scrollable_canvas:
                    self._scroll_update_pending = False
                    self._scroll_retry_count = 0
                    return
                if not hasattr(self, 'scrollable_frame') or not self.scrollable_frame:
                    self._scroll_update_pending = False
                    self._scroll_retry_count = 0
                    return
                
                # 检查canvas是否仍然存在
                try:
                    self.scrollable_canvas.winfo_exists()
                except:
                    self._scroll_update_pending = False
                    self._scroll_retry_count = 0
                    return
                
                # 获取bbox，检查是否有效
                bbox = self.scrollable_canvas.bbox("all")
                if bbox is None:
                    # 如果bbox为None，可能是widget还未完全渲染，延迟重试（最多重试3次）
                    self._scroll_update_pending = False
                    if self._scroll_retry_count < 3:
                        self._scroll_retry_count += 1
                        self.window.after(50, update_scrollregion)
                    else:
                        self._scroll_retry_count = 0
                    return
                
                # 检查bbox是否有效（宽度和高度应该大于0）
                if len(bbox) >= 4:
                    x1, y1, x2, y2 = bbox[:4]
                    if x2 > x1 and y2 > y1:
                        # 只有bbox有效时才更新scrollregion
                        self.scrollable_canvas.configure(scrollregion=bbox)
                        self._scroll_retry_count = 0  # 成功时重置计数器
                    else:
                        # bbox无效，延迟重试（最多重试3次）
                        self._scroll_update_pending = False
                        if self._scroll_retry_count < 3:
                            self._scroll_retry_count += 1
                            self.window.after(50, update_scrollregion)
                        else:
                            self._scroll_retry_count = 0
                        return
                else:
                    # bbox格式不正确，延迟重试（最多重试3次）
                    self._scroll_update_pending = False
                    if self._scroll_retry_count < 3:
                        self._scroll_retry_count += 1
                        self.window.after(50, update_scrollregion)
                    else:
                        self._scroll_retry_count = 0
                    return
            except Exception as e:
                # 记录错误但不抛出，避免影响其他功能
                self._scroll_retry_count = 0
            finally:
                self._scroll_update_pending = False
        
        def on_scrollable_configure(event=None):
            if not self._scroll_update_pending:
                self._scroll_update_pending = True
                self.window.after_idle(update_scrollregion)
        
        # 根据窗口宽度动态更新canvas宽度（固定为窗口宽度的2/3）
        def update_canvas_width(event=None):
            if self._width_update_pending:
                return
            self._width_update_pending = True
            def do_update():
                try:
                    # 检查canvas和scrollable_frame是否仍然有效
                    if not hasattr(self, 'scrollable_canvas') or not self.scrollable_canvas:
                        self._width_update_pending = False
                        return
                    if not hasattr(self, 'scrollable_frame') or not self.scrollable_frame:
                        self._width_update_pending = False
                        return
                    
                    # 检查canvas是否仍然存在
                    try:
                        self.scrollable_canvas.winfo_exists()
                    except:
                        self._width_update_pending = False
                        return
                    
                    # 获取窗口宽度并计算2/3
                    window_width = self.window.winfo_width()
                    if window_width > 1:
                        width = int(window_width * 2 / 3)
                        # 确保宽度至少为1，避免设置为0导致内容不可见
                        if width < 1:
                            width = 1
                        self._cached_width = width
                        canvas.config(width=width)
                        scrollable_frame.config(width=width)
                        
                        # 更新宽度后，延迟更新滚动区域，确保widget已经重新布局
                        self.window.after(10, lambda: on_scrollable_configure())
                except:
                    pass
                finally:
                    self._width_update_pending = False
            self.window.after_idle(do_update)
        
        scrollable_frame.bind("<Configure>", on_scrollable_configure)
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.pack(fill="both", expand=True)
        
        # 存储scrollable_frame和canvas的引用
        self.scrollable_frame = scrollable_frame
        self.scrollable_canvas = canvas
        
        # 加载并解析存档（延迟渲染以提高响应性）
        self.save_data = self.load_save_file()
        if self.save_data:
            self.window.after(10, lambda: self.display_save_info(scrollable_frame, self.save_data))
        else:
            error_label = ttk.Label(scrollable_frame, text=self.t("save_file_not_found"), 
                                   font=get_cjk_font(12), foreground="red")
            error_label.pack(pady=20)
            self.save_data = None
        
        # 绑定主窗口的Configure事件，监听窗口大小变化
        def on_window_configure(event=None):
            # 只响应主窗口的大小变化
            if event is None or event.widget == self.window:
                update_canvas_width()
        
        self.window.bind("<Configure>", on_window_configure)
        # 延迟执行以确保窗口已完全渲染
        self.window.after(100, update_canvas_width)
        
        # 右侧1/3区域：显示图片（不可滚动）
        right_frame = tk.Frame(main_paned, bg="white")
        main_paned.add(right_frame, width=400, minsize=200)
        self._right_frame = right_frame
        
        # 性能优化：使用防抖机制设置PanedWindow比例（固定2:1）
        self._paned_update_pending = False
        def set_paned_ratio(event=None):
            if self._paned_update_pending:
                return
            self._paned_update_pending = True
            def do_update():
                try:
                    if main_paned.winfo_width() > 1:
                        total_width = main_paned.winfo_width()
                        left_width = int(total_width * 0.67)
                        main_paned.paneconfig(left_frame, width=left_width)
                except:
                    pass
                self._paned_update_pending = False
            self.window.after_idle(do_update)
        
        # 禁用拖动分割线
        def disable_sash_drag(event):
            return "break"
        
        main_paned.bind("<Button-1>", disable_sash_drag)
        main_paned.bind("<B1-Motion>", disable_sash_drag)
        main_paned.bind("<ButtonRelease-1>", disable_sash_drag)
        
        main_paned.bind("<Configure>", set_paned_ratio)
        set_paned_ratio()
        
        # 创建Canvas用于显示图片
        image_canvas = tk.Canvas(right_frame, bg="white", highlightthickness=0)
        image_canvas.pack(fill="both", expand=True)
        
        # 加载并显示base64图片
        self.load_and_display_image(image_canvas, right_frame)
        
        # 创建滚动条，放在主容器最右侧
        scrollbar = Scrollbar(main_container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        
        # 绑定鼠标滚轮（绑定到整个可滚动区域）
        def on_mousewheel(event):
            try:
                if event.delta:
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                else:
                    if event.num == 4:
                        canvas.yview_scroll(-1, "units")
                    elif event.num == 5:
                        canvas.yview_scroll(1, "units")
            except:
                pass
        
        # 递归绑定滚轮事件到widget及其所有子组件
        def bind_mousewheel_recursive(widget):
            """递归绑定滚轮事件到widget及其所有子组件"""
            try:
                widget.bind("<MouseWheel>", on_mousewheel)
                widget.bind("<Button-4>", on_mousewheel)
                widget.bind("<Button-5>", on_mousewheel)
                # 递归绑定所有子组件
                for child in widget.winfo_children():
                    bind_mousewheel_recursive(child)
            except:
                pass
        
        # 绑定到canvas、left_frame和scrollable_frame
        bind_mousewheel_recursive(canvas)
        bind_mousewheel_recursive(left_frame)
        bind_mousewheel_recursive(scrollable_frame)
        
        # 保存函数引用，以便在添加新组件后重新绑定
        self._bind_mousewheel_recursive = bind_mousewheel_recursive
        self._scrollable_frame = scrollable_frame
        self._left_frame = left_frame
    
    def toggle_var_names_display(self):
        """切换变量名显示状态"""
        show = self.show_var_names_var.get()
        for widget_info in self.var_name_widgets:
            widget = widget_info['widget']
            parent = widget_info['parent']
            label_widget = widget_info['label_widget']
            
            if show:
                # 在标签前面显示变量名
                widget.pack(side="left", padx=2, before=label_widget)
            else:
                widget.pack_forget()
    
    def refresh(self):
        """刷新存档分析页面：重新加载存档并更新显示"""
        # 清除scrollable_frame中的所有内容
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # 清空变量名widget列表
        self.var_name_widgets = []
        
        # 重新加载存档
        self.save_data = self.load_save_file()
        
        if self.save_data:
            # 重新显示存档信息
            self.display_save_info(self.scrollable_frame, self.save_data)
            # 重新加载并显示图片
            if hasattr(self, '_image_canvas') and self._image_canvas and hasattr(self, '_right_frame') and self._right_frame:
                self.load_and_display_image(self._image_canvas, self._right_frame)
        else:
            # 显示错误信息
            error_label = ttk.Label(self.scrollable_frame, text=self.t("save_file_not_found"), 
                                   font=get_cjk_font(12), foreground="red")
            error_label.pack(pady=20)
            self.save_data = None
    
    def t(self, key, **kwargs):
        """翻译函数"""
        text = self.translations[self.current_language].get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text
    
    def load_save_file(self):
        """加载并解码存档文件"""
        sf_path = os.path.join(self.storage_dir, 'DevilConnection_sf.sav')
        if not os.path.exists(sf_path):
            return None
        
        try:
            with open(sf_path, 'r', encoding='utf-8') as f:
                encoded = f.read().strip()
            unquoted = urllib.parse.unquote(encoded)
            return json.loads(unquoted)
        except Exception as e:
            return None
    
    def apply_red_filter(self, img):
        """将黑色线条转换为红色，保持白色/透明背景不变"""
        # 转换为RGB模式（如果不是的话）
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # 使用逐像素操作来应用红色滤镜
        pixels = img.load()
        width, height = img.size
        
        for y in range(height):
            for x in range(width):
                r, g, b = pixels[x, y]
                
                # 判断是否为黑色或接近黑色的像素（线条）
                # 如果RGB值都比较低，认为是黑色线条
                # 阈值设为180，扩大检测范围以捕获更多灰色线条
                max_component = max(r, g, b)
                
                if max_component < 180:
                    # 黑色线条：转换为红色
                    # 保持原有的明暗程度，但改为红色调
                    # 使用原始亮度来确定红色的深浅
                    brightness = (r + g + b) / 3
                    # 将黑色映射到红色，保持明暗对比
                    # 纯黑色(0) -> 深红色(50)，较黑的灰色 -> 较亮的红色
                    red_intensity = int(50 + (255 - brightness) * 0.8)
                    red_intensity = min(255, max(50, red_intensity))  # 限制在50-255范围
                    pixels[x, y] = (red_intensity, 0, 0)
                # 如果像素较亮（白色背景或浅色），保持不变
        
        return img
    
    def load_and_display_image(self, canvas, parent):
        """从utils模块加载base64图片并显示"""
        try:
            # 直接从导入的变量获取 base64 数据
            base64_data = SUMMONER_PIC_BASE64
            
            if not base64_data:
                canvas.config(bg="white")
                return
            
            # 清理base64字符串：只保留有效的base64字符
            import string
            valid_chars = string.ascii_letters + string.digits + '+/='
            base64_clean = ''.join(c for c in base64_data if c in valid_chars)
            
            # 移除所有=，然后重新添加正确的填充
            data_only = ''.join(c for c in base64_clean if c != '=')
            
            # 计算需要添加的填充（使长度成为4的倍数）
            remainder = len(data_only) % 4
            if remainder:
                data_only += '=' * (4 - remainder)
            
            # 解码base64图片
            try:
                image_data = base64.b64decode(data_only)
                image = Image.open(io.BytesIO(image_data))
            except Exception as e:
                canvas.config(bg="white")
                return
            
            # 检查是否需要应用红色滤镜和闪烁效果
            should_apply_effect = False
            if self.save_data:
                killed = self.save_data.get("killed", 0)
                kill = self.save_data.get("kill", 0)
                kill_start = self.save_data.get("killStart", 0)
                if killed == 1 or kill > 0 or kill_start > 0:
                    should_apply_effect = True
            
            # 存储图片引用，避免被垃圾回收
            self.image_ref = image
            self.should_apply_effect = should_apply_effect
            self._image_canvas = canvas
            self._image_base_x = None
            self._image_base_y = None
            self._flash_animation_id = None
            self._processed_image = None  # 存储处理后的图片（红色滤镜）
            
            # 性能优化：使用防抖机制和更快的重采样方法
            self._image_update_pending = False
            self._last_image_size = None
            
            def update_image_size(event=None):
                """更新图片大小以适应canvas（防抖优化）"""
                if self._image_update_pending:
                    return
                self._image_update_pending = True
                
                # 取消正在运行的闪烁动画，避免冲突
                if self._flash_animation_id:
                    try:
                        self.window.after_cancel(self._flash_animation_id)
                    except:
                        pass
                    self._flash_animation_id = None
                
                def do_update():
                    try:
                        canvas_width = canvas.winfo_width()
                        canvas_height = canvas.winfo_height()
                        if canvas_width > 1 and canvas_height > 1:
                            # 检查尺寸是否真的改变了
                            current_size = (canvas_width, canvas_height)
                            if self._last_image_size == current_size and not should_apply_effect:
                                self._image_update_pending = False
                                return
                            self._last_image_size = current_size
                            
                            # 计算缩放比例，保持宽高比
                            img_width, img_height = image.size
                            scale_w = canvas_width / img_width
                            scale_h = canvas_height / img_height
                            scale = min(scale_w, scale_h)
                            
                            new_width = int(img_width * scale)
                            new_height = int(img_height * scale)
                            
                            # 使用BILINEAR而不是LANCZOS，速度更快，质量足够
                            # 如果缩放比例很大，使用NEAREST会更快
                            if scale < 0.5:
                                resized_image = image.resize((new_width, new_height), Image.Resampling.BILINEAR)
                            else:
                                resized_image = image.resize((new_width, new_height), Image.Resampling.NEAREST)
                            
                            # 如果需要应用红色滤镜
                            if should_apply_effect:
                                resized_image = self.apply_red_filter(resized_image)
                                # 保存处理后的图片供闪烁使用
                                self._processed_image = resized_image
                            
                            photo = ImageTk.PhotoImage(resized_image)
                            
                            # 清除canvas并重新绘制（只清除图片canvas）
                            canvas.delete("all")
                            # 居中显示
                            base_x = (canvas_width - new_width) // 2
                            base_y = (canvas_height - new_height) // 2
                            
                            # 保存基础位置
                            self._image_base_x = base_x
                            self._image_base_y = base_y
                            
                            # 居中显示，不添加位移
                            x = base_x
                            y = base_y
                            
                            canvas.create_image(x, y, anchor="nw", image=photo)
                            canvas.image = photo
                            
                            # 如果应用效果，启动闪烁动画（在更新完成后）
                            if should_apply_effect:
                                # 延迟启动闪烁动画，确保图片更新完成
                                self.window.after(100, lambda: self.start_flash_animation(canvas, base_x, base_y, new_width, new_height))
                    except Exception as e:
                        canvas.delete("all")
                        canvas.config(bg="white")
                    finally:
                        self._image_update_pending = False
                
                # 延迟更新，避免频繁重采样
                self.window.after(50, do_update)
            
            # 绑定大小变化事件（只绑定canvas，避免重复触发）
            canvas.bind("<Configure>", update_image_size)
            # 延迟一下再显示，确保canvas已经有尺寸
            self.window.after(100, update_image_size)
            
        except Exception as e:
            canvas.config(bg="white")
    
    def start_flash_animation(self, canvas, base_x, base_y, img_width, img_height):
        """启动闪烁动画效果"""
        # 取消之前的动画（如果存在）
        if self._flash_animation_id:
            self.window.after_cancel(self._flash_animation_id)
        
        # 保存canvas引用，确保只操作图片canvas
        image_canvas = canvas
        # 验证canvas是否为图片canvas
        if not hasattr(self, '_image_canvas') or image_canvas != self._image_canvas:
            # 如果传入的canvas不是图片canvas，使用存储的引用
            if hasattr(self, '_image_canvas') and self._image_canvas:
                image_canvas = self._image_canvas
            else:
                # 如果没有图片canvas，不启动动画
                return
        
        def flash_animation():
            """执行闪烁动画"""
            try:
                # 检查canvas是否仍然有效
                if not hasattr(self, '_image_canvas') or not self._image_canvas:
                    return
                if image_canvas != self._image_canvas:
                    return
                try:
                    # 检查canvas是否仍然存在
                    image_canvas.winfo_exists()
                except:
                    return
                
                if not hasattr(self, 'image_ref') or not self.image_ref:
                    return
                
                # 检查是否有图片更新正在进行，如果有则跳过本次动画
                if hasattr(self, '_image_update_pending') and self._image_update_pending:
                    # 延迟重试
                    self._flash_animation_id = self.window.after(500, flash_animation)
                    return
                
                # 清除canvas（只清除图片canvas）
                image_canvas.delete("all")
                
                # 重新计算缩放（以防窗口大小改变）
                canvas_width = image_canvas.winfo_width()
                canvas_height = image_canvas.winfo_height()
                if canvas_width > 1 and canvas_height > 1:
                    img = self.image_ref
                    scale_w = canvas_width / img.size[0]
                    scale_h = canvas_height / img.size[1]
                    scale = min(scale_w, scale_h)
                    
                    new_width = int(img.size[0] * scale)
                    new_height = int(img.size[1] * scale)
                    
                    # 重新缩放并应用红色滤镜
                    # 如果缩放比例很大，使用NEAREST会更快
                    if scale < 0.5:
                        resized_image = img.resize((new_width, new_height), Image.Resampling.BILINEAR)
                    else:
                        resized_image = img.resize((new_width, new_height), Image.Resampling.NEAREST)
                    resized_image = self.apply_red_filter(resized_image)
                    photo = ImageTk.PhotoImage(resized_image)
                    
                    # 更新基础位置（居中显示）
                    base_x = (canvas_width - new_width) // 2
                    base_y = (canvas_height - new_height) // 2
                    self._image_base_x = base_x
                    self._image_base_y = base_y
                    
                    # 直接居中显示，不添加位移
                    image_canvas.create_image(base_x, base_y, anchor="nw", image=photo)
                    image_canvas.image = photo
                    
                    # 保存处理后的图片供闪烁使用
                    self._processed_image = resized_image
                    
                    # 快速闪烁几次（每0.1秒一次，共3次）
                    flash_count = [0]
                    def quick_flash():
                        try:
                            # 再次检查canvas有效性
                            if not hasattr(self, '_image_canvas') or not self._image_canvas:
                                return
                            if image_canvas != self._image_canvas:
                                return
                            try:
                                image_canvas.winfo_exists()
                            except:
                                return
                            
                            # 检查是否有图片更新正在进行
                            if hasattr(self, '_image_update_pending') and self._image_update_pending:
                                # 延迟重试
                                self._flash_animation_id = self.window.after(500, flash_animation)
                                return
                            
                            flash_count[0] += 1
                            if flash_count[0] <= 3:
                                # 清除canvas（只清除图片canvas）
                                image_canvas.delete("all")
                                # 使用保存的基础位置（居中，不位移）
                                current_base_x = self._image_base_x if self._image_base_x is not None else base_x
                                current_base_y = self._image_base_y if self._image_base_y is not None else base_y
                                
                                # 闪烁时稍微变亮或变暗
                                flash_intensity = random.uniform(0.7, 1.1)
                                if self._processed_image:
                                    enhancer = ImageEnhance.Brightness(self._processed_image)
                                    flash_img = enhancer.enhance(flash_intensity)
                                    flash_photo = ImageTk.PhotoImage(flash_img)
                                else:
                                    flash_photo = photo
                                
                                # 居中显示，不添加位移
                                image_canvas.create_image(current_base_x, current_base_y, anchor="nw", image=flash_photo)
                                image_canvas.image = flash_photo
                                
                                if flash_count[0] < 3:
                                    self._flash_animation_id = self.window.after(100, quick_flash)
                                else:
                                    # 闪烁结束后，恢复原位置并等待5秒
                                    image_canvas.delete("all")
                                    image_canvas.create_image(current_base_x, current_base_y, anchor="nw", image=photo)
                                    image_canvas.image = photo
                                    self._flash_animation_id = self.window.after(5000, flash_animation)
                        except Exception as e:
                            # 出错时停止动画，避免无限重试
                            self._flash_animation_id = None
                    
                    # 开始快速闪烁
                    self._flash_animation_id = self.window.after(100, quick_flash)
            except Exception as e:
                # 出错时重新安排动画（但增加延迟，避免频繁重试）
                self._flash_animation_id = self.window.after(5000, flash_animation)
        
        # 5秒后开始第一次闪烁
        self._flash_animation_id = self.window.after(5000, flash_animation)
    
    def create_section(self, parent, title):
        """创建带标题的分区"""
        section_frame = tk.Frame(parent, bg="white", relief="ridge", borderwidth=2)
        section_frame.pack(fill="x", padx=10, pady=5)
        
        # 使用缓存的宽度计算标题换行长度
        def get_title_wraplength():
            return int(self._cached_width * 0.9)
        
        title_label = ttk.Label(section_frame, text=title, font=get_cjk_font(12, "bold"), 
                               wraplength=get_title_wraplength(), justify="left")
        title_label.pack(anchor="w", padx=5, pady=5)
        
        content_frame = tk.Frame(section_frame, bg="white")
        content_frame.pack(fill="x", padx=10, pady=5)
        
        return content_frame
    
    def create_section_with_button(self, parent, title, button_text, button_command=None):
        """创建带标题和按钮的分区"""
        section_frame = tk.Frame(parent, bg="white", relief="ridge", borderwidth=2)
        section_frame.pack(fill="x", padx=10, pady=5)
        
        # 标题和按钮在同一行
        header_frame = tk.Frame(section_frame, bg="white")
        header_frame.pack(fill="x", padx=5, pady=5)
        
        # 使用缓存的宽度计算标题换行长度
        def get_title_wraplength():
            return int(self._cached_width * 0.6)
        
        title_label = ttk.Label(header_frame, text=title, font=get_cjk_font(12, "bold"), 
                               wraplength=get_title_wraplength(), justify="left")
        title_label.pack(side="left", padx=5)
        
        if button_text:
            button = ttk.Button(header_frame, text=button_text, command=button_command if button_command else lambda: None)
            button.pack(side="right", padx=5)
        
        content_frame = tk.Frame(section_frame, bg="white")
        content_frame.pack(fill="x", padx=10, pady=5)
        
        return content_frame
    
    def add_info_line(self, parent, label, value, var_name=None):
        """添加信息行"""
        line_frame = tk.Frame(parent, bg="white")
        line_frame.pack(fill="x", padx=5, pady=2)
        
        label_widget = ttk.Label(line_frame, text=label + ":", font=get_cjk_font(10), wraplength=200)
        label_widget.pack(side="left", padx=5)
        
        # 如果有变量名，在冒号前面显示灰色的变量名
        var_name_widget = None
        if var_name:
            var_name_widget = ttk.Label(line_frame, text=f"[{var_name}]", 
                                       font=get_cjk_font(9), 
                                       foreground="gray",
                                       wraplength=150)
            # 默认隐藏，只有勾选复选框时才显示
            if self.show_var_names_var.get():
                var_name_widget.pack(side="left", padx=2, before=label_widget)
            # 存储widget信息以便后续切换显示
            self.var_name_widgets.append({
                'widget': var_name_widget,
                'parent': line_frame,
                'label_widget': label_widget
            })
        
        wraplength = int(self._cached_width * 0.7)
        
        value_widget = ttk.Label(line_frame, text=str(value), font=get_cjk_font(10), wraplength=wraplength, justify="left")
        value_widget.pack(side="left", padx=5, fill="x", expand=True)
    
    def add_list_info(self, parent, label, items):
        """添加列表信息，显示完整列表"""
        line_frame = tk.Frame(parent, bg="white")
        line_frame.pack(fill="x", padx=5, pady=2)
        
        label_widget = ttk.Label(line_frame, text=label + ":", font=get_cjk_font(10), wraplength=200)
        label_widget.pack(side="left", padx=5)
        
        wraplength = int(self._cached_width * 0.7)
        
        if len(items) == 0:
            value_widget = ttk.Label(line_frame, text=self.t("none"), font=get_cjk_font(10), 
                                     foreground="gray", wraplength=wraplength, justify="left")
            value_widget.pack(side="left", padx=5, fill="x", expand=True)
        else:
            value_text = ", ".join(str(item) for item in items)
            value_widget = ttk.Label(line_frame, text=value_text, font=get_cjk_font(10), 
                                    wraplength=wraplength, justify="left")
            value_widget.pack(side="left", padx=5, fill="x", expand=True)
    
    def add_list_info_horizontal(self, parent, label, items):
        """添加列表信息，横向一行展示（为之后修改功能留接口）"""
        line_frame = tk.Frame(parent, bg="white")
        line_frame.pack(fill="x", padx=5, pady=2)
        
        label_widget = ttk.Label(line_frame, text=label + ":", font=get_cjk_font(10))
        label_widget.pack(side="left", padx=5)
        
        # 创建可滚动的横向显示区域
        canvas_frame = tk.Frame(line_frame, bg="white")
        canvas_frame.pack(side="left", fill="x", expand=True, padx=5)
        
        # 使用Canvas实现横向滚动
        canvas = tk.Canvas(canvas_frame, height=25, bg="white", highlightthickness=0)
        scrollbar_h = Scrollbar(canvas_frame, orient="horizontal", command=canvas.xview)
        scrollable_frame = tk.Frame(canvas, bg="white")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(xscrollcommand=scrollbar_h.set)
        
        if len(items) == 0:
            value_widget = ttk.Label(scrollable_frame, text=self.t("none"), font=get_cjk_font(10), 
                                     foreground="gray")
            value_widget.pack(side="left", padx=2)
        else:
            value_text = ", ".join(str(item) for item in items)
            value_widget = ttk.Label(scrollable_frame, text=value_text, font=get_cjk_font(10))
            value_widget.pack(side="left", padx=2)
        
        canvas.pack(side="left", fill="x", expand=True)
        if len(items) > 10:  # 只有内容较多时才显示滚动条
            scrollbar_h.pack(side="bottom", fill="x")
        
        # 存储items以便之后修改功能使用
        scrollable_frame.items_data = items
        scrollable_frame.label_key = label
        
        return scrollable_frame
    
    def add_info_line_with_tooltip(self, parent, label, value, tooltip_text, var_name=None):
        """添加带可点击问号的信息行"""
        # 创建一个容器来包含主行和提示信息
        container = tk.Frame(parent, bg="white")
        container.pack(fill="x", padx=5, pady=2)
        
        line_frame = tk.Frame(container, bg="white")
        line_frame.pack(fill="x")
        
        label_widget = ttk.Label(line_frame, text=label + ":", font=get_cjk_font(10), wraplength=200)
        label_widget.pack(side="left", padx=5)
        
        # 如果有变量名，在冒号前面显示灰色的变量名
        var_name_widget = None
        if var_name:
            var_name_widget = ttk.Label(line_frame, text=f"[{var_name}]", 
                                       font=get_cjk_font(9), 
                                       foreground="gray",
                                       wraplength=150)
            # 默认隐藏，只有勾选复选框时才显示
            if self.show_var_names_var.get():
                var_name_widget.pack(side="left", padx=2, before=label_widget)
            # 存储widget信息以便后续切换显示
            self.var_name_widgets.append({
                'widget': var_name_widget,
                'parent': line_frame,
                'label_widget': label_widget
            })
        
        # 性能优化：使用缓存的宽度
        wraplength = int(self._cached_width * 0.7)
        
        value_widget = ttk.Label(line_frame, text=str(value), font=get_cjk_font(10), 
                                wraplength=wraplength, justify="left")
        value_widget.pack(side="left", padx=5, fill="x", expand=True)
        
        # 创建可点击的信息符号
        tooltip_label = ttk.Label(line_frame, text="ℹ", font=get_cjk_font(10, "bold"), 
                                  foreground="blue", cursor="hand2")
        tooltip_label.pack(side="left", padx=2)
        
        # 提示信息标签（初始隐藏）
        tooltip_frame = tk.Frame(container, bg="white")
        tooltip_wraplength = int(self._cached_width * 0.85)
        
        tooltip_text_widget = ttk.Label(tooltip_frame, text=tooltip_text, 
                                       font=get_cjk_font(9), 
                                       foreground="gray",
                                       wraplength=tooltip_wraplength,
                                       justify="left")
        tooltip_text_widget.pack(anchor="w", padx=15, pady=2)
        
        # 切换显示/隐藏提示信息
        def toggle_tooltip(event=None):
            if tooltip_frame.winfo_viewable():
                tooltip_frame.pack_forget()
            else:
                tooltip_frame.pack(fill="x", padx=5, pady=2)
        
        tooltip_label.bind("<Button-1>", toggle_tooltip)
    
    def display_save_info(self, parent, save_data):
        """显示存档信息"""
        parent.update_idletasks()
        # 确保scrollable_frame的宽度已正确设置为窗口宽度的2/3
        try:
            window_width = self.window.winfo_width()
            if window_width > 1:
                width = int(window_width * 2 / 3)
                self._cached_width = width
                parent.config(width=width)
        except:
            pass
        
        # 1. 角色信息
        memory = save_data.get("memory", {})
        character_section = self.create_section(parent, self.t("character_info"))
        
        character_name = memory.get("name", self.t("not_set"))
        self.add_info_line(character_section, self.t("character_name"), character_name, "memory.name")
        
        seibetu = memory.get("seibetu", 0)
        if seibetu == 1:
            gender_text = self.t("gender_male")
        elif seibetu == 2:
            gender_text = self.t("gender_female")
        else:
            gender_text = self.t("not_set")
        self.add_info_line(character_section, self.t("character_gender"), gender_text, "memory.seibetu")
        
        hutanari = memory.get("hutanari", 0)
        self.add_info_line(character_section, self.t("hutanari"), hutanari, "memory.hutanari")
        
        # 2. 结局统计 + "查看达成条件"按钮
        endings = set(save_data.get("endings", []))
        collected_endings = set(save_data.get("collectedEndings", []))
        missing_endings = sorted(endings - collected_endings, key=lambda x: int(x) if x.isdigit() else 999)
        
        endings_section = self.create_section_with_button(
            parent, 
            self.t("endings_statistics"), 
            self.t("view_requirements"),
            button_command=lambda: self.show_endings_requirements(save_data, endings, collected_endings, missing_endings)
        )
        
        endings_count = len(endings)
        collected_endings_count = len(collected_endings)
        
        self.add_info_line(endings_section, self.t("total_endings"), endings_count, "endings")
        self.add_info_line(endings_section, self.t("collected_endings"), collected_endings_count, "collectedEndings")
        if missing_endings:
            self.add_info_line(endings_section, self.t("missing_endings"), 
                             f"{len(missing_endings)}: {', '.join(missing_endings)}")
        else:
            self.add_info_line(endings_section, self.t("missing_endings"), self.t("none"))
        
        # 3. 贴纸统计 + "查看达成条件"按钮
        stickers_section = self.create_section_with_button(
            parent, 
            self.t("stickers_statistics"), 
            self.t("view_requirements"),
            button_command=lambda: None
        )
        
        stickers = set(save_data.get("sticker", []))
        # 总共132个贴纸，编号1-133，没有82
        all_sticker_ids = set(range(1, 82)) | set(range(83, 134))  # 1-81, 83-133
        stickers_count = len(stickers)
        total_stickers = 132
        missing_stickers = sorted(all_sticker_ids - stickers)
        
        self.add_info_line(stickers_section, self.t("total_stickers"), total_stickers)
        self.add_info_line(stickers_section, self.t("collected_stickers"), stickers_count, "sticker")
        self.add_info_line(stickers_section, self.t("missing_stickers_count"), len(missing_stickers))
        if missing_stickers:
            self.add_info_line(stickers_section, self.t("missing_stickers"), 
                             ", ".join(str(s) for s in missing_stickers))
        else:
            self.add_info_line(stickers_section, self.t("missing_stickers"), self.t("none"))
        
        # 4. 角色统计
        characters_section = self.create_section(
            parent, 
            self.t("characters_statistics")
        )
        
        # 过滤掉空字符串和空白字符
        characters = set(c for c in save_data.get("characters", []) if c and c.strip())
        collected_characters = set(c for c in save_data.get("collectedCharacters", []) if c and c.strip())
        characters_count = max(0, len(characters))
        collected_characters_count = max(0, len(collected_characters))
        missing_characters = sorted(characters - collected_characters)
        
        self.add_info_line(characters_section, self.t("total_characters"), characters_count, "characters")
        self.add_info_line(characters_section, self.t("collected_characters"), collected_characters_count, "collectedCharacters")
        if missing_characters:
            self.add_list_info(characters_section, self.t("missing_characters"), missing_characters)
        else:
            self.add_info_line(characters_section, self.t("missing_characters"), self.t("none"))
        
        # 5. 额外内容统计
        omakes_section = self.create_section(
            parent, 
            self.t("omakes_statistics")
        )
        
        omakes = set(save_data.get("omakes", []))
        omakes_count = len(omakes)
        collected_omakes = omakes & collected_endings  # 已收集的额外内容
        collected_omakes_count = len(collected_omakes)
        missing_omakes = sorted(omakes - collected_endings, key=lambda x: int(x) if x.isdigit() else 999)
        
        # omakes是已观看的额外内容数量
        self.add_info_line(omakes_section, self.t("total_omakes"), omakes_count, "omakes")
        self.add_info_line(omakes_section, self.t("collected_omakes"), collected_omakes_count)
        if missing_omakes:
            self.add_info_line(omakes_section, self.t("missing_omakes"), 
                             f"{len(missing_omakes)}: {', '.join(missing_omakes)}")
        else:
            self.add_info_line(omakes_section, self.t("missing_omakes"), self.t("none"))
        
        # 画廊数量和NG场景数移到额外内容统计
        gallery = save_data.get("gallery", [])
        gallery_count = len(gallery)
        self.add_info_line(omakes_section, self.t("gallery_count"), gallery_count, "gallery")
        
        ng_scene = save_data.get("ngScene", [])
        ng_scene_count = len(ng_scene)
        self.add_info_line(omakes_section, self.t("ng_scene_count"), ng_scene_count, "ngScene")
        
        # 6. 游戏统计
        stats_section = self.create_section(parent, self.t("game_statistics"))
        
        whole_total_mp = save_data.get("wholeTotalMP", 0)
        self.add_info_line(stats_section, self.t("total_mp"), whole_total_mp, "wholeTotalMP")
        
        judge_counts = save_data.get("judgeCounts", {})
        perfect = judge_counts.get("perfect", 0)
        good = judge_counts.get("good", 0)
        bad = judge_counts.get("bad", 0)
        self.add_info_line(stats_section, self.t("judge_perfect"), perfect, "judgeCounts.perfect")
        self.add_info_line(stats_section, self.t("judge_good"), good, "judgeCounts.good")
        self.add_info_line(stats_section, self.t("judge_bad"), bad, "judgeCounts.bad")
        
        epilogue = save_data.get("epilogue", 0)
        self.add_info_line(stats_section, self.t("epilogue_count"), epilogue, "epilogue")
        
        loop_count = save_data.get("loopCount", 0)
        self.add_info_line(stats_section, self.t("loop_count"), loop_count, "loopCount")
        
        # 周回记录：记录到达真结局时的周回数
        loop_record = save_data.get("loopRecord", 0)
        self.add_info_line_with_tooltip(stats_section, self.t("loop_record"), loop_record,
                                       self.t("loop_record_tooltip"), "loopRecord")
        
        # 6.5. 狂信徒相关
        zealot_section = self.create_section(parent, self.t("zealot_related"))
        
        neo = save_data.get("NEO", 0)
        self.add_info_line_with_tooltip(zealot_section, self.t("neo_value"), neo, 
                                       self.t("neo_value_tooltip"), "NEO")
        
        # 是否遭受拉米亚的诅咒
        lamia_noroi = save_data.get("Lamia_noroi", 0)
        self.add_info_line(zealot_section, self.t("lamia_curse"), lamia_noroi, "Lamia_noroi")
        
        # 创伤值
        trauma = save_data.get("trauma", 0)
        self.add_info_line(zealot_section, self.t("trauma_value"), trauma, "trauma")
        
        # killWarning - 狂信徒警告
        kill_warning = save_data.get("killWarning", 0)
        self.add_info_line(zealot_section, self.t("kill_warning"), kill_warning, "killWarning")
        
        # killed - 是否正在进行狂信徒线
        killed = save_data.get("killed", None)
        if killed is None:
            killed_display = self.t("variable_not_exist")
        else:
            killed_display = killed
        self.add_info_line_with_tooltip(zealot_section, self.t("killed"), killed_display,
                                       self.t("killed_tooltip"), "killed")
        
        # kill - 狂信徒线完成数
        kill = save_data.get("kill", 0)
        self.add_info_line_with_tooltip(zealot_section, self.t("kill_count"), kill,
                                       self.t("kill_count_tooltip"), "kill")
        
        # killStart - 在狂信徒线中选择新开一局游戏的次数
        kill_start = save_data.get("killStart", 0)
        self.add_info_line_with_tooltip(zealot_section, self.t("kill_start"), kill_start,
                                       self.t("kill_start_tooltip"), "killStart")
        
        # 7. 其他信息
        other_section = self.create_section(parent, self.t("other_info"))
        
        # 存档列表编号和相册页码（相册页码从0开始，显示时+1）
        save_list_no = save_data.get("saveListNo", 0)
        album_page_no = save_data.get("albumPageNo", 0) + 1
        self.add_info_line(other_section, self.t("save_list_no"), save_list_no, "saveListNo")
        self.add_info_line(other_section, self.t("album_page_no"), album_page_no, "albumPageNo")
        
        desu = save_data.get("desu", 0)
        self.add_info_line(other_section, self.t("desu"), desu, "desu")
        
        hade = save_data.get("hade", 0)
        self.add_info_line(other_section, self.t("hade"), hade, "hade")
        
        camera_enable = memory.get("cameraEnable", 0)
        self.add_info_line(other_section, self.t("camera_enable"), camera_enable, "memory.cameraEnable")
        
        yubiwa = memory.get("yubiwa", 0)
        self.add_info_line(other_section, self.t("yubiwa"), yubiwa, "memory.yubiwa")
        
        autosave = save_data.get("system", {}).get("autosave", False)
        self.add_info_line(other_section, self.t("autosave_enabled"), autosave, "system.autosave")
        
        fullscreen = save_data.get("fullscreen", False)
        self.add_info_line(other_section, self.t("fullscreen"), fullscreen, "fullscreen")
        
        # 添加提示文字
        hint_label = ttk.Label(other_section, text=self.t("other_info_hint"), 
                              font=get_cjk_font(9), 
                              foreground="gray",
                              wraplength=int(self._cached_width * 0.85),
                              justify="left")
        hint_label.pack(anchor="w", padx=5, pady=(5, 0))
        
        # 8. 查看存档文件按钮
        button_frame = tk.Frame(parent, bg="white")
        button_frame.pack(fill="x", padx=10, pady=15)
        view_file_button = ttk.Button(button_frame, text=self.t("view_save_file"), 
                                      command=self.show_save_file_viewer)
        view_file_button.pack(pady=5)
        
        # 所有组件创建完成后，更新滚动区域并绑定滚轮事件
        def finalize_scrolling():
            try:
                # 检查必要的属性是否存在
                if not hasattr(self, 'scrollable_canvas') or not self.scrollable_canvas:
                    return
                if not hasattr(self, 'scrollable_frame') or not self.scrollable_frame:
                    return
                
                # 检查canvas是否仍然存在
                try:
                    self.scrollable_canvas.winfo_exists()
                except:
                    return
                
                # 获取bbox并检查是否有效
                bbox = self.scrollable_canvas.bbox("all")
                if bbox is None:
                    # 如果bbox为None，延迟重试
                    self.window.after(50, finalize_scrolling)
                    return
                
                # 检查bbox是否有效
                if len(bbox) >= 4:
                    x1, y1, x2, y2 = bbox[:4]
                    if x2 > x1 and y2 > y1:
                        # 只有bbox有效时才更新scrollregion
                        self.scrollable_canvas.configure(scrollregion=bbox)
                    else:
                        # bbox无效，延迟重试
                        self.window.after(50, finalize_scrolling)
                        return
                else:
                    # bbox格式不正确，延迟重试
                    self.window.after(50, finalize_scrolling)
                    return
                
                # 为新添加的所有组件绑定滚轮事件（重新绑定整个scrollable_frame及其子组件）
                if hasattr(self, '_bind_mousewheel_recursive') and hasattr(self, '_scrollable_frame'):
                    try:
                        self._bind_mousewheel_recursive(self._scrollable_frame)
                    except:
                        pass
                # 同时重新绑定left_frame，确保整个区域都能滚动
                if hasattr(self, '_bind_mousewheel_recursive') and hasattr(self, '_left_frame'):
                    try:
                        self._bind_mousewheel_recursive(self._left_frame)
                    except:
                        pass
            except Exception:
                # 出错时延迟重试
                self.window.after(50, finalize_scrolling)
        
        self.window.after_idle(finalize_scrolling)
    
    def apply_json_syntax_highlight(self, text_widget, content):
        """应用JSON语法高亮"""
        # 定义高亮规则（按优先级，先匹配更具体的）
        patterns = [
            (r'"[^"]*"', 'string'),  # 字符串（包含转义字符）
            (r'\b(true|false|null)\b', 'keyword'),  # 关键字
            (r'\b\d+\.?\d*\b', 'number'),  # 数字
            (r'[{}[\]]', 'bracket'),  # 括号
            (r'[:,]', 'punctuation'),  # 标点
        ]
        
        # 清除现有tags
        for tag in ['string', 'keyword', 'number', 'bracket', 'punctuation']:
            text_widget.tag_remove(tag, "1.0", "end")
        
        # 获取等宽字体
        try:
            if platform.system() == "Windows":
                mono_font = ("Consolas", 10)
            elif platform.system() == "Darwin":
                mono_font = ("Monaco", 10)
            else:
                mono_font = ("DejaVu Sans Mono", 10)
        except:
            mono_font = ("Courier", 10)
        
        # 配置tag样式
        text_widget.tag_config('string', foreground='#008000', font=mono_font)  # 绿色
        text_widget.tag_config('keyword', foreground='#0000FF', font=mono_font)  # 蓝色
        text_widget.tag_config('number', foreground='#FF0000', font=mono_font)  # 红色
        text_widget.tag_config('bracket', foreground='#000000', font=(mono_font[0], mono_font[1], "bold"))  # 黑色加粗
        text_widget.tag_config('punctuation', foreground='#666666', font=mono_font)  # 灰色
        
        # 应用高亮（按行处理，避免跨行匹配问题）
        lines = content.split('\n')
        for line_num, line in enumerate(lines):
            for pattern, tag_name in patterns:
                for match in re.finditer(pattern, line):
                    start_line = line_num + 1
                    start_col = match.start()
                    end_line = line_num + 1
                    end_col = match.end()
                    start = f"{start_line}.{start_col}"
                    end = f"{end_line}.{end_col}"
                    text_widget.tag_add(tag_name, start, end)
    
    def show_save_file_viewer(self):
        """显示存档文件查看器窗口"""
        if not self.save_data:
            return
        
        # 获取根窗口（从parent向上查找）
        root_window = self.window
        while not isinstance(root_window, tk.Tk) and hasattr(root_window, 'master'):
            root_window = root_window.master
        
        # 创建新窗口
        viewer_window = tk.Toplevel(root_window)
        viewer_window.title(self.t("save_file_viewer_title"))
        viewer_window.geometry("900x700")
        set_window_icon(viewer_window)
        
        
        # 创建主框架
        main_frame = tk.Frame(viewer_window)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 添加提示文字
        hint_frame = tk.Frame(main_frame, bg="white")
        hint_frame.pack(fill="x", pady=(0, 10))
        hint_label = ttk.Label(hint_frame, text=self.t("viewer_hint_text"), 
                               font=get_cjk_font(9), 
                               foreground="gray",
                               wraplength=850,
                               justify="left")
        hint_label.pack(anchor="w", padx=5)
        
        # 创建工具栏
        toolbar = tk.Frame(main_frame)
        toolbar.pack(fill="x", pady=(0, 5))
        
        # 初始化搜索相关变量（需要在update_display之前定义）
        search_matches = []  # 所有匹配位置
        current_search_pos = [0]  # 当前搜索位置
        search_results_label = None  # 稍后创建
        
        # 取消折叠/横置复选框变量
        disable_collapse_var = tk.BooleanVar(value=False)
        
        # 开启修改复选框变量
        enable_edit_var = tk.BooleanVar(value=False)
        
        # 保存按钮（稍后创建，初始禁用）
        save_button = None
        
        # 自定义JSON格式化函数
        def format_json_custom(obj, indent=0):
            """自定义JSON格式化，列表字段在一行内显示"""
            list_fields = ["endings", "collectedEndings", "omakes", "characters", "collectedCharacters", "sticker", "gallery", "ngScene"]
            indent_str = "  " * indent
            
            if isinstance(obj, dict):
                items = []
                for key, value in obj.items():
                    if key in list_fields and isinstance(value, list):
                        # 列表字段横向展示
                        value_str = json.dumps(value, ensure_ascii=False)
                        items.append(f'"{key}": {value_str}')
                    elif isinstance(value, (dict, list)):
                        # 嵌套对象正常格式化
                        value_str = format_json_custom(value, indent + 1)
                        items.append(f'"{key}": {value_str}')
                    else:
                        value_str = json.dumps(value, ensure_ascii=False)
                        items.append(f'"{key}": {value_str}')
                
                if indent == 0:
                    return "{\n" + indent_str + "  " + (",\n" + indent_str + "  ").join(items) + "\n" + indent_str + "}"
                else:
                    return "{\n" + indent_str + "  " + (",\n" + indent_str + "  ").join(items) + "\n" + indent_str + "}"
            elif isinstance(obj, list):
                # 普通列表正常格式化
                items = [format_json_custom(item, indent + 1) if isinstance(item, (dict, list)) else json.dumps(item, ensure_ascii=False) for item in obj]
                return "[\n" + indent_str + "  " + (",\n" + indent_str + "  ").join(items) + "\n" + indent_str + "]"
            else:
                return json.dumps(obj, ensure_ascii=False)
        
        # 初始化显示数据
        collapsed_fields = {}
        fields_to_collapse = ["record", "_tap_effect", "initialVars"]
        for field in fields_to_collapse:
            if field in self.save_data:
                collapsed_fields[field] = self.save_data[field]
            elif isinstance(self.save_data, dict):
                for key, value in self.save_data.items():
                    if isinstance(value, dict) and field in value:
                        collapsed_fields[f"{key}.{field}"] = value[field]
                        break
        
        display_data = json.loads(json.dumps(self.save_data))
        for field_key, field_value in collapsed_fields.items():
            if "." in field_key:
                key_parts = field_key.split(".")
                temp = display_data
                for part in key_parts[:-1]:
                    temp = temp[part]
                temp[key_parts[-1]] = self.t("collapsed_field_text")
            else:
                display_data[field_key] = self.t("collapsed_field_text")
        
        formatted_json = format_json_custom(display_data)
        
        # 创建Text widget和滚动条
        text_frame = tk.Frame(main_frame)
        text_frame.pack(fill="both", expand=True)
        
        # 获取等宽字体
        try:
            if platform.system() == "Windows":
                mono_font = ("Consolas", 10)
            elif platform.system() == "Darwin":
                mono_font = ("Monaco", 10)
            else:
                mono_font = ("DejaVu Sans Mono", 10)
        except:
            mono_font = ("Courier", 10)
        
        # 创建行号栏
        line_numbers = tk.Text(text_frame, 
                              font=mono_font,
                              bg="#e8e8e8",
                              fg="#666666",
                              width=4,
                              padx=5,
                              pady=2,
                              state="disabled",
                              wrap="none",
                              highlightthickness=0,
                              borderwidth=0)
        line_numbers.pack(side="left", fill="y")
        
        # 创建文本编辑区域容器
        text_container = tk.Frame(text_frame)
        text_container.pack(side="left", fill="both", expand=True)
        
        # 垂直滚动条
        v_scrollbar = Scrollbar(text_container, orient="vertical")
        v_scrollbar.pack(side="right", fill="y")
        
        # 水平滚动条
        h_scrollbar = Scrollbar(text_container, orient="horizontal")
        h_scrollbar.pack(side="bottom", fill="x")
        
        text_widget = tk.Text(text_container, 
                             font=mono_font,
                             bg="#f5f5f5",
                             fg="#333333",
                             yscrollcommand=lambda *args: (v_scrollbar.set(*args), update_line_numbers()),
                             xscrollcommand=h_scrollbar.set,
                             wrap="none",
                             tabs=("2c", "4c", "6c", "8c", "10c", "12c", "14c", "16c"))
        text_widget.pack(side="left", fill="both", expand=True)
        v_scrollbar.config(command=lambda *args: (text_widget.yview(*args), update_line_numbers()))
        h_scrollbar.config(command=text_widget.xview)
        
        # 存储原始内容（用于检测修改）
        original_content = formatted_json
        
        def update_line_numbers():
            """更新行号显示"""
            line_numbers.config(state="normal")
            line_numbers.delete("1.0", "end")
            
            # 获取文本总行数
            content = text_widget.get("1.0", "end-1c")
            if content:
                line_count = content.count('\n') + 1
            else:
                line_count = 1
            
            # 添加行号
            for i in range(1, line_count + 1):
                line_numbers.insert("end", f"{i}\n")
            
            line_numbers.config(state="disabled")
            
            # 同步滚动
            line_numbers.yview_moveto(text_widget.yview()[0])
        
        # 绑定文本变化事件以更新行号
        def on_text_change(*args):
            update_line_numbers()
            # 检测修改并添加高亮
            if enable_edit_var.get():
                detect_and_highlight_changes()
        
        text_widget.bind("<<Modified>>", on_text_change)
        text_widget.bind("<KeyRelease>", lambda e: update_line_numbers())
        text_widget.bind("<Button-1>", lambda e: update_line_numbers())
        
        # 存储修改高亮tag
        text_widget.tag_config("user_edit", background="#fff9c4")  # 非常淡的黄色
        
        def detect_and_highlight_changes():
            """检测并高亮用户修改"""
            if not enable_edit_var.get():
                return
            
            # 清除之前的高亮
            text_widget.tag_remove("user_edit", "1.0", "end")
            
            # 获取当前内容
            current_content = text_widget.get("1.0", "end-1c")
            
            # 比较原始内容和当前内容，找出差异
            if current_content != original_content:
                # 简单的逐行比较
                original_lines = original_content.split('\n')
                current_lines = current_content.split('\n')
                
                max_lines = max(len(original_lines), len(current_lines))
                for i in range(max_lines):
                    original_line = original_lines[i] if i < len(original_lines) else ""
                    current_line = current_lines[i] if i < len(current_lines) else ""
                    
                    if original_line != current_line:
                        # 高亮整行
                        line_start = f"{i+1}.0"
                        line_end = f"{i+1}.end"
                        try:
                            text_widget.tag_add("user_edit", line_start, line_end)
                        except:
                            pass
        
        # 插入JSON内容
        text_widget.insert("1.0", formatted_json)
        
        # 存储原始内容（用于检测修改）
        original_content = formatted_json
        
        # 应用语法高亮
        self.apply_json_syntax_highlight(text_widget, formatted_json)
        
        # 更新行号
        update_line_numbers()
        
        # 禁用编辑
        text_widget.config(state="disabled")
        
        # 存储折叠文本的位置范围（用于编辑限制）
        collapsed_text_ranges = []
        
        def update_collapsed_ranges():
            """更新折叠文本的位置范围"""
            collapsed_text_ranges.clear()
            if not disable_collapse_var.get():
                collapsed_text = self.t("collapsed_field_text")
                content = text_widget.get("1.0", "end-1c")
                start_pos = "1.0"
                while True:
                    pos = text_widget.search(collapsed_text, start_pos, "end", exact=True)
                    if not pos:
                        break
                    end_pos = f"{pos}+{len(collapsed_text)}c"
                    collapsed_text_ranges.append((pos, end_pos))
                    start_pos = end_pos
        
        def is_in_collapsed_range(pos):
            """检查位置是否在折叠文本范围内"""
            if disable_collapse_var.get():
                return False  # 取消折叠后，所有区域都可编辑
            for start, end in collapsed_text_ranges:
                if text_widget.compare(start, "<=", pos) and text_widget.compare(pos, "<", end):
                    return True
            return False
        
        def on_text_edit(event=None):
            """文本编辑事件处理"""
            if not enable_edit_var.get():
                return "break"
            
            # 检查是否在折叠区域内
            cursor_pos = text_widget.index("insert")
            if is_in_collapsed_range(cursor_pos):
                from tkinter import messagebox
                messagebox.showwarning(
                    self.t("cannot_edit_collapsed"),
                    self.t("cannot_edit_collapsed_detail"),
                    parent=viewer_window
                )
                return "break"
            
            return None
        
        def on_text_change(event=None):
            """文本改变事件处理（用于检测粘贴等操作）"""
            if not enable_edit_var.get():
                return
            
            # 检查当前光标位置是否在折叠区域内
            try:
                cursor_pos = text_widget.index("insert")
                if is_in_collapsed_range(cursor_pos):
                    # 如果光标在折叠区域内，阻止编辑
                    from tkinter import messagebox
                    messagebox.showwarning(
                        self.t("cannot_edit_collapsed"),
                        self.t("cannot_edit_collapsed_detail"),
                        parent=viewer_window
                    )
                    # 尝试撤销最后一次操作
                    try:
                        text_widget.edit_undo()
                    except:
                        pass
            except:
                pass
        
        # 绑定文本编辑事件
        text_widget.bind("<KeyPress>", on_text_edit)
        text_widget.bind("<Button-1>", lambda e: update_collapsed_ranges())
        text_widget.bind("<<Modified>>", on_text_change)
        
        # 启用撤销功能
        text_widget.config(undo=True)
        
        # 定义update_display函数
        def update_display(check_changes=False):
            """更新显示内容"""
            nonlocal original_content
            
            # 如果切换折叠/横置状态，检查是否有未保存的修改
            if check_changes and enable_edit_var.get():
                current_content = text_widget.get("1.0", "end-1c")
                if current_content != original_content:
                    # 有未保存的修改，弹出确认提示
                    from tkinter import messagebox
                    result = messagebox.askyesno(
                        self.t("refresh_confirm_title"),
                        self.t("unsaved_changes_warning"),
                        parent=viewer_window
                    )
                    if not result:
                        # 用户取消操作，恢复复选框状态
                        disable_collapse_var.set(not disable_collapse_var.get())
                        return
            
            text_widget.config(state="normal")
            
            # 清除搜索高亮
            text_widget.tag_delete("search_highlight")
            search_matches.clear()
            current_search_pos[0] = 0
            if search_results_label:
                search_results_label.config(text="")
            
            if disable_collapse_var.get():
                # 取消折叠/横置：显示完整解码后的文件
                full_json = json.dumps(self.save_data, ensure_ascii=False, indent=2)
                text_widget.delete("1.0", "end")
                text_widget.insert("1.0", full_json)
                self.apply_json_syntax_highlight(text_widget, full_json)
                original_content = full_json
                collapsed_text_ranges.clear()  # 取消折叠后，没有折叠区域
            else:
                # 应用折叠和横置
                # 处理需要折叠的字段：record, _tap_effect, initialVars
                collapsed_fields = {}  # 记录哪些字段被折叠
                fields_to_collapse = ["record", "_tap_effect", "initialVars"]
                
                # 检查需要折叠的字段
                for field in fields_to_collapse:
                    if field in self.save_data:
                        collapsed_fields[field] = self.save_data[field]
                    elif isinstance(self.save_data, dict):
                        # 检查嵌套的字段
                        for key, value in self.save_data.items():
                            if isinstance(value, dict) and field in value:
                                collapsed_fields[f"{key}.{field}"] = value[field]
                                break
                
                # 创建处理后的数据用于显示
                display_data = json.loads(json.dumps(self.save_data))  # 深拷贝
                
                # 折叠字段
                for field_key, field_value in collapsed_fields.items():
                    if "." in field_key:
                        key_parts = field_key.split(".")
                        temp = display_data
                        for part in key_parts[:-1]:
                            temp = temp[part]
                        temp[key_parts[-1]] = self.t("collapsed_field_text")
                    else:
                        display_data[field_key] = self.t("collapsed_field_text")
                
                # 自定义JSON格式化：列表字段横向展示
                formatted_json = format_json_custom(display_data)
                text_widget.delete("1.0", "end")
                text_widget.insert("1.0", formatted_json)
                self.apply_json_syntax_highlight(text_widget, formatted_json)
                original_content = formatted_json
                
                # 更新折叠文本范围
                update_collapsed_ranges()
            
            # 更新行号
            update_line_numbers()
            
            # 根据编辑模式设置编辑状态
            if enable_edit_var.get():
                text_widget.config(state="normal")
                if save_button:
                    save_button.config(state="normal")
                # 检测并高亮修改
                detect_and_highlight_changes()
            else:
                text_widget.config(state="disabled")
                if save_button:
                    save_button.config(state="disabled")
                # 清除修改高亮
                text_widget.tag_remove("user_edit", "1.0", "end")
        
        # 添加取消折叠/横置复选框
        def toggle_collapse():
            """切换折叠/横置状态"""
            # update_display会检查未保存的修改
            update_display(check_changes=True)
        
        disable_collapse_checkbox = ttk.Checkbutton(toolbar, 
                                                     text=self.t("disable_collapse_horizontal"),
                                                     variable=disable_collapse_var,
                                                     command=toggle_collapse)
        disable_collapse_checkbox.pack(side="left", padx=5)
        
        # 添加查找功能
        search_frame = tk.Frame(toolbar)
        search_frame.pack(side="left", padx=5)
        
        search_entry = ttk.Entry(search_frame, width=20)
        search_entry.pack(side="left", padx=2)
        
        search_results_label = ttk.Label(search_frame, text="")
        search_results_label.pack(side="left", padx=2)
        
        # 添加复制按钮
        def copy_to_clipboard():
            viewer_window.clipboard_clear()
            # 复制完整数据
            full_json = json.dumps(self.save_data, ensure_ascii=False, indent=2)
            viewer_window.clipboard_append(full_json)
        
        copy_button = ttk.Button(toolbar, text=self.t("copy_to_clipboard"), command=copy_to_clipboard)
        copy_button.pack(side="left", padx=5)
        
        # 添加右侧区域（用于放置开启修改复选框和保存按钮）
        toolbar_right = tk.Frame(toolbar)
        toolbar_right.pack(side="right", padx=5)
        
        # 添加刷新按钮
        def check_unsaved_changes():
            """检查是否有未保存的修改，如果有则弹出确认提示"""
            if enable_edit_var.get():
                current_content = text_widget.get("1.0", "end-1c")
                if current_content != original_content:
                    # 有未保存的修改，弹出确认提示
                    from tkinter import messagebox
                    result = messagebox.askyesno(
                        self.t("refresh_confirm_title"),
                        self.t("unsaved_changes_warning"),
                        parent=viewer_window  # 确保从viewer_window弹出
                    )
                    return result
            return True  # 没有修改或未开启编辑模式，允许继续
        
        # 绑定窗口关闭事件
        def on_window_close():
            """窗口关闭事件处理"""
            # 检查是否有未保存的修改
            if not check_unsaved_changes():
                # 用户取消关闭，阻止窗口关闭
                return
            viewer_window.destroy()
            # 窗口关闭后，刷新存档分析页面
            self.refresh()
        
        viewer_window.protocol("WM_DELETE_WINDOW", on_window_close)
        
        def refresh_save_file():
            """刷新存档文件"""
            # 检查是否有未保存的修改
            if not check_unsaved_changes():
                return
            
            # 重新加载存档文件
            self.save_data = self.load_save_file()
            if not self.save_data:
                from tkinter import messagebox
                messagebox.showerror(
                    self.t("error"),
                    self.t("save_file_not_found"),
                    parent=viewer_window
                )
                return
            
            # 更新显示
            update_display()
        
        refresh_button = ttk.Button(toolbar_right, text=self.t("refresh"), command=refresh_save_file)
        refresh_button.pack(side="right", padx=5)
        
        # 添加开启修改复选框（最右侧）
        enable_edit_checkbox = ttk.Checkbutton(toolbar_right, 
                                               text=self.t("enable_edit"),
                                               variable=enable_edit_var,
                                               command=lambda: toggle_edit_mode())
        enable_edit_checkbox.pack(side="right", padx=5)
        
        # 添加保存按钮
        def save_save_file():
            """保存存档文件"""
            try:
                # 获取文本内容
                text_widget.config(state="normal")
                content = text_widget.get("1.0", "end-1c")
                
                # 验证JSON格式
                try:
                    edited_data = json.loads(content)
                except json.JSONDecodeError as e:
                    text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
                    from tkinter import messagebox
                    messagebox.showerror(
                        self.t("json_format_error"),
                        self.t("json_format_error_detail").format(error=str(e)),
                        parent=viewer_window
                    )
                    return
                
                # 将显示格式转回原始格式
                # 如果取消折叠/横置，数据已经是完整格式，直接使用
                # 如果折叠/横置，需要恢复折叠字段的原始值
                if not disable_collapse_var.get():
                    # 恢复折叠字段的原始值
                    collapsed_text = self.t("collapsed_field_text")
                    fields_to_collapse = ["record", "_tap_effect", "initialVars"]
                    
                    # 检查并恢复折叠字段
                    for field in fields_to_collapse:
                        if field in edited_data:
                            if isinstance(edited_data[field], str) and edited_data[field] == collapsed_text:
                                # 这是折叠字段，恢复原始值
                                if field in self.save_data:
                                    edited_data[field] = self.save_data[field]
                        else:
                            # 检查嵌套字段
                            for key, value in self.save_data.items():
                                if isinstance(value, dict) and field in value:
                                    # 检查edited_data中是否有这个嵌套字段
                                    if key in edited_data and isinstance(edited_data[key], dict):
                                        if field in edited_data[key]:
                                            if isinstance(edited_data[key][field], str) and edited_data[key][field] == collapsed_text:
                                                # 这是折叠字段，恢复原始值
                                                edited_data[key][field] = value[field]
                                    elif key in edited_data and isinstance(edited_data[key], str) and edited_data[key] == collapsed_text:
                                        # 整个嵌套对象被折叠了，恢复整个对象
                                        edited_data[key] = value
                                    break
                
                # 确认保存
                from tkinter import messagebox
                result = messagebox.askyesno(
                    self.t("save_confirm_title"),
                    self.t("save_confirm_text"),
                    parent=viewer_window
                )
                
                if not result:
                    text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
                    return
                
                # 保存到文件
                sf_path = os.path.join(self.storage_dir, 'DevilConnection_sf.sav')
                json_str = json.dumps(edited_data, ensure_ascii=False)
                encoded = urllib.parse.quote(json_str)
                
                with open(sf_path, 'w', encoding='utf-8') as f:
                    f.write(encoded)
                
                # 更新self.save_data
                self.save_data = edited_data
                
                # 更新原始内容
                nonlocal original_content
                original_content = content
                
                # 显示成功消息
                messagebox.showinfo(
                    self.t("success"), 
                    self.t("save_success"),
                    parent=viewer_window
                )
                
                # 刷新显示
                update_display()
                
            except Exception as e:
                from tkinter import messagebox
                messagebox.showerror(
                    self.t("save_failed"),
                    str(e),
                    parent=viewer_window
                )
                text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
        
        save_button = ttk.Button(toolbar_right, text=self.t("save_file"), 
                                command=save_save_file, state="disabled")
        save_button.pack(side="right", padx=5)
        
        def toggle_edit_mode():
            """切换编辑模式"""
            # 如果取消勾选"开启修改"，检查是否有未保存的修改
            if not enable_edit_var.get():
                if not check_unsaved_changes():
                    # 用户取消操作，恢复勾选状态
                    enable_edit_var.set(True)
                    return
            
            # 每次切换都刷新sav文件
            self.save_data = self.load_save_file()
            if not self.save_data:
                enable_edit_var.set(False)
                from tkinter import messagebox
                messagebox.showerror(
                    self.t("error"),
                    self.t("save_file_not_found"),
                    parent=viewer_window
                )
                return
            
            if enable_edit_var.get():
                # 开启编辑模式：刷新显示并允许编辑
                update_display()
                # 更新原始内容为当前显示的内容
                nonlocal original_content
                original_content = text_widget.get("1.0", "end-1c")
            else:
                # 关闭编辑模式：禁用编辑
                text_widget.config(state="disabled")
                if save_button:
                    save_button.config(state="disabled")
                # 清除修改高亮
                text_widget.tag_remove("user_edit", "1.0", "end")
        
        def find_text(direction="next"):
            """查找文本"""
            search_term = search_entry.get()
            if not search_term:
                search_results_label.config(text="")
                return
            
            # 启用编辑以进行搜索
            was_disabled = text_widget.cget("state") == "disabled"
            if was_disabled:
                text_widget.config(state="normal")
            content = text_widget.get("1.0", "end-1c")
            
            # 清除之前的搜索高亮
            text_widget.tag_delete("search_highlight")
            text_widget.tag_config("search_highlight", background="yellow")
            
            # 查找所有匹配
            search_matches.clear()
            start_pos = "1.0"
            while True:
                pos = text_widget.search(search_term, start_pos, "end", nocase=True)
                if not pos:
                    break
                end_pos = f"{pos}+{len(search_term)}c"
                search_matches.append((pos, end_pos))
                text_widget.tag_add("search_highlight", pos, end_pos)
                start_pos = end_pos
            
            # 导航到匹配位置
            if search_matches:
                if direction == "next":
                    current_search_pos[0] = (current_search_pos[0] + 1) % len(search_matches)
                else:
                    current_search_pos[0] = (current_search_pos[0] - 1) % len(search_matches)
                
                pos, end_pos = search_matches[current_search_pos[0]]
                text_widget.see(pos)
                text_widget.mark_set("insert", pos)
                text_widget.see(pos)
                
                search_results_label.config(text=f"{current_search_pos[0] + 1}/{len(search_matches)}")
            else:
                search_results_label.config(text="未找到")
            
            if was_disabled:
                text_widget.config(state="disabled")
        
        def find_next():
            find_text("next")
        
        def find_prev():
            find_text("prev")
        
        find_next_button = ttk.Button(search_frame, text="↓", command=find_next, width=3)
        find_next_button.pack(side="left", padx=2)
        
        find_prev_button = ttk.Button(search_frame, text="↑", command=find_prev, width=3)
        find_prev_button.pack(side="left", padx=2)
        
        # 绑定Ctrl+F
        def on_ctrl_f(event):
            search_entry.focus()
            search_entry.select_range(0, "end")
            return "break"
        
        viewer_window.bind("<Control-f>", on_ctrl_f)
        viewer_window.bind("<Control-F>", on_ctrl_f)
        
        # 绑定回车键查找下一个，Shift+Enter查找上一个
        def on_search_enter(event):
            if event.state & 0x1:  # Shift键
                find_prev()
            else:
                find_next()
            return "break"
        
        search_entry.bind("<Return>", on_search_enter)
    
    def show_endings_requirements(self, save_data, endings, collected_endings, missing_endings):
        """显示结局达成条件窗口"""
        # 获取根窗口
        root_window = self.window
        while not isinstance(root_window, tk.Tk) and hasattr(root_window, 'master'):
            root_window = root_window.master
        
        # 创建新窗口
        requirements_window = tk.Toplevel(root_window)
        requirements_window.title(self.t("endings_statistics") + " - " + self.t("view_requirements"))
        requirements_window.geometry("800x600")
        set_window_icon(requirements_window)
        
        # 创建主框架
        main_frame = tk.Frame(requirements_window, bg="white")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 创建滚动区域
        canvas = tk.Canvas(main_frame, bg="white")
        scrollable_frame = tk.Frame(canvas, bg="white")
        
        scrollbar = Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        def update_scrollregion(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        scrollable_frame.bind("<Configure>", update_scrollregion)
        
        # 获取所有结局ID（1-45）
        all_ending_ids = [str(i) for i in range(1, 46)]
        
        # 将 missing_endings 转换为集合以便快速查找
        missing_endings_set = set(missing_endings)
        collected_endings_set = set(collected_endings)
        
        # 分离已达成和未达成的结局
        collected_list = []
        missing_list = []
        
        for ending_id in all_ending_ids:
            ending_key = f"END{ending_id}_unlock_cond"
            condition_text = self.t(ending_key)
            
            # 判断是否为未达成的结局
            # 如果结局不在 collected_endings 中，则视为未达成
            if ending_id not in collected_endings_set:
                # 未达成的结局
                missing_list.append((ending_id, condition_text))
            else:
                # 已达成的结局
                collected_list.append((ending_id, condition_text))
        
        # 先显示未达成的结局（突出显示），然后显示已达成的结局
        display_order = missing_list + collected_list
        
        # 创建标题
        title_label = ttk.Label(scrollable_frame, 
                               text=self.t("endings_statistics") + " - " + self.t("view_requirements"),
                               font=get_cjk_font(14, "bold"))
        title_label.pack(anchor="w", pady=(0, 10))
        
        # 如果有未达成的结局，添加提示
        if missing_list:
            hint_label = ttk.Label(scrollable_frame,
                                 text=f"⚠ {self.t('missing_endings')}: {len(missing_list)}",
                                 font=get_cjk_font(11, "bold"),
                                 foreground="red")
            hint_label.pack(anchor="w", pady=(0, 10))
        
        # 显示所有结局
        for ending_id, condition_text in display_order:
            # 创建每个结局的框架
            ending_frame = tk.Frame(scrollable_frame, bg="white", relief="ridge", borderwidth=1)
            ending_frame.pack(fill="x", pady=5, padx=5)
            
            # 判断是否为未达成的结局
            is_missing = ending_id not in collected_endings_set
            
            # 设置背景色和字体样式
            if is_missing:
                # 未达成的结局：使用浅红色背景，加粗字体
                ending_frame.config(bg="#ffe6e6")
                title_bg = "#ffe6e6"
                title_fg = "red"
                title_font = get_cjk_font(11, "bold")
            else:
                # 已达成的结局：使用浅绿色背景，普通字体
                ending_frame.config(bg="#e6ffe6")
                title_bg = "#e6ffe6"
                title_fg = "green"
                title_font = get_cjk_font(11, "normal")
            
            # 结局标题
            title_frame = tk.Frame(ending_frame, bg=title_bg)
            title_frame.pack(fill="x", padx=5, pady=5)
            
            ending_title = ttk.Label(title_frame, 
                                    text=f"END{ending_id}",
                                    font=title_font,
                                    foreground=title_fg,
                                    background=title_bg)
            ending_title.pack(side="left", padx=5)
            
            # 状态标签
            if is_missing:
                status_label = ttk.Label(title_frame,
                                       text="❌ " + self.t("missing_endings"),
                                       font=get_cjk_font(10, "bold"),
                                       foreground="red",
                                       background=title_bg)
            else:
                status_label = ttk.Label(title_frame,
                                       text="✓ " + self.t("collected_endings"),
                                       font=get_cjk_font(10, "normal"),
                                       foreground="green",
                                       background=title_bg)
            status_label.pack(side="right", padx=5)
            
            # 达成条件文本
            condition_frame = tk.Frame(ending_frame, bg=title_bg)
            condition_frame.pack(fill="x", padx=10, pady=(0, 5))
            
            wraplength = 700
            condition_label = ttk.Label(condition_frame,
                                        text=condition_text,
                                        font=get_cjk_font(10),
                                        wraplength=wraplength,
                                        justify="left",
                                        background=title_bg)
            condition_label.pack(anchor="w", padx=5)
        
        # 布局滚动条和画布
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 绑定鼠标滚轮
        def on_mousewheel(event):
            try:
                if event.delta:
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                else:
                    if event.num == 4:
                        canvas.yview_scroll(-1, "units")
                    elif event.num == 5:
                        canvas.yview_scroll(1, "units")
            except:
                pass
        
        canvas.bind("<MouseWheel>", on_mousewheel)
        canvas.bind("<Button-4>", on_mousewheel)
        canvas.bind("<Button-5>", on_mousewheel)
        
        # 更新滚动区域
        requirements_window.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

