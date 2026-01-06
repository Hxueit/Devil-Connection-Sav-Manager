"""乱码效果管理器

负责狂信徒路线的文字乱码特效，包括canvas文本、标签和判定统计的乱码显示
"""

import logging
import tkinter as tk
from tkinter import font as tkfont
from typing import Dict, Any, Optional, Callable, List

import customtkinter as ctk

from src.utils.styles import get_cjk_font
from .constants import (
    CANVAS_SIZE,
    TOTAL_STICKERS,
    NEO_FANATIC_COLOR,
    NEO_GOOD_COLOR,
    NEO_BAD_COLOR,
    GIBBERISH_UPDATE_INTERVAL_MS,
    JUDGE_SEPARATOR,
    JUDGE_TEXT_Y_POSITION,
)
from .data_extractor import load_neo_content, create_font_object
from ..visual_effects import generate_gibberish_text

logger = logging.getLogger(__name__)


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


class GibberishEffectManager:
    """乱码效果管理器 - 负责狂信徒路线的文字乱码特效"""
    
    def __init__(
        self,
        window: tk.Widget,
        t_func: Callable[[str], str],
        storage_dir: str
    ) -> None:
        """初始化乱码效果管理器
        
        Args:
            window: 主窗口对象
            t_func: 翻译函数
            storage_dir: 存档目录
        """
        self.window = window
        self.t = t_func
        self.storage_dir = storage_dir
        self._gibberish_update_job: Optional[int] = None
        self._original_texts: Dict[int, str] = {}
        self._gibberish_widgets: List[Dict[str, Any]] = []
    
    def setup_effect(
        self,
        sticker_canvas: ctk.CTkCanvas,
        stickers_percent: float,
        collected_stickers: int,
        mp_label_value: Optional[tk.Label],
        whole_total_mp: int,
        judge_canvas: Optional[ctk.CTkCanvas],
        judge_data: Dict[str, int],
        neo_label: Optional[tk.Label],
        stats_widgets: Dict[str, Any]
    ) -> None:
        """设置乱码效果
        
        Args:
            sticker_canvas: 贴纸canvas
            stickers_percent: 贴纸百分比
            collected_stickers: 已收集贴纸数
            mp_label_value: MP值标签
            whole_total_mp: 总MP值
            judge_canvas: 判定canvas
            judge_data: 判定数据字典
            neo_label: NEO标签
            stats_widgets: 统计面板widget引用字典
        """
        self._gibberish_widgets.clear()
        self._original_texts.clear()
        
        center_x = stats_widgets.get('center_x', CANVAS_SIZE // 2)
        center_y = stats_widgets.get('center_y', CANVAS_SIZE // 2)
        
        all_text_ids = [
            item for item in sticker_canvas.find_all()
            if sticker_canvas.type(item) == 'text'
        ]
        if len(all_text_ids) >= 3:
            self._add_canvas_text(
                sticker_canvas, all_text_ids[-3], center_x, center_y - 20,
                get_cjk_font(12, "bold"), self.t('stickers_statistics')
            )
            self._add_canvas_text(
                sticker_canvas, all_text_ids[-2], center_x, center_y + 2,
                get_cjk_font(20, "bold"), f"{stickers_percent:.1f}%"
            )
            self._add_canvas_text(
                sticker_canvas, all_text_ids[-1], center_x, center_y + 22,
                get_cjk_font(11), f"{collected_stickers}/{TOTAL_STICKERS}"
            )
        
        mp_label_title = stats_widgets.get('mp_label_title')
        if mp_label_title:
            self._add_label(mp_label_title, self.t("total_mp"))
        if mp_label_value:
            self._add_label(mp_label_value, f"{whole_total_mp:,}")
        
        if judge_canvas:
            full_text = f"{judge_data['perfect']:,} - {judge_data['good']:,} - {judge_data['bad']:,}"
            font_obj = create_font_object(get_cjk_font(10))
            text_width = font_obj.measure(full_text)
            canvas_width = max(250, text_width + 20)
            self._add_judge_canvas(
                judge_canvas, judge_data, canvas_width, font_obj, text_width
            )
        
        if neo_label and _is_widget_valid(neo_label):
            neo_result = load_neo_content(self.storage_dir)
            if neo_result:
                neo_text, _ = neo_result
                if neo_text is None:
                    display_text = self.t("good_neo") if neo_result[1] == NEO_GOOD_COLOR else self.t("bad_neo")
                else:
                    display_text = neo_text
                self._add_label(neo_label, display_text)
        
        self._update_texts()
    
    def reset(self) -> None:
        """重置乱码效果状态"""
        if self._gibberish_update_job is not None:
            _safe_after_cancel(self.window, self._gibberish_update_job)
            self._gibberish_update_job = None
        self._gibberish_widgets.clear()
        self._original_texts.clear()
    
    def _add_canvas_text(
        self,
        canvas: ctk.CTkCanvas,
        text_id: int,
        x: int,
        y: int,
        font_spec,
        original_text: str
    ) -> None:
        """添加canvas文本到乱码列表
        
        Args:
            canvas: Canvas对象
            text_id: 文本ID
            x: X坐标
            y: Y坐标
            font_spec: 字体规格
            original_text: 原始文本
        """
        self._gibberish_widgets.append({
            'type': 'canvas_text',
            'canvas': canvas,
            'text_id': text_id,
            'x': x,
            'y': y,
            'font': font_spec,
            'fill': NEO_FANATIC_COLOR,
            'anchor': 'center',
            'tag': 'title_text'
        })
        self._original_texts[len(self._gibberish_widgets) - 1] = original_text
    
    def _add_label(self, widget: tk.Label, original_text: str) -> None:
        """添加标签到乱码列表
        
        Args:
            widget: 标签widget
            original_text: 原始文本
        """
        self._gibberish_widgets.append({
            'type': 'tk_label',
            'widget': widget
        })
        self._original_texts[len(self._gibberish_widgets) - 1] = original_text
    
    def _add_judge_canvas(
        self,
        canvas: ctk.CTkCanvas,
        judge_data: Dict[str, int],
        canvas_width: int,
        font_obj: tkfont.Font,
        text_width: int
    ) -> None:
        """添加判定canvas到乱码列表
        
        Args:
            canvas: Canvas对象
            judge_data: 判定数据字典
            canvas_width: Canvas宽度
            font_obj: 字体对象
            text_width: 文本宽度
        """
        full_text = f"{judge_data['perfect']:,} - {judge_data['good']:,} - {judge_data['bad']:,}"
        self._gibberish_widgets.append({
            'type': 'judge_canvas',
            'canvas': canvas,
            'perfect': judge_data['perfect'],
            'good': judge_data['good'],
            'bad': judge_data['bad'],
            'canvas_width': canvas_width,
            'font_obj': font_obj,
            'center_x': canvas_width // 2,
            'text_width': text_width
        })
        self._original_texts[len(self._gibberish_widgets) - 1] = full_text
    
    def _update_texts(self) -> None:
        """更新所有文字为乱码效果"""
        if not _is_widget_valid(self.window):
            self._gibberish_update_job = None
            return
        
        if not self._gibberish_widgets:
            return
        
        for idx, widget_info in enumerate(self._gibberish_widgets):
            if idx not in self._original_texts:
                continue
            
            original_text = self._original_texts[idx]
            gibberish_text = generate_gibberish_text(original_text)
            
            try:
                if widget_info['type'] == 'canvas_text':
                    self._update_canvas_text(widget_info, gibberish_text)
                elif widget_info['type'] == 'tk_label':
                    self._update_label(widget_info, gibberish_text)
                elif widget_info['type'] == 'judge_canvas':
                    self._update_judge_canvas(widget_info)
            except (tk.TclError, RuntimeError):
                continue
        
        if _is_widget_valid(self.window):
            try:
                self._gibberish_update_job = self.window.after(
                    GIBBERISH_UPDATE_INTERVAL_MS, self._update_texts
                )
            except (tk.TclError, RuntimeError):
                self._gibberish_update_job = None
        else:
            self._gibberish_update_job = None
    
    def _update_canvas_text(
        self,
        widget_info: Dict[str, Any],
        gibberish_text: str
    ) -> None:
        """更新canvas文本为乱码
        
        Args:
            widget_info: widget信息字典
            gibberish_text: 乱码文本
        """
        canvas = widget_info.get('canvas')
        if not _is_widget_valid(canvas):
            return
        
        try:
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
        except (tk.TclError, RuntimeError):
            pass
    
    def _update_label(
        self,
        widget_info: Dict[str, Any],
        gibberish_text: str
    ) -> None:
        """更新标签为乱码
        
        Args:
            widget_info: widget信息字典
            gibberish_text: 乱码文本
        """
        widget = widget_info.get('widget')
        if _is_widget_valid(widget):
            try:
                widget.config(text=gibberish_text, fg=NEO_FANATIC_COLOR)
            except (tk.TclError, RuntimeError):
                pass
    
    def _update_judge_canvas(self, widget_info: Dict[str, Any]) -> None:
        """更新判定canvas为乱码
        
        Args:
            widget_info: widget信息字典
        """
        canvas = widget_info.get('canvas')
        if not _is_widget_valid(canvas):
            return
        
        try:
            canvas.delete("all")
        except (tk.TclError, AttributeError, RuntimeError):
            return
        
        perfect_count = widget_info.get('perfect', 0)
        good_count = widget_info.get('good', 0)
        bad_count = widget_info.get('bad', 0)
        
        perfect_text = generate_gibberish_text(f"{perfect_count:,}")
        good_text = generate_gibberish_text(f"{good_count:,}")
        bad_text = generate_gibberish_text(f"{bad_count:,}")
        
        font_obj = widget_info.get('font_obj')
        if not font_obj:
            logger.warning("Missing font_obj in judge canvas widget_info")
            return
        
        try:
            self._draw_judge_texts(
                canvas, perfect_text, good_text, bad_text,
                font_obj, widget_info.get('canvas_width', 250),
                NEO_FANATIC_COLOR
            )
        except (tk.TclError, RuntimeError):
            pass
    
    def _draw_judge_texts(
        self,
        canvas: ctk.CTkCanvas,
        perfect_text: str,
        good_text: str,
        bad_text: str,
        font_obj: tkfont.Font,
        canvas_width: int,
        text_color: str
    ) -> None:
        """绘制判定统计文本
        
        Args:
            canvas: Canvas对象
            perfect_text: Perfect文本
            good_text: Good文本
            bad_text: Bad文本
            font_obj: 字体对象
            canvas_width: Canvas宽度
            text_color: 文本颜色
        """
        if not _is_widget_valid(canvas):
            return
        
        full_text = f"{perfect_text}{JUDGE_SEPARATOR}{good_text}{JUDGE_SEPARATOR}{bad_text}"
        center_x = canvas_width // 2
        current_x = center_x - font_obj.measure(full_text) // 2
        
        judge_items = [
            ("perfect", perfect_text),
            ("good", good_text),
            ("bad", bad_text),
        ]
        
        text_widths = []
        for judge_type, text in judge_items:
            text_width_item = font_obj.measure(text)
            text_widths.append(text_width_item)
            if not _is_widget_valid(canvas):
                return
            try:
                canvas.create_text(
                    current_x + text_width_item // 2,
                    JUDGE_TEXT_Y_POSITION,
                    text=text,
                    font=get_cjk_font(10),
                    fill=text_color,
                    anchor="center"
                )
            except (tk.TclError, AttributeError, RuntimeError):
                return
            current_x += text_width_item + font_obj.measure(JUDGE_SEPARATOR)
        
        sep_width = font_obj.measure(JUDGE_SEPARATOR)
        sep1_x = center_x - font_obj.measure(full_text) // 2 + text_widths[0]
        sep2_x = sep1_x + sep_width + text_widths[1]
        
        for sep_x in (sep1_x, sep2_x):
            if not _is_widget_valid(canvas):
                return
            try:
                canvas.create_text(
                    sep_x + sep_width // 2,
                    JUDGE_TEXT_Y_POSITION,
                    text=JUDGE_SEPARATOR,
                    font=get_cjk_font(10),
                    fill=text_color,
                    anchor="center"
                )
            except (tk.TclError, AttributeError, RuntimeError):
                return
