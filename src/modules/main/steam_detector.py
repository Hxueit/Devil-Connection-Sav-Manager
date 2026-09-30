"""自动查找 Steam 版游戏的 _storage 文件夹"""
import os
import platform
import re

GAME_APP_ID = "3054820"
GAME_FOLDER_NAME = "でびるコネクショん"
STEAM_REGISTRY_KEYS = [r"SOFTWARE\WOW6432Node\Valve\Steam", r"SOFTWARE\Valve\Steam"]


def get_steam_path() -> str:
    """Windows 上先查注册表，找不到就用各系统的默认安装位置"""
    system = platform.system()
    if system == "Windows":
        import winreg
        for key_path in STEAM_REGISTRY_KEYS:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                    steam_path = winreg.QueryValueEx(key, "InstallPath")[0]
            except OSError:
                continue
            if os.path.exists(steam_path):
                return steam_path
        return r"C:\Program Files (x86)\Steam"
    if system == "Darwin":
        return os.path.expanduser("~/Library/Application Support/Steam")
    return os.path.expanduser("~/.steam/steam")


def _read_text(path: str) -> str:
    """读取 Steam 的配置文件；不存在或读不了时返回空字符串"""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return ""


def get_steam_libraries(steam_path: str) -> list[str]:
    """Steam 主目录 + libraryfolders.vdf 里登记的其他库"""
    libraries = [steam_path] if os.path.exists(steam_path) else []
    content = _read_text(os.path.join(steam_path, "steamapps", "libraryfolders.vdf"))
    for match in re.findall(r'"path"\s+"([^"]+)"', content):
        path = os.path.normpath(match.replace("\\\\", "\\").replace("\\/", "/"))
        if os.path.exists(path) and path not in libraries:
            libraries.append(path)
    return libraries


def find_game_directory(library_path: str) -> str | None:
    """先找默认文件夹名，找不到再看 appmanifest 里的 installdir"""
    common_dir = os.path.join(library_path, "steamapps", "common")
    candidates = [GAME_FOLDER_NAME]
    manifest = _read_text(os.path.join(library_path, "steamapps", f"appmanifest_{GAME_APP_ID}.acf"))
    match = re.search(r'"installdir"\s+"([^"]+)"', manifest)
    if match:
        candidates.append(match.group(1))
    for name in candidates:
        game_dir = os.path.join(common_dir, name)
        if os.path.isdir(game_dir):
            return game_dir
    return None


def auto_detect_storage() -> str | None:
    """返回游戏 _storage 文件夹的绝对路径，找不到时返回 None"""
    steam_path = get_steam_path()
    if not os.path.exists(steam_path):
        return None
    for library in get_steam_libraries(steam_path):
        game_dir = find_game_directory(library)
        if game_dir:
            storage = os.path.join(game_dir, "_storage")
            if os.path.isdir(storage):
                return os.path.abspath(storage)
    return None
