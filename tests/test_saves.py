"""修改游戏存档的功能：确认写出的文件正确，出错时不损坏已有存档"""
import base64
import zipfile
from io import BytesIO

import pytest
from PIL import Image

from src.constants import TYRANO_SAVE_FILENAME
from src.modules.backup import backups
from src.modules.save_analysis.tyrano.analyzer import TyranoAnalyzer
from src.modules.screenshot import screenshot_manager as sm
from src.utils.sav_io import read_sav, write_sav

EMPTY_SLOT = {"title": "NO SAVE", "save_date": "", "img_data": "", "stat": {}}


def slot(day):
    return {"title": "s", "save_date": "2024/05/01", "img_data": "", "stat": {"f": {"day": day}}}


# ---------- Tyrano 存档槽 ----------

@pytest.fixture
def tyrano(tmp_path):
    slots = [slot(i) for i in range(8)]
    slots[3] = dict(EMPTY_SLOT)
    write_sav(tmp_path / TYRANO_SAVE_FILENAME, {"data": slots, "other": 1})
    analyzer = TyranoAnalyzer(str(tmp_path))
    assert analyzer.load_save_file()
    return analyzer


def days_on_disk(analyzer):
    return [s["stat"].get("f", {}).get("day") for s in read_sav(analyzer.file_path)["data"]]


def test_tyrano_modifications(tyrano):
    assert tyrano.reorder_slots([1, 0, 2, 3, 4, 5, 6, 7])
    assert days_on_disk(tyrano)[:2] == [1, 0]
    assert tyrano.clear_slots([0])
    assert read_sav(tyrano.file_path)["data"][0] == EMPTY_SLOT
    assert tyrano.import_slot(slot(99))          # 填到第一个空位
    assert days_on_disk(tyrano)[0] == 99
    assert tyrano.remove_slots([0, 1])
    assert len(days_on_disk(tyrano)) == 6
    assert read_sav(tyrano.file_path)["other"] == 1   # 其他字段保持不变


def test_tyrano_keeps_saves_made_by_the_game_meanwhile(tyrano):
    """玩家开着本工具时在游戏里存了档：修改其他槽位不能覆盖它"""
    on_disk = read_sav(tyrano.file_path)
    on_disk["data"][2] = slot(42)
    write_sav(tyrano.file_path, on_disk)

    assert tyrano.replace_slot(0, slot(5))
    assert days_on_disk(tyrano)[:3] == [5, 1, 42]


def test_tyrano_failed_write_keeps_memory(tyrano, monkeypatch):
    before = list(tyrano.save_slots)
    monkeypatch.setattr("src.modules.save_analysis.tyrano.analyzer.write_sav",
                        lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    assert not tyrano.remove_slots([0])
    assert tyrano.save_slots == before


# ---------- 截图 ----------

def png_data_uri(size=(40, 30)):
    buffer = BytesIO()
    Image.new("RGB", size, "red").save(buffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


@pytest.fixture
def screenshots(tmp_path):
    write_sav(tmp_path / sm.IDS_FILENAME, [{"id": "aaa", "date": "2024/01/02 00:00:00"}])
    write_sav(tmp_path / sm.ALL_IDS_FILENAME, ["aaa"])
    write_sav(tmp_path / "DevilConnection_photo_aaa.sav", png_data_uri())
    write_sav(tmp_path / "DevilConnection_photo_aaa_thumb.sav", png_data_uri((32, 24)))
    manager = sm.ScreenshotManager(str(tmp_path))
    assert manager.load_screenshots()
    return manager


def test_screenshot_add_and_delete(screenshots, tmp_path):
    image = tmp_path / "new.jpg"
    Image.new("RGB", (80, 60), "blue").save(image, "JPEG")
    screenshots.add_screenshot("bbb", "2024/05/05 00:00:00", str(image))
    assert read_sav(tmp_path / sm.ALL_IDS_FILENAME) == ["aaa", "bbb"]
    assert read_sav(tmp_path / "DevilConnection_photo_bbb.sav").startswith("data:image/png;base64,")

    screenshots.delete_screenshots(["aaa"])
    assert read_sav(tmp_path / sm.ALL_IDS_FILENAME) == ["bbb"]
    assert not (tmp_path / "DevilConnection_photo_aaa.sav").exists()


def test_screenshot_add_non_image_changes_nothing(screenshots, tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_text("not an image")
    with pytest.raises(sm.ScreenshotError):
        screenshots.add_screenshot("ccc", "2024/05/05 00:00:00", str(bad))
    assert read_sav(tmp_path / sm.ALL_IDS_FILENAME) == ["aaa"]
    assert not (tmp_path / "DevilConnection_photo_ccc.sav").exists()


def test_malformed_screenshot_index_is_rejected(tmp_path):
    write_sav(tmp_path / sm.IDS_FILENAME, {"a": 1})
    write_sav(tmp_path / sm.ALL_IDS_FILENAME, [])
    assert sm.ScreenshotManager(str(tmp_path)).load_screenshots() is False


# ---------- 备份 ----------

@pytest.fixture
def storage(tmp_path):
    storage = tmp_path / "game" / "_storage"
    (storage / "sub").mkdir(parents=True)
    (storage / "DevilConnection_sf.sav").write_text("sf")
    (storage / "DevilConnection_tyrano_data.sav").write_text("tyrano")
    (storage / "sub" / "img.png").write_bytes(b"x" * 100)
    return storage


def test_backup_and_restore(storage):
    path = backups.create_backup(storage)
    (storage / "DevilConnection_sf.sav").write_text("changed")
    (storage / "extra.txt").write_text("new file")

    backups.restore_backup(path, storage)
    assert (storage / "DevilConnection_sf.sav").read_text() == "sf"
    assert (storage / "sub" / "img.png").exists()
    assert not (storage / "extra.txt").exists()
    assert sorted(p.name for p in storage.parent.iterdir()) == ["_storage", "dcsm_backups"]


def test_restore_bad_zip_keeps_storage(storage):
    bad = storage.parent / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(zipfile.BadZipFile):
        backups.restore_backup(bad, storage)
    assert (storage / "DevilConnection_sf.sav").read_text() == "sf"


def test_restore_when_folder_is_locked(storage, monkeypatch):
    """Windows 上 _storage 被占用时无法整体重命名，会改为逐个文件替换"""
    path = backups.create_backup(storage)
    (storage / "DevilConnection_sf.sav").write_text("changed")
    real_rename = type(storage).rename

    def locked_rename(self, target):
        if self == storage:
            raise PermissionError("folder in use")
        return real_rename(self, target)

    monkeypatch.setattr(type(storage), "rename", locked_rename)
    backups.restore_backup(path, storage)
    assert (storage / "DevilConnection_sf.sav").read_text() == "sf"
