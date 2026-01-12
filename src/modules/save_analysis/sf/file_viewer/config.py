"""文件查看器配置常量

定义文件查看器相关的配置常量和默认值。
"""

from typing import Final, FrozenSet

# 默认折叠字段
DEFAULT_SF_COLLAPSED_FIELDS: Final[list[str]] = ["record", "_tap_effect", "initialVars"]

# 存档文件名
SAVE_FILE_NAME: Final[str] = "DevilConnection_sf.sav"

# 时间延迟常量（毫秒）
CLOSE_CALLBACK_DELAY_MS: Final[int] = 100
REFRESH_AFTER_INJECT_DELAY_MS: Final[int] = 200

# 单行显示的列表字段（这些字段在JSON格式化时保持在一行内）
SINGLE_LINE_LIST_FIELDS: Final[FrozenSet[str]] = frozenset([
    "endings", "collectedEndings", "omakes", "characters",
    "collectedCharacters", "sticker", "gallery", "ngScene"
])

# UI 配置
DEFAULT_WINDOW_SIZE: Final[str] = "1200x900"
HINT_WRAPLENGTH: Final[int] = 850
CHECKBOX_PADX: Final[int] = 5

# 行号显示配置
LINE_NUMBER_WIDTH: Final[int] = 4
LINE_NUMBER_PADX: Final[int] = 5
LINE_NUMBER_PADY: Final[int] = 2

# 文本编辑器配置
TEXT_FONT_SIZE: Final[int] = 10
TEXT_TABS: Final[tuple[str, ...]] = ("2c", "4c", "6c", "8c", "10c", "12c", "14c", "16c")

# 搜索高亮颜色
SEARCH_HIGHLIGHT_COLOR: Final[str] = "yellow"

# 用户编辑高亮颜色
USER_EDIT_HIGHLIGHT_COLOR: Final[str] = "#fff9c4"
