"""文件监控模块

负责监控存档文件的变化并触发相应的通知。
"""
import logging
import os
import threading
import time
from typing import Optional, Callable, Dict, Any

from src.modules.main.save_file_service import SaveFileService
from src.modules.main.save_data_comparator import SaveDataComparator

logger = logging.getLogger(__name__)


class FileMonitor:
    """文件监控器类
    
    使用内存缓存存储上一次的文件状态。
    """
    
    MONITOR_INTERVAL = 0.3
    ERROR_RETRY_DELAY = 1.0
    THREAD_JOIN_TIMEOUT = 2.0
    FILE_READ_MAX_RETRIES = 3
    FILE_READ_RETRY_DELAY = 0.1
    INITIALIZATION_RETRY_ATTEMPTS = 5
    INITIALIZATION_RETRY_DELAY = 0.2
    
    def __init__(
        self,
        storage_dir: Optional[str],
        save_file_service: SaveFileService,
        comparator: SaveDataComparator,
        on_change: Callable[[list[str]], None],
        on_ab_initio: Optional[Callable[[], None]] = None
    ):
        """初始化文件监控器
        
        Args:
            storage_dir: 存储目录路径
            save_file_service: 存档文件服务
            comparator: 数据比较器
            on_change: 变更回调函数
            on_ab_initio: AB INITIO事件回调函数
            
        Raises:
            ValueError: 如果必需参数为None
        """
        if save_file_service is None:
            raise ValueError("save_file_service cannot be None")
        if comparator is None:
            raise ValueError("comparator cannot be None")
        if on_change is None:
            raise ValueError("on_change cannot be None")
        
        self.storage_dir = storage_dir
        self.save_file_service = save_file_service
        self.comparator = comparator
        self.on_change = on_change
        self.on_ab_initio = on_ab_initio
        
        # 内存缓存：存储上一次的文件状态
        self._last_save_content_hash: Optional[str] = None
        self._last_save_content: Optional[str] = None
        self._last_save_data: Optional[Dict[str, Any]] = None
        
        # 线程控制
        self.monitor_thread: Optional[threading.Thread] = None
        self.monitor_running = False
        self.ab_initio_triggered = False
        self._shutdown_lock = threading.Lock()
    
    def start(self) -> None:
        """启动文件监控"""
        if not self.storage_dir:
            return
        
        self.stop()
        
        self.save_file_service.set_storage_dir(self.storage_dir)
        self._initialize_memory_cache()
        
        self.monitor_running = True
        self.ab_initio_triggered = False
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop(self) -> None:
        """停止文件监控"""
        with self._shutdown_lock:
            if not self.monitor_running:
                return
            
            self.monitor_running = False
            
            if self.monitor_thread is not None and self.monitor_thread.is_alive():
                try:
                    self.monitor_thread.join(timeout=self.THREAD_JOIN_TIMEOUT)
                    if self.monitor_thread.is_alive():
                        logger.warning("Monitor thread did not stop gracefully within timeout")
                except (RuntimeError, OSError) as e:
                    logger.error(f"Error stopping monitor thread: {e}", exc_info=True)
                finally:
                    self.monitor_thread = None
            
            self._clear_memory_cache()
    
    def set_storage_dir(self, storage_dir: str) -> None:
        """设置存储目录
        
        Args:
            storage_dir: 存储目录路径
        """
        self.storage_dir = storage_dir
        if self.monitor_running:
            self.start()
    
    def _monitor_loop(self) -> None:
        """监控循环（在后台线程中运行）"""
        while self.monitor_running:
            try:
                self._check_file_changes()
            except (OSError, PermissionError) as e:
                logger.warning(f"File I/O error in monitor loop: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in monitor loop: {e}", exc_info=True)
            
            if self.monitor_running:
                time.sleep(self.MONITOR_INTERVAL)
    
    def _check_file_changes(self) -> None:
        """检查文件是否有变动（通过比较当前文件和内存缓存）"""
        if not self._is_valid_storage_dir():
            return
        
        save_file_path = self.save_file_service.save_file_path
        if not save_file_path:
            return
        
        storage_dir_exists = self._safe_path_exists(self.storage_dir)
        save_file_exists = self._safe_path_exists(save_file_path)
        
        if not save_file_exists:
            if not storage_dir_exists:
                self._handle_ab_initio()
            elif self._last_save_content_hash is not None:
                # 文件被删除，清空缓存
                self._clear_memory_cache()
            return
        
        current_save_content = self._read_save_file_with_retry(save_file_path)
        if current_save_content is None:
            return
        
        current_hash = self.save_file_service.get_file_hash(current_save_content)
        if current_hash is None:
            return
        
        # 首次初始化或文件哈希值发生变化
        if self._last_save_content_hash is None:
            self._update_memory_cache(current_save_content, current_hash)
            return
        
        if current_hash == self._last_save_content_hash:
            return
        
        # 文件内容发生变化，处理变更
        self._process_file_changes(current_save_content, current_hash)
    
    def _handle_ab_initio(self) -> None:
        """处理AB INITIO事件"""
        if not self.ab_initio_triggered and self.on_ab_initio:
            self.ab_initio_triggered = True
            try:
                self.on_ab_initio()
            except Exception as e:
                logger.error(f"Error in ab_initio callback: {e}", exc_info=True)
    
    def _read_save_file_with_retry(
        self, 
        save_file_path: str, 
        max_retries: Optional[int] = None
    ) -> Optional[str]:
        """带重试的文件读取，处理文件锁定等异常情况
        
        Args:
            save_file_path: 存档文件路径
            max_retries: 最大重试次数，默认使用类常量
            
        Returns:
            文件内容，失败返回None
        """
        if max_retries is None:
            max_retries = self.FILE_READ_MAX_RETRIES
        
        for attempt in range(max_retries):
            try:
                save_content = self.save_file_service.read_file(save_file_path)
                if save_content is not None:
                    return save_content
            except (OSError, PermissionError) as e:
                logger.debug(
                    f"File read attempt {attempt + 1}/{max_retries} failed "
                    f"(file may be locked): {e}"
                )
            except Exception as e:
                logger.warning(f"Unexpected error reading file: {e}")
            
            if attempt < max_retries - 1:
                time.sleep(self.FILE_READ_RETRY_DELAY * (attempt + 1))
        
        return None
    
    def _process_file_changes(self, current_save_content: str, current_hash: str) -> None:
        """处理文件变化
        
        Args:
            current_save_content: 当前存档文件内容
            current_hash: 当前文件内容的哈希值
        """
        if self._last_save_content is None or self._last_save_data is None:
            # 无法比较，直接更新缓存
            self._update_memory_cache(current_save_content, current_hash)
            return
        
        try:
            last_save_data = self._last_save_data
            current_save_data = self.save_file_service.parse_save_content(current_save_content)
            
            if current_save_data is None:
                logger.warning("Failed to parse current save content, updating cache without comparison")
                self._update_memory_cache(current_save_content, current_hash)
                return
            
            changes = self.comparator.deep_compare(last_save_data, current_save_data)
            
            if changes:
                try:
                    self.on_change(changes)
                except Exception as e:
                    logger.error(f"Error in change callback: {e}", exc_info=True)
            
            # 更新内存缓存
            self._update_memory_cache(current_save_content, current_hash, current_save_data)
        except (ValueError, TypeError) as e:
            logger.warning(f"Error parsing save content: {e}, updating cache without comparison")
            self._update_memory_cache(current_save_content, current_hash)
        except Exception as e:
            logger.error(f"Unexpected error processing file changes: {e}", exc_info=True)
            # 即使出错也更新缓存，避免重复处理
            self._update_memory_cache(current_save_content, current_hash)
    
    def _initialize_memory_cache(self) -> None:
        """初始化内存缓存：读取当前存档文件并缓存其状态"""
        save_file_path = self.save_file_service.save_file_path
        if not save_file_path:
            return
        
        if not self._safe_path_exists(save_file_path):
            return
        
        for attempt in range(self.INITIALIZATION_RETRY_ATTEMPTS):
            save_content = self._read_save_file_with_retry(save_file_path)
            if save_content is not None:
                save_hash = self.save_file_service.get_file_hash(save_content)
                if save_hash is not None:
                    save_data = self.save_file_service.parse_save_content(save_content)
                    self._update_memory_cache(save_content, save_hash, save_data)
                    return
            
            if attempt < self.INITIALIZATION_RETRY_ATTEMPTS - 1:
                time.sleep(self.INITIALIZATION_RETRY_DELAY)
    
    def _update_memory_cache(
        self,
        save_content: str,
        save_hash: str,
        save_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """更新内存缓存
        
        Args:
            save_content: 存档文件内容
            save_hash: 文件内容的哈希值
            save_data: 解析后的存档数据（可选，如果为None则尝试解析）
        """
        self._last_save_content_hash = save_hash
        self._last_save_content = save_content
        
        if save_data is None:
            save_data = self.save_file_service.parse_save_content(save_content)
        
        self._last_save_data = save_data
    
    def _clear_memory_cache(self) -> None:
        """清空内存缓存"""
        self._last_save_content_hash = None
        self._last_save_content = None
        self._last_save_data = None
    
    def _is_valid_storage_dir(self) -> bool:
        """检查存储目录是否有效
        
        Returns:
            是否有效
        """
        return (
            self.storage_dir is not None 
            and isinstance(self.storage_dir, str) 
            and len(self.storage_dir) > 0
        )
    
    def _safe_path_exists(self, path: Optional[str]) -> bool:
        """安全地检查路径是否存在
        
        Args:
            path: 路径
            
        Returns:
            是否存在
        """
        if not path or not isinstance(path, str):
            return False
        
        try:
            return os.path.exists(path)
        except (OSError, PermissionError) as e:
            logger.debug(f"Error checking path existence: {e}")
            return False
        except (TypeError, ValueError, AttributeError) as e:
            logger.warning(f"Invalid path type: {e}")
            return False
