"""sf 存档变动提示（「其他」页里开启 toast 后才运行）

- compare_saves：比较两份存档数据，生成「变量 旧值→新值」这样的变更列表
- SaveChangeMonitor：在主线程定时检查 sf 存档，只在文件的修改时间/大小变化时才读取和比较
- ChangeNotifier：用 toast 显示变更；同一个变量连续变化时合并成一行「a→b→c」
"""
import json
import logging
import os
import tkinter as tk
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from src.constants import SF_SAVE_FILENAME
from src.utils.sav_io import read_sav
from src.utils.toast import Toast
from src.utils.ui_utils import widget_alive

logger = logging.getLogger(__name__)

ARROW = "→"
FLOAT_EPSILON = 1e-10


# ---------- 比较 ----------

def parse_ignored_vars(text: str) -> Set[str]:
    """'record, initialVars' -> {'record', 'initialVars'}"""
    return {name.strip() for name in (text or "").split(",") if name.strip()}


def _format_value(value: Any) -> str:
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _values_equal(old: Any, new: Any) -> bool:
    """宽松的相等判断：1 和 1.0 相等，"1" 和 1 也视为相等（游戏有时会改变值的类型）"""
    if old is None or new is None:
        return old is new
    if type(old) is type(new):
        return old == new
    if _is_number(old) and _is_number(new):
        return abs(float(old) - float(new)) < FLOAT_EPSILON
    if isinstance(old, (dict, list)) or isinstance(new, (dict, list)):
        return False
    return str(old) == str(new)


def _list_key(item: Any) -> str:
    """列表元素的比较键（元素可能是不可哈希的 dict/list）"""
    if isinstance(item, (dict, list)):
        return json.dumps(item, sort_keys=True, ensure_ascii=False)
    return str(item)


def _compare_lists(key: str, old: list, new: list) -> List[str]:
    old_keys = {_list_key(item) for item in old}
    new_keys = {_list_key(item) for item in new}
    changes = [f"{key}.append({_format_value(item)})" for item in new if _list_key(item) not in old_keys]
    changes += [f"{key}.remove({_format_value(item)})" for item in old if _list_key(item) not in new_keys]
    return changes


def _is_ignored(full_key: str, key: str, ignored: Set[str]) -> bool:
    return key in ignored or any(full_key == name or full_key.startswith(name + ".") for name in ignored)


def compare_saves(old: Any, new: Any, ignored: Iterable[str] = (), prefix: str = "") -> List[str]:
    """递归比较两份存档，返回变更列表

    格式：「-键」删除，「+键 = 值」新增，「键 旧值→新值」修改，
    「键.append(值)」/「键.remove(值)」列表增减。ignored 中的变量（及其子键）会被跳过。
    """
    ignored = set(ignored)
    old = old if isinstance(old, dict) else {}
    new = new if isinstance(new, dict) else {}
    changes: List[str] = []
    for key in list(old) + [k for k in new if k not in old]:
        full_key = f"{prefix}.{key}" if prefix else key
        if _is_ignored(full_key, key, ignored):
            continue
        if key not in new:
            changes.append(f"-{full_key}")
            continue
        new_value = new[key]
        if key not in old:
            if isinstance(new_value, dict):
                changes += compare_saves({}, new_value, ignored, full_key)
            else:
                changes.append(f"+{full_key} = {_format_value(new_value)}")
            continue

        old_value = old[key]
        if _values_equal(old_value, new_value):
            # 数值相同但类型变了（如 1 → 1.0），也提示一下
            if type(old_value) is not type(new_value) and _is_number(old_value) and _is_number(new_value):
                changes.append(
                    f"{full_key} {_format_value(old_value)} ({type(old_value).__name__}){ARROW}"
                    f"{_format_value(new_value)} ({type(new_value).__name__})"
                )
        elif isinstance(old_value, dict) and isinstance(new_value, dict):
            changes += compare_saves(old_value, new_value, ignored, full_key)
        elif isinstance(old_value, list) and isinstance(new_value, list):
            changes += _compare_lists(full_key, old_value, new_value)
        else:
            changes.append(f"{full_key} {_format_value(old_value)}{ARROW}{_format_value(new_value)}")
    return changes


# ---------- 监控 ----------

