"""其他功能标签页UI

负责渲染其他功能标签页的UI界面，处理用户交互事件。
业务逻辑已委托给相应的服务模块。
"""
from tkinter import filedialog
from pathlib import Path
from typing import Optional, Dict, Any
import customtkinter as ctk
import json
import logging
from src.modules.others.config import OthersTabConfig
from src.modules.others.tyrano_service import TyranoService
from src.modules.others.update_service import UpdateService
from src.modules.others.ui_components import CRC32Calculator
from src.utils.styles import get_cjk_font, Colors
from src.utils.ui_utils import (
    showinfo_relative,
    showerror_relative,
    askyesno_relative
)

logger = logging.getLogger(__name__)


class OthersTab:
    """其他功能标签页
    
    主要负责UI渲染和事件处理，业务逻辑委托给服务层。
    """
    
    def __init__(
        self,
        parent: ctk.CTkFrame,
        storage_dir: Optional[str],
        translations: Dict[str, Dict[str, str]],
        current_language: str,
        main_app: Any
    ) -> None:
        """
        初始化其他功能标签页
        
        Args:
            parent: 父容器（Frame）
            storage_dir: 存储目录路径
            translations: 翻译字典
            current_language: 当前语言
            main_app: 主应用实例（用于访问toast相关功能）
        """
        self.parent = parent
        self.storage_dir = Path(storage_dir) if storage_dir else None
        self.translations = translations
        self.current_language = current_language
        self.main_app = main_app
        
        # 初始化服务
        self.tyrano_service = TyranoService(
            calculation_timeout_seconds=OthersTabConfig.CRC32_CALCULATION_TIMEOUT_SECONDS
        )
        self.crc32_calculator = CRC32Calculator(self.tyrano_service)
        
        # 从主应用同步默认设置
        self.toast_enabled = getattr(
            main_app,
            'toast_enabled',
            OthersTabConfig.DEFAULT_TOAST_ENABLED
        )
        self.toast_ignore_record = getattr(
            main_app,
            'toast_ignore_record',
            OthersTabConfig.DEFAULT_TOAST_IGNORE_RECORD
        )
        
        self._init_ui()
    
    def _init_ui(self) -> None:
        """初始化UI"""
        main_container = ctk.CTkFrame(self.parent, fg_color=Colors.WHITE)
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        content_frame = ctk.CTkFrame(
            main_container,
            fg_color=Colors.WHITE,
            corner_radius=10
        )
        content_frame.pack(fill="both", expand=True)
        
        button_frame = ctk.CTkFrame(content_frame, fg_color=Colors.WHITE)
        button_frame.pack(fill="x", pady=10)
        
        self._create_toast_section(button_frame)
        self._create_ignore_vars_section(button_frame)
        self._create_action_buttons(button_frame)
    
    def _create_toast_section(self, parent: ctk.CTkFrame) -> None:
        """创建Toast功能开关区域"""
        toast_frame = ctk.CTkFrame(parent, fg_color=Colors.WHITE)
        toast_frame.pack(fill="x", pady=10)
        
        self.toast_var = ctk.BooleanVar(value=self.toast_enabled)
        toast_checkbox = ctk.CTkCheckBox(
            toast_frame,
            text=self.t("enable_toast"),
            variable=self.toast_var,
            command=self._on_toast_toggle,
            fg_color=Colors.ACCENT_BLUE,
            hover_color=Colors.ACCENT_PINK,
            border_width=2,
            corner_radius=6
        )
        toast_checkbox.pack(anchor="w", pady=2)
    
    def _create_ignore_vars_section(self, parent: ctk.CTkFrame) -> None:
        """创建忽略变量输入区域"""
        ignore_vars_frame = ctk.CTkFrame(parent, fg_color=Colors.WHITE)
        ignore_vars_frame.pack(fill="x", pady=10)
        
        ignore_vars_label = ctk.CTkLabel(
            ignore_vars_frame,
            text=self.t("toast_ignore_vars_label"),
            font=get_cjk_font(10),
            text_color=Colors.TEXT_PRIMARY
        )
        ignore_vars_label.pack(anchor="w", pady=(0, 5))
        
        self.ignore_vars_var = ctk.StringVar(value=self.toast_ignore_record)
        self.ignore_vars_entry = ctk.CTkEntry(
            ignore_vars_frame,
            textvariable=self.ignore_vars_var,
            font=get_cjk_font(10),
            corner_radius=8,
            fg_color=Colors.WHITE,
            text_color=Colors.TEXT_PRIMARY,
            border_color=Colors.GRAY,
            width=OthersTabConfig.IGNORE_VARS_ENTRY_WIDTH,
            placeholder_text=self.t("toast_ignore_vars_hint")
        )
        self.ignore_vars_entry.pack(fill="x", anchor="w")
        self.ignore_vars_entry.bind(
            "<KeyRelease>",
            lambda e: self._on_ignore_vars_change()
        )
        
        ignore_vars_hint = ctk.CTkLabel(
            ignore_vars_frame,
            text=self.t("toast_ignore_vars_hint"),
            font=get_cjk_font(9),
            text_color=Colors.TEXT_SECONDARY
        )
        ignore_vars_hint.pack(anchor="w", pady=(3, 0))
        
        self._update_ignore_vars_entry_state()
    
    def _create_action_buttons(self, parent: ctk.CTkFrame) -> None:
        """创建操作按钮"""
        button_configs = [
            {
                "text_key": "export_tyrano_data",
                "command": self._export_tyrano_data
            },
            {
                "text_key": "import_tyrano_data",
                "command": self._import_tyrano_data
            },
            {
                "text_key": "check_for_updates",
                "command": self._check_for_updates
            }
        ]
        
        for config in button_configs:
            button = self._create_standard_button(
                parent,
                self.t(config["text_key"]),
                config["command"]
            )
            button.pack(fill="x", pady=10)
    
    def _create_standard_button(
        self,
        parent: ctk.CTkFrame,
        text: str,
        command: callable
    ) -> ctk.CTkButton:
        """创建标准样式的按钮"""
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            corner_radius=8,
            fg_color=Colors.WHITE,
            hover_color=Colors.LIGHT_GRAY,
            border_width=1,
            border_color=Colors.GRAY,
            text_color=Colors.TEXT_PRIMARY,
            font=get_cjk_font(10)
        )
    
    def t(self, key: str, **kwargs: Any) -> str:
        """翻译函数"""
        text = self.translations[self.current_language].get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text
    
    def _on_toast_toggle(self) -> None:
        """toast功能开关回调"""
        self.toast_enabled = self.toast_var.get()
        self.main_app.toast_enabled = self.toast_enabled
        self._update_ignore_vars_entry_state()
    
    def _update_ignore_vars_entry_state(self) -> None:
        """更新ignore_vars_entry的可用状态"""
        if not hasattr(self, 'ignore_vars_entry'):
            return
        
        if self.toast_enabled:
            self.ignore_vars_entry.configure(
                state="normal",
                fg_color=Colors.WHITE,
                text_color=Colors.TEXT_PRIMARY,
                border_color=Colors.GRAY
            )
        else:
            self.ignore_vars_entry.configure(
                state="disabled",
                fg_color=Colors.LIGHT_GRAY,
                text_color=Colors.TEXT_DISABLED,
                border_color=Colors.DARK_GRAY
            )
    
    def _on_ignore_vars_change(self) -> None:
        """忽略变量输入框变化回调"""
        self.toast_ignore_record = self.ignore_vars_var.get()
        self.main_app.toast_ignore_record = self.toast_ignore_record
        
        if hasattr(self.main_app, 'update_toast_ignore_record'):
            self.main_app.update_toast_ignore_record(self.toast_ignore_record)
    
    def _validate_storage_dir(self) -> Optional[Path]:
        """
        验证存储目录是否有效
        
        Returns:
            存储目录Path对象，如果无效则返回None并显示错误
        """
        if not self.storage_dir:
            self._show_error("select_dir_hint")
            return None
        return self.storage_dir
    
    def _get_tyrano_file_path(self) -> Optional[Path]:
        """
        获取tyrano文件路径
        
        Returns:
            tyrano文件路径，如果存储目录无效则返回None
        """
        storage_dir = self._validate_storage_dir()
        if not storage_dir:
            return None
        
        tyrano_file_path = storage_dir / OthersTabConfig.TYRANO_SAV_FILENAME
        return tyrano_file_path
    
    def _show_error(self, message_key: str, **kwargs: Any) -> None:
        """显示错误对话框"""
        showerror_relative(
            self.parent,
            self.t("error"),
            self.t(message_key, **kwargs)
        )
    
    def _show_success(self, message_key: str, **kwargs: Any) -> None:
        """显示成功对话框"""
        showinfo_relative(
            self.parent,
            self.t("success"),
            self.t(message_key, **kwargs)
        )
    
    def _export_tyrano_data(self) -> None:
        """解码并导出tyrano_data.sav"""
        tyrano_file_path = self._get_tyrano_file_path()
        if not tyrano_file_path:
            return
        
        if not tyrano_file_path.exists():
            self._show_error("tyrano_file_not_found")
            return
        
        try:
            save_data = self.tyrano_service.load_tyrano_save_file(tyrano_file_path)
        except FileNotFoundError:
            self._show_error("tyrano_file_not_found")
            return
        except PermissionError:
            logger.exception("无权限读取tyrano文件")
            self._show_error("export_tyrano_failed", error="无权限读取文件")
            return
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.exception("解析tyrano文件失败")
            self._show_error("export_tyrano_failed", error=f"文件格式错误: {e}")
            return
        except OSError as e:
            logger.exception("读取tyrano文件失败")
            self._show_error("export_tyrano_failed", error=str(e))
            return
        
        export_path = self._select_export_path()
        if not export_path:
            return
        
        try:
            self.tyrano_service.save_json_file(export_path, save_data)
            self._show_success("export_tyrano_success", path=str(export_path))
        except PermissionError:
            logger.exception("无权限写入导出文件")
            self._show_error("export_tyrano_failed", error="无权限写入文件")
        except ValueError as e:
            logger.exception("保存导出文件失败（数据无效）")
            self._show_error("export_tyrano_failed", error=f"数据无效: {e}")
        except OSError as e:
            logger.exception("写入导出文件失败")
            self._show_error("export_tyrano_failed", error=str(e))
    
    def _select_export_path(self) -> Optional[Path]:
        """选择导出文件路径"""
        file_path = filedialog.asksaveasfilename(
            title=self.t("save_file"),
            defaultextension=OthersTabConfig.JSON_EXTENSION,
            initialfile=OthersTabConfig.TYRANO_JSON_FILENAME,
            filetypes=[
                (self.t("json_files"), "*.json"),
                (self.t("all_files"), "*.*")
            ]
        )
        return Path(file_path) if file_path else None
    
    def _import_tyrano_data(self) -> None:
        """导入、编码并保存tyrano_data.sav"""
        tyrano_file_path = self._get_tyrano_file_path()
        if not tyrano_file_path:
            return
        
        import_save_data = self._load_import_json_file()
        if import_save_data is None:
            return
        
        crc32_result = self.crc32_calculator.calculate_with_progress(
            self.parent,
            import_save_data,
            tyrano_file_path,
            self.t("calculating_crc32"),
            self.t("calculating_crc32_progress")
        )
        
        if crc32_result is None:
            self._show_error("crc32_calculation_failed", error="计算失败")
            return
        
        new_crc32_value, existing_crc32_value = crc32_result
        
        if existing_crc32_value is not None and new_crc32_value == existing_crc32_value:
            showinfo_relative(
                self.parent,
                self.t("info"),
                self.t("tyrano_no_changes")
            )
            return
        
        if not self._confirm_import():
            return
        
        try:
            self.tyrano_service.save_tyrano_save_file(tyrano_file_path, import_save_data)
            self._show_success("import_tyrano_success")
        except PermissionError:
            logger.exception("无权限写入tyrano文件")
            self._show_error("import_tyrano_failed", error="无权限写入文件")
        except ValueError as e:
            logger.exception("保存tyrano数据失败（数据无效）")
            self._show_error("import_tyrano_failed", error=f"数据无效: {e}")
        except OSError as e:
            logger.exception("保存tyrano数据失败")
            self._show_error("import_tyrano_failed", error=str(e))
    
    def _load_import_json_file(self) -> Optional[Dict[str, Any]]:
        """加载要导入的JSON文件"""
        selected_file_path = filedialog.askopenfilename(
            title=self.t("select_json_file"),
            filetypes=[
                (self.t("json_files"), "*.json"),
                (self.t("all_files"), "*.*")
            ]
        )
        
        if not selected_file_path:
            return None
        
        json_file_path = Path(selected_file_path)
        
        try:
            return self.tyrano_service.load_json_file(json_file_path)
        except FileNotFoundError:
            self._show_error("import_tyrano_failed", error="文件不存在")
            return None
        except PermissionError:
            logger.exception("无权限读取JSON文件")
            self._show_error("import_tyrano_failed", error="无权限读取文件")
            return None
        except json.JSONDecodeError as e:
            logger.exception("JSON格式错误")
            showerror_relative(
                self.parent,
                self.t("error"),
                self.t("json_format_error_detail", error=str(e))
            )
            return None
        except ValueError as e:
            logger.exception("JSON文件内容无效")
            self._show_error("import_tyrano_failed", error=f"文件内容无效: {e}")
            return None
        except OSError as e:
            logger.exception("读取JSON文件失败")
            self._show_error("import_tyrano_failed", error=str(e))
            return None
    
    def _confirm_import(self) -> bool:
        """确认导入操作"""
        if not askyesno_relative(
            self.parent,
            self.t("warning"),
            self.t("import_tyrano_confirm_1")
        ):
            return False
        
        if not askyesno_relative(
            self.parent,
            self.t("warning"),
            self.t("import_tyrano_confirm_2")
        ):
            return False
        
        return True
    
    def set_storage_dir(self, storage_dir: Optional[str]) -> None:
        """设置存储目录"""
        self.storage_dir = Path(storage_dir) if storage_dir else None
    
    def _check_for_updates(self) -> None:
        """检查GitHub更新"""
        try:
            from src.constants import VERSION
        except ImportError as e:
            logger.exception("无法导入版本号")
            self._show_error("update_check_failed", error=f"无法获取版本号: {e}")
            return
        
        if not VERSION:
            logger.error("版本号为空")
            self._show_error("update_check_failed", error="版本号无效")
            return
        
        try:
            update_service = UpdateService(VERSION)
            update_service.check_for_updates_async(
                self.parent,
                self.translations,
                self.current_language
            )
        except ValueError as e:
            logger.exception("初始化更新检查服务失败（参数错误）")
            self._show_error("update_check_failed", error=f"参数错误: {e}")
        except Exception as e:
            logger.exception("初始化更新检查服务失败（未知错误）")
            self._show_error("update_check_failed", error=str(e))
    
    def update_language(self, language: str) -> None:
        """
        更新语言
        
        Args:
            language: 新的语言代码
        """
        if not language or not isinstance(language, str):
            logger.warning(f"无效的语言代码: {language}")
            return
        
        if language not in self.translations:
            logger.warning(f"不支持的语言: {language}")
            return
        
        self.current_language = language
        
        try:
            for widget in self.parent.winfo_children():
                widget.destroy()
            self._init_ui()
        except Exception as e:
            logger.exception("更新语言时出错")
            raise
