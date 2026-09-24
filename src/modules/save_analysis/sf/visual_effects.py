"""视觉效果工具模块

提供各种视觉效果和动画功能，包括颜色处理、进度环绘制、文本换行等
"""

import tkinter as tk
import math
import time
import random
import string
from typing import Callable, Optional

from src.utils.styles import ease_out_cubic


def interpolate_color(color1: str, color2: str, factor: float) -> str:
    """在两个颜色之间进行线性插值
    
    Args:
        color1: 起始颜色（hex格式，如 "#RRGGBB"）
        color2: 结束颜色（hex格式）
        factor: 插值因子（0.0 = color1, 1.0 = color2）
        
    Returns:
        插值后的颜色（hex格式）
    """
    r1 = int(color1[1:3], 16)
    g1 = int(color1[3:5], 16)
    b1 = int(color1[5:7], 16)
    
    r2 = int(color2[1:3], 16)
    g2 = int(color2[3:5], 16)
    b2 = int(color2[5:7], 16)
    
    r = int(r1 + (r2 - r1) * factor)
    g = int(g1 + (g2 - g1) * factor)
    b = int(b1 + (b2 - b1) * factor)
    
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    
    return f"#{r:02x}{g:02x}{b:02x}"


def lighten_color(color: str, factor: float = 0.3) -> str:
    """将颜色变浅（用于发光效果）
    
    Args:
        color: 原始颜色（hex格式）
        factor: 变浅程度（0.0 = 不变, 1.0 = 纯白）
        
    Returns:
        变浅后的颜色（hex格式）
    """
    return interpolate_color(color, "#FFFFFF", factor)


def draw_progress_ring(
    canvas: tk.Canvas,
    center_x: int,
    center_y: int,
    radius: int,
    line_width: int,
    current_percent: float,
    progress_color: str,
    tag: str = "progress",
    skip_full_highlight: bool = False
) -> None:
    """绘制进度圆环
    
    Args:
        canvas: tkinter Canvas对象
        center_x: 圆心X坐标
        center_y: 圆心Y坐标
        radius: 半径
        line_width: 线宽
        current_percent: 当前百分比（0-100）
        progress_color: 进度主颜色
        tag: 用于标记进度元素的tag，方便清除
        skip_full_highlight: 100%时是否跳过整体高亮（用于庆祝动画前）
    """
    rounded_percent = round(current_percent)
    
    if rounded_percent <= 0:
        canvas.delete(tag)
        canvas.delete(f"{tag}_glow")
        canvas.delete(f"{tag}_highlight")
        return
    
    # 不道为什么-360会直接导致圆环消失，故359.9，视觉效果无差别
    if rounded_percent >= 100:
        extent = -359.9
    else:
        extent = -(current_percent / 100) * 360
    
    is_complete = rounded_percent >= 100 and not skip_full_highlight
    highlight_color = lighten_color(progress_color, 0.35)
    arc_color = highlight_color if is_complete else progress_color
    
    main_arc_tag = f"{tag}_arc"
    glow_arc_tag = f"{tag}_glow_arc"
    
    main_bbox = (
        center_x - radius,
        center_y - radius,
        center_x + radius,
        center_y + radius
    )
    
    existing_main = canvas.find_withtag(main_arc_tag)
    existing_glow = canvas.find_withtag(glow_arc_tag)
    
    glow_width = line_width + 6
    glow_color = lighten_color(arc_color, 0.65)
    glow_bbox = main_bbox
    
    if existing_glow:
        canvas.itemconfig(existing_glow[0], extent=extent, outline=glow_color)
    else:
        canvas.create_arc(
            *glow_bbox,
            start=90,
            extent=extent,
            style=tk.ARC,
            outline=glow_color,
            width=glow_width,
            tags=(f"{tag}_glow", glow_arc_tag)
        )
    
    if existing_main:
        canvas.itemconfig(existing_main[0], extent=extent, outline=arc_color)
    else:
        canvas.create_arc(
            *main_bbox,
            start=90,
            extent=extent,
            style=tk.ARC,
            outline=arc_color,
            width=line_width,
            tags=(tag, main_arc_tag)
        )
    
    highlight_tag = f"{tag}_highlight"
    canvas.delete(highlight_tag)
    
    if not is_complete and rounded_percent > 0:
        highlight_segments = min(8, rounded_percent)
        angle_per_segment = 360 / 100
        num_segments = min(rounded_percent, 99)
        
        for i in range(max(0, num_segments - highlight_segments), num_segments):
            segments_from_end = num_segments - 1 - i
            highlight_factor = 1 - (segments_from_end / highlight_segments)
            segment_color = interpolate_color(progress_color, highlight_color, highlight_factor)
            
            start_angle = 90 - (i * angle_per_segment)
            end_angle = 90 - ((i + 1) * angle_per_segment)
            
            start_angle_rad = math.radians(start_angle)
            end_angle_rad = math.radians(end_angle)
            
            start_x = center_x + radius * math.cos(start_angle_rad)
            start_y = center_y - radius * math.sin(start_angle_rad)
            end_x = center_x + radius * math.cos(end_angle_rad)
            end_y = center_y - radius * math.sin(end_angle_rad)
            
            canvas.create_line(
                start_x, start_y,
                end_x, end_y,
                fill=segment_color,
                width=line_width,
                capstyle=tk.ROUND,
                tags=highlight_tag
            )


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
        pass


