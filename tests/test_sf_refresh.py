import os

import pytest

tk = pytest.importorskip("tkinter")

from src.modules.save_analysis.sf.analyzer import SaveAnalyzer  # noqa: E402
from src.utils.sav_io import write_sav  # noqa: E402


@pytest.fixture
def root():
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        pytest.skip("needs a display")
    r = tk.Tk()
    yield r
    r.destroy()


def test_refresh_skips_when_save_file_unchanged(root, tmp_path):
    sf_path = tmp_path / "DevilConnection_sf.sav"
    write_sav(sf_path, {"sticker": [1, 2]})
    analyzer = SaveAnalyzer(tk.Frame(root), str(tmp_path), lambda key, **kwargs: key)
    loads = []
    original_update = analyzer.statistics_panel.update
    analyzer.statistics_panel.update = lambda data: (loads.append(data), original_update(data))

    analyzer.refresh()
    root.update()
    assert len(loads) == 1

    analyzer.refresh()  # 文件没变：跳过
    root.update()
    assert len(loads) == 1

    analyzer.refresh(force=True)
    root.update()
    assert len(loads) == 2

    write_sav(sf_path, {"sticker": [1, 2, 3]})
    analyzer.refresh()
    root.update()
    assert len(loads) == 3
    assert loads[-1] == {"sticker": [1, 2, 3]}
