"""统计面板模块

负责创建和更新右侧统计面板，包括贴纸环形图、MP显示、判定统计等。
"""

import tkinter as tk
from tkinter import font as tkfont
import customtkinter as ctk
import os
import urllib.parse
import time
from typing import Dict, Any, Optional, Callable

from src.utils.styles import Colors, get_cjk_font, ease_out_cubic
from .visual_effects import draw_progress_ring, animate_completion_celebration, generate_gibberish_text


class StatisticsPanel:
    """统计面板管理器"""
    
    def __init__(self, window: tk.Widget, storage_dir: str, t_func: Callable[[str], str]):
        """初始化统计面板
        
        Args:
            window: 主窗口对象
            storage_dir: 存档目录
            t_func: 翻译函数
        """
        self.window = window
        self.storage_dir = storage_dir
        self.t = t_func
        self._stats_container = None
        self._stats_widgets = {}
        self._gibberish_update_job = None
        self._original_texts = {}
        self._gibberish_widgets = []
    
    def create(self, parent: tk.Widget) -> tk.Widget:
        """创建统计面板容器
        
        Args:
            parent: 父容器
            
        Returns:
            统计面板容器
        """
        if self._stats_container and self._stats_container.winfo_exists():
            self._stats_container.destroy()
        self._stats_container = None
        
        self._stats_widgets.clear()
        
        stats_container = tk.Frame(parent, bg=Colors.WHITE)
        stats_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        self._stats_container = stats_container
        self._gibberish_update_job = None
        self._original_texts = {}
        self._gibberish_widgets = []
        
        placeholder = tk.Label(
            stats_container,
            text=self.t("no_save_data"),
            font=get_cjk_font(12),
            bg=Colors.WHITE
        )
        placeholder.pack(pady=50)
        
        return stats_container
    
    def update(self, parent: tk.Widget, save_data: Dict[str, Any]) -> None:
        """更新统计面板内容
        
        Args:
            parent: 父容器
            save_data: 存档数据
        """
        if not parent or not parent.winfo_exists():
            self._stats_widgets.clear()
            return
        
        if self._gibberish_update_job is not None:
            self.window.after_cancel(self._gibberish_update_job)
            self._gibberish_update_job = None
        
        if not self._gibberish_widgets:
            self._gibberish_widgets = []
        if not self._original_texts:
            self._original_texts = {}
        
        if 'sticker_canvas' in self._stats_widgets:
            sticker_canvas = self._stats_widgets.get('sticker_canvas')
            if sticker_canvas and sticker_canvas.winfo_exists():
                self.update_incremental(parent, save_data)
                return
            self._stats_widgets.clear()
        
        for widget in parent.winfo_children():
            widget.destroy()
        
        kill = save_data.get("kill", None)
        killed = save_data.get("killed", None)
        
        is_fanatic_route = (
            (kill is not None and kill == 1) or
            (killed is not None and killed == 1)
        )
        stickers = set(save_data.get("sticker", []))
        total_stickers = 132
        collected_stickers = len(stickers)
        stickers_percent = (collected_stickers / total_stickers * 100) if total_stickers > 0 else 0
        
        whole_total_mp = save_data.get("wholeTotalMP", 0)
        judge_counts = save_data.get("judgeCounts", {})
        perfect = judge_counts.get("perfect", 0)
        good = judge_counts.get("good", 0)
        bad = judge_counts.get("bad", 0)
        
        sticker_frame = tk.Frame(parent, bg=Colors.WHITE)
        sticker_frame.pack(pady=(0, 20))
        
        canvas_size = 280
        sticker_canvas = ctk.CTkCanvas(
            sticker_frame,
            width=canvas_size,
            height=canvas_size,
            bg=Colors.WHITE,
            highlightthickness=0
        )
        sticker_canvas.pack()
        
        TITLE_Y_OFFSET = -30
        PERCENT_Y_OFFSET = 2
        COUNT_Y_OFFSET = 40
        
        center_x, center_y = canvas_size // 2, canvas_size // 2
        radius = 100
        line_width = 30
        
        sticker_canvas.delete("background_ring")
        for offset, width in [(0, line_width + 2), (0.5, line_width + 1), (1, line_width)]:
            sticker_canvas.create_oval(
                center_x - radius - offset, center_y - radius - offset,
                center_x + radius + offset, center_y + radius + offset,
                outline="#e0e0e0",
                width=int(width),
                tags="background_ring"
            )
        
        if is_fanatic_route:
            progress_color = "#BF0204"
        elif stickers_percent == 100:
            progress_color = "#FFD54F"
        elif stickers_percent >= 95:
            progress_color = "#81C784"
        elif stickers_percent >= 90:
            progress_color = "#4DB6AC"
        elif stickers_percent >= 75:
            progress_color = "#4FC3F7"
        else:
            progress_color = "#64B5F6"
        
        sticker_canvas.create_text(
            center_x, center_y + TITLE_Y_OFFSET,
            text=self.t('stickers_statistics'),
            font=get_cjk_font(12, "bold"),
            fill=Colors.TEXT_DARK,
            tags="title_text"
        )
        
        percent_text_id = sticker_canvas.create_text(
            center_x, center_y + PERCENT_Y_OFFSET,
            text="0.0%",
            font=get_cjk_font(20, "bold"),
            fill=Colors.TEXT_DARK,
            tags="percent_text"
        )
        
        target_percent = stickers_percent
        animation_duration = 1.5
        animation_start_time = time.time()
        
        if hasattr(sticker_canvas, '_animation_job'):
            if sticker_canvas._animation_job:
                self.window.after_cancel(sticker_canvas._animation_job)
        
        anim_center_x = center_x
        anim_center_y = center_y
        anim_radius = radius
        anim_line_width = line_width
        anim_progress_color = progress_color
        
        def animate_progress():
            if not sticker_canvas.winfo_exists():
                return
            
            elapsed = time.time() - animation_start_time
            progress = min(elapsed / animation_duration, 1.0)
            eased_progress = ease_out_cubic(progress)
            current_percent = target_percent * eased_progress
            
            draw_progress_ring(
                sticker_canvas, anim_center_x, anim_center_y, anim_radius, anim_line_width,
                current_percent, anim_progress_color, tag="progress",
                skip_full_highlight=(target_percent >= 100)
            )
            
            sticker_canvas.itemconfig(
                percent_text_id,
                text=f"{current_percent:.1f}%"
            )
            
            if progress < 1.0:
                sticker_canvas._animation_job = self.window.after(16, animate_progress)
            else:
                sticker_canvas.itemconfig(
                    percent_text_id,
                    text=f"{target_percent:.1f}%"
                )
                sticker_canvas._animation_job = None
                
                if target_percent >= 100:
                    draw_progress_ring(
                        sticker_canvas, anim_center_x, anim_center_y, anim_radius, anim_line_width,
                        target_percent, anim_progress_color, tag="progress", skip_full_highlight=True
                    )
                    animate_completion_celebration(
                        sticker_canvas, anim_center_x, anim_center_y, 
                        anim_radius, anim_line_width, anim_progress_color,
                        self.window, draw_progress_ring
                    )
                else:
                    draw_progress_ring(
                        sticker_canvas, anim_center_x, anim_center_y, anim_radius, anim_line_width,
                        target_percent, anim_progress_color, tag="progress"
                    )
        
        animate_progress()
        
        sticker_canvas.create_text(
            center_x, center_y + COUNT_Y_OFFSET,
            text=f"{collected_stickers}/{total_stickers}",
            font=get_cjk_font(11),
            fill=Colors.TEXT_MUTED,
            tags="count_text"
        )
        
        mp_frame = tk.Frame(parent, bg=Colors.WHITE)
        mp_frame.pack(pady=(0, 15))
        
        mp_label_title = tk.Label(
            mp_frame,
            text=self.t("total_mp"),
            font=get_cjk_font(12),
            fg=Colors.TEXT_MUTED,
            bg=Colors.WHITE
        )
        mp_label_title.pack()
        
        mp_label_value = tk.Label(
            mp_frame,
            text=f"{whole_total_mp:,}",
            font=get_cjk_font(32, "bold"),
            fg=Colors.TEXT_INFO,
            bg=Colors.WHITE
        )
        mp_label_value.pack()
        
        judge_frame = tk.Frame(parent, bg=Colors.WHITE)
        judge_frame.pack(pady=(30, 0))
        
        judge_canvas = ctk.CTkCanvas(
            judge_frame,
            height=25,
            bg=Colors.WHITE,
            highlightthickness=0
        )
        judge_canvas.pack()
        
        perfect_text = f"{perfect:,}"
        good_text = f"{good:,}"
        bad_text = f"{bad:,}"
        full_text = f"{perfect_text} - {good_text} - {bad_text}"
        
        temp_font = get_cjk_font(10)
        if isinstance(temp_font, tuple):
            font_obj = tkfont.Font(family=temp_font[0], size=temp_font[1])
        else:
            font_obj = tkfont.Font(font=temp_font)
        
        text_width = font_obj.measure(full_text)
        canvas_width = max(250, text_width + 20)
        judge_canvas.config(width=canvas_width)
        
        center_x_judge = canvas_width // 2
        current_x = center_x_judge - text_width // 2
        
        perfect_width = font_obj.measure(perfect_text)
        judge_canvas.create_text(
            current_x + perfect_width // 2, 12,
            text=perfect_text,
            font=get_cjk_font(10),
            fill="#CC6DAE",
            anchor="center"
        )
        current_x += perfect_width + font_obj.measure(" - ")
        
        good_width = font_obj.measure(good_text)
        judge_canvas.create_text(
            current_x + good_width // 2, 12,
            text=good_text,
            font=get_cjk_font(10),
            fill="#F5CE88",
            anchor="center"
        )
        current_x += good_width + font_obj.measure(" - ")
        
        bad_width = font_obj.measure(bad_text)
        judge_canvas.create_text(
            current_x + bad_width // 2, 12,
            text=bad_text,
            font=get_cjk_font(10),
            fill="#6DB7AB",
            anchor="center"
        )
        
        sep_width = font_obj.measure(" - ")
        sep1_x = center_x_judge - text_width // 2 + perfect_width
        sep2_x = sep1_x + sep_width + good_width
        judge_canvas.create_text(sep1_x + sep_width // 2, 12, text=" - ", font=get_cjk_font(10), fill=Colors.TEXT_MUTED, anchor="center")
        judge_canvas.create_text(sep2_x + sep_width // 2, 12, text=" - ", font=get_cjk_font(10), fill=Colors.TEXT_MUTED, anchor="center")
        
        neo_label = None
        neo_original_text = None
        neo_sav_path = os.path.join(self.storage_dir, 'NEO.sav')
        if os.path.exists(neo_sav_path):
            try:
                with open(neo_sav_path, 'r', encoding='utf-8') as f:
                    encoded_content = f.read().strip()
                
                decoded_content = urllib.parse.unquote(encoded_content)
                
                neo_frame = tk.Frame(parent, bg=Colors.WHITE)
                neo_frame.pack(pady=(55, 0))
                
                if decoded_content == '"キミたちに永遠の祝福を"':
                    neo_text = self.t("good_neo")
                    text_color = "#FFEB9E"
                elif decoded_content == '"オマエに永遠の制裁を"':
                    neo_text = self.t("bad_neo")
                    text_color = "#FF0000"
                else:
                    neo_text = decoded_content
                    text_color = "#000000"
                
                neo_label = tk.Label(
                    neo_frame,
                    text=neo_text,
                    font=get_cjk_font(14),
                    fg=text_color,
                    bg=Colors.WHITE,
                    wraplength=200
                )
                neo_label.pack()
                neo_original_text = neo_text
                
                if is_fanatic_route:
                    dark_red_color = "#8b0000"
                    neo_label.config(fg=dark_red_color)
            except Exception:
                pass
        
        if is_fanatic_route:
            self._setup_gibberish_effect(
                sticker_canvas, center_x, center_y, stickers_percent,
                collected_stickers, total_stickers, mp_label_title,
                mp_label_value, whole_total_mp, judge_canvas, perfect,
                good, bad, canvas_width, font_obj, center_x_judge,
                text_width, neo_label, neo_original_text
            )
        
        self._stats_widgets['sticker_canvas'] = sticker_canvas
        self._stats_widgets['sticker_frame'] = sticker_frame
        self._stats_widgets['mp_label_title'] = mp_label_title
        self._stats_widgets['mp_label_value'] = mp_label_value
        self._stats_widgets['judge_canvas'] = judge_canvas
        self._stats_widgets['judge_frame'] = judge_frame
        if neo_label is not None:
            self._stats_widgets['neo_label'] = neo_label
            self._stats_widgets['neo_frame'] = neo_frame
        self._stats_widgets['percent_text_id'] = percent_text_id
        self._stats_widgets['canvas_size'] = canvas_size
        self._stats_widgets['center_x'] = center_x
        self._stats_widgets['center_y'] = center_y
        self._stats_widgets['radius'] = radius
        self._stats_widgets['line_width'] = line_width
    
    def update_incremental(self, parent: tk.Widget, save_data: Dict[str, Any]) -> None:
        """增量更新统计面板
        
        Args:
            parent: 父容器
            save_data: 存档数据
        """
        kill = save_data.get("kill", None)
        killed = save_data.get("killed", None)
        
        is_fanatic_route = (
            (kill is not None and kill == 1) or
            (killed is not None and killed == 1)
        )
        
        stickers = set(save_data.get("sticker", []))
        total_stickers = 132
        collected_stickers = len(stickers)
        stickers_percent = (collected_stickers / total_stickers * 100) if total_stickers > 0 else 0
        
        whole_total_mp = save_data.get("wholeTotalMP", 0)
        judge_counts = save_data.get("judgeCounts", {})
        perfect = judge_counts.get("perfect", 0)
        good = judge_counts.get("good", 0)
        bad = judge_counts.get("bad", 0)
        
        if not parent:
            self._stats_widgets.clear()
            return
        
        if not parent.winfo_exists():
            self._stats_widgets.clear()
            return
        
        sticker_canvas = self._stats_widgets.get('sticker_canvas')
        mp_label_value = self._stats_widgets.get('mp_label_value')
        judge_canvas = self._stats_widgets.get('judge_canvas')
        percent_text_id = self._stats_widgets.get('percent_text_id')
        radius = self._stats_widgets.get('radius', 70)
        line_width = self._stats_widgets.get('line_width', 20)
        
        widget_invalid = False
        if not sticker_canvas or not sticker_canvas.winfo_exists():
            widget_invalid = True
        elif mp_label_value and not mp_label_value.winfo_exists():
            widget_invalid = True
        elif judge_canvas and not judge_canvas.winfo_exists():
            widget_invalid = True
        
        if widget_invalid:
            self._stats_widgets.clear()
            self.update(parent, save_data)
            return
        
        canvas_width = sticker_canvas.winfo_width()
        canvas_height = sticker_canvas.winfo_height()
        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width = self._stats_widgets.get('canvas_size', 180)
            canvas_height = canvas_width
        center_x = canvas_width // 2
        center_y = canvas_height // 2
        
        if is_fanatic_route:
            progress_color = "#BF0204"
        elif stickers_percent == 100:
            progress_color = "#FFD54F"
        elif stickers_percent >= 95:
            progress_color = "#81C784"
        elif stickers_percent >= 90:
            progress_color = "#4DB6AC"
        elif stickers_percent >= 75:
            progress_color = "#4FC3F7"
        else:
            progress_color = "#64B5F6"
        
        TITLE_Y_OFFSET = -30
        PERCENT_Y_OFFSET = 2
        COUNT_Y_OFFSET = 40
        
        sticker_canvas.delete("progress")
        sticker_canvas.delete("title_text")
        sticker_canvas.delete("percent_text")
        sticker_canvas.delete("count_text")
        
        background_exists = len(sticker_canvas.find_withtag("background_ring")) > 0
        if not background_exists:
            for offset, width in [(0, line_width + 2), (0.5, line_width + 1), (1, line_width)]:
                sticker_canvas.create_oval(
                    center_x - radius - offset, center_y - radius - offset,
                    center_x + radius + offset, center_y + radius + offset,
                    outline="#e0e0e0",
                    width=int(width),
                    tags="background_ring"
                )
        
        sticker_canvas.create_text(
            center_x, center_y + TITLE_Y_OFFSET,
            text=self.t('stickers_statistics'),
            font=get_cjk_font(12, "bold"),
            fill=Colors.TEXT_DARK,
            tags="title_text"
        )
        
        percent_text_id = sticker_canvas.create_text(
            center_x, center_y + PERCENT_Y_OFFSET,
            text="0.0%",
            font=get_cjk_font(20, "bold"),
            fill=Colors.TEXT_DARK,
            tags="percent_text"
        )
        self._stats_widgets['percent_text_id'] = percent_text_id
        
        target_percent = stickers_percent
        animation_duration = 1.5
        animation_start_time = time.time()
        
        if hasattr(sticker_canvas, '_animation_job'):
            if sticker_canvas._animation_job:
                self.window.after_cancel(sticker_canvas._animation_job)
        
        anim_center_x = center_x
        anim_center_y = center_y
        anim_radius = radius
        anim_line_width = line_width
        anim_progress_color = progress_color
        
        def animate_progress():
            if not sticker_canvas.winfo_exists():
                return
            
            elapsed = time.time() - animation_start_time
            progress = min(elapsed / animation_duration, 1.0)
            eased_progress = ease_out_cubic(progress)
            current_percent = target_percent * eased_progress
            
            draw_progress_ring(
                sticker_canvas, anim_center_x, anim_center_y, anim_radius, anim_line_width,
                current_percent, anim_progress_color, tag="progress",
                skip_full_highlight=(target_percent >= 100)
            )
            
            sticker_canvas.itemconfig(
                percent_text_id,
                text=f"{current_percent:.1f}%"
            )
            
            if progress < 1.0:
                sticker_canvas._animation_job = self.window.after(16, animate_progress)
            else:
                sticker_canvas.itemconfig(
                    percent_text_id,
                    text=f"{target_percent:.1f}%"
                )
                sticker_canvas._animation_job = None
                
                if target_percent >= 100:
                    draw_progress_ring(
                        sticker_canvas, anim_center_x, anim_center_y, anim_radius, anim_line_width,
                        target_percent, anim_progress_color, tag="progress", skip_full_highlight=True
                    )
                    animate_completion_celebration(
                        sticker_canvas, anim_center_x, anim_center_y, 
                        anim_radius, anim_line_width, anim_progress_color,
                        self.window, draw_progress_ring
                    )
                else:
                    draw_progress_ring(
                        sticker_canvas, anim_center_x, anim_center_y, anim_radius, anim_line_width,
                        target_percent, anim_progress_color, tag="progress"
                    )
        
        animate_progress()
        
        sticker_canvas.delete("count_text")
        sticker_canvas.create_text(
            center_x, center_y + COUNT_Y_OFFSET,
            text=f"{collected_stickers}/{total_stickers}",
            font=get_cjk_font(11),
            fill=Colors.TEXT_MUTED,
            tags="count_text"
        )
        
        if mp_label_value and mp_label_value.winfo_exists():
            mp_label_value.config(text=f"{whole_total_mp:,}")
        
        if judge_canvas and judge_canvas.winfo_exists():
            judge_canvas.delete("all")
            
            perfect_text = f"{perfect:,}"
            good_text = f"{good:,}"
            bad_text = f"{bad:,}"
            full_text = f"{perfect_text} - {good_text} - {bad_text}"
            
            temp_font = get_cjk_font(10)
            if isinstance(temp_font, tuple):
                font_obj = tkfont.Font(family=temp_font[0], size=temp_font[1])
            else:
                font_obj = tkfont.Font(font=temp_font)
            
            text_width = font_obj.measure(full_text)
            canvas_width = max(250, text_width + 20)
            judge_canvas.config(width=canvas_width)
            
            center_x_judge = canvas_width // 2
            current_x = center_x_judge - text_width // 2
            
            perfect_width = font_obj.measure(perfect_text)
            judge_canvas.create_text(
                current_x + perfect_width // 2, 12,
                text=perfect_text,
                font=get_cjk_font(10),
                fill="#CC6DAE",
                anchor="center"
            )
            current_x += perfect_width + font_obj.measure(" - ")
            
            good_width = font_obj.measure(good_text)
            judge_canvas.create_text(
                current_x + good_width // 2, 12,
                text=good_text,
                font=get_cjk_font(10),
                fill="#F5CE88",
                anchor="center"
            )
            current_x += good_width + font_obj.measure(" - ")
            
            bad_width = font_obj.measure(bad_text)
            judge_canvas.create_text(
                current_x + bad_width // 2, 12,
                text=bad_text,
                font=get_cjk_font(10),
                fill="#6DB7AB",
                anchor="center"
            )
            
            sep_width = font_obj.measure(" - ")
            sep1_x = center_x_judge - text_width // 2 + perfect_width
            sep2_x = sep1_x + sep_width + good_width
            judge_canvas.create_text(sep1_x + sep_width // 2, 12, text=" - ", font=get_cjk_font(10), fill=Colors.TEXT_MUTED, anchor="center")
            judge_canvas.create_text(sep2_x + sep_width // 2, 12, text=" - ", font=get_cjk_font(10), fill=Colors.TEXT_MUTED, anchor="center")
        
        neo_sav_path = os.path.join(self.storage_dir, 'NEO.sav')
        neo_label = self._stats_widgets.get('neo_label')
        neo_text = None
        if os.path.exists(neo_sav_path):
            try:
                with open(neo_sav_path, 'r', encoding='utf-8') as f:
                    encoded_content = f.read().strip()
                
                decoded_content = urllib.parse.unquote(encoded_content)
                
                if decoded_content == '"キミたちに永遠の祝福を"':
                    neo_text = self.t("good_neo")
                    text_color = "#FFEB9E"
                elif decoded_content == '"オマエに永遠の制裁を"':
                    neo_text = self.t("bad_neo")
                    text_color = "#FF0000"
                else:
                    neo_text = decoded_content
                    text_color = "#000000"
                
                if neo_label and neo_label.winfo_exists():
                    neo_label.config(text=neo_text, fg=text_color)
            except Exception:
                pass
        
        if is_fanatic_route:
            self._gibberish_widgets = []
            self._original_texts = {}
        else:
            if self._gibberish_update_job is not None:
                if self._gibberish_update_job:
                    self.window.after_cancel(self._gibberish_update_job)
                self._gibberish_update_job = None
            
            if self._gibberish_widgets:
                for widget_info in self._gibberish_widgets:
                    if widget_info['type'] == 'canvas_text':
                        canvas = widget_info.get('canvas')
                        text_id = widget_info.get('text_id')
                        if canvas and text_id and canvas.winfo_exists():
                            canvas.delete(text_id)
                
                self._gibberish_widgets = []
            self._original_texts = {}
        
        if is_fanatic_route:
            mp_label_title = self._stats_widgets.get('mp_label_title')
            self._setup_gibberish_effect(
                sticker_canvas, center_x, center_y, stickers_percent,
                collected_stickers, total_stickers, mp_label_title,
                mp_label_value, whole_total_mp, judge_canvas, perfect,
                good, bad, canvas_width, font_obj, canvas_width // 2,
                text_width, neo_label, neo_text
            )
    
    def _setup_gibberish_effect(self, sticker_canvas, center_x, center_y, stickers_percent,
                               collected_stickers, total_stickers, mp_label_title,
                               mp_label_value, whole_total_mp, judge_canvas, perfect,
                               good, bad, canvas_width, font_obj, center_x_judge,
                               text_width, neo_label, neo_text):
        """设置乱码效果
        
        Args:
            sticker_canvas: 贴纸canvas
            center_x: 中心X坐标
            center_y: 中心Y坐标
            stickers_percent: 贴纸百分比
            collected_stickers: 已收集贴纸数
            total_stickers: 总贴纸数
            mp_label_title: MP标题标签
            mp_label_value: MP值标签
            whole_total_mp: 总MP值
            judge_canvas: 判定canvas
            perfect: Perfect数量
            good: Good数量
            bad: Bad数量
            canvas_width: Canvas宽度
            font_obj: 字体对象
            center_x_judge: 判定canvas中心X
            text_width: 文本宽度
            neo_label: NEO标签
            neo_text: NEO文本
        """
        dark_red_color = "#8b0000"
        
        all_text_ids = [item for item in sticker_canvas.find_all() if sticker_canvas.type(item) == 'text']
        if len(all_text_ids) >= 3:
            self._gibberish_widgets.append({
                'type': 'canvas_text',
                'canvas': sticker_canvas,
                'text_id': all_text_ids[-3],
                'x': center_x,
                'y': center_y - 20,
                'font': get_cjk_font(12, "bold"),
                'fill': dark_red_color,
                'anchor': 'center',
                'tag': 'title_text'
            })
            self._original_texts[len(self._gibberish_widgets) - 1] = self.t('stickers_statistics')
            
            self._gibberish_widgets.append({
                'type': 'canvas_text',
                'canvas': sticker_canvas,
                'text_id': all_text_ids[-2],
                'x': center_x,
                'y': center_y + 2,
                'font': get_cjk_font(20, "bold"),
                'fill': dark_red_color,
                'anchor': 'center',
                'tag': 'percent_text'
            })
            self._original_texts[len(self._gibberish_widgets) - 1] = f"{stickers_percent:.1f}%"
            
            self._gibberish_widgets.append({
                'type': 'canvas_text',
                'canvas': sticker_canvas,
                'text_id': all_text_ids[-1],
                'x': center_x,
                'y': center_y + 22,
                'font': get_cjk_font(11),
                'fill': dark_red_color,
                'anchor': 'center',
                'tag': 'count_text'
            })
            self._original_texts[len(self._gibberish_widgets) - 1] = f"{collected_stickers}/{total_stickers}"
        
        if mp_label_title:
            self._gibberish_widgets.append({
                'type': 'tk_label',
                'widget': mp_label_title
            })
            self._original_texts[len(self._gibberish_widgets) - 1] = self.t("total_mp")
        
        if mp_label_value:
            self._gibberish_widgets.append({
                'type': 'tk_label',
                'widget': mp_label_value
            })
            self._original_texts[len(self._gibberish_widgets) - 1] = f"{whole_total_mp:,}"
        
        if judge_canvas:
            full_text = f"{perfect:,} - {good:,} - {bad:,}"
            
            self._gibberish_widgets.append({
                'type': 'judge_canvas',
                'canvas': judge_canvas,
                'perfect': perfect,
                'good': good,
                'bad': bad,
                'canvas_width': canvas_width,
                'font_obj': font_obj,
                'center_x': center_x_judge,
                'text_width': text_width
            })
            self._original_texts[len(self._gibberish_widgets) - 1] = full_text
        
        if neo_label and neo_label.winfo_exists() and neo_text:
            self._gibberish_widgets.append({
                'type': 'tk_label',
                'widget': neo_label
            })
            self._original_texts[len(self._gibberish_widgets) - 1] = neo_text
        
        self._update_gibberish_texts()
    
    def _update_gibberish_texts(self) -> None:
        """更新所有文字为乱码效果"""
        if not self._gibberish_widgets:
            return
        
        for idx, widget_info in enumerate(self._gibberish_widgets):
            if idx not in self._original_texts:
                continue
            
            original_text = self._original_texts[idx]
            gibberish_text = generate_gibberish_text(original_text)
            
            if widget_info['type'] == 'canvas_text':
                canvas = widget_info['canvas']
                if canvas and canvas.winfo_exists():
                    text_id = widget_info.get('text_id')
                    if text_id:
                        canvas.delete(text_id)
                    
                    text_tag = widget_info.get('tag', 'gibberish_text')
                    new_text_id = canvas.create_text(
                        widget_info['x'],
                        widget_info['y'],
                        text=gibberish_text,
                        font=widget_info['font'],
                        fill=widget_info['fill'],
                        anchor=widget_info['anchor'],
                        tags=text_tag
                    )
                    widget_info['text_id'] = new_text_id
            
            elif widget_info['type'] == 'tk_label':
                widget = widget_info.get('widget')
                if widget and widget.winfo_exists():
                    dark_red_color = "#8b0000"
                    widget.config(text=gibberish_text, fg=dark_red_color)
            
            elif widget_info['type'] == 'judge_canvas':
                canvas = widget_info['canvas']
                if canvas and canvas.winfo_exists():
                    canvas.delete("all")
                    
                    perfect_text = generate_gibberish_text(f"{widget_info['perfect']:,}")
                    good_text = generate_gibberish_text(f"{widget_info['good']:,}")
                    bad_text = generate_gibberish_text(f"{widget_info['bad']:,}")
                    full_text = f"{perfect_text} - {good_text} - {bad_text}"
                    
                    font_obj = widget_info['font_obj']
                    text_width = font_obj.measure(full_text)
                    center_x = widget_info['canvas_width'] // 2
                    current_x = center_x - text_width // 2
                    
                    dark_red_color = "#8b0000"
                    
                    perfect_width = font_obj.measure(perfect_text)
                    canvas.create_text(
                        current_x + perfect_width // 2, 12,
                        text=perfect_text,
                        font=get_cjk_font(10),
                        fill=dark_red_color,
                        anchor="center"
                    )
                    current_x += perfect_width + font_obj.measure(" - ")
                    
                    good_width = font_obj.measure(good_text)
                    canvas.create_text(
                        current_x + good_width // 2, 12,
                        text=good_text,
                        font=get_cjk_font(10),
                        fill=dark_red_color,
                        anchor="center"
                    )
                    current_x += good_width + font_obj.measure(" - ")
                    
                    bad_width = font_obj.measure(bad_text)
                    canvas.create_text(
                        current_x + bad_width // 2, 12,
                        text=bad_text,
                        font=get_cjk_font(10),
                        fill=dark_red_color,
                        anchor="center"
                    )
                    
                    sep_width = font_obj.measure(" - ")
                    sep1_x = center_x - text_width // 2 + perfect_width
                    sep2_x = sep1_x + sep_width + good_width
                    canvas.create_text(sep1_x + sep_width // 2, 12, text=" - ", font=get_cjk_font(10), fill=dark_red_color, anchor="center")
                    canvas.create_text(sep2_x + sep_width // 2, 12, text=" - ", font=get_cjk_font(10), fill=dark_red_color, anchor="center")
        
        self._gibberish_update_job = self.window.after(150, self._update_gibberish_texts)

