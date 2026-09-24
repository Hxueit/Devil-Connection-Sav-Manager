"""语言检测和翻译服务模块

提供系统语言检测、语言切换和翻译功能。
"""
import locale
import logging
import os
import platform
from typing import Optional, Dict, Callable

from src.utils.translations import TRANSLATIONS

logger = logging.getLogger(__name__)


class LanguageService:
    """语言服务类，负责语言检测和翻译"""
    
    DEFAULT_LANGUAGE = "en_US"
    SUPPORTED_LANGUAGES = {"zh_CN", "ja_JP", "en_US"}
    LANGUAGE_MAPPING = {
        'zh': 'zh_CN',
        'ja': 'ja_JP',
        'en': 'en_US'
    }
    
    def __init__(self, translations: Dict[str, Dict[str, str]]):
        """初始化语言服务
        
        Args:
            translations: 翻译字典
            
        Raises:
            ValueError: 如果translations为空或None
        """
        if not translations:
            raise ValueError("translations cannot be empty or None")
        
        self.translations = translations
        self.current_language = self.detect_system_language()
    
    def detect_system_language(self) -> str:
        """检测系统语言并返回支持的语言代码
        
        Returns:
            支持的语言代码，默认为en_US
        """
        language_detectors: list[Callable[[], Optional[str]]] = [
            self._detect_from_locale_getdefaultlocale,
            self._detect_from_environment_vars,
            self._detect_from_locale_getlocale,
            self._detect_from_windows_api,
            self._detect_from_system_locale
        ]
        
        for detector in language_detectors:
            try:
                result = detector()
                if result and result in self.SUPPORTED_LANGUAGES:
                    return result
            except Exception as e:
                logger.debug(f"Language detection method failed: {e}")
                continue
        
        return self.DEFAULT_LANGUAGE
    
    def _detect_from_locale_getdefaultlocale(self) -> Optional[str]:
        """从locale.getdefaultlocale检测语言"""
        try:
            default_locale = locale.getdefaultlocale()
            if default_locale and default_locale[0]:
                language_code = default_locale[0].split('_')[0].lower()
                return self._map_language_code(language_code)
        except (AttributeError, IndexError, TypeError) as e:
            logger.debug(f"Error in getdefaultlocale detection: {e}")
        return None
    
    def _detect_from_environment_vars(self) -> Optional[str]:
        """从环境变量检测语言"""
        env_keys = ['APP_LANG', 'SCREENSHOT_TOOL_LANG', 'LANGUAGE', 'LANG', 'LC_ALL', 'LC_MESSAGES']
        
        for env_key in env_keys:
            env_lang = os.environ.get(env_key)
            if env_lang:
                try:
                    normalized_lang = env_lang.strip().replace('-', '_').split('.')[0].lower()
                    mapped = self._map_language_code(normalized_lang)
                    if mapped:
                        return mapped
                except (AttributeError, ValueError) as e:
                    logger.debug(f"Error parsing env var {env_key}: {e}")
                    continue
        return None
    
    def _detect_from_locale_getlocale(self) -> Optional[str]:
        """从locale.getlocale检测语言"""
        try:
            system_locale, _ = locale.getlocale()
            if not system_locale:
                try:
                    locale.setlocale(locale.LC_ALL, '')
                    system_locale, _ = locale.getlocale()
                except (locale.Error, ValueError) as e:
                    logger.debug(f"Error setting locale: {e}")
            
            if system_locale:
                locale_lower = system_locale.replace('-', '_').split('.')[0].lower()
                return self._map_language_code(locale_lower)
        except (AttributeError, TypeError, ValueError) as e:
            logger.debug(f"Error in getlocale detection: {e}")
        return None
    
    def _detect_from_windows_api(self) -> Optional[str]:
        """从Windows API检测语言"""
        if platform.system() != "Windows":
            return None
            
        try:
            import ctypes
            windll = ctypes.windll
            GetUserDefaultUILanguage = windll.kernel32.GetUserDefaultUILanguage
            lang_id = GetUserDefaultUILanguage()
            
            LANGUAGE_ID_MAP = {
                0x804: "zh_CN", 0x404: "zh_CN", 0xc04: "zh_CN",
                0x1004: "zh_CN", 0x1404: "zh_CN", 0x7c04: "zh_CN",
                0x411: "ja_JP", 0x814: "ja_JP",
                0x409: "en_US", 0x809: "en_US"
            }
            
            return LANGUAGE_ID_MAP.get(lang_id)
        except (AttributeError, OSError, ImportError) as e:
            logger.debug(f"Error in Windows API detection: {e}")
        return None
    
    def _detect_from_system_locale(self) -> Optional[str]:
        """从系统locale检测语言"""
        try:
            system_locale = locale.getlocale()[0]
            if system_locale:
                locale_lower = system_locale.replace('-', '_').split('.')[0].lower()
                return self._map_language_code(locale_lower)
        except (AttributeError, IndexError, TypeError) as e:
            logger.debug(f"Error in system locale detection: {e}")
        return None
    
    def _map_language_code(self, language_code: str) -> Optional[str]:
        """映射语言代码到支持的语言
        
        Args:
            language_code: 语言代码
            
        Returns:
            映射后的语言代码，如果无法映射则返回None
        """
        if not language_code or not isinstance(language_code, str):
            return None
        
        language_code = language_code.lower()
        
        if language_code in self.LANGUAGE_MAPPING:
            return self.LANGUAGE_MAPPING[language_code]
        
        for prefix, lang in self.LANGUAGE_MAPPING.items():
            if language_code.startswith(prefix):
                return lang
        
        return None
    
    def translate(self, key: str, **kwargs) -> str:
        """翻译函数，支持格式化字符串
        
        Args:
            key: 翻译键
            **kwargs: 格式化参数
            
        Returns:
            翻译后的文本
        """
        if not key or not isinstance(key, str):
            return str(key) if key is not None else ""
        
        try:
            lang_dict = self.translations.get(self.current_language, {})
            text = lang_dict.get(key, key)
            
            if kwargs:
                try:
                    return text.format(**kwargs)
                except (KeyError, ValueError, IndexError) as e:
                    logger.debug(f"Error formatting translation key '{key}': {e}")
                    return text
            return text
        except (AttributeError, TypeError) as e:
            logger.warning(f"Error translating key '{key}': {e}")
            return key
    
    def change_language(self, lang: str) -> bool:
        """切换语言
        
        Args:
            lang: 语言代码
            
        Returns:
            是否切换成功
        """
        if not lang or not isinstance(lang, str):
            return False
        
        if lang not in self.translations:
            logger.warning(f"Unsupported language: {lang}")
            return False
        
        if lang not in self.SUPPORTED_LANGUAGES:
            logger.warning(f"Language {lang} not in supported languages")
            return False
            
        self.current_language = lang
        return True
    
    def get_supported_languages(self) -> list[tuple[str, str]]:
        """获取支持的语言列表
        
        Returns:
            (显示名称, 语言代码) 的列表
        """
        return [
            ("日本語", "ja_JP"),
            ("中文", "zh_CN"),
            ("English", "en_US")
        ]

