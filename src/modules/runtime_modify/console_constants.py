"""控制台模块常量定义"""

from typing import Final, List, Tuple

# 命令历史最大数量
MAX_HISTORY: Final[int] = 100

# 预设命令定义
SHORTCUT_COMMANDS: Final[List[Tuple[str, str]]] = [
    ("runtime_modify_console_cmd_display_save", "TYRANO.kag.menu.displaySavePage()"),
    ("runtime_modify_console_cmd_display_load", "TYRANO.kag.menu.displayLoadPage()"),
    ("runtime_modify_console_cmd_display_log", "TYRANO.kag.menu.displayLog()"),
    ("runtime_modify_console_cmd_set_quick_save", "TYRANO.kag.menu.setQuickSave()"),
    ("runtime_modify_console_cmd_load_quick_save", "TYRANO.kag.menu.loadQuickSave()"),
    ("runtime_modify_console_cmd_take_photo", "TYRANO.kag.ftag.startTag('sleepgame', { storage: 'photo.ks', next: false })"),
]
