import platform
import logging
import tkinter
from typing import Optional, Tuple, List
import customtkinter as ctk
from src.utils.styles import get_cjk_font, Colors

logger = logging.getLogger(__name__)


class ToastConfig:
    """Toast 配置常量"""
    # 尺寸配置
    DEFAULT_WIDTH = 280
    MIN_TEXT_WIDTH = 50
    MIN_CONTENT_HEIGHT = 30
    DEFAULT_CONTENT_HEIGHT = 50
    MIN_WINDOW_HEIGHT = 60
    MIN_AVAILABLE_WIDTH = 50
    
    # 间距配置
    TOAST_SPACING = 10
    MARGIN_LEFT = 12
    MARGIN_RIGHT = 150
    MARGIN_BOTTOM = 12
    MARGIN_TOP = 12
    HORIZONTAL_PADDING = 30
    
    # 字体和文本配置
    TOP_BAR_HEIGHT = 19
    BOTTOM_PADDING = 8
    LINE_HEIGHT = 18
    CHAR_WIDTH = 7
    CLOSE_BTN_FONT_SIZE = 9
    PIN_INDICATOR_FONT_SIZE = 8
    MESSAGE_FONT_SIZE = 9
    
    # 透明度配置
    FADE_START_ALPHA = 0.0
    FADE_END_ALPHA = 0.85
    FLASH_ALPHA = 0.95
    FADE_OUT_END_ALPHA = 0.0
    
    # 动画配置
    ANIMATION_FRAME_INTERVAL = 16  # 约 60 FPS
    FLASH_DURATION_MS = 200
    
    # 布局配置
    MAX_HEIGHT_RATIO = 0.8
    
    # 颜色配置
    CLOSE_BTN_COLOR_NORMAL = "#666666"
    CLOSE_BTN_COLOR_HOVER = "#ff6b6b"
    PIN_INDICATOR_COLOR = "#888888"
    TEXT_COLOR_GREEN = "#4ade80"
    TEXT_COLOR_RED = "#f87171"
    
    # Windows API 常量
    SPI_GETWORKAREA = 0x0030


