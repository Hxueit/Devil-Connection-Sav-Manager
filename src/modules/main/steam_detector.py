"""Steam路径检测服务模块

负责检测Steam安装路径和游戏目录。
"""
import logging
import os
import re
import platform
from typing import Optional, List

logger = logging.getLogger(__name__)

if platform.system() == "Windows":
    try:
        import winreg
    except ImportError:
        winreg = None
else:
    winreg = None


class SteamDetector:
    """Steam路径检测器类"""
    
    STEAM_REGISTRY_KEY_64 = r"SOFTWARE\WOW6432Node\Valve\Steam"
    STEAM_REGISTRY_KEY_32 = r"SOFTWARE\Valve\Steam"
    GAME_APP_ID = "3054820"
    GAME_FOLDER_NAME = "でびるコネクショん"
    STORAGE_FOLDER_NAME = "_storage"
    
    def __init__(self):
        """初始化Steam检测器"""
        pass
    
    def get_steam_path(self) -> Optional[str]:
        """从Windows注册表获取Steam主路径，如果不是Windows则使用默认路径
        
        Returns:
            Steam安装路径
        """
        if platform.system() == "Windows" and winreg:
            steam_path = self._get_steam_path_from_registry()
            if steam_path:
                return steam_path
        
        return self._get_default_steam_path()
    
    def _get_steam_path_from_registry(self) -> Optional[str]:
        """从Windows注册表获取Steam路径"""
        registry_keys = [self.STEAM_REGISTRY_KEY_64, self.STEAM_REGISTRY_KEY_32]
        
        for reg_key in registry_keys:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_key) as key:
                    steam_path = winreg.QueryValueEx(key, "InstallPath")[0]
                    if steam_path and os.path.exists(steam_path):
                        return steam_path
            except (OSError, FileNotFoundError, ValueError) as e:
                logger.debug(f"Registry key {reg_key} not found: {e}")
                continue
        
        return None
    
    def _get_default_steam_path(self) -> str:
        """获取默认Steam路径"""
        system = platform.system()
        if system == "Windows":
            return os.path.expanduser(r"C:\Program Files (x86)\Steam")
        elif system == "Darwin":
            return os.path.expanduser("~/Library/Application Support/Steam")
        else:
            return os.path.expanduser("~/.steam/steam")
    
    def parse_libraryfolders_vdf(self, vdf_path: str) -> List[str]:
        """解析libraryfolders.vdf文件，返回所有Steam库路径列表
        
        Args:
            vdf_path: VDF文件路径
            
        Returns:
            Steam库路径列表
        """
        if not os.path.exists(vdf_path):
            return []
        
        try:
            with open(vdf_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except (IOError, OSError, UnicodeDecodeError) as e:
            logger.warning(f"Failed to read VDF file {vdf_path}: {e}")
            return []
        
        pattern = r'"path"\s+"([^"]+)"'
        matches = re.findall(pattern, content)
        
        library_paths = []
        for match in matches:
            try:
                path = match.replace('\\\\', '\\').replace('\\/', '/')
                path = os.path.normpath(path)
                if os.path.exists(path):
                    library_paths.append(path)
            except (OSError, ValueError) as e:
                logger.debug(f"Invalid library path {match}: {e}")
                continue
        
        return library_paths
    
    def get_steam_libraries(self, steam_path: str) -> List[str]:
        """获取所有Steam库路径
        
        Args:
            steam_path: Steam主路径
            
        Returns:
            Steam库路径列表
        """
        libraries = []
        
        if os.path.exists(steam_path):
            libraries.append(steam_path)
        
        vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
        additional_libraries = self.parse_libraryfolders_vdf(vdf_path)
        
        for lib in additional_libraries:
            if lib not in libraries:
                libraries.append(lib)
        
        return libraries
    
    def parse_appmanifest_acf(self, acf_path: str) -> Optional[str]:
        """解析appmanifest_3054820.acf文件，获取installdir字段
        
        Args:
            acf_path: ACF文件路径
            
        Returns:
            安装目录名称，失败返回None
        """
        if not os.path.exists(acf_path):
            return None
        
        try:
            with open(acf_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except (IOError, OSError, UnicodeDecodeError) as e:
            logger.warning(f"Failed to read ACF file {acf_path}: {e}")
            return None
        
        pattern = r'"installdir"\s+"([^"]+)"'
        match = re.search(pattern, content)
        if match:
            return match.group(1)
        
        return None
    
    def find_game_directory(self, library_path: str) -> Optional[str]:
        """在指定的Steam库中查找游戏目录
        
        Args:
            library_path: Steam库路径
            
        Returns:
            游戏目录路径，失败返回None
        """
        steamapps_common = os.path.join(library_path, "steamapps", "common")
        
        if not os.path.exists(steamapps_common):
            return None
        
        game_folder_path = os.path.join(steamapps_common, self.GAME_FOLDER_NAME)
        
        if os.path.exists(game_folder_path) and os.path.isdir(game_folder_path):
            return game_folder_path
        
        appmanifest_path = os.path.join(library_path, "steamapps", f"appmanifest_{self.GAME_APP_ID}.acf")
        installdir = self.parse_appmanifest_acf(appmanifest_path)
        
        if installdir:
            game_folder_path = os.path.join(steamapps_common, installdir)
            if os.path.exists(game_folder_path) and os.path.isdir(game_folder_path):
                return game_folder_path
        
        return None
    
    def auto_detect_storage(self) -> Optional[str]:
        """自动检测Steam游戏目录的_storage文件夹
        
        Returns:
            _storage文件夹路径，失败返回None
        """
        steam_path = self.get_steam_path()
        
        if not steam_path or not os.path.exists(steam_path):
            return None
        
        libraries = self.get_steam_libraries(steam_path)
        
        for library in libraries:
            game_dir = self.find_game_directory(library)
            if game_dir:
                storage_path = os.path.join(game_dir, self.STORAGE_FOLDER_NAME)
                if os.path.exists(storage_path) and os.path.isdir(storage_path):
                    return os.path.abspath(storage_path)
        
        return None

