"""统计面板UI模块

提供统计面板的主UI类，协调各个子模块完成统计面板的创建和更新
"""

import logging
import tkinter as tk
from tkinter import font as tkfont
from typing import Dict, Any, Optional, Callable

import customtkinter as ctk

from src.utils.styles import Colors, get_cjk_font
from ..ui_components import LABEL_TEXT_WRAPLENGTH
from .constants import (
    CANVAS_SIZE,
    TOTAL_STICKERS,
    RING_RADIUS,
    RING_LINE_WIDTH,
    TITLE_Y_OFFSET,
    PERCENT_Y_OFFSET,
    COUNT_Y_OFFSET,
    JUDGE_COLORS,
    NEO_FANATIC_COLOR,
    NEO_GOOD_COLOR,
    JUDGE_SEPARATOR,
    JUDGE_CANVAS_HEIGHT,
    JUDGE_TEXT_Y_POSITION,
    MIN_JUDGE_CANVAS_WIDTH,
    CANVAS_WIDTH_PADDING,
)
from .data_extractor import (
    is_fanatic_route,
    extract_sticker_data,
    extract_judge_data,
    get_progress_color,
    load_neo_content,
    create_font_object,
)
from .ring_animator import (
    draw_background_ring,
    start_ring_animation,
)
from .gibberish_effect import GibberishEffectManager

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


def _cancel_canvas_animations(canvas: Optional[ctk.CTkCanvas], window: tk.Widget) -> None:
    """安全取消canvas上的所有动画
    
    Args:
        canvas: Canvas对象
        window: 窗口对象
    """
    if canvas is None:
        return
    
    if hasattr(canvas, '_animation_job') and canvas._animation_job:
        _safe_after_cancel(window, canvas._animation_job)
        canvas._animation_job = None
    
    if hasattr(canvas, '_celebration_job') and canvas._celebration_job:
        _safe_after_cancel(window, canvas._celebration_job)
        canvas._celebration_job = None


