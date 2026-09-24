import os

import pytest

tk = pytest.importorskip("tkinter")

from src.utils.background import run_in_background  # noqa: E402


@pytest.fixture
def root():
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        pytest.skip("needs a display")
    r = tk.Tk()
    yield r
    r.destroy()


def _run_until(root, results):
    root.after(3000, root.quit)
    root.mainloop()
    return results


def test_result_delivered_on_main_thread(root):
    import threading
    main = threading.get_ident()
    results = []

    def done(result, error):
        results.append((result, error, threading.get_ident() == main))
        root.quit()

    run_in_background(root, lambda: 42, done)
    assert _run_until(root, results) == [(42, None, True)]


def test_error_delivered(root):
    results = []

    def work():
        raise ValueError("boom")

    def done(result, error):
        results.append((result, type(error)))
        root.quit()

    run_in_background(root, work, done)
    assert _run_until(root, results) == [(None, ValueError)]
