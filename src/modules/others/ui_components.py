"""其他功能模块UI组件

提供可复用的UI组件，如进度窗口等。
"""
import logging
import threading
from typing import Optional, Tuple, Dict, Any, Final
from pathlib import Path
import customtkinter as ctk
from src.modules.others.config import OthersTabConfig
from src.modules.others.utils import center_window
from src.modules.others.tyrano_service import TyranoService
from src.utils.styles import Colors, get_cjk_font

logger = logging.getLogger(__name__)


class ProgressWindow:
    """进度窗口管理器
    
    用于显示长时间运行操作的进度，支持后台线程计算和自动关闭。
    """
    
    def __init__(
        self,
        parent: ctk.CTkFrame,
        title: str,
        message: str
    ) -> None:
        """
        初始化进度窗口
        
        Args:
            parent: 父窗口
            title: 窗口标题
            message: 进度消息文本
        """
        self.parent = parent
        self.title = title
        self.message = message
        self.window: Optional[ctk.CTkToplevel] = None
        self.progress_bar: Optional[ctk.CTkProgressBar] = None
    
    def create(self) -> ctk.CTkToplevel:
        """
        创建并显示进度窗口
        
        Returns:
            创建的进度窗口对象
        """
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title(self.title)
        self.window.geometry(
            f"{OthersTabConfig.PROGRESS_WINDOW_WIDTH}x"
            f"{OthersTabConfig.PROGRESS_WINDOW_HEIGHT}"
        )
        self.window.transient(self.parent)
        self.window.grab_set()
        self.window.resizable(False, False)
        
        center_window(self.window)
        
        label = ctk.CTkLabel(
            self.window,
            text=self.message,
            font=get_cjk_font(10),
            text_color=Colors.TEXT_PRIMARY
        )
        label.pack(pady=20)
        
        self.progress_bar = ctk.CTkProgressBar(
            self.window,
            mode='indeterminate',
            width=OthersTabConfig.PROGRESS_BAR_WIDTH,
            fg_color=Colors.GRAY,
            progress_color=Colors.ACCENT_BLUE
        )
        self.progress_bar.pack(pady=10)
        self.progress_bar.start()
        
        return self.window
    
    def destroy(self) -> None:
        """关闭进度窗口"""
        if self.window is None:
            return
        
        try:
            if self.progress_bar is not None:
                try:
                    self.progress_bar.stop()
                except (AttributeError, RuntimeError) as e:
                    logger.debug(f"停止进度条时出错（可能已销毁）: {e}")
            
            try:
                self.window.destroy()
            except (AttributeError, RuntimeError) as e:
                logger.debug(f"销毁窗口时出错（可能已销毁）: {e}")
        except Exception as e:
            logger.warning(f"关闭进度窗口时发生未知错误: {e}")
        finally:
            self.window = None
            self.progress_bar = None


class CRC32Calculator:
    """CRC32计算器（带进度显示）
    
    在后台线程中计算CRC32值，同时显示进度窗口。
    """
    
    def __init__(self, tyrano_service: TyranoService) -> None:
        """
        初始化CRC32计算器
        
        Args:
            tyrano_service: Tyrano服务实例
        """
        self.tyrano_service = tyrano_service
    
    def calculate_with_progress(
        self,
        parent: ctk.CTkFrame,
        new_save_data: Dict[str, Any],
        tyrano_path: Path,
        title: str,
        message: str
    ) -> Optional[Tuple[int, Optional[int]]]:
        """
        带进度显示的CRC32计算
        
        Args:
            parent: 父窗口
            new_save_data: 新的JSON数据
            tyrano_path: tyrano文件路径
            title: 进度窗口标题
            message: 进度消息
            
        Returns:
            (新数据CRC32, 现有文件CRC32) 元组，如果计算失败返回None
        """
        if not new_save_data:
            logger.error("计算数据不能为空")
            return None
        
        if not tyrano_path:
            logger.error("文件路径不能为空")
            return None
        
        progress_window = ProgressWindow(parent, title, message)
        try:
            progress_window.create()
        except Exception as e:
            logger.error(f"创建进度窗口失败: {e}")
            return None
        
        calculation_complete = threading.Event()
        calculation_error = threading.Event()
        result_container: list[Optional[Tuple[int, Optional[int]]]] = [None]
        error_message_container: list[Optional[str]] = [None]
        
        def calculate_crc32() -> None:
            """在后台线程中计算CRC32"""
            try:
                crc32_result = self.tyrano_service.calculate_crc32(
                    new_save_data,
                    tyrano_path
                )
                result_container[0] = crc32_result
            except ValueError as e:
                logger.error(f"CRC32计算失败（数据无效）: {e}")
                calculation_error.set()
                error_message_container[0] = str(e)
            except Exception as e:
                logger.exception("CRC32计算失败（未知错误）")
                calculation_error.set()
                error_message_container[0] = str(e)
            finally:
                calculation_complete.set()
        
        def check_calculation_done() -> None:
            """在主线程中检查计算是否完成"""
            if calculation_complete.is_set():
                try:
                    progress_window.destroy()
                except Exception as e:
                    logger.debug(f"关闭进度窗口时出错: {e}")
            else:
                if progress_window.window is not None:
                    try:
                        progress_window.window.after(
                            OthersTabConfig.POLL_INTERVAL_MS,
                            check_calculation_done
                        )
                    except (AttributeError, RuntimeError) as e:
                        logger.debug(f"调度检查函数失败（窗口可能已关闭）: {e}")
        
        calculation_thread = threading.Thread(target=calculate_crc32, daemon=True)
        calculation_thread.start()
        
        if progress_window.window is not None:
            try:
                progress_window.window.after(
                    OthersTabConfig.POLL_INTERVAL_MS,
                    check_calculation_done
                )
                progress_window.window.wait_window()
            except (AttributeError, RuntimeError) as e:
                logger.debug(f"等待窗口关闭时出错: {e}")
        
        # 等待线程完成，但不超过超时时间
        calculation_thread.join(timeout=OthersTabConfig.CRC32_CALCULATION_TIMEOUT_SECONDS)
        
        if calculation_thread.is_alive():
            logger.warning("CRC32计算超时")
            return None
        
        if calculation_error.is_set():
            error_msg = error_message_container[0] or "未知错误"
            logger.error(f"CRC32计算失败: {error_msg}")
            return None
        
        return result_container[0]

