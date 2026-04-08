"""提示动画工具模块

提供可复用的提示动画功能，用于在用户尝试执行禁用操作时给出视觉反馈。
"""

from typing import Optional
import time
import tkinter as tk
from tkinter import ttk

from src.modules.screenshot.animation_constants import (
    SHAKE_OFFSETS,
    SHAKE_STEP_DELAY_MS,
    SHAKE_COLOR_RESTORE_DELAY_MS,
    HINT_COLOR_ORANGE,
    CHECKBOX_STYLE_HINT
)


class HintAnimation:
    """提示动画管理器
    
    提供统一的提示动画接口，支持变色和抖动效果。
    """
    
    def __init__(self, root: tk.Tk, target_widget: ttk.Checkbutton, 
                 normal_style: str, hint_style: str = CHECKBOX_STYLE_HINT) -> None:
        """初始化提示动画管理器
        
        Args:
            root: 根窗口对象
            target_widget: 目标控件（通常是复选框）
            normal_style: 正常状态的样式名称
            hint_style: 提示状态的样式名称
        """
        self.root = root
        self.target_widget = target_widget
        self.normal_style = normal_style
        self.hint_style = hint_style
        self.wrapper: Optional[tk.Frame] = getattr(target_widget, 'wrapper', None)
        self._last_trigger_time = 0.0
        self._debounce_delay_ms = 500
    
    def trigger(self) -> None:
        """触发提示动画（带防抖）
        
        使用防抖机制避免短时间内重复触发动画，提升性能和用户体验。
        """
        current_time = time.time() * 1000
        
        if current_time - self._last_trigger_time < self._debounce_delay_ms:
            return
        
        self._last_trigger_time = current_time
        self._start_animation()
    
    def _start_animation(self) -> None:
        """开始动画"""
        if not self.wrapper:
            return
        
        self._apply_hint_style()
        original_padx = self._get_original_padx()
        self._start_shake_animation(original_padx)
    
    def _apply_hint_style(self) -> None:
        """应用提示样式（红橙色）"""
        checkbox_style = ttk.Style(self.root)
        checkbox_style.configure(
            self.hint_style,
            background=self._get_background_color(),
            foreground=HINT_COLOR_ORANGE
        )
        self.target_widget.config(style=self.hint_style)
    
    def _get_background_color(self) -> str:
        """获取背景颜色"""
        from src.utils.styles import Colors
        # 尝试从目标控件的父容器获取背景色
        try:
            parent = self.target_widget.master
            if hasattr(parent, 'cget'):
                bg = parent.cget('bg')
                if bg:
                    return bg
        except (tk.TclError, AttributeError):
            pass
        return Colors.LIGHT_GRAY
    
    def _get_original_padx(self) -> int:
        """获取原始padx值
        
        Returns:
            原始padx值（整数）
        """
        DEFAULT_PADX = 5
        pack_info = getattr(self.target_widget, '_original_pack_info', {})
        raw_padx = pack_info.get('padx', DEFAULT_PADX)
        
        if isinstance(raw_padx, (list, tuple)):
            return int(raw_padx[0]) if raw_padx else DEFAULT_PADX
        return int(raw_padx) if raw_padx else DEFAULT_PADX
    
    def _start_shake_animation(self, original_padx: int) -> None:
        """开始抖动动画
        
        Args:
            original_padx: 原始padx值
        """
        if not self.wrapper:
            return
        
        def shake_step(step_index: int) -> None:
            """执行抖动步骤"""
            if step_index >= len(SHAKE_OFFSETS):
                self._restore_normal_state(original_padx)
                return
            
            offset = SHAKE_OFFSETS[step_index]
            new_padx = max(0, original_padx + offset)
            self.wrapper.pack_configure(padx=new_padx)
            
            self.root.after(
                SHAKE_STEP_DELAY_MS,
                lambda: shake_step(step_index + 1)
            )
        
        shake_step(0)
    
    def _restore_normal_state(self, original_padx: int) -> None:
        """恢复正常状态
        
        Args:
            original_padx: 原始padx值
        """
        if self.wrapper:
            self.wrapper.pack_configure(padx=original_padx)
        
        self.root.after(
            SHAKE_COLOR_RESTORE_DELAY_MS,
            lambda: self.target_widget.config(style=self.normal_style)
        )

