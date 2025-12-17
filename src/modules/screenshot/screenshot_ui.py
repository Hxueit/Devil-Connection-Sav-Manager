"""截图管理UI主模块

负责截图管理的UI界面协调，整合各个功能模块。
"""

from typing import Optional, Callable
import tkinter as tk
from tkinter import messagebox, ttk

from src.modules.screenshot.screenshot_manager import ScreenshotManager
from src.modules.screenshot.gallery_preview import GalleryPreview
from src.modules.screenshot.dialogs import ScreenshotDialogs
from src.modules.screenshot.constants import PREVIEW_WIDTH, PREVIEW_HEIGHT
from src.modules.screenshot.checkbox_manager import CheckboxManager
from src.modules.screenshot.drag_handler import DragHandler
from src.modules.screenshot.preview_handler import PreviewHandler
from src.modules.screenshot.status_indicator import StatusIndicator
from src.modules.screenshot.list_renderer import ListRenderer
from src.modules.screenshot.ui_components import UIComponentsBuilder
from src.modules.screenshot.edit_mode_manager import EditModeManager
from src.modules.screenshot.animation_constants import (
    SHAKE_OFFSETS,
    SHAKE_STEP_DELAY_MS,
    SHAKE_COLOR_RESTORE_DELAY_MS,
    HINT_COLOR_ORANGE,
    CHECKBOX_STYLE_NORMAL,
    CHECKBOX_STYLE_HINT
)

from src.utils.styles import Colors
from src.utils.ui_utils import (
    showinfo_relative, 
    showwarning_relative, 
    showerror_relative, 
    askyesno_relative
)


