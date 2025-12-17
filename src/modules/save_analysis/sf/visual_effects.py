"""视觉效果工具模块

提供各种视觉效果和动画功能，包括颜色处理、进度环绘制、文本换行等。
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


def draw_progress_ring(canvas: tk.Canvas, center_x: int, center_y: int, radius: int, 
                       line_width: int, current_percent: float, progress_color: str, 
                       tag: str = "progress", skip_full_highlight: bool = False):
    """绘制进度圆环（支持动画、末端高亮和发光效果）
    
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
    canvas.delete(tag)
    canvas.delete(f"{tag}_glow")
    
    rounded_percent = round(current_percent)
    if rounded_percent >= 100:
        num_segments = 99
    else:
        num_segments = rounded_percent
    
    if num_segments <= 0:
        return
    
    angle_per_segment = 360 / 100
    
    is_complete = rounded_percent >= 100 and not skip_full_highlight
    highlight_color = lighten_color(progress_color, 0.35)
    highlight_segments = 8
    
    if is_complete:
        glow_layers = [
            (8, 0.75),
            (5, 0.55),
            (3, 0.35),
        ]
    else:
        glow_layers = [
            (6, 0.85),
            (4, 0.70),
            (2, 0.50),
        ]
    
    for extra_width, lighten_factor in glow_layers:
        glow_width = line_width + extra_width
        for i in range(num_segments):
            if is_complete:
                glow_color = lighten_color(highlight_color, lighten_factor)
            else:
                segments_from_end = num_segments - 1 - i
                if segments_from_end < highlight_segments:
                    highlight_factor = 1 - (segments_from_end / highlight_segments)
                    base_color = interpolate_color(progress_color, highlight_color, highlight_factor)
                    glow_color = lighten_color(base_color, lighten_factor)
                else:
                    glow_color = lighten_color(progress_color, lighten_factor)
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
                fill=glow_color,
                width=int(glow_width),
                capstyle=tk.ROUND,
                tags=f"{tag}_glow"
            )
    
    for offset, width in [(0, line_width), (0.5, line_width - 1), (1, max(1, line_width - 2))]:
        offset_radius = radius + offset
        
        for i in range(num_segments):
            if is_complete:
                segment_color = highlight_color
            else:
                segments_from_end = num_segments - 1 - i
                if segments_from_end < highlight_segments:
                    highlight_factor = 1 - (segments_from_end / highlight_segments)
                    segment_color = interpolate_color(progress_color, highlight_color, highlight_factor)
                else:
                    segment_color = progress_color
            
            start_angle = 90 - (i * angle_per_segment)
            end_angle = 90 - ((i + 1) * angle_per_segment)
            
            start_angle_rad = math.radians(start_angle)
            end_angle_rad = math.radians(end_angle)
            
            start_x = center_x + offset_radius * math.cos(start_angle_rad)
            start_y = center_y - offset_radius * math.sin(start_angle_rad)
            end_x = center_x + offset_radius * math.cos(end_angle_rad)
            end_y = center_y - offset_radius * math.sin(end_angle_rad)
            
            canvas.create_line(
                start_x, start_y,
                end_x, end_y,
                fill=segment_color,
                width=int(width),
                capstyle=tk.ROUND,
                tags=tag
            )


def animate_completion_celebration(canvas: tk.Canvas, center_x: int, center_y: int, 
                                  radius: int, line_width: int, progress_color: str,
                                  window: tk.Widget, draw_func: Callable):
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
    if hasattr(canvas, '_celebration_job') and canvas._celebration_job:
        window.after_cancel(canvas._celebration_job)
    
    animation_duration = 0.6
    animation_start_time = time.time()
    highlight_color = lighten_color(progress_color, 0.35)
    total_segments = 99
    angle_per_segment = 360 / 100
    initial_highlight_segments = 8
    
    def animate_spread():
        """蔓延动画循环"""
        if not canvas.winfo_exists():
            return
        
        elapsed = time.time() - animation_start_time
        
        if elapsed >= animation_duration:
            draw_func(
                canvas, center_x, center_y, radius, line_width,
                100, progress_color, tag="progress"
            )
            canvas._celebration_job = None
            return
        
        progress = elapsed / animation_duration
        eased_progress = ease_out_cubic(progress)
        
        current_highlight_count = initial_highlight_segments + int(
            (total_segments - initial_highlight_segments) * eased_progress
        )
        
        canvas.delete("progress")
        canvas.delete("progress_glow")
        
        glow_layers = [
            (8, 0.75),
            (5, 0.55),
            (3, 0.35),
        ]
        
        for extra_width, lighten_factor in glow_layers:
            glow_width = line_width + extra_width
            for i in range(total_segments):
                segments_from_end = total_segments - 1 - i
                is_highlighted = (i < current_highlight_count) or (segments_from_end < initial_highlight_segments)
                
                if is_highlighted:
                    glow_color = lighten_color(highlight_color, lighten_factor)
                else:
                    glow_color = lighten_color(progress_color, lighten_factor)
                
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
                    fill=glow_color,
                    width=int(glow_width),
                    capstyle=tk.ROUND,
                    tags="progress_glow"
                )
        
        for offset, width in [(0, line_width), (0.5, line_width - 1), (1, max(1, line_width - 2))]:
            offset_radius = radius + offset
            
            for i in range(total_segments):
                segments_from_end = total_segments - 1 - i
                is_highlighted = (i < current_highlight_count) or (segments_from_end < initial_highlight_segments)
                
                if is_highlighted:
                    segment_color = highlight_color
                else:
                    segment_color = progress_color
                
                start_angle = 90 - (i * angle_per_segment)
                end_angle = 90 - ((i + 1) * angle_per_segment)
                
                start_angle_rad = math.radians(start_angle)
                end_angle_rad = math.radians(end_angle)
                
                start_x = center_x + offset_radius * math.cos(start_angle_rad)
                start_y = center_y - offset_radius * math.sin(start_angle_rad)
                end_x = center_x + offset_radius * math.cos(end_angle_rad)
                end_y = center_y - offset_radius * math.sin(end_angle_rad)
                
                canvas.create_line(
                    start_x, start_y,
                    end_x, end_y,
                    fill=segment_color,
                    width=int(width),
                    capstyle=tk.ROUND,
                    tags="progress"
                )
        
        canvas._celebration_job = window.after(16, animate_spread)
    
    animate_spread()


def generate_gibberish_text(original_text: str) -> str:
    """生成乱码文本，将20-50%的字符替换为随机乱码
    
    Args:
        original_text: 原始文本
        
    Returns:
        乱码文本
    """
    if not original_text:
        return original_text
    
    # 随机选择替换比例（20-50%）
    replace_ratio = random.uniform(0.2, 0.5)
    num_replace = max(1, int(len(original_text) * replace_ratio))
    
    # 随机选择要替换的位置
    positions_to_replace = random.sample(range(len(original_text)), min(num_replace, len(original_text)))
    
    # 生成乱码文本
    result = list(original_text)
    printable_chars = string.printable  # 包含所有可打印字符
    
    for pos in positions_to_replace:
        # 替换为随机可打印字符
        result[pos] = random.choice(printable_chars)
    
    return ''.join(result)


def create_rounded_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, 
                        radius: float, **kwargs) -> int:
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
    words = text
    lines = []
    current_line = ""
    
    for char in words:
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

