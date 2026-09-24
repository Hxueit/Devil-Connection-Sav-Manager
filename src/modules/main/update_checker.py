"""更新检查服务模块

负责检查应用程序更新并显示更新提示。
"""
import json
import logging
import urllib.request
import urllib.error
import threading
from typing import Optional, Callable

from src.constants import VERSION

logger = logging.getLogger(__name__)


class UpdateChecker:
    """更新检查器类"""
    
    GITHUB_API_URL = "https://api.github.com/repos/Hxueit/Devil-Connection-Sav-Manager/releases/latest"
    REQUEST_TIMEOUT = 10
    USER_AGENT = 'Devil-Connection-Sav-Manager'
    
    def __init__(self, current_version: str = VERSION):
        """初始化更新检查器
        
        Args:
            current_version: 当前版本号
        """
        self.current_version = current_version
        self.latest_version: Optional[str] = None
        self.latest_release_url: Optional[str] = None
    
    def check_for_updates_async(self, callback: Optional[Callable[[bool, Optional[str], Optional[str]], None]] = None) -> None:
        """异步检查更新
        
        Args:
            callback: 回调函数，参数为 (has_update, latest_version, release_url)
        """
        def check_thread():
            try:
                has_update, latest_version, release_url = self._check_updates()
                if callback:
                    callback(has_update, latest_version, release_url)
            except Exception as e:
                logger.error(f"Error checking for updates: {e}", exc_info=True)
                if callback:
                    callback(False, None, None)
        
        threading.Thread(target=check_thread, daemon=True).start()
    
    def _check_updates(self) -> tuple[bool, Optional[str], Optional[str]]:
        """检查更新
        
        Returns:
            (是否有更新, 最新版本号, 发布页面URL)
        """
        try:
            req = urllib.request.Request(self.GITHUB_API_URL)
            req.add_header('User-Agent', self.USER_AGENT)
            
            with urllib.request.urlopen(req, timeout=self.REQUEST_TIMEOUT) as response:
                response_data = response.read().decode('utf-8')
                data = json.loads(response_data)
                
                latest_version = data.get('tag_name')
                release_url = data.get('html_url')
                
                if not latest_version:
                    logger.warning("No tag_name in GitHub API response")
                    return False, None, None
                
                if self._compare_versions(self.current_version, latest_version) < 0:
                    self.latest_version = latest_version
                    self.latest_release_url = release_url
                    return True, latest_version, release_url
                else:
                    return False, latest_version, release_url
        except urllib.error.URLError as e:
            logger.debug(f"Network error checking updates: {e}")
            return False, None, None
        except urllib.error.HTTPError as e:
            logger.warning(f"HTTP error checking updates: {e.code} {e.reason}")
            return False, None, None
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON response: {e}")
            return False, None, None
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Error parsing update response: {e}")
            return False, None, None
    
    def _compare_versions(self, v1: str, v2: str) -> int:
        """比较版本号
        
        Args:
            v1: 版本号1
            v2: 版本号2
            
        Returns:
            -1: v1 < v2
            0: v1 == v2
            1: v1 > v2
        """
        v1_clean = v1.lstrip('v')
        v2_clean = v2.lstrip('v')
        
        try:
            parts1 = [int(x) for x in v1_clean.split('.')]
            parts2 = [int(x) for x in v2_clean.split('.')]
        except ValueError:
            return -1 if v1_clean < v2_clean else (1 if v1_clean > v2_clean else 0)
        
        max_len = max(len(parts1), len(parts2))
        parts1.extend([0] * (max_len - len(parts1)))
        parts2.extend([0] * (max_len - len(parts2)))
        
        for p1, p2 in zip(parts1, parts2):
            if p1 < p2:
                return -1
            elif p1 > p2:
                return 1
        return 0