class ScreenshotManagerUI:
    """截图管理UI协调器
    
    负责整合各个功能模块，提供统一的UI接口。
    """
    
    def __init__(self, parent_frame: tk.Frame, root: tk.Tk, 
                 storage_dir: Optional[str], translations: dict, 
                 current_language: str, t_func: Callable[[str], str]):
        """初始化截图管理UI
        
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
        
        # 导入工具函数
        from src.utils.styles import get_cjk_font, Colors
        from src.utils.ui_utils import set_window_icon
        self.get_cjk_font = get_cjk_font
        self.Colors = Colors
        self.set_window_icon = set_window_icon
        
        # 初始化业务逻辑管理器
        self.screenshot_manager = ScreenshotManager(t_func=self.t)
        
        # 初始化编辑模式管理器（默认禁用）
        self.edit_mode_manager = EditModeManager(initial_state=False)
        self.edit_mode_manager.register_state_change_callback(self._on_edit_mode_changed)
        
        # 初始化UI组件构建器
        self.ui_builder = UIComponentsBuilder(
            self.parent_frame, self.root, 
            self.get_cjk_font, self.Colors, self.t
        )
        
        # 创建基础UI组件（不依赖功能模块的部分）
        self._create_base_ui_components()
        
        # 初始化功能模块（需要tree等组件）
        self.checkbox_manager = CheckboxManager(
            self.tree, self.root, self.t,
            selection_change_callback=self.update_batch_export_button
        )
        self.status_indicator = StatusIndicator(self.tree, self.root)
        self.list_renderer = ListRenderer(
            self.tree, self.checkbox_manager, self.t, self.screenshot_manager
        )
        self.preview_handler = PreviewHandler(
            self.preview_label, self.root, self.storage_dir,
            self.screenshot_manager, self.Colors, self.t, 
            preview_size=(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        )
        self.drag_handler = DragHandler(
            self.tree, self.root, self.checkbox_manager, 
            self.screenshot_manager, self.load_screenshots,
            self.checkbox_manager.update_checkbox_display,
            self.edit_mode_manager
        )
        self.drag_handler.setup_drag_indicator_line(self.tree_frame)
        
        # 完成UI组件创建（需要功能模块的部分）
        self._complete_ui_components()
        
        # 初始化其他组件
        self.gallery_preview = GalleryPreview(
            self.root, self.storage_dir, self.screenshot_manager,
            self.t, self.get_cjk_font, self.Colors, self.set_window_icon
        )
        self.dialogs = ScreenshotDialogs(
            self.root, self.storage_dir, self.screenshot_manager,
            self.t, self.get_cjk_font, self.Colors, self.set_window_icon,
            self.translations, self.current_language,
            self.load_screenshots, self.show_status_indicator
        )
        
        # 绑定事件
        self._bind_events()
        
        # 初始化编辑模式状态（默认禁用所有修改操作）
        self._update_edit_mode_ui()
        
        # 如果已有存储目录，加载截图
        if self.storage_dir:
            self.screenshot_manager.set_storage_dir(self.storage_dir)
            self.load_screenshots(silent=True)
    
    def _create_base_ui_components(self) -> None:
        """创建基础UI组件（不依赖功能模块）"""
        # 创建提示标签
        self.hint_label = self.ui_builder.create_hint_label(self.storage_dir)
        self.success_label = self.ui_builder.create_success_label()
        self.success_label_timer: Optional[int] = None
        
        # 创建列表头部
        (self.list_header_frame, self.list_label, 
         self.sort_asc_button, self.sort_desc_button,
         self.enable_edit_checkbox) = self.ui_builder.create_list_header(
            self.load_screenshots, self.sort_ascending, self.sort_descending,
            self._toggle_edit_mode
        )
        
        # 创建列表框架
        (self.list_frame, self.preview_frame, self.list_right_frame, 
         self.tree_frame, self.preview_label_text, 
         self.preview_label) = self.ui_builder.create_list_frame()
        
        # 创建Treeview（使用临时回调，稍后更新）
        (self.tree, self.scrollbar, 
         self.drag_indicator_line) = self.ui_builder.create_treeview(
            self.tree_frame, lambda: None  # 临时占位，稍后更新
        )
        
        # 创建操作按钮
        (self.button_frame, self.add_button, self.replace_button,
         self.delete_button, self.gallery_preview_button) = self.ui_builder.create_action_buttons(
            self.add_new, self.replace_selected, 
            self.delete_selected, self.show_gallery_preview
        )
        
        # 创建导出按钮
        (self.export_button, 
         self.batch_export_button) = self.ui_builder.create_export_buttons(
            self.preview_frame, self.export_image, self.batch_export_images
        )
    
    def _complete_ui_components(self) -> None:
        """完成UI组件创建（需要功能模块的部分）"""
        # 更新Treeview的全选回调
        self.tree.heading("select", text="☐", anchor="center", 
                         command=self.checkbox_manager.toggle_select_all)
    
    def _bind_events(self) -> None:
        """绑定事件处理器"""
        self.tree.bind('<<TreeviewSelect>>', self._on_tree_select)
        self.tree.bind('<Button-1>', self._on_button1_click)
        self.tree.bind('<B1-Motion>', self._on_drag_motion)
        self.tree.bind('<ButtonRelease-1>', self._on_drag_end)
        
        # 为修改按钮绑定点击事件（用于检测禁用状态下的点击）
        self._bind_disabled_button_events()
    
    def _on_tree_select(self, event) -> None:
        """处理Treeview选择事件"""
        selected = self.tree.selection()
        if not selected:
            self.preview_handler._clear_preview()
            self.export_button.pack_forget()
            return
        
        item_id = selected[0]
        item_tags = self.tree.item(item_id, "tags")
        
        # 忽略页眉选择
        if item_tags and ("PageHeaderLeft" in item_tags or "PageHeaderRight" in item_tags):
            self.tree.selection_remove(item_id)
            return
        
        # 显示预览
        id_str = self.checkbox_manager.get_id_str(item_id)
        if id_str:
            self.preview_handler.show_preview(id_str)
            self.export_button.pack(pady=5)
    
    def _on_button1_click(self, event) -> Optional[str]:
        """处理Button-1点击事件"""
        return self.drag_handler.handle_button1_click(event)
    
    def _on_drag_motion(self, event) -> None:
        """处理拖拽移动事件"""
        self.drag_handler.handle_drag_motion(event)
    
    def _on_drag_end(self, event) -> None:
        """处理拖拽结束事件"""
        self.drag_handler.handle_drag_end(event)
    
    def set_storage_dir(self, storage_dir: Optional[str]) -> None:
        """设置存储目录
        
        Args:
            storage_dir: 存储目录路径
        """
        self.storage_dir = storage_dir
        if self.storage_dir:
            self.screenshot_manager.set_storage_dir(self.storage_dir)
            self.gallery_preview.storage_dir = storage_dir
            self.dialogs.storage_dir = storage_dir
            self.preview_handler.storage_dir = storage_dir
            self.hint_label.pack_forget()
        else:
            self.hint_label.pack(pady=10)
    
    def update_ui_texts(self) -> None:
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
        if self.enable_edit_checkbox:
            self.enable_edit_checkbox.config(text=self.t("enable_edit"))
    
    def load_screenshots(self, silent: bool = False) -> None:
        """加载截图列表并更新UI显示
        
        Args:
            silent: 是否静默模式，静默模式下不显示错误消息，默认为False
        """
        if not self.storage_dir:
            return
        
        self.screenshot_manager.set_storage_dir(self.storage_dir)
        
        if not self.screenshot_manager.load_screenshots():
            if not silent:
                messagebox.showerror(self.t("error"), self.t("missing_files"))
            return
        
        self.hint_label.pack_forget()
        self.status_indicator.clear_all_indicators()
        self.list_renderer.render_list()
        self.update_batch_export_button()
    
    def sort_ascending(self) -> None:
        """按时间正序排序截图列表"""
        if not self.edit_mode_manager.is_enabled:
            return
        
        if not self.storage_dir:
            showerror_relative(self.root, self.t("error"), self.t("select_dir_hint"))
            return
        
        result = askyesno_relative(
            self.root,
            self.t("confirm_sort"),
            self.t("sort_warning"),
            icon='warning'
        )
        
        if not result:
            return
        
        self.screenshot_manager.sort_by_date(ascending=True)
        self.load_screenshots()
        showinfo_relative(self.root, self.t("success"), self.t("sort_asc_success"))
    
    def sort_descending(self) -> None:
        """按时间倒序排序截图列表"""
        if not self.edit_mode_manager.is_enabled:
            return
        
        if not self.storage_dir:
            showerror_relative(self.root, self.t("error"), self.t("select_dir_hint"))
            return
        
        result = askyesno_relative(
            self.root,
            self.t("confirm_sort"),
            self.t("sort_warning"),
            icon='warning'
        )
        
        if not result:
            return
        
        self.screenshot_manager.sort_by_date(ascending=False)
        self.load_screenshots()
        showinfo_relative(self.root, self.t("success"), self.t("sort_desc_success"))
    
    def get_selected_ids(self) -> list:
        """获取所有选中的ID列表
        
        Returns:
            选中的截图ID列表
        """
        return self.checkbox_manager.get_selected_ids()
    
    def get_selected_count(self) -> int:
        """获取选中的数量
        
        Returns:
            选中的截图数量
        """
        return self.checkbox_manager.get_selected_count()
    
    def update_batch_export_button(self) -> None:
        """更新批量导出按钮显示"""
        if not self.storage_dir:
            self.batch_export_button.pack_forget()
            return
        
        selected_count = self.get_selected_count()
        if selected_count > 0:
            self.batch_export_button.pack(pady=5)
        else:
            self.batch_export_button.pack_forget()
    
    def show_status_indicator(self, id_str: str, is_new: bool = True) -> None:
        """在指定ID的截图名称前显示状态指示器
        
        Args:
            id_str: 截图ID字符串
            is_new: 是否为新截图，True显示新截图标记，False显示替换标记
        """
        self.status_indicator.show_status_indicator(id_str, is_new)
    
    def show_gallery_preview(self) -> None:
        """显示画廊预览窗口"""
        self.gallery_preview.show_gallery_preview()
    
    def add_new(self) -> None:
        """添加新截图"""
        if not self.edit_mode_manager.is_enabled:
            return
        self.dialogs.show_add_dialog()
    
    def replace_selected(self) -> None:
        """替换选中的截图"""
        if not self.edit_mode_manager.is_enabled:
            return
        
        selected = self.tree.selection()
        if not selected:
            showwarning_relative(self.root, self.t("warning"), self.t("select_screenshot"))
            return
        
        item_id = selected[0]
        id_str = self.checkbox_manager.get_id_str(item_id)
        if not id_str:
            messagebox.showerror(self.t("error"), self.t("invalid_selection"))
            return
        
        self.dialogs.show_replace_dialog(id_str, self.checkbox_manager.checkbox_vars, self.tree)
    
    def delete_selected(self) -> None:
        """删除选中的截图"""
        if not self.edit_mode_manager.is_enabled:
            return
        
        selected_ids = self.get_selected_ids()
        
        if not selected_ids:
            showwarning_relative(self.root, self.t("warning"), self.t("delete_select_error"))
            return
        
        # 构建确认消息
        if len(selected_ids) == 1:
            confirm_msg = self.t("delete_confirm_single").format(id=selected_ids[0])
        else:
            ids_str = ", ".join(selected_ids)
            confirm_msg = self.t("delete_confirm_multiple").format(
                count=len(selected_ids), ids=ids_str
            )
        
        result = askyesno_relative(self.root, self.t("delete_confirm"), confirm_msg)
        
        if not result:
            return
        
        deleted_count = self.screenshot_manager.delete_screenshots(selected_ids)
        
        if deleted_count > 0:
            showinfo_relative(
                self.root, 
                self.t("success"), 
                self.t("delete_success").format(count=deleted_count)
            )
            self.load_screenshots()
        else:
            showwarning_relative(self.root, self.t("warning"), self.t("delete_warning"))
    
    def export_image(self) -> None:
        """导出当前选中的图片"""
        selected = self.tree.selection()
        if not selected:
            showwarning_relative(self.root, self.t("warning"), self.t("select_screenshot"))
            return
        
        item_id = selected[0]
        id_str = self.checkbox_manager.get_id_str(item_id)
        if not id_str:
            messagebox.showerror(self.t("error"), self.t("invalid_selection"))
            return
        
        self.dialogs.show_export_dialog(id_str)
    
    def batch_export_images(self) -> None:
        """批量导出图片到ZIP文件"""
        selected_ids = self.get_selected_ids()
        
        if not selected_ids:
            showwarning_relative(self.root, self.t("warning"), self.t("select_screenshot"))
            return
        
        self.dialogs.show_batch_export_dialog(selected_ids)
    
    def _toggle_edit_mode(self) -> None:
        """切换编辑模式"""
        if self.enable_edit_checkbox and hasattr(self.enable_edit_checkbox, 'var'):
            new_state = self.enable_edit_checkbox.var.get()
            if new_state:
                self.edit_mode_manager.enable()
            else:
                self.edit_mode_manager.disable()
    
    def _on_edit_mode_changed(self, is_enabled: bool) -> None:
        """编辑模式状态改变时的回调
        
        Args:
            is_enabled: 是否启用编辑模式
        """
        self._update_edit_mode_ui()
    
    def _bind_disabled_button_events(self) -> None:
        """为修改按钮绑定点击事件，用于检测禁用状态下的点击"""
        edit_buttons = (
            self.add_button,
            self.replace_button,
            self.delete_button,
            self.sort_asc_button,
            self.sort_desc_button
        )
        
        for button in edit_buttons:
            button.bind('<Button-1>', self._on_edit_button_click, add='+')
    
    def _on_edit_button_click(self, event: tk.Event) -> Optional[str]:
        """处理修改按钮的点击事件
        
        Args:
            event: 鼠标点击事件
            
        Returns:
            如果按钮被禁用则返回"break"阻止事件传播，否则返回None
        """
        button = event.widget
        
        if button.instate(['disabled']):
            self._trigger_edit_mode_hint_animation()
            return "break"
        
        return None
    
    def _trigger_edit_mode_hint_animation(self) -> None:
        """触发"开启修改"复选框的提示动画（变色+抖动）"""
        if not self._can_trigger_animation():
            return
        
        wrapper = self.enable_edit_checkbox.wrapper
        self._apply_hint_style()
        original_padx = self._get_original_padx()
        
        self._start_shake_animation(wrapper, original_padx)
    
    def _can_trigger_animation(self) -> bool:
        """检查是否可以触发动画
        
        Returns:
            如果可以触发动画返回True，否则返回False
        """
        return (self.enable_edit_checkbox is not None and 
                hasattr(self.enable_edit_checkbox, 'wrapper'))
    
    def _apply_hint_style(self) -> None:
        """应用提示样式（红橙色）"""
        checkbox_style = ttk.Style(self.root)
        checkbox_style.configure(
            CHECKBOX_STYLE_HINT,
            background=self.Colors.LIGHT_GRAY,
            foreground=HINT_COLOR_ORANGE
        )
        self.enable_edit_checkbox.config(style=CHECKBOX_STYLE_HINT)
    
    def _get_original_padx(self) -> int:
        """获取原始padx值
        
        Returns:
            原始padx值（整数）
        """
        DEFAULT_PADX = 5
        pack_info = getattr(self.enable_edit_checkbox, '_original_pack_info', {})
        raw_padx = pack_info.get('padx', DEFAULT_PADX)
        
        if isinstance(raw_padx, (list, tuple)):
            return int(raw_padx[0]) if raw_padx else DEFAULT_PADX
        return int(raw_padx) if raw_padx else DEFAULT_PADX
    
    def _start_shake_animation(self, wrapper: tk.Frame, original_padx: int) -> None:
        """开始抖动动画
        
        Args:
            wrapper: 复选框包装Frame
            original_padx: 原始padx值
        """
        def shake_step(step_index: int) -> None:
            """执行抖动步骤"""
            if step_index >= len(SHAKE_OFFSETS):
                self._restore_normal_state(wrapper, original_padx)
                return
            
            offset = SHAKE_OFFSETS[step_index]
            new_padx = max(0, original_padx + offset)
            wrapper.pack_configure(padx=new_padx)
            
            self.root.after(
                SHAKE_STEP_DELAY_MS,
                lambda: shake_step(step_index + 1)
            )
        
        shake_step(0)
    
    def _restore_normal_state(self, wrapper: tk.Frame, original_padx: int) -> None:
        """恢复正常状态
        
        Args:
            wrapper: 复选框包装Frame
            original_padx: 原始padx值
        """
        wrapper.pack_configure(padx=original_padx)
        self.root.after(
            SHAKE_COLOR_RESTORE_DELAY_MS,
            lambda: self.enable_edit_checkbox.config(style=CHECKBOX_STYLE_NORMAL)
        )
    
    def _update_edit_mode_ui(self) -> None:
        """更新编辑模式相关的UI状态"""
        is_enabled = self.edit_mode_manager.is_enabled
        
        self._update_checkbox_state(is_enabled)
        self._update_edit_buttons_state(is_enabled)
    
    def _update_checkbox_state(self, is_enabled: bool) -> None:
        """更新复选框状态
        
        Args:
            is_enabled: 是否启用编辑模式
        """
        if self.enable_edit_checkbox and hasattr(self.enable_edit_checkbox, 'var'):
            self.enable_edit_checkbox.var.set(is_enabled)
    
    def _update_edit_buttons_state(self, is_enabled: bool) -> None:
        """更新修改操作按钮的状态
        
        Args:
            is_enabled: 是否启用编辑模式
        """
        button_state = "normal" if is_enabled else "disabled"
        edit_buttons = (
            self.add_button,
            self.replace_button,
            self.delete_button,
            self.sort_asc_button,
            self.sort_desc_button
        )
        
        for button in edit_buttons:
            button.config(state=button_state)
    
