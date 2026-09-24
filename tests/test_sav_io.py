import json
import urllib.parse

import pytest

from src.utils.sav_io import decode_sav, encode_sav, read_sav, write_sav


def test_round_trip(tmp_path):
    data = {"name": "でびる", "list": [1, 2, {"a": None}], "text": "a b/c%&"}
    path = tmp_path / "test.sav"
    write_sav(path, data)
    assert read_sav(path) == data


def test_matches_previous_encoding():
    data = {"key": "値 with space"}
    assert encode_sav(data) == urllib.parse.quote(json.dumps(data, ensure_ascii=False))
    assert decode_sav(encode_sav(data) + "\n") == data


def test_failed_write_keeps_original(tmp_path, monkeypatch):
    path = tmp_path / "test.sav"
    write_sav(path, {"v": 1})

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr("os.replace", broken_replace)
    with pytest.raises(OSError):
        write_sav(path, {"v": 2})
    assert read_sav(path) == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["test.sav"]
