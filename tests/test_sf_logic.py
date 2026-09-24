import json

import pytest

from src.modules.save_analysis.sf.fields import (
    FANATIC_SECTION_KEY,
    SECTIONS,
    compute_shared_data,
    field_value,
    load_save_file,
    section_order,
)
from src.modules.save_analysis.sf.statistics_panel import (
    extract_judge_data,
    extract_sticker_data,
    format_mp_value_for_display,
    get_progress_color,
    load_neo_content,
)
from src.modules.save_analysis.sf.viewer_json import (
    format_display_data,
    format_json,
    restore_collapsed_fields,
)
from src.utils.sav_io import write_sav


def t(key):
    return f"<{key}>"


def _values(save_data):
    computed = compute_shared_data(save_data)
    return {f.label_key: field_value(f, save_data, computed, t)
            for s in SECTIONS.values() for f in s.fields}


def test_load_save_file_distinguishes_missing_and_corrupt(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_save_file(str(tmp_path))
    (tmp_path / "DevilConnection_sf.sav").write_text("%7Bbroken", encoding="utf-8")
    with pytest.raises(ValueError):
        load_save_file(str(tmp_path))
    write_sav(tmp_path / "DevilConnection_sf.sav", [1, 2])
    with pytest.raises(ValueError):
        load_save_file(str(tmp_path))
    write_sav(tmp_path / "DevilConnection_sf.sav", {"NEO": 2})
    assert load_save_file(str(tmp_path)) == {"NEO": 2}


def test_field_keys_are_unique():
    keys = [f.label_key for s in SECTIONS.values() for f in s.fields]
    assert len(keys) == len(set(keys))


def test_field_values():
    values = _values({
        "endings": ["1", "10", "2"], "collectedEndings": ["1"],
        "characters": ["a", "b", " "], "collectedCharacters": ["a"],
        "memory": {"name": "", "seibetu": 2}, "albumPageNo": 4, "judgeCounts": {"good": 7},
        "ngScene": ["geki"],
    })
    assert values["missing_endings"] == "2: 2, 10"
    assert values["current_collected_characters"] == "2"
    assert values["missing_characters"] == "b"
    assert values["character_name"] == "<not_set>"
    assert values["character_gender"] == "<gender_female>"
    assert values["album_page_no"] == "5"
    assert values["judge_good"] == "7"
    assert values["judge_bad"] == "0"
    assert values["killed"] == "<variable_not_exist>"
    assert values["autosave_enabled"] == "False"
    assert values["missing_omakes"] != "<none>"


def test_field_value_falls_back_to_raw_value_on_bad_type():
    assert _values({"albumPageNo": "x"})["album_page_no"] == "x"


def test_empty_lists_show_none():
    values = _values({"sticker": list(range(1, 200)), "characters": []})
    assert values["missing_stickers"] == "<none>"
    assert values["missing_characters"] == "<none>"


def test_section_order_moves_fanatic_section():
    assert section_order(True)[0] == FANATIC_SECTION_KEY
    normal = section_order(False)
    assert normal.index(FANATIC_SECTION_KEY) == normal.index("character_info") - 1
    assert sorted(normal) == sorted(SECTIONS)
    assert compute_shared_data({"killed": 1})["is_fanatic_route"]
    assert not compute_shared_data({"kill": 2})["is_fanatic_route"]


def test_format_json_keeps_collection_lists_on_one_line():
    text = format_json({"endings": [1, 2], "other": [1, 2], "empty": {}})
    assert '"endings": [1, 2]' in text
    assert '"other": [\n    1,\n    2\n  ]' in text
    assert json.loads(text) == {"endings": [1, 2], "other": [1, 2], "empty": {}}


def test_collapse_and_restore_roundtrip():
    data = {"record": [1, 2], "stat": {"map_label": {"a": 1}, "none": None}, "x": 1}
    fields = ["record", "stat.map_label", "stat.none", "missing"]
    text = format_display_data(data, fields, "COLLAPSED")
    edited = json.loads(text)
    assert edited["record"] == "COLLAPSED"
    assert edited["stat"]["map_label"] == "COLLAPSED"
    assert edited["stat"]["none"] is None  # 嵌套的 null 不折叠
    edited["x"] = 2
    restore_collapsed_fields(edited, data, fields, "COLLAPSED")
    assert edited == {"record": [1, 2], "stat": {"map_label": {"a": 1}, "none": None}, "x": 2}
    assert data["record"] == [1, 2]  # 原数据不被修改


def test_restore_keeps_user_replaced_value():
    edited = {"record": [9]}
    restore_collapsed_fields(edited, {"record": [1]}, ["record"], "COLLAPSED")
    assert edited == {"record": [9]}


def test_statistics_extraction(tmp_path):
    assert extract_sticker_data({"sticker": [1, 1, 2]})[0] == 2
    assert extract_sticker_data({"sticker": "bad"}) == (0, 0.0)
    assert extract_judge_data({"judgeCounts": {"perfect": 3.0, "good": "x"}}) == {"perfect": 3, "good": 0, "bad": 0}
    assert format_mp_value_for_display(1234567) == ("1,234,567", False)
    assert format_mp_value_for_display("1,000.50") == ("1,000.5", False)
    assert format_mp_value_for_display("abc") == ("abc", True)
    assert format_mp_value_for_display(float("nan"))[1] is True
    assert get_progress_color(100, False) == "#FFD54F"
    assert get_progress_color(10, True) == "#BF0204"

    assert load_neo_content(str(tmp_path)) is None
    (tmp_path / "NEO.sav").write_text("%22%E3%82%AD%E3%83%9F%E3%81%9F%E3%81%A1%E3%81%AB%E6%B0%B8%E9%81%A0%E3%81%AE"
                                      "%E7%A5%9D%E7%A6%8F%E3%82%92%22", encoding="utf-8")
    assert load_neo_content(str(tmp_path)) == (None, "#FFEB9E")
    (tmp_path / "NEO.sav").write_text("hi%20there", encoding="utf-8")
    assert load_neo_content(str(tmp_path)) == ("hi there", "#000000")
