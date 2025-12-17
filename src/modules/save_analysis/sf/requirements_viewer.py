"""需求显示窗口模块

提供结局、贴纸、NG场景的达成条件显示功能，使用Canvas绘制卡片式UI。
"""

import tkinter as tk
from tkinter import Scrollbar
from typing import Dict, Any, Set, List, Callable

from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import set_window_icon
from .visual_effects import create_rounded_rect, wrap_text
import customtkinter as ctk


class RequirementsViewer:
    """需求显示窗口管理器"""
    
    def __init__(self, window: tk.Widget, t_func: Callable[[str], str]):
        """初始化需求显示窗口
        
        Args:
            window: 主窗口对象
            t_func: 翻译函数
        """
        self.window = window
        self.t = t_func
    
    def show(self, title_key: str, hint_key: str, items: List[tuple], 
             collected_set: Set[str], id_prefix: str, window_title_suffix: str,
             is_sticker: bool = False, is_ng_scene: bool = False) -> None:
        """显示需求窗口
        
        Args:
            title_key: 标题翻译键
            hint_key: 提示翻译键
            items: 项目列表，每个元素为 (item_id, condition_text)
            collected_set: 已收集的项目集合
            id_prefix: ID前缀（如"END"、"#"等）
            window_title_suffix: 窗口标题后缀
            is_sticker: 是否为贴纸
            is_ng_scene: 是否为NG场景
        """
        root_window = self.window
        while not isinstance(root_window, tk.Tk) and hasattr(root_window, 'master'):
            root_window = root_window.master
        
        requirements_window = tk.Toplevel(root_window)
        requirements_window.title(self.t(title_key) + " - " + self.t("view_requirements"))
        requirements_window.geometry("1275x975")
        requirements_window.configure(bg=Colors.MODAL_BG)
        set_window_icon(requirements_window)
        
        CARD_PADDING = 16
        CARD_RADIUS = 12
        CARD_MARGIN = 12
        CARD_WIDTH = 780
        SHADOW_OFFSET = 3
        SCALE_FACTOR = 1.5
        
        COLORS = {
            'bg': '#f5f5f7',
            'missing_card': '#fff0f3',
            'missing_border': '#ffb3c1',
            'missing_shadow': '#ffd6e0',
            'missing_title': '#c9184a',
            'missing_status': '#ff4d6d',
            'missing_text': '#590d22',
            'collected_card': '#f0fdf4',
            'collected_border': '#86efac',
            'collected_shadow': '#bbf7d0',
            'collected_title': '#15803d',
            'collected_status': '#22c55e',
            'collected_text': '#14532d',
            'header_bg': '#ffffff',
            'header_text': '#1f2937',
            'hint_text': '#dc2626',
        }
        
        font_title = get_cjk_font(16, "bold")
        font_hint = get_cjk_font(12, "bold")
        font_card_title = get_cjk_font(13, "bold")
        font_card_status = get_cjk_font(10, "bold")
        font_card_text = get_cjk_font(10)
        
        main_frame = tk.Frame(requirements_window, bg=COLORS['bg'])
        main_frame.pack(fill="both", expand=True)
        
        header_frame = tk.Frame(main_frame, bg=COLORS['header_bg'], height=120)
        header_frame.pack(fill="x", padx=0, pady=0)
        header_frame.pack_propagate(False)
        
        missing_list = [(item_id, cond) for item_id, cond in items if item_id not in collected_set]
        collected_list = [(item_id, cond) for item_id, cond in items if item_id in collected_set]
        
        title_text = self.t(title_key) + " - " + self.t("view_requirements")
        title_label = tk.Label(header_frame, text=title_text, font=font_title, 
                              bg=COLORS['header_bg'], fg=COLORS['header_text'])
        title_label.pack(anchor="w", padx=20, pady=(15, 5))
        
        if is_ng_scene:
            stats_text = f"✓ {self.t('ng_scene_count')}: {len(collected_list)}/{len(items)}    "
            if missing_list:
                stats_text += f"⚠ {self.t('missing_omakes')}: {len(missing_list)}"
        else:
            stats_text = f"✓ {self.t('collected_endings') if not is_sticker else self.t('collected_stickers')}: {len(collected_list)}    "
            if missing_list:
                stats_text += f"⚠ {self.t('missing_endings') if not is_sticker else self.t('missing_stickers_count')}: {len(missing_list)}"
        stats_label = tk.Label(
            header_frame,
            text=stats_text,
            font=font_hint,
            bg=COLORS['header_bg'],
            fg=COLORS['hint_text'] if missing_list else COLORS['collected_title'],
            wraplength=CARD_WIDTH
        )
        stats_label.pack(anchor="w", padx=20, pady=(2, 12))
        
        separator = tk.Frame(main_frame, height=1, bg='#e5e7eb')
        separator.pack(fill="x")
        
        scroll_frame = tk.Frame(main_frame, bg=COLORS['bg'])
        scroll_frame.pack(fill="both", expand=True)
        
        canvas = ctk.CTkCanvas(scroll_frame, bg=COLORS['bg'], highlightthickness=0)
        scrollbar = Scrollbar(scroll_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        display_order = missing_list + collected_list
        
        y_offset = 20
        card_data = []
        
        for item_id, condition_text in display_order:
            is_missing = item_id not in collected_set
            
            wrapped_lines = wrap_text(condition_text, font_card_text, CARD_WIDTH - CARD_PADDING * 2 - 20, canvas)
            line_height = 18
            text_height = len(wrapped_lines) * line_height
            
            card_height = 40 + text_height + CARD_PADDING * 2
            
            card_data.append({
                'item_id': item_id,
                'condition_text': condition_text,
                'wrapped_lines': wrapped_lines,
                'is_missing': is_missing,
                'y': y_offset,
                'height': card_height
            })
            
            y_offset += card_height + CARD_MARGIN
        
        total_height = y_offset + 20
        
        canvas.configure(scrollregion=(0, 0, CARD_WIDTH + 40, total_height))
        
        for card in card_data:
            is_missing = card['is_missing']
            y = card['y']
            h = card['height']
            
            if is_missing:
                card_color = COLORS['missing_card']
                border_color = COLORS['missing_border']
                shadow_color = COLORS['missing_shadow']
                title_color = COLORS['missing_title']
                status_color = COLORS['missing_status']
                text_color = COLORS['missing_text']
                status_text = "❌ " + (self.t("status_missing_ending") if not is_sticker and not is_ng_scene else (self.t("status_missing_sticker") if is_sticker else self.t("status_missing_ending")))
            else:
                card_color = COLORS['collected_card']
                border_color = COLORS['collected_border']
                shadow_color = COLORS['collected_shadow']
                title_color = COLORS['collected_title']
                status_color = COLORS['collected_status']
                text_color = COLORS['collected_text']
                status_text = "✓ " + (self.t("status_collected_ending") if not is_sticker and not is_ng_scene else (self.t("status_collected_sticker") if is_sticker else self.t("status_collected_ending")))
            
            x1, y1 = 25, y
            x2, y2 = 25 + CARD_WIDTH, y + h
            
            create_rounded_rect(canvas, 
                             x1 + SHADOW_OFFSET, y1 + SHADOW_OFFSET, 
                             x2 + SHADOW_OFFSET, y2 + SHADOW_OFFSET, 
                             CARD_RADIUS, fill=shadow_color, outline="")
            
            create_rounded_rect(canvas, x1 - 1, y1 - 1, x2 + 1, y2 + 1, 
                             CARD_RADIUS, fill=border_color, outline="")
            
            create_rounded_rect(canvas, x1, y1, x2, y2, 
                             CARD_RADIUS, fill=card_color, outline="")
            
            title_text = f"{id_prefix}{card['item_id']}"
            canvas.create_text(x1 + CARD_PADDING, y1 + CARD_PADDING, 
                             text=title_text, font=font_card_title, 
                             fill=title_color, anchor="nw")
            
            canvas.create_text(x2 - CARD_PADDING, y1 + CARD_PADDING, 
                             text=status_text, font=font_card_status, 
                             fill=status_color, anchor="ne")
            
            line_y = y1 + 40
            canvas.create_line(x1 + CARD_PADDING, line_y, x2 - CARD_PADDING, line_y, 
                             fill=border_color, width=1)
            
            text_y = line_y + 12
            text_height = len(card['wrapped_lines']) * 18
            
            text_frame = tk.Frame(canvas, bg=card_color)
            text_widget = tk.Text(
                text_frame,
                wrap=tk.NONE,
                font=font_card_text,
                fg=text_color,
                bg=card_color,
                relief=tk.FLAT,
                borderwidth=0,
                highlightthickness=0,
                selectbackground='#4A90E2',
                selectforeground='white',
                cursor='ibeam',
                state=tk.NORMAL,
                padx=0,
                pady=0,
                spacing1=0,
                spacing2=0,
                spacing3=0
            )
            
            full_text = '\n'.join(card['wrapped_lines'])
            text_widget.insert('1.0', full_text)
            text_widget.config(state=tk.DISABLED)
            
            text_widget.pack(fill='both', expand=True)
            
            canvas.create_window(
                x1 + CARD_PADDING, text_y,
                window=text_frame,
                anchor='nw',
                width=CARD_WIDTH - CARD_PADDING * 2,
                height=text_height
            )
        
        canvas.scale("all", 0, 0, SCALE_FACTOR, SCALE_FACTOR)
        canvas.configure(scrollregion=canvas.bbox("all"))
        
        def on_mousewheel(event):
            if event.delta:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            else:
                if event.num == 4:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.yview_scroll(1, "units")
        
        canvas.bind("<MouseWheel>", on_mousewheel)
        canvas.bind("<Button-4>", on_mousewheel)
        canvas.bind("<Button-5>", on_mousewheel)
        
        requirements_window.bind("<MouseWheel>", on_mousewheel)
        requirements_window.bind("<Button-4>", on_mousewheel)
        requirements_window.bind("<Button-5>", on_mousewheel)

