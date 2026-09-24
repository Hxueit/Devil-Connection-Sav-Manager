"""在后台线程执行耗时操作，并把结果交回 Tk 主线程

Tkinter 不是线程安全的：后台线程里不能创建/修改控件，也不能调用 after()。
run_in_background 让后台线程只负责计算，结果由主线程定时检查后再回调，
所以回调函数里可以放心地更新界面。

用法：
    def work():
        return read_something_slow()        # 在后台线程执行，不要碰界面

    def done(result, error):
        if error:                           # 出错时 result 为 None，error 是异常对象
            show_error(str(error))
        else:
            label.config(text=result)       # 在主线程执行，可以更新界面

    run_in_background(root, work, done)
"""

import logging
import queue
import threading
import tkinter as tk
from typing import Any, Callable, Optional

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
    on_done: Optional[Callable[[Any, Optional[BaseException]], None]] = None,
) -> None:
    """在后台线程执行 work()，完成后在主线程调用 on_done(result, error)

    Args:
        widget: 任意一个 Tk 控件，用来在主线程上定时检查结果
        work: 在后台线程执行的函数，不能操作界面
        on_done: 完成后在主线程调用；如果 widget 已经被销毁则不会调用
    """
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
        try:
            if not widget.winfo_exists():
                return
        except tk.TclError:
            return
        if not finished.is_set():
            widget.after(POLL_INTERVAL_MS, poll)
            return
        if on_done is not None:
            on_done(outcome.get("result"), outcome.get("error"))

    _jobs.put(job)
    widget.after(POLL_INTERVAL_MS, poll)
