"""
备份管理服务

负责删除和重命名备份文件
"""
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class BackupManager:
    """备份管理器"""
    
    @staticmethod
    def delete_backup(zip_path: Path) -> bool:
        """
        删除备份文件，如果备份目录为空则删除目录
        
        Args:
            zip_path: 备份zip文件路径
            
        Returns:
            成功返回True，失败返回False
        """
        if not zip_path.exists():
            logger.warning(f"备份文件不存在: {zip_path}")
            return False
        
        try:
            backup_dir = zip_path.parent
            zip_path.unlink()
            
            if backup_dir.exists():
                remaining_items = list(backup_dir.iterdir())
                if not remaining_items:
                    try:
                        backup_dir.rmdir()
                    except (OSError, PermissionError) as e:
                        logger.debug(f"无法删除空备份目录: {backup_dir}, 错误: {e}")
            
            return True
            
        except (OSError, PermissionError) as e:
            logger.error(f"删除备份失败: {zip_path}, 错误: {e}")
            return False
    
    @staticmethod
    def rename_backup(zip_path: Path, new_filename: str) -> Optional[Tuple[Path, str]]:
        """
        重命名备份文件
        
        Args:
            zip_path: 备份zip文件路径
            new_filename: 新的文件名（不包含路径，只包含文件名和扩展名）
            
        Returns:
            (新文件路径, 旧文件名) 如果成功，None 如果失败
        """
        if not zip_path.exists():
            logger.error(f"备份文件不存在: {zip_path}")
            return None
        
        if not new_filename.endswith('.zip'):
            new_filename = f"{new_filename}.zip"
        
        try:
            backup_dir = zip_path.parent
            old_filename = zip_path.name
            new_path = backup_dir / new_filename
            
            if new_path.exists() and new_path != zip_path:
                logger.warning(f"目标文件已存在: {new_path}")
                return None
            
            zip_path.rename(new_path)
            
            return (new_path, old_filename)
            
        except (OSError, PermissionError) as e:
            logger.error(f"重命名备份失败: {zip_path}, 错误: {e}")
            return None

