"""
备份扫描服务

负责扫描备份目录和验证备份文件
"""
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from src.modules.backup.models import BackupInfo, BACKUP_INFO_FILENAME, REQUIRED_SAVE_FILES

logger = logging.getLogger(__name__)


class BackupScanner:
    """备份扫描器"""
    
    @staticmethod
    def scan_backups(backup_dir: Path) -> List[BackupInfo]:
        """
        扫描备份目录，返回备份列表
        
        Args:
            backup_dir: 备份目录路径
            
        Returns:
            备份列表，按时间戳排序（有INFO的在前，按时间倒序；无INFO的在后）
        """
        if not backup_dir.exists():
            return []
        
        backups = []
        
        try:
            for zip_file in backup_dir.glob('*.zip'):
                if not zip_file.is_file():
                    continue
                
                file_size = zip_file.stat().st_size
                timestamp, has_info = BackupScanner._extract_backup_info(zip_file)
                
                if timestamp is None and not has_info:
                    logger.warning(f"无法读取备份文件信息: {zip_file}")
                    file_size = 0
                
                backups.append(BackupInfo(
                    zip_path=zip_file,
                    timestamp=timestamp,
                    has_info=has_info,
                    file_size=file_size
                ))
            
            backups_with_info = [
                backup for backup in backups
                if backup.has_info and backup.timestamp is not None
            ]
            backups_without_info = [
                backup for backup in backups
                if not backup.has_info or backup.timestamp is None
            ]
            
            backups_with_info.sort(key=lambda x: x.timestamp, reverse=True)
            
            return backups_with_info + backups_without_info
            
        except Exception as e:
            logger.error(f"扫描备份目录失败: {backup_dir}, 错误: {e}", exc_info=True)
            return []
    
    @staticmethod
    def _extract_backup_info(zip_path: Path) -> Tuple[Optional[datetime], bool]:
        """
        从备份文件中提取信息
        
        Args:
            zip_path: 备份zip文件路径
            
        Returns:
            (时间戳, 是否有INFO文件)
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                if BACKUP_INFO_FILENAME not in zipf.namelist():
                    return None, False
                
                try:
                    with zipf.open(BACKUP_INFO_FILENAME) as info_file:
                        first_line = info_file.readline().decode('utf-8').strip()
                        try:
                            timestamp = datetime.strptime(first_line, '%Y-%m-%d %H:%M:%S')
                            return timestamp, True
                        except ValueError:
                            return None, True
                except (zipfile.BadZipFile, UnicodeDecodeError) as e:
                    logger.warning(f"无法读取INFO文件: {zip_path}, 错误: {e}")
                    return None, True
                    
        except (zipfile.BadZipFile, OSError) as e:
            logger.warning(f"无法打开备份文件: {zip_path}, 错误: {e}")
            return None, False
    
    @staticmethod
    def check_required_files(zip_path: Path) -> List[str]:
        """
        检查zip文件中是否包含必需文件
        
        Args:
            zip_path: zip文件路径
            
        Returns:
            缺失文件列表，如果都存在则返回空列表
        """
        if not zip_path.exists():
            return REQUIRED_SAVE_FILES.copy()
        
        missing_files = []
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                file_list = set(zipf.namelist())
                for required_file in REQUIRED_SAVE_FILES:
                    if required_file not in file_list:
                        missing_files.append(required_file)
        except (zipfile.BadZipFile, OSError) as e:
            logger.error(f"无法打开zip文件: {zip_path}, 错误: {e}")
            return REQUIRED_SAVE_FILES.copy()
        
        return missing_files

