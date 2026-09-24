"""「查看达成条件」窗口：结局 / 贴纸 / NG 场景的解锁条件，用 Canvas 画成卡片列表

未收集的排在前面（红色卡片），已收集的在后面（绿色卡片）。
"""

import platform
import tkinter as tk
from tkinter import Scrollbar
from tkinter import font as tkfont
from typing import Callable, List, Literal, Set, Tuple

import customtkinter as ctk

from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import set_window_icon

TEXT_SELECT_CURSOR = "ibeam" if platform.system() == "Windows" else "xterm"

CARD_PADDING = 16
CARD_RADIUS = 12
CARD_MARGIN = 12
CARD_WIDTH = 780
SHADOW_OFFSET = 3
LINE_HEIGHT = 18
# 先按 1 倍尺寸排版，最后整体放大
SCALE_FACTOR = 1.5

COLORS = {
    "bg": "#f5f5f7",
    "missing_card": "#fff0f3",
    "missing_border": "#ffb3c1",
    "missing_shadow": "#ffd6e0",
    "missing_title": "#c9184a",
    "missing_status": "#ff4d6d",
    "missing_text": "#590d22",
    "collected_card": "#f0fdf4",
    "collected_border": "#86efac",
    "collected_shadow": "#bbf7d0",
    "collected_title": "#15803d",
    "collected_status": "#22c55e",
    "collected_text": "#14532d",
    "header_bg": "#ffffff",
    "header_text": "#1f2937",
    "hint_text": "#dc2626",
}

Kind = Literal["ending", "sticker", "ng_scene"]


def create_rounded_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
                        radius: float, **kwargs) -> int:
    """用平滑多边形在 Canvas 上画圆角矩形"""
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1, x1 + radius, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def wrap_text(text: str, font: tkfont.Font, max_width: int) -> List[str]:
    """按像素宽度逐字换行（条件文本是中日文，没有空格可断）"""
    lines: List[str] = []
    current = ""
    for char in text:
        if current and font.measure(current + char) > max_width:
            lines.append(current)
            current = char
        else:
            current += char
    if current:
        lines.append(current)
    return lines or [text]


