"""
备份/还原管理器

提供统一的备份和还原功能接口，组合各个服务模块
"""
import logging
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from src.modules.backup.backup_creator import BackupCreator
from src.modules.backup.backup_manager import BackupManager
from src.modules.backup.backup_scanner import BackupScanner
from src.modules.backup.models import BACKUP_DIR_NAME, BACKUP_INFO_FILENAME
from src.modules.backup.utils import format_size

logger = logging.getLogger(__name__)


class BackupRestore:
    """
    备份/还原管理器
    
    提供备份创建、还原、扫描、删除和重命名等功能
    """
    
    def __init__(self, storage_dir: str | Path):
        """
        初始化备份/还原管理器
        
        Args:
            storage_dir: _storage文件夹的路径
        """
        self.storage_dir = Path(storage_dir) if storage_dir else None
    
    def get_backup_dir(self) -> Optional[Path]:
        """
        获取备份目录路径（不自动创建）
        
        Returns:
            备份目录的绝对路径，如果storage_dir无效则返回None
        """
        if not self.storage_dir:
            return None
        
        parent_dir = self.storage_dir.parent
        backup_dir = parent_dir / BACKUP_DIR_NAME
        
        return backup_dir.resolve()
    
    def format_size(self, size_bytes: int) -> str:
        """
        格式化文件大小为可读格式
        
        Args:
            size_bytes: 文件大小（字节）
            
        Returns:
            格式化后的字符串（如 "1.5 MB"）
        """
        return format_size(size_bytes)
    
    def estimate_compressed_size(self, storage_dir: str | Path) -> Optional[int]:
        """
        估算压缩后的大小
        
        Args:
            storage_dir: _storage文件夹路径
            
        Returns:
            估算的大小（字节），失败返回None
        """
        storage_path = Path(storage_dir) if isinstance(storage_dir, str) else storage_dir
        return BackupCreator.estimate_compressed_size(storage_path)
    
    def create_backup(
        self,
        storage_dir: str | Path,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Optional[Tuple[str, int, str]]:
        """
        创建备份
        
        Args:
            storage_dir: _storage文件夹路径
            progress_callback: 进度回调函数，接收 (current, total) 参数
            
        Returns:
            (备份文件路径, 实际大小, 绝对路径) 或 None（如果失败）
            路径以字符串形式返回以保持向后兼容
        """
        storage_path = Path(storage_dir) if isinstance(storage_dir, str) else storage_dir
        backup_dir = self.get_backup_dir()
        
        if not backup_dir:
            logger.error("无法获取备份目录")
            return None
        
        result = BackupCreator.create_backup(storage_path, backup_dir, progress_callback)
        
        if result is None:
            return None
        
        backup_path, actual_size, abs_path = result
        return (str(backup_path), actual_size, str(abs_path))
    
    def scan_backups(self, backup_dir: str | Path) -> List[Tuple[str, Optional[datetime], bool, int]]:
        """
        扫描备份目录，返回备份列表
        
        Args:
            backup_dir: 备份目录路径
            
        Returns:
            备份列表：[(zip_path, timestamp, has_info, file_size), ...]
            按时间戳排序（有INFO的在前，按时间倒序；无INFO的在后）
            路径以字符串形式返回以保持向后兼容
        """
        backup_path = Path(backup_dir) if isinstance(backup_dir, str) else backup_dir
        backups = BackupScanner.scan_backups(backup_path)
        
        return [
            (str(backup.zip_path), backup.timestamp, backup.has_info, backup.file_size)
            for backup in backups
        ]
    
    def check_required_files(self, zip_path: str | Path) -> List[str]:
        """
        检查zip文件中是否包含必需文件
        
        Args:
            zip_path: zip文件路径
            
        Returns:
            缺失文件列表，如果都存在则返回空列表
        """
        zip_file_path = Path(zip_path) if isinstance(zip_path, str) else zip_path
        return BackupScanner.check_required_files(zip_file_path)
    
    def restore_backup(self, zip_path: str | Path, storage_dir: str | Path) -> bool:
        """
        还原备份
        
        Args:
            zip_path: 备份zip文件路径
            storage_dir: _storage文件夹路径
            
        Returns:
            成功返回True，失败返回False
        """
        zip_file_path = Path(zip_path) if isinstance(zip_path, str) else zip_path
        storage_path = Path(storage_dir) if isinstance(storage_dir, str) else storage_dir
        
        return BackupRestore._restore_backup(zip_file_path, storage_path)
    
    @staticmethod
    def _restore_backup(zip_path: Path, storage_dir: Path) -> bool:
        """
        还原备份的核心实现
        
        Args:
            zip_path: 备份zip文件路径
            storage_dir: _storage文件夹路径
            
        Returns:
            成功返回True，失败返回False
        """
        if not zip_path.exists():
            logger.error(f"备份文件不存在: {zip_path}")
            return False
        
        try:
            if storage_dir.exists():
                BackupRestore._clear_directory(storage_dir)
            
            storage_dir.mkdir(parents=True, exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                for member in zipf.namelist():
                    if member == BACKUP_INFO_FILENAME:
                        continue
                    
                    try:
                        zipf.extract(member, storage_dir)
                    except (zipfile.BadZipFile, OSError) as e:
                        logger.warning(f"无法解压文件: {member}, 错误: {e}")
                        continue
            
            return True
            
        except Exception as e:
            logger.error(f"还原备份失败: {zip_path}, 错误: {e}", exc_info=True)
            return False
    
    @staticmethod
    def _clear_directory(directory: Path) -> None:
        """
        清空目录内容
        
        Args:
            directory: 要清空的目录路径
        """
        try:
            for file_path in directory.rglob('*'):
                if file_path.is_file():
                    try:
                        file_path.unlink()
                    except (OSError, PermissionError) as e:
                        logger.warning(f"无法删除文件: {file_path}, 错误: {e}")
            
            dirs_to_remove = [
                d for d in directory.rglob('*')
                if d.is_dir()
            ]
            dirs_to_remove.sort(key=lambda p: len(p.parts), reverse=True)
            
            for dir_path in dirs_to_remove:
                try:
                    dir_path.rmdir()
                except (OSError, PermissionError) as e:
                    logger.warning(f"无法删除目录: {dir_path}, 错误: {e}")
            
            if any(directory.iterdir()):
                shutil.rmtree(directory)
                directory.mkdir(parents=True, exist_ok=True)
                
        except Exception as e:
            logger.error(f"清空目录失败: {directory}, 错误: {e}", exc_info=True)
            raise
    
    def delete_backup(self, zip_path: str | Path) -> bool:
        """
        删除备份文件，如果备份目录为空则删除目录
        
        Args:
            zip_path: 备份zip文件路径
            
        Returns:
            成功返回True，失败返回False
        """
        zip_file_path = Path(zip_path) if isinstance(zip_path, str) else zip_path
        return BackupManager.delete_backup(zip_file_path)
    
    def rename_backup(
        self,
        zip_path: str | Path,
        new_filename: str
    ) -> Optional[Tuple[str, str]]:
        """
        重命名备份文件
        
        Args:
            zip_path: 备份zip文件路径
            new_filename: 新的文件名（不包含路径，只包含文件名和扩展名）
            
        Returns:
            (新文件路径, 旧文件名) 如果成功，None 如果失败
            路径以字符串形式返回以保持向后兼容
        """
        zip_file_path = Path(zip_path) if isinstance(zip_path, str) else zip_path
        result = BackupManager.rename_backup(zip_file_path, new_filename)
        
        if result is None:
            return None
        
        new_path, old_filename = result
        return (str(new_path), old_filename)
