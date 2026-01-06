"""统计面板常量定义

集中管理统计面板相关的所有常量配置。
"""

from typing import Final, List, Tuple

from src.utils.styles import Colors

# 贴纸相关
TOTAL_STICKERS: Final[int] = 132

# Canvas尺寸
CANVAS_SIZE: Final[int] = 280
RING_RADIUS: Final[int] = 100
RING_LINE_WIDTH: Final[int] = 30

# 动画配置
ANIMATION_DURATION_SECONDS: Final[float] = 1.5
ANIMATION_FRAME_INTERVAL_MS: Final[int] = 33  # ~30fps
GIBBERISH_UPDATE_INTERVAL_MS: Final[int] = 150

# 贴纸百分比颜色阈值（按百分比降序排列，用于二分查找）
STICKER_COLOR_THRESHOLDS: Final[List[Tuple[int, str]]] = [
    (100, "#FFD54F"),  # 100% - 金色
    (95, "#81C784"),   # 95%+ - 绿色
    (90, "#4DB6AC"),  # 90%+ - 青绿色
    (75, "#4FC3F7"),  # 75%+ - 浅蓝色
    (0, "#64B5F6"),   # 默认 - 蓝色
]
FANATIC_ROUTE_COLOR: Final[str] = "#BF0204"

# 文本偏移量
TITLE_Y_OFFSET: Final[int] = -30
PERCENT_Y_OFFSET: Final[int] = 2
COUNT_Y_OFFSET: Final[int] = 40

# 判定统计颜色
JUDGE_COLORS: Final[dict[str, str]] = {
    "perfect": "#CC6DAE",
    "good": "#F5CE88",
    "bad": "#6DB7AB",
    "separator": Colors.TEXT_MUTED,
}

# 判定统计绘制配置
JUDGE_SEPARATOR: Final[str] = " - "
JUDGE_CANVAS_HEIGHT: Final[int] = 25
JUDGE_TEXT_Y_POSITION: Final[int] = 12
MIN_JUDGE_CANVAS_WIDTH: Final[int] = 250
CANVAS_WIDTH_PADDING: Final[int] = 20

# NEO文件相关
NEO_FILENAME: Final[str] = "NEO.sav"
NEO_GOOD_MESSAGE: Final[str] = '"キミたちに永遠の祝福を"'
NEO_BAD_MESSAGE: Final[str] = '"オマエに永遠の制裁を"'
NEO_GOOD_COLOR: Final[str] = "#FFEB9E"
NEO_BAD_COLOR: Final[str] = "#FF0000"
NEO_DEFAULT_COLOR: Final[str] = "#000000"
NEO_FANATIC_COLOR: Final[str] = "#8b0000"

# 背景环配置
BACKGROUND_RING_OFFSETS: Final[List[Tuple[float, int]]] = [
    (0.0, RING_LINE_WIDTH + 2),
    (0.5, RING_LINE_WIDTH + 1),
    (1.0, RING_LINE_WIDTH),
]

