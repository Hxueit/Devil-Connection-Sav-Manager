"""更新检查服务模块

负责检查GitHub发布更新，处理版本比较和发布信息获取。
"""
import json
import logging
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import Optional, Dict, Any, Final, Tuple
from src.modules.others.config import OthersTabConfig
from src.modules.others.utils import format_release_date
from src.utils.ui_utils import (
    askyesno_relative,
    showerror_relative,
    showinfo_relative
)

logger = logging.getLogger(__name__)

# 版本号解析正则表达式
_VERSION_PATTERN: Final[re.Pattern[str]] = re.compile(r'^v?(\d+(?:\.\d+)*)')


class UpdateService:
    """更新检查服务
    
    负责从GitHub API获取最新发布信息，比较版本号，并触发UI回调。
    """
    
    def __init__(self, current_version: str) -> None:
        """
        初始化更新服务
        
        Args:
            current_version: 当前应用版本号
        """
        self.current_version = current_version
    
    def check_for_updates_async(
        self,
        parent: Any,
        translations: Dict[str, Dict[str, str]],
        current_language: str
    ) -> None:
        """
        异步检查更新并在完成后显示结果
        
        Args:
            parent: 父窗口（用于显示对话框）
            translations: 翻译字典
            current_language: 当前语言
        """
        if not parent:
            logger.error("父窗口不能为None")
            return
        
        def check_thread() -> None:
            """在后台线程中检查更新"""
            try:
                release_info = self._fetch_latest_release_info()
                if release_info is None:
                    error_msg = self._t(
                        translations,
                        current_language,
                        "update_check_failed",
                        error="无法获取发布信息"
                    )
                    parent.after(
                        0,
                        lambda: showerror_relative(
                            parent,
                            self._t(translations, current_language, "error"),
                            error_msg
                        )
                    )
                    return
                
                # 提取发布信息，添加边界检查
                latest_version = release_info.get('tag_name', '')
                release_url = release_info.get('html_url', '')
                published_at = release_info.get('published_at', '')
                
                if not latest_version:
                    logger.warning("发布信息中缺少tag_name")
                    error_msg = self._t(
                        translations,
                        current_language,
                        "update_check_failed",
                        error="发布信息格式不正确"
                    )
                    parent.after(
                        0,
                        lambda: showerror_relative(
                            parent,
                            self._t(translations, current_language, "error"),
                            error_msg
                        )
                    )
                    return
                
                release_date = format_release_date(published_at)
                
                version_comparison = self._compare_versions(
                    self.current_version,
                    latest_version
                )
                
                if version_comparison < 0:
                    parent.after(
                        0,
                        lambda: self._show_update_available(
                            parent,
                            translations,
                            current_language,
                            self.current_version,
                            latest_version,
                            release_url
                        )
                    )
                else:
                    parent.after(
                        0,
                        lambda: self._show_no_update(
                            parent,
                            translations,
                            current_language,
                            self.current_version,
                            latest_version,
                            release_date
                        )
                    )
            except urllib.error.URLError as e:
                logger.exception("网络错误，无法检查更新")
                error_msg = self._t(
                    translations,
                    current_language,
                    "update_check_failed",
                    error=f"网络错误: {str(e)}"
                )
                parent.after(
                    0,
                    lambda: showerror_relative(
                        parent,
                        self._t(translations, current_language, "error"),
                        error_msg
                    )
                )
            except Exception as e:
                logger.exception("检查更新时发生未知错误")
                error_msg = self._t(
                    translations,
                    current_language,
                    "update_check_failed",
                    error=str(e)
                )
                parent.after(
                    0,
                    lambda: showerror_relative(
                        parent,
                        self._t(translations, current_language, "error"),
                        error_msg
                    )
                )
        
        update_thread = threading.Thread(target=check_thread, daemon=True)
        update_thread.start()
    
    def _fetch_latest_release_info(self) -> Optional[Dict[str, Any]]:
        """
        从GitHub API获取最新发布信息
        
        Returns:
            发布信息字典，如果获取失败则返回None
            
        Raises:
            urllib.error.URLError: 网络请求失败
            json.JSONDecodeError: JSON解析失败
        """
        if not OthersTabConfig.GITHUB_API_BASE_URL:
            logger.error("GitHub API URL未配置")
            return None
        
        try:
            request = urllib.request.Request(OthersTabConfig.GITHUB_API_BASE_URL)
            request.add_header('User-Agent', OthersTabConfig.USER_AGENT)
            
            with urllib.request.urlopen(
                request,
                timeout=OthersTabConfig.UPDATE_CHECK_TIMEOUT_SECONDS
            ) as response:
                response_code = response.getcode()
                if response_code != 200:
                    logger.warning(f"GitHub API返回非200状态码: {response_code}")
                    return None
                
                response_data = response.read()
                if not response_data:
                    logger.warning("GitHub API返回空响应")
                    return None
                
                try:
                    release_info = json.loads(response_data.decode('utf-8'))
                except UnicodeDecodeError as e:
                    logger.error(f"响应解码失败: {e}")
                    return None
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析失败: {e}")
                    return None
                
                if not isinstance(release_info, dict):
                    logger.warning("发布信息格式不正确，期望字典类型")
                    return None
                
                return release_info
                
        except urllib.error.HTTPError as e:
            logger.warning(f"HTTP错误: {e.code} - {e.reason}")
            return None
        except urllib.error.URLError as e:
            logger.warning(f"网络请求失败: {e.reason}")
            return None
        except TimeoutError:
            logger.warning("请求超时")
            return None
        except Exception as e:
            logger.exception(f"获取发布信息时发生未知错误: {e}")
            return None
    
    def _parse_version_parts(self, version_str: str) -> Tuple[int, ...]:
        """
        解析版本号字符串为数字元组
        
        Args:
            version_str: 版本号字符串（例如: "v1.2.3" 或 "1.2.3"）
            
        Returns:
            版本号数字元组（例如: (1, 2, 3)）
        """
        if not version_str or not isinstance(version_str, str):
            return (0,)
        
        version_str = version_str.strip()
        match = _VERSION_PATTERN.match(version_str)
        
        if not match:
            logger.warning(f"无法解析版本号: {version_str}")
            return (0,)
        
        version_number_str = match.group(1)
        
        try:
            parts = tuple(int(part) for part in version_number_str.split('.'))
            if not parts:
                return (0,)
            return parts
        except ValueError as e:
            logger.warning(f"版本号解析失败: {version_str}, 错误: {e}")
            return (0,)
    
    def _compare_versions(self, version1: str, version2: str) -> int:
        """
        比较版本号
        
        Args:
            version1: 版本号1
            version2: 版本号2
        
        Returns:
            -1: version1 < version2
            0: version1 == version2
            1: version1 > version2
        """
        if not version1 or not version2:
            logger.warning("版本号不能为空")
            return 0
        
        parts1 = self._parse_version_parts(version1)
        parts2 = self._parse_version_parts(version2)
        
        # 对齐版本号长度，较短的用0补齐
        max_length = max(len(parts1), len(parts2))
        normalized_parts1 = parts1 + (0,) * (max_length - len(parts1))
        normalized_parts2 = parts2 + (0,) * (max_length - len(parts2))
        
        # 逐位比较
        for part1, part2 in zip(normalized_parts1, normalized_parts2):
            if part1 < part2:
                return -1
            if part1 > part2:
                return 1
        
        return 0
    
    def _show_no_update(
        self,
        parent: Any,
        translations: Dict[str, Dict[str, str]],
        current_language: str,
        current_version: str,
        latest_version: str,
        release_date: str
    ) -> None:
        """
        显示无更新对话框
        
        Args:
            parent: 父窗口
            translations: 翻译字典
            current_language: 当前语言
            current_version: 当前版本
            latest_version: 最新版本
            release_date: 发布日期
        """
        message_lines = [
            self._t(
                translations,
                current_language,
                "already_latest_version",
                version=current_version
            ),
            f"\n{self._t(translations, current_language, 'latest_version_info')}: {latest_version}"
        ]
        
        if release_date:
            message_lines.append(
                f"{self._t(translations, current_language, 'release_date')}: {release_date}"
            )
        
        message = "\n".join(message_lines)
        showinfo_relative(
            parent,
            self._t(translations, current_language, "no_update"),
            message
        )
    
    def _show_update_available(
        self,
        parent: Any,
        translations: Dict[str, Dict[str, str]],
        current_language: str,
        current_version: str,
        latest_version: str,
        release_url: str
    ) -> None:
        """
        显示更新可用对话框
        
        Args:
            parent: 父窗口
            translations: 翻译字典
            current_language: 当前语言
            current_version: 当前版本
            latest_version: 最新版本
            release_url: 发布页面URL
        """
        if not release_url:
            logger.warning("发布URL为空，无法打开浏览器")
            return
        
        update_message = self._t(
            translations,
            current_language,
            "update_available",
            current=current_version,
            latest=latest_version
        )
        
        user_wants_update = askyesno_relative(
            parent,
            self._t(translations, current_language, "update_available_title"),
            update_message
        )
        
        if user_wants_update:
            try:
                webbrowser.open(release_url)
            except Exception as e:
                logger.error(f"无法打开浏览器: {e}")
                showerror_relative(
                    parent,
                    self._t(translations, current_language, "error"),
                    f"无法打开浏览器: {release_url}"
                )
    
    def _t(
        self,
        translations: Dict[str, Dict[str, str]],
        language: str,
        key: str,
        **kwargs: Any
    ) -> str:
        """
        翻译函数
        
        Args:
            translations: 翻译字典
            language: 当前语言
            key: 翻译键
            **kwargs: 格式化参数
            
        Returns:
            翻译后的文本
        """
        text = translations[language].get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text



