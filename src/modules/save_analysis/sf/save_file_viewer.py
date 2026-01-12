"""文件查看器模块

提供存档文件的查看和编辑功能，包括JSON语法高亮、折叠显示、搜索等。

本模块已重构，使用子模块分离职责：
- file_viewer.config: 配置常量
- file_viewer.models: 数据模型
- file_viewer.viewer_registry: 查看器注册表
- file_viewer.json_formatter: JSON格式化
- file_viewer.file_saver: 文件保存服务
- file_viewer.runtime_injector_service: 运行时注入服务
- file_viewer.search_handler: 搜索功能
"""

import asyncio
import json
import logging
import threading
import urllib.parse
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional, Tuple

import tkinter as tk
from tkinter import Scrollbar, messagebox, ttk

from src.utils.styles import Colors, get_cjk_font, get_mono_font
from src.utils.ui_utils import (
    askyesno_relative,
    set_window_icon,
    showerror_relative,
    showinfo_relative,
    showwarning_relative,
)
from src.utils.hint_animation import HintAnimation
from src.modules.screenshot.animation_constants import CHECKBOX_STYLE_NORMAL, CHECKBOX_STYLE_HINT

from .file_viewer.json_highlighter import apply_json_syntax_highlight
from .file_viewer.config import (
    DEFAULT_SF_COLLAPSED_FIELDS,
    SAVE_FILE_NAME,
    CLOSE_CALLBACK_DELAY_MS,
    REFRESH_AFTER_INJECT_DELAY_MS,
    SINGLE_LINE_LIST_FIELDS,
    DEFAULT_WINDOW_SIZE,
    HINT_WRAPLENGTH,
    CHECKBOX_PADX,
    USER_EDIT_HIGHLIGHT_COLOR,
)
from .file_viewer.models import ViewerConfig
from .file_viewer.viewer_registry import (
    register_viewer,
    unregister_viewer,
    focus_existing_viewer,
    is_viewer_alive,
)
from .file_viewer.json_formatter import JSONFormatter
from .file_viewer.file_saver import FileSaver
from .file_viewer.runtime_injector_service import RuntimeInjectorService
from .file_viewer.search_handler import SearchHandler
from .file_viewer.ui_builder import UIBuilder
from .file_viewer.editor_controller import EditorController

logger = logging.getLogger(__name__)

__all__ = [
    "SaveFileViewer",
    "ViewerConfig",
    "DEFAULT_SF_COLLAPSED_FIELDS",
]


