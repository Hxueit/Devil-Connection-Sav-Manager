"""文件查看器模块

提供存档文件的查看和编辑功能，包括JSON语法高亮、折叠显示、搜索等。
"""

import tkinter as tk
from tkinter import ttk, Scrollbar, messagebox
import json
import urllib.parse
import os
import re
from typing import Dict, Any, Optional, Callable

from src.utils.styles import Colors, get_cjk_font, get_mono_font
from src.utils.ui_utils import set_window_icon, showinfo_relative, showwarning_relative, showerror_relative, askyesno_relative
from src.utils.hint_animation import HintAnimation
from src.modules.screenshot.animation_constants import CHECKBOX_STYLE_NORMAL, CHECKBOX_STYLE_HINT


# 常量定义
COLLAPSED_FIELDS = ["record", "_tap_effect", "initialVars"]
SAVE_FILE_NAME = "DevilConnection_sf.sav"
CLOSE_CALLBACK_DELAY_MS = 100


def apply_json_syntax_highlight(text_widget: tk.Text, content: str) -> None:
    """应用JSON语法高亮
    
    Args:
        text_widget: 文本widget
        content: 要高亮的JSON内容
    """
    patterns = [
        (r'"[^"]*"', 'string'),
        (r'\b(true|false|null)\b', 'keyword'),
        (r'\b\d+\.?\d*\b', 'number'),
        (r'[{}[\]]', 'bracket'),
        (r'[:,]', 'punctuation'),
    ]
    
    for tag in ['string', 'keyword', 'number', 'bracket', 'punctuation']:
        text_widget.tag_remove(tag, "1.0", "end")
    
    mono_font = get_mono_font(10)
    
    text_widget.tag_config('string', foreground='#008000', font=mono_font)
    text_widget.tag_config('keyword', foreground='#0000FF', font=mono_font)
    text_widget.tag_config('number', foreground='#FF0000', font=mono_font)
    text_widget.tag_config('bracket', foreground='#000000', font=(mono_font[0], mono_font[1], "bold"))
    text_widget.tag_config('punctuation', foreground=Colors.TEXT_MUTED, font=mono_font)
    
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


