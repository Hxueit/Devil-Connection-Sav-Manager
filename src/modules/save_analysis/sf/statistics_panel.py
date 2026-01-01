"""统计面板模块

负责创建和更新右侧统计面板，包括贴纸环形图、MP显示、判定统计等。
"""

import logging
import os
import time
import tkinter as tk
import urllib.parse
from pathlib import Path
from tkinter import font as tkfont
from typing import Dict, Any, Optional, Callable, Tuple

import customtkinter as ctk

from src.utils.styles import Colors, get_cjk_font, ease_out_cubic
from .visual_effects import (
    draw_progress_ring,
    animate_completion_celebration,
    generate_gibberish_text
)

logger = logging.getLogger(__name__)


# 常量配置
TOTAL_STICKERS = 132
CANVAS_SIZE = 280
RING_RADIUS = 100
RING_LINE_WIDTH = 30
ANIMATION_DURATION_SECONDS = 1.5
ANIMATION_FRAME_INTERVAL_MS = 33  # ~30fps
GIBBERISH_UPDATE_INTERVAL_MS = 150

# 贴纸百分比颜色阈值
STICKER_COLOR_THRESHOLDS = [
    (100, "#FFD54F"),  # 100% - 金色
    (95, "#81C784"),   # 95%+ - 绿色
    (90, "#4DB6AC"),  # 90%+ - 青绿色
    (75, "#4FC3F7"),  # 75%+ - 浅蓝色
    (0, "#64B5F6"),   # 默认 - 蓝色
]
FANATIC_ROUTE_COLOR = "#BF0204"

# 文本偏移量
TITLE_Y_OFFSET = -30
PERCENT_Y_OFFSET = 2
COUNT_Y_OFFSET = 40

# 判定统计颜色
JUDGE_COLORS = {
    "perfect": "#CC6DAE",
    "good": "#F5CE88",
    "bad": "#6DB7AB",
    "separator": Colors.TEXT_MUTED,
}

# NEO文件相关
NEO_FILENAME = "NEO.sav"
NEO_GOOD_MESSAGE = '"キミたちに永遠の祝福を"'
NEO_BAD_MESSAGE = '"オマエに永遠の制裁を"'
NEO_GOOD_COLOR = "#FFEB9E"
NEO_BAD_COLOR = "#FF0000"
NEO_DEFAULT_COLOR = "#000000"
NEO_FANATIC_COLOR = "#8b0000"

# 背景环配置
BACKGROUND_RING_OFFSETS = [
    (0, RING_LINE_WIDTH + 2),
    (0.5, RING_LINE_WIDTH + 1),
    (1, RING_LINE_WIDTH),
]


def _get_progress_color(stickers_percent: float, is_fanatic_route: bool) -> str:
    """根据贴纸百分比和路线获取进度颜色
    
    Args:
        stickers_percent: 贴纸百分比 (0-100)
        is_fanatic_route: 是否为狂信徒路线
        
    Returns:
        颜色十六进制字符串
    """
    if is_fanatic_route:
        return FANATIC_ROUTE_COLOR
    
    for threshold, color in STICKER_COLOR_THRESHOLDS:
        if stickers_percent >= threshold:
            return color
    
    return STICKER_COLOR_THRESHOLDS[-1][1]  # 默认颜色


def _is_fanatic_route(save_data: Dict[str, Any]) -> bool:
    """判断是否为狂信徒路线
    
    Args:
        save_data: 存档数据字典
        
    Returns:
        是否为狂信徒路线
    """
    kill = save_data.get("kill")
    killed = save_data.get("killed")
    return (kill == 1) or (killed == 1)


def _extract_sticker_data(save_data: Dict[str, Any]) -> Tuple[int, float]:
    """提取贴纸数据
    
    Args:
        save_data: 存档数据字典
        
    Returns:
        (collected_count, percent) 元组
    """
    stickers = set(save_data.get("sticker", []))
    collected_count = len(stickers)
    percent = (collected_count / TOTAL_STICKERS * 100) if TOTAL_STICKERS > 0 else 0.0
    return collected_count, percent


