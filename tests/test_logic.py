"""几个容易出错的纯逻辑函数"""
from src.characters import CHARACTER_NAMES
from src.constants import TOTAL_CHARACTERS
from src.modules.main.main_window import detect_system_language
from src.modules.main.save_change_monitor import compare_saves, parse_ignored_vars
from src.modules.main.update_checker import is_newer
from src.modules.save_analysis.sf.fields import SECTIONS, compute_shared_data, field_value
from src.utils.translations import TRANSLATIONS


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


def test_character_table_matches_total():
    assert len(CHARACTER_NAMES) == TOTAL_CHARACTERS


def test_missing_characters_use_translated_names_in_collection_order():
    save = {"characters": ["ペイン", "新キャラ", "リリカ", "  "], "collectedCharacters": []}
    field = next(f for f in SECTIONS["characters_statistics"].fields if f.label_key == "missing_characters")

    def text(lang):
        return field_value(field, save, compute_shared_data(save), TRANSLATIONS[lang].get)

    assert text("en_US") == "Lyrica, Paine, 新キャラ"
    assert text("ja_JP") == "リリカ, ペイン, 新キャラ"


def test_ng_scene_count_ignores_duplicates():
    save = {"ngScene": ["debi", "extra", "extra", "extra"]}
    field = next(f for s in SECTIONS.values() for f in s.fields if f.label_key == "ng_scene_count")
    assert field_value(field, save, compute_shared_data(save), TRANSLATIONS["zh_CN"].get).startswith("2/")


def test_detect_system_language(monkeypatch):
    for value, expected in [("zh_TW", "zh_TW"), ("zh_HK.UTF-8", "zh_TW"), ("zh_CN.UTF-8", "zh_CN"), ("ja_JP", "ja_JP")]:
        monkeypatch.setenv("APP_LANG", value)
        assert detect_system_language() == expected
