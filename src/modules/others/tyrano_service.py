"""Tyrano数据处理服务模块

负责Tyrano保存文件的编码/解码、CRC32计算等业务逻辑。
不包含UI相关代码，可独立测试和复用。
"""
import json
import logging
import urllib.parse
import zlib
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Final

from src.modules.others.config import OthersTabConfig

logger = logging.getLogger(__name__)

# 常量
_DEFAULT_TIMEOUT_SECONDS: Final[int] = 30
_CRC32_MASK: Final[int] = 0xffffffff
_BYTES_PER_MB: Final[int] = 1024 * 1024


class TyranoService:
    """Tyrano数据处理服务"""
    
    def __init__(self, calculation_timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS) -> None:
        """
        初始化Tyrano服务
        
        Args:
            calculation_timeout_seconds: CRC32计算超时时间（秒）
            
        Raises:
            ValueError: 如果超时时间小于等于0
        """
        if calculation_timeout_seconds <= 0:
            raise ValueError("Timeout must be greater than 0")
        self.calculation_timeout_seconds = calculation_timeout_seconds
    
    def load_tyrano_save_file(self, tyrano_path: Path) -> Dict[str, Any]:
        """
        加载并解码tyrano保存文件
        
        Args:
            tyrano_path: tyrano保存文件路径
            
        Returns:
            解码后的JSON数据字典
            
        Raises:
            FileNotFoundError: 文件不存在
            PermissionError: 无权限读取文件
            OSError: 文件读取失败
            json.JSONDecodeError: JSON解析失败
            UnicodeDecodeError: 编码解码失败
            ValueError: 内存不足或文件过大
        """
        if not tyrano_path.exists():
            raise FileNotFoundError(f"文件不存在: {tyrano_path}")
        
        if not tyrano_path.is_file():
            raise ValueError(f"路径不是文件: {tyrano_path}")
        
        # 检查文件大小（记录日志，不阻止操作）
        self._log_large_file_if_needed(tyrano_path)
        
        try:
            with tyrano_path.open('r', encoding='utf-8') as f:
                encoded_content = f.read().strip()
        except MemoryError:
            logger.error(f"Insufficient memory to read file: {tyrano_path}")
            raise ValueError("Insufficient memory to read file. Please close other programs and try again.")
        except PermissionError:
            logger.error(f"Permission denied reading file: {tyrano_path}")
            raise
        except OSError as e:
            logger.error(f"Failed to read file: {tyrano_path}, error: {e}")
            raise
        
        if not encoded_content:
            raise ValueError(f"File is empty: {tyrano_path}")
        
        try:
            unquoted_content = urllib.parse.unquote(encoded_content)
        except Exception as e:
            logger.error(f"URL decode failed: {e}")
            raise ValueError(f"URL decode failed: {e}")
        
        try:
            return json.loads(unquoted_content)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {e}")
            raise
    
    def save_tyrano_save_file(
        self,
        tyrano_path: Path,
        save_data: Dict[str, Any]
    ) -> None:
        """
        编码并保存tyrano保存文件
        
        Args:
            tyrano_path: tyrano保存文件路径
            save_data: 要保存的JSON数据字典
            
        Raises:
            PermissionError: 无权限写入文件
            OSError: 文件写入失败（包括磁盘空间不足）
            ValueError: 数据为空或无效
        """
        if not save_data:
            raise ValueError("Save data cannot be empty")
        
        try:
            json_str = json.dumps(save_data, ensure_ascii=False)
        except MemoryError:
            logger.error("Insufficient memory to serialize JSON data")
            raise ValueError("Insufficient memory to save data. Please close other programs and try again.")
        except (TypeError, ValueError) as e:
            logger.error(f"JSON serialization failed: {e}")
            raise ValueError(f"Data cannot be serialized to JSON: {e}")
        
        encoded_content = urllib.parse.quote(json_str)
        
        # 检查磁盘空间
        self._check_disk_space(tyrano_path.parent, len(encoded_content.encode('utf-8')))
        
        try:
            tyrano_path.parent.mkdir(parents=True, exist_ok=True)
            with tyrano_path.open('w', encoding='utf-8') as f:
                f.write(encoded_content)
        except PermissionError:
            logger.error(f"Permission denied writing file: {tyrano_path}")
            raise
        except OSError as e:
            if self._is_disk_space_error(e):
                logger.error(f"Insufficient disk space: {tyrano_path}")
                raise OSError("Insufficient disk space. Please free up disk space and try again.")
            logger.error(f"Failed to write file: {tyrano_path}, error: {e}")
            raise
    
    def load_json_file(self, json_path: Path) -> Dict[str, Any]:
        """
        加载JSON文件
        
        Args:
            json_path: JSON文件路径
            
        Returns:
            解析后的JSON数据字典
            
        Raises:
            FileNotFoundError: 文件不存在
            PermissionError: 无权限读取文件
            OSError: 文件读取失败
            json.JSONDecodeError: JSON解析失败
        """
        if not json_path.exists():
            raise FileNotFoundError(f"文件不存在: {json_path}")
        
        if not json_path.is_file():
            raise ValueError(f"路径不是文件: {json_path}")
        
        try:
            with json_path.open('r', encoding='utf-8') as f:
                content = json.load(f)
        except MemoryError:
            logger.error(f"Insufficient memory to read file: {json_path}")
            raise ValueError("Insufficient memory to read file. Please close other programs and try again.")
        except PermissionError:
            logger.error(f"Permission denied reading file: {json_path}")
            raise
        except OSError as e:
            logger.error(f"Failed to read file: {json_path}, error: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {json_path}, error: {e}")
            raise
        
        if not isinstance(content, dict):
            raise ValueError(f"JSON file content must be a dict, got: {type(content)}")
        
        return content
    
    def save_json_file(self, file_path: Path, save_data: Dict[str, Any]) -> None:
        """
        保存JSON文件
        
        Args:
            file_path: 保存文件路径
            save_data: 要保存的JSON数据字典
            
        Raises:
            PermissionError: 无权限写入文件
            OSError: 文件写入失败
            ValueError: 数据为空或无效
        """
        if not save_data:
            raise ValueError("Save data cannot be empty")
        
        # 估算所需磁盘空间
        estimated_size = self._estimate_json_file_size(save_data)
        self._check_disk_space(file_path.parent, estimated_size)
        
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with file_path.open('w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
        except MemoryError:
            logger.error("Insufficient memory to serialize JSON data")
            raise ValueError("Insufficient memory to save data. Please close other programs and try again.")
        except PermissionError:
            logger.error(f"Permission denied writing file: {file_path}")
            raise
        except OSError as e:
            if self._is_disk_space_error(e):
                logger.error(f"Insufficient disk space: {file_path}")
                raise OSError("Insufficient disk space. Please free up disk space and try again.")
            logger.error(f"Failed to write file: {file_path}, error: {e}")
            raise
        except (TypeError, ValueError) as e:
            logger.error(f"JSON serialization failed: {e}")
            raise ValueError(f"Data cannot be serialized to JSON: {e}")
    
    def compute_json_crc32(self, save_data: Dict[str, Any]) -> int:
        """
        计算JSON数据的CRC32值
        
        Args:
            save_data: JSON数据字典
            
        Returns:
            CRC32值（32位无符号整数）
            
        Raises:
            ValueError: 数据无法序列化
        """
        if not save_data:
            raise ValueError("数据不能为空")
        
        try:
            json_str = json.dumps(save_data, ensure_ascii=False, sort_keys=True)
        except MemoryError:
            logger.error("Insufficient memory to serialize JSON data")
            raise ValueError("Insufficient memory to calculate CRC32. Please close other programs and try again.")
        except (TypeError, ValueError) as e:
            logger.error(f"JSON serialization failed: {e}")
            raise ValueError(f"Data cannot be serialized to JSON: {e}")
        
        try:
            json_bytes = json_str.encode('utf-8')
        except MemoryError:
            logger.error("Insufficient memory to encode JSON data")
            raise ValueError("Insufficient memory to calculate CRC32. Please close other programs and try again.")
        except UnicodeEncodeError as e:
            logger.error(f"UTF-8 encoding failed: {e}")
            raise ValueError(f"Data cannot be encoded to UTF-8: {e}")
        
        return zlib.crc32(json_bytes) & _CRC32_MASK
    
    def compute_existing_file_crc32(
        self,
        tyrano_path: Path
    ) -> Optional[int]:
        """
        计算现有tyrano文件的CRC32值
        
        Args:
            tyrano_path: tyrano保存文件路径
            
        Returns:
            CRC32值，如果文件不存在或读取失败则返回None
        """
        if not tyrano_path.exists() or not tyrano_path.is_file():
            return None
        
        try:
            with tyrano_path.open('r', encoding='utf-8') as f:
                encoded_content = f.read().strip()
            
            if not encoded_content:
                logger.warning(f"File is empty: {tyrano_path}")
                return None
            
            unquoted_content = urllib.parse.unquote(encoded_content)
            existing_data = json.loads(unquoted_content)
            
            if not isinstance(existing_data, dict):
                logger.warning(f"File content is not a dict: {tyrano_path}")
                return None
            
            return self.compute_json_crc32(existing_data)
        except (FileNotFoundError, PermissionError):
            logger.warning(f"Cannot access file: {tyrano_path}")
            return None
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Error parsing existing file {tyrano_path}: {e}")
            return None
        except OSError as e:
            logger.warning(f"Error reading existing file {tyrano_path}: {e}")
            return None
        except ValueError as e:
            logger.warning(f"Error calculating CRC32: {e}")
            return None
    
    def calculate_crc32(
        self,
        new_save_data: Dict[str, Any],
        tyrano_path: Path
    ) -> Tuple[int, Optional[int]]:
        """
        计算新数据和现有文件的CRC32值
        
        Args:
            new_save_data: 新的JSON数据字典
            tyrano_path: tyrano保存文件路径
            
        Returns:
            (新数据的CRC32值, 现有文件的CRC32值)
            如果现有文件不存在，第二个值为None
            
        Raises:
            ValueError: 新数据无效或无法计算CRC32
        """
        if not new_save_data:
            raise ValueError("New data cannot be empty")
        
        new_crc32 = self.compute_json_crc32(new_save_data)
        existing_crc32 = self.compute_existing_file_crc32(tyrano_path)
        return (new_crc32, existing_crc32)
    
    def _log_large_file_if_needed(self, file_path: Path) -> None:
        """记录大文件信息日志（如果文件超过警告阈值）
        
        Args:
            file_path: 文件路径
        """
        try:
            file_size = file_path.stat().st_size
            file_size_mb = file_size / _BYTES_PER_MB
            if file_size_mb > (OthersTabConfig.LARGE_FILE_WARNING_BYTES / _BYTES_PER_MB):
                logger.info(
                    f"Large file detected: {file_path.name} ({file_size_mb:.2f}MB), "
                    f"processing may take longer"
                )
        except OSError:
            # Cannot get file size, continue silently
            pass
    
    def _check_disk_space(self, directory: Path, required_size: int) -> None:
        """检查磁盘可用空间
        
        Args:
            directory: 目录路径
            required_size: 需要的空间大小（字节）
            
        Raises:
            OSError: 如果磁盘空间不足
        """
        try:
            required_with_buffer = int(required_size * OthersTabConfig.DISK_SPACE_BUFFER_RATIO)
            disk_usage = shutil.disk_usage(directory)
            if disk_usage.free < required_with_buffer:
                required_mb = required_with_buffer / _BYTES_PER_MB
                available_mb = disk_usage.free / _BYTES_PER_MB
                error_msg = (
                    f"Insufficient disk space. Required: ~{required_mb:.2f}MB, "
                    f"Available: {available_mb:.2f}MB"
                )
                logger.error(error_msg)
                raise OSError(error_msg)
        except OSError:
            # Cannot check disk space (e.g., network path), continue silently
            pass
        except Exception as e:
            logger.debug(f"Disk space check failed: {e}, continuing")
    
    def _estimate_json_file_size(self, save_data: Dict[str, Any]) -> int:
        """估算JSON文件序列化后的大小
        
        Args:
            save_data: 要保存的数据字典
            
        Returns:
            估算的文件大小（字节）
        """
        # 使用字符串表示估算大小，然后乘以估算系数
        estimated_size = len(str(save_data).encode('utf-8'))
        return int(estimated_size * OthersTabConfig.JSON_SIZE_ESTIMATE_RATIO)
    
    def _is_disk_space_error(self, error: OSError) -> bool:
        """检查OSError是否是磁盘空间不足错误
        
        Args:
            error: OSError异常对象
            
        Returns:
            是否是磁盘空间不足错误
        """
        error_str = str(error).lower()
        return "no space left" in error_str or "磁盘空间不足" in error_str

