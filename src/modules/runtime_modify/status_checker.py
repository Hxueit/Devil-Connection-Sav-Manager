"""状态检查器

负责游戏和Hook状态的异步检查，使用线程池和缓存机制避免阻塞主线程。
"""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Callable, Any

import tkinter as tk

from src.modules.runtime_modify.config import RuntimeModifyConfig
from src.modules.runtime_modify.service import RuntimeModifyService
from src.modules.runtime_modify.state import RuntimeModifyState

logger = logging.getLogger(__name__)


class StatusChecker:
    """状态检查器 - 负责游戏和Hook状态的异步检查"""
    
    def __init__(
        self,
        service: RuntimeModifyService,
        state: RuntimeModifyState,
        root: tk.Widget,
        get_port_entry: Callable[[], Optional[Any]],
        on_game_status_updated: Callable[[bool], None],
        on_hook_status_updated: Callable[[bool], None],
        on_ws_url_updated: Callable[[int], None]
    ) -> None:
        """初始化状态检查器
        
        Args:
            service: 运行时修改服务
            state: 状态管理对象
            root: 根窗口（用于after调用）
            get_port_entry: 获取端口输入框的函数
            on_game_status_updated: 游戏状态更新回调
            on_hook_status_updated: Hook状态更新回调
            on_ws_url_updated: WebSocket URL更新回调
        """
        self.service = service
        self.state = state
        self.root = root
        self.get_port_entry = get_port_entry
        self.on_game_status_updated = on_game_status_updated
        self.on_hook_status_updated = on_hook_status_updated
        self.on_ws_url_updated = on_ws_url_updated
        
        # 确保线程池存在
        if not self.state.executor:
            self.state.executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="RuntimeModifyStatus"
            )
    
    def start(self) -> None:
        """启动定时状态检查（完全异步化，不阻塞主线程）"""
        def check() -> None:
            try:
                # 异步更新游戏状态（不阻塞）
                self.check_game_status_async()
                
                # 如果游戏正在运行，检查Hook状态
                # 使用缓存结果判断，避免重复检查
                if (self.state.cached_game_running is True or 
                    (self.state.cached_game_running is None and self.service.game_process is not None)):
                    self.check_hook_status_async()
            except Exception as e:
                logger.debug(f"Status check error: {e}")
            finally:
                # 根据游戏状态动态调整检查间隔
                # 如果游戏未运行，降低检查频率
                interval = (
                    RuntimeModifyConfig.STATUS_CHECK_INTERVAL_IDLE_MS
                    if self.state.cached_game_running is False
                    else RuntimeModifyConfig.STATUS_CHECK_INTERVAL_MS
                )
                self.state.status_check_job = self.root.after(interval, check)
        
        check()
    
    def stop(self) -> None:
        """停止定时状态检查"""
        if self.state.status_check_job:
            try:
                self.root.after_cancel(self.state.status_check_job)
            except (ValueError, AttributeError):
                pass
            self.state.status_check_job = None
    
    def check_game_status_async(self) -> None:
        """异步更新游戏运行状态显示（只要exe在运行就为真）
        
        使用线程池在后台检查，避免阻塞主线程。
        """
        # 检查缓存
        current_time = time.time()
        if (self.state.cached_game_running is not None and 
            current_time - self.state.last_game_status_check < RuntimeModifyConfig.STATUS_CACHE_TTL):
            # 使用缓存结果
            self.on_game_status_updated(self.state.cached_game_running)
            return
        
        # 提交到线程池执行
        if not self.state.executor:
            self.state.executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="RuntimeModifyStatus"
            )
        
        future = self.state.executor.submit(self._check_game_status_in_thread)
        future.add_done_callback(
            lambda f: self.root.after(0, lambda: self._on_game_status_checked(f.result()))
        )
    
    def _check_game_status_in_thread(self) -> bool:
        """在后台线程中检查游戏状态
        
        Returns:
            游戏是否在运行
        """
        try:
            # 快速路径：优先检查自己启动的进程
            if self.service.game_process is not None:
                try:
                    if self.service.game_process.poll() is None:
                        return True
                except (OSError, ProcessLookupError):
                    # 进程已结束或不存在
                    pass
                # 进程已结束，清除引用
                self.service.game_process = None
            
            # 慢速路径：通过exe路径检测系统进程（可能阻塞）
            if self.service.game_exe_path:
                from src.modules.runtime_modify.utils import is_game_running_by_path
                return is_game_running_by_path(self.service.game_exe_path)
            
            return False
        except (OSError, ProcessLookupError) as e:
            logger.debug(f"OS error checking game status: {e}")
            return False
        except Exception as e:
            logger.debug(f"Unexpected error checking game status: {e}")
            return False
    
    def _on_game_status_checked(self, is_running: bool) -> None:
        """游戏状态检查完成回调（在主线程执行）"""
        # 更新缓存
        self.state.cached_game_running = is_running
        self.state.last_game_status_check = time.time()
        
        # 通知外部更新UI
        self.on_game_status_updated(is_running)
    
    def check_hook_status_async(self) -> None:
        """异步检查Hook状态（CDP连接是否可用）
        
        使用线程池和缓存机制，避免频繁检查。
        """
        port_entry = self.get_port_entry()
        if not port_entry:
            return
        
        # 防止重复检查
        if self.state.checking_hook:
            return
        
        # 检查缓存时间
        current_time = time.time()
        if current_time - self.state.last_hook_check_time < RuntimeModifyConfig.STATUS_CACHE_TTL:
            return
        
        try:
            port_str = port_entry.get().strip()
            if not port_str:
                return
            
            port = int(port_str)
            if port < RuntimeModifyConfig.MIN_PORT or port > RuntimeModifyConfig.MAX_PORT:
                logger.debug(f"Port {port} out of valid range")
                return
        except (ValueError, TypeError) as e:
            logger.debug(f"Invalid port value: {e}")
            return
        except AttributeError:
            logger.debug("Port entry widget has no 'get' method")
            return
        
        # 设置检查标志
        self.state.checking_hook = True
        self.state.last_hook_check_time = current_time
        
        # 使用线程池执行检查
        if not self.state.executor:
            self.state.executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="RuntimeModifyStatus"
            )
        
        future = self.state.executor.submit(self._check_hook_status_in_thread, port)
        future.add_done_callback(
            lambda f: self.root.after(0, lambda: self._on_hook_status_checked(f.result(), port))
        )
    
    def _check_hook_status_in_thread(self, port: int) -> bool:
        """在后台线程中检查Hook状态
        
        Args:
            port: CDP端口
            
        Returns:
            Hook是否启用
        """
        loop: Optional[asyncio.AbstractEventLoop] = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            ws_url, _ = loop.run_until_complete(
                self.service.fetch_ws_url(port)
            )
            return ws_url is not None
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.debug(f"Network error checking Hook status on port {port}: {e}")
            return False
        except Exception as e:
            logger.debug(f"Unexpected error checking Hook status on port {port}: {e}")
            return False
        finally:
            if loop:
                try:
                    pending_tasks = asyncio.all_tasks(loop)
                    if pending_tasks:
                        for task in pending_tasks:
                            task.cancel()
                        loop.run_until_complete(
                            asyncio.gather(*pending_tasks, return_exceptions=True)
                        )
                    loop.close()
                except Exception as cleanup_error:
                    logger.debug(f"Error cleaning up event loop: {cleanup_error}")
    
    def _on_hook_status_checked(self, hook_enabled: bool, port: int) -> None:
        """Hook状态检查完成回调（在主线程执行）
        
        Args:
            hook_enabled: Hook是否启用
            port: CDP端口
        """
        self.state.checking_hook = False
        self.on_hook_status_updated(hook_enabled)
        
        # 如果Hook启用，更新缓存的ws_url
        if hook_enabled:
            self.update_cached_ws_url(port)
        else:
            self.state.cached_ws_url = None
    
    def update_cached_ws_url(self, port: int) -> None:
        """更新缓存的 WebSocket URL（异步）
        
        Args:
            port: CDP 端口
        """
        def run_in_thread() -> None:
            """在后台线程中运行异步代码"""
            loop: Optional[asyncio.AbstractEventLoop] = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                ws_url, _ = loop.run_until_complete(
                    self.service.fetch_ws_url(port)
                )
                
                # 在主线程中更新缓存
                self.root.after(0, lambda: self._on_ws_url_fetched(ws_url, port))
            except Exception as e:
                logger.debug(f"Error fetching ws_url: {e}")
                self.root.after(0, lambda: self._on_ws_url_fetched(None, port))
            finally:
                if loop:
                    try:
                        pending_tasks = asyncio.all_tasks(loop)
                        if pending_tasks:
                            for task in pending_tasks:
                                task.cancel()
                            loop.run_until_complete(
                                asyncio.gather(*pending_tasks, return_exceptions=True)
                            )
                        loop.close()
                    except Exception as e:
                        logger.debug(f"Error cleaning up event loop: {e}")
        
        import threading
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
    
    def _on_ws_url_fetched(self, ws_url: Optional[str], port: int) -> None:
        """WebSocket URL 获取完成回调（在主线程执行）
        
        Args:
            ws_url: 获取到的 WebSocket URL
            port: CDP 端口
        """
        self.state.cached_ws_url = ws_url
        if ws_url:
            self.on_ws_url_updated(port)

