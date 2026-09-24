import base64
import threading
from io import BytesIO

import pytest
from PIL import Image

from src.modules.save_analysis.tyrano.analyzer import (
    TyranoAnalyzer,
    describe_slot,
    extract_save_info,
    is_empty_save,
)
from src.modules.save_analysis.tyrano.constants import TYRANO_SAV_FILENAME
from src.modules.save_analysis.tyrano.image_utils import (
    ImageCache,
    decode_image_data,
    slot_thumbnail,
    thumbnail_size,
)
from src.utils.sav_io import read_sav, write_sav

EMPTY = {"title": "NO SAVE", "save_date": "", "img_data": "", "stat": {}}


def t(key):
    return {"tyrano_day_label": "{day}日目", "tyrano_epilogue_day_label": "后日谈{day}日目"}.get(key, key)


def slot(day=1, finished=(), epilogue=0, date="2024/05/01 12:00:00", subtitle=None, img=""):
    s = {"title": "s", "save_date": date, "img_data": img,
         "stat": {"f": {"day": day, "day_epilogue": epilogue, "finished": list(finished)}}}
    if subtitle:
        s.update(subtitle=True, subtitleText=subtitle)
    return s


def jpeg_uri(size=(64, 48)):
    buf = BytesIO()
    Image.new("RGB", size, "red").save(buf, "JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


# --- 存档槽解析 ---

def test_is_empty_save():
    assert is_empty_save(None)
    assert is_empty_save(EMPTY)
    assert is_empty_save({"title": "x", "save_date": "", "img_data": "", "stat": {}})
    assert not is_empty_save(slot())


def test_extract_save_info_day_and_finished():
    info = extract_save_info(slot(day=2, finished=[1] * 8))
    assert (info.day, info.is_epilogue, info.finished_count) == (2, False, 2)   # finished[6:9] 只有 2 个
    assert extract_save_info(slot(day=0, finished=[1] * 5)).finished_count == 3
    assert extract_save_info(slot(day="3", finished=[1] * 12)).finished_count == 3
    assert extract_save_info(slot(day="abc")).day is None


def test_extract_save_info_epilogue_and_subtitle():
    info = extract_save_info(slot(day=5, epilogue=2, subtitle="sub"))
    assert (info.day, info.is_epilogue, info.subtitle) == (2, True, "sub")
    assert extract_save_info({"subtitle": False, "subtitleText": "x"}).subtitle is None
    assert extract_save_info({"stat": "broken"}).day is None


def test_describe_slot():
    assert describe_slot(slot(day=1, finished=[1, 1, 1, 1], subtitle="s"), t) == \
        "1日目 · ●○○ · 2024/05/01 12:00:00 · s"
    assert describe_slot(slot(day=1, epilogue=3), t) == "后日谈3日目 · 2024/05/01 12:00:00"
    assert describe_slot(EMPTY, t) == ""
    assert describe_slot(None, t) == ""


# --- 存档文件 ---

@pytest.fixture
def storage(tmp_path):
    slots = [slot(day=i + 1) for i in range(8)]
    slots[3] = dict(EMPTY)
    write_sav(tmp_path / TYRANO_SAV_FILENAME, {"data": slots, "other": 1})
    return tmp_path


def disk_slots(storage):
    return read_sav(storage / TYRANO_SAV_FILENAME)["data"]


def test_load_and_paging(storage):
    an = TyranoAnalyzer(str(storage))
    assert an.load_save_file()
    assert (an.total_pages, an.current_page) == (2, 1)
    an.go_to_prev_page()
    assert an.current_page == 2
    page = an.get_current_page_slots()
    assert len(page) == 6 and page[2:] == [None] * 4
    an.go_to_next_page()
    assert an.current_page == 1
    assert not an.set_page(3)


def test_load_missing_or_broken(tmp_path):
    an = TyranoAnalyzer(str(tmp_path))
    assert not an.load_save_file()
    (tmp_path / TYRANO_SAV_FILENAME).write_text("%7Bbroken", encoding="utf-8")
    assert not an.load_save_file()
    assert an.save_slots == [] and an.total_pages == 0


def test_modifications_are_written(storage):
    an = TyranoAnalyzer(str(storage))
    an.load_save_file()
    original = list(an.save_slots)

    assert an.reorder_slots([1, 0, 2, 3, 4, 5, 6, 7])
    assert disk_slots(storage)[:2] == [original[1], original[0]]
    assert not an.reorder_slots([0, 0, 1, 2, 3, 4, 5, 6])

    assert an.clear_slots([0])
    assert disk_slots(storage)[0] == EMPTY

    new = slot(day=9)
    assert an.import_slot(new)          # 填到第一个空位（索引 0）
    assert disk_slots(storage)[0] == new
    assert an.import_slot(new)          # 下一个空位是索引 3
    assert disk_slots(storage)[3] == new
    assert an.import_slot(new)          # 没有空位，追加
    assert len(disk_slots(storage)) == 9 and an.total_pages == 2

    assert an.replace_slot(8, slot(day=7))
    assert disk_slots(storage)[8]["stat"]["f"]["day"] == 7
    assert not an.replace_slot(99, new)

    assert an.remove_slots([0, 1, 2])
    assert len(disk_slots(storage)) == 6 and an.total_pages == 1
    assert read_sav(storage / TYRANO_SAV_FILENAME)["other"] == 1


def test_failed_write_keeps_memory(storage, monkeypatch):
    an = TyranoAnalyzer(str(storage))
    an.load_save_file()
    before = list(an.save_slots)

    def fail(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr("src.modules.save_analysis.tyrano.analyzer.write_sav", fail)
    assert not an.remove_slots([0])
    assert an.save_slots == before


# --- 缩略图 ---

def test_decode_image_data():
    assert decode_image_data(jpeg_uri()).size == (64, 48)
    assert decode_image_data("data:image/jpeg;base64,!!!") is None
    assert decode_image_data("no separator") is None
    assert decode_image_data(None) is None


def test_thumbnail_size_keeps_aspect_ratio():
    assert thumbnail_size((300, 150)) == (85, 63)
    w, h = thumbnail_size((400, 300), (800, 450))
    assert abs(w / h - 16 / 9) < 0.05
    assert thumbnail_size((0, 0)) == (120, 90)


def test_slot_thumbnail_and_cache():
    cache = ImageCache(max_originals=2, max_thumbnails=2)
    uri = jpeg_uri()
    thumb = slot_thumbnail(uri, (300, 150), cache, "none", "bad")
    assert thumb.size == thumbnail_size((300, 150), (64, 48))
    assert slot_thumbnail(uri, (300, 150), cache, "none", "bad") is thumb
    assert slot_thumbnail("", (300, 150), cache, "none", "bad").size == thumbnail_size((300, 150))
    assert slot_thumbnail("data:x;base64,@@", (300, 150), cache, "none", "bad") is not None
    assert cache.get_thumbnail(123, (300, 150)) is None


def test_image_cache_concurrent_use():
    cache = ImageCache(max_originals=2, max_thumbnails=3)
    uris = [jpeg_uri((40 + i, 30)) for i in range(6)]
    errors = []

    def worker(offset):
        try:
            for i in range(200):
                cache.get_thumbnail(uris[(i + offset) % 6], (300 + i % 5, 150))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert not errors
