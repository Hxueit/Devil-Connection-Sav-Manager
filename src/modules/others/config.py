"""其他功能模块配置常量

定义其他功能标签页相关的配置常量和默认值。
"""
from typing import Final


class OthersTabConfig:
    """其他功能标签页配置常量"""
    # 文件相关
    TYRANO_SAV_FILENAME: Final[str] = "DevilConnection_tyrano_data.sav"
    TYRANO_JSON_FILENAME: Final[str] = "DevilConnection_tyrano_data.json"
    JSON_EXTENSION: Final[str] = ".json"
    
    # Toast 默认值
    DEFAULT_TOAST_ENABLED: Final[bool] = False
    DEFAULT_TOAST_IGNORE_RECORD: Final[str] = "record, initialVars"
    
    # UI 配置
    PROGRESS_WINDOW_WIDTH: Final[int] = 400
    PROGRESS_WINDOW_HEIGHT: Final[int] = 120
    PROGRESS_BAR_WIDTH: Final[int] = 300
    IGNORE_VARS_ENTRY_WIDTH: Final[int] = 400
    
    # 线程超时
    CRC32_CALCULATION_TIMEOUT_SECONDS: Final[int] = 30
    UPDATE_CHECK_TIMEOUT_SECONDS: Final[int] = 10
    POLL_INTERVAL_MS: Final[int] = 50
    
    # GitHub API
    GITHUB_API_BASE_URL: Final[str] = (
        "https://api.github.com/repos/Hxueit/Devil-Connection-Sav-Manager/releases/latest"
    )
    USER_AGENT: Final[str] = "Devil-Connection-Sav-Manager"
    
    # 日期时间格式
    ISO_DATE_TIME_SEPARATOR: Final[str] = 'T'
    DEFAULT_TIME_STR: Final[str] = "00:00:00"
    MIN_DATE_STRING_LENGTH: Final[int] = 10
    
    # 文件大小阈值（用于缓存策略优化，单位：字节）
    # 超过此大小的文件在FileMonitor中只缓存哈希值，不缓存完整内容
    LARGE_FILE_THRESHOLD_BYTES: Final[int] = 20 * 1024 * 1024  # 20MB
    
    # 文件大小警告阈值（单位：字节）
    # 超过此大小的文件在读取时会记录信息日志
    LARGE_FILE_WARNING_BYTES: Final[int] = 50 * 1024 * 1024  # 50MB
    
    # 磁盘空间检查缓冲系数
    DISK_SPACE_BUFFER_RATIO: Final[float] = 1.1  # 10%缓冲
    
    # JSON序列化大小估算系数
    JSON_SIZE_ESTIMATE_RATIO: Final[float] = 2.0

