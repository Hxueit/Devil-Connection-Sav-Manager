"""Tyrano 存档数据：读写 DevilConnection_tyrano_data.sav，并解析单个存档槽的信息

文件结构：{"data": [存档槽, 存档槽, ...], ...其他字段}
空存档槽的格式为 {"title": "NO SAVE", "save_date": "", "img_data": "", "stat": {}}
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.constants import TYRANO_SAVE_FILENAME
from src.modules.save_analysis.tyrano.constants import TYRANO_SAVES_PER_PAGE
from src.utils.sav_io import read_sav, write_sav

logger = logging.getLogger(__name__)


# 单个存档槽的解析（存档槽是游戏写的数据，里面的字段可能缺失或类型不对）

def is_empty_save(slot: dict[str, Any] | None) -> bool:
    if not slot:
        return True
    if slot.get("title") == "NO SAVE":
        return True
    return slot.get("save_date", "") == "" and slot.get("img_data", "") == "" and slot.get("stat", {}) == {}


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


@dataclass
class SaveInfo:
    day: int | None         # 第几天（后日谈时为后日谈的天数）
    is_epilogue: bool
    finished_count: int     # 当天的 3 个事件中完成了几个
    save_date: str | None
    subtitle: str | None

    def circles(self, done: str = "●", todo: str = "○") -> str:
        return "".join(done if i < self.finished_count else todo for i in range(3))


def extract_save_info(slot: dict[str, Any]) -> SaveInfo:
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
    if isinstance(finished, list) and day is not None and day >= 0:
        finished_count = len(finished[day * 3:day * 3 + 3])
    else:
        finished_count = 0

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
    if info.day is None:
        return ""
    key = "tyrano_epilogue_day_label" if info.is_epilogue else "tyrano_day_label"
    return t(key, day=info.day)


def describe_slot(slot: dict[str, Any], t: Callable[..., str]) -> str:
    """一行文字描述存档槽，如"3日目 · ●●○ · 2024/05/01 12:00:00 · 副标题"；无可用信息时返回空字符串"""
    info = extract_save_info(slot)
    parts = [day_text(info, t)]
    if info.day is not None and not info.is_epilogue:
        parts.append(info.circles())
    parts += [info.save_date, info.subtitle]
    return " · ".join(p for p in parts if p)


class TyranoAnalyzer:
    """所有修改都先写文件，写入成功后才更新内存里的数据"""

    def __init__(self, storage_dir: str) -> None:
        self.storage_dir = Path(storage_dir)
        self.save_data: dict[str, Any] | None = None
        self.save_slots: list[dict[str, Any]] = []
        self.current_page = 0   # 从 1 开始；没有存档时为 0
        self.total_pages = 0

    @property
    def file_path(self) -> Path:
        return self.storage_dir / TYRANO_SAVE_FILENAME

    def read_file(self) -> dict[str, Any] | None:
        """可以在后台线程调用，失败返回 None。返回的 "data" 一定是 dict 列表"""
        try:
            save_data = read_sav(self.file_path)
        except FileNotFoundError:
            logger.warning("Tyrano save file not found: %s", self.file_path)
            return None
        except (OSError, ValueError) as e:
            logger.error("Failed to load %s: %s", self.file_path, e)
            return None
        if not isinstance(save_data, dict):
            logger.error("Unexpected save format in %s", self.file_path)
            return None
        data = save_data.get("data")
        if not isinstance(data, list):
            logger.warning("'data' field missing or not a list in %s", self.file_path)
            data = []
        return {**save_data, "data": [slot for slot in data if isinstance(slot, dict)]}

    def set_save_data(self, save_data: dict[str, Any] | None) -> None:
        self.save_data = save_data
        self.save_slots = save_data["data"] if save_data is not None else []
        count = len(self.save_slots)
        self.total_pages = (count + TYRANO_SAVES_PER_PAGE - 1) // TYRANO_SAVES_PER_PAGE
        self.current_page = 1 if count else 0

    def get_current_page_slots(self) -> list[dict[str, Any] | None]:
        start = max(self.current_page - 1, 0) * TYRANO_SAVES_PER_PAGE
        page = self.save_slots[start:start + TYRANO_SAVES_PER_PAGE]
        return page + [None] * (TYRANO_SAVES_PER_PAGE - len(page))

    def _modify_slots(self, change: Callable[[list[dict[str, Any]]], list[dict[str, Any]] | None],
                      back_to_first_page: bool = False) -> bool:
        """读磁盘上最新的存档 → change(存档槽列表) → 写回 → 更新内存

        一定要重新读文件：玩家可能一边开着本工具一边在游戏里存档，
        直接用内存里的旧数据写回会把新存档覆盖掉。change 返回 None 表示不写。
        """
        latest = self.read_file()
        if latest is None:
            return False
        new_slots = change(latest["data"])
        if new_slots is None:
            return False
        new_save_data = {**latest, "data": new_slots}
        try:
            write_sav(self.file_path, new_save_data)
        except OSError as e:
            logger.error("Failed to write %s: %s", self.file_path, e)
            return False

        page = self.current_page
        self.set_save_data(new_save_data)
        if not back_to_first_page and 1 <= page <= self.total_pages:
            self.current_page = page
        return True

    def reorder_slots(self, new_order: list[int]) -> bool:
        """按 new_order 重排：new_order[i] 是新位置 i 上的存档原来的索引"""
        def change(slots):
            if sorted(new_order) != list(range(len(slots))):
                return None
            return [slots[i] for i in new_order]
        return self._modify_slots(change)

    def replace_slot(self, index: int, slot_data: dict[str, Any]) -> bool:
        def change(slots):
            if not 0 <= index < len(slots):
                return None
            slots[index] = slot_data
            return slots
        return self._modify_slots(change)

    def clear_slots(self, indices: list[int]) -> bool:
        def change(slots):
            valid = [i for i in indices if 0 <= i < len(slots)]
            if not valid:
                return None
            for i in valid:
                slots[i] = {"title": "NO SAVE", "save_date": "", "img_data": "", "stat": {}}
            return slots
        return self._modify_slots(change)

    def remove_slots(self, indices: list[int]) -> bool:
        def change(slots):
            removed = {i for i in indices if 0 <= i < len(slots)}
            if not removed:
                return None
            return [slot for i, slot in enumerate(slots) if i not in removed]
        return self._modify_slots(change, back_to_first_page=True)

    def import_slot(self, slot_data: dict[str, Any]) -> bool:
        """导入一个存档槽：放到最靠前的空存档位置，没有空位时追加到末尾"""
        def change(slots):
            empty_index = next((i for i, slot in enumerate(slots) if is_empty_save(slot)), None)
            if empty_index is None:
                slots.append(slot_data)
            else:
                slots[empty_index] = slot_data
            return slots
        return self._modify_slots(change, back_to_first_page=True)
