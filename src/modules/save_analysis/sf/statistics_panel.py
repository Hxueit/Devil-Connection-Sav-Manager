"""sf 存档分析页右侧的统计面板

从上到下：贴纸收集进度环、总 MP、判定统计（perfect - good - bad）、NEO.sav 的内容。
狂信徒路线时所有文字变成深红色并不断随机变成乱码。
"""

import logging
import math
import random
import re
import string
import time
import tkinter as tk
import urllib.parse
from pathlib import Path
from tkinter import font as tkfont
from typing import Any, Callable, Dict, List, Optional, Tuple

import customtkinter as ctk

from src.constants import NEO_SAVE_FILENAME, TOTAL_STICKERS
from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import widget_alive

from .fields import is_fanatic_route

logger = logging.getLogger(__name__)

# 进度环
CANVAS_SIZE = 280
RING_RADIUS = 100
RING_LINE_WIDTH = 30
BACKGROUND_RING_COLOR = "#e0e0e0"
ANIMATION_DURATION_SECONDS = 1.5
ANIMATION_FRAME_INTERVAL_MS = 33  # 约 30fps
CELEBRATION_DURATION_SECONDS = 0.6

# 贴纸百分比 -> 进度环颜色（从高到低匹配）
STICKER_COLOR_THRESHOLDS = [
    (100, "#FFD54F"),  # 金色
    (95, "#81C784"),   # 绿色
    (90, "#4DB6AC"),   # 青绿色
    (75, "#4FC3F7"),   # 浅蓝色
    (0, "#64B5F6"),    # 蓝色
]
FANATIC_RING_COLOR = "#BF0204"
FANATIC_TEXT_COLOR = "#8b0000"
GIBBERISH_UPDATE_INTERVAL_MS = 150

# 判定统计
JUDGE_COLORS = {"perfect": "#CC6DAE", "good": "#F5CE88", "bad": "#6DB7AB"}
JUDGE_SEPARATOR = " - "
JUDGE_CANVAS_HEIGHT = 25
JUDGE_TEXT_Y = 12
MIN_JUDGE_CANVAS_WIDTH = 250

# NEO.sav：游戏在两种结局下写入固定台词，其他情况下内容由玩家决定
NEO_GOOD_MESSAGE = '"キミたちに永遠の祝福を"'
NEO_BAD_MESSAGE = '"オマエに永遠の制裁を"'
NEO_GOOD_COLOR = "#FFEB9E"
NEO_BAD_COLOR = "#FF0000"
NEO_DEFAULT_COLOR = "#000000"
NEO_WRAPLENGTH = 400

_NUMERIC_STRING = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


# ---------------------------------------------------------------- 数据提取

def get_progress_color(stickers_percent: float, fanatic_route: bool) -> str:
    if fanatic_route:
        return FANATIC_RING_COLOR
    for threshold, color in STICKER_COLOR_THRESHOLDS:
        if stickers_percent >= threshold:
            return color
    return STICKER_COLOR_THRESHOLDS[-1][1]


def extract_sticker_data(save_data: Dict[str, Any]) -> Tuple[int, float]:
    """返回 (已收集贴纸数, 百分比)"""
    stickers = save_data.get("sticker")
    count = len(set(stickers)) if isinstance(stickers, list) else 0
    return count, count / TOTAL_STICKERS * 100.0


def extract_judge_data(save_data: Dict[str, Any]) -> Dict[str, int]:
    judge_counts = save_data.get("judgeCounts")
    if not isinstance(judge_counts, dict):
        judge_counts = {}
    result = {}
    for key in ("perfect", "good", "bad"):
        value = judge_counts.get(key)
        result[key] = int(value) if isinstance(value, (int, float)) else 0
    return result


