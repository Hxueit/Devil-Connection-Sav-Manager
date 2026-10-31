"""几个容易出错的纯逻辑函数"""
from src.modules.main.save_change_monitor import compare_saves, parse_ignored_vars
from src.modules.main.update_checker import is_newer


def test_compare_saves():
    old = {"a": 1, "gone": True, "sys": {"level": 1}, "l": [1]}
    new = {"a": 2, "sys": {"level": 2}, "l": [1, 3], "new": 3.0}
    assert compare_saves(old, new) == ["a 1→2", "-gone", "sys.level 1→2", "l.append(3)", "+new = 3"]
    assert compare_saves({"a": "1"}, {"a": 1}) == []   # 字符串和数字表示同一个值时不算变化


def test_compare_saves_ignores_vars():
    ignored = parse_ignored_vars(" record, sys.x ")
    old = {"record": {"a": 1}, "sys": {"x": 1, "y": 1}}
    new = {"record": {"a": 2}, "sys": {"x": 2, "y": 2}}
    assert compare_saves(old, new, ignored) == ["sys.y 1→2"]


def test_is_newer():
    assert is_newer("v0.5.3", "v0.5.2")
    assert is_newer("v0.10.0", "v0.9.0")
    assert not is_newer("v0.5.2", "v0.5.2")
    assert not is_newer("v0.5", "v0.5.0")
