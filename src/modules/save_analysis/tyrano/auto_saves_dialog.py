"""Tyrano自动存档管理对话框

提供自动存档文件的查看和编辑功能
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List, Tuple, Final
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

from src.modules.others.tyrano_service import TyranoService
from src.modules.save_analysis.sf.save_file_viewer import SaveFileViewer, ViewerConfig
from src.utils.ui_utils import (
    showinfo_relative,
    showerror_relative,
    set_window_icon
)

logger = logging.getLogger(__name__)

AUTO_SAVE_FILES: Final[List[Tuple[str, str]]] = [
    ("DevilConnection_tyrano_auto_save.sav", "tyrano_auto_save_name_default"),
    ("DevilConnection_tyrano_auto_save_day3.sav", "tyrano_auto_save_name_day3"),
    ("DevilConnection_tyrano_auto_save_kui.sav", "tyrano_auto_save_name_kui"),
    ("DevilConnection_tyrano_auto_save_b.sav", "tyrano_auto_save_name_b"),
]

TYRANO_COLLAPSED_FIELDS: Final[List[str]] = [
    "stat.map_label",
    "stat.charas",
    "stat.map_keyframe",
    "stat.stack",
    "stat.popopo",
    "stat.map_macro",
    "stat.fuki",
    "three"
]

STATUS_COLOR_EXISTS = "#4CAF50"
STATUS_COLOR_NOT_EXISTS = "#757575"
DIALOG_SIZE = "500x280"
ICON_SETUP_DELAYS = [50, 200]


class AutoSaveFileViewer(SaveFileViewer):
    """自动存档文件查看器，覆盖保存逻辑以保存到指定文件"""
    
    def __init__(
        self,
        window: tk.Widget,
        storage_dir: str,
        save_data: Dict[str, Any],
        t_func: Callable[[str], str],
        file_path: Path,
        on_save_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        viewer_config: Optional[ViewerConfig] = None,
        _viewer_id: Optional[str] = None
    ) -> None:
        """初始化自动存档文件查看器
        
        Args:
            window: 主窗口对象
            storage_dir: 存档目录
            save_data: 存档数据
            t_func: 翻译函数
            file_path: 要保存到的文件路径
            on_save_callback: 保存成功后的回调函数
            viewer_config: 查看器配置
            _viewer_id: 内部使用，用于注册表管理
        """
        self.auto_save_file_path = file_path
        self.on_save_callback = on_save_callback
        super().__init__(
            window=window,
            storage_dir=storage_dir,
            save_data=save_data,
            t_func=t_func,
            on_close_callback=None,
            mode="file",
            viewer_config=viewer_config,
            _viewer_id=_viewer_id
        )
    
    def _save_to_file(
        self,
        edited_data: Dict[str, Any],
        content: str,
        enable_edit_var: tk.BooleanVar,
        text_widget: tk.Text,
        update_display: Callable,
        get_current_text_content: Callable[[], str]
    ) -> None:
        """保存到文件"""
        user_confirmed = messagebox.askyesno(
            self.t("save_confirm_title"),
            self.t("save_confirm_text"),
            parent=self.viewer_window
        )
        
        if not user_confirmed:
            text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
            return
        
        tyrano_service = TyranoService()
        try:
            tyrano_service.save_tyrano_save_file(self.auto_save_file_path, edited_data)
            self.save_data = edited_data
            self.original_save_data = self._deep_copy_data(edited_data)
            
            showinfo_relative(
                self.viewer_window,
                self.t("success"),
                self.t("save_success")
            )
            
            if self.on_save_callback:
                self.on_save_callback(edited_data)
            
            update_display()
        except (PermissionError, OSError, ValueError) as e:
            logger.error(
                "Failed to save auto save file %s: %s",
                self.auto_save_file_path,
                e,
                exc_info=True
            )
            showerror_relative(
                self.viewer_window,
                self.t("error"),
                self.t("save_file_failed").format(error=str(e))
            )
        finally:
            text_widget.config(state="normal" if enable_edit_var.get() else "disabled")


class TyranoAutoSavesDialog:
    """Tyrano自动存档管理对话框"""
    
    def __init__(
        self,
        parent: tk.Widget,
        root_window: tk.Widget,
        storage_dir: str,
        translation_func: Callable[[str], str],
        get_cjk_font_func: Callable[[int], Any],
        colors_class: type
    ) -> None:
        """初始化自动存档对话框
        
        Args:
            parent: 父窗口
            root_window: 根窗口（可以是tk.Widget，会自动查找tk.Tk）
            storage_dir: 存储目录路径
            translation_func: 翻译函数
            get_cjk_font_func: 字体获取函数
            colors_class: 颜色常量类
        """
        self.parent = parent
        self.root = self._find_root_window(root_window)
        self.storage_dir = Path(storage_dir)
        self.translate = translation_func
        self.get_cjk_font = get_cjk_font_func
        self.Colors = colors_class
        self.tyrano_service = TyranoService()
        
        self.dialog: Optional[ctk.CTkToplevel] = None
        self.file_info_list: List[Tuple[str, str, Path, bool]] = []
        self.file_rows: List[Dict[str, Any]] = []
        
        self._scan_files()
        self._create_dialog()
    
    def _scan_files(self) -> None:
        """扫描自动存档文件"""
        self.file_info_list = []
        
        for filename, name_key in AUTO_SAVE_FILES:
            file_path = self.storage_dir / filename
            exists = file_path.exists() and file_path.is_file()
            self.file_info_list.append((filename, name_key, file_path, exists))
    
    def _create_dialog(self) -> None:
        """创建对话框窗口"""
        self.dialog = ctk.CTkToplevel(self.root)
        self.dialog.title(self.translate("tyrano_auto_saves_dialog_title"))
        self.dialog.geometry(DIALOG_SIZE)
        self.dialog.transient(self.root)
        
        dialog_ref = self.dialog
        for delay in ICON_SETUP_DELAYS:
            self.dialog.after(delay, lambda d=dialog_ref: set_window_icon(d))
        
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        
        main_frame = ctk.CTkFrame(self.dialog, fg_color=self.Colors.WHITE)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self._create_file_list(main_frame)
    
    def _create_file_list(self, parent: ctk.CTkFrame) -> None:
        """创建文件列表UI"""
        self.file_rows = []
        
        for filename, name_key, file_path, exists in self.file_info_list:
            # 主行容器
            row_container = ctk.CTkFrame(parent, fg_color=self.Colors.WHITE)
            row_container.pack(fill="x", padx=5, pady=5)
            
            # 第一行：名称、状态、按钮
            row_frame = ctk.CTkFrame(row_container, fg_color=self.Colors.WHITE)
            row_frame.pack(fill="x", padx=0, pady=0)
            
            name_label = ctk.CTkLabel(
                row_frame,
                text=self.translate(name_key),
                font=self.get_cjk_font(12),
                text_color=self.Colors.TEXT_PRIMARY,
                anchor="w",
                width=200
            )
            name_label.pack(side="left", padx=(10, 20))
            
            status_text_key = (
                "tyrano_auto_save_file_exists" if exists
                else "tyrano_auto_save_file_not_exists"
            )
            status_color = (
                STATUS_COLOR_EXISTS if exists
                else STATUS_COLOR_NOT_EXISTS
            )
            
            status_label = ctk.CTkLabel(
                row_frame,
                text=self.translate(status_text_key),
                font=self.get_cjk_font(11),
                text_color=status_color,
                width=80
            )
            status_label.pack(side="left", padx=(0, 20))
            
            edit_button = ctk.CTkButton(
                row_frame,
                text=self.translate("tyrano_auto_save_edit_button"),
                command=lambda fp=file_path, fn=filename: self._on_edit_click(fp, fn),
                width=80,
                height=30,
                corner_radius=8,
                fg_color=self.Colors.WHITE,
                hover_color=self.Colors.LIGHT_GRAY,
                border_width=1,
                border_color=self.Colors.GRAY,
                text_color=self.Colors.TEXT_PRIMARY,
                font=self.get_cjk_font(10),
                state="normal" if exists else "disabled"
            )
            edit_button.pack(side="right", padx=(0, 10))
            
            # 第二行：说明文字（仅对default和b显示）
            desc_key = None
            if name_key == "tyrano_auto_save_name_b":
                desc_key = "tyrano_auto_save_desc_b"
            elif name_key == "tyrano_auto_save_name_default":
                desc_key = "tyrano_auto_save_desc_default"
            
            if desc_key:
                desc_label = ctk.CTkLabel(
                    row_container,
                    text=self.translate(desc_key),
                    font=self.get_cjk_font(9),
                    text_color=self.Colors.TEXT_SECONDARY,
                    anchor="w",
                    justify="left"
                )
                desc_label.pack(fill="x", padx=(10, 10), pady=(0, 5))
            else:
                desc_label = None
            
            self.file_rows.append({
                "row_frame": row_frame,
                "name_label": name_label,
                "status_label": status_label,
                "edit_button": edit_button,
                "desc_label": desc_label,
                "file_path": file_path,
                "filename": filename,
                "exists": exists
            })
    
    def _get_name_key_from_filename(self, filename: str) -> str:
        """根据文件名获取友好名称键
        
        Args:
            filename: 文件名
            
        Returns:
            翻译键名
        """
        if "day3" in filename:
            return "tyrano_auto_save_name_day3"
        if "kui" in filename:
            return "tyrano_auto_save_name_kui"
        if "_b.sav" in filename:
            return "tyrano_auto_save_name_b"
        return "tyrano_auto_save_name_default"
    
    def _on_edit_click(self, file_path: Path, filename: str) -> None:
        """编辑按钮点击事件
        
        Args:
            file_path: 文件路径
            filename: 文件名
        """
        try:
            save_data = self.tyrano_service.load_tyrano_save_file(file_path)
        except FileNotFoundError:
            showerror_relative(
                self.dialog,
                self.translate("error"),
                self.translate("tyrano_auto_save_load_failed").format(error="文件不存在")
            )
            return
        except PermissionError as e:
            logger.error("Permission denied reading file %s: %s", filename, e)
            showerror_relative(
                self.dialog,
                self.translate("error"),
                self.translate("tyrano_auto_save_load_failed").format(error="无权限读取文件")
            )
            return
        except (OSError, ValueError) as e:
            logger.error("Failed to load auto save file %s: %s", filename, e, exc_info=True)
            showerror_relative(
                self.dialog,
                self.translate("error"),
                self.translate("tyrano_auto_save_load_failed").format(error=str(e))
            )
            return
        
        def on_save(edited_data: Dict[str, Any]) -> None:
            showinfo_relative(
                self.dialog,
                self.translate("success"),
                self.translate("tyrano_auto_save_save_success")
            )
        
        name_key = self._get_name_key_from_filename(filename)
        
        # 创建自定义加载函数，从指定的自动存档文件加载数据
        def load_auto_save_data() -> Optional[Dict[str, Any]]:
            try:
                return self.tyrano_service.load_tyrano_save_file(file_path)
            except (FileNotFoundError, PermissionError, OSError, ValueError) as e:
                logger.error("Failed to load auto save file %s: %s", filename, e, exc_info=True)
                return None
        
        viewer_config = ViewerConfig(
            enable_edit_by_default=True,
            show_enable_edit_checkbox=False,
            show_collapse_checkbox=True,
            show_hint_label=True,
            title_key="save_file_viewer_title",
            collapsed_fields=TYRANO_COLLAPSED_FIELDS.copy(),
            custom_load_func=load_auto_save_data
        )
        
        viewer = AutoSaveFileViewer.open_or_focus(
            viewer_id=str(file_path.resolve()),  # 使用绝对路径，避免同名文件冲突
            window=self.dialog,
            storage_dir=str(self.storage_dir),
            save_data=save_data,
            t_func=self.translate,
            file_path=file_path,
            on_save_callback=on_save,
            viewer_config=viewer_config
        )
        
        if (hasattr(viewer, 'viewer_window') and
            viewer.viewer_window and
            viewer.viewer_window.winfo_exists()):
            title = f"{self.translate('tyrano_auto_saves_dialog_title')} - {self.translate(name_key)}"
            viewer.viewer_window.title(title)
    
    def _find_root_window(self, window: tk.Widget) -> tk.Tk:
        """查找根窗口"""
        root = window
        while not isinstance(root, tk.Tk) and hasattr(root, 'master'):
            root = root.master
        return root
    
    def _on_close(self) -> None:
        """关闭对话框"""
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.destroy()

