"""文件保存服务

负责存档文件的加载和保存操作。
"""

import json
import logging
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from src.utils.ui_utils import showerror_relative, showinfo_relative

from .config import SAVE_FILE_NAME
from .models import ViewerConfig

logger = logging.getLogger(__name__)


class FileSaver:
    """文件保存服务，处理文件 I/O 操作"""
    
    def __init__(
        self,
        storage_dir: str,
        viewer_config: ViewerConfig,
        translate_func: Callable[[str], str],
        window: Any
    ):
        """初始化文件保存服务
        
        Args:
            storage_dir: 存档目录路径
            viewer_config: 查看器配置
            translate_func: 翻译函数
            window: 窗口对象（用于显示错误消息）
        """
        self.storage_dir = storage_dir
        self.viewer_config = viewer_config
        self.t = translate_func
        self.window = window
    
    def load_save_file(self) -> Optional[Dict[str, Any]]:
        """从文件系统加载存档文件
        
        Returns:
            存档数据字典，如果加载失败则返回 None
        """
        if self.viewer_config.custom_load_func:
            try:
                return self.viewer_config.custom_load_func()
            except Exception as e:
                logger.error(f"Custom load function failed: {e}", exc_info=True)
                showerror_relative(
                    self.window,
                    self.t("error"),
                    self.t("save_file_load_failed").format(error=str(e))
                )
                return None
        
        from ..save_data_service import load_save_file
        try:
            return load_save_file(self.storage_dir)
        except Exception as e:
            logger.error(f"Failed to load save file: {e}", exc_info=True)
            showerror_relative(
                self.window,
                self.t("error"),
                self.t("save_file_not_found")
            )
            return None
    
    def save_to_file(
        self,
        edited_data: Dict[str, Any],
        on_success: Optional[Callable[[], None]] = None
    ) -> bool:
        """保存数据到文件
        
        Args:
            edited_data: 编辑后的数据字典
            on_success: 保存成功后的回调函数
            
        Returns:
            是否保存成功
        """
        if self.viewer_config.custom_save_func:
            try:
                success = self.viewer_config.custom_save_func(edited_data)
                if success:
                    if self.viewer_config.on_save_callback:
                        try:
                            self.viewer_config.on_save_callback(edited_data)
                        except Exception as callback_error:
                            logger.error(f"on_save_callback failed: {callback_error}", exc_info=True)
                    
                    if on_success:
                        on_success()
                    
                    showinfo_relative(
                        self.window,
                        self.t("success"),
                        self.t("save_success")
                    )
                else:
                    showerror_relative(
                        self.window,
                        self.t("error"),
                        self.t("save_file_failed").format(error="保存失败")
                    )
                return success
            except Exception as save_error:
                logger.error(f"Custom save function failed: {save_error}", exc_info=True)
                showerror_relative(
                    self.window,
                    self.t("error"),
                    self.t("save_file_failed").format(error=str(save_error))
                )
                return False
        
        # 默认保存逻辑：保存到 DevilConnection_sf.sav
        save_file_path = Path(self.storage_dir) / SAVE_FILE_NAME
        
        try:
            json_str = json.dumps(edited_data, ensure_ascii=False)
            encoded_content = urllib.parse.quote(json_str)
            
            with open(save_file_path, 'w', encoding='utf-8') as file_handle:
                file_handle.write(encoded_content)
            
            if self.viewer_config.on_save_callback:
                try:
                    self.viewer_config.on_save_callback(edited_data)
                except Exception as callback_error:
                    logger.error(f"on_save_callback failed: {callback_error}", exc_info=True)
            
            if on_success:
                on_success()
            
            showinfo_relative(
                self.window,
                self.t("success"),
                self.t("save_success")
            )
            return True
            
        except (OSError, IOError, PermissionError) as file_error:
            logger.error(f"Failed to save file: {file_error}", exc_info=True)
            showerror_relative(
                self.window,
                self.t("error"),
                self.t("save_file_failed").format(error=str(file_error))
            )
            return False
        except Exception as e:
            logger.error(f"Unexpected error saving file: {e}", exc_info=True)
            showerror_relative(
                self.window,
                self.t("error"),
                self.t("save_file_failed").format(error=str(e))
            )
            return False