class Toast:
    """Toast 通知窗口类"""
    
    _active_toasts: List['Toast'] = []
    
    def __init__(
        self,
        root: ctk.CTk,
        message: str,
        duration: int = 10000,
        fade_in: int = 200,
        fade_out: int = 200,
        y_offset: Optional[int] = None,
        relative_to_window: bool = True,
        position: str = "bottom-right"
    ):
        """
        创建通知
        
        Args:
            root: 根窗口
            message: 通知消息
            duration: 显示持续时间（毫秒，不包括动画时间）
            fade_in: 淡入动画时间（毫秒）
            fade_out: 淡出动画时间（毫秒）
            y_offset: Y轴偏移量（从底部算起），如果为None则自动计算
            relative_to_window: 是否相对于主窗口定位（True）还是相对于整个屏幕（False）
            position: 弹窗位置，可选值："bottom-right"、"top-right"、"bottom-left"、"top-left"
        """
        self.root = root
        self.message = message
        self.duration = duration
        self.fade_in = fade_in
        self.fade_out = fade_out
        self.y_offset = y_offset
        self.relative_to_window = relative_to_window
        self.position = position
        self._fade_out_scheduled: Optional[str] = None
        self._pinned = False
        
        self.margin_left = ToastConfig.MARGIN_LEFT
        self.margin_right = ToastConfig.MARGIN_RIGHT
        self.margin_bottom = ToastConfig.MARGIN_BOTTOM
        self.margin_top = ToastConfig.MARGIN_TOP
        
        self.window_width = ToastConfig.DEFAULT_WIDTH
        self.window_height = 0
        
        self.screen_width = root.winfo_screenwidth()
        self.screen_height = root.winfo_screenheight()
        
        self._work_area: Optional[Tuple[int, int, int, int]] = None
        self.supports_alpha = self._check_alpha_support()
        self.window_scaling = self._get_window_scaling()
        
        self._create_window()
        self._create_ui_components()
        self._bind_click_events()
        self._insert_colored_text(self._tk_text, message)
        
        self.window.update_idletasks()
        self._calculate_and_set_geometry()
        
        Toast._active_toasts.append(self)
        self._animate()
    
    def _check_alpha_support(self) -> bool:
        """检查系统是否支持透明度"""
        if platform.system() != "Windows":
            return False
        
        try:
            test_window = ctk.CTkToplevel(self.root)
            test_window.attributes("-alpha", 0.0)
            test_window.destroy()
            return True
        except (AttributeError, tkinter.TclError) as e:
            logger.debug(f"Alpha transparency not supported: {e}")
            return False
    
    def _get_window_scaling(self) -> float:
        """获取窗口缩放比例"""
        try:
            return ctk.get_window_scaling()
        except (AttributeError, Exception) as e:
            logger.debug(f"Failed to get window scaling: {e}")
            return 1.0
    
    def _create_window(self) -> None:
        """创建主窗口"""
        self.window = ctk.CTkToplevel(self.root)
        self.window.title("")
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(fg_color=Colors.TOAST_BG)
        
        if self.supports_alpha:
            try:
                self.window.attributes("-alpha", ToastConfig.FADE_START_ALPHA)
            except (AttributeError, tkinter.TclError) as e:
                logger.warning(f"Failed to set initial alpha: {e}")
                self.supports_alpha = False
    
    def _create_ui_components(self) -> None:
        """创建 UI 组件"""
        self.main_container = ctk.CTkFrame(self.window, fg_color=Colors.TOAST_BG)
        self.main_container.pack(fill="both", expand=True)
        
        self._create_top_bar()
        self._create_content_area()
    
    def _create_top_bar(self) -> None:
        """创建顶部栏"""
        self.top_bar = ctk.CTkFrame(
            self.main_container,
            fg_color=Colors.TOAST_BG,
            height=16
        )
        self.top_bar.pack(fill="x", padx=5, pady=(3, 0))
        self.top_bar.pack_propagate(False)
        
        self.close_btn = ctk.CTkLabel(
            self.top_bar,
            text="×",
            font=get_cjk_font(ToastConfig.CLOSE_BTN_FONT_SIZE),
            text_color=ToastConfig.CLOSE_BTN_COLOR_NORMAL,
            fg_color=Colors.TOAST_BG,
            cursor="hand2"
        )
        self.close_btn.pack(side="right", padx=2)
        self.close_btn.bind("<Enter>", self._on_close_hover)
        self.close_btn.bind("<Leave>", self._on_close_leave)
        self.close_btn.bind("<Button-1>", self._on_close_click)
        
        self.pin_indicator = ctk.CTkLabel(
            self.top_bar,
            text="📌",
            font=get_cjk_font(ToastConfig.PIN_INDICATOR_FONT_SIZE),
            text_color=ToastConfig.PIN_INDICATOR_COLOR,
            fg_color=Colors.TOAST_BG
        )
    
    def _create_content_area(self) -> None:
        """创建内容区域"""
        self.content_frame = ctk.CTkFrame(self.main_container, fg_color=Colors.TOAST_BG)
        self.content_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        
        self.message_text = ctk.CTkTextbox(
            self.content_frame,
            font=get_cjk_font(ToastConfig.MESSAGE_FONT_SIZE),
            text_color=Colors.TOAST_TEXT,
            fg_color=Colors.TOAST_BG,
            border_width=0,
            corner_radius=0,
            activate_scrollbars=False,
        )
        self._tk_text = getattr(self.message_text, "_textbox", self.message_text)
        self._tk_text.configure(wrap="word", state="disabled", cursor="arrow")
        self.message_text.pack(anchor="nw", fill="both", expand=True)
        
        self._tk_text.tag_configure("green", foreground=ToastConfig.TEXT_COLOR_GREEN)
        self._tk_text.tag_configure("red", foreground=ToastConfig.TEXT_COLOR_RED)
        self._tk_text.tag_configure("default", foreground=Colors.TOAST_TEXT)
    
    def _bind_click_events(self) -> None:
        """绑定点击事件"""
        clickable_widgets = [
            self.main_container,
            self.content_frame,
            self.message_text,
            self.top_bar
        ]
        for widget in clickable_widgets:
            widget.bind("<Button-1>", self._on_toast_click)
    
    def _on_close_hover(self, event) -> None:
        """关闭按钮悬停事件"""
        self.close_btn.configure(text_color=ToastConfig.CLOSE_BTN_COLOR_HOVER)
    
    def _on_close_leave(self, event) -> None:
        """关闭按钮离开事件"""
        self.close_btn.configure(text_color=ToastConfig.CLOSE_BTN_COLOR_NORMAL)
    
    def _on_close_click(self, event) -> None:
        """关闭按钮点击事件"""
        self._close_toast()
    
    def _on_toast_click(self, event) -> None:
        """Toast 点击事件（固定 Toast）"""
        if self._pinned:
            return
        
        self._pinned = True
        self._cancel_fade_out()
        self.pin_indicator.pack(side="left", padx=2)
        self._flash_feedback()
    
    def _cancel_fade_out(self) -> None:
        """取消淡出动画"""
        if self._fade_out_scheduled is not None:
            try:
                self.window.after_cancel(self._fade_out_scheduled)
            except (ValueError, AttributeError) as e:
                logger.debug(f"Failed to cancel fade out: {e}")
            finally:
                self._fade_out_scheduled = None
    
    def _flash_feedback(self) -> None:
        """闪烁反馈效果"""
        if not self._window_exists():
            return
        
        if not self.supports_alpha:
            return
        
        try:
            self.window.attributes("-alpha", ToastConfig.FLASH_ALPHA)
            self.window.after(
                ToastConfig.FLASH_DURATION_MS,
                self._restore_alpha
            )
        except (AttributeError, tkinter.TclError) as e:
            logger.debug(f"Failed to flash feedback: {e}")
    
    def _restore_alpha(self) -> None:
        """恢复透明度"""
        if not self._window_exists():
            return
        
        if not self.supports_alpha:
            return
        
        try:
            self.window.attributes("-alpha", ToastConfig.FADE_END_ALPHA)
        except (AttributeError, tkinter.TclError) as e:
            logger.debug(f"Failed to restore alpha: {e}")
    
    def _window_exists(self) -> bool:
        """检查窗口是否仍然存在"""
        try:
            return self.window.winfo_exists()
        except (tkinter.TclError, AttributeError):
            return False
    
    def _close_toast(self) -> None:
        """关闭 Toast"""
        if not self._window_exists():
            return
        
        self._cancel_fade_out()
        
        try:
            self.window.destroy()
        except (tkinter.TclError, AttributeError) as e:
            logger.debug(f"Failed to destroy window: {e}")
        
        if self in Toast._active_toasts:
            Toast._active_toasts.remove(self)
        
        Toast._reposition_toasts()
    
    def _calculate_content_height(self, available_width: Optional[int] = None) -> int:
        """计算内容高度"""
        if available_width is None:
            available_width = self.window_width
        
        self.message_text.update_idletasks()
        
        text_width = max(
            ToastConfig.MIN_TEXT_WIDTH,
            available_width - ToastConfig.HORIZONTAL_PADDING
        )
        
        height_from_text = self._calculate_height_from_text(text_width)
        if height_from_text is not None:
            return height_from_text
        
        height_from_widget = self._calculate_height_from_widget()
        if height_from_widget is not None:
            return height_from_widget
        
        return ToastConfig.DEFAULT_CONTENT_HEIGHT
    
    def _calculate_height_from_text(self, text_width: int) -> Optional[int]:
        """从文本内容计算高度"""
        try:
            end_index = self._tk_text.index("end-1c")
            logical_lines = int(end_index.split(".")[0])
            
            chars_per_line = max(1, text_width // ToastConfig.CHAR_WIDTH)
            total_display_lines = 0
            
            for line_num in range(1, logical_lines + 1):
                line_start = f"{line_num}.0"
                line_end = f"{line_num}.end"
                try:
                    line_content = self._tk_text.get(line_start, line_end)
                    line_chars = len(line_content)
                    display_lines = max(1, (line_chars + chars_per_line - 1) // chars_per_line)
                    total_display_lines += display_lines
                except (tkinter.TclError, ValueError) as e:
                    logger.debug(f"Failed to get line {line_num}: {e}")
                    total_display_lines += 1
            
            content_height = total_display_lines * ToastConfig.LINE_HEIGHT
            return max(content_height, ToastConfig.MIN_CONTENT_HEIGHT)
        except (tkinter.TclError, ValueError, IndexError) as e:
            logger.debug(f"Failed to calculate height from text: {e}")
            return None
    
    def _calculate_height_from_widget(self) -> Optional[int]:
        """从 widget 请求高度计算"""
        try:
            req_height = self._tk_text.winfo_reqheight()
            if req_height > 0:
                return req_height
        except (tkinter.TclError, AttributeError) as e:
            logger.debug(f"Failed to get widget height: {e}")
        return None
    
    def _get_work_area(self) -> Tuple[int, int, int, int]:
        """
        获取可用工作区（避免被任务栏覆盖）
        
        Returns:
            (left, top, right, bottom) 元组
        """
        if platform.system() == "Windows":
            work_area = self._get_windows_work_area()
            if work_area is not None:
                return work_area
        
        return self._get_fallback_work_area()
    
    def _get_windows_work_area(self) -> Optional[Tuple[int, int, int, int]]:
        """获取 Windows 工作区"""
        try:
            import ctypes
            from ctypes import wintypes
            
            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long)
                ]
            
            rect = RECT()
            success = ctypes.windll.user32.SystemParametersInfoW(
                ToastConfig.SPI_GETWORKAREA,
                0,
                ctypes.byref(rect),
                0
            )
            
            if success:
                return rect.left, rect.top, rect.right, rect.bottom
        except (OSError, AttributeError, ImportError) as e:
            logger.debug(f"Failed to get Windows work area: {e}")
        
        return None
    
    def _get_fallback_work_area(self) -> Tuple[int, int, int, int]:
        """获取回退工作区（整个屏幕）"""
        try:
            screen_width = self.window.winfo_screenwidth()
            screen_height = self.window.winfo_screenheight()
            return 0, 0, screen_width, screen_height
        except (tkinter.TclError, AttributeError) as e:
            logger.debug(f"Failed to get fallback work area: {e}")
            return 0, 0, self.screen_width, self.screen_height
    
    def _calculate_available_width(self) -> int:
        """计算可用宽度"""
        if self._work_area is None:
            return self.window_width
        
        work_left, _, work_right, _ = self._work_area
        work_width = work_right - work_left
        available_width = work_width - self.margin_left - self.margin_right
        
        return max(ToastConfig.MIN_AVAILABLE_WIDTH, available_width)
    
    def _calculate_window_position_relative(
        self,
        window_height: int,
        actual_width: int
    ) -> Optional[Tuple[int, int]]:
        """计算相对于屏幕工作区的位置（定位到屏幕右下）"""
        try:
            # 获取屏幕尺寸
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            
            # 使用工作区（如果可用），避开任务栏
            if self._work_area is not None:
                work_left, work_top, work_right, work_bottom = self._work_area
            else:
                work_left, work_top, work_right, work_bottom = 0, 0, screen_width, screen_height
            
            y_offset = self.y_offset if self.y_offset is not None else 0
            
            position_calculators = {
                "bottom-right": lambda: (
                    work_right - actual_width - self.margin_right,
                    work_bottom - window_height - y_offset - self.margin_bottom
                ),
                "top-right": lambda: (
                    work_right - actual_width - self.margin_right,
                    work_top + self.margin_top + y_offset
                ),
                "bottom-left": lambda: (
                    work_left + self.margin_left,
                    work_bottom - window_height - y_offset - self.margin_bottom
                ),
                "top-left": lambda: (
                    work_left + self.margin_left,
                    work_top + self.margin_top + y_offset
                ),
            }
            
            calculator = position_calculators.get(
                self.position,
                position_calculators["bottom-right"]
            )
            x, y = calculator()
            
            # 确保不超出工作区边界
            x = max(work_left, min(x, work_right - actual_width))
            y = max(work_top, min(y, work_bottom - window_height))
            
            return x, y
        except (tkinter.TclError, AttributeError) as e:
            logger.debug(f"Failed to calculate relative position: {e}")
            return None
    
    def _calculate_window_position_screen(
        self,
        window_height: int,
        actual_width: int
    ) -> Tuple[int, int]:
        """计算相对于屏幕的位置"""
        if self._work_area is None:
            x = self.screen_width - self.window_width - self.margin_right
            y = self.screen_height - window_height - (self.y_offset or 0) - self.margin_bottom
            return x, y
        
        work_left, work_top, work_right, work_bottom = self._work_area
        
        x = work_right - actual_width - self.margin_right
        x = max(work_left + self.margin_left, x)
        
        y_offset = self.y_offset if self.y_offset is not None else 0
        y = work_bottom - window_height - y_offset - self.margin_bottom
        y = max(work_top, y)
        
        return x, y
    
    def _layout_in_work_area(self, window_height: int) -> Tuple[int, int, int]:
        """
        依据工作区计算宽度裁剪与位置
        
        Args:
            window_height: 窗口高度（像素）
        
        Returns:
            (x, y, width): 窗口的 x 坐标、y 坐标和宽度
        """
        available_width = self._calculate_available_width()
        actual_width = min(available_width, self.window_width)
        
        if self.relative_to_window:
            position = self._calculate_window_position_relative(window_height, actual_width)
            if position is not None:
                x, y = position
                return x, y, actual_width
        
        x, y = self._calculate_window_position_screen(window_height, actual_width)
        return x, y, actual_width
    
    def _calculate_window_height(
        self,
        content_height: int
    ) -> int:
        """计算窗口高度"""
        window_height = (
            content_height +
            ToastConfig.TOP_BAR_HEIGHT +
            ToastConfig.BOTTOM_PADDING
        )
        
        max_height = self._calculate_max_height()
        window_height = min(window_height, max_height)
        window_height = max(window_height, ToastConfig.MIN_WINDOW_HEIGHT)
        
        return window_height
    
    def _calculate_max_height(self) -> int:
        """计算最大高度"""
        if self._work_area is not None:
            _, work_top, _, work_bottom = self._work_area
            work_height = work_bottom - work_top
            return int(work_height * ToastConfig.MAX_HEIGHT_RATIO)
        return int(self.screen_height * ToastConfig.MAX_HEIGHT_RATIO)
    
    def _calculate_y_offset(self) -> int:
        """计算 Y 轴偏移量"""
        if self.y_offset is not None:
            return self.y_offset
        
        active_toasts = [
            toast for toast in Toast._active_toasts
            if toast._window_exists()
        ]
        
        if not active_toasts:
            return 0
        
        total_height = sum(
            toast.window_height + ToastConfig.TOAST_SPACING
            for toast in active_toasts
        )
        return total_height
    
    def _calculate_and_set_geometry(self) -> None:
        """计算并设置窗口几何尺寸"""
        self._work_area = self._get_work_area()
        
        available_width = self._calculate_available_width()
        actual_width = min(available_width, self.window_width)
        
        content_height = self._calculate_content_height(actual_width)
        window_height = self._calculate_window_height(content_height)
        
        self.window_height = window_height
        self.y_offset = self._calculate_y_offset()
        
        x, y, final_width = self._layout_in_work_area(window_height)
        self.window_width = final_width
        
        try:
            self.window.geometry(f"{final_width}x{window_height}+{x}+{y}")
        except (tkinter.TclError, AttributeError) as e:
            logger.warning(f"Failed to set geometry: {e}")
        
        self._configure_text_height(content_height)
    
    def _configure_text_height(self, content_height: int) -> None:
        """配置文本高度"""
        try:
            lines_needed = max(
                1,
                content_height // ToastConfig.LINE_HEIGHT
            )
            self.message_text.configure(height=lines_needed)
        except (tkinter.TclError, AttributeError) as e:
            logger.debug(f"Failed to configure text height: {e}")
    
    def update_message(self, new_message: str) -> bool:
        """更新 toast 的消息内容（用于合并连续变化）"""
        if not self._window_exists():
            return False
        
        self.message = new_message
        self._insert_colored_text(self._tk_text, new_message)
        
        self.window.update_idletasks()
        
        old_height = self.window_height
        self._recalculate_geometry()
        
        if old_height != self.window_height:
            Toast._reposition_toasts()
        
        return True
    
    def _recalculate_geometry(self) -> None:
        """重新计算几何尺寸"""
        self._work_area = self._get_work_area()
        
        available_width = self._calculate_available_width()
        actual_width = min(available_width, self.window_width)
        
        content_height = self._calculate_content_height(actual_width)
        new_height = self._calculate_window_height(content_height)
        
        self.window_height = new_height
        self.window_width = actual_width
        
        x, y, final_width = self._layout_in_work_area(new_height)
        self.window_width = final_width
        
        try:
            self.window.geometry(f"{final_width}x{new_height}+{x}+{y}")
        except (tkinter.TclError, AttributeError) as e:
            logger.warning(f"Failed to update geometry: {e}")
        
        self._configure_text_height(content_height)
    
    def reset_timer(self) -> bool:
        """重置 toast 的显示时间（延长显示）"""
        if not self._window_exists():
            return False
        
        if self._pinned:
            return True
        
        self._cancel_fade_out()
        self._fade_out_scheduled = self.window.after(
            self.duration,
            self._start_fade_out
        )
        return True
    
    def _insert_colored_text(self, text_widget, message: str) -> None:
        """插入带颜色的文本到 Text widget"""
        text_widget.configure(state="normal")
        text_widget.delete("1.0", "end")
        
        lines = message.split("\n")
        for line_idx, line in enumerate(lines):
            if line_idx > 0:
                text_widget.insert("end", "\n")
            
            self._insert_colored_line(text_widget, line)
        
        text_widget.configure(state="disabled")
    
    def _insert_colored_line(self, text_widget, line: str) -> None:
        """插入带颜色的单行文本"""
        line_stripped = line.strip()
        
        if line_stripped.startswith("+"):
            self._insert_plus_line(text_widget, line)
        elif line_stripped.startswith("-"):
            self._insert_minus_line(text_widget, line)
        elif ".append(" in line:
            self._insert_append_line(text_widget, line)
        elif ".remove(" in line:
            self._insert_remove_line(text_widget, line)
        else:
            text_widget.insert("end", line, "default")
    
    def _insert_plus_line(self, text_widget, line: str) -> None:
        """插入以 + 开头的行"""
        plus_pos = line.find("+")
        if plus_pos >= 0:
            text_widget.insert("end", line[:plus_pos], "default")
            text_widget.insert("end", "+", "green")
            remaining = line[plus_pos + 1:]
            if remaining:
                text_widget.insert("end", remaining, "default")
        else:
            text_widget.insert("end", line, "default")
    
    def _insert_minus_line(self, text_widget, line: str) -> None:
        """插入以 - 开头的行"""
        minus_pos = line.find("-")
        if minus_pos >= 0:
            text_widget.insert("end", line[:minus_pos], "default")
            text_widget.insert("end", "-", "red")
            remaining = line[minus_pos + 1:]
            if remaining:
                text_widget.insert("end", remaining, "default")
        else:
            text_widget.insert("end", line, "default")
    
    def _insert_append_line(self, text_widget, line: str) -> None:
        """插入包含 .append( 的行"""
        parts = line.split(".append(")
        text_widget.insert("end", parts[0], "default")
        text_widget.insert("end", ".append(", "green")
        if len(parts) > 1:
            text_widget.insert("end", parts[1], "default")
    
    def _insert_remove_line(self, text_widget, line: str) -> None:
        """插入包含 .remove( 的行"""
        parts = line.split(".remove(")
        text_widget.insert("end", parts[0], "default")
        text_widget.insert("end", ".remove(", "red")
        if len(parts) > 1:
            text_widget.insert("end", parts[1], "default")
    
    def _animate(self) -> None:
        """开始动画"""
        self._fade_in(
            ToastConfig.FADE_START_ALPHA,
            ToastConfig.FADE_END_ALPHA,
            self.fade_in,
            0
        )
    
    def _fade_in(
        self,
        start_alpha: float,
        end_alpha: float,
        duration: int,
        step: int
    ) -> None:
        """淡入动画"""
        if not self._window_exists():
            return
        
        steps = max(1, duration // ToastConfig.ANIMATION_FRAME_INTERVAL)
        alpha_step = (end_alpha - start_alpha) / steps
        
        if step < steps:
            current_alpha = start_alpha + alpha_step * step
            self._set_alpha(current_alpha)
            self.window.after(
                ToastConfig.ANIMATION_FRAME_INTERVAL,
                lambda: self._fade_in(start_alpha, end_alpha, duration, step + 1)
            )
        else:
            self._set_alpha(end_alpha)
            if not self._pinned:
                self._fade_out_scheduled = self.window.after(
                    self.duration,
                    self._start_fade_out
                )
    
    def _start_fade_out(self) -> None:
        """开始淡出动画"""
        if not self._window_exists() or self._pinned:
            return
        
        current_alpha = ToastConfig.FADE_END_ALPHA
        if self.supports_alpha:
            try:
                current_alpha = self.window.attributes("-alpha")
            except (AttributeError, tkinter.TclError) as e:
                logger.debug(f"Failed to get current alpha: {e}")
        
        self._fade_out(
            current_alpha,
            ToastConfig.FADE_OUT_END_ALPHA,
            self.fade_out,
            0
        )
    
    def _fade_out(
        self,
        start_alpha: float,
        end_alpha: float,
        duration: int,
        step: int
    ) -> None:
        """淡出动画"""
        if not self._window_exists():
            return
        
        steps = max(1, duration // ToastConfig.ANIMATION_FRAME_INTERVAL)
        alpha_step = (end_alpha - start_alpha) / steps
        
        if step < steps:
            current_alpha = start_alpha + alpha_step * step
            self._set_alpha(current_alpha)
            self.window.after(
                ToastConfig.ANIMATION_FRAME_INTERVAL,
                lambda: self._fade_out(start_alpha, end_alpha, duration, step + 1)
            )
        else:
            self._close_toast()
    
    def _set_alpha(self, alpha: float) -> None:
        """设置窗口透明度"""
        if not self.supports_alpha:
            return
        
        try:
            self.window.attributes("-alpha", alpha)
        except (AttributeError, tkinter.TclError) as e:
            logger.debug(f"Failed to set alpha: {e}")
    
    @staticmethod
    def _reposition_toasts() -> None:
        """重新定位所有活跃的 Toast"""
        if not Toast._active_toasts:
            return
        
        try:
            root = Toast._active_toasts[0].root
        except (IndexError, AttributeError) as e:
            logger.debug(f"Failed to get root for repositioning: {e}")
            return
        
        active_toasts = [
            toast for toast in Toast._active_toasts
            if toast._window_exists()
        ]
        Toast._active_toasts = active_toasts
        
        if not active_toasts:
            return
        
        # 更新所有 toast 的工作区
        for toast in active_toasts:
            try:
                toast._work_area = toast._get_work_area()
            except Exception as e:
                logger.debug(f"Failed to update work area for toast: {e}")
        
        # 重新定位所有 toast
        y_offset = 0
        for toast in active_toasts:
            try:
                if toast._window_exists():
                    toast.y_offset = y_offset
                    x, y, width = toast._layout_in_work_area(toast.window_height)
                    toast.window_width = width
                    toast.window.geometry(f"{width}x{toast.window_height}+{x}+{y}")
                    y_offset += toast.window_height + ToastConfig.TOAST_SPACING
            except Exception as e:
                logger.debug(f"Failed to reposition toast: {e}")
                continue
