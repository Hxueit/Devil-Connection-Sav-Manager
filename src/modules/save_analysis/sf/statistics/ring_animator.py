"""环形动画模块

提供贴纸环形图的动画功能
"""

import logging
import time
import tkinter as tk
from typing import Optional

import customtkinter as ctk

from src.utils.styles import ease_out_cubic
from ..visual_effects import draw_progress_ring, animate_completion_celebration
from .constants import (
    RING_RADIUS,
    RING_LINE_WIDTH,
    ANIMATION_DURATION_SECONDS,
    ANIMATION_FRAME_INTERVAL_MS,
    BACKGROUND_RING_OFFSETS,
)

logger = logging.getLogger(__name__)

BACKGROUND_RING_COLOR: str = "#e0e0e0"


def _is_widget_valid(widget: Optional[tk.Widget]) -> bool:
    """检查widget是否有效
    
    Args:
        widget: 要检查的widget
        
    Returns:
        widget是否有效
    """
    if widget is None:
        return False
    try:
        return widget.winfo_exists()
    except (tk.TclError, AttributeError, RuntimeError):
        return False


def _safe_after_cancel(window: tk.Widget, job_id: Optional[int]) -> None:
    """安全取消after调度
    
    Args:
        window: 窗口对象
        job_id: after调度的ID
    """
    if job_id is None:
        return
    if not _is_widget_valid(window):
        return
    try:
        window.after_cancel(job_id)
    except (tk.TclError, ValueError, AttributeError, RuntimeError):
        logger.debug(f"Failed to cancel after job {job_id}")


def draw_background_ring(
    canvas: ctk.CTkCanvas,
    center_x: int,
    center_y: int
) -> None:
    """绘制背景环
    
    Args:
        canvas: Canvas对象
        center_x: 中心X坐标
        center_y: 中心Y坐标
    """
    if not _is_widget_valid(canvas):
        return
    
    try:
        canvas.delete("background_ring")
        for offset, width in BACKGROUND_RING_OFFSETS:
            canvas.create_oval(
                center_x - RING_RADIUS - offset,
                center_y - RING_RADIUS - offset,
                center_x + RING_RADIUS + offset,
                center_y + RING_RADIUS + offset,
                outline=BACKGROUND_RING_COLOR,
                width=int(width),
                tags="background_ring"
            )
    except (tk.TclError, AttributeError) as e:
        logger.debug(f"Error drawing background ring: {e}")


def start_ring_animation(
    window: tk.Widget,
    canvas: ctk.CTkCanvas,
    center_x: int,
    center_y: int,
    target_percent: float,
    progress_color: str,
    percent_text_id: int
) -> None:
    """启动环形图动画
    
    Args:
        window: 窗口对象（用于after调用）
        canvas: Canvas对象
        center_x: 中心X坐标
        center_y: 中心Y坐标
        target_percent: 目标百分比
        progress_color: 进度颜色
        percent_text_id: 百分比文本ID
    """
    if not _is_widget_valid(canvas) or not _is_widget_valid(window):
        return
    
    animation_start_time = time.time()
    
    if hasattr(canvas, '_animation_job') and canvas._animation_job:
        _safe_after_cancel(window, canvas._animation_job)
        canvas._animation_job = None
    
    def animate_progress() -> None:
        if not _is_widget_valid(window) or not _is_widget_valid(canvas):
            return
        
        elapsed = time.time() - animation_start_time
        progress = min(elapsed / ANIMATION_DURATION_SECONDS, 1.0)
        eased_progress = ease_out_cubic(progress)
        current_percent = target_percent * eased_progress
        
        if not _is_widget_valid(canvas):
            return
        
        try:
            draw_progress_ring(
                canvas, center_x, center_y, RING_RADIUS, RING_LINE_WIDTH,
                current_percent, progress_color, tag="progress",
                skip_full_highlight=(target_percent >= 100)
            )
            canvas.itemconfig(percent_text_id, text=f"{current_percent:.1f}%")
        except (tk.TclError, AttributeError, RuntimeError):
            return
        
        if progress < 1.0:
            if _is_widget_valid(window):
                try:
                    canvas._animation_job = window.after(
                        ANIMATION_FRAME_INTERVAL_MS, animate_progress
                    )
                except (tk.TclError, RuntimeError):
                    pass
        else:
            if not _is_widget_valid(canvas):
                return
            
            try:
                canvas.itemconfig(percent_text_id, text=f"{target_percent:.1f}%")
                canvas._animation_job = None
                
                if target_percent >= 100:
                    draw_progress_ring(
                        canvas, center_x, center_y, RING_RADIUS, RING_LINE_WIDTH,
                        target_percent, progress_color, tag="progress",
                        skip_full_highlight=True
                    )
                    if _is_widget_valid(window) and _is_widget_valid(canvas):
                        animate_completion_celebration(
                            canvas, center_x, center_y,
                            RING_RADIUS, RING_LINE_WIDTH, progress_color,
                            window, draw_progress_ring
                        )
                else:
                    draw_progress_ring(
                        canvas, center_x, center_y, RING_RADIUS, RING_LINE_WIDTH,
                        target_percent, progress_color, tag="progress"
                    )
            except (tk.TclError, AttributeError, RuntimeError):
                pass
    
    if _is_widget_valid(window):
        try:
            window.after_idle(animate_progress)
        except (tk.TclError, RuntimeError):
            pass