class SaveFileViewer:
    """存档文件查看器"""
    
    def __init__(self, window: tk.Widget, storage_dir: str, save_data: Dict[str, Any],
                 t_func: Callable[[str], str], on_close_callback: Optional[Callable] = None):
        """初始化文件查看器
        
        Args:
            window: 主窗口对象
            storage_dir: 存档目录
            save_data: 存档数据
            t_func: 翻译函数
            on_close_callback: 窗口关闭时的回调函数
        """
        self.window = window
        self.storage_dir = storage_dir
        self.save_data = save_data
        self.t = t_func
        self.on_close_callback = on_close_callback
        
        root_window = window
        while not isinstance(root_window, tk.Tk) and hasattr(root_window, 'master'):
            root_window = root_window.master
        
        self.viewer_window = tk.Toplevel(root_window)
        self.viewer_window.title(self.t("save_file_viewer_title"))
        self.viewer_window.geometry("1200x900")
        set_window_icon(self.viewer_window)
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """设置UI界面"""
        main_frame = tk.Frame(self.viewer_window)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        hint_frame = tk.Frame(main_frame, bg=Colors.WHITE)
        hint_frame.pack(fill="x", pady=(0, 10))
        hint_label = ttk.Label(hint_frame, text=self.t("viewer_hint_text"), 
                               font=get_cjk_font(9), 
                               foreground="gray",
                               wraplength=850,
                               justify="left")
        hint_label.pack(anchor="w", padx=5)
        
        toolbar = tk.Frame(main_frame)
        toolbar.pack(fill="x", pady=(0, 5))
        
        self.search_matches = []
        self.current_search_pos = [0]
        self.search_results_label = None
        
        disable_collapse_var = tk.BooleanVar(value=False)
        enable_edit_var = tk.BooleanVar(value=False)
        self.save_button = None
        
        def format_json_custom(obj, indent=0):
            """自定义JSON格式化，列表字段在一行内显示"""
            list_fields = ["endings", "collectedEndings", "omakes", "characters", "collectedCharacters", "sticker", "gallery", "ngScene"]
            indent_str = "  " * indent
            
            if isinstance(obj, dict):
                items = []
                for key, value in obj.items():
                    if key in list_fields and isinstance(value, list):
                        value_str = json.dumps(value, ensure_ascii=False)
                        items.append(f'"{key}": {value_str}')
                    elif isinstance(value, (dict, list)):
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
                items = [format_json_custom(item, indent + 1) if isinstance(item, (dict, list)) else json.dumps(item, ensure_ascii=False) for item in obj]
                return "[\n" + indent_str + "  " + (",\n" + indent_str + "  ").join(items) + "\n" + indent_str + "]"
            else:
                return json.dumps(obj, ensure_ascii=False)
        
        collapsed_fields = {}
        for field in COLLAPSED_FIELDS:
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
        
        text_frame = tk.Frame(main_frame)
        text_frame.pack(fill="both", expand=True)
        
        mono_font = get_mono_font(10)
        
        line_numbers = tk.Text(text_frame, 
                              font=mono_font,
                              bg=Colors.CODE_GUTTER_BG,
                              fg=Colors.TEXT_MUTED,
                              width=4,
                              padx=5,
                              pady=2,
                              state="disabled",
                              wrap="none",
                              highlightthickness=0,
                              borderwidth=0)
        line_numbers.pack(side="left", fill="y")
        
        text_container = tk.Frame(text_frame)
        text_container.pack(side="left", fill="both", expand=True)
        
        v_scrollbar = Scrollbar(text_container, orient="vertical")
        v_scrollbar.pack(side="right", fill="y")
        
        h_scrollbar = Scrollbar(text_container, orient="horizontal")
        h_scrollbar.pack(side="bottom", fill="x")
        
        text_widget = tk.Text(text_container, 
                             font=mono_font,
                             bg=Colors.CODE_BG,
                             fg=Colors.TEXT_DARK,
                             yscrollcommand=lambda *args: (v_scrollbar.set(*args), update_line_numbers()),
                             xscrollcommand=h_scrollbar.set,
                             wrap="none",
                             tabs=("2c", "4c", "6c", "8c", "10c", "12c", "14c", "16c"))
        text_widget.pack(side="left", fill="both", expand=True)
        v_scrollbar.config(command=lambda *args: (text_widget.yview(*args), update_line_numbers()))
        h_scrollbar.config(command=text_widget.xview)
        
        original_content = formatted_json
        
        def update_line_numbers():
            """更新行号显示"""
            line_numbers.config(state="normal")
            line_numbers.delete("1.0", "end")
            
            content = text_widget.get("1.0", "end-1c")
            if content:
                line_count = content.count('\n') + 1
            else:
                line_count = 1
            
            for i in range(1, line_count + 1):
                line_numbers.insert("end", f"{i}\n")
            
            line_numbers.config(state="disabled")
            line_numbers.yview_moveto(text_widget.yview()[0])
        
        def on_text_change(*args):
            update_line_numbers()
            if enable_edit_var.get():
                detect_and_highlight_changes()
        
        text_widget.bind("<<Modified>>", on_text_change)
        text_widget.bind("<KeyRelease>", lambda e: update_line_numbers())
        text_widget.bind("<Button-1>", lambda e: update_line_numbers())
        
        text_widget.tag_config("user_edit", background="#fff9c4")
        
        def detect_and_highlight_changes():
            """检测并高亮用户修改"""
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
                        if text_widget.compare(line_start, "<=", "end") and text_widget.compare(line_end, "<=", "end"):
                            text_widget.tag_add("user_edit", line_start, line_end)
        
        text_widget.insert("1.0", formatted_json)
        original_content = formatted_json
        
        apply_json_syntax_highlight(text_widget, formatted_json)
        update_line_numbers()
        
        text_widget.config(state="disabled")
        
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
                return False
            for start, end in collapsed_text_ranges:
                if text_widget.compare(start, "<=", pos) and text_widget.compare(pos, "<", end):
                    return True
            return False
        
        # 先定义 hint_animation 变量（稍后初始化）
        hint_animation: Optional[HintAnimation] = None
        
        def on_text_edit(event=None):
            """文本编辑事件处理"""
            if not enable_edit_var.get():
                # 允许 Ctrl+C 复制功能，即使编辑模式未开启
                if event:
                    key = event.keysym
                    is_ctrl_c = (event.state & 0x4 and key.lower() == "c")  # Ctrl+C
                    if is_ctrl_c:
                        return None  # 允许复制操作
                    
                    # 检查是否有文本被选中且按下了编辑相关按键（不包括 Ctrl+C）
                    if hint_animation:
                        has_selection = bool(text_widget.tag_ranges("sel"))
                        if has_selection:
                            is_edit_key = key in ("Delete", "BackSpace")
                            if is_edit_key:
                                hint_animation.trigger()
                return "break"
            
            cursor_pos = text_widget.index("insert")
            if is_in_collapsed_range(cursor_pos):
                showwarning_relative(self.viewer_window,
                    self.t("cannot_edit_collapsed"),
                    self.t("cannot_edit_collapsed_detail")
                )
                return "break"
            
            return None
        
        def on_text_change(event=None):
            """文本改变事件处理"""
            if not enable_edit_var.get():
                return
            
            cursor_pos = text_widget.index("insert")
            if is_in_collapsed_range(cursor_pos):
                showwarning_relative(self.viewer_window,
                    self.t("cannot_edit_collapsed"),
                    self.t("cannot_edit_collapsed_detail")
                )
                if text_widget.tk.call(text_widget._w, 'edit', 'canundo'):
                    text_widget.edit_undo()
        
        text_widget.bind("<KeyPress>", on_text_edit)
        text_widget.bind("<Button-1>", lambda e: update_collapsed_ranges())
        text_widget.bind("<<Modified>>", on_text_change)
        
        text_widget.config(undo=True)
        
        def update_display(check_changes: bool = False) -> None:
            """更新显示内容
            
            Args:
                check_changes: 是否在更新前检查未保存的修改
            """
            nonlocal original_content
            
            if check_changes and _has_unsaved_changes():
                user_confirmed = _confirm_discard_changes()
                if not user_confirmed:
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
                collapsed_fields = {}
                
                for field in COLLAPSED_FIELDS:
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
                text_widget.delete("1.0", "end")
                text_widget.insert("1.0", formatted_json)
                apply_json_syntax_highlight(text_widget, formatted_json)
                original_content = formatted_json
                
                update_collapsed_ranges()
            
            update_line_numbers()
            
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
            """切换折叠状态"""
            update_display(check_changes=True)
        
        disable_collapse_checkbox = ttk.Checkbutton(toolbar, 
                                                     text=self.t("disable_collapse_horizontal"),
                                                     variable=disable_collapse_var,
                                                     command=toggle_collapse)
        disable_collapse_checkbox.pack(side="left", padx=5)
        
        search_frame = tk.Frame(toolbar)
        search_frame.pack(side="left", padx=5)
        
        search_entry = ttk.Entry(search_frame, width=20)
        search_entry.pack(side="left", padx=2)
        
        self.search_results_label = ttk.Label(search_frame, text="")
        self.search_results_label.pack(side="left", padx=2)
        
        def copy_to_clipboard():
            self.viewer_window.clipboard_clear()
            full_json = json.dumps(self.save_data, ensure_ascii=False, indent=2)
            self.viewer_window.clipboard_append(full_json)
        
        copy_button = ttk.Button(toolbar, text=self.t("copy_to_clipboard"), command=copy_to_clipboard)
        copy_button.pack(side="left", padx=5)
        
        toolbar_right = tk.Frame(toolbar)
        toolbar_right.pack(side="right", padx=5)
        
        def _get_current_text_content() -> str:
            """获取当前文本内容"""
            try:
                return text_widget.get("1.0", "end-1c")
            except tk.TclError:
                return ""
        
        def _has_unsaved_changes() -> bool:
            """检查是否有未保存的修改"""
            if not enable_edit_var.get():
                return False
            current_content = _get_current_text_content()
            return current_content != original_content
        
        def _confirm_discard_changes() -> bool:
            """确认是否抛弃未保存的更改
            
            Returns:
                True 表示用户确认抛弃更改，False 表示用户取消操作
            """
            user_confirmed = askyesno_relative(
                self.viewer_window,
                self.t("refresh_confirm_title"),
                self.t("unsaved_changes_warning")
            )
            return user_confirmed
        
        def check_unsaved_changes(force_check: bool = False) -> bool:
            """检查未保存的修改，必要时弹出确认对话框
            
            Args:
                force_check: 是否强制检查（即使编辑模式未开启）
                
            Returns:
                True 表示可以继续操作（无修改或用户确认抛弃），False 表示用户取消操作
            """
            should_check = force_check or enable_edit_var.get()
            if not should_check:
                return True
            
            if not _has_unsaved_changes():
                return True
            
            return _confirm_discard_changes()
        
        def on_window_close() -> None:
            """窗口关闭事件处理
            
            如果有未保存的修改，弹出确认对话框询问用户是否抛弃更改。
            用户选择"是"则关闭窗口，选择"否"则保持窗口打开。
            """
            if _has_unsaved_changes():
                user_wants_to_discard = _confirm_discard_changes()
                if not user_wants_to_discard:
                    return
            
            self.viewer_window.destroy()
            if self.on_close_callback:
                self.viewer_window.after(CLOSE_CALLBACK_DELAY_MS, self.on_close_callback)
        
        self.viewer_window.protocol("WM_DELETE_WINDOW", on_window_close)
        
        def refresh_save_file() -> None:
            """刷新存档文件
            
            如果存在未保存的修改，会先弹出确认对话框询问用户是否抛弃更改。
            """
            can_proceed = check_unsaved_changes()
            if not can_proceed:
                return
            
            from .save_data_service import load_save_file
            reloaded_save_data = load_save_file(self.storage_dir)
            if reloaded_save_data is None:
                showerror_relative(
                    self.viewer_window,
                    self.t("error"),
                    self.t("save_file_not_found")
                )
                return
            
            self.save_data = reloaded_save_data
            update_display()
        
        refresh_button = ttk.Button(toolbar_right, text=self.t("refresh"), command=refresh_save_file)
        refresh_button.pack(side="right", padx=5)
        
        def toggle_edit_mode() -> None:
            """切换编辑模式
            
            当关闭编辑模式时，如果存在未保存的修改，会弹出确认对话框。
            当开启编辑模式时，会重新加载存档文件以确保数据是最新的。
            """
            is_enabling_edit = not enable_edit_var.get()
            
            if is_enabling_edit:
                can_proceed = check_unsaved_changes(force_check=True)
                if not can_proceed:
                    enable_edit_var.set(True)
                    return
            
            from .save_data_service import load_save_file
            reloaded_save_data = load_save_file(self.storage_dir)
            if reloaded_save_data is None:
                enable_edit_var.set(False)
                showerror_relative(
                    self.viewer_window,
                    self.t("error"),
                    self.t("save_file_not_found")
                )
                return
            
            self.save_data = reloaded_save_data
            
            if enable_edit_var.get():
                update_display()
                nonlocal original_content
                original_content = _get_current_text_content()
            else:
                text_widget.config(state="disabled")
                if self.save_button:
                    self.save_button.config(state="disabled")
                text_widget.tag_remove("user_edit", "1.0", "end")
        
        # 创建包装 Frame 用于抖动动画
        DEFAULT_CHECKBOX_PADX = 5
        checkbox_wrapper = tk.Frame(toolbar_right, bg=Colors.WHITE)
        checkbox_wrapper.pack(side="right", padx=DEFAULT_CHECKBOX_PADX)
        
        # 创建复选框样式
        checkbox_style = ttk.Style(self.viewer_window)
        checkbox_style.configure(
            CHECKBOX_STYLE_NORMAL,
            background=Colors.WHITE
        )
        checkbox_style.configure(
            CHECKBOX_STYLE_HINT,
            background=Colors.WHITE,
            foreground="#FF6B35"  # 红橙色
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
        
        # 初始化提示动画管理器
        hint_animation = HintAnimation(
            self.viewer_window,
            enable_edit_checkbox,
            CHECKBOX_STYLE_NORMAL,
            CHECKBOX_STYLE_HINT
        )
        
        def _restore_collapsed_fields(edited_data: Dict[str, Any]) -> None:
            """恢复折叠字段的原始值
            
            Args:
                edited_data: 编辑后的数据字典
            """
            if disable_collapse_var.get():
                return
            
            collapsed_text = self.t("collapsed_field_text")
            
            for field_name in COLLAPSED_FIELDS:
                if field_name in edited_data:
                    if isinstance(edited_data[field_name], str) and edited_data[field_name] == collapsed_text:
                        if field_name in self.save_data:
                            edited_data[field_name] = self.save_data[field_name]
                else:
                    for key, value in self.save_data.items():
                        if not isinstance(value, dict) or field_name not in value:
                            continue
                        
                        if key in edited_data:
                            if isinstance(edited_data[key], dict):
                                if field_name in edited_data[key]:
                                    if isinstance(edited_data[key][field_name], str) and edited_data[key][field_name] == collapsed_text:
                                        edited_data[key][field_name] = value[field_name]
                            elif isinstance(edited_data[key], str) and edited_data[key] == collapsed_text:
                                edited_data[key] = value
                        break
        
        def save_save_file() -> None:
            """保存存档文件
            
            解析当前文本内容为JSON，恢复折叠字段，然后保存到文件。
            如果JSON格式错误或用户取消确认，则不会保存。
            """
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
            
            user_confirmed = messagebox.askyesno(
                self.t("save_confirm_title"),
                self.t("save_confirm_text"),
                parent=self.viewer_window
            )
            
            if not user_confirmed:
                text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
                return
            
            save_file_path = os.path.join(self.storage_dir, SAVE_FILE_NAME)
            json_str = json.dumps(edited_data, ensure_ascii=False)
            encoded_content = urllib.parse.quote(json_str)
            
            try:
                with open(save_file_path, 'w', encoding='utf-8') as file_handle:
                    file_handle.write(encoded_content)
            except (OSError, IOError, PermissionError) as file_error:
                showerror_relative(
                    self.viewer_window,
                    self.t("error"),
                    f"保存文件失败: {file_error}"
                )
                text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
                return
            
            self.save_data = edited_data
            nonlocal original_content
            original_content = content
            
            showinfo_relative(
                self.viewer_window,
                self.t("success"), 
                self.t("save_success")
            )
            
            update_display()
        
        self.save_button = ttk.Button(toolbar_right, text=self.t("save_file"), 
                                command=save_save_file, state="disabled")
        self.save_button.pack(side="right", padx=5)
        
        def find_text(direction="next"):
            """查找文本"""
            search_term = search_entry.get()
            if not search_term:
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
                
                self.search_results_label.config(text=f"{self.current_search_pos[0] + 1}/{len(self.search_matches)}")
            else:
                self.search_results_label.config(text="未找到")
            
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

