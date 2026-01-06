"""文件查看器模块

提供存档文件的查看和编辑功能，包括JSON语法高亮、折叠显示、搜索等。
"""

import asyncio
import json
import logging
import threading
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional, Tuple

import tkinter as tk
from tkinter import Scrollbar, messagebox, ttk

from src.utils.styles import Colors, get_cjk_font, get_mono_font
from src.utils.ui_utils import (
    askyesno_relative,
    restore_and_activate_window,
    set_window_icon,
    showerror_relative,
    showinfo_relative,
    showwarning_relative,
)
from src.utils.hint_animation import HintAnimation
from src.modules.screenshot.animation_constants import CHECKBOX_STYLE_NORMAL, CHECKBOX_STYLE_HINT

from .file_viewer.json_highlighter import apply_json_syntax_highlight

logger = logging.getLogger(__name__)

DEFAULT_SF_COLLAPSED_FIELDS = ["record", "_tap_effect", "initialVars"]
SAVE_FILE_NAME = "DevilConnection_sf.sav"
CLOSE_CALLBACK_DELAY_MS = 100
REFRESH_AFTER_INJECT_DELAY_MS = 200
SINGLE_LINE_LIST_FIELDS = frozenset([
    "endings", "collectedEndings", "omakes", "characters",
    "collectedCharacters", "sticker", "gallery", "ngScene"
])
DEFAULT_WINDOW_SIZE = "1200x900"
HINT_WRAPLENGTH = 850
CHECKBOX_PADX = 5

_current_save_file_viewer: Optional['SaveFileViewer'] = None


@dataclass
class ViewerConfig:
    """查看器配置类，适用于 file 和 runtime 模式"""
    ws_url: Optional[str] = None
    service: Optional[Any] = None
    inject_method: str = "sf"
    enable_edit_by_default: bool = False
    save_button_text: str = "save_file"
    show_enable_edit_checkbox: bool = False
    show_collapse_checkbox: bool = False
    show_hint_label: bool = False
    title_key: str = "save_file_viewer_title"
    collapsed_fields: List[str] = field(default_factory=list)


