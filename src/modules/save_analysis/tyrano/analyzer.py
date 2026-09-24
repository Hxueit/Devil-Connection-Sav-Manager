"""Tyrano 存档数据：读写 DevilConnection_tyrano_data.sav，并解析单个存档槽的信息

文件结构：{"data": [存档槽, 存档槽, ...], ...其他字段}
空存档槽的格式为 {"title": "NO SAVE", "save_date": "", "img_data": "", "stat": {}}
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.constants import TYRANO_SAVE_FILENAME
from src.modules.save_analysis.tyrano.constants import TYRANO_SAVES_PER_PAGE
from src.utils.sav_io import read_sav, write_sav

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 单个存档槽的解析
# ---------------------------------------------------------------------------

def is_empty_save(slot: Optional[Dict[str, Any]]) -> bool:
    """是否为空存档槽（NO SAVE）"""
    if not slot:
        return True
    if slot.get("title", "") == "NO SAVE":
        return True
    stat = slot.get("stat", {})
    return (slot.get("save_date", "") == "" and slot.get("img_data", "") == ""
            and isinstance(stat, dict) and len(stat) == 0)


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


@dataclass
class SaveInfo:
    """存档槽中用于显示的信息"""
    day: Optional[int] = None          # 第几天（后日谈时为后日谈的天数）
    is_epilogue: bool = False
    finished_count: int = 0            # 当天已完成的 3 个事件中完成了几个
    save_date: Optional[str] = None
    subtitle: Optional[str] = None

    def circles(self, done: str = "●", todo: str = "○") -> str:
        return "".join(done if i < self.finished_count else todo for i in range(3))


def extract_save_info(slot: Optional[Dict[str, Any]]) -> SaveInfo:
    """从存档槽的 stat.f 中读出天数、完成情况等信息"""
    if not slot:
        return SaveInfo()

    stat = slot.get("stat")
    f = stat.get("f") if isinstance(stat, dict) else None
    if not isinstance(f, dict):
        f = {}

    # day_epilogue 不为 0 时表示处于后日谈，此时显示后日谈的天数
    epilogue_day = _to_int(f.get("day_epilogue"))
    if epilogue_day:
        day, is_epilogue = epilogue_day, True
    else:
        day, is_epilogue = _to_int(f.get("day")), False

    # finished 按天存放，每天 3 个事件：第 N 天对应 finished[N*3 : N*3+3]
    finished = f.get("finished")
    if not isinstance(finished, list):
        finished = []
    if day is None or day < 0:
        finished_count = 0
    else:
        finished_count = min(len(finished[day * 3:day * 3 + 3]), 3)

    save_date = slot.get("save_date")
    subtitle = slot.get("subtitleText") if slot.get("subtitle") else None
    return SaveInfo(
        day=day,
        is_epilogue=is_epilogue,
        finished_count=finished_count,
        save_date=str(save_date) if save_date is not None else None,
        subtitle=str(subtitle) if subtitle else None,
    )


def day_text(info: SaveInfo, t: Callable[..., str]) -> str:
    """「3日目」/「后日谈2日目」，没有天数时返回空字符串"""
    if info.day is None:
        return ""
    key = "tyrano_epilogue_day_label" if info.is_epilogue else "tyrano_day_label"
    return t(key, day=info.day)


def describe_slot(slot: Optional[Dict[str, Any]], t: Callable[..., str]) -> str:
    """一行文字描述存档槽，如「3日目 · ●●○ · 2024/05/01 12:00:00 · 副标题」；无可用信息时返回空字符串"""
    if not slot:
        return ""
    info = extract_save_info(slot)
    parts = [day_text(info, t)]
    if info.day is not None and not info.is_epilogue:
        parts.append(info.circles())
    parts += [info.save_date, info.subtitle]
    return " · ".join(p for p in parts if p)


def step_page(page: int, total: int, delta: int) -> int:
    """翻页：从 page 向前/后翻 delta 页，首尾循环（第一页之前是最后一页）；没有页面时返回 0"""
    if total <= 0:
        return 0
    return (page - 1 + delta) % total + 1


# ---------------------------------------------------------------------------
# 整个存档文件
# ---------------------------------------------------------------------------

class TyranoAnalyzer:
    """读取 tyrano_data.sav，提供分页与修改（重排、清空、删除、导入、替换）功能

    所有修改都先写文件，写入成功后才更新内存中的数据。
    """

    def __init__(self, storage_dir: str) -> None:
        if not storage_dir:
            raise ValueError("storage_dir cannot be empty")
        self.storage_dir = Path(storage_dir)
        self.save_data: Optional[Dict[str, Any]] = None
        self.save_slots: List[Dict[str, Any]] = []
        self.current_page = 0   # 从 1 开始；没有存档时为 0
        self.total_pages = 0

    @property
    def file_path(self) -> Path:
        return self.storage_dir / TYRANO_SAVE_FILENAME

    def load_save_file(self) -> bool:
        """加载存档文件，成功返回 True；失败时清空数据并返回 False"""
        return self.set_save_data(self.read_file())

    def read_file(self) -> Optional[Dict[str, Any]]:
        """只读取并解码存档文件，不修改内存中的数据（可以在后台线程调用）；失败时返回 None"""
        try:
            save_data = read_sav(self.file_path)
        except FileNotFoundError:
            logger.warning("Tyrano save file not found: %s", self.file_path)
            return None
        except (OSError, ValueError) as e:
            logger.error("Failed to load %s: %s", self.file_path, e, exc_info=True)
            return None
        return save_data if isinstance(save_data, dict) else None

    def set_save_data(self, save_data: Optional[Dict[str, Any]]) -> bool:
        """使用 read_file() 读到的数据；None 表示读取失败，清空数据并返回 False"""
        if save_data is None:
            self.save_data = None
            self.save_slots = []
            self.current_page = self.total_pages = 0
            return False

        data = save_data.get("data")
        if not isinstance(data, list):
            logger.warning("'data' field missing or not a list in %s", self.file_path)
            data = []
        self.save_data = save_data
        self.save_slots = [slot for slot in data if isinstance(slot, dict)]
        self._repaginate()
        logger.info("Loaded %d tyrano save slots, %d pages", len(self.save_slots), self.total_pages)
        return True

    def _repaginate(self) -> None:
        count = len(self.save_slots)
        self.total_pages = (count + TYRANO_SAVES_PER_PAGE - 1) // TYRANO_SAVES_PER_PAGE
        self.current_page = 1 if count else 0

    # --- 分页 ---

    def get_current_page_slots(self) -> List[Optional[Dict[str, Any]]]:
        """当前页的 6 个存档槽，不足的位置用 None 补齐"""
        if not self.save_slots or self.current_page < 1:
            return []
        start = (self.current_page - 1) * TYRANO_SAVES_PER_PAGE
        page = self.save_slots[start:start + TYRANO_SAVES_PER_PAGE]
        return page + [None] * (TYRANO_SAVES_PER_PAGE - len(page))

    def set_page(self, page: int) -> bool:
        if 1 <= page <= self.total_pages:
            self.current_page = page
            return True
        return False

    # --- 修改 ---

    def _modify_slots(self, change: Callable[[List[Dict[str, Any]]], Optional[List[Dict[str, Any]]]],
                      repaginate: bool = False) -> bool:
        """读取磁盘上最新的存档 → change(存档槽列表) 得到新列表 → 写回文件 → 更新内存

        一定要重新读文件：玩家可能开着本工具同时在游戏里存档，
        如果直接用内存里的旧数据写回，会把游戏新存的档覆盖掉。
        change 返回 None 表示参数无效，不写文件。写入失败时内存状态保持不变。
        """
        try:
            latest = read_sav(self.file_path)
        except (OSError, ValueError) as e:
            logger.error("Failed to re-read %s before writing: %s", self.file_path, e)
            return False
        if not isinstance(latest, dict):
            logger.error("Unexpected save format in %s", self.file_path)
            return False
        data = latest.get("data")
        slots = [slot for slot in data if isinstance(slot, dict)] if isinstance(data, list) else []

        new_slots = change(slots)
        if new_slots is None:
            return False
        new_save_data = {**latest, "data": new_slots}
        try:
            write_sav(self.file_path, new_save_data)
        except (OSError, TypeError, ValueError) as e:
            logger.error("Failed to write save slots: %s", e, exc_info=True)
            return False

        page = self.current_page
        self.save_data = new_save_data
        self.save_slots = new_slots
        self._repaginate()
        if not repaginate and 1 <= page <= self.total_pages:
            self.current_page = page
        return True

    def reorder_slots(self, new_order: List[int]) -> bool:
        """按 new_order 重排：new_order[i] 是新位置 i 上的存档原来的索引"""
        def change(slots):
            if sorted(new_order) != list(range(len(slots))):
                logger.error("Invalid order: %s", new_order)
                return None
            return [slots[i] for i in new_order]
        return self._modify_slots(change)

    def replace_slot(self, index: int, slot_data: Dict[str, Any]) -> bool:
        """替换指定位置的存档槽"""
        def change(slots):
            if not 0 <= index < len(slots):
                logger.error("Slot index out of range: %d", index)
                return None
            return slots[:index] + [slot_data] + slots[index + 1:]
        return self._modify_slots(change)

    def clear_slots(self, indices: List[int]) -> bool:
        """把指定存档槽清空为 NO SAVE（位置保留）"""
        def change(slots):
            valid = [i for i in indices if 0 <= i < len(slots)]
            if not valid:
                return None
            new_slots = list(slots)
            for i in valid:
                new_slots[i] = {"title": "NO SAVE", "save_date": "", "img_data": "", "stat": {}}
            return new_slots
        return self._modify_slots(change)

    def remove_slots(self, indices: List[int]) -> bool:
        """删除指定存档槽，后面的存档依次前移"""
        def change(slots):
            removed = {i for i in indices if 0 <= i < len(slots)}
            if not removed:
                return None
            return [slot for i, slot in enumerate(slots) if i not in removed]
        return self._modify_slots(change, repaginate=True)

    def import_slot(self, slot_data: Dict[str, Any]) -> bool:
        """导入一个存档槽：放到最靠前的空存档位置，没有空位时追加到末尾"""
        if not isinstance(slot_data, dict):
            return False

        def change(slots):
            new_slots = list(slots)
            empty_index = next((i for i, slot in enumerate(new_slots) if is_empty_save(slot)), None)
            if empty_index is None:
                new_slots.append(slot_data)
            else:
                new_slots[empty_index] = slot_data
            return new_slots
        return self._modify_slots(change, repaginate=True)
