"""运行时修改工具函数

提供端口检测、路径处理等工具函数。
"""
import socket
import logging
import subprocess
import platform
from pathlib import Path
from typing import Optional, Tuple

from src.modules.runtime_modify.config import RuntimeModifyConfig

logger = logging.getLogger(__name__)

# 本地回环地址
_LOCALHOST = "127.0.0.1"


def check_port_available(port: int) -> bool:
    """检测端口是否可用（未被占用）
    
    Args:
        port: 要检测的端口号
        
    Returns:
        如果端口可用（未被占用）返回True，否则返回False
    """
    if not isinstance(port, int):
        return False
    
    if not (RuntimeModifyConfig.MIN_PORT <= port <= RuntimeModifyConfig.MAX_PORT):
        return False
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(RuntimeModifyConfig.PORT_CHECK_TIMEOUT)
            # connect_ex返回0表示连接成功（端口被占用），非0表示连接失败（端口可用）
            connection_result = sock.connect_ex((_LOCALHOST, port))
            return connection_result != 0
    except OSError as e:
        logger.debug(f"Port check error: {e}")
        return False


def get_game_exe_path(storage_dir: Optional[str]) -> Optional[Path]:
    """从storage_dir获取游戏可执行文件路径
    
    游戏路径为storage_dir的上层目录（不含_storage）下的DevilConnection.exe
    
    Args:
        storage_dir: _storage目录路径
        
    Returns:
        游戏可执行文件路径，如果路径无效则返回None
    """
    if not storage_dir:
        return None
    
    try:
        storage_path = Path(storage_dir)
        if not storage_path.exists():
            logger.debug(f"Storage directory does not exist: {storage_path}")
            return None
        
        if not storage_path.is_dir():
            logger.debug(f"Storage path is not a directory: {storage_path}")
            return None
        
        parent_dir = storage_path.parent
        game_exe_path = parent_dir / RuntimeModifyConfig.GAME_EXE_NAME
        
        if not game_exe_path.exists():
            logger.debug(f"Game executable not found: {game_exe_path}")
            return None
        
        if not game_exe_path.is_file():
            logger.debug(f"Game path is not a file: {game_exe_path}")
            return None
        
        return game_exe_path
        
    except (OSError, ValueError) as e:
        logger.debug(f"Error getting game path: {e}")
        return None


def validate_port(port: int) -> Tuple[bool, Optional[str]]:
    """验证端口号是否有效
    
    Args:
        port: 要验证的端口号
        
    Returns:
        (是否有效, 错误信息)
    """
    if not isinstance(port, int):
        return False, "Port must be an integer"
    
    if port < RuntimeModifyConfig.MIN_PORT:
        return (
            False,
            f"Port must be at least {RuntimeModifyConfig.MIN_PORT}"
        )
    
    if port > RuntimeModifyConfig.MAX_PORT:
        return (
            False,
            f"Port must be at most {RuntimeModifyConfig.MAX_PORT}"
        )
    
    return True, None


def is_game_running_by_path(exe_path: Path) -> bool:
    """通过exe路径检测游戏进程是否在运行
    
    使用PowerShell的Get-Process命令获取进程路径，与已知路径进行比较。
    无需额外依赖。
    
    Args:
        exe_path: 游戏可执行文件的完整路径
        
    Returns:
        如果找到匹配的进程返回True，否则返回False
    """
    if not exe_path or not isinstance(exe_path, Path):
        return False
    
    # 只在Windows上支持
    if platform.system() != "Windows":
        logger.debug("Process detection by path only supported on Windows")
        return False
    
    try:
        # 规范化路径（转换为绝对路径，统一大小写）
        normalized_target = str(exe_path.resolve()).lower()
        exe_name = exe_path.stem  # 不带扩展名的进程名
        
        # 使用PowerShell获取匹配进程的路径
        # 这个命令更可靠，即使没有匹配进程也不会返回错误
        ps_cmd = (
            f"Get-Process -Name '{exe_name}' -ErrorAction SilentlyContinue | "
            f"Select-Object -ExpandProperty Path"
        )
        
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_cmd],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        
        # PowerShell命令即使没有匹配进程也返回0
        # 解析输出，查找匹配的路径
        for line in result.stdout.splitlines():
            process_path = line.strip()
            if process_path:
                try:
                    # 规范化并比较路径
                    normalized_process = str(Path(process_path).resolve()).lower()
                    if normalized_process == normalized_target:
                        logger.debug(f"Found matching process: {process_path}")
                        return True
                except (OSError, ValueError):
                    # 路径无效，跳过
                    continue
        
        return False
        
    except subprocess.TimeoutExpired:
        logger.debug("PowerShell command timeout")
        return False
    except FileNotFoundError:
        logger.debug("PowerShell not found")
        return False
    except Exception as e:
        logger.debug(f"Error checking process by path: {e}")
        return False
