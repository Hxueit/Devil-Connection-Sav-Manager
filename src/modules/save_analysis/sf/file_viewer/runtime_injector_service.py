"""运行时注入服务

负责运行时模式下的数据注入、刷新和错误处理。
"""

import asyncio
import logging
import threading
from typing import Any, Callable, Dict, Optional, Tuple

import tkinter as tk
from tkinter import messagebox

from src.utils.ui_utils import showerror_relative, showinfo_relative

from .config import REFRESH_AFTER_INJECT_DELAY_MS
from .models import ViewerConfig

logger = logging.getLogger(__name__)


class RuntimeInjectorService:
    """运行时注入服务，处理运行时模式下的数据操作"""
    
    def __init__(
        self,
        window: tk.Widget,
        viewer_config: ViewerConfig,
        translate_func: Callable[[str], str]
    ):
        """初始化运行时注入服务
        
        Args:
            window: 窗口对象
            viewer_config: 查看器配置
            translate_func: 翻译函数
        """
        self.window = window
        self.viewer_config = viewer_config
        self.t = translate_func
    
    def is_available(self) -> bool:
        """检查运行时服务是否可用
        
        Returns:
            服务是否可用
        """
        return (self.viewer_config.service is not None and 
                self.viewer_config.ws_url is not None)
    
    def save_to_runtime(
        self,
        edited_data: Dict[str, Any],
        original_save_data: Dict[str, Any],
        on_success: Callable[[Dict[str, Any]], None],
        on_error: Callable[[str], None],
        require_confirmation: bool = True
    ) -> None:
        """保存数据到运行时内存
        
        Args:
            edited_data: 编辑后的数据
            original_save_data: 原始存档数据（用于变更检测）
            on_success: 成功回调，接收 edited_data 作为参数
            on_error: 错误回调，接收错误消息作为参数
            require_confirmation: 是否需要用户确认
        """
        if not self.is_available():
            error_msg = self.t("runtime_modify_sf_game_not_running")
            on_error(error_msg)
            return
        
        if require_confirmation:
            if self.viewer_config.inject_method == "kag_stat":
                confirm_key = "runtime_modify_kag_stat_confirm_inject"
            else:
                confirm_key = "runtime_modify_sf_confirm_inject"
            
            user_confirmed = messagebox.askyesno(
                self.t("save_confirm_title"),
                self.t(confirm_key),
                parent=self.window
            )
            if not user_confirmed:
                return
        
        if self.viewer_config.inject_method == "kag_stat":
            self._inject_kag_stat(edited_data, on_success, on_error)
        else:
            self.check_changes_and_inject(edited_data, original_save_data, on_success, on_error)
    
    def refresh_from_runtime(
        self,
        on_complete: Callable[[Optional[Dict[str, Any]], Optional[str]], None]
    ) -> None:
        """从运行时内存刷新数据
        
        Args:
            on_complete: 完成回调 (data, error)
        """
        if not self.is_available():
            error_msg = self.t("runtime_modify_sf_game_not_running")
            on_complete(None, error_msg)
            return
        
        if self.viewer_config.inject_method == "kag_stat":
            read_method = self.viewer_config.service.read_tyrano_kag_stat
            error_key = "runtime_modify_kag_stat_read_failed"
        else:
            read_method = self.viewer_config.service.read_tyrano_variable_sf
            error_key = "runtime_modify_sf_read_failed"
        
        def read_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                data, error = loop.run_until_complete(read_method(self.viewer_config.ws_url))
                self.window.after(0, lambda: self._on_read_complete(data, error, error_key, on_complete))
            except Exception as e:
                logger.error(f"Error reading runtime data: {e}", exc_info=True)
                self.window.after(0, lambda: on_complete(None, str(e)))
            finally:
                loop.close()
        
        thread = threading.Thread(target=read_in_thread, daemon=True)
        thread.start()
    
    def check_changes_and_inject(
        self,
        edited_data: Dict[str, Any],
        original_save_data: Dict[str, Any],
        on_success: Callable[[Dict[str, Any]], None],
        on_error: Callable[[str], None]
    ) -> None:
        """检查变更并执行注入"""
        def check_and_inject_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                has_changes, changes_info = loop.run_until_complete(
                    self.viewer_config.service.check_sf_changes(
                        self.viewer_config.ws_url,
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
                        self.window.after(0, lambda: on_error(self.t("user_cancelled")))
                        return
                
                success, error = loop.run_until_complete(
                    self.viewer_config.service.inject_and_save_sf(
                        self.viewer_config.ws_url,
                        edited_data
                    )
                )
                
                if success:
                    self.window.after(0, lambda: self._on_inject_success(edited_data, on_success))
                else:
                    error_msg = error or self.t("runtime_modify_sf_error_unknown")
                    showerror_relative(
                        self.window,
                        self.t("error"),
                        self.t("runtime_modify_sf_inject_failed").format(error=error_msg)
                    )
                    self.window.after(0, lambda: on_error(error_msg))
            except Exception as e:
                logger.error(f"Error in check_and_inject: {e}", exc_info=True)
                error_msg = str(e)
                showerror_relative(
                    self.window,
                    self.t("error"),
                    self.t("runtime_modify_sf_inject_failed").format(error=error_msg)
                )
                self.window.after(0, lambda: on_error(error_msg))
            finally:
                loop.close()
        
        thread = threading.Thread(target=check_and_inject_in_thread, daemon=True)
        thread.start()
    
    def _inject_kag_stat(
        self,
        edited_data: Dict[str, Any],
        on_success: Callable[[Dict[str, Any]], None],
        on_error: Callable[[str], None]
    ) -> None:
        """注入 kag.stat 数据"""
        inject_coro = self.viewer_config.service.inject_kag_stat(
            self.viewer_config.ws_url,
            edited_data
        )
        
        def on_complete(success: bool, error: Optional[str]) -> None:
            if success:
                self._on_inject_success(edited_data, on_success)
            else:
                error_msg = error or "Unknown error"
                logger.error("kag.stat injection failed: %s", error_msg)
                showerror_relative(
                    self.window,
                    self.t("error"),
                    self.t("runtime_modify_kag_stat_inject_failed").format(error=error_msg)
                )
                on_error(error_msg)
        
        self._run_async_in_thread(inject_coro, on_complete)
    
    def _on_inject_success(
        self,
        edited_data: Dict[str, Any],
        on_success: Callable[[Dict[str, Any]], None]
    ) -> None:
        """注入成功处理"""
        if self.viewer_config.on_save_callback:
            try:
                self.viewer_config.on_save_callback(edited_data)
            except Exception as callback_error:
                logger.error(f"on_save_callback failed: {callback_error}", exc_info=True)
        
        showinfo_relative(
            self.window,
            self.t("success"),
            self.t("runtime_modify_sf_inject_success")
        )
        
        on_success(edited_data)
    
    def _on_read_complete(
        self,
        data: Optional[Dict[str, Any]],
        error: Optional[str],
        error_key: str,
        on_complete: Callable[[Optional[Dict[str, Any]], Optional[str]], None]
    ) -> None:
        """读取完成回调"""
        if error:
            error_msg = self.t(error_key).format(error=error)
            on_complete(None, error_msg)
            return
        
        if data is None:
            if error_key == "runtime_modify_kag_stat_read_failed":
                error_msg = self.t("runtime_modify_kag_stat_read_failed").format(error="Empty data")
            else:
                error_msg = self.t("runtime_modify_sf_error_empty_data")
            on_complete(None, error_msg)
            return
        
        on_complete(data, None)
    
    def refresh_after_inject(
        self,
        on_complete: Callable[[Optional[Dict[str, Any]], Optional[str]], None]
    ) -> None:
        """注入后刷新数据"""
        if not self.is_available():
            on_complete(None, self.t("runtime_modify_sf_game_not_running"))
            return
        
        def read_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                if self.viewer_config.inject_method == "kag_stat":
                    read_method = self.viewer_config.service.read_tyrano_kag_stat
                else:
                    read_method = self.viewer_config.service.read_tyrano_variable_sf
                
                data, read_error = loop.run_until_complete(read_method(self.viewer_config.ws_url))
                self.window.after(0, lambda: on_complete(data, read_error))
            except Exception as e:
                logger.error(f"Error refreshing after inject: {e}", exc_info=True)
                self.window.after(0, lambda: on_complete(None, str(e)))
            finally:
                loop.close()
        
        def start_refresh():
            thread = threading.Thread(target=read_in_thread, daemon=True)
            thread.start()
        
        self.window.after(REFRESH_AFTER_INJECT_DELAY_MS, start_refresh)
    
    def _run_async_in_thread(
        self,
        coro: Any,
        on_complete: Callable[[bool, Optional[str]], None]
    ) -> None:
        """在后台线程中运行异步协程
        
        Args:
            coro: 异步协程对象
            on_complete: 完成回调 (success, error)
        """
        """在后台线程中运行异步协程"""
        def run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result, error = loop.run_until_complete(coro)
                self.window.after(0, lambda: on_complete(result, error))
            except Exception as e:
                logger.exception("Unexpected error in async thread")
                self.window.after(0, lambda: on_complete(False, str(e)))
            finally:
                pending = asyncio.all_tasks(loop)
                if pending:
                    for task in pending:
                        task.cancel()
                    try:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    except Exception as gather_error:
                        logger.debug("Error gathering pending tasks: %s", gather_error)
                loop.close()
        
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
