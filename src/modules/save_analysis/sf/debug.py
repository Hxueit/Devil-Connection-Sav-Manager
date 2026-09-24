"""存档分析页切换标签时的日志（主窗口 on_tab_changed 使用）

打包时 nuitka 会排除本模块，主窗口在 ImportError 时直接跳过。
"""

import logging

logger = logging.getLogger(__name__)


class AnalyzerDebugger:
    def log_tab_change(self, tab_index: int) -> None:
        logger.debug("Switched to tab %d", tab_index)

    def log_tab_refresh_start(self) -> None:
        logger.debug("Refreshing sf save analyzer tab")

    def log_refresh_complete(self) -> None:
        logger.debug("sf save analyzer tab refreshed")

    def log_tab_refresh_error(self, error: Exception) -> None:
        logger.error("Failed to refresh sf save analyzer tab: %s", error, exc_info=error)

    def log_tab_warning(self, message: str) -> None:
        logger.warning(message)


_debugger = AnalyzerDebugger()


def get_debugger() -> AnalyzerDebugger:
    return _debugger
