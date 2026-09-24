import base64
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from src.modules.screenshot import screenshot_manager as sm
from src.utils.images import data_uri_to_bytes, image_to_data_uri
from src.utils.sav_io import read_sav, write_sav


def _png_uri(color="red", size=(40, 30), fmt="PNG"):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, fmt)
    mime = "jpeg" if fmt == "JPEG" else fmt.lower()
    return f"data:image/{mime};base64,{base64.b64encode(buffer.getvalue()).decode()}"


def _write_image(path: Path, fmt: str, size=(40, 30)) -> Path:
    Image.new("RGB", size, "blue").save(path, fmt)
    return path


@pytest.fixture
def storage(tmp_path):
    ids = [{"id": "aaa", "date": "2024/01/02 00:00:00"}, {"id": "bbb", "date": "2023/01/01 00:00:00"}]
    write_sav(tmp_path / sm.IDS_FILENAME, ids)
    write_sav(tmp_path / sm.ALL_IDS_FILENAME, ["aaa", "bbb"])
    for sid in ("aaa", "bbb"):
        write_sav(tmp_path / f"DevilConnection_photo_{sid}.sav", _png_uri())
        write_sav(tmp_path / f"DevilConnection_photo_{sid}_thumb.sav", _png_uri(size=(32, 24), fmt="JPEG"))
    manager = sm.ScreenshotManager(str(tmp_path))
    assert manager.load_screenshots()
    return manager


def test_parse_filename():
    assert sm.parse_screenshot_filename("DevilConnection_photo_ab12.sav") == ("ab12", False)
    assert sm.parse_screenshot_filename("DevilConnection_photo_ab12_thumb.sav") == ("ab12", True)
    assert sm.parse_screenshot_filename(sm.IDS_FILENAME) is None
    assert sm.parse_screenshot_filename(sm.ALL_IDS_FILENAME) is None
    assert sm.parse_screenshot_filename("other.sav") is None


def test_data_uri_roundtrip():
    img = Image.new("RGB", (4, 3), "red")
    data = data_uri_to_bytes(image_to_data_uri(img))
    assert Image.open(BytesIO(data)).size == (4, 3)
    with pytest.raises(ValueError):
        data_uri_to_bytes("not a uri")


def test_load_and_image_data(storage):
    assert set(storage.sav_pairs) >= {"aaa", "bbb"}
    assert Image.open(BytesIO(storage.get_image_data("aaa"))).size == (40, 30)


def test_add_converts_to_png_and_writes_index_last(storage, tmp_path):
    src = _write_image(tmp_path / "in.jpg", "JPEG")
    storage.add_screenshot("ccc", "2024/05/05 00:00:00", str(src))
    main_uri = read_sav(tmp_path / "DevilConnection_photo_ccc.sav")
    assert main_uri.startswith("data:image/png;base64,")
    assert Image.open(BytesIO(data_uri_to_bytes(main_uri))).format == "PNG"
    thumb = Image.open(BytesIO(data_uri_to_bytes(read_sav(tmp_path / "DevilConnection_photo_ccc_thumb.sav"))))
    assert thumb.size == (32, 24)  # 跟已有缩略图一样大
    assert read_sav(tmp_path / sm.ALL_IDS_FILENAME) == ["aaa", "bbb", "ccc"]


