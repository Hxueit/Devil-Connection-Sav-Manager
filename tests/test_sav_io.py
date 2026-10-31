import pytest

from src.utils.sav_io import decode_sav, encode_sav, read_sav, write_sav


def test_round_trip(tmp_path):
    data = {"name": "でびる", "list": [1, 2, {"a": None}], "text": "a b/c%&"}
    path = tmp_path / "test.sav"
    write_sav(path, data)
    assert read_sav(path) == data


def test_encoding_matches_the_game():
    """游戏用 JSON.stringify + encodeURIComponent 写存档，编码结果要和它完全一致"""
    data = {"a": "b/c d", "n": [1, 2.5], "jp": "で"}
    assert encode_sav(data) == "%7B%22a%22%3A%22b%2Fc%20d%22%2C%22n%22%3A%5B1%2C2.5%5D%2C%22jp%22%3A%22%E3%81%A7%22%7D"
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