def _format_number(value: float) -> str:
    if value.is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def format_mp_value_for_display(mp: Any) -> Tuple[str, bool]:
    """格式化总 MP，返回 (显示文本, 是否异常)

    存档被改坏时 wholeTotalMP 可能是任意字符串，原样显示并标记为异常。
    """
    if mp is None:
        return "0", False
    if isinstance(mp, (bool, int)):
        return f"{int(mp):,}", False
    if isinstance(mp, float):
        if not math.isfinite(mp):
            return str(mp), True
        return _format_number(mp), False
    if isinstance(mp, str):
        text = mp.strip()
        if not text:
            return "-", True
        normalized = text.replace(",", "")
        if _NUMERIC_STRING.fullmatch(normalized):
            if "." in normalized:
                return _format_number(float(normalized)), False
            return f"{int(normalized):,}", False
        return text, True
    return str(mp), True


def load_neo_content(storage_dir: str) -> Optional[Tuple[Optional[str], str]]:
    """读取 NEO.sav，返回 (自定义文本, 颜色)；固定台词时文本为 None；文件不存在返回 None"""
    if not storage_dir:
        return None
    neo_path = Path(storage_dir) / NEO_SAVE_FILENAME
    try:
        content = urllib.parse.unquote(neo_path.read_text(encoding="utf-8").strip())
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("Failed to read %s: %s", neo_path, e)
        return None
    if not content:
        return None
    if content == NEO_GOOD_MESSAGE:
        return None, NEO_GOOD_COLOR
    if content == NEO_BAD_MESSAGE:
        return None, NEO_BAD_COLOR
    return content, NEO_DEFAULT_COLOR


def generate_gibberish_text(original_text: str) -> str:
    """把 20%~50% 的字符替换成随机字符"""
    if not original_text:
        return original_text
    count = max(1, int(len(original_text) * random.uniform(0.2, 0.5)))
    result = list(original_text)
    for pos in random.sample(range(len(result)), min(count, len(result))):
        result[pos] = random.choice(string.printable)
    return "".join(result)


# ---------------------------------------------------------------- 进度环绘制

def ease_out_cubic(progress: float) -> float:
    """三次缓出：progress ∈ [0, 1] -> [0, 1]，开始快、结束慢"""
    return 1.0 - pow(1.0 - progress, 3)


def _interpolate_color(color1: str, color2: str, factor: float) -> str:
    c1 = [int(color1[i:i + 2], 16) for i in (1, 3, 5)]
    c2 = [int(color2[i:i + 2], 16) for i in (1, 3, 5)]
    r, g, b = (max(0, min(255, int(a + (b - a) * factor))) for a, b in zip(c1, c2))
    return f"#{r:02x}{g:02x}{b:02x}"


def _lighten(color: str, factor: float) -> str:
    return _interpolate_color(color, "#FFFFFF", factor)


def _ring_bbox(cx: int, cy: int) -> Tuple[int, int, int, int]:
    return cx - RING_RADIUS, cy - RING_RADIUS, cx + RING_RADIUS, cy + RING_RADIUS


def draw_progress_ring(canvas: tk.Canvas, cx: int, cy: int, percent: float, color: str,
                       skip_full_highlight: bool = False) -> None:
    """画进度环：带外发光，末端 8 段渐变高亮；100% 时整环高亮

    skip_full_highlight: 100% 时先不整环高亮（庆祝动画会把高亮蔓延到整环）
    """
    rounded = round(percent)
    if rounded <= 0:
        canvas.delete("progress", "progress_glow", "progress_highlight")
        return

    # extent=-360 会让圆弧整个消失，用 -359.9 代替，视觉上没有区别
    extent = -359.9 if rounded >= 100 else -(percent / 100) * 360
    is_complete = rounded >= 100 and not skip_full_highlight
    highlight_color = _lighten(color, 0.35)
    arc_color = highlight_color if is_complete else color
    glow_color = _lighten(arc_color, 0.65)
    bbox = _ring_bbox(cx, cy)

    # 动画每帧都会调用，已有圆弧时只改属性，避免重复创建
    glow = canvas.find_withtag("progress_glow_arc")
    if glow:
        canvas.itemconfig(glow[0], extent=extent, outline=glow_color)
    else:
        canvas.create_arc(*bbox, start=90, extent=extent, style=tk.ARC, outline=glow_color,
                          width=RING_LINE_WIDTH + 6, tags=("progress_glow", "progress_glow_arc"))
    arc = canvas.find_withtag("progress_arc")
    if arc:
        canvas.itemconfig(arc[0], extent=extent, outline=arc_color)
    else:
        canvas.create_arc(*bbox, start=90, extent=extent, style=tk.ARC, outline=arc_color,
                          width=RING_LINE_WIDTH, tags=("progress", "progress_arc"))

    canvas.delete("progress_highlight")
    if is_complete:
        return
    # 末端 8 小段（每段 1%）从主色渐变到高亮色
    highlight_segments = min(8, rounded)
    segment_angle = 360 / 100
    segments = min(rounded, 99)
    for i in range(max(0, segments - highlight_segments), segments):
        factor = 1 - (segments - 1 - i) / highlight_segments
        start = math.radians(90 - i * segment_angle)
        end = math.radians(90 - (i + 1) * segment_angle)
        canvas.create_line(
            cx + RING_RADIUS * math.cos(start), cy - RING_RADIUS * math.sin(start),
            cx + RING_RADIUS * math.cos(end), cy - RING_RADIUS * math.sin(end),
            fill=_interpolate_color(color, highlight_color, factor),
            width=RING_LINE_WIDTH, capstyle=tk.ROUND, tags="progress_highlight",
        )


