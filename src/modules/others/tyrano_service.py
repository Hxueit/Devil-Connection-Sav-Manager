"""Tyrano数据处理服务模块

负责Tyrano保存文件的编码/解码、CRC32计算等业务逻辑。
不包含UI相关代码，可独立测试和复用。
"""
import json
import logging
import urllib.parse
import zlib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Final

logger = logging.getLogger(__name__)

# 常量
_DEFAULT_TIMEOUT_SECONDS: Final[int] = 30
_CRC32_MASK: Final[int] = 0xffffffff


class TyranoService:
    """Tyrano数据处理服务"""
    
    def __init__(self, calculation_timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS) -> None:
        """
        初始化Tyrano服务
        
        Args:
            calculation_timeout_seconds: CRC32计算超时时间（秒）
        """
        if calculation_timeout_seconds <= 0:
            raise ValueError("超时时间必须大于0")
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
        """
        if not tyrano_path.exists():
            raise FileNotFoundError(f"文件不存在: {tyrano_path}")
        
        if not tyrano_path.is_file():
            raise ValueError(f"路径不是文件: {tyrano_path}")
        
        try:
            with tyrano_path.open('r', encoding='utf-8') as f:
                encoded_content = f.read().strip()
        except PermissionError:
            logger.error(f"无权限读取文件: {tyrano_path}")
            raise
        except OSError as e:
            logger.error(f"读取文件失败: {tyrano_path}, 错误: {e}")
            raise
        
        if not encoded_content:
            raise ValueError(f"文件为空: {tyrano_path}")
        
        try:
            unquoted_content = urllib.parse.unquote(encoded_content)
        except Exception as e:
            logger.error(f"URL解码失败: {e}")
            raise ValueError(f"URL解码失败: {e}")
        
        try:
            return json.loads(unquoted_content)
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
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
            OSError: 文件写入失败
            ValueError: 数据为空或无效
        """
        if not save_data:
            raise ValueError("保存数据不能为空")
        
        try:
            json_str = json.dumps(save_data, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            logger.error(f"JSON序列化失败: {e}")
            raise ValueError(f"数据无法序列化为JSON: {e}")
        
        encoded_content = urllib.parse.quote(json_str)
        
        try:
            tyrano_path.parent.mkdir(parents=True, exist_ok=True)
            with tyrano_path.open('w', encoding='utf-8') as f:
                f.write(encoded_content)
        except PermissionError:
            logger.error(f"无权限写入文件: {tyrano_path}")
            raise
        except OSError as e:
            logger.error(f"写入文件失败: {tyrano_path}, 错误: {e}")
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
        except PermissionError:
            logger.error(f"无权限读取文件: {json_path}")
            raise
        except OSError as e:
            logger.error(f"读取文件失败: {json_path}, 错误: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {json_path}, 错误: {e}")
            raise
        
        if not isinstance(content, dict):
            raise ValueError(f"JSON文件内容必须是字典类型，实际类型: {type(content)}")
        
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
            raise ValueError("保存数据不能为空")
        
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with file_path.open('w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
        except PermissionError:
            logger.error(f"无权限写入文件: {file_path}")
            raise
        except OSError as e:
            logger.error(f"写入文件失败: {file_path}, 错误: {e}")
            raise
        except (TypeError, ValueError) as e:
            logger.error(f"JSON序列化失败: {e}")
            raise ValueError(f"数据无法序列化为JSON: {e}")
    
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
        except (TypeError, ValueError) as e:
            logger.error(f"JSON序列化失败: {e}")
            raise ValueError(f"数据无法序列化为JSON: {e}")
        
        try:
            json_bytes = json_str.encode('utf-8')
        except UnicodeEncodeError as e:
            logger.error(f"UTF-8编码失败: {e}")
            raise ValueError(f"数据无法编码为UTF-8: {e}")
        
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
                logger.warning(f"文件为空: {tyrano_path}")
                return None
            
            unquoted_content = urllib.parse.unquote(encoded_content)
            existing_data = json.loads(unquoted_content)
            
            if not isinstance(existing_data, dict):
                logger.warning(f"文件内容不是字典类型: {tyrano_path}")
                return None
            
            return self.compute_json_crc32(existing_data)
        except (FileNotFoundError, PermissionError):
            logger.warning(f"无法访问文件: {tyrano_path}")
            return None
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"解析现有文件 {tyrano_path} 时出错: {e}")
            return None
        except OSError as e:
            logger.warning(f"读取现有文件 {tyrano_path} 时出错: {e}")
            return None
        except ValueError as e:
            logger.warning(f"计算CRC32时出错: {e}")
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
            raise ValueError("新数据不能为空")
        
        new_crc32 = self.compute_json_crc32(new_save_data)
        existing_crc32 = self.compute_existing_file_crc32(tyrano_path)
        return (new_crc32, existing_crc32)

