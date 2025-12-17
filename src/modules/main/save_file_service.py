"""存档文件读写服务模块

负责存档文件的读取、写入和解析，处理文件锁定问题。
"""
import logging
import os
import json
import urllib.parse
import tempfile
import shutil
import platform
import hashlib
import time
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class SaveFileService:
    """存档文件服务类"""
    
    SAVE_FILE_NAME = "DevilConnection_sf.sav"
    TEMP_FILE_PREFIX = ".temp_sf_"
    TEMP_FILE_SUFFIX = ".sav"
    MAX_RETRIES = 3
    RETRY_DELAY = 0.1
    
    def __init__(self, storage_dir: Optional[str] = None):
        """初始化存档文件服务
        
        Args:
            storage_dir: 存储目录路径
        """
        self.storage_dir = storage_dir
        self.save_file_path: Optional[str] = None
        self.temp_file_path: Optional[str] = None
        
        if storage_dir:
            self._update_paths()
    
    def set_storage_dir(self, storage_dir: str) -> None:
        """设置存储目录
        
        Args:
            storage_dir: 存储目录路径
        """
        self.storage_dir = storage_dir
        self._update_paths()
    
    def _update_paths(self) -> None:
        """更新文件路径"""
        if not self.storage_dir:
            self.save_file_path = None
            self.temp_file_path = None
            return
        
        try:
            self.save_file_path = os.path.join(self.storage_dir, self.SAVE_FILE_NAME)
            self.temp_file_path = os.path.join(
                self.storage_dir, 
                f"{self.TEMP_FILE_PREFIX}{self.SAVE_FILE_NAME}"
            )
        except (OSError, TypeError) as e:
            logger.error(f"Error updating paths: {e}", exc_info=True)
            self.save_file_path = None
            self.temp_file_path = None
    
    def read_file(self, file_path: Optional[str] = None) -> Optional[str]:
        """读取文件内容
        
        Args:
            file_path: 文件路径，如果为None则使用save_file_path
            
        Returns:
            文件内容，失败返回None
        """
        target_path = file_path or self.save_file_path
        if not self._is_valid_file_path(target_path):
            return None
        
        read_strategies = [
            self._read_utf8_text,
            self._read_binary_decode,
            self._read_with_retry
        ]
        
        for strategy in read_strategies:
            try:
                content = strategy(target_path)
                if content is not None:
                    return content.strip()
            except (IOError, OSError, PermissionError, UnicodeDecodeError) as e:
                logger.debug(f"Read strategy failed for {target_path}: {e}")
                continue
        
        logger.warning(f"All read strategies failed for {target_path}")
        return None
    
    def _is_valid_file_path(self, file_path: Optional[str]) -> bool:
        """检查文件路径是否有效
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否有效
        """
        if not file_path or not isinstance(file_path, str):
            return False
        
        try:
            return os.path.exists(file_path) and os.path.isfile(file_path)
        except (OSError, TypeError):
            return False
    
    def _read_utf8_text(self, file_path: str) -> Optional[str]:
        """以UTF-8文本模式读取文件"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='strict') as f:
                return f.read()
        except (IOError, OSError, PermissionError, UnicodeDecodeError) as e:
            logger.debug(f"UTF-8 text read failed for {file_path}: {e}")
            return None
    
    def _read_binary_decode(self, file_path: str) -> Optional[str]:
        """以二进制模式读取并解码"""
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read()
            return raw_data.decode('utf-8', errors='ignore')
        except (IOError, OSError, PermissionError, UnicodeDecodeError) as e:
            logger.debug(f"Binary decode read failed for {file_path}: {e}")
            return None
    
    def _read_with_retry(self, file_path: str, max_retries: Optional[int] = None) -> Optional[str]:
        """带重试的文件读取"""
        if max_retries is None:
            max_retries = self.MAX_RETRIES
        
        for attempt in range(max_retries):
            try:
                if not os.access(file_path, os.R_OK):
                    if attempt < max_retries - 1:
                        time.sleep(self.RETRY_DELAY * (attempt + 1))
                    continue
                
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except (IOError, OSError, PermissionError) as e:
                logger.debug(f"Read retry attempt {attempt + 1} failed for {file_path}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                continue
        return None
    
    def read_save_file(self) -> Optional[Dict[str, Any]]:
        """读取存档文件并解析为JSON对象
        
        Returns:
            存档数据字典，失败返回None
        """
        if not self._is_valid_file_path(self.save_file_path):
            return None
        
        read_strategies = [
            self._read_save_file_direct,
            self._read_save_file_binary,
            self._read_save_file_copy
        ]
        
        for strategy in read_strategies:
            try:
                encoded = strategy()
                if encoded:
                    parsed = self._parse_encoded_content(encoded)
                    if parsed:
                        return parsed
            except Exception as e:
                logger.debug(f"Read save file strategy failed: {e}")
                continue
        
        logger.warning(f"All read strategies failed for save file: {self.save_file_path}")
        return None
    
    def _read_save_file_direct(self) -> Optional[str]:
        """直接读取存档文件"""
        try:
            with open(self.save_file_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except (IOError, OSError, PermissionError, UnicodeDecodeError):
            return None
    
    def _read_save_file_binary(self) -> Optional[str]:
        """以二进制模式读取存档文件"""
        try:
            with open(self.save_file_path, 'rb') as f:
                raw_data = f.read()
            return raw_data.decode('utf-8', errors='ignore').strip()
        except (IOError, OSError, PermissionError, UnicodeDecodeError):
            return None
    
    def _read_save_file_copy(self) -> Optional[str]:
        """通过创建副本读取存档文件（Windows特有）"""
        if platform.system() != "Windows":
            return None
        
        try:
            temp_fd, temp_path = tempfile.mkstemp(suffix='.sav')
            try:
                os.close(temp_fd)
                shutil.copy2(self.save_file_path, temp_path)
                
                with open(temp_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            finally:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
        except Exception:
            return None
    
    def parse_save_content(self, content: str) -> Optional[Dict[str, Any]]:
        """解析存档文件内容为JSON对象
        
        Args:
            content: 存档文件内容
            
        Returns:
            JSON字典对象，失败返回None
        """
        if not content or not isinstance(content, str):
            return None
        
        try:
            unquoted = urllib.parse.unquote(content)
            data = json.loads(unquoted)
            if isinstance(data, dict):
                return data
            logger.warning(f"Parsed content is not a dict: {type(data)}")
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug(f"Failed to parse save content: {e}")
        except Exception as e:
            logger.error(f"Unexpected error parsing save content: {e}", exc_info=True)
        return None
    
    def _parse_encoded_content(self, encoded: str) -> Optional[Dict[str, Any]]:
        """解析编码后的内容"""
        return self.parse_save_content(encoded)
    
    def write_temp_file(self, content: Optional[str]) -> bool:
        """写入临时文件
        
        Args:
            content: 文件内容
            
        Returns:
            是否成功
        """
        if not self._is_valid_temp_file_path() or content is None:
            return False
        
        temp_dir = os.path.dirname(self.temp_file_path)
        if not temp_dir:
            logger.error("Temp file path has no directory")
            return False
        
        try:
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create temp directory {temp_dir}: {e}")
            return False
        
        temp_fd = None
        temp_path = None
        
        try:
            temp_fd, temp_path = tempfile.mkstemp(
                dir=temp_dir,
                prefix=self.TEMP_FILE_PREFIX,
                suffix=self.TEMP_FILE_SUFFIX
            )
            
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                f.write(content)
            temp_fd = None
            
            if os.path.exists(self.temp_file_path):
                os.replace(temp_path, self.temp_file_path)
            else:
                os.rename(temp_path, self.temp_file_path)
            
            return True
        except (OSError, IOError) as e:
            logger.error(f"Failed to write temp file: {e}", exc_info=True)
            if temp_fd is not None:
                try:
                    os.close(temp_fd)
                except OSError:
                    pass
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
            return False
    
    def read_temp_file(self) -> Optional[str]:
        """读取临时文件内容"""
        if not self._is_valid_temp_file_path():
            return None
        
        return self.read_file(self.temp_file_path)
    
    def _is_valid_temp_file_path(self) -> bool:
        """检查临时文件路径是否有效"""
        return (self.temp_file_path is not None and
                isinstance(self.temp_file_path, str) and
                len(self.temp_file_path) > 0)
    
    def get_file_hash(self, content: Optional[str]) -> Optional[str]:
        """获取文件内容的哈希值
        
        Args:
            content: 文件内容
            
        Returns:
            MD5哈希值，失败返回None
        """
        if content is None:
            return None
        
        if not isinstance(content, str):
            return None
        
        try:
            return hashlib.md5(content.encode('utf-8')).hexdigest()
        except (UnicodeEncodeError, AttributeError) as e:
            logger.debug(f"Failed to hash content: {e}")
            return None
    
    def cleanup_temp_file(self) -> None:
        """清理临时文件"""
        if not self._is_valid_temp_file_path():
            return
        
        if not os.path.exists(self.temp_file_path):
            return
        
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                os.remove(self.temp_file_path)
                return
            except (OSError, PermissionError) as e:
                if attempt < max_attempts - 1:
                    time.sleep(self.RETRY_DELAY)
                else:
                    logger.warning(f"Failed to remove temp file after {max_attempts} attempts: {e}")
            except Exception as e:
                logger.error(f"Unexpected error removing temp file: {e}", exc_info=True)
                return
    
    def initialize_temp_file(self) -> bool:
        """初始化临时文件：读取当前存档并写入临时文件
        
        Returns:
            是否成功
        """
        if not self.save_file_path or not isinstance(self.save_file_path, str):
            return False
        
        if not os.path.exists(self.save_file_path):
            if self.temp_file_path and isinstance(self.temp_file_path, str) and os.path.exists(self.temp_file_path):
                try:
                    os.remove(self.temp_file_path)
                except Exception:
                    pass
            return False
        
        save_content = None
        for retry in range(5):
            save_content = self.read_file(self.save_file_path)
            if save_content is not None:
                break
            time.sleep(0.2)
        
        if save_content is not None:
            return self.write_temp_file(save_content)
        
        return False

