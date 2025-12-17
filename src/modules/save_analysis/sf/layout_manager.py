"""UI布局和滚动管理模块

负责管理存档分析器的主窗口布局、滚动区域更新、画布宽度调整和鼠标滚轮事件绑定。
此模块专注于UI布局相关的逻辑，不涉及数据渲染。
"""

import tkinter as tk
from tkinter import Scrollbar
from typing import Optional, Callable, Dict, Any
import customtkinter as ctk
from src.utils.styles import Colors


class LayoutManager:
    """管理UI布局和滚动区域的类"""
    
    def __init__(
        self,
        window: tk.Widget,
        cached_width: int,
        update_scrollregion_callback: Callable[[str], None]
    ):
        """初始化布局管理器
        
        Args:
            window: 主窗口widget
            cached_width: 缓存的宽度值
            update_scrollregion_callback: 更新滚动区域的回调函数
        """
        self.window = window
        self._cached_width = cached_width
        self._update_scrollregion = update_scrollregion_callback
        self._width_update_pending = False
        self._scroll_update_pending = False
        self._scroll_retry_count: Dict[str, int] = {}
        self._paned_update_pending = False
        self._canvas: Optional[ctk.CTkCanvas] = None
        self._scrollable_frame: Optional[tk.Frame] = None
        self._canvas_for_wheel: Optional[ctk.CTkCanvas] = None
        self._on_mousewheel_handler: Optional[Callable] = None
    
    def create_main_layout(
        self,
        control_frame_callback: Callable[[tk.Frame], None]
    ) -> tuple[tk.Frame, tk.Frame, tk.Frame, ctk.CTkCanvas]:
        """创建主窗口布局
        
        Args:
            control_frame_callback: 创建控制面板的回调函数
            
        Returns:
            (main_container, left_frame, right_frame, canvas) 元组
        """
        control_frame = tk.Frame(self.window, bg=Colors.WHITE)
        control_frame.pack(fill="x", padx=10, pady=5)
        control_frame_callback(control_frame)
        
        main_container = tk.Frame(
            self.window, 
            bg=Colors.WHITE, 
            highlightthickness=0, 
            takefocus=0
        )
        main_container.pack(fill="both", expand=True)
        
        main_paned = tk.PanedWindow(
            main_container, 
            orient="horizontal", 
            sashwidth=0, 
            bg=Colors.WHITE, 
            sashrelief='flat'
        )
        main_paned.pack(side="left", fill="both", expand=True)
        
        left_frame = tk.Frame(
            main_paned, 
            bg=Colors.WHITE, 
            highlightthickness=0, 
            takefocus=0
        )
        main_paned.add(left_frame, width=800, minsize=400)
        
        canvas = ctk.CTkCanvas(left_frame, bg=Colors.WHITE)
        scrollable_frame = tk.Frame(
            canvas, 
            bg=Colors.WHITE, 
            highlightthickness=0, 
            takefocus=0
        )
        scrollable_frame.config(width=self._cached_width)
        
        scrollable_frame.bind("<Configure>", self._on_scrollable_configure)
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.pack(fill="both", expand=True)
        
        self.window.bind("<Configure>", self._on_window_configure)
        
        right_frame = tk.Frame(main_paned, bg=Colors.WHITE)
        main_paned.add(right_frame, width=400, minsize=200)
        
        self._setup_paned_window(main_paned, left_frame)
        
        scrollbar = Scrollbar(
            main_container, 
            orient="vertical", 
            command=canvas.yview
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        
        self._bind_mousewheel_events(canvas, left_frame, scrollable_frame)
        
        # 存储引用以便后续使用
        self._canvas = canvas
        self._scrollable_frame = scrollable_frame
        
        return main_container, left_frame, right_frame, canvas, scrollable_frame
    
    def _on_scrollable_configure(self, event: Optional[tk.Event] = None) -> None:
        """处理可滚动区域的配置事件"""
        if not self._scroll_update_pending:
            self._scroll_update_pending = True
            retry_key = f"configure_{id(event) if event else 'idle'}"
            self.window.after_idle(
                lambda: self.update_scrollregion(retry_key, canvas=self._canvas, scrollable_frame=self._scrollable_frame)
            )
    
    def _on_window_configure(self, event: Optional[tk.Event] = None) -> None:
        """处理窗口配置事件"""
        if event is None or event.widget == self.window:
            self._update_canvas_width(self._canvas, self._scrollable_frame)
    
    def _update_canvas_width(
        self, 
        canvas: Optional[ctk.CTkCanvas] = None,
        scrollable_frame: Optional[tk.Frame] = None
    ) -> None:
        """更新画布宽度
        
        Args:
            canvas: 画布widget（如果为None，则从回调中获取）
            scrollable_frame: 可滚动frame（如果为None，则从回调中获取）
        """
        if self._width_update_pending:
            return
        
        self._width_update_pending = True
        
        def do_update() -> None:
            if canvas is None or scrollable_frame is None:
                self._width_update_pending = False
                return
            
            if not canvas.winfo_exists():
                self._width_update_pending = False
                return
            
            window_width = self.window.winfo_width()
            if window_width > 1:
                width = max(1, int(window_width * 2 / 3))
                self._cached_width = width
                canvas.config(width=width)
                scrollable_frame.config(width=width)
                self.window.after_idle(
                    lambda: self.update_scrollregion("canvas_width_update", canvas=canvas, scrollable_frame=scrollable_frame)
                )
            
            self._width_update_pending = False
        
        self.window.after_idle(do_update)
    
    def _setup_paned_window(
        self, 
        main_paned: tk.PanedWindow, 
        left_frame: tk.Frame
    ) -> None:
        """设置分割窗口的行为"""
        def set_paned_ratio(event: Optional[tk.Event] = None) -> None:
            if self._paned_update_pending:
                return
            
            self._paned_update_pending = True
            
            def do_update() -> None:
                if main_paned.winfo_width() > 1:
                    total_width = main_paned.winfo_width()
                    left_width = int(total_width * 0.67)
                    main_paned.paneconfig(left_frame, width=left_width)
                self._paned_update_pending = False
            
            self.window.after_idle(do_update)
        
        def disable_sash_drag(event: tk.Event) -> str:
            return "break"
        
        main_paned.bind("<Button-1>", disable_sash_drag)
        main_paned.bind("<B1-Motion>", disable_sash_drag)
        main_paned.bind("<ButtonRelease-1>", disable_sash_drag)
        main_paned.bind("<Configure>", set_paned_ratio)
        set_paned_ratio()
    
    def _bind_mousewheel_events(
        self,
        canvas: ctk.CTkCanvas,
        left_frame: tk.Frame,
        scrollable_frame: tk.Frame
    ) -> None:
        """绑定鼠标滚轮事件"""
        self._canvas_for_wheel = canvas
        self._on_mousewheel_handler = self._create_mousewheel_handler(canvas)
        self._bind_mousewheel_recursive(canvas)
        self._bind_mousewheel_recursive(left_frame)
        self._bind_mousewheel_recursive(scrollable_frame)
    
    def _create_mousewheel_handler(self, canvas: ctk.CTkCanvas) -> Callable:
        """创建鼠标滚轮事件处理器
        
        Args:
            canvas: 画布widget
            
        Returns:
            事件处理函数
        """
        def on_mousewheel(event: tk.Event) -> None:
            if event.delta:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
        return on_mousewheel
    
    def _bind_mousewheel_recursive(self, widget: tk.Widget) -> None:
        """递归绑定滚轮事件到widget及其所有子组件
        
        Args:
            widget: 要绑定的widget
        """
        if widget and widget.winfo_exists():
            widget.bind("<MouseWheel>", self._on_mousewheel_handler)
            widget.bind("<Button-4>", self._on_mousewheel_handler)
            widget.bind("<Button-5>", self._on_mousewheel_handler)
            for child in widget.winfo_children():
                self._bind_mousewheel_recursive(child)
    
    def rebind_mousewheel_to_frame(self, frame: tk.Widget) -> None:
        """重新绑定鼠标滚轮事件到指定的frame及其所有子组件
        
        用于在动态创建新widget后重新绑定滚轮事件
        
        Args:
            frame: 要绑定滚轮事件的frame
        """
        if not hasattr(self, '_on_mousewheel_handler') or not self._on_mousewheel_handler:
            # 如果handler未初始化，使用canvas重新创建
            if self._canvas_for_wheel:
                self._on_mousewheel_handler = self._create_mousewheel_handler(self._canvas_for_wheel)
            else:
                return
        
        self._bind_mousewheel_recursive(frame)
    
    def update_scrollregion(
        self,
        retry_key: str = "default",
        max_retries: int = 3,
        canvas: Optional[ctk.CTkCanvas] = None,
        scrollable_frame: Optional[tk.Frame] = None
    ) -> None:
        """更新滚动区域
        
        Args:
            retry_key: 重试键，用于区分不同的调用点
            max_retries: 最大重试次数
            canvas: 画布widget
            scrollable_frame: 可滚动frame
        """
        if canvas is None or scrollable_frame is None:
            self._scroll_update_pending = False
            self._scroll_retry_count.pop(retry_key, None)
            return
        
        if not canvas.winfo_exists():
            self._scroll_update_pending = False
            self._scroll_retry_count.pop(retry_key, None)
            return
        
        try:
            scrollable_frame.update_idletasks()
            canvas.update_idletasks()
            self.window.update_idletasks()
            
            bbox = canvas.bbox("all")
            
            if bbox is None:
                self._handle_scroll_retry(retry_key, max_retries)
                return
            
            if not isinstance(bbox, tuple) or len(bbox) < 4:
                self._handle_scroll_retry(retry_key, max_retries)
                return
            
            x1, y1, x2, y2 = bbox[:4]
            
            if x2 <= x1 or y2 <= y1:
                self._handle_scroll_retry(retry_key, max_retries)
                return
            
            canvas.configure(scrollregion=bbox)
            self._scroll_retry_count.pop(retry_key, None)
            self._scroll_update_pending = False
            
        except (AttributeError, tk.TclError) as e:
            self._handle_scroll_retry(retry_key, max_retries)
        finally:
            if retry_key not in self._scroll_retry_count or self._scroll_retry_count.get(retry_key, 0) == 0:
                self._scroll_update_pending = False
    
    def _handle_scroll_retry(self, retry_key: str, max_retries: int) -> None:
        """处理滚动区域更新的重试逻辑"""
        retry_count = self._scroll_retry_count.get(retry_key, 0)
        if retry_count < max_retries:
            self._scroll_retry_count[retry_key] = retry_count + 1
            self.window.after_idle(
                lambda: self.update_scrollregion(retry_key, max_retries, canvas, scrollable_frame)
            )
        else:
            self._scroll_update_pending = False
            self._scroll_retry_count.pop(retry_key, None)
    
    @property
    def cached_width(self) -> int:
        """获取缓存的宽度"""
        return self._cached_width
    
    @cached_width.setter
    def cached_width(self, value: int) -> None:
        """设置缓存的宽度"""
        self._cached_width = value

