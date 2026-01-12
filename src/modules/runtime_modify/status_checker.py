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
        """启动定时状态检查"""
        def check() -> None:
            if self.state.is_closing:
                return
            
            try:
                self.check_game_status_async()
                if (self.state.cached_game_running is True or 
                    (self.state.cached_game_running is None and self.service.game_process is not None)):
                    self.check_hook_status_async()
            except Exception as e:
                logger.debug(f"Status check error: {e}")
            finally:
                if self.state.is_closing:
                    return
                
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
        """异步更新游戏运行状态"""
        if self.state.is_closing:
            return
        
        current_time = time.time()
        if (self.state.cached_game_running is not None and 
            current_time - self.state.last_game_status_check < RuntimeModifyConfig.STATUS_CACHE_TTL):
            self.on_game_status_updated(self.state.cached_game_running)
            return
        
        if not self.state.executor:
            self.state.executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="RuntimeModifyStatus"
            )
        
        future = self.state.executor.submit(self._check_game_status_in_thread)
        future.add_done_callback(
            lambda f: self._safe_after_callback(lambda: self._on_game_status_checked(f.result()))
        )
    
    def _safe_after_callback(self, callback: Callable[[], None]) -> None:
        """安全调用 root.after，检查关闭状态和窗口有效性"""
        if self.state.is_closing:
            return
        if not hasattr(self.root, 'after'):
            return
        try:
            self.root.after(0, callback)
        except (tk.TclError, RuntimeError):
            pass
    
    def _check_game_status_in_thread(self) -> bool:
        """在后台线程中检查游戏状态
        
        Returns:
            游戏是否在运行
        """
        if self.state.is_closing:
            return False
        
        try:
            if self.service.game_process is not None:
                if self.service.game_process.poll() is None:
                    return True
                self.service.game_process = None
            
            if self.state.is_closing:
                return False
            
            if self.service.game_exe_path:
                from src.modules.runtime_modify.utils import is_game_running_by_path
                return is_game_running_by_path(self.service.game_exe_path)
            
            return False
        except (OSError, ProcessLookupError) as e:
            logger.debug(f"OS error checking game status: {e}")
            if self.service.game_process is not None:
                self.service.game_process = None
            return False
        except Exception as e:
            logger.debug(f"Unexpected error checking game status: {e}")
            return False
    
    def _on_game_status_checked(self, is_running: bool) -> None:
        """游戏状态检查完成回调"""
        self.state.cached_game_running = is_running
        self.state.last_game_status_check = time.time()
        self.on_game_status_updated(is_running)
    
    def check_hook_status_async(self) -> None:
        """异步检查Hook状态"""
        if self.state.is_closing:
            return
        
        port_entry = self.get_port_entry()
        if not port_entry:
            return
        
        if self.state.checking_hook:
            return
        
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
        
        self.state.checking_hook = True
        self.state.last_hook_check_time = current_time
        
        if not self.state.executor:
            self.state.executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="RuntimeModifyStatus"
            )
        
        future = self.state.executor.submit(self._check_hook_status_in_thread, port)
        future.add_done_callback(
            lambda f: self._safe_after_callback(lambda: self._on_hook_status_checked(f.result(), port))
        )
    
    def _check_hook_status_in_thread(self, port: int) -> bool:
        """在后台线程中检查Hook状态
        
        Args:
            port: CDP端口
            
        Returns:
            Hook是否启用
        """
        if self.state.is_closing:
            return False
        
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
        """Hook状态检查完成回调
        
        Args:
            hook_enabled: Hook是否启用
            port: CDP端口
        """
        self.state.checking_hook = False
        self.on_hook_status_updated(hook_enabled)
        
        if hook_enabled:
            self.update_cached_ws_url(port)
        else:
            self.state.cached_ws_url = None
    
    def update_cached_ws_url(self, port: int) -> None:
        """更新缓存的 WebSocket URL
        
        Args:
            port: CDP 端口
        """
        if self.state.is_closing:
            return
        
        def run_in_thread() -> None:
            if self.state.is_closing:
                return
            
            loop: Optional[asyncio.AbstractEventLoop] = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                ws_url, _ = loop.run_until_complete(
                    self.service.fetch_ws_url(port)
                )
                
                self._safe_after_callback(lambda: self._on_ws_url_fetched(ws_url, port))
            except Exception as e:
                logger.debug(f"Error fetching ws_url: {e}")
                self._safe_after_callback(lambda: self._on_ws_url_fetched(None, port))
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
        """WebSocket URL 获取完成回调
        
        Args:
            ws_url: 获取到的 WebSocket URL
            port: CDP 端口
        """
        self.state.cached_ws_url = ws_url
        if ws_url:
            self.on_ws_url_updated(port)