def draw_background_ring(canvas: tk.Canvas, cx: int, cy: int) -> None:
    for offset, width in ((0.0, RING_LINE_WIDTH + 2), (0.5, RING_LINE_WIDTH + 1), (1.0, RING_LINE_WIDTH)):
        r = RING_RADIUS + offset
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=BACKGROUND_RING_COLOR,
                           width=int(width), tags="background_ring")


# ---------------------------------------------------------------- 面板

class StatisticsPanel:
    """统计面板；每次 update 都会重建内容并重新播放进度环动画"""

    def __init__(self, parent: tk.Widget, storage_dir: str, t: Callable[..., str]) -> None:
        self.storage_dir = storage_dir
        self.t = t
        self._ring_job: Optional[str] = None
        self._gibberish_job: Optional[str] = None
        # 狂信徒路线的乱码效果：[(刷新函数, 原文)]，每次刷新把原文打乱后交给刷新函数
        self._gibberish_targets: List[Tuple[Callable[[str], None], str]] = []

        self.container = tk.Frame(parent, bg=Colors.WHITE)
        self.container.pack(fill="both", expand=True, padx=10, pady=10)
        tk.Label(self.container, text=self.t("no_save_data"), font=get_cjk_font(12),
                 bg=Colors.WHITE).pack(pady=50)

    def update(self, save_data: Dict[str, Any]) -> None:
        if not widget_alive(self.container):
            return
        self._cancel_jobs()
        for child in self.container.winfo_children():
            child.destroy()

        fanatic = is_fanatic_route(save_data)
        self._create_sticker_ring(save_data, fanatic)
        self._create_mp_display(save_data.get("wholeTotalMP", 0), fanatic)
        self._create_judge_display(extract_judge_data(save_data), fanatic)
        self._create_neo_display(fanatic)
        if fanatic:
            self._update_gibberish()

    def _cancel_jobs(self) -> None:
        for job in (self._ring_job, self._gibberish_job):
            if job is not None:
                try:
                    self.container.after_cancel(job)
                except tk.TclError:
                    pass
        self._ring_job = self._gibberish_job = None
        self._gibberish_targets.clear()

    # ---- 贴纸进度环

    def _create_sticker_ring(self, save_data: Dict[str, Any], fanatic: bool) -> None:
        collected, percent = extract_sticker_data(save_data)
        frame = tk.Frame(self.container, bg=Colors.WHITE)
        frame.pack(pady=(0, 20))
        canvas = ctk.CTkCanvas(frame, width=CANVAS_SIZE, height=CANVAS_SIZE, bg=Colors.WHITE,
                               highlightthickness=0)
        canvas.pack()
        center = CANVAS_SIZE // 2
        draw_background_ring(canvas, center, center)

        title = self.t("stickers_statistics")
        count = f"{collected}/{TOTAL_STICKERS}"
        percent_text_id: Optional[int] = None
        if fanatic:
            # 三行文字都是深红色乱码（行距比正常时紧凑），百分比不跟随动画变化
            lines = [
                (center - 20, get_cjk_font(12, "bold"), title),
                (center + 2, get_cjk_font(20, "bold"), f"{percent:.1f}%"),
                (center + 22, get_cjk_font(11), count),
            ]
            for y, font, text in lines:
                item = canvas.create_text(center, y, text=text, font=font, fill=FANATIC_TEXT_COLOR)
                self._gibberish_targets.append((lambda s, i=item: canvas.itemconfig(i, text=s), text))
        else:
            canvas.create_text(center, center - 30, text=title, font=get_cjk_font(12, "bold"),
                               fill=Colors.TEXT_DARK)
            percent_text_id = canvas.create_text(center, center + 2, text="0.0%", font=get_cjk_font(20, "bold"),
                                                 fill=Colors.TEXT_DARK)
            canvas.create_text(center, center + 40, text=count, font=get_cjk_font(11), fill=Colors.TEXT_MUTED)
        self._animate_ring(canvas, center, percent, get_progress_color(percent, fanatic), percent_text_id)

    def _animate_ring(self, canvas: tk.Canvas, center: int, target: float, color: str,
                      percent_text_id: Optional[int]) -> None:
        """进度环从 0 增长到目标值（缓出）；到 100% 时再播放一次庆祝动画

        percent_text_id: 环中间的百分比文字，动画中跟着变化；None 表示不更新
        """
        start_time = time.time()

        def frame() -> None:
            self._ring_job = None
            if not widget_alive(canvas):
                return
            progress = min((time.time() - start_time) / ANIMATION_DURATION_SECONDS, 1.0)
            current = target * ease_out_cubic(progress)
            draw_progress_ring(canvas, center, center, current, color, skip_full_highlight=target >= 100)
            if progress < 1.0:
                if percent_text_id is not None:
                    canvas.itemconfig(percent_text_id, text=f"{current:.1f}%")
                self._ring_job = self.container.after(ANIMATION_FRAME_INTERVAL_MS, frame)
                return
            if percent_text_id is not None:
                canvas.itemconfig(percent_text_id, text=f"{target:.1f}%")
            if target >= 100:
                self._animate_celebration(canvas, center, color)
            else:
                draw_progress_ring(canvas, center, center, target, color)

        self._ring_job = self.container.after_idle(frame)

    def _animate_celebration(self, canvas: tk.Canvas, center: int, color: str) -> None:
        """100% 庆祝动画：高亮从末端的 8 段蔓延到整个环，结束后画成整环高亮"""
        canvas.delete("progress", "progress_glow", "progress_highlight")
        bbox = _ring_bbox(center, center)
        highlight_color = _lighten(color, 0.35)
        width = RING_LINE_WIDTH
        canvas.create_arc(*bbox, start=90, extent=-356.4, style=tk.ARC, outline=_lighten(color, 0.65),
                          width=width + 6, tags="celebration")
        canvas.create_arc(*bbox, start=90, extent=-356.4, style=tk.ARC, outline=color,
                          width=width, tags="celebration")
        glow_id = canvas.create_arc(*bbox, start=90, extent=0, style=tk.ARC,
                                    outline=_lighten(highlight_color, 0.65), width=width + 6, tags="celebration")
        arc_id = canvas.create_arc(*bbox, start=90, extent=0, style=tk.ARC, outline=highlight_color,
                                   width=width, tags="celebration")
        start_time = time.time()

        def frame() -> None:
            self._ring_job = None
            if not widget_alive(canvas):
                return
            progress = (time.time() - start_time) / CELEBRATION_DURATION_SECONDS
            if progress >= 1.0:
                canvas.delete("celebration")
                draw_progress_ring(canvas, center, center, 100, color)
                return
            segments = 8 + int((99 - 8) * ease_out_cubic(progress))
            extent = -segments * 360 / 100
            canvas.itemconfig(glow_id, extent=extent)
            canvas.itemconfig(arc_id, extent=extent)
            self._ring_job = self.container.after(20, frame)

        frame()

    # ---- MP / 判定 / NEO

    def _create_mp_display(self, mp: Any, fanatic: bool) -> None:
        frame = tk.Frame(self.container, bg=Colors.WHITE)
        frame.pack(pady=(0, 15))
        title_text = self.t("total_mp")
        value_text, is_anomalous = format_mp_value_for_display(mp)
        value_color = Colors.TEXT_WARNING_AQUA if is_anomalous else Colors.TEXT_INFO
        title = tk.Label(frame, text=title_text, font=get_cjk_font(12), bg=Colors.WHITE,
                         fg=FANATIC_TEXT_COLOR if fanatic else Colors.TEXT_MUTED)
        title.pack()
        value = tk.Label(frame, text=value_text, font=get_cjk_font(32, "bold"), bg=Colors.WHITE,
                         fg=FANATIC_TEXT_COLOR if fanatic else value_color)
        value.pack()
        if fanatic:
            self._gibberish_targets.append((lambda s: title.config(text=s), title_text))
            self._gibberish_targets.append((lambda s: value.config(text=s), value_text))

    def _create_judge_display(self, judge: Dict[str, int], fanatic: bool) -> None:
        frame = tk.Frame(self.container, bg=Colors.WHITE)
        frame.pack(pady=(30, 0))
        texts = [f"{judge[key]:,}" for key in ("perfect", "good", "bad")]
        family, size = get_cjk_font(10)[:2]
        font = tkfont.Font(family=family, size=size)
        width = max(MIN_JUDGE_CANVAS_WIDTH, font.measure(JUDGE_SEPARATOR.join(texts)) + 20)
        canvas = ctk.CTkCanvas(frame, width=width, height=JUDGE_CANVAS_HEIGHT, bg=Colors.WHITE,
                               highlightthickness=0)
        canvas.pack()

        def draw(parts: List[str], colors: List[str], separator_color: str) -> None:
            """把三个数字和分隔符居中排成一行，每段单独着色"""
            canvas.delete("all")
            separator_width = font.measure(JUDGE_SEPARATOR)
            x = width // 2 - font.measure(JUDGE_SEPARATOR.join(parts)) // 2
            for i, (text, color) in enumerate(zip(parts, colors)):
                text_width = font.measure(text)
                canvas.create_text(x + text_width // 2, JUDGE_TEXT_Y, text=text, font=get_cjk_font(10),
                                   fill=color, anchor="center")
                x += text_width
                if i < len(parts) - 1:
                    canvas.create_text(x + separator_width // 2, JUDGE_TEXT_Y, text=JUDGE_SEPARATOR,
                                       font=get_cjk_font(10), fill=separator_color, anchor="center")
                    x += separator_width

        if fanatic:
            # 三个数字分别打乱后整行重画（分隔符保持不变）
            def draw_gibberish(_: str) -> None:
                draw([generate_gibberish_text(text) for text in texts], [FANATIC_TEXT_COLOR] * 3,
                     FANATIC_TEXT_COLOR)

            self._gibberish_targets.append((draw_gibberish, ""))
        else:
            draw(texts, list(JUDGE_COLORS.values()), Colors.TEXT_MUTED)

    def _create_neo_display(self, fanatic: bool) -> None:
        neo = load_neo_content(self.storage_dir)
        if neo is None:
            return
        text, color = neo
        if text is None:
            text = self.t("good_neo") if color == NEO_GOOD_COLOR else self.t("bad_neo")
        frame = tk.Frame(self.container, bg=Colors.WHITE)
        frame.pack(pady=(55, 0))
        label = tk.Label(frame, text=text, font=get_cjk_font(14), fg=FANATIC_TEXT_COLOR if fanatic else color,
                         bg=Colors.WHITE, wraplength=NEO_WRAPLENGTH)
        label.pack()
        if fanatic:
            self._gibberish_targets.append((lambda s: label.config(text=s), text))

    # ---- 狂信徒路线的乱码效果

    def _update_gibberish(self) -> None:
        self._gibberish_job = None
        try:
            for apply, text in self._gibberish_targets:
                apply(generate_gibberish_text(text))
        except tk.TclError:
            return  # 控件已销毁
        self._gibberish_job = self.container.after(GIBBERISH_UPDATE_INTERVAL_MS, self._update_gibberish)
