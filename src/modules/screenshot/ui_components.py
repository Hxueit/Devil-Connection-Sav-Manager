"""UI组件创建模块

负责创建和配置截图管理UI的所有组件，包括布局、样式设置等。
"""

from typing import Optional, Callable
import tkinter as tk
from tkinter import Scrollbar, Label
from tkinter import ttk

from src.modules.screenshot.constants import PREVIEW_WIDTH, PREVIEW_HEIGHT
from src.modules.screenshot.animation_constants import (
    CHECKBOX_STYLE_NORMAL,
    CHECKBOX_STYLE_HINT,
    HINT_COLOR_ORANGE
)


class UIComponentsBuilder:
    """UI组件构建器
    
    负责创建和配置UI组件。
    """
    
    def __init__(self, parent_frame: tk.Frame, root: tk.Tk, 
                 get_cjk_font: Callable, colors, t_func: Callable):
        """初始化UI组件构建器
        
        Args:
            parent_frame: 父框架
            root: 根窗口
            get_cjk_font: 字体获取函数
            colors: 颜色常量类
            t_func: 翻译函数
        """
        self.parent_frame = parent_frame
        self.root = root
        self.get_cjk_font = get_cjk_font
        self.colors = colors
        self.t = t_func
    
    def create_hint_label(self, storage_dir: Optional[str]) -> tk.Label:
        """创建提示标签
        
        Args:
            storage_dir: 存储目录，如果为None则显示提示
            
        Returns:
            提示标签组件
        """
        hint_label = tk.Label(
            self.parent_frame, 
            text=self.t("select_dir_hint"), 
            fg=self.colors.TEXT_HIGHLIGHT, 
            font=self.get_cjk_font(10),
            bg=self.colors.LIGHT_GRAY
        )
        if not storage_dir:
            hint_label.pack(pady=15)
        return hint_label
    
    def create_success_label(self) -> tk.Label:
        """创建成功提示标签
        
        Returns:
            成功提示标签组件
        """
        return tk.Label(
            self.parent_frame, 
            text="", 
            fg=self.colors.TEXT_SUCCESS_MINT, 
            font=self.get_cjk_font(10),
            bg=self.colors.LIGHT_GRAY
        )
    
    def create_list_header(self, load_screenshots_callback: Callable,
                          sort_asc_callback: Callable,
                          sort_desc_callback: Callable,
                          enable_edit_callback: Optional[Callable[[], None]] = None) -> tuple:
        """创建列表头部框架
        
        Args:
            load_screenshots_callback: 刷新回调函数
            sort_asc_callback: 升序排序回调函数
            sort_desc_callback: 降序排序回调函数
            enable_edit_callback: 开启修改回调函数，可选
            
        Returns:
            (list_header_frame, list_label, sort_asc_button, sort_desc_button, enable_edit_checkbox) 元组
        """
        list_header_frame = tk.Frame(self.parent_frame, bg=self.colors.LIGHT_GRAY)
        list_header_frame.pack(pady=8, fill="x")
        list_header_frame.columnconfigure(0, weight=1)
        list_header_frame.columnconfigure(2, weight=1)
        
        # 左侧占位
        left_spacer = tk.Frame(list_header_frame, bg=self.colors.LIGHT_GRAY)
        left_spacer.grid(row=0, column=0, sticky="ew")
        
        # 左侧标题
        left_header = tk.Frame(list_header_frame, bg=self.colors.LIGHT_GRAY)
        left_header.grid(row=0, column=1)
        list_label = tk.Label(
            left_header, 
            text=self.t("screenshot_list"), 
            font=self.get_cjk_font(10), 
            fg=self.colors.TEXT_PRIMARY,
            bg=self.colors.LIGHT_GRAY
        )
        list_label.pack(side="left", padx=5)
        
        # 右侧按钮区域
        right_area = tk.Frame(list_header_frame, bg=self.colors.LIGHT_GRAY)
        right_area.grid(row=0, column=2, sticky="ew")
        right_area.columnconfigure(0, weight=1)
        
        right_spacer = tk.Frame(right_area, bg=self.colors.LIGHT_GRAY)
        right_spacer.grid(row=0, column=0, sticky="ew")
        
        button_container = tk.Frame(right_area, bg=self.colors.LIGHT_GRAY)
        button_container.grid(row=0, column=1, sticky="e")
        
        ttk.Button(
            button_container, 
            text=self.t("refresh"), 
            command=load_screenshots_callback, 
            width=3
        ).pack(side="left", padx=2)
        
        sort_asc_button = ttk.Button(
            button_container, 
            text=self.t("sort_asc"), 
            command=sort_asc_callback
        )
        sort_asc_button.pack(side="left", padx=2)
        
        sort_desc_button = ttk.Button(
            button_container, 
            text=self.t("sort_desc"), 
            command=sort_desc_callback
        )
        sort_desc_button.pack(side="left", padx=2)
        
        # 开启修改复选框
        enable_edit_checkbox = None
        if enable_edit_callback is not None:
            DEFAULT_CHECKBOX_PADX = 5
            enable_edit_var = tk.BooleanVar(value=False)
            # 创建包装 Frame 用于抖动动画（保持 pack 布局）
            checkbox_wrapper = tk.Frame(button_container, bg=self.colors.LIGHT_GRAY)
            checkbox_wrapper.pack(side="left", padx=DEFAULT_CHECKBOX_PADX)
            
            # 创建自定义样式以匹配背景
            checkbox_style = ttk.Style(self.root)
            checkbox_style.configure(
                CHECKBOX_STYLE_NORMAL,
                background=self.colors.LIGHT_GRAY
            )
            checkbox_style.configure(
                CHECKBOX_STYLE_HINT,
                background=self.colors.LIGHT_GRAY,
                foreground=HINT_COLOR_ORANGE
            )
            
            enable_edit_checkbox = ttk.Checkbutton(
                checkbox_wrapper,
                text=self.t("enable_edit"),
                variable=enable_edit_var,
                command=enable_edit_callback,
                style=CHECKBOX_STYLE_NORMAL
            )
            enable_edit_checkbox.pack()
            # 保存变量引用以便后续访问
            enable_edit_checkbox.var = enable_edit_var
            # 保存包装 Frame 引用以便抖动动画
            enable_edit_checkbox.wrapper = checkbox_wrapper
            # 保存原始布局方法（在 pack 之后保存）
            button_container.update_idletasks()
            enable_edit_checkbox._original_pack_info = checkbox_wrapper.pack_info()
        
        return list_header_frame, list_label, sort_asc_button, sort_desc_button, enable_edit_checkbox
    
    def create_list_frame(self) -> tuple:
        """创建列表框架
        
        Returns:
            (list_frame, preview_frame, list_right_frame, tree_frame) 元组
        """
        list_frame = tk.Frame(self.parent_frame, bg=self.colors.LIGHT_GRAY)
        list_frame.pack(fill="both", expand=True, pady=8)
        
        # 预览区域
        preview_frame = tk.Frame(list_frame, bg=self.colors.LIGHT_GRAY)
        preview_frame.pack(side="left", padx=5)
        
        preview_label_text = tk.Label(
            preview_frame, 
            text=self.t("preview"), 
            font=self.get_cjk_font(10), 
            bg=self.colors.LIGHT_GRAY
        )
        preview_label_text.pack()
        
        preview_container = tk.Frame(
            preview_frame, 
            width=PREVIEW_WIDTH, 
            height=PREVIEW_HEIGHT, 
            bg=self.colors.PREVIEW_BG, 
            relief="sunken"
        )
        preview_container.pack()
        preview_container.pack_propagate(False)
        
        preview_label = Label(preview_container, bg=self.colors.PREVIEW_BG)
        preview_label.pack(fill="both", expand=True)
        
        # 列表右侧区域
        list_right_frame = tk.Frame(list_frame)
        list_right_frame.pack(side="right", fill="both", expand=True)
        
        tree_frame = tk.Frame(list_right_frame)
        tree_frame.pack(side="left", fill="both", expand=True)
        
        return list_frame, preview_frame, list_right_frame, tree_frame, preview_label_text, preview_label
    
    def create_treeview(self, tree_frame: tk.Frame, 
                       toggle_select_all_callback: Callable) -> tuple:
        """创建Treeview组件
        
        Args:
            tree_frame: 树框架
            toggle_select_all_callback: 全选切换回调函数
            
        Returns:
            (tree, scrollbar, drag_indicator_line) 元组
        """
        scrollbar = Scrollbar(tree_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        
        tree_style = ttk.Style(self.root)
        tree_style.configure("Screenshot.Treeview", rowheight=26, padding=(0, 6))
        
        tree = ttk.Treeview(
            tree_frame,
            columns=("select", "info"),
            show="headings",
            height=20,
            style="Screenshot.Treeview"
        )
        
        # 配置列
        tree.heading("#0", text="", anchor="w")
        tree.column("#0", width=0, stretch=False, minwidth=0)
        
        tree.heading("select", text="☐", anchor="center", 
                    command=toggle_select_all_callback)
        tree.column("select", width=40, stretch=False, anchor="center")
        
        tree.heading("info", text=self.t("list_header"), anchor="w")
        tree.column("info", width=800, stretch=True)
        
        # 配置标签样式
        tree.tag_configure("DragIndicatorUp", foreground="#85A9A5")
        tree.tag_configure("DragIndicatorDown", foreground="#D06CAA")
        tree.tag_configure("NewIndicator", foreground="#FED491")
        tree.tag_configure("ReplaceIndicator", foreground="#BDC9B2")
        tree.tag_configure("PageHeaderLeft", foreground="#D26FAB", 
                          font=self.get_cjk_font(10, "bold"))
        tree.tag_configure("PageHeaderRight", foreground="#85A9A5", 
                          font=self.get_cjk_font(10, "bold"))
        tree.tag_configure("Dragging", background="#E3F2FD", foreground="#1976D2")
        
        scrollbar.config(command=tree.yview)
        tree.config(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        
        # 拖拽指示线
        drag_indicator_line = tk.Frame(tree_frame, bg="black", height=3)
        drag_indicator_line.place_forget()
        
        return tree, scrollbar, drag_indicator_line
    
    def create_action_buttons(self, add_callback: Callable,
                            replace_callback: Callable,
                            delete_callback: Callable,
                            gallery_callback: Callable) -> tuple:
        """创建操作按钮
        
        Args:
            add_callback: 添加回调函数
            replace_callback: 替换回调函数
            delete_callback: 删除回调函数
            gallery_callback: 画廊回调函数
            
        Returns:
            (button_frame, add_button, replace_button, delete_button, gallery_preview_button) 元组
        """
        button_frame = ttk.Frame(self.parent_frame)
        button_frame.pack(pady=5)
        
        add_button = ttk.Button(
            button_frame, 
            text=self.t("add_new"), 
            command=add_callback
        )
        add_button.pack(side='left', padx=5)
        
        replace_button = ttk.Button(
            button_frame, 
            text=self.t("replace_selected"), 
            command=replace_callback
        )
        replace_button.pack(side='left', padx=5)
        
        delete_button = ttk.Button(
            button_frame, 
            text=self.t("delete_selected"), 
            command=delete_callback
        )
        delete_button.pack(side='left', padx=5)
        
        gallery_preview_button = ttk.Button(
            button_frame, 
            text=self.t("gallery_preview"), 
            command=gallery_callback
        )
        gallery_preview_button.pack(side='left', padx=5)
        
        return button_frame, add_button, replace_button, delete_button, gallery_preview_button
    
    def create_export_buttons(self, preview_frame: tk.Frame,
                             export_callback: Callable,
                             batch_export_callback: Callable) -> tuple:
        """创建导出按钮
        
        Args:
            preview_frame: 预览框架
            export_callback: 导出回调函数
            batch_export_callback: 批量导出回调函数
            
        Returns:
            (export_button, batch_export_button) 元组
        """
        export_button = ttk.Button(
            preview_frame, 
            text=self.t("export_image"), 
            command=export_callback
        )
        export_button.pack(pady=8)
        export_button.pack_forget()
        
        batch_export_button = ttk.Button(
            preview_frame, 
            text=self.t("batch_export"), 
            command=batch_export_callback
        )
        batch_export_button.pack(pady=8)
        batch_export_button.pack_forget()
        
        return export_button, batch_export_button

