from src.modules.main.update_checker import format_release_date, is_newer, parse_version


def test_parse_version():
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("0.5") == (0, 5)
    assert parse_version("v1.2.3-beta") == (1, 2, 3)
    assert parse_version("garbage") == (0,)


def test_is_newer():
    assert is_newer("v0.5.3", "v0.5.2")
    assert is_newer("v0.6", "v0.5.9")
    assert not is_newer("v0.5.2", "v0.5.2")
    assert not is_newer("v0.5", "v0.5.0")
    assert not is_newer("v0.5.1", "v0.5.2")
    assert is_newer("v0.10.0", "v0.9.0")


def test_format_release_date():
    assert format_release_date("2024-01-01T12:00:00Z") == "2024-01-01 12:00:00"
    assert format_release_date("") == ""
