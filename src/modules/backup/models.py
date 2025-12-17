"""
备份模块的数据模型和常量

定义备份相关的数据结构和配置常量
"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


BACKUP_DIR_NAME = "dcsm_backups"
BACKUP_INFO_FILENAME = "dcsmINFO.txt"
REQUIRED_SAVE_FILES = [
    'DevilConnection_sf.sav',
    'DevilConnection_tyrano_data.sav'
]
DEFAULT_COMPRESSION_RATIO = 0.7
COMPRESSION_LEVEL = 7
SAMPLE_RATIO = 0.1


@dataclass
class BackupInfo:
    """备份文件信息"""
    zip_path: Path
    timestamp: Optional[datetime]
    has_info: bool
    file_size: int
    
    def __post_init__(self):
        """确保zip_path是Path对象"""
        if isinstance(self.zip_path, str):
            self.zip_path = Path(self.zip_path)