class SaveChangeMonitor:
    """定时检查 sf 存档，内容变化时调用 on_change(changes)

    整个 _storage 文件夹消失时（游戏里的「AB INITIO」）调用一次 on_ab_initio()。
    检查在主线程上执行：平时只做一次 os.stat，文件变化时才读取和解析。
    """

    POLL_INTERVAL_MS = 300

    def __init__(
        self,
        widget: tk.Misc,
        storage_dir: str,
        ignored_vars: Set[str],
        on_change: Callable[[List[str]], None],
        on_ab_initio: Callable[[], None],
    ) -> None:
        self.widget = widget
        self.save_path = Path(storage_dir) / SF_SAVE_FILENAME
        self.ignored_vars = ignored_vars
        self.on_change = on_change
        self.on_ab_initio = on_ab_initio
        self._stamp: Optional[Tuple[int, int]] = None  # (mtime_ns, size)
        self._data: Any = None
        self._ab_initio_fired = False
        self._job: Optional[str] = None

    def start(self) -> None:
        self.stop()
        self._stamp, self._data = None, None
        self._ab_initio_fired = False
        self._check(notify=False)  # 记录当前内容作为比较基准
        self._job = self.widget.after(self.POLL_INTERVAL_MS, self._poll)

    def stop(self) -> None:
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def _poll(self) -> None:
        self._job = self.widget.after(self.POLL_INTERVAL_MS, self._poll)
        try:
            self._check(notify=True)
        except Exception:
            logger.exception("检查存档变化失败")

    def _check(self, notify: bool) -> None:
        try:
            stat = os.stat(self.save_path)
        except FileNotFoundError:
            if not self.save_path.parent.exists():
                if notify and not self._ab_initio_fired:
                    self._ab_initio_fired = True
                    self.on_ab_initio()
            else:
                self._stamp, self._data = None, None  # 存档被删除，重新出现时作为新的基准
            return
        except OSError:
            return

        stamp = (stat.st_mtime_ns, stat.st_size)
        if stamp == self._stamp:
            return
        try:
            data = read_sav(self.save_path)
        except (OSError, ValueError):
            # 游戏可能正在写入或占用文件（Windows），不更新 stamp，下次再试
            return
        old_data = self._data
        self._stamp, self._data = stamp, data
        if notify and old_data is not None:
            changes = compare_saves(old_data, data, self.ignored_vars)
            if changes:
                self.on_change(changes)


# ---------- 显示 ----------

def _parse_arrow_change(change: str) -> Optional[Tuple[str, str, str]]:
    """'var old→new' -> (var, old, new)；不是这种格式时返回 None"""
    if change.startswith(("+", "-")) or ARROW not in change:
        return None
    prefix, new_value = change.split(ARROW, 1)
    last_space = prefix.rfind(" ")
    if last_space <= 0 or not prefix[:last_space].strip():
        return None
    return prefix[:last_space].strip(), prefix[last_space + 1:].strip(), new_value.strip()


def _toast_alive(toast: Optional[Toast]) -> bool:
    return toast is not None and widget_alive(toast.window)


class ChangeNotifier:
    """用 toast 显示存档变更；变量的后续变化合并到仍在显示的那条 toast 里"""

    TOAST_DURATION_MS = 15000

    def __init__(self, root: tk.Misc, t: Callable[[str], str]) -> None:
        self.root = root
        self.t = t
        # 变量名 -> (依次出现过的值, 显示它的 toast)
        self._chains: Dict[str, Tuple[List[str], Optional[Toast]]] = {}

    def show(self, changes: List[str]) -> None:
        new_lines: List[str] = []
        new_vars: List[str] = []
        for change in changes:
            parsed = _parse_arrow_change(change)
            if parsed is None:
                new_lines.append(change)
                continue
            var, old_value, new_value = parsed
            values, toast = self._chains.get(var, ([], None))
            if _toast_alive(toast):
                values.append(new_value)
                toast.reset_timer()
                toast.update_message(_replace_line(toast.message, var, f"{var} {ARROW.join(values)}"))
            else:
                self._chains[var] = ([old_value, new_value], None)
                new_vars.append(var)
                new_lines.append(f"{var} {old_value}{ARROW}{new_value}")

        if new_lines:
            message = "\n".join([self.t("sf_sav_changes_notification")] + new_lines)
            toast = Toast(self.root, message, duration=self.TOAST_DURATION_MS, fade_in=200, fade_out=200)
            for var in new_vars:
                self._chains[var] = (self._chains[var][0], toast)

        # 忘掉已经关闭的 toast
        self._chains = {var: chain for var, chain in self._chains.items() if _toast_alive(chain[1])}


def _replace_line(message: str, var: str, new_line: str) -> str:
    """把消息中该变量的那一行换成 new_line（找不到就追加）"""
    lines = message.split("\n") if message else []
    for i, line in enumerate(lines):
        if line.startswith(f"{var} ") and ARROW in line:
            lines[i] = new_line
            return "\n".join(lines)
    return "\n".join(lines + [new_line])
