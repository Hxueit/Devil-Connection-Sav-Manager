import tkinter as tk
import platform
from styles import get_cjk_font, Colors


class Toast:
    
    # 类变量：存储所有活跃的toast实例
    _active_toasts = []
    _toast_spacing = 10  # toast之间的间距（像素）
    
    def __init__(self, root, message, duration=10000, fade_in=200, fade_out=200, y_offset=None):
        """
        创建通知
        
        Args:
            root: 根窗口
            message: 通知消息
            duration: 显示持续时间（毫秒，不包括动画时间）
            fade_in: 淡入动画时间（毫秒）
            fade_out: 淡出动画时间（毫秒）
            y_offset: Y轴偏移量（从底部算起），如果为None则自动计算
        """
        self.root = root
        self.message = message
        self.duration = duration
        self.fade_in = fade_in
        self.fade_out = fade_out
        self.y_offset = y_offset
        self._fade_out_scheduled = None
        self._pinned = False
        
        self.window = tk.Toplevel(root)
        self.window.title("")
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        
        self.window.configure(bg=Colors.TOAST_BG)
        
        self.screen_width = root.winfo_screenwidth()
        self.screen_height = root.winfo_screenheight()
        
        self.window_width = 300
        
        self.supports_alpha = False
        if platform.system() == "Windows":
            try:
                self.window.attributes("-alpha", 0.0)
                self.supports_alpha = True
            except:
                self.supports_alpha = False
        
        self.main_container = tk.Frame(self.window, bg=Colors.TOAST_BG)
        self.main_container.pack(fill="both", expand=True)
        
        self.top_bar = tk.Frame(self.main_container, bg=Colors.TOAST_BG, height=16)
        self.top_bar.pack(fill="x", padx=5, pady=(3, 0))
        self.top_bar.pack_propagate(False)
        
        self.close_btn = tk.Label(
            self.top_bar,
            text="×",
            font=get_cjk_font(9),
            fg="#666666",
            bg=Colors.TOAST_BG,
            cursor="hand2"
        )
        self.close_btn.pack(side="right", padx=2)
        self.close_btn.bind("<Enter>", self._on_close_hover)
        self.close_btn.bind("<Leave>", self._on_close_leave)
        self.close_btn.bind("<Button-1>", self._on_close_click)
        
        self.pin_indicator = tk.Label(
            self.top_bar,
            text="📌",
            font=get_cjk_font(8),
            fg="#888888",
            bg=Colors.TOAST_BG
        )
        
        self.content_frame = tk.Frame(self.main_container, bg=Colors.TOAST_BG)
        self.content_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        
        self.message_text = tk.Text(
            self.content_frame,
            font=get_cjk_font(9),
            fg=Colors.TOAST_TEXT,
            bg=Colors.TOAST_BG,
            wrap="word",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            state="disabled",
            cursor="arrow"
        )
        self.message_text.pack(anchor="nw", fill="both", expand=True)
        
        self.message_text.tag_configure("green", foreground="#4ade80")
        self.message_text.tag_configure("red", foreground="#f87171")
        self.message_text.tag_configure("default", foreground=Colors.TOAST_TEXT)
        
        self._bind_click_events()
        
        self._insert_colored_text(self.message_text, message)
        
        self.window.update_idletasks()
        
        self._calculate_and_set_geometry()
        
        Toast._active_toasts.append(self)
        
        self._animate()
    
    def _bind_click_events(self):
        """绑定点击事件到所有组件（除了关闭按钮）"""
        for widget in [self.main_container, self.content_frame, self.message_text, self.top_bar]:
            widget.bind("<Button-1>", self._on_toast_click)
    
    def _on_close_hover(self, event):
        """鼠标悬停在关闭按钮上"""
        self.close_btn.configure(fg="#ff6b6b")
    
    def _on_close_leave(self, event):
        """鼠标离开关闭按钮"""
        self.close_btn.configure(fg="#666666")
    
    def _on_close_click(self, event):
        """点击关闭按钮"""
        self._close_toast()
    
    def _on_toast_click(self, event):
        """点击toast的其他部分"""
        if self._pinned:
            return
        
        self._pinned = True
        
        if self._fade_out_scheduled:
            try:
                self.window.after_cancel(self._fade_out_scheduled)
                self._fade_out_scheduled = None
            except:
                pass
        
        self.pin_indicator.pack(side="left", padx=2)
        
        self._flash_feedback()
    
    def _flash_feedback(self):
        """点击反馈：短暂提高透明度"""
        if not self.window.winfo_exists():
            return
        
        if self.supports_alpha:
            try:
                self.window.attributes("-alpha", 0.95)
                self.window.after(200, self._restore_alpha)
            except:
                pass
    
    def _restore_alpha(self):
        """恢复正常透明度"""
        if not self.window.winfo_exists():
            return
        
        if self.supports_alpha:
            try:
                self.window.attributes("-alpha", 0.85)
            except:
                pass
    
    def _close_toast(self):
        """关闭toast"""
        if not self.window.winfo_exists():
            return
        
        if self._fade_out_scheduled:
            try:
                self.window.after_cancel(self._fade_out_scheduled)
            except:
                pass
        
        self.window.destroy()
        
        if self in Toast._active_toasts:
            Toast._active_toasts.remove(self)
        
        Toast._reposition_toasts()
    
    def _calculate_content_height(self):
        """计算内容实际需要的高度"""
        self.message_text.update_idletasks()
        
        try:
            end_index = self.message_text.index("end-1c")
            logical_lines = int(end_index.split(".")[0])
            
            total_display_lines = 0
            text_width = self.window_width - 30
            char_width = 7
            chars_per_line = max(1, text_width // char_width)
            
            for i in range(1, logical_lines + 1):
                line_start = f"{i}.0"
                line_end = f"{i}.end"
                try:
                    line_content = self.message_text.get(line_start, line_end)
                    line_chars = len(line_content)
                    display_lines = max(1, (line_chars + chars_per_line - 1) // chars_per_line)
                    total_display_lines += display_lines
                except:
                    total_display_lines += 1
            
            line_height = 18
            content_height = total_display_lines * line_height
            
            return max(content_height, 30)
        except:
            pass
        
        try:
            req_height = self.message_text.winfo_reqheight()
            if req_height > 0:
                return req_height
        except:
            pass
        
        return 50
    
    def _calculate_and_set_geometry(self):
        """计算并设置窗口位置和大小"""
        content_height = self._calculate_content_height()
        
        top_bar_height = 19
        bottom_padding = 8
        window_height = content_height + top_bar_height + bottom_padding
        
        max_height = int(self.screen_height * 0.8)
        if window_height > max_height:
            window_height = max_height
        
        min_height = 60
        if window_height < min_height:
            window_height = min_height
        
        self.window_height = window_height
        
        if self.y_offset is None:
            active_toasts = [toast for toast in Toast._active_toasts if toast.window.winfo_exists()]
            if active_toasts:
                total_height = sum(toast.window_height + Toast._toast_spacing 
                                 for toast in active_toasts)
                y_offset = total_height
            else:
                y_offset = 0
            self.y_offset = y_offset
        
        x = self.screen_width - self.window_width - 15
        y = self.screen_height - window_height - 15 - self.y_offset
        
        self.window.geometry(f"{self.window_width}x{window_height}+{x}+{y}")
        
        try:
            lines_needed = max(1, content_height // 18)
            self.message_text.configure(height=lines_needed)
        except:
            pass
    
    def update_message(self, new_message):
        """更新toast的消息内容（用于合并连续变化）"""
        if not self.window.winfo_exists():
            return False
        
        self.message = new_message
        self._insert_colored_text(self.message_text, new_message)
        
        self.window.update_idletasks()
        
        content_height = self._calculate_content_height()
        
        top_bar_height = 19
        bottom_padding = 8
        new_height = content_height + top_bar_height + bottom_padding
        
        max_height = int(self.screen_height * 0.8)
        if new_height > max_height:
            new_height = max_height
        min_height = 60
        if new_height < min_height:
            new_height = min_height
        
        old_height = self.window_height
        self.window_height = new_height
        
        x = self.screen_width - self.window_width - 15
        y = self.screen_height - new_height - 15 - self.y_offset
        self.window.geometry(f"{self.window_width}x{new_height}+{x}+{y}")
        
        try:
            lines_needed = max(1, content_height // 18)
            self.message_text.configure(height=lines_needed)
        except:
            pass
        
        if old_height != new_height:
            Toast._reposition_toasts()
        
        return True
    
    def reset_timer(self):
        """重置toast的显示时间（延长显示）"""
        if not self.window.winfo_exists():
            return False
        
        if self._pinned:
            return True
        
        if self._fade_out_scheduled:
            try:
                self.window.after_cancel(self._fade_out_scheduled)
                self._fade_out_scheduled = None
            except:
                pass
        
        self._fade_out_scheduled = self.window.after(self.duration, self._start_fade_out)
        return True
    
    def _insert_colored_text(self, text_widget, message):
        """插入带颜色的文本到Text widget"""
        text_widget.config(state="normal")
        text_widget.delete("1.0", "end")
        
        lines = message.split("\n")
        for line_idx, line in enumerate(lines):
            if line_idx > 0:
                text_widget.insert("end", "\n")
            
            if line.strip().startswith("+"):
                plus_pos = line.find("+")
                if plus_pos >= 0:
                    text_widget.insert("end", line[:plus_pos], "default")
                    text_widget.insert("end", "+", "green")
                    remaining = line[plus_pos + 1:]
                    if remaining:
                        text_widget.insert("end", remaining, "default")
                else:
                    text_widget.insert("end", line, "default")
            elif line.strip().startswith("-"):
                minus_pos = line.find("-")
                if minus_pos >= 0:
                    text_widget.insert("end", line[:minus_pos], "default")
                    text_widget.insert("end", "-", "red")
                    remaining = line[minus_pos + 1:]
                    if remaining:
                        text_widget.insert("end", remaining, "default")
                else:
                    text_widget.insert("end", line, "default")
            elif ".append(" in line:
                parts = line.split(".append(")
                text_widget.insert("end", parts[0], "default")
                text_widget.insert("end", ".append(", "green")
                if len(parts) > 1:
                    text_widget.insert("end", parts[1], "default")
            elif ".remove(" in line:
                parts = line.split(".remove(")
                text_widget.insert("end", parts[0], "default")
                text_widget.insert("end", ".remove(", "red")
                if len(parts) > 1:
                    text_widget.insert("end", parts[1], "default")
            else:
                text_widget.insert("end", line, "default")
        
        text_widget.config(state="disabled")
    
    def _animate(self):
        """执行淡入-等待-淡出动画"""
        self._fade_in(0.0, 0.85, self.fade_in, 0)
    
    def _fade_in(self, start_alpha, end_alpha, duration, step):
        """淡入动画"""
        if not self.window.winfo_exists():
            return
        
        steps = max(1, duration // 16)
        alpha_step = (end_alpha - start_alpha) / steps
        
        if step < steps:
            current_alpha = start_alpha + alpha_step * step
            if self.supports_alpha:
                try:
                    self.window.attributes("-alpha", current_alpha)
                except:
                    pass
            self.window.after(16, lambda: self._fade_in(start_alpha, end_alpha, duration, step + 1))
        else:
            if self.supports_alpha:
                try:
                    self.window.attributes("-alpha", end_alpha)
                except:
                    pass
            if not self._pinned:
                self._fade_out_scheduled = self.window.after(self.duration, self._start_fade_out)
    
    def _start_fade_out(self):
        """开始淡出动画"""
        if not self.window.winfo_exists():
            return
        
        if self._pinned:
            return
        
        current_alpha = 0.85
        if self.supports_alpha:
            try:
                current_alpha = self.window.attributes("-alpha")
            except:
                current_alpha = 0.85
        
        self._fade_out(current_alpha, 0.0, self.fade_out, 0)
    
    def _fade_out(self, start_alpha, end_alpha, duration, step):
        """淡出动画"""
        if not self.window.winfo_exists():
            return
        
        steps = max(1, duration // 16)
        alpha_step = (end_alpha - start_alpha) / steps
        
        if step < steps:
            current_alpha = start_alpha + alpha_step * step
            if self.supports_alpha:
                try:
                    self.window.attributes("-alpha", current_alpha)
                except:
                    pass
            self.window.after(16, lambda: self._fade_out(start_alpha, end_alpha, duration, step + 1))
        else:
            if self.window.winfo_exists():
                self.window.destroy()
            if self in Toast._active_toasts:
                Toast._active_toasts.remove(self)
            Toast._reposition_toasts()
    
    @staticmethod
    def _reposition_toasts():
        """重新排列所有活跃的toast"""
        if not Toast._active_toasts:
            return
        
        try:
            root = Toast._active_toasts[0].root
            screen_width = root.winfo_screenwidth()
            screen_height = root.winfo_screenheight()
        except:
            return
        
        active_toasts = [toast for toast in Toast._active_toasts if toast.window.winfo_exists()]
        Toast._active_toasts = active_toasts
        
        if not active_toasts:
            return
        
        y_offset = 0
        window_width = 300
        
        for toast in active_toasts:
            x = screen_width - window_width - 15
            y = screen_height - toast.window_height - 15 - y_offset
            try:
                if toast.window.winfo_exists():
                    toast.window.geometry(f"{window_width}x{toast.window_height}+{x}+{y}")
                    toast.y_offset = y_offset
                    y_offset += toast.window_height + Toast._toast_spacing
            except:
                continue
