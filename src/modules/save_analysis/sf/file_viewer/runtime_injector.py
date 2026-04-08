"""运行时内存注入模块

提供运行时模式下的内存注入和刷新功能
"""

import asyncio
import json
import logging
import threading
from typing import Any, Callable, Dict, Optional

import tkinter as tk
from tkinter import messagebox

from src.utils.ui_utils import showerror_relative, showinfo_relative

logger = logging.getLogger(__name__)

# 常量定义
_REFRESH_AFTER_INJECT_DELAY_MS: int = 200  # 注入后刷新延迟（毫秒）


class RuntimeInjector:
    """运行时内存注入器"""
    
    def __init__(
        self,
        window: tk.Widget,
        service: Any,
        ws_url: Optional[str],
        t_func: Callable[[str], str]
    ) -> None:
        """初始化注入器
        
        Args:
            window: 窗口对象
            service: 运行时服务对象
            ws_url: WebSocket URL
            t_func: 翻译函数
        """
        self.window = window
        self.service = service
        self.ws_url = ws_url
        self.t = t_func
    
    def check_changes_and_inject_async(
        self,
        edited_data: Dict[str, Any],
        original_save_data: Dict[str, Any],
        on_complete: Callable[[bool, Optional[str], Dict[str, Any]], None]
    ) -> None:
        """异步检查变更并执行注入
        
        Args:
            edited_data: 编辑后的数据
            original_save_data: 原始存档数据
            on_complete: 完成回调函数 (success, error, edited_data)
        """
        def check_and_inject_in_thread():
            """在后台线程中检查变更并执行注入"""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                has_changes, changes_info = loop.run_until_complete(
                    self.service.check_sf_changes(
                        self.ws_url,
                        original_save_data
                    )
                )
                changes_text = changes_info.get("changes_text", "") if has_changes else ""
                
                if has_changes:
                    # 在主线程中显示警告
                    user_continue = messagebox.askyesno(
                        self.t("warning"),
                        self.t("runtime_modify_sf_changes_detected").format(changes=changes_text),
                        parent=self.window
                    )
                    if not user_continue:
                        self.window.after(0, lambda: on_complete(False, None, edited_data))
                        return
                
                # 执行注入
                success, error = loop.run_until_complete(
                    self.service.inject_and_save_sf(
                        self.ws_url,
                        edited_data
                    )
                )
                self.window.after(0, lambda: on_complete(success, error, edited_data))
            except Exception as e:
                logger.error(f"Error in check_and_inject: {e}", exc_info=True)
                self.window.after(0, lambda: on_complete(False, str(e), edited_data))
            finally:
                loop.close()
        
        thread = threading.Thread(target=check_and_inject_in_thread, daemon=True)
        thread.start()
    
    def read_save_data_async(
        self,
        on_complete: Callable[[Optional[Dict[str, Any]], Optional[str]], None]
    ) -> None:
        """异步读取存档数据
        
        Args:
            on_complete: 完成回调函数 (data, error)
        """
        def read_in_thread():
            """在后台线程中读取数据"""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                data, error = loop.run_until_complete(
                    self.service.read_tyrano_variable_sf(self.ws_url)
                )
                self.window.after(0, lambda: on_complete(data, error))
            except Exception as e:
                logger.error(f"Error reading save data: {e}", exc_info=True)
                self.window.after(0, lambda: on_complete(None, str(e)))
            finally:
                loop.close()
        
        thread = threading.Thread(target=read_in_thread, daemon=True)
        thread.start()
    
    def refresh_after_inject(
        self,
        on_complete: Callable[[Optional[Dict[str, Any]], Optional[str]], None]
    ) -> None:
        """注入后刷新数据
        
        Args:
            on_complete: 完成回调函数 (data, error)
        """
        def read_in_thread():
            """在后台线程中读取数据"""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                data, read_error = loop.run_until_complete(
                    self.service.read_tyrano_variable_sf(self.ws_url)
                )
                self.window.after(0, lambda: on_complete(data, read_error))
            except Exception as e:
                logger.error(f"Error refreshing after inject: {e}", exc_info=True)
                self.window.after(0, lambda: on_complete(None, str(e)))
            finally:
                loop.close()
        
        # 延迟一点再刷新，确保注入操作完全完成
        def start_refresh():
            thread = threading.Thread(target=read_in_thread, daemon=True)
            thread.start()
        
        self.window.after(_REFRESH_AFTER_INJECT_DELAY_MS, start_refresh)







