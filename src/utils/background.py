"""在后台线程执行耗时操作，结果交回 Tk 主线程

Tkinter 不是线程安全的，后台线程里不能碰控件，也不能调用 after()。
所以后台只负责计算，主线程定时检查，算完后调用 on_done(result, error)。
"""

import logging
import queue
import threading
import tkinter as tk
from collections.abc import Callable
from typing import Any

from src.utils.ui_utils import widget_alive

logger = logging.getLogger(__name__)

POLL_INTERVAL_MS = 30
WORKER_COUNT = 6

# 后台线程在导入本模块时（还没有任何窗口时）就全部启动，之后一直复用。
# 不在点击按钮时临时 Thread.start()：新线程启动时可能触发垃圾回收，
# 回收 tkinter.font.Font 等对象需要主线程配合，而此时主线程正卡在 start() 里等新线程，会互相等待而卡死。
_jobs: "queue.Queue[Callable[[], None]]" = queue.Queue()


def _worker_loop() -> None:
    while True:
        job = _jobs.get()
        job()


for _ in range(WORKER_COUNT):
    threading.Thread(target=_worker_loop, daemon=True, name="background-worker").start()


def run_in_background(
    widget: tk.Misc,
    work: Callable[[], Any],
    on_done: Callable[[Any, BaseException | None], None],
) -> None:
    """widget 已经被销毁时不会调用 on_done"""
    outcome: dict = {}
    finished = threading.Event()

    def job() -> None:
        try:
            outcome["result"] = work()
        except Exception as e:
            logger.exception("Background task failed")
            outcome["error"] = e
        finished.set()

    def poll() -> None:
        if not widget_alive(widget):
            return
        if not finished.is_set():
            widget.after(POLL_INTERVAL_MS, poll)
            return
        on_done(outcome.get("result"), outcome.get("error"))

    _jobs.put(job)
    widget.after(POLL_INTERVAL_MS, poll)