class StatisticsPanel:
    """统计面板管理器"""
    
    def __init__(
        self,
        window: tk.Widget,
        storage_dir: str,
        t_func: Callable[[str], str]
    ) -> None:
        """初始化统计面板
        
        Args:
            window: 主窗口对象
            storage_dir: 存档目录
            t_func: 翻译函数
        """
        self.window = window
        self.storage_dir = storage_dir
        self.t = t_func
        self._stats_container: Optional[tk.Widget] = None
        self._stats_widgets: Dict[str, Any] = {}
        self._last_sticker_count: Optional[int] = None
        self._gibberish_manager = GibberishEffectManager(window, t_func, storage_dir)
    
    def create(self, parent: tk.Widget) -> tk.Widget:
        """创建统计面板容器
        
        Args:
            parent: 父容器
            
        Returns:
            统计面板容器
        """
        self._cancel_all_animations()
        
        if self._stats_container and _is_widget_valid(self._stats_container):
            try:
                self._stats_container.destroy()
            except (tk.TclError, RuntimeError):
                pass
        
        self._stats_container = None
        self._stats_widgets.clear()
        self._gibberish_manager.reset()
        
        stats_container = tk.Frame(parent, bg=Colors.WHITE)
        stats_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        self._stats_container = stats_container
        
        placeholder = tk.Label(
            stats_container,
            text=self.t("no_save_data"),
            font=get_cjk_font(12),
            bg=Colors.WHITE
        )
        placeholder.pack(pady=50)
        
        return stats_container
    
    def _cancel_all_animations(self) -> None:
        """取消所有正在运行的动画"""
        self._gibberish_manager.reset()
        
        sticker_canvas = self._stats_widgets.get('sticker_canvas')
        if sticker_canvas:
            _cancel_canvas_animations(sticker_canvas, self.window)
    
    def update(self, parent: tk.Widget, save_data: Dict[str, Any]) -> None:
        """更新统计面板内容
        
        Args:
            parent: 父容器
            save_data: 存档数据
        """
        if not _is_widget_valid(parent):
            self._cancel_all_animations()
            self._stats_widgets.clear()
            return
        
        self._gibberish_manager.reset()
        
        collected_stickers, _ = extract_sticker_data(save_data)
        
        if self._should_use_incremental_update(collected_stickers):
            self.update_incremental(parent, save_data)
            return
        
        self._rebuild_panel(parent, save_data)
    
    def _should_use_incremental_update(self, collected_stickers: int) -> bool:
        """判断是否应该使用增量更新
        
        Args:
            collected_stickers: 当前收集的贴纸数量
            
        Returns:
            是否应该使用增量更新
        """
        if 'sticker_canvas' not in self._stats_widgets:
            return False
        
        sticker_canvas = self._stats_widgets.get('sticker_canvas')
        if not _is_widget_valid(sticker_canvas):
            self._cancel_all_animations()
            self._stats_widgets.clear()
            return False
        
        if (self._last_sticker_count is not None and
            self._last_sticker_count == collected_stickers):
            return False
        
        return True
    
    def _rebuild_panel(self, parent: tk.Widget, save_data: Dict[str, Any]) -> None:
        """完整重建统计面板
        
        Args:
            parent: 父容器
            save_data: 存档数据
        """
        self._cancel_all_animations()
        
        if not _is_widget_valid(parent):
            return
        
        try:
            for widget in parent.winfo_children():
                widget.destroy()
        except (tk.TclError, RuntimeError):
            return
        
        is_fanatic = is_fanatic_route(save_data)
        collected_stickers, stickers_percent = extract_sticker_data(save_data)
        whole_total_mp = save_data.get("wholeTotalMP", 0)
        judge_data = extract_judge_data(save_data)
        
        sticker_canvas = self._create_sticker_ring(
            parent, stickers_percent, is_fanatic, collected_stickers
        )
        
        mp_label_value = self._create_mp_display(parent, whole_total_mp)
        judge_canvas = self._create_judge_display(parent, judge_data)
        neo_label = self._create_neo_display(parent, is_fanatic)
        
        if is_fanatic:
            self._gibberish_manager.setup_effect(
                sticker_canvas, stickers_percent, collected_stickers,
                mp_label_value, whole_total_mp, judge_canvas, judge_data,
                neo_label, self._stats_widgets
            )
        
        self._save_widget_references(
            sticker_canvas, mp_label_value, judge_canvas, neo_label
        )
        
        self._last_sticker_count = collected_stickers
    
    def _create_sticker_ring(
        self,
        parent: tk.Widget,
        stickers_percent: float,
        is_fanatic_route: bool,
        collected_stickers: int
    ) -> ctk.CTkCanvas:
        """创建贴纸环形图
        
        Args:
            parent: 父容器
            stickers_percent: 贴纸百分比
            is_fanatic_route: 是否为狂信徒路线
            collected_stickers: 已收集贴纸数
            
        Returns:
            Canvas对象
        """
        sticker_frame = tk.Frame(parent, bg=Colors.WHITE)
        sticker_frame.pack(pady=(0, 20))
        
        sticker_canvas = ctk.CTkCanvas(
            sticker_frame,
            width=CANVAS_SIZE,
            height=CANVAS_SIZE,
            bg=Colors.WHITE,
            highlightthickness=0
        )
        sticker_canvas.pack()
        
        center_x = center_y = CANVAS_SIZE // 2
        progress_color = get_progress_color(stickers_percent, is_fanatic_route)
        
        draw_background_ring(sticker_canvas, center_x, center_y)
        
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
        
        sticker_canvas.create_text(
            center_x, center_y + COUNT_Y_OFFSET,
            text=f"{collected_stickers}/{TOTAL_STICKERS}",
            font=get_cjk_font(11),
            fill=Colors.TEXT_MUTED,
            tags="count_text"
        )
        
        start_ring_animation(
            self.window, sticker_canvas, center_x, center_y, stickers_percent,
            progress_color, percent_text_id
        )
        
        return sticker_canvas
    
    def _create_mp_display(
        self,
        parent: tk.Widget,
        whole_total_mp: int
    ) -> tk.Label:
        """创建MP显示
        
        Args:
            parent: 父容器
            whole_total_mp: 总MP值
            
        Returns:
            MP值标签
        """
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
        
        self._stats_widgets['mp_label_title'] = mp_label_title
        return mp_label_value
    
    def _create_judge_display(
        self,
        parent: tk.Widget,
        judge_data: Dict[str, int]
    ) -> ctk.CTkCanvas:
        """创建判定统计显示
        
        Args:
            parent: 父容器
            judge_data: 判定数据字典
            
        Returns:
            Canvas对象
        """
        if not judge_data:
            judge_data = {"perfect": 0, "good": 0, "bad": 0}
        
        judge_frame = tk.Frame(parent, bg=Colors.WHITE)
        judge_frame.pack(pady=(30, 0))
        
        perfect_count = judge_data.get("perfect", 0)
        good_count = judge_data.get("good", 0)
        bad_count = judge_data.get("bad", 0)
        
        perfect_text = f"{perfect_count:,}"
        good_text = f"{good_count:,}"
        bad_text = f"{bad_count:,}"
        full_text = f"{perfect_text}{JUDGE_SEPARATOR}{good_text}{JUDGE_SEPARATOR}{bad_text}"
        
        font_obj = create_font_object(get_cjk_font(10))
        text_width = font_obj.measure(full_text)
        canvas_width = max(MIN_JUDGE_CANVAS_WIDTH, text_width + CANVAS_WIDTH_PADDING)
        
        judge_canvas = ctk.CTkCanvas(
            judge_frame,
            width=canvas_width,
            height=JUDGE_CANVAS_HEIGHT,
            bg=Colors.WHITE,
            highlightthickness=0
        )
        judge_canvas.pack()
        
        self._draw_judge_texts_normal(
            judge_canvas, perfect_text, good_text, bad_text, font_obj, canvas_width, text_width
        )
        
        return judge_canvas
    
    def _draw_judge_texts_normal(
        self,
        canvas: ctk.CTkCanvas,
        perfect_text: str,
        good_text: str,
        bad_text: str,
        font_obj: tkfont.Font,
        canvas_width: int,
        text_width: int
    ) -> None:
        """绘制判定统计文本（正常模式，非乱码）
        
        Args:
            canvas: Canvas对象
            perfect_text: Perfect文本
            good_text: Good文本
            bad_text: Bad文本
            font_obj: 字体对象
            canvas_width: Canvas宽度
            text_width: 文本总宽度
        """
        center_x = canvas_width // 2
        current_x = center_x - text_width // 2
        
        judge_items = [
            ("perfect", perfect_text, JUDGE_COLORS["perfect"]),
            ("good", good_text, JUDGE_COLORS["good"]),
            ("bad", bad_text, JUDGE_COLORS["bad"]),
        ]
        
        text_widths = []
        for judge_type, text, color in judge_items:
            text_width_item = font_obj.measure(text)
            text_widths.append(text_width_item)
            canvas.create_text(
                current_x + text_width_item // 2,
                JUDGE_TEXT_Y_POSITION,
                text=text,
                font=get_cjk_font(10),
                fill=color,
                anchor="center"
            )
            current_x += text_width_item + font_obj.measure(JUDGE_SEPARATOR)
        
        sep_width = font_obj.measure(JUDGE_SEPARATOR)
        sep1_x = center_x - text_width // 2 + text_widths[0]
        sep2_x = sep1_x + sep_width + text_widths[1]
        
        for sep_x in (sep1_x, sep2_x):
            canvas.create_text(
                sep_x + sep_width // 2,
                JUDGE_TEXT_Y_POSITION,
                text=JUDGE_SEPARATOR,
                font=get_cjk_font(10),
                fill=JUDGE_COLORS["separator"],
                anchor="center"
            )
    
    def _create_neo_display(
        self,
        parent: tk.Widget,
        is_fanatic_route: bool
    ) -> Optional[tk.Label]:
        """创建NEO显示
        
        Args:
            parent: 父容器
            is_fanatic_route: 是否为狂信徒路线
            
        Returns:
            NEO标签，如果文件不存在则返回None
        """
        neo_result = load_neo_content(self.storage_dir)
        if neo_result is None:
            return None
        
        neo_text, text_color = neo_result
        
        neo_frame = tk.Frame(parent, bg=Colors.WHITE)
        neo_frame.pack(pady=(55, 0))
        
        if neo_text is None:
            display_text = self.t("good_neo") if text_color == NEO_GOOD_COLOR else self.t("bad_neo")
        else:
            display_text = neo_text
        
        if is_fanatic_route:
            text_color = NEO_FANATIC_COLOR
        
        neo_label = tk.Label(
            neo_frame,
            text=display_text,
            font=get_cjk_font(14),
            fg=text_color,
            bg=Colors.WHITE,
            wraplength=LABEL_TEXT_WRAPLENGTH
        )
        neo_label.pack()
        
        return neo_label
    
    def _save_widget_references(
        self,
        sticker_canvas: ctk.CTkCanvas,
        mp_label_value: tk.Label,
        judge_canvas: ctk.CTkCanvas,
        neo_label: Optional[tk.Label]
    ) -> None:
        """保存widget引用到字典
        
        Args:
            sticker_canvas: 贴纸canvas
            mp_label_value: MP值标签
            judge_canvas: 判定canvas
            neo_label: NEO标签（可选）
        """
        self._stats_widgets.update({
            'sticker_canvas': sticker_canvas,
            'mp_label_value': mp_label_value,
            'judge_canvas': judge_canvas,
            'canvas_size': CANVAS_SIZE,
            'center_x': CANVAS_SIZE // 2,
            'center_y': CANVAS_SIZE // 2,
            'radius': RING_RADIUS,
            'line_width': RING_LINE_WIDTH,
        })
        
        if neo_label is not None:
            self._stats_widgets['neo_label'] = neo_label
    
    def update_incremental(self, parent: tk.Widget, save_data: Dict[str, Any]) -> None:
        """增量更新统计面板
        
        Args:
            parent: 父容器
            save_data: 存档数据
        """
        collected_stickers, stickers_percent = extract_sticker_data(save_data)
        
        if (self._last_sticker_count is not None and
            self._last_sticker_count == collected_stickers):
            return
        
        is_fanatic = is_fanatic_route(save_data)
        whole_total_mp = save_data.get("wholeTotalMP", 0)
        judge_data = extract_judge_data(save_data)
        
        if not _is_widget_valid(parent):
            self._cancel_all_animations()
            self._stats_widgets.clear()
            return
        
        if not self._validate_widgets():
            self._cancel_all_animations()
            self._stats_widgets.clear()
            self.update(parent, save_data)
            return
        
        sticker_canvas = self._stats_widgets['sticker_canvas']
        mp_label_value = self._stats_widgets.get('mp_label_value')
        judge_canvas = self._stats_widgets.get('judge_canvas')
        
        canvas_width = sticker_canvas.winfo_width()
        canvas_height = sticker_canvas.winfo_height()
        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width = self._stats_widgets.get('canvas_size', CANVAS_SIZE)
            canvas_height = canvas_width
        
        center_x = canvas_width // 2
        center_y = canvas_height // 2
        progress_color = get_progress_color(stickers_percent, is_fanatic)
        
        self._update_sticker_ring_incremental(
            sticker_canvas, center_x, center_y, stickers_percent,
            progress_color, collected_stickers
        )
        
        if _is_widget_valid(mp_label_value):
            try:
                mp_label_value.config(text=f"{whole_total_mp:,}")
            except (tk.TclError, RuntimeError):
                pass
        
        if _is_widget_valid(judge_canvas):
            self._update_judge_display_incremental(judge_canvas, judge_data)
        
        self._update_neo_display_incremental(is_fanatic)
        
        if is_fanatic:
            self._gibberish_manager.setup_effect(
                sticker_canvas, stickers_percent, collected_stickers,
                mp_label_value, whole_total_mp, judge_canvas, judge_data,
                self._stats_widgets.get('neo_label'), self._stats_widgets
            )
        else:
            self._gibberish_manager.reset()
        
        self._last_sticker_count = collected_stickers
    
    def _validate_widgets(self) -> bool:
        """验证widget是否有效
        
        Returns:
            widget是否有效
        """
        sticker_canvas = self._stats_widgets.get('sticker_canvas')
        if not _is_widget_valid(sticker_canvas):
            return False
        
        mp_label_value = self._stats_widgets.get('mp_label_value')
        if mp_label_value and not _is_widget_valid(mp_label_value):
            return False
        
        judge_canvas = self._stats_widgets.get('judge_canvas')
        if judge_canvas and not _is_widget_valid(judge_canvas):
            return False
        
        return True
    
    def _update_sticker_ring_incremental(
        self,
        canvas: ctk.CTkCanvas,
        center_x: int,
        center_y: int,
        stickers_percent: float,
        progress_color: str,
        collected_stickers: int
    ) -> None:
        """增量更新贴纸环形图
        
        Args:
            canvas: Canvas对象
            center_x: 中心X坐标
            center_y: 中心Y坐标
            stickers_percent: 贴纸百分比
            progress_color: 进度颜色
            collected_stickers: 已收集贴纸数
        """
        canvas.delete("progress")
        canvas.delete("title_text")
        canvas.delete("percent_text")
        canvas.delete("count_text")
        
        if not canvas.find_withtag("background_ring"):
            draw_background_ring(canvas, center_x, center_y)
        
        canvas.create_text(
            center_x, center_y + TITLE_Y_OFFSET,
            text=self.t('stickers_statistics'),
            font=get_cjk_font(12, "bold"),
            fill=Colors.TEXT_DARK,
            tags="title_text"
        )
        
        percent_text_id = canvas.create_text(
            center_x, center_y + PERCENT_Y_OFFSET,
            text="0.0%",
            font=get_cjk_font(20, "bold"),
            fill=Colors.TEXT_DARK,
            tags="percent_text"
        )
        self._stats_widgets['percent_text_id'] = percent_text_id
        
        canvas.create_text(
            center_x, center_y + COUNT_Y_OFFSET,
            text=f"{collected_stickers}/{TOTAL_STICKERS}",
            font=get_cjk_font(11),
            fill=Colors.TEXT_MUTED,
            tags="count_text"
        )
        
        start_ring_animation(
            self.window, canvas, center_x, center_y, stickers_percent,
            progress_color, percent_text_id
        )
    
    def _update_judge_display_incremental(
        self,
        canvas: ctk.CTkCanvas,
        judge_data: Dict[str, int]
    ) -> None:
        """增量更新判定统计显示
        
        Args:
            canvas: Canvas对象
            judge_data: 判定数据字典
        """
        if not _is_widget_valid(canvas):
            return
        
        try:
            canvas.delete("all")
        except (tk.TclError, RuntimeError):
            return
        
        if not judge_data:
            judge_data = {"perfect": 0, "good": 0, "bad": 0}
        
        perfect_count = judge_data.get("perfect", 0)
        good_count = judge_data.get("good", 0)
        bad_count = judge_data.get("bad", 0)
        
        perfect_text = f"{perfect_count:,}"
        good_text = f"{good_count:,}"
        bad_text = f"{bad_count:,}"
        full_text = f"{perfect_text}{JUDGE_SEPARATOR}{good_text}{JUDGE_SEPARATOR}{bad_text}"
        
        font_obj = create_font_object(get_cjk_font(10))
        text_width = font_obj.measure(full_text)
        canvas_width = max(MIN_JUDGE_CANVAS_WIDTH, text_width + CANVAS_WIDTH_PADDING)
        
        if not _is_widget_valid(canvas):
            return
        
        try:
            canvas.config(width=canvas_width)
        except (tk.TclError, RuntimeError):
            return
        
        self._draw_judge_texts_normal(
            canvas, perfect_text, good_text, bad_text, font_obj, canvas_width, text_width
        )
    
    def _update_neo_display_incremental(self, is_fanatic_route: bool) -> None:
        """增量更新NEO显示
        
        Args:
            is_fanatic_route: 是否为狂信徒路线
        """
        neo_label = self._stats_widgets.get('neo_label')
        if not _is_widget_valid(neo_label):
            return
        
        neo_result = load_neo_content(self.storage_dir)
        if neo_result is None:
            return
        
        neo_text, text_color = neo_result
        
        if neo_text is None:
            display_text = self.t("good_neo") if text_color == NEO_GOOD_COLOR else self.t("bad_neo")
        else:
            display_text = neo_text
        
        if is_fanatic_route:
            text_color = NEO_FANATIC_COLOR
        
        try:
            neo_label.config(text=display_text, fg=text_color)
        except (tk.TclError, RuntimeError):
            pass
