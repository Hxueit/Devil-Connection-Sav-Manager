"""运行时修改模块配置常量

定义运行时修改功能相关的配置常量和默认值。
"""
from typing import Final


class RuntimeModifyConfig:
    """运行时修改功能配置常量"""
    
    # 默认端口
    DEFAULT_PORT: Final[int] = 1145
    
    # 端口范围
    MIN_PORT: Final[int] = 1
    MAX_PORT: Final[int] = 65535
    
    # 超时设置（秒）
    PORT_CHECK_TIMEOUT: Final[float] = 0.1
    CDP_CONNECT_TIMEOUT: Final[float] = 5.0
    GAME_STARTUP_DELAY: Final[float] = 3.0
    CDP_RETRY_DELAY: Final[float] = 1.0
    CDP_MAX_RETRIES: Final[int] = 3
    
    # 游戏可执行文件名
    GAME_EXE_NAME: Final[str] = "DevilConnection.exe"
    
    # CDP相关
    CDP_LIST_URL_TEMPLATE: Final[str] = "http://127.0.0.1:{port}/json/list"
    CDP_TIMEOUT_PARAM: Final[str] = "t"
    
    # 状态检查间隔（毫秒）
    STATUS_CHECK_INTERVAL_MS: Final[int] = 2000
    # 状态检查缓存时间（秒）- 减少重复检查
    STATUS_CACHE_TTL: Final[float] = 1.0
    # 游戏未运行时的检查间隔（毫秒）- 降低频率
    STATUS_CHECK_INTERVAL_IDLE_MS: Final[int] = 5000