def test_add_non_image_leaves_index_untouched(storage, tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_text("not an image")
    with pytest.raises(sm.ScreenshotError) as excinfo:
        storage.add_screenshot("ddd", "2024/05/05 00:00:00", str(bad))
    assert excinfo.value.key == "file_operation_failed"
    assert read_sav(tmp_path / sm.ALL_IDS_FILENAME) == ["aaa", "bbb"]
    assert not (tmp_path / "DevilConnection_photo_ddd.sav").exists()
    assert "ddd" not in storage.sav_pairs


def test_add_index_failure_removes_written_files(storage, tmp_path, monkeypatch):
    src = _write_image(tmp_path / "in.png", "PNG")

    def fail():
        raise OSError("disk full")

    monkeypatch.setattr(storage, "_save_index", fail)
    with pytest.raises(sm.ScreenshotError) as excinfo:
        storage.add_screenshot("eee", "2024/05/05 00:00:00", str(src))
    assert (excinfo.value.key, excinfo.value.detail) == ("save_failed", "disk full")
    assert not (tmp_path / "DevilConnection_photo_eee.sav").exists()
    assert [item["id"] for item in storage.ids_data] == ["aaa", "bbb"]


def test_move_and_sort(storage, tmp_path):
    storage.move_item(0, 1)
    assert read_sav(tmp_path / sm.ALL_IDS_FILENAME) == ["bbb", "aaa"]
    storage.sort_by_date(ascending=False)
    assert read_sav(tmp_path / sm.ALL_IDS_FILENAME) == ["aaa", "bbb"]


def test_move_save_failure_keeps_order(storage, monkeypatch):
    monkeypatch.setattr(sm, "write_sav", lambda *a: (_ for _ in ()).throw(OSError("read-only")))
    with pytest.raises(OSError):
        storage.move_item(0, 1)
    assert [item["id"] for item in storage.ids_data] == ["aaa", "bbb"]


def test_delete(storage, tmp_path):
    assert storage.delete_screenshots(["aaa"]) == []
    assert read_sav(tmp_path / sm.ALL_IDS_FILENAME) == ["bbb"]
    assert not (tmp_path / "DevilConnection_photo_aaa.sav").exists()
    assert "aaa" not in storage.sav_pairs


def test_delete_index_failure_keeps_files(storage, tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "write_sav", lambda *a: (_ for _ in ()).throw(OSError("read-only")))
    with pytest.raises(OSError):
        storage.delete_screenshots(["aaa"])
    assert (tmp_path / "DevilConnection_photo_aaa.sav").exists()
    assert "aaa" in storage.sav_pairs


def test_replace_keeps_thumb_size(storage, tmp_path):
    src = _write_image(tmp_path / "new.webp", "WEBP", size=(80, 60))
    storage.replace_screenshot("bbb", str(src))
    assert Image.open(BytesIO(storage.get_image_data("bbb"))).size == (80, 60)
    assert sm.thumb_image_size(tmp_path / "DevilConnection_photo_bbb_thumb.sav") == (32, 24)


@pytest.mark.parametrize("ids_content", [{"a": 1}, [{"date": "x"}], ["1", "2"], "text"])
def test_malformed_index_is_rejected(tmp_path, ids_content):
    write_sav(tmp_path / sm.IDS_FILENAME, ids_content)
    write_sav(tmp_path / sm.ALL_IDS_FILENAME, [])
    manager = sm.ScreenshotManager()
    manager.set_storage_dir(str(tmp_path))
    assert manager.load_screenshots() is False


def test_add_and_replace_errors(storage, tmp_path):
    src = _write_image(tmp_path / "in.png", "PNG")
    with pytest.raises(sm.ScreenshotError) as excinfo:
        storage.add_screenshot("aaa", "2024/05/05 00:00:00", str(src))
    assert excinfo.value.key == "id_exists"
    with pytest.raises(sm.ScreenshotError) as excinfo:
        storage.add_screenshot("fff", "2024/05/05 00:00:00", str(tmp_path / "missing.png"))
    assert excinfo.value.key == "file_not_exist"
    with pytest.raises(sm.ScreenshotError) as excinfo:
        storage.replace_screenshot("zzz", str(src))
    assert excinfo.value.key == "screenshot_not_exist"
    (tmp_path / "DevilConnection_photo_bbb_thumb.sav").unlink()
    storage.load_screenshots()
    with pytest.raises(sm.ScreenshotError) as excinfo:
        storage.replace_screenshot("bbb", str(src))
    assert excinfo.value.key == "file_missing"


def test_load_resized_image(storage, tmp_path):
    image = sm.load_resized_image(storage.file_path("aaa"), (8, 6))
    assert image.size == (8, 6)
    bad = tmp_path / "DevilConnection_photo_bad.sav"
    write_sav(bad, "data:image/png;base64,AAAA")
    assert sm.load_resized_image(bad, (8, 6)) is None
    assert sm.load_resized_image(tmp_path / "nope.sav", (8, 6)) is None
