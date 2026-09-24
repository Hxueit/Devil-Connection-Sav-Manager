"""自动存档对话框：列出游戏的几个自动存档文件，可以用 JSON 编辑器打开并修改"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

import customtkinter as ctk

from src.modules.save_analysis.sf.save_file_viewer import SaveFileViewer
from src.modules.save_analysis.tyrano.save_slot import TYRANO_COLLAPSED_FIELDS
from src.utils.sav_io import read_sav, write_sav
from src.utils.styles import Colors, get_cjk_font, white_button
from src.utils.ui_utils import create_dialog, showerror_relative, showinfo_relative

if TYPE_CHECKING:
    from src.modules.save_analysis.tyrano.save_viewer import TyranoSaveViewer

logger = logging.getLogger(__name__)

# (文件名, 名称的翻译键, 说明的翻译键)
AUTO_SAVE_FILES = [
    ("DevilConnection_tyrano_auto_save.sav", "tyrano_auto_save_name_default", "tyrano_auto_save_desc_default"),
    ("DevilConnection_tyrano_auto_save_day3.sav", "tyrano_auto_save_name_day3", None),
    ("DevilConnection_tyrano_auto_save_kui.sav", "tyrano_auto_save_name_kui", None),
    ("DevilConnection_tyrano_auto_save_b.sav", "tyrano_auto_save_name_b", "tyrano_auto_save_desc_b"),
]


class TyranoAutoSavesDialog:
    """自动存档列表"""

    def __init__(self, viewer: "TyranoSaveViewer") -> None:
        self.t = t = viewer.t
        self.storage_dir = Path(viewer.analyzer.storage_dir)

        self.dialog = create_dialog(viewer.root_window, t("tyrano_auto_saves_dialog_title"), "500x280",
                                    modal=False, use_ctk=True)
        main_frame = ctk.CTkFrame(self.dialog, fg_color=Colors.WHITE)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        for filename, name_key, desc_key in AUTO_SAVE_FILES:
            file_path = self.storage_dir / filename
            exists = file_path.is_file()

            row_container = ctk.CTkFrame(main_frame, fg_color=Colors.WHITE)
            row_container.pack(fill="x", padx=5, pady=5)
            row = ctk.CTkFrame(row_container, fg_color=Colors.WHITE)
            row.pack(fill="x")
            ctk.CTkLabel(row, text=t(name_key), font=get_cjk_font(12), text_color=Colors.TEXT_PRIMARY,
                         anchor="w", width=200).pack(side="left", padx=(10, 20))
            ctk.CTkLabel(row, font=get_cjk_font(11), width=80,
                         text=t("tyrano_auto_save_file_exists" if exists else "tyrano_auto_save_file_not_exists"),
                         text_color="#4CAF50" if exists else "#757575").pack(side="left", padx=(0, 20))
            white_button(row, t("tyrano_auto_save_edit_button"),
                         lambda p=file_path, k=name_key: self._open_editor(p, k),
                         width=80, height=30, state="normal" if exists else "disabled",
                         ).pack(side="right", padx=(0, 10))
            if desc_key:
                ctk.CTkLabel(row_container, text=t(desc_key), font=get_cjk_font(9),
                             text_color=Colors.TEXT_SECONDARY, anchor="w", justify="left",
                             ).pack(fill="x", padx=(10, 10), pady=(0, 5))

    def _open_editor(self, file_path: Path, name_key: str) -> None:
        t = self.t
        try:
            save_data = read_sav(file_path)
        except FileNotFoundError:
            error = t("tyrano_auto_save_error_not_found")
        except PermissionError:
            error = t("tyrano_auto_save_error_no_permission")
        except (OSError, ValueError) as e:
            logger.error("Failed to load auto save file %s: %s", file_path, e, exc_info=True)
            error = str(e)
        else:
            error = None
        if error is not None:
            showerror_relative(self.dialog, t("error"), t("tyrano_auto_save_load_failed", error=error))
            return

        def load() -> Optional[Dict[str, Any]]:
            try:
                return read_sav(file_path)
            except (OSError, ValueError) as e:
                logger.error("Failed to reload auto save file %s: %s", file_path, e, exc_info=True)
                return None

        def save(edited_data: Dict[str, Any]) -> bool:
            write_sav(file_path, edited_data)
            return True

        SaveFileViewer.open_or_focus(
            viewer_id=str(file_path.resolve()),   # 用绝对路径区分不同文件的编辑器窗口
            parent=self.dialog,
            t=t,
            data=save_data,
            title=f"{t('tyrano_auto_saves_dialog_title')} - {t(name_key)}",
            load=load,
            save=save,
            collapsed_fields=TYRANO_COLLAPSED_FIELDS,
            show_collapse_toggle=True,
            on_saved=lambda edited: showinfo_relative(self.dialog, t("success"), t("tyrano_auto_save_save_success")),
        )
