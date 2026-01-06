"""运行时修改状态管理模块

使用dataclass管理运行时修改的状态
"""

from dataclasses import dataclass
from typing import Optional, Any
from concurrent.futures import ThreadPoolExecutor


@dataclass
class RuntimeModifyState:
    """运行时修改状态数据类"""
    
    # 游戏状态
    is_launching: bool = False
    hook_enabled: bool = False
    cached_ws_url: Optional[str] = None
    cached_game_running: Optional[bool] = None
    
    # 状态检查缓存
    last_game_status_check: float = 0.0
    last_hook_check_time: float = 0.0
    checking_hook: bool = False
    
    # 后台任务
    status_check_job: Optional[str] = None
    executor: Optional[ThreadPoolExecutor] = None
    
    def reset(self) -> None:
        """重置状态"""
        self.is_launching = False
        self.hook_enabled = False
        self.cached_ws_url = None
        self.cached_game_running = None
        self.last_game_status_check = 0.0
        self.last_hook_check_time = 0.0
        self.checking_hook = False
        self.status_check_job = None