def _extract_judge_data(save_data: Dict[str, Any]) -> Dict[str, int]:
    """提取判定统计数据
    
    Args:
        save_data: 存档数据字典
        
    Returns:
        包含perfect, good, bad的字典
    """
    judge_counts = save_data.get("judgeCounts", {})
    return {
        "perfect": judge_counts.get("perfect", 0),
        "good": judge_counts.get("good", 0),
        "bad": judge_counts.get("bad", 0),
    }


def _create_font_object(font_spec) -> tkfont.Font:
    """创建字体对象
    
    Args:
        font_spec: 字体规格（元组或字体对象）
        
    Returns:
        tkinter Font对象
    """
    if isinstance(font_spec, tuple):
        return tkfont.Font(family=font_spec[0], size=font_spec[1])
    return tkfont.Font(font=font_spec)


def _load_neo_content(storage_dir: str) -> Optional[Tuple[str, str]]:
    """加载NEO文件内容
    
    Args:
        storage_dir: 存储目录路径
        
    Returns:
        (neo_text, text_color) 元组，如果文件不存在或读取失败则返回None
    """
    neo_path = Path(storage_dir) / NEO_FILENAME
    if not neo_path.exists():
        return None
    
    try:
        with open(neo_path, 'r', encoding='utf-8') as f:
            encoded_content = f.read().strip()
        
        decoded_content = urllib.parse.unquote(encoded_content)
        
        if decoded_content == NEO_GOOD_MESSAGE:
            return (None, NEO_GOOD_COLOR)  # 使用翻译键
        elif decoded_content == NEO_BAD_MESSAGE:
            return (None, NEO_BAD_COLOR)  # 使用翻译键
        else:
            return (decoded_content, NEO_DEFAULT_COLOR)
    except (OSError, UnicodeDecodeError, urllib.parse.UnquotePlusError) as e:
        logger.warning(f"Failed to load NEO file: {e}")
        return None


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
        self._gibberish_update_job: Optional[int] = None
        self._original_texts: Dict[int, str] = {}
        self._gibberish_widgets: list = []
        self._last_sticker_count: Optional[int] = None
    
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
        self._reset_gibberish_state()
        
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
    
    def _reset_gibberish_state(self) -> None:
        """重置乱码效果状态"""
        if self._gibberish_update_job is not None:
            self.window.after_cancel(self._gibberish_update_job)
            self._gibberish_update_job = None
        self._gibberish_widgets.clear()
        self._original_texts.clear()
    
    def update(self, parent: tk.Widget, save_data: Dict[str, Any]) -> None:
        """更新统计面板内容
        
        Args:
            parent: 父容器
            save_data: 存档数据
        """
        if not parent or not parent.winfo_exists():
            self._stats_widgets.clear()
            return
        
        self._reset_gibberish_state()
        
        collected_stickers, _ = _extract_sticker_data(save_data)
        
        # 检查是否可以增量更新
        if self._should_use_incremental_update(collected_stickers):
            self.update_incremental(parent, save_data)
            return
        
        # 完整重建
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
        if not sticker_canvas or not sticker_canvas.winfo_exists():
            self._stats_widgets.clear()
            return False
        
        # 如果sticker数量没有变化，不需要更新
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
        for widget in parent.winfo_children():
            widget.destroy()
        
        is_fanatic_route = _is_fanatic_route(save_data)
        collected_stickers, stickers_percent = _extract_sticker_data(save_data)
        whole_total_mp = save_data.get("wholeTotalMP", 0)
        judge_data = _extract_judge_data(save_data)
        
        # 创建贴纸环形图
        sticker_canvas = self._create_sticker_ring(
            parent, stickers_percent, is_fanatic_route, collected_stickers
        )
        
        # 创建MP显示
        mp_label_value = self._create_mp_display(parent, whole_total_mp)
        
        # 创建判定统计
        judge_canvas = self._create_judge_display(parent, judge_data)
        
        # 创建NEO显示（如果存在）
        neo_label = self._create_neo_display(parent, is_fanatic_route)
        
        # 设置狂信徒路线的乱码效果
        if is_fanatic_route:
            self._setup_gibberish_effect(
                sticker_canvas, stickers_percent, collected_stickers,
                mp_label_value, whole_total_mp, judge_canvas, judge_data,
                neo_label
            )
        
        # 保存widget引用
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
        progress_color = _get_progress_color(stickers_percent, is_fanatic_route)
        
        # 绘制背景环
        self._draw_background_ring(sticker_canvas, center_x, center_y)
        
        # 创建文本元素
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
        
        # 启动动画
        self._start_ring_animation(
            sticker_canvas, center_x, center_y, stickers_percent,
            progress_color, percent_text_id
        )
        
        return sticker_canvas
    
    def _draw_background_ring(
        self,
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
        canvas.delete("background_ring")
        for offset, width in BACKGROUND_RING_OFFSETS:
            canvas.create_oval(
                center_x - RING_RADIUS - offset,
                center_y - RING_RADIUS - offset,
                center_x + RING_RADIUS + offset,
                center_y + RING_RADIUS + offset,
                outline="#e0e0e0",
                width=int(width),
                tags="background_ring"
            )
    
    def _start_ring_animation(
        self,
        canvas: ctk.CTkCanvas,
        center_x: int,
        center_y: int,
        target_percent: float,
        progress_color: str,
        percent_text_id: int
    ) -> None:
        """启动环形图动画
        
        Args:
            canvas: Canvas对象
            center_x: 中心X坐标
            center_y: 中心Y坐标
            target_percent: 目标百分比
            progress_color: 进度颜色
            percent_text_id: 百分比文本ID
        """
        animation_start_time = time.time()
        
        # 取消之前的动画
        if hasattr(canvas, '_animation_job') and canvas._animation_job:
            self.window.after_cancel(canvas._animation_job)
        
        def animate_progress() -> None:
            if not canvas.winfo_exists():
                return
            
            elapsed = time.time() - animation_start_time
            progress = min(elapsed / ANIMATION_DURATION_SECONDS, 1.0)
            eased_progress = ease_out_cubic(progress)
            current_percent = target_percent * eased_progress
            
            draw_progress_ring(
                canvas, center_x, center_y, RING_RADIUS, RING_LINE_WIDTH,
                current_percent, progress_color, tag="progress",
                skip_full_highlight=(target_percent >= 100)
            )
            
            canvas.itemconfig(percent_text_id, text=f"{current_percent:.1f}%")
            
            if progress < 1.0:
                canvas._animation_job = self.window.after(
                    ANIMATION_FRAME_INTERVAL_MS, animate_progress
                )
            else:
                canvas.itemconfig(percent_text_id, text=f"{target_percent:.1f}%")
                canvas._animation_job = None
                
                if target_percent >= 100:
                    draw_progress_ring(
                        canvas, center_x, center_y, RING_RADIUS, RING_LINE_WIDTH,
                        target_percent, progress_color, tag="progress",
                        skip_full_highlight=True
                    )
                    animate_completion_celebration(
                        canvas, center_x, center_y,
                        RING_RADIUS, RING_LINE_WIDTH, progress_color,
                        self.window, draw_progress_ring
                    )
                else:
                    draw_progress_ring(
                        canvas, center_x, center_y, RING_RADIUS, RING_LINE_WIDTH,
                        target_percent, progress_color, tag="progress"
                    )
        
        # 延迟启动动画，等待left panel渲染完成
        self.window.after_idle(animate_progress)
    
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
        judge_frame = tk.Frame(parent, bg=Colors.WHITE)
        judge_frame.pack(pady=(30, 0))
        
        perfect = judge_data["perfect"]
        good = judge_data["good"]
        bad = judge_data["bad"]
        
        perfect_text = f"{perfect:,}"
        good_text = f"{good:,}"
        bad_text = f"{bad:,}"
        full_text = f"{perfect_text} - {good_text} - {bad_text}"
        
        font_obj = _create_font_object(get_cjk_font(10))
        text_width = font_obj.measure(full_text)
        canvas_width = max(250, text_width + 20)
        
        judge_canvas = ctk.CTkCanvas(
            judge_frame,
            width=canvas_width,
            height=25,
            bg=Colors.WHITE,
            highlightthickness=0
        )
        judge_canvas.pack()
        
        center_x_judge = canvas_width // 2
        current_x = center_x_judge - text_width // 2
        
        # 绘制perfect
        perfect_width = font_obj.measure(perfect_text)
        judge_canvas.create_text(
            current_x + perfect_width // 2, 12,
            text=perfect_text,
            font=get_cjk_font(10),
            fill=JUDGE_COLORS["perfect"],
            anchor="center"
        )
        current_x += perfect_width + font_obj.measure(" - ")
        
        # 绘制good
        good_width = font_obj.measure(good_text)
        judge_canvas.create_text(
            current_x + good_width // 2, 12,
            text=good_text,
            font=get_cjk_font(10),
            fill=JUDGE_COLORS["good"],
            anchor="center"
        )
        current_x += good_width + font_obj.measure(" - ")
        
        # 绘制bad
        bad_width = font_obj.measure(bad_text)
        judge_canvas.create_text(
            current_x + bad_width // 2, 12,
            text=bad_text,
            font=get_cjk_font(10),
            fill=JUDGE_COLORS["bad"],
            anchor="center"
        )
        
        # 绘制分隔符
        sep_width = font_obj.measure(" - ")
        sep1_x = center_x_judge - text_width // 2 + perfect_width
        sep2_x = sep1_x + sep_width + good_width
        judge_canvas.create_text(
            sep1_x + sep_width // 2, 12,
            text=" - ",
            font=get_cjk_font(10),
            fill=JUDGE_COLORS["separator"],
            anchor="center"
        )
        judge_canvas.create_text(
            sep2_x + sep_width // 2, 12,
            text=" - ",
            font=get_cjk_font(10),
            fill=JUDGE_COLORS["separator"],
            anchor="center"
        )
        
        return judge_canvas
    
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
        neo_result = _load_neo_content(self.storage_dir)
        if neo_result is None:
            return None
        
        neo_text, text_color = neo_result
        
        neo_frame = tk.Frame(parent, bg=Colors.WHITE)
        neo_frame.pack(pady=(55, 0))
        
        # 确定显示的文本
        if neo_text is None:
            # 使用翻译键
            if text_color == NEO_GOOD_COLOR:
                display_text = self.t("good_neo")
            else:
                display_text = self.t("bad_neo")
        else:
            display_text = neo_text
        
        # 狂信徒路线使用深红色
        if is_fanatic_route:
            text_color = NEO_FANATIC_COLOR
        
        neo_label = tk.Label(
            neo_frame,
            text=display_text,
            font=get_cjk_font(14),
            fg=text_color,
            bg=Colors.WHITE,
            wraplength=200
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
        collected_stickers, stickers_percent = _extract_sticker_data(save_data)
        
        # 检查sticker数量是否有变化
        if (self._last_sticker_count is not None and
            self._last_sticker_count == collected_stickers):
            return
        
        is_fanatic_route = _is_fanatic_route(save_data)
        whole_total_mp = save_data.get("wholeTotalMP", 0)
        judge_data = _extract_judge_data(save_data)
        
        if not parent or not parent.winfo_exists():
            self._stats_widgets.clear()
            return
        
        # 验证widget有效性
        if not self._validate_widgets():
            self._stats_widgets.clear()
            self.update(parent, save_data)
            return
        
        sticker_canvas = self._stats_widgets['sticker_canvas']
        mp_label_value = self._stats_widgets.get('mp_label_value')
        judge_canvas = self._stats_widgets.get('judge_canvas')
        
        # 获取canvas尺寸
        canvas_width = sticker_canvas.winfo_width()
        canvas_height = sticker_canvas.winfo_height()
        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width = self._stats_widgets.get('canvas_size', CANVAS_SIZE)
            canvas_height = canvas_width
        
        center_x = canvas_width // 2
        center_y = canvas_height // 2
        progress_color = _get_progress_color(stickers_percent, is_fanatic_route)
        
        # 更新环形图
        self._update_sticker_ring_incremental(
            sticker_canvas, center_x, center_y, stickers_percent,
            progress_color, collected_stickers
        )
        
        # 更新MP显示
        if mp_label_value and mp_label_value.winfo_exists():
            mp_label_value.config(text=f"{whole_total_mp:,}")
        
        # 更新判定统计
        if judge_canvas and judge_canvas.winfo_exists():
            self._update_judge_display_incremental(judge_canvas, judge_data)
        
        # 更新NEO显示
        self._update_neo_display_incremental(is_fanatic_route)
        
        # 更新乱码效果
        if is_fanatic_route:
            self._setup_gibberish_effect(
                sticker_canvas, stickers_percent, collected_stickers,
                mp_label_value, whole_total_mp, judge_canvas, judge_data,
                self._stats_widgets.get('neo_label')
            )
        else:
            self._reset_gibberish_state()
        
        self._last_sticker_count = collected_stickers
    
    def _validate_widgets(self) -> bool:
        """验证widget是否有效
        
        Returns:
            widget是否有效
        """
        sticker_canvas = self._stats_widgets.get('sticker_canvas')
        if not sticker_canvas or not sticker_canvas.winfo_exists():
            return False
        
        mp_label_value = self._stats_widgets.get('mp_label_value')
        if mp_label_value and not mp_label_value.winfo_exists():
            return False
        
        judge_canvas = self._stats_widgets.get('judge_canvas')
        if judge_canvas and not judge_canvas.winfo_exists():
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
        
        # 检查背景环是否存在
        if not canvas.find_withtag("background_ring"):
            self._draw_background_ring(canvas, center_x, center_y)
        
        # 重新创建文本
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
        
        # 启动动画
        radius = self._stats_widgets.get('radius', RING_RADIUS)
        line_width = self._stats_widgets.get('line_width', RING_LINE_WIDTH)
        self._start_ring_animation(
            canvas, center_x, center_y, stickers_percent,
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
        canvas.delete("all")
        
        perfect = judge_data["perfect"]
        good = judge_data["good"]
        bad = judge_data["bad"]
        
        perfect_text = f"{perfect:,}"
        good_text = f"{good:,}"
        bad_text = f"{bad:,}"
        full_text = f"{perfect_text} - {good_text} - {bad_text}"
        
        font_obj = _create_font_object(get_cjk_font(10))
        text_width = font_obj.measure(full_text)
        canvas_width = max(250, text_width + 20)
        canvas.config(width=canvas_width)
        
        center_x_judge = canvas_width // 2
        current_x = center_x_judge - text_width // 2
        
        # 绘制perfect
        perfect_width = font_obj.measure(perfect_text)
        canvas.create_text(
            current_x + perfect_width // 2, 12,
            text=perfect_text,
            font=get_cjk_font(10),
            fill=JUDGE_COLORS["perfect"],
            anchor="center"
        )
        current_x += perfect_width + font_obj.measure(" - ")
        
        # 绘制good
        good_width = font_obj.measure(good_text)
        canvas.create_text(
            current_x + good_width // 2, 12,
            text=good_text,
            font=get_cjk_font(10),
            fill=JUDGE_COLORS["good"],
            anchor="center"
        )
        current_x += good_width + font_obj.measure(" - ")
        
        # 绘制bad
        bad_width = font_obj.measure(bad_text)
        canvas.create_text(
            current_x + bad_width // 2, 12,
            text=bad_text,
            font=get_cjk_font(10),
            fill=JUDGE_COLORS["bad"],
            anchor="center"
        )
        
        # 绘制分隔符
        sep_width = font_obj.measure(" - ")
        sep1_x = center_x_judge - text_width // 2 + perfect_width
        sep2_x = sep1_x + sep_width + good_width
        canvas.create_text(
            sep1_x + sep_width // 2, 12,
            text=" - ",
            font=get_cjk_font(10),
            fill=JUDGE_COLORS["separator"],
            anchor="center"
        )
        canvas.create_text(
            sep2_x + sep_width // 2, 12,
            text=" - ",
            font=get_cjk_font(10),
            fill=JUDGE_COLORS["separator"],
            anchor="center"
        )
    
    def _update_neo_display_incremental(self, is_fanatic_route: bool) -> None:
        """增量更新NEO显示
        
        Args:
            is_fanatic_route: 是否为狂信徒路线
        """
        neo_label = self._stats_widgets.get('neo_label')
        if not neo_label or not neo_label.winfo_exists():
            return
        
        neo_result = _load_neo_content(self.storage_dir)
        if neo_result is None:
            return
        
        neo_text, text_color = neo_result
        
        # 确定显示的文本
        if neo_text is None:
            if text_color == NEO_GOOD_COLOR:
                display_text = self.t("good_neo")
            else:
                display_text = self.t("bad_neo")
        else:
            display_text = neo_text
        
        # 狂信徒路线使用深红色
        if is_fanatic_route:
            text_color = NEO_FANATIC_COLOR
        
        neo_label.config(text=display_text, fg=text_color)
    
    def _setup_gibberish_effect(
        self,
        sticker_canvas: ctk.CTkCanvas,
        stickers_percent: float,
        collected_stickers: int,
        mp_label_value: Optional[tk.Label],
        whole_total_mp: int,
        judge_canvas: Optional[ctk.CTkCanvas],
        judge_data: Dict[str, int],
        neo_label: Optional[tk.Label]
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
        """
        self._gibberish_widgets.clear()
        self._original_texts.clear()
        
        center_x = self._stats_widgets.get('center_x', CANVAS_SIZE // 2)
        center_y = self._stats_widgets.get('center_y', CANVAS_SIZE // 2)
        
        # 添加canvas文本到乱码列表
        all_text_ids = [
            item for item in sticker_canvas.find_all()
            if sticker_canvas.type(item) == 'text'
        ]
        if len(all_text_ids) >= 3:
            self._add_gibberish_canvas_text(
                sticker_canvas, all_text_ids[-3], center_x, center_y - 20,
                get_cjk_font(12, "bold"), self.t('stickers_statistics')
            )
            self._add_gibberish_canvas_text(
                sticker_canvas, all_text_ids[-2], center_x, center_y + 2,
                get_cjk_font(20, "bold"), f"{stickers_percent:.1f}%"
            )
            self._add_gibberish_canvas_text(
                sticker_canvas, all_text_ids[-1], center_x, center_y + 22,
                get_cjk_font(11), f"{collected_stickers}/{TOTAL_STICKERS}"
            )
        
        # 添加MP标签
        mp_label_title = self._stats_widgets.get('mp_label_title')
        if mp_label_title:
            self._add_gibberish_label(mp_label_title, self.t("total_mp"))
        if mp_label_value:
            self._add_gibberish_label(mp_label_value, f"{whole_total_mp:,}")
        
        # 添加判定canvas
        if judge_canvas:
            full_text = f"{judge_data['perfect']:,} - {judge_data['good']:,} - {judge_data['bad']:,}"
            font_obj = _create_font_object(get_cjk_font(10))
            text_width = font_obj.measure(full_text)
            canvas_width = max(250, text_width + 20)
            self._add_gibberish_judge_canvas(
                judge_canvas, judge_data, canvas_width, font_obj, text_width
            )
        
        # 添加NEO标签
        if neo_label and neo_label.winfo_exists():
            neo_result = _load_neo_content(self.storage_dir)
            if neo_result:
                neo_text, _ = neo_result
                if neo_text is None:
                    if neo_result[1] == NEO_GOOD_COLOR:
                        display_text = self.t("good_neo")
                    else:
                        display_text = self.t("bad_neo")
                else:
                    display_text = neo_text
                self._add_gibberish_label(neo_label, display_text)
        
        self._update_gibberish_texts()
    
    def _add_gibberish_canvas_text(
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
    
    def _add_gibberish_label(self, widget: tk.Label, original_text: str) -> None:
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
    
    def _add_gibberish_judge_canvas(
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
                self._update_gibberish_canvas_text(widget_info, gibberish_text)
            elif widget_info['type'] == 'tk_label':
                self._update_gibberish_label(widget_info, gibberish_text)
            elif widget_info['type'] == 'judge_canvas':
                self._update_gibberish_judge_canvas(widget_info)
        
        self._gibberish_update_job = self.window.after(
            GIBBERISH_UPDATE_INTERVAL_MS, self._update_gibberish_texts
        )
    
    def _update_gibberish_canvas_text(
        self,
        widget_info: Dict[str, Any],
        gibberish_text: str
    ) -> None:
        """更新canvas文本为乱码
        
        Args:
            widget_info: widget信息字典
            gibberish_text: 乱码文本
        """
        canvas = widget_info['canvas']
        if not canvas or not canvas.winfo_exists():
            return
        
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
    
    def _update_gibberish_label(
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
        if widget and widget.winfo_exists():
            widget.config(text=gibberish_text, fg=NEO_FANATIC_COLOR)
    
    def _update_gibberish_judge_canvas(self, widget_info: Dict[str, Any]) -> None:
        """更新判定canvas为乱码
        
        Args:
            widget_info: widget信息字典
        """
        canvas = widget_info['canvas']
        if not canvas or not canvas.winfo_exists():
            return
        
        canvas.delete("all")
        
        perfect_text = generate_gibberish_text(f"{widget_info['perfect']:,}")
        good_text = generate_gibberish_text(f"{widget_info['good']:,}")
        bad_text = generate_gibberish_text(f"{widget_info['bad']:,}")
        full_text = f"{perfect_text} - {good_text} - {bad_text}"
        
        font_obj = widget_info['font_obj']
        text_width = font_obj.measure(full_text)
        center_x = widget_info['canvas_width'] // 2
        current_x = center_x - text_width // 2
        
        # 绘制perfect
        perfect_width = font_obj.measure(perfect_text)
        canvas.create_text(
            current_x + perfect_width // 2, 12,
            text=perfect_text,
            font=get_cjk_font(10),
            fill=NEO_FANATIC_COLOR,
            anchor="center"
        )
        current_x += perfect_width + font_obj.measure(" - ")
        
        # 绘制good
        good_width = font_obj.measure(good_text)
        canvas.create_text(
            current_x + good_width // 2, 12,
            text=good_text,
            font=get_cjk_font(10),
            fill=NEO_FANATIC_COLOR,
            anchor="center"
        )
        current_x += good_width + font_obj.measure(" - ")
        
        # 绘制bad
        bad_width = font_obj.measure(bad_text)
        canvas.create_text(
            current_x + bad_width // 2, 12,
            text=bad_text,
            font=get_cjk_font(10),
            fill=NEO_FANATIC_COLOR,
            anchor="center"
        )
        
        # 绘制分隔符
        sep_width = font_obj.measure(" - ")
        sep1_x = center_x - text_width // 2 + perfect_width
        sep2_x = sep1_x + sep_width + good_width
        canvas.create_text(
            sep1_x + sep_width // 2, 12,
            text=" - ",
            font=get_cjk_font(10),
            fill=NEO_FANATIC_COLOR,
            anchor="center"
        )
        canvas.create_text(
            sep2_x + sep_width // 2, 12,
            text=" - ",
            font=get_cjk_font(10),
            fill=NEO_FANATIC_COLOR,
            anchor="center"
        )