class SaveFileViewer:
    """存档文件查看器"""
    
    @classmethod
    def open_or_focus(
        cls,
        viewer_id: str,
        **kwargs
    ) -> 'SaveFileViewer':
        """工厂方法：打开新窗口或聚焦已存在的窗口
        
        Args:
            viewer_id: 唯一标识符，用于区分不同的编辑器实例
            **kwargs: 传递给 __init__ 的参数
            
        Returns:
            SaveFileViewer 实例（新创建或已存在的）
            
        Note:
            如果窗口已存在，只会聚焦该窗口，不会刷新数据。
            这是为了避免覆盖用户正在编辑但未保存的内容。
        """
        existing = focus_existing_viewer(viewer_id)
        if existing is not None:
            return existing
        
        # 使用 cls 创建实例以支持子类继承
        viewer = cls(**kwargs, _viewer_id=viewer_id)
        register_viewer(viewer_id, viewer)
        return viewer
    
    def __init__(
        self,
        window: tk.Widget,
        storage_dir: str,
        save_data: Dict[str, Any],
        t_func: Callable[[str], str],
        on_close_callback: Optional[Callable] = None,
        mode: Literal["file", "runtime"] = "file",
        viewer_config: Optional[ViewerConfig] = None,
        _viewer_id: Optional[str] = None
    ) -> None:
        """初始化文件查看器
        
        Args:
            window: 主窗口对象
            storage_dir: 存档目录
            save_data: 存档数据
            t_func: 翻译函数
            on_close_callback: 窗口关闭时的回调函数
            mode: 模式，"file"为文件模式，"runtime"为运行时模式
            viewer_config: 查看器配置（通用配置，适用于两种模式）
            _viewer_id: 内部使用，用于注册表管理
        """
        self._viewer_id = _viewer_id
        self.window = window
        self.storage_dir = storage_dir
        self.save_data = save_data
        self.t = t_func
        self.on_close_callback = on_close_callback
        self.mode = mode
        self.viewer_config = viewer_config or ViewerConfig()
        self.original_save_data = JSONFormatter._deep_copy_data(save_data)
        self._data_was_saved = False  # 标志位：是否保存过数据
        
        # 初始化服务模块
        self.json_formatter = JSONFormatter(
            self.viewer_config.collapsed_fields or [],
            t_func
        )
        self.file_saver = FileSaver(
            storage_dir,
            self.viewer_config,
            t_func,
            None  # window 将在 _create_viewer_window 后设置
        )
        self.runtime_injector = RuntimeInjectorService(
            None,  # window 将在 _create_viewer_window 后设置
            self.viewer_config,
            t_func
        )
        
        root_window = self._find_root_window(window)
        self.viewer_window = self._create_viewer_window(root_window)
        
        # 更新服务模块的窗口引用
        self.file_saver.window = self.viewer_window
        self.runtime_injector.window = self.viewer_window
        
        self._bind_destroy_cleanup()
        
        self._setup_ui()
    
    def _bind_destroy_cleanup(self) -> None:
        """绑定窗口销毁事件，确保从注册表中移除"""
        def on_destroy(event):
            # <Destroy> 事件会在子控件销毁时也触发，需检查是否为窗口本身
            if event.widget is self.viewer_window:
                if self._viewer_id:
                    unregister_viewer(self._viewer_id)
        
        self.viewer_window.bind("<Destroy>", on_destroy)
    
    def _find_root_window(self, window: tk.Widget) -> tk.Tk:
        """查找根窗口"""
        root = window
        while not isinstance(root, tk.Tk) and hasattr(root, 'master'):
            root = root.master
        return root
    
    def _create_viewer_window(self, root_window: tk.Tk) -> tk.Toplevel:
        """创建查看器窗口"""
        window = tk.Toplevel(root_window)
        title_key = self.viewer_config.title_key
        window.title(self.t(title_key))
        window.geometry(DEFAULT_WINDOW_SIZE)
        window.configure(bg=Colors.MODAL_BG)
        set_window_icon(window)
        return window
    
    def _deep_copy_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """深拷贝数据"""
        return JSONFormatter._deep_copy_data(data)
    
    def _setup_ui(self) -> None:
        """设置UI界面"""
        # 初始化UI构建器
        self.ui_builder = UIBuilder(self.viewer_window, self.t)
        self.ui_builder.setup_modal_styles()
        
        main_frame = self.ui_builder.create_main_frame()
        
        if self.viewer_config.show_hint_label:
            self.ui_builder.create_hint_label(main_frame)
        
        toolbar = self.ui_builder.create_toolbar(main_frame)
        
        # 创建文本组件
        initial_content = self.json_formatter.format_display_data(self.save_data)
        text_widget, line_numbers = self.ui_builder.create_text_widgets(
            main_frame,
            initial_content,
            self.viewer_config.enable_edit_by_default
        )
        self.line_numbers = line_numbers
        self.text_widget = text_widget
        
        # 应用语法高亮
        apply_json_syntax_highlight(text_widget, initial_content)
        self._update_line_numbers(text_widget, line_numbers)
        
        # 设置工具栏控件
        self._setup_toolbar_controls(toolbar, text_widget, line_numbers)
    
    def _format_display_data(self) -> str:
        """格式化显示数据"""
        return self.json_formatter.format_display_data(self.save_data)
    
    
    def _update_line_numbers(self, text_widget: tk.Text, line_numbers: tk.Text) -> None:
        """更新行号显示"""
        if hasattr(self, 'ui_builder'):
            self.ui_builder.update_line_numbers(text_widget, line_numbers)
        else:
            line_numbers.config(state="normal")
            line_numbers.delete("1.0", "end")
            content = text_widget.get("1.0", "end-1c")
            line_count = content.count('\n') + 1 if content else 1
            line_numbers.insert("end", "\n".join(str(i) for i in range(1, line_count + 1)) + "\n")
            line_numbers.config(state="disabled")
            line_numbers.yview_moveto(text_widget.yview()[0])
    
    def _setup_toolbar_controls(
        self,
        toolbar: tk.Frame,
        text_widget: tk.Text,
        line_numbers: tk.Text
    ) -> None:
        """设置工具栏控件"""
        disable_collapse_var = tk.BooleanVar(value=False)
        default_edit = self.viewer_config.enable_edit_by_default
        enable_edit_var = tk.BooleanVar(value=default_edit)
        self._enable_edit_var = enable_edit_var
        self.save_button: Optional[ttk.Button] = None
        
        original_content = text_widget.get("1.0", "end-1c")
        collapsed_text_ranges: List[Tuple[str, str]] = []
        
        def update_collapsed_ranges():
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
        
        def is_in_collapsed_range(pos: str) -> bool:
            if disable_collapse_var.get():
                return False
            return any(
                text_widget.compare(start, "<=", pos) and text_widget.compare(pos, "<", end)
                for start, end in collapsed_text_ranges
            )
        
        hint_animation: Optional[HintAnimation] = None
        
        def on_text_edit(event=None):
            if not enable_edit_var.get():
                if event:
                    key = event.keysym
                    is_ctrl_c = (event.state & 0x4 and key.lower() == "c")
                    if is_ctrl_c:
                        return None
                    if hint_animation:
                        has_selection = bool(text_widget.tag_ranges("sel"))
                        if has_selection and key in ("Delete", "BackSpace"):
                            hint_animation.trigger()
                return "break"
            
            cursor_pos = text_widget.index("insert")
            if is_in_collapsed_range(cursor_pos):
                showwarning_relative(
                    self.viewer_window,
                    self.t("cannot_edit_collapsed"),
                    self.t("cannot_edit_collapsed_detail")
                )
                return "break"
            return None
        
        def on_text_change(event=None):
            if not enable_edit_var.get():
                return
            cursor_pos = text_widget.index("insert")
            if is_in_collapsed_range(cursor_pos):
                showwarning_relative(
                    self.viewer_window,
                    self.t("cannot_edit_collapsed"),
                    self.t("cannot_edit_collapsed_detail")
                )
                if text_widget.tk.call(text_widget._w, 'edit', 'canundo'):
                    text_widget.edit_undo()
        
        text_widget.bind("<KeyPress>", on_text_edit)
        text_widget.bind("<Button-1>", lambda e: update_collapsed_ranges())
        text_widget.bind("<<Modified>>", on_text_change)
        
        def detect_and_highlight_changes():
            if not enable_edit_var.get():
                return
            text_widget.tag_remove("user_edit", "1.0", "end")
            current_content = text_widget.get("1.0", "end-1c")
            if current_content != original_content:
                original_lines = original_content.split('\n')
                current_lines = current_content.split('\n')
                max_lines = max(len(original_lines), len(current_lines))
                for i in range(max_lines):
                    original_line = original_lines[i] if i < len(original_lines) else ""
                    current_line = current_lines[i] if i < len(current_lines) else ""
                    if original_line != current_line:
                        line_start = f"{i+1}.0"
                        line_end = f"{i+1}.end"
                        if (text_widget.compare(line_start, "<=", "end") and
                            text_widget.compare(line_end, "<=", "end")):
                            text_widget.tag_add("user_edit", line_start, line_end)
        
        self._detect_and_highlight_changes = detect_and_highlight_changes
        
        def update_display(check_changes: bool = False) -> None:
            nonlocal original_content
            
            if check_changes and _has_unsaved_changes():
                if not _confirm_discard_changes():
                    disable_collapse_var.set(not disable_collapse_var.get())
                    return
            
            scroll_position = text_widget.yview()[0]
            text_widget.config(state="normal")
            
            # 清除搜索高亮
            if hasattr(self, 'search_handler'):
                self.search_handler.clear_search()
            
            if disable_collapse_var.get():
                full_json = json.dumps(self.save_data, ensure_ascii=False, indent=2)
                text_widget.delete("1.0", "end")
                text_widget.insert("1.0", full_json)
                apply_json_syntax_highlight(text_widget, full_json)
                original_content = full_json
                collapsed_text_ranges.clear()
            else:
                formatted_json = self.json_formatter.format_display_data(self.save_data)
                text_widget.delete("1.0", "end")
                text_widget.insert("1.0", formatted_json)
                apply_json_syntax_highlight(text_widget, formatted_json)
                original_content = formatted_json
                update_collapsed_ranges()
            
            self._update_line_numbers(text_widget, self.line_numbers)
            
            if enable_edit_var.get():
                text_widget.config(state="normal")
                if self.save_button:
                    self.save_button.config(state="normal")
                detect_and_highlight_changes()
            else:
                text_widget.config(state="disabled")
                if self.save_button:
                    self.save_button.config(state="disabled")
                text_widget.tag_remove("user_edit", "1.0", "end")
            
            def restore_scroll():
                text_widget.yview_moveto(scroll_position)
            self.viewer_window.after_idle(restore_scroll)
        
        def toggle_collapse():
            update_display(check_changes=True)
        
        if self.viewer_config.show_collapse_checkbox:
            disable_collapse_checkbox = ttk.Checkbutton(
                toolbar,
                text=self.t("disable_collapse_horizontal"),
                variable=disable_collapse_var,
                command=toggle_collapse,
                style="Modal.TCheckbutton"
            )
            disable_collapse_checkbox.pack(side="left", padx=5)
        
        # 创建搜索组件
        search_frame = tk.Frame(toolbar, bg=Colors.MODAL_BG)
        search_frame.pack(side="left", padx=5)
        
        search_entry = ttk.Entry(search_frame, width=20)
        search_entry.pack(side="left", padx=2)
        
        self.search_results_label = ttk.Label(search_frame, text="", style="Modal.TLabel")
        self.search_results_label.pack(side="left", padx=2)
        
        # 初始化搜索处理器
        self.search_handler = SearchHandler(
            text_widget,
            search_entry,
            self.search_results_label,
            self.t
        )
        
        def copy_to_clipboard():
            self.viewer_window.clipboard_clear()
            # 复制文本编辑器中当前显示的内容
            current_display_content = text_widget.get("1.0", "end-1c")
            self.viewer_window.clipboard_append(current_display_content)
        
        copy_button = ttk.Button(toolbar, text=self.t("copy_to_clipboard"), command=copy_to_clipboard)
        copy_button.pack(side="left", padx=5)
        
        toolbar_right = tk.Frame(toolbar, bg=Colors.MODAL_BG)
        toolbar_right.pack(side="right", padx=5)
        
        def _get_current_text_content() -> str:
            try:
                return text_widget.get("1.0", "end-1c")
            except tk.TclError:
                return ""
        
        def _has_unsaved_changes() -> bool:
            if not enable_edit_var.get():
                return False
            return _get_current_text_content() != original_content
        
        def _confirm_discard_changes() -> bool:
            return askyesno_relative(
                self.viewer_window,
                self.t("refresh_confirm_title"),
                self.t("unsaved_changes_warning")
            )
        
        def check_unsaved_changes(force_check: bool = False) -> bool:
            should_check = force_check or enable_edit_var.get()
            if not should_check:
                return True
            if not _has_unsaved_changes():
                return True
            return _confirm_discard_changes()
        
        def refresh_save_file() -> None:
            if not check_unsaved_changes():
                return
            
            if self.mode == "runtime":
                self._refresh_from_runtime(text_widget, update_display)
            else:
                reloaded_data = self.file_saver.load_save_file()
                if reloaded_data is None:
                    return
                self.save_data = reloaded_data
                self.original_save_data = JSONFormatter._deep_copy_data(reloaded_data)
                update_display()
        
        refresh_button = ttk.Button(toolbar_right, text=self.t("refresh"), command=refresh_save_file)
        refresh_button.pack(side="right", padx=5)
        
        def toggle_edit_mode() -> None:
            nonlocal original_content
            is_enabling_edit = not enable_edit_var.get()
            
            if is_enabling_edit:
                if not check_unsaved_changes(force_check=True):
                    enable_edit_var.set(True)
                    return
            
            if self.mode == "runtime":
                if enable_edit_var.get():
                    update_display()
                    original_content = _get_current_text_content()
                else:
                    text_widget.config(state="disabled")
                    if self.save_button:
                        self.save_button.config(state="disabled")
                    text_widget.tag_remove("user_edit", "1.0", "end")
            else:
                reloaded_data = self.file_saver.load_save_file()
                if reloaded_data is None:
                    enable_edit_var.set(False)
                    return
                
                self.save_data = reloaded_data
                if enable_edit_var.get():
                    update_display()
                    original_content = _get_current_text_content()
                else:
                    text_widget.config(state="disabled")
                    if self.save_button:
                        self.save_button.config(state="disabled")
                    text_widget.tag_remove("user_edit", "1.0", "end")
        
        hint_animation = None
        enable_edit_checkbox = None
        if self.viewer_config.show_enable_edit_checkbox:
            checkbox_wrapper = tk.Frame(toolbar_right, bg=Colors.MODAL_BG)
            checkbox_wrapper.pack(side="right", padx=CHECKBOX_PADX)
            
            checkbox_style = ttk.Style(self.viewer_window)
            checkbox_style.configure(CHECKBOX_STYLE_NORMAL, background=Colors.MODAL_BG)
            checkbox_style.configure(
                CHECKBOX_STYLE_HINT,
                background=Colors.MODAL_BG,
                foreground="#FF6B35"
            )
            
            enable_edit_checkbox = ttk.Checkbutton(
                checkbox_wrapper,
                text=self.t("enable_edit"),
                variable=enable_edit_var,
                command=toggle_edit_mode,
                style=CHECKBOX_STYLE_NORMAL
            )
            enable_edit_checkbox.pack()
            enable_edit_checkbox.wrapper = checkbox_wrapper
            toolbar_right.update_idletasks()
            enable_edit_checkbox._original_pack_info = checkbox_wrapper.pack_info()
            
            hint_animation = HintAnimation(
                self.viewer_window,
                enable_edit_checkbox,
                CHECKBOX_STYLE_NORMAL,
                CHECKBOX_STYLE_HINT
            )
        
        if self.viewer_config.enable_edit_by_default:
            text_widget.config(state="normal")
            if self.save_button:
                self.save_button.config(state="normal")
        
        def _restore_collapsed_fields(edited_data: Dict[str, Any]) -> None:
            """恢复被折叠的字段值"""
            self.json_formatter.restore_collapsed_fields(
                edited_data,
                self.save_data,
                disable_collapse_var.get()
            )
        
        def save_save_file() -> None:
            nonlocal original_content
            
            text_widget.config(state="normal")
            content = _get_current_text_content()
            
            try:
                edited_data = json.loads(content)
            except json.JSONDecodeError as json_error:
                text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
                showerror_relative(
                    self.viewer_window,
                    self.t("json_format_error"),
                    self.t("json_format_error_detail").format(error=str(json_error))
                )
                return
            
            _restore_collapsed_fields(edited_data)
            
            if self.mode == "runtime":
                self._save_to_runtime(edited_data, content, enable_edit_var, text_widget, update_display, _get_current_text_content)
            else:
                self._save_to_file(edited_data, content, enable_edit_var, text_widget, update_display, _get_current_text_content)
            
            def update_original_content_ref():
                nonlocal original_content
                if hasattr(self, '_original_content_wrapper') and self._original_content_wrapper:
                    original_content = self._original_content_wrapper[0]
            
            if self.mode == "runtime":
                self.viewer_window.after(100, update_original_content_ref)
        
        save_button_text_key = self.viewer_config.save_button_text
        initial_button_state = ("normal" if self.viewer_config.enable_edit_by_default else "disabled")
        self.save_button = ttk.Button(
            toolbar_right,
            text=self.t(save_button_text_key),
            command=save_save_file,
            state=initial_button_state
        )
        self.save_button.pack(side="right", padx=5)
        
        def find_next():
            if hasattr(self, 'search_handler'):
                self.search_handler.find_next()
        
        def find_prev():
            if hasattr(self, 'search_handler'):
                self.search_handler.find_prev()
        
        find_next_button = ttk.Button(search_frame, text="↓", command=find_next, width=3)
        find_next_button.pack(side="left", padx=2)
        
        find_prev_button = ttk.Button(search_frame, text="↑", command=find_prev, width=3)
        find_prev_button.pack(side="left", padx=2)
        
        def on_ctrl_f(event):
            search_entry.focus()
            search_entry.select_range(0, "end")
            return "break"
        
        self.viewer_window.bind("<Control-f>", on_ctrl_f)
        self.viewer_window.bind("<Control-F>", on_ctrl_f)
        
        def on_search_enter(event):
            if event.state & 0x1:
                find_prev()
            else:
                find_next()
            return "break"
        
        search_entry.bind("<Return>", on_search_enter)
        
        def on_window_close() -> None:
            if _has_unsaved_changes():
                if not _confirm_discard_changes():
                    return
            
            self.viewer_window.destroy()
            if self._viewer_id:
                unregister_viewer(self._viewer_id)
            
            if self.on_close_callback and self._data_was_saved:
                root = self._find_root_window(self.window)
                if root and root.winfo_exists():
                    root.after(CLOSE_CALLBACK_DELAY_MS, self.on_close_callback)
        
        self.viewer_window.protocol("WM_DELETE_WINDOW", on_window_close)
    
    def _restore_nested_collapsed_field(
        self,
        edited_data: Dict[str, Any],
        field_path: str,
        collapsed_text: str
    ) -> None:
        """恢复嵌套的折叠字段值"""
        self.json_formatter._restore_nested_collapsed_field(
            edited_data,
            self.save_data,
            field_path,
            collapsed_text
        )
    
    def _load_save_file(self) -> Optional[Dict[str, Any]]:
        """从文件系统加载存档文件"""
        return self.file_saver.load_save_file()
    
    def _refresh_from_file(self, text_widget: tk.Text, update_display: Callable) -> None:
        """从文件系统刷新数据"""
        reloaded_data = self.file_saver.load_save_file()
        if reloaded_data is None:
            return
        
        self.save_data = reloaded_data
        self.original_save_data = JSONFormatter._deep_copy_data(reloaded_data)
        update_display()
    
    def _refresh_from_runtime(self, text_widget: tk.Text, update_display: Callable) -> None:
        """从运行时内存刷新数据"""
        def on_complete(data: Optional[Dict[str, Any]], error: Optional[str]) -> None:
            if error:
                showerror_relative(
                    self.viewer_window,
                    self.t("error"),
                    error
                )
                return
            
            if data is None:
                showerror_relative(
                    self.viewer_window,
                    self.t("error"),
                    self.t("runtime_modify_sf_error_empty_data")
                )
                return
            
            self.save_data = data
            self.original_save_data = JSONFormatter._deep_copy_data(data)
            update_display()
        
        self.runtime_injector.refresh_from_runtime(on_complete)
    
    def _save_to_file(
        self,
        edited_data: Dict[str, Any],
        content: str,
        enable_edit_var: tk.BooleanVar,
        text_widget: tk.Text,
        update_display: Callable,
        get_current_text_content: Callable[[], str]
    ) -> None:
        """保存到文件"""
        user_confirmed = messagebox.askyesno(
            self.t("save_confirm_title"),
            self.t("save_confirm_text"),
            parent=self.viewer_window
        )
        
        if not user_confirmed:
            text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
            return
        
        # 优先使用自定义保存函数
        if self.viewer_config and self.viewer_config.custom_save_func:
            try:
                success = self.viewer_config.custom_save_func(edited_data)
                if success:
                    self.save_data = edited_data
                    self.original_save_data = self._deep_copy_data(edited_data)
                    self._data_was_saved = True
                    showinfo_relative(
                        self.viewer_window,
                        self.t("success"),
                        self.t("save_success")
                    )
                    update_display()
                    # 调用保存回调
                    if self.viewer_config.on_save_callback:
                        try:
                            self.viewer_config.on_save_callback(edited_data)
                        except Exception as callback_error:
                            logger.error(f"on_save_callback failed: {callback_error}", exc_info=True)
                else:
                    showerror_relative(
                        self.viewer_window,
                        self.t("error"),
                        self.t("save_file_failed").format(error="保存失败")
                    )
            except Exception as save_error:
                logger.error(f"Custom save function failed: {save_error}", exc_info=True)
                showerror_relative(
                    self.viewer_window,
                    self.t("error"),
                    self.t("save_file_failed").format(error=str(save_error))
                )
            finally:
                text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
            return
        
        # 默认保存逻辑：保存到 DevilConnection_sf.sav
        save_file_path = Path(self.storage_dir) / SAVE_FILE_NAME
        json_str = json.dumps(edited_data, ensure_ascii=False)
        encoded_content = urllib.parse.quote(json_str)
        
        try:
            with open(save_file_path, 'w', encoding='utf-8') as file_handle:
                file_handle.write(encoded_content)
        except (OSError, IOError, PermissionError) as file_error:
            showerror_relative(
                self.viewer_window,
                self.t("error"),
                self.t("save_file_failed").format(error=str(file_error))
            )
            text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
            return
        
        self.save_data = edited_data
        self.original_save_data = self._deep_copy_data(edited_data)
        self._data_was_saved = True
        showinfo_relative(
            self.viewer_window,
            self.t("success"),
            self.t("save_success")
        )
        update_display()
        text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
        
        # 调用保存回调
        if self.viewer_config and self.viewer_config.on_save_callback:
            try:
                self.viewer_config.on_save_callback(edited_data)
            except Exception as callback_error:
                logger.error(f"on_save_callback failed: {callback_error}", exc_info=True)
    
    def _save_to_runtime(
        self,
        edited_data: Dict[str, Any],
        content: str,
        enable_edit_var: tk.BooleanVar,
        text_widget: tk.Text,
        update_display: Callable,
        get_current_text_content: Callable[[], str]
    ) -> None:
        """保存到运行时内存（使用 RuntimeInjectorService）"""
        original_content_wrapper = [content]
        self._original_content_wrapper = original_content_wrapper
        
        def on_success(saved_data: Dict[str, Any]) -> None:
            """保存成功回调"""
            self.save_data = saved_data
            self.original_save_data = JSONFormatter._deep_copy_data(saved_data)
            self._data_was_saved = True
            original_content_wrapper[0] = get_current_text_content()
            
            # 如果是运行时模式，刷新数据
            if self.mode == "runtime" and self.runtime_injector.is_available():
                def on_refresh_complete(refreshed_data: Optional[Dict[str, Any]], error: Optional[str]) -> None:
                    if error:
                        logger.warning(f"Failed to refresh after inject: {error}")
                        return
                    if refreshed_data:
                        self.save_data = refreshed_data
                        self.original_save_data = JSONFormatter._deep_copy_data(refreshed_data)
                        original_content_wrapper[0] = get_current_text_content()
                    update_display()
                    text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
                
                self.runtime_injector.refresh_after_inject(on_refresh_complete)
            else:
                update_display()
                text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
        
        def on_error(error_msg: str) -> None:
            """保存失败回调"""
            text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
        
        self.runtime_injector.save_to_runtime(
            edited_data,
            self.original_save_data,
            on_success,
            on_error,
            require_confirmation=True
        )
    
    def _get_collapsed_fields_list(self) -> List[str]:
        """获取要折叠的字段列表"""
        return self.viewer_config.collapsed_fields if self.viewer_config else []
    
    def _collect_collapsed_fields(self) -> Dict[str, Any]:
        """收集需要折叠的字段"""
        return {}
    
    def _resolve_nested_field(self, field_path: str) -> Optional[Any]:
        """解析嵌套字段路径并返回字段值"""
        return self.json_formatter._resolve_nested_field(self.save_data, field_path)
    
    def _check_changes_and_inject_async(
        self,
        edited_data: Dict[str, Any],
        content: str,
        enable_edit_var: tk.BooleanVar,
        text_widget: tk.Text,
        update_display: Callable[[], None],
        get_current_text_content: Callable[[], str],
        original_content_ref: list
    ) -> None:
        """异步检查变更并执行注入"""
        def check_and_inject_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                has_changes, changes_info = loop.run_until_complete(
                    self.viewer_config.service.check_sf_changes(
                        self.viewer_config.ws_url,
                        self.original_save_data
                    )
                )
                changes_text = changes_info.get("changes_text", "") if has_changes else ""
                self.viewer_window.after(0, lambda: self._handle_changes_and_inject(
                    has_changes,
                    changes_text,
                    edited_data,
                    content,
                    enable_edit_var,
                    text_widget,
                    update_display,
                    get_current_text_content,
                    original_content_ref
                ))
            finally:
                loop.close()
        
        thread = threading.Thread(target=check_and_inject_in_thread, daemon=True)
        thread.start()
    
    def _handle_changes_and_inject(
        self,
        has_changes: bool,
        changes_text: str,
        edited_data: Dict[str, Any],
        content: str,
        enable_edit_var: tk.BooleanVar,
        text_widget: tk.Text,
        update_display: Callable[[], None],
        get_current_text_content: Callable[[], str],
        original_content_ref: list
    ) -> None:
        """在主线程中处理变更提示并执行注入"""
        if has_changes:
            user_continue = messagebox.askyesno(
                self.t("warning"),
                self.t("runtime_modify_sf_changes_detected").format(changes=changes_text),
                parent=self.viewer_window
            )
            if not user_continue:
                text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
                return
        
        def inject_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                success, error = loop.run_until_complete(
                    self.viewer_config.service.inject_and_save_sf(
                        self.viewer_config.ws_url,
                        edited_data
                    )
                )
                self.viewer_window.after(0, lambda: self._on_inject_complete(
                    success,
                    error,
                    edited_data,
                    content,
                    enable_edit_var,
                    text_widget,
                    update_display,
                    get_current_text_content,
                    original_content_ref
                ))
            finally:
                loop.close()
        
        thread = threading.Thread(target=inject_in_thread, daemon=True)
        thread.start()
    
    def _on_inject_complete(
        self,
        success: bool,
        error: Optional[str],
        edited_data: Dict[str, Any],
        content: str,
        enable_edit_var: tk.BooleanVar,
        text_widget: tk.Text,
        update_display: Callable[[], None],
        get_current_text_content: Callable[[], str],
        original_content_ref: list
    ) -> None:
        """注入完成回调"""
        if not success:
            error_msg = error or self.t("runtime_modify_sf_error_unknown")
            showerror_relative(
                self.viewer_window,
                self.t("error"),
                self.t("runtime_modify_sf_inject_failed").format(error=error_msg)
            )
            text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
            return
        
        self._data_was_saved = True
        showinfo_relative(
            self.viewer_window,
            self.t("success"),
            self.t("runtime_modify_sf_inject_success")
        )
        
        # 调用保存回调
        if self.viewer_config and self.viewer_config.on_save_callback:
            try:
                self.viewer_config.on_save_callback(edited_data)
            except Exception as callback_error:
                logger.error(f"on_save_callback failed: {callback_error}", exc_info=True)
        
        if self.mode == "runtime" and self.viewer_config.service and self.viewer_config.ws_url:
            self._refresh_after_inject(
                enable_edit_var,
                text_widget,
                update_display,
                get_current_text_content,
                original_content_ref
            )
        else:
            self.save_data = edited_data
            self.original_save_data = self._deep_copy_data(edited_data)
            original_content_ref[0] = content
            update_display()
            text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
    
    def _refresh_after_inject(
        self,
        enable_edit_var: tk.BooleanVar,
        text_widget: tk.Text,
        update_display: Callable[[], None],
        get_current_text_content: Callable[[], str],
        original_content_ref: list
    ) -> None:
        """注入后刷新数据"""
        def read_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                data, read_error = loop.run_until_complete(
                    self.viewer_config.service.read_tyrano_variable_sf(
                        self.viewer_config.ws_url
                    )
                )
                self.viewer_window.after(0, lambda: self._on_refresh_complete(
                    data,
                    read_error,
                    enable_edit_var,
                    text_widget,
                    update_display,
                    get_current_text_content,
                    original_content_ref
                ))
            finally:
                loop.close()
        
        def start_refresh():
            thread = threading.Thread(target=read_in_thread, daemon=True)
            thread.start()
        
        self.viewer_window.after(REFRESH_AFTER_INJECT_DELAY_MS, start_refresh)
    
    def _on_refresh_complete(
        self,
        data: Optional[Dict[str, Any]],
        read_error: Optional[str],
        enable_edit_var: tk.BooleanVar,
        text_widget: tk.Text,
        update_display: Callable[[], None],
        get_current_text_content: Callable[[], str],
        original_content_ref: list
    ) -> None:
        """刷新完成回调"""
        if read_error:
            logger.warning("Failed to refresh after inject: %s", read_error)
            return
        
        if data is None:
            return
        
        self.save_data = data
        self.original_save_data = self._deep_copy_data(data)
        original_content_ref[0] = get_current_text_content()
        update_display()
        text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
    
    def _run_async_in_thread(
        self,
        coro: Awaitable[Tuple[Any, Optional[str]]],
        on_complete: Callable[[Any, Optional[str]], None]
    ) -> None:
        """在后台线程中运行异步协程"""
        def run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result, error = loop.run_until_complete(coro)
                self.viewer_window.after(0, lambda: on_complete(result, error))
            except Exception as e:
                logger.exception("Unexpected error in async thread")
                self.viewer_window.after(0, lambda: on_complete(None, str(e)))
            finally:
                pending = asyncio.all_tasks(loop)
                if pending:
                    for task in pending:
                        task.cancel()
                    try:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    except Exception as gather_error:
                        logger.debug("Error gathering pending tasks: %s", gather_error)
                loop.close()
        
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
    
    def _inject_kag_stat_async(
        self,
        edited_data: Dict[str, Any],
        content: str,
        enable_edit_var: tk.BooleanVar,
        text_widget: tk.Text,
        update_display: Callable[[], None],
        get_current_text_content: Callable[[], str],
        original_content_ref: list
    ) -> None:
        """异步执行 kag.stat 注入（不检查变更）"""
        if not self.viewer_config.service or not self.viewer_config.ws_url:
            logger.error("Cannot inject kag.stat: service or ws_url is missing")
            return
        
        inject_coro = self.viewer_config.service.inject_kag_stat(
            self.viewer_config.ws_url,
            edited_data
        )
        
        def on_complete(success: bool, error: Optional[str]) -> None:
            self._on_kag_stat_inject_complete(
                success,
                error,
                edited_data,
                content,
                enable_edit_var,
                text_widget,
                update_display,
                get_current_text_content,
                original_content_ref
            )
        
        self._run_async_in_thread(inject_coro, on_complete)
    
    def _on_kag_stat_inject_complete(
        self,
        success: bool,
        error: Optional[str],
        edited_data: Dict[str, Any],
        content: str,
        enable_edit_var: tk.BooleanVar,
        text_widget: tk.Text,
        update_display: Callable[[], None],
        get_current_text_content: Callable[[], str],
        original_content_ref: list
    ) -> None:
        """kag.stat 注入完成回调"""
        if not success:
            error_message = error or "Unknown error"
            logger.error("kag.stat injection failed: %s", error_message)
            showerror_relative(
                self.viewer_window,
                self.t("error"),
                self.t("runtime_modify_kag_stat_inject_failed").format(error=error_message)
            )
            text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
            return
        
        logger.info("kag.stat injection successful")
        self._data_was_saved = True
        showinfo_relative(
            self.viewer_window,
            self.t("success"),
            self.t("runtime_modify_kag_stat_inject_success")
        )
        
        # 调用保存回调
        if self.viewer_config and self.viewer_config.on_save_callback:
            try:
                self.viewer_config.on_save_callback(edited_data)
            except Exception as callback_error:
                logger.error(f"on_save_callback failed: {callback_error}", exc_info=True)
        
        is_runtime_mode = (
            self.mode == "runtime"
            and self.viewer_config
            and self.viewer_config.service
            and self.viewer_config.ws_url
        )
        
        if is_runtime_mode:
            self._refresh_kag_stat_after_inject(
                enable_edit_var,
                text_widget,
                update_display,
                get_current_text_content,
                original_content_ref
            )
        else:
            self.save_data = edited_data
            self.original_save_data = self._deep_copy_data(edited_data)
            original_content_ref[0] = content
            update_display()
            text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
    
    def _refresh_kag_stat_after_inject(
        self,
        enable_edit_var: tk.BooleanVar,
        text_widget: tk.Text,
        update_display: Callable[[], None],
        get_current_text_content: Callable[[], str],
        original_content_ref: list
    ) -> None:
        """注入后刷新 kag.stat 数据"""
        if not self.viewer_config.service or not self.viewer_config.ws_url:
            logger.warning("Cannot refresh kag.stat: service or ws_url is missing")
            return
        
        read_coro = self.viewer_config.service.read_tyrano_kag_stat(
            self.viewer_config.ws_url
        )
        
        def on_complete(kag_stat_data: Optional[Dict[str, Any]], read_error: Optional[str]) -> None:
            self._on_kag_stat_refresh_complete(
                kag_stat_data,
                read_error,
                enable_edit_var,
                text_widget,
                update_display,
                get_current_text_content,
                original_content_ref
            )
        
        def start_refresh():
            self._run_async_in_thread(read_coro, on_complete)
        
        self.viewer_window.after(REFRESH_AFTER_INJECT_DELAY_MS, start_refresh)
    
    def _on_kag_stat_refresh_complete(
        self,
        kag_stat_data: Optional[Dict[str, Any]],
        read_error: Optional[str],
        enable_edit_var: tk.BooleanVar,
        text_widget: tk.Text,
        update_display: Callable[[], None],
        get_current_text_content: Callable[[], str],
        original_content_ref: list
    ) -> None:
        """kag.stat 刷新完成回调"""
        if read_error:
            logger.warning("Failed to refresh kag.stat after inject: %s", read_error)
            return
        
        if kag_stat_data is None:
            logger.warning("kag.stat refresh returned None data")
            return
        
        self.save_data = kag_stat_data
        self.original_save_data = self._deep_copy_data(kag_stat_data)
        original_content_ref[0] = get_current_text_content()
        update_display()
        text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