def animate_completion_celebration(
    canvas: tk.Canvas,
    center_x: int,
    center_y: int,
    radius: int,
    line_width: int,
    progress_color: str,
    window: tk.Widget,
    draw_func: Callable
) -> None:
    """100%达成时的庆祝动画：高亮从末端逐渐蔓延到整个环
    
    Args:
        canvas: tkinter Canvas对象
        center_x: 圆心X坐标
        center_y: 圆心Y坐标
        radius: 半径
        line_width: 线宽
        progress_color: 进度颜色
        window: 窗口对象，用于调用after方法
        draw_func: 绘制函数，用于绘制进度环
    """
    if not _is_widget_valid(canvas) or not _is_widget_valid(window):
        return
    
    if hasattr(canvas, '_celebration_job') and canvas._celebration_job:
        _safe_after_cancel(window, canvas._celebration_job)
        canvas._celebration_job = None
    
    animation_duration = 0.6
    animation_start_time = time.time()
    highlight_color = lighten_color(progress_color, 0.35)
    total_segments = 99
    angle_per_segment = 360 / 100
    initial_highlight_segments = 8
    
    try:
        canvas.delete("progress")
        canvas.delete("progress_glow")
        canvas.delete("progress_highlight")
        canvas.delete("celebration_base")
        canvas.delete("celebration_highlight")
        canvas.delete("celebration_glow")
    except (tk.TclError, RuntimeError):
        return
    
    main_bbox = (
        center_x - radius,
        center_y - radius,
        center_x + radius,
        center_y + radius
    )
    
    try:
        base_glow_color = lighten_color(progress_color, 0.65)
        canvas.create_arc(
            *main_bbox,
            start=90,
            extent=-356.4,
            style=tk.ARC,
            outline=base_glow_color,
            width=line_width + 6,
            tags="celebration_glow"
        )
        canvas.create_arc(
            *main_bbox,
            start=90,
            extent=-356.4,
            style=tk.ARC,
            outline=progress_color,
            width=line_width,
            tags="celebration_base"
        )
        
        highlight_glow_color = lighten_color(highlight_color, 0.65)
        highlight_glow_id = canvas.create_arc(
            *main_bbox,
            start=90,
            extent=0,
            style=tk.ARC,
            outline=highlight_glow_color,
            width=line_width + 6,
            tags="celebration_highlight_glow"
        )
        highlight_arc_id = canvas.create_arc(
            *main_bbox,
            start=90,
            extent=0,
            style=tk.ARC,
            outline=highlight_color,
            width=line_width,
            tags="celebration_highlight"
        )
    except (tk.TclError, RuntimeError):
        return
    
    def animate_spread() -> None:
        if not _is_widget_valid(window) or not _is_widget_valid(canvas):
            return
        
        elapsed = time.time() - animation_start_time
        
        if elapsed >= animation_duration:
            if not _is_widget_valid(canvas):
                return
            try:
                canvas.delete("celebration_base")
                canvas.delete("celebration_highlight")
                canvas.delete("celebration_glow")
                canvas.delete("celebration_highlight_glow")
                draw_func(
                    canvas, center_x, center_y, radius, line_width,
                    100, progress_color, tag="progress"
                )
                canvas._celebration_job = None
            except (tk.TclError, RuntimeError):
                pass
            return
        
        progress = elapsed / animation_duration
        eased_progress = ease_out_cubic(progress)
        
        current_highlight_count = initial_highlight_segments + int(
            (total_segments - initial_highlight_segments) * eased_progress
        )
        highlight_extent = -(current_highlight_count * angle_per_segment)
        
        if not _is_widget_valid(canvas):
            return
        
        try:
            canvas.itemconfig(highlight_glow_id, extent=highlight_extent)
            canvas.itemconfig(highlight_arc_id, extent=highlight_extent)
            
            if _is_widget_valid(window):
                canvas._celebration_job = window.after(20, animate_spread)
        except (tk.TclError, RuntimeError):
            pass
    
    if _is_widget_valid(window):
        try:
            animate_spread()
        except (tk.TclError, RuntimeError):
            pass


def generate_gibberish_text(original_text: str) -> str:
    """生成乱码文本，将20-50%的字符替换为随机乱码
    
    Args:
        original_text: 原始文本
        
    Returns:
        乱码文本
    """
    if not original_text:
        return original_text
    
    replace_ratio = random.uniform(0.2, 0.5)
    num_replace = max(1, int(len(original_text) * replace_ratio))
    
    positions_to_replace = random.sample(
        range(len(original_text)),
        min(num_replace, len(original_text))
    )
    
    result = list(original_text)
    printable_chars = string.printable
    
    for pos in positions_to_replace:
        result[pos] = random.choice(printable_chars)
    
    return ''.join(result)


def create_rounded_rect(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    **kwargs
) -> int:
    """在Canvas上绘制圆角矩形
    
    Args:
        canvas: tkinter Canvas对象
        x1: 左上角X坐标
        y1: 左上角Y坐标
        x2: 右下角X坐标
        y2: 右下角Y坐标
        radius: 圆角半径
        **kwargs: 传递给create_polygon的其他参数
        
    Returns:
        创建的图形ID
    """
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
        x1 + radius, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def wrap_text(text: str, font, max_width: int, canvas: tk.Canvas) -> list:
    """计算文本换行，返回行列表
    
    Args:
        text: 要换行的文本
        font: 字体对象
        max_width: 最大宽度
        canvas: tkinter Canvas对象（用于测量文本宽度）
        
    Returns:
        换行后的行列表
    """
    lines = []
    current_line = ""
    
    for char in text:
        test_line = current_line + char
        temp_id = canvas.create_text(0, 0, text=test_line, font=font, anchor="nw")
        bbox = canvas.bbox(temp_id)
        canvas.delete(temp_id)
        
        if bbox and (bbox[2] - bbox[0]) > max_width:
            if current_line:
                lines.append(current_line)
            current_line = char
        else:
            current_line = test_line
    
    if current_line:
        lines.append(current_line)
    
    return lines if lines else [text]