class SaveFileViewer:
    """存档文件查看器"""
    
    def __init__(
        self,
        window: tk.Widget,
        storage_dir: str,
        save_data: Dict[str, Any],
        t_func: Callable[[str], str],
        on_close_callback: Optional[Callable] = None,
        mode: Literal["file", "runtime"] = "file",
        viewer_config: Optional[ViewerConfig] = None
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
        """
        global _current_save_file_viewer
        
        if _current_save_file_viewer is not None:
            if self._try_restore_existing_viewer(_current_save_file_viewer):
                return
        
        self.window = window
        self.storage_dir = storage_dir
        self.save_data = save_data
        self.t = t_func
        self.on_close_callback = on_close_callback
        self.mode = mode
        self.viewer_config = viewer_config or ViewerConfig()
        self.original_save_data = self._deep_copy_data(save_data)
        
        root_window = self._find_root_window(window)
        self.viewer_window = self._create_viewer_window(root_window)
        _current_save_file_viewer = self
        
        self._setup_ui()
    
    def _try_restore_existing_viewer(self, existing_viewer: 'SaveFileViewer') -> bool:
        """尝试恢复已存在的查看器窗口
        
        Args:
            existing_viewer: 已存在的查看器实例
            
        Returns:
            是否成功恢复窗口
        """
        if not hasattr(existing_viewer, 'viewer_window'):
            _current_save_file_viewer = None
            return False
        
        if not existing_viewer.viewer_window.winfo_exists():
            _current_save_file_viewer = None
            return False
        
        if restore_and_activate_window(existing_viewer.viewer_window):
            return True
        
        _current_save_file_viewer = None
        return False
    
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
        return json.loads(json.dumps(data))
    
    def _setup_ui(self) -> None:
        """设置UI界面"""
        self._setup_modal_styles()
        main_frame = self._create_main_frame()
        
        if self.viewer_config.show_hint_label:
            self._create_hint_label(main_frame)
        
        toolbar = self._create_toolbar(main_frame)
        text_widget, line_numbers = self._create_text_widgets(main_frame)
        self.line_numbers = line_numbers  # 保存为实例变量，供其他方法使用
        
        self._setup_text_widget_handlers(text_widget, line_numbers)
        self._setup_toolbar_controls(toolbar, text_widget)
    
    def _setup_modal_styles(self) -> None:
        """设置模态窗口样式"""
        modal_style = ttk.Style(self.viewer_window)
        
        modal_style.configure(
            "Modal.TLabel",
            background=Colors.MODAL_BG,
            foreground="gray",
            borderwidth=0,
            relief="flat"
        )
        modal_style.map("Modal.TLabel",
                       background=[("active", Colors.MODAL_BG),
                                  ("!active", Colors.MODAL_BG)])
        
        modal_style.configure(
            "Modal.TCheckbutton",
            background=Colors.MODAL_BG,
            foreground=Colors.TEXT_PRIMARY,
            borderwidth=0,
            relief="flat"
        )
        modal_style.map("Modal.TCheckbutton",
                       background=[("active", Colors.MODAL_BG),
                                  ("!active", Colors.MODAL_BG),
                                  ("selected", Colors.MODAL_BG)])
    
    def _create_main_frame(self) -> tk.Frame:
        """创建主框架"""
        main_frame = tk.Frame(self.viewer_window, bg=Colors.MODAL_BG)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        return main_frame
    
    def _create_hint_label(self, parent: tk.Widget) -> None:
        """创建提示标签"""
        hint_frame = tk.Frame(parent, bg=Colors.MODAL_BG)
        hint_frame.pack(fill="x", pady=(0, 10))
        hint_label = ttk.Label(
            hint_frame,
            text=self.t("viewer_hint_text"),
            font=get_cjk_font(9),
            wraplength=HINT_WRAPLENGTH,
            justify="left",
            style="Modal.TLabel"
        )
        hint_label.pack(anchor="w", padx=5)
    
    def _create_toolbar(self, parent: tk.Widget) -> tk.Frame:
        """创建工具栏"""
        toolbar = tk.Frame(parent, bg=Colors.MODAL_BG)
        toolbar.pack(fill="x", pady=(0, 5))
        return toolbar
    
    def _create_text_widgets(self, parent: tk.Widget) -> Tuple[tk.Text, tk.Text]:
        """创建文本显示组件"""
        self.search_matches: List[Tuple[str, str]] = []
        self.current_search_pos = [0]
        self.search_results_label: Optional[ttk.Label] = None
        
        text_frame = tk.Frame(parent)
        text_frame.pack(fill="both", expand=True)
        
        mono_font = get_mono_font(10)
        
        line_numbers = tk.Text(
            text_frame,
            font=mono_font,
            bg=Colors.CODE_GUTTER_BG,
            fg=Colors.TEXT_MUTED,
            width=4,
            padx=5,
            pady=2,
            state="disabled",
            wrap="none",
            highlightthickness=0,
            borderwidth=0
        )
        line_numbers.pack(side="left", fill="y")
        
        text_container = tk.Frame(text_frame)
        text_container.pack(side="left", fill="both", expand=True)
        
        v_scrollbar = Scrollbar(text_container, orient="vertical")
        v_scrollbar.pack(side="right", fill="y")
        
        h_scrollbar = Scrollbar(text_container, orient="horizontal")
        h_scrollbar.pack(side="bottom", fill="x")
        
        text_widget = tk.Text(
            text_container,
            font=mono_font,
            bg=Colors.CODE_BG,
            fg=Colors.TEXT_DARK,
            yscrollcommand=lambda *args: (v_scrollbar.set(*args), self._update_line_numbers(text_widget, line_numbers)),
            xscrollcommand=h_scrollbar.set,
            wrap="none",
            tabs=("2c", "4c", "6c", "8c", "10c", "12c", "14c", "16c")
        )
        text_widget.pack(side="left", fill="both", expand=True)
        v_scrollbar.config(command=lambda *args: (text_widget.yview(*args), self._update_line_numbers(text_widget, line_numbers)))
        h_scrollbar.config(command=text_widget.xview)
        
        initial_content = self._format_display_data()
        text_widget.insert("1.0", initial_content)
        apply_json_syntax_highlight(text_widget, initial_content)
        self._update_line_numbers(text_widget, line_numbers)
        
        if self.viewer_config.enable_edit_by_default:
            text_widget.config(state="normal")
        else:
            text_widget.config(state="disabled")
        
        return text_widget, line_numbers
    
    def _format_display_data(self) -> str:
        """格式化显示数据"""
        collapsed_fields = self._collect_collapsed_fields()
        display_data = self._deep_copy_data(self.save_data)
        collapsed_text = self.t("collapsed_field_text")
        
        for field_key in collapsed_fields.keys():
            if "." in field_key:
                self._replace_nested_field(display_data, field_key, collapsed_text)
            else:
                if isinstance(display_data, dict) and field_key in display_data:
                    display_data[field_key] = collapsed_text
        
        return self._format_json_custom(display_data)
    
    def _replace_nested_field(self, data: Dict[str, Any], field_key: str, replacement: str) -> None:
        """替换嵌套字段"""
        key_parts = field_key.split(".")
        nested_obj = data
        for part in key_parts[:-1]:
            if not isinstance(nested_obj, dict) or part not in nested_obj:
                return
            nested_obj = nested_obj[part]
        if isinstance(nested_obj, dict) and key_parts[-1] in nested_obj:
            nested_obj[key_parts[-1]] = replacement
    
    def _format_json_custom(self, obj: Any, indent: int = 0) -> str:
        """自定义JSON格式化，列表字段在一行内显示"""
        indent_str = "  " * indent
        
        if isinstance(obj, dict):
            items = []
            for key, value in obj.items():
                if key in SINGLE_LINE_LIST_FIELDS and isinstance(value, list):
                    value_str = json.dumps(value, ensure_ascii=False)
                elif isinstance(value, (dict, list)):
                    value_str = self._format_json_custom(value, indent + 1)
                else:
                    value_str = json.dumps(value, ensure_ascii=False)
                items.append(f'"{key}": {value_str}')
            
            item_separator = ",\n" + indent_str + "  "
            return f"{{\n{indent_str}  {item_separator.join(items)}\n{indent_str}}}"
        elif isinstance(obj, list):
            formatted_items = [
                self._format_json_custom(item, indent + 1) if isinstance(item, (dict, list))
                else json.dumps(item, ensure_ascii=False)
                for item in obj
            ]
            item_separator = ",\n" + indent_str + "  "
            return f"[\n{indent_str}  {item_separator.join(formatted_items)}\n{indent_str}]"
        else:
            return json.dumps(obj, ensure_ascii=False)
    
    def _update_line_numbers(self, text_widget: tk.Text, line_numbers: tk.Text) -> None:
        """更新行号显示"""
        line_numbers.config(state="normal")
        line_numbers.delete("1.0", "end")
        
        content = text_widget.get("1.0", "end-1c")
        line_count = content.count('\n') + 1 if content else 1
        
        line_numbers.insert("end", "\n".join(str(i) for i in range(1, line_count + 1)) + "\n")
        line_numbers.config(state="disabled")
        line_numbers.yview_moveto(text_widget.yview()[0])
    
    def _setup_text_widget_handlers(self, text_widget: tk.Text, line_numbers: tk.Text) -> None:
        """设置文本组件事件处理"""
        text_widget.tag_config("user_edit", background="#fff9c4")
        text_widget.config(undo=True)
        
        def on_text_change(*args):
            self._update_line_numbers(text_widget, line_numbers)
            if hasattr(self, '_enable_edit_var') and self._enable_edit_var.get():
                if hasattr(self, '_detect_and_highlight_changes'):
                    self._detect_and_highlight_changes()
        
        text_widget.bind("<<Modified>>", on_text_change)
        text_widget.bind("<KeyRelease>", lambda e: self._update_line_numbers(text_widget, line_numbers))
        text_widget.bind("<Button-1>", lambda e: self._update_line_numbers(text_widget, line_numbers))
    
    def _setup_toolbar_controls(
        self,
        toolbar: tk.Frame,
        text_widget: tk.Text
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
            
            text_widget.tag_delete("search_highlight")
            self.search_matches.clear()
            self.current_search_pos[0] = 0
            if self.search_results_label:
                self.search_results_label.config(text="")
            
            if disable_collapse_var.get():
                full_json = json.dumps(self.save_data, ensure_ascii=False, indent=2)
                text_widget.delete("1.0", "end")
                text_widget.insert("1.0", full_json)
                apply_json_syntax_highlight(text_widget, full_json)
                original_content = full_json
                collapsed_text_ranges.clear()
            else:
                formatted_json = self._format_display_data()
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
        
        search_frame = tk.Frame(toolbar, bg=Colors.MODAL_BG)
        search_frame.pack(side="left", padx=5)
        
        search_entry = ttk.Entry(search_frame, width=20)
        search_entry.pack(side="left", padx=2)
        
        self.search_results_label = ttk.Label(search_frame, text="", style="Modal.TLabel")
        self.search_results_label.pack(side="left", padx=2)
        
        def copy_to_clipboard():
            self.viewer_window.clipboard_clear()
            full_json = json.dumps(self.save_data, ensure_ascii=False, indent=2)
            self.viewer_window.clipboard_append(full_json)
        
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
                self._refresh_from_file(text_widget, update_display)
        
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
                reloaded_data = self._load_save_file()
                if reloaded_data is None:
                    enable_edit_var.set(False)
                    showerror_relative(
                        self.viewer_window,
                        self.t("error"),
                        self.t("save_file_not_found")
                    )
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
            if disable_collapse_var.get() or not isinstance(self.save_data, dict):
                return
            
            collapsed_text = self.t("collapsed_field_text")
            fields_to_check = self._get_collapsed_fields_list()
            
            for field_path in fields_to_check:
                if "." in field_path:
                    self._restore_nested_collapsed_field(edited_data, field_path, collapsed_text)
                else:
                    if (field_path in edited_data and
                        isinstance(edited_data[field_path], str) and
                        edited_data[field_path] == collapsed_text and
                        field_path in self.save_data):
                        edited_data[field_path] = self.save_data[field_path]
        
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
        
        def find_text(direction: str = "next") -> None:
            search_term = search_entry.get()
            if not search_term:
                if self.search_results_label:
                    self.search_results_label.config(text="")
                return
            
            was_disabled = text_widget.cget("state") == "disabled"
            if was_disabled:
                text_widget.config(state="normal")
            
            content = text_widget.get("1.0", "end-1c")
            text_widget.tag_delete("search_highlight")
            text_widget.tag_config("search_highlight", background="yellow")
            
            self.search_matches.clear()
            start_pos = "1.0"
            while True:
                pos = text_widget.search(search_term, start_pos, "end", nocase=True)
                if not pos:
                    break
                end_pos = f"{pos}+{len(search_term)}c"
                self.search_matches.append((pos, end_pos))
                text_widget.tag_add("search_highlight", pos, end_pos)
                start_pos = end_pos
            
            if self.search_matches:
                if direction == "next":
                    self.current_search_pos[0] = (self.current_search_pos[0] + 1) % len(self.search_matches)
                else:
                    self.current_search_pos[0] = (self.current_search_pos[0] - 1) % len(self.search_matches)
                
                pos, end_pos = self.search_matches[self.current_search_pos[0]]
                text_widget.see(pos)
                text_widget.mark_set("insert", pos)
                text_widget.see(pos)
                
                if self.search_results_label:
                    self.search_results_label.config(text=f"{self.current_search_pos[0] + 1}/{len(self.search_matches)}")
            else:
                if self.search_results_label:
                    self.search_results_label.config(text=self.t("search_not_found"))
            
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
            global _current_save_file_viewer
            
            if _has_unsaved_changes():
                if not _confirm_discard_changes():
                    return
            
            self.viewer_window.destroy()
            if _current_save_file_viewer is self:
                _current_save_file_viewer = None
            
            if self.on_close_callback:
                self.viewer_window.after(CLOSE_CALLBACK_DELAY_MS, self.on_close_callback)
        
        self.viewer_window.protocol("WM_DELETE_WINDOW", on_window_close)
    
    def _restore_nested_collapsed_field(
        self,
        edited_data: Dict[str, Any],
        field_path: str,
        collapsed_text: str
    ) -> None:
        """恢复嵌套的折叠字段值
        
        Args:
            edited_data: 编辑后的数据
            field_path: 字段路径，如 "stat.map_label"
            collapsed_text: 折叠文本占位符
        """
        path_parts = field_path.split(".")
        if len(path_parts) < 2:
            return
        
        original_value = self._resolve_nested_field(field_path)
        if original_value is None:
            return
        
        current_edited = edited_data
        for part in path_parts[:-1]:
            if not isinstance(current_edited, dict) or part not in current_edited:
                return
            current_edited = current_edited[part]
        
        if not isinstance(current_edited, dict):
            return
        
        last_part = path_parts[-1]
        if (last_part in current_edited and
            isinstance(current_edited[last_part], str) and
            current_edited[last_part] == collapsed_text):
            current_edited[last_part] = original_value
    
    def _load_save_file(self) -> Optional[Dict[str, Any]]:
        """从文件系统加载存档文件"""
        from .save_data_service import load_save_file
        return load_save_file(self.storage_dir)
    
    def _refresh_from_file(self, text_widget: tk.Text, update_display: Callable) -> None:
        """从文件系统刷新数据"""
        reloaded_data = self._load_save_file()
        if reloaded_data is None:
            showerror_relative(
                self.viewer_window,
                self.t("error"),
                self.t("save_file_not_found")
            )
            return
        
        self.save_data = reloaded_data
        self.original_save_data = self._deep_copy_data(reloaded_data)
        update_display()
    
    def _refresh_from_runtime(self, text_widget: tk.Text, update_display: Callable) -> None:
        """从运行时内存刷新数据"""
        if not self.viewer_config.service or not self.viewer_config.ws_url:
            showerror_relative(
                self.viewer_window,
                self.t("error"),
                self.t("runtime_modify_sf_game_not_running")
            )
            return
        
        if self.viewer_config.inject_method == "kag_stat":
            read_method = self.viewer_config.service.read_tyrano_kag_stat
            read_error_key = "runtime_modify_kag_stat_read_failed"
        else:
            read_method = self.viewer_config.service.read_tyrano_variable_sf
            read_error_key = "runtime_modify_sf_read_failed"
        
        def read_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                data, error = loop.run_until_complete(read_method(self.viewer_config.ws_url))
                self.viewer_window.after(0, lambda: self._on_runtime_read_complete(
                    data, error, read_error_key, update_display
                ))
            finally:
                loop.close()
        
        thread = threading.Thread(target=read_in_thread, daemon=True)
        thread.start()
    
    def _on_runtime_read_complete(
        self,
        data: Optional[Dict[str, Any]],
        error: Optional[str],
        error_key: str,
        update_display: Callable
    ) -> None:
        """运行时读取完成回调"""
        if error:
            showerror_relative(
                self.viewer_window,
                self.t("error"),
                self.t(error_key).format(error=error)
            )
            return
        
        if data is None:
            if error_key == "runtime_modify_kag_stat_read_failed":
                error_msg = self.t("runtime_modify_kag_stat_read_failed").format(error="Empty data")
            else:
                error_msg = self.t("runtime_modify_sf_error_empty_data")
            showerror_relative(
                self.viewer_window,
                self.t("error"),
                self.t(error_key).format(error=error_msg)
            )
            return
        
        self.save_data = data
        self.original_save_data = self._deep_copy_data(data)
        update_display()
    
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
        showinfo_relative(
            self.viewer_window,
            self.t("success"),
            self.t("save_success")
        )
        update_display()
        text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
    
    def _save_to_runtime(
        self,
        edited_data: Dict[str, Any],
        content: str,
        enable_edit_var: tk.BooleanVar,
        text_widget: tk.Text,
        update_display: Callable,
        get_current_text_content: Callable[[], str]
    ) -> None:
        """保存到运行时内存"""
        if not self.viewer_config.service or not self.viewer_config.ws_url:
            showerror_relative(
                self.viewer_window,
                self.t("error"),
                self.t("runtime_modify_sf_game_not_running")
            )
            text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
            return
        
        if self.viewer_config.inject_method == "kag_stat":
            confirm_key = "runtime_modify_kag_stat_confirm_inject"
        else:
            confirm_key = "runtime_modify_sf_confirm_inject"
        
        user_confirmed = messagebox.askyesno(
            self.t("save_confirm_title"),
            self.t(confirm_key),
            parent=self.viewer_window
        )
        
        if not user_confirmed:
            text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
            return
        
        original_content_wrapper = [content]
        self._original_content_wrapper = original_content_wrapper
        
        if self.viewer_config.inject_method == "kag_stat":
            self._inject_kag_stat_async(
                edited_data,
                content,
                enable_edit_var,
                text_widget,
                update_display,
                get_current_text_content,
                original_content_wrapper
            )
        else:
            self._check_changes_and_inject_async(
                edited_data,
                content,
                enable_edit_var,
                text_widget,
                update_display,
                get_current_text_content,
                original_content_wrapper
            )
    
    def _get_collapsed_fields_list(self) -> List[str]:
        """获取要折叠的字段列表"""
        if self.viewer_config and self.viewer_config.collapsed_fields:
            return self.viewer_config.collapsed_fields
        return []
    
    def _collect_collapsed_fields(self) -> Dict[str, Any]:
        """收集需要折叠的字段
        
        Returns:
            字段路径到字段值的映射字典
        """
        if not isinstance(self.save_data, dict):
            return {}
        
        collapsed_fields: Dict[str, Any] = {}
        fields_to_collapse = set(self._get_collapsed_fields_list())
        
        for field_path in fields_to_collapse:
            if "." in field_path:
                field_value = self._resolve_nested_field(field_path)
                if field_value is not None:
                    collapsed_fields[field_path] = field_value
            elif field_path in self.save_data:
                collapsed_fields[field_path] = self.save_data[field_path]
        
        return collapsed_fields
    
    def _resolve_nested_field(self, field_path: str) -> Optional[Any]:
        """解析嵌套字段路径并返回字段值
        
        Args:
            field_path: 字段路径，如 "stat.map_label"
            
        Returns:
            字段值，如果路径不存在则返回 None
        """
        path_parts = field_path.split(".")
        if len(path_parts) < 2:
            return None
        
        current_obj = self.save_data
        for part in path_parts[:-1]:
            if not isinstance(current_obj, dict) or part not in current_obj:
                return None
            current_obj = current_obj[part]
        
        if isinstance(current_obj, dict) and path_parts[-1] in current_obj:
            return current_obj[path_parts[-1]]
        
        return None
    
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
        
        showinfo_relative(
            self.viewer_window,
            self.t("success"),
            self.t("runtime_modify_sf_inject_success")
        )
        
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
        showinfo_relative(
            self.viewer_window,
            self.t("success"),
            self.t("runtime_modify_kag_stat_inject_success")
        )
        
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