def show_requirements(window: tk.Misc, t: Callable[[str], str], title_key: str,
                      items: List[Tuple[str, str]], collected: Set[str], id_prefix: str, kind: Kind) -> None:
    """打开达成条件窗口

    Args:
        items: [(编号, 条件文本)]
        collected: 已收集的编号
        id_prefix: 卡片标题中编号前的前缀（"END"、"#" 等）
    """
    top = tk.Toplevel(window.nametowidget("."))
    title_text = t(title_key) + " - " + t("view_requirements")
    top.title(title_text)
    top.geometry("1275x975")
    top.configure(bg=Colors.MODAL_BG)
    set_window_icon(top)

    font_card_text = get_cjk_font(10)
    missing = [(i, cond) for i, cond in items if i not in collected]
    done = [(i, cond) for i, cond in items if i in collected]

    main_frame = tk.Frame(top, bg=COLORS["bg"])
    main_frame.pack(fill="both", expand=True)

    header = tk.Frame(main_frame, bg=COLORS["header_bg"], height=120)
    header.pack(fill="x")
    header.pack_propagate(False)
    tk.Label(header, text=title_text, font=get_cjk_font(16, "bold"), bg=COLORS["header_bg"],
             fg=COLORS["header_text"]).pack(anchor="w", padx=20, pady=(15, 5))

    if kind == "ng_scene":
        stats_text = f"✓ {t('ng_scene_count')}: {len(done)}/{len(items)}    "
        missing_key = "missing_omakes"
    elif kind == "sticker":
        stats_text = f"✓ {t('collected_stickers')}: {len(done)}    "
        missing_key = "missing_stickers_count"
    else:
        stats_text = f"✓ {t('collected_endings')}: {len(done)}    "
        missing_key = "missing_endings"
    if missing:
        stats_text += f"⚠ {t(missing_key)}: {len(missing)}"
    tk.Label(header, text=stats_text, font=get_cjk_font(12, "bold"), bg=COLORS["header_bg"],
             fg=COLORS["hint_text"] if missing else COLORS["collected_title"],
             wraplength=CARD_WIDTH).pack(anchor="w", padx=20, pady=(2, 12))

    tk.Frame(main_frame, height=1, bg="#e5e7eb").pack(fill="x")

    scroll_frame = tk.Frame(main_frame, bg=COLORS["bg"])
    scroll_frame.pack(fill="both", expand=True)
    canvas = ctk.CTkCanvas(scroll_frame, bg=COLORS["bg"], highlightthickness=0)
    scrollbar = Scrollbar(scroll_frame, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    status_suffix = "sticker" if kind == "sticker" else "ending"
    measure_font = tkfont.Font(family=font_card_text[0], size=font_card_text[1])
    y = 20
    for item_id, condition in missing + done:
        state = "missing" if item_id not in collected else "collected"
        mark = "❌ " if state == "missing" else "✓ "
        lines = wrap_text(condition, measure_font, CARD_WIDTH - CARD_PADDING * 2 - 20)
        text_height = len(lines) * LINE_HEIGHT
        height = 40 + text_height + CARD_PADDING * 2
        x1, y1, x2, y2 = 25, y, 25 + CARD_WIDTH, y + height
        card_color = COLORS[f"{state}_card"]
        border_color = COLORS[f"{state}_border"]

        create_rounded_rect(canvas, x1 + SHADOW_OFFSET, y1 + SHADOW_OFFSET, x2 + SHADOW_OFFSET,
                            y2 + SHADOW_OFFSET, CARD_RADIUS, fill=COLORS[f"{state}_shadow"], outline="")
        create_rounded_rect(canvas, x1 - 1, y1 - 1, x2 + 1, y2 + 1, CARD_RADIUS, fill=border_color, outline="")
        create_rounded_rect(canvas, x1, y1, x2, y2, CARD_RADIUS, fill=card_color, outline="")
        canvas.create_text(x1 + CARD_PADDING, y1 + CARD_PADDING, text=f"{id_prefix}{item_id}",
                           font=get_cjk_font(13, "bold"), fill=COLORS[f"{state}_title"], anchor="nw")
        canvas.create_text(x2 - CARD_PADDING, y1 + CARD_PADDING,
                           text=mark + t(f"status_{state}_{status_suffix}"),
                           font=get_cjk_font(10, "bold"), fill=COLORS[f"{state}_status"], anchor="ne")
        line_y = y1 + 40
        canvas.create_line(x1 + CARD_PADDING, line_y, x2 - CARD_PADDING, line_y, fill=border_color, width=1)

        # 用只读 Text 显示条件，方便用户选中复制
        text_frame = tk.Frame(canvas, bg=card_color)
        text_widget = tk.Text(
            text_frame, wrap=tk.NONE, font=font_card_text, fg=COLORS[f"{state}_text"], bg=card_color,
            relief=tk.FLAT, borderwidth=0, highlightthickness=0, selectbackground="#4A90E2",
            selectforeground="white", cursor=TEXT_SELECT_CURSOR, padx=0, pady=0,
            spacing1=0, spacing2=0, spacing3=0,
        )
        text_widget.insert("1.0", "\n".join(lines))
        text_widget.config(state=tk.DISABLED)
        text_widget.pack(fill="both", expand=True)
        canvas.create_window(x1 + CARD_PADDING, line_y + 12, window=text_frame, anchor="nw",
                             width=CARD_WIDTH - CARD_PADDING * 2, height=text_height)
        y += height + CARD_MARGIN

    canvas.scale("all", 0, 0, SCALE_FACTOR, SCALE_FACTOR)
    canvas.configure(scrollregion=canvas.bbox("all"))

    def on_mousewheel(event: tk.Event) -> None:
        if event.delta:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif event.num == 4:
            canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            canvas.yview_scroll(1, "units")

    for widget in (canvas, top):
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(sequence, on_mousewheel)
