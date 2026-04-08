"""
备份创建服务

负责创建备份文件和估算压缩大小
"""
import logging
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Tuple

from src.constants import VERSION
from src.modules.backup.models import (
    BACKUP_INFO_FILENAME,
    COMPRESSION_LEVEL,
    DEFAULT_COMPRESSION_RATIO,
    SAMPLE_RATIO,
)

logger = logging.getLogger(__name__)


class BackupCreator:
    """备份创建器"""
    
    @staticmethod
    def estimate_compressed_size(storage_dir: Path) -> Optional[int]:
        """
        估算压缩后的大小
        
        Args:
            storage_dir: _storage文件夹路径
            
        Returns:
            估算的大小（字节），失败返回None
        """
        if not storage_dir.exists():
            return None
        
        try:
            file_list = []
            total_size = 0
            
            for file_path in storage_dir.rglob('*'):
                if file_path.is_file():
                    try:
                        file_size = file_path.stat().st_size
                        file_list.append((file_path, file_size))
                        total_size += file_size
                    except (OSError, PermissionError) as e:
                        logger.warning(f"无法读取文件大小: {file_path}, 错误: {e}")
                        continue
            
            if not file_list:
                return 0
            
            sample_count = max(1, int(len(file_list) * SAMPLE_RATIO))
            sample_files = file_list[:sample_count]
            sample_total_size = sum(size for _, size in sample_files)
            
            if sample_total_size == 0:
                return int(total_size * DEFAULT_COMPRESSION_RATIO)
            
            compressed_sample_size = BackupCreator._test_compression_ratio(
                storage_dir, sample_files
            )
            
            if compressed_sample_size is not None and compressed_sample_size > 0:
                compression_ratio = compressed_sample_size / sample_total_size
                compression_ratio = max(0.1, min(1.0, compression_ratio))
            else:
                compression_ratio = DEFAULT_COMPRESSION_RATIO
            
            estimated_size = int(total_size * compression_ratio)
            return estimated_size
            
        except Exception as e:
            logger.error(f"估算压缩大小失败: {e}", exc_info=True)
            return None
    
    @staticmethod
    def _test_compression_ratio(
        storage_dir: Path,
        sample_files: list[Tuple[Path, int]]
    ) -> Optional[int]:
        """
        测试压缩比
        
        Args:
            storage_dir: 存储目录
            sample_files: 采样文件列表
            
        Returns:
            压缩后的大小，失败返回None
        """
        temp_zip_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
                temp_zip_path = temp_file.name
            
            with zipfile.ZipFile(
                temp_zip_path,
                'w',
                zipfile.ZIP_DEFLATED,
                compresslevel=COMPRESSION_LEVEL
            ) as test_zip:
                for file_path, _ in sample_files:
                    try:
                        rel_path = file_path.relative_to(storage_dir)
                        test_zip.write(file_path, rel_path)
                    except (OSError, ValueError) as e:
                        logger.warning(f"无法压缩测试文件: {file_path}, 错误: {e}")
                        continue
            
            if Path(temp_zip_path).exists():
                compressed_size = Path(temp_zip_path).stat().st_size
                return compressed_size
            return None
            
        except Exception as e:
            logger.error(f"压缩测试失败: {e}", exc_info=True)
            return None
        finally:
            if temp_zip_path and Path(temp_zip_path).exists():
                try:
                    Path(temp_zip_path).unlink()
                except OSError:
                    pass
    
    @staticmethod
    def create_backup(
        storage_dir: Path,
        backup_dir: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Optional[Tuple[Path, int, Path]]:
        """
        创建备份
        
        Args:
            storage_dir: _storage文件夹路径
            backup_dir: 备份目录路径
            progress_callback: 进度回调函数，接收 (current, total) 参数
            
        Returns:
            (备份文件路径, 实际大小, 绝对路径) 或 None（如果失败）
        """
        if not storage_dir.exists():
            logger.error(f"存储目录不存在: {storage_dir}")
            return None
        
        if not backup_dir.exists():
            try:
                backup_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.error(f"无法创建备份目录: {backup_dir}, 错误: {e}")
                return None
        
        try:
            timestamp = datetime.now()
            filename = f"DC_storage_backup_{timestamp.strftime('%Y%m%d_%H%M%S')}.zip"
            backup_path = backup_dir / filename
            
            all_files = [
                file_path
                for file_path in storage_dir.rglob('*')
                if file_path.is_file()
            ]
            
            total_files = len(all_files) + 1
            
            with tempfile.TemporaryDirectory() as temp_dir:
                info_file_path = Path(temp_dir) / BACKUP_INFO_FILENAME
                
                timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                info_file_path.write_text(
                    f"{timestamp_str}\n"
                    f"This backup .zip was created using "
                    f"https://github.com/Hxueit/Devil-Connection-Sav-Manager/\n"
                    f"ver:{VERSION}\n",
                    encoding='utf-8'
                )
                
                current = 0
                with zipfile.ZipFile(
                    backup_path,
                    'w',
                    zipfile.ZIP_DEFLATED,
                    compresslevel=COMPRESSION_LEVEL
                ) as zipf:
                    zipf.write(info_file_path, BACKUP_INFO_FILENAME)
                    current += 1
                    if progress_callback:
                        progress_callback(current, total_files)
                    
                    for file_path in all_files:
                        try:
                            rel_path = file_path.relative_to(storage_dir)
                            zipf.write(file_path, rel_path)
                            current += 1
                            if progress_callback:
                                progress_callback(current, total_files)
                        except (OSError, ValueError) as e:
                            logger.warning(f"无法添加文件到备份: {file_path}, 错误: {e}")
                            continue
                
                actual_size = backup_path.stat().st_size
                abs_path = backup_path.resolve()
                
                return (backup_path, actual_size, abs_path)
                
        except Exception as e:
            logger.error(f"创建备份失败: {e}", exc_info=True)
            return None

