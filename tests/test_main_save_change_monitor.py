import os

from src.modules.main.save_change_monitor import (
    SaveChangeMonitor,
    _parse_arrow_change,
    _replace_line,
    compare_saves,
    parse_ignored_vars,
)
from src.utils.sav_io import write_sav


def test_no_changes():
    data = {"a": 1, "b": {"c": [1, 2]}, "d": "x"}
    assert compare_saves(data, dict(data)) == []


def test_value_change_add_remove():
    old = {"a": 1, "gone": True, "s": "x"}
    new = {"a": 2, "s": "y", "new": 3.0}
    assert compare_saves(old, new) == ['a 1→2', "-gone", 's "x"→"y"', "+new = 3"]


def test_nested_dict_and_new_dict():
    old = {"sys": {"level": 1}}
    new = {"sys": {"level": 2}, "extra": {"x": 1, "y": {"z": "q"}}}
    assert compare_saves(old, new) == ["sys.level 1→2", "+extra.x = 1", '+extra.y.z = "q"']


def test_list_append_remove_with_unhashable_items():
    old = {"l": [1, {"k": 1}, [2]]}
    new = {"l": [1, {"k": 2}, [2], 3]}
    assert compare_saves(old, new) == ["l.append({'k': 2})", "l.append(3)", "l.remove({'k': 1})"]


def test_int_float_same_value_reports_type_change():
    assert compare_saves({"a": 1}, {"a": 1.0}) == ["a 1 (int)→1 (float)"]


def test_loose_equality():
    # 字符串和数字表示同一个值时不算变化；bool 和数字不算相等
    assert compare_saves({"a": "1"}, {"a": 1}) == []
    assert compare_saves({"a": True}, {"a": 1}) == ["a True→1"]
    assert compare_saves({"a": None}, {"a": 0}) == ["a None→0"]
    assert compare_saves({"a": [1]}, {"a": {"x": 1}}) == ["a [1]→{'x': 1}"]


def test_ignored_vars():
    ignored = parse_ignored_vars(" record, initialVars ,, sys.x ")
    assert ignored == {"record", "initialVars", "sys.x"}
    old = {"record": {"a": 1}, "sys": {"x": {"deep": 1}, "y": 1}}
    new = {"record": {"a": 2}, "sys": {"x": {"deep": 2}, "y": 2}}
    assert compare_saves(old, new, ignored) == ["sys.y 1→2"]


def test_parse_arrow_change():
    assert _parse_arrow_change("sys.level 1→2") == ("sys.level", "1", "2")
    assert _parse_arrow_change("+a = 1") is None
    assert _parse_arrow_change("l.append(1)") is None
    assert _parse_arrow_change("nospace→2") is None


def test_replace_line():
    message = "header\na 1→2\nb 3→4"
    assert _replace_line(message, "a", "a 1→2→3") == "header\na 1→2→3\nb 3→4"
    assert _replace_line(message, "c", "c 5→6") == message + "\nc 5→6"


def test_monitor_detects_changes_only_when_file_changes(tmp_path):
    storage = tmp_path / "_storage"
    storage.mkdir()
    save = storage / "DevilConnection_sf.sav"
    write_sav(save, {"v": 1})
    seen, ab_initio = [], []
    monitor = SaveChangeMonitor(None, str(storage), set(), seen.append, lambda: ab_initio.append(1))
    monitor._check(notify=False)

    monitor._check(notify=True)
    assert seen == []

    write_sav(save, {"v": 2})
    os.utime(save, ns=(1, 1))  # 保证 mtime 变化（有些文件系统时间精度较低）
    monitor._check(notify=True)
    assert seen == [["v 1→2"]]

    # 解析失败（游戏写到一半）时不更新基准，下次再比较
    save.write_text("%7B%22v%22")
    os.utime(save, ns=(2, 2))
    monitor._check(notify=True)
    write_sav(save, {"v": 3})
    os.utime(save, ns=(3, 3))
    monitor._check(notify=True)
    assert seen == [["v 1→2"], ["v 2→3"]]

    # 整个 _storage 被删除：只触发一次 AB INITIO
    for path in storage.iterdir():
        path.unlink()
    storage.rmdir()
    monitor._check(notify=True)
    monitor._check(notify=True)
    assert ab_initio == [1]
