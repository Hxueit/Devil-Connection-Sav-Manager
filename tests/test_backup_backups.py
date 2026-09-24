import zipfile

import pytest

from src.modules.backup import backups


@pytest.fixture
def storage(tmp_path):
    storage = tmp_path / "game" / "_storage"
    (storage / "sub").mkdir(parents=True)
    (storage / "DevilConnection_sf.sav").write_text("sf")
    (storage / "DevilConnection_tyrano_data.sav").write_text("tyrano")
    (storage / "sub" / "img.png").write_bytes(b"x" * 1000)
    return storage


def test_create_scan_restore(storage):
    progress = []
    path = backups.create_backup(storage, lambda cur, total: progress.append((cur, total)))
    assert path.parent == backups.get_backup_dir(storage) == storage.parent / "dcsm_backups"
    assert progress[-1] == (4, 4)
    with zipfile.ZipFile(path) as zf:
        assert set(zf.namelist()) == {
            "dcsmINFO.txt", "DevilConnection_sf.sav", "DevilConnection_tyrano_data.sav", "sub/img.png"
        }
    assert backups.missing_required_files(path) == []

    second = backups.create_backup(storage)  # 同一秒内再次备份不覆盖
    assert second != path
    infos = backups.scan_backups(path.parent)
    assert len(infos) == 2 and all(info.has_info and info.timestamp for info in infos)
    assert not list(path.parent.glob("*.partial"))

    (storage / "DevilConnection_sf.sav").write_text("changed")
    (storage / "extra.txt").write_text("new file")
    backups.restore_backup(path, storage)
    assert (storage / "DevilConnection_sf.sav").read_text() == "sf"
    assert not (storage / "extra.txt").exists()
    assert not (storage / "dcsmINFO.txt").exists()
    assert sorted(p.name for p in storage.parent.iterdir()) == ["_storage", "dcsm_backups"]


def test_failed_backup_leaves_no_file(storage, monkeypatch):
    def broken_write(self, *args, **kwargs):
        raise OSError("file locked")

    monkeypatch.setattr(zipfile.ZipFile, "write", broken_write)
    with pytest.raises(OSError):
        backups.create_backup(storage)
    assert list(backups.get_backup_dir(storage).iterdir()) == []


def test_restore_bad_zip_keeps_storage(storage):
    bad = storage.parent / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(zipfile.BadZipFile):
        backups.restore_backup(bad, storage)
    assert (storage / "DevilConnection_sf.sav").read_text() == "sf"
    assert sorted(p.name for p in storage.parent.iterdir()) == ["_storage", "bad.zip"]


def test_scan_without_info_and_missing_files(tmp_path):
    backup_dir = tmp_path / "dcsm_backups"
    backup_dir.mkdir()
    with zipfile.ZipFile(backup_dir / "plain.zip", "w") as zf:
        zf.writestr("DevilConnection_sf.sav", "sf")
    (backup_dir / "broken.zip").write_bytes(b"junk")
    infos = backups.scan_backups(backup_dir)
    assert {info.zip_path.name: info.has_info for info in infos} == {"plain.zip": False, "broken.zip": False}
    assert backups.missing_required_files(backup_dir / "plain.zip") == ["DevilConnection_tyrano_data.sav"]
    assert backups.missing_required_files(backup_dir / "broken.zip") == backups.REQUIRED_SAVE_FILES
    assert backups.scan_backups(tmp_path / "nope") == []


def test_rename_and_delete(storage):
    path = backups.create_backup(storage)
    other = backups.create_backup(storage)
    renamed = backups.rename_backup(path, "mine")
    assert renamed.name == "mine.zip" and renamed.exists() and not path.exists()
    with pytest.raises(FileExistsError):
        backups.rename_backup(other, "mine.zip")
    backups.delete_backup(renamed)
    assert other.parent.exists()
    backups.delete_backup(other)
    assert not other.parent.exists()


def test_estimate_and_format(storage):
    assert 0 < backups.estimate_compressed_size(storage) <= 1100
    assert backups.format_size(500) == "500 B"
    assert backups.format_size(1536) == "1.50 KB"
    assert backups.format_size(5 * 1024 ** 2) == "5.00 MB"
    assert backups.format_size(3 * 1024 ** 4) == "3072.00 GB"
