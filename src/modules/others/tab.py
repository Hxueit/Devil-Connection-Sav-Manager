"""「其他」标签页

- 开关存档变动提示（toast），设置不监听的变量
- 导出 / 导入 tyrano 存档（明文 JSON）
- 手动检查更新
"""
import json
import logging
import webbrowser
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from src.constants import TYRANO_SAVE_FILENAME
from src.constants import VERSION
from src.modules.main.update_checker import fetch_latest_release, format_release_date, is_newer
from src.utils.background import run_in_background
from src.utils.sav_io import read_sav, write_sav, write_text_atomic
from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import askyesno_relative, showerror_relative, showinfo_relative

logger = logging.getLogger(__name__)

TYRANO_JSON_FILENAME = "DevilConnection_tyrano_data.json"


class OthersTab:
    """app 是主窗口 SavTool：提供 storage_dir、t() 以及 toast 设置"""

    def __init__(self, parent: ctk.CTkFrame, app) -> None:
        self.parent = parent
        self.app = app
        self.t = app.t
        self.container = None
        self._build_ui()

    @property
    def tyrano_path(self) -> Path:
        return Path(self.app.storage_dir) / TYRANO_SAVE_FILENAME

    # ---------- 界面 ----------

    def _build_ui(self) -> None:
        self.container = ctk.CTkFrame(self.parent, fg_color=Colors.WHITE)
        self.container.pack(fill="both", expand=True, padx=20, pady=20)
        content = ctk.CTkFrame(self.container, fg_color=Colors.WHITE, corner_radius=10)
        content.pack(fill="both", expand=True)

        # 当前路径
        path_frame = ctk.CTkFrame(content, fg_color=Colors.WHITE)
        path_frame.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(
            path_frame, text=self.t("current_selected_path"), font=get_cjk_font(11), text_color=Colors.TEXT_PRIMARY
        ).pack(anchor="w", pady=(0, 5))
        path_display = ctk.CTkTextbox(
            path_frame, height=32, font=get_cjk_font(10), fg_color=Colors.WHITE, text_color=Colors.TEXT_PRIMARY,
            border_color=Colors.GRAY, border_width=1, corner_radius=6, wrap="none",
        )
        path_display.pack(fill="x", anchor="w")
        path_display.insert("1.0", str(self.app.storage_dir))
        path_display.configure(state="disabled")

        button_frame = ctk.CTkFrame(content, fg_color=Colors.WHITE)
        button_frame.pack(fill="x", pady=10)

        # toast 开关
        toast_frame = ctk.CTkFrame(button_frame, fg_color=Colors.WHITE)
        toast_frame.pack(fill="x", pady=10)
        self.toast_var = ctk.BooleanVar(value=self.app.toast_enabled)
        ctk.CTkCheckBox(
            toast_frame, text=self.t("enable_toast"), variable=self.toast_var, command=self._on_toast_toggle,
            fg_color=Colors.ACCENT_BLUE, hover_color=Colors.ACCENT_PINK, border_width=2, corner_radius=6,
        ).pack(anchor="w", pady=2)

        # 不监听的变量
        ignore_frame = ctk.CTkFrame(button_frame, fg_color=Colors.WHITE)
        ignore_frame.pack(fill="x", pady=10)
        ctk.CTkLabel(
            ignore_frame, text=self.t("toast_ignore_vars_label"), font=get_cjk_font(10),
            text_color=Colors.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 5))
        self.ignore_vars_var = ctk.StringVar(value=self.app.toast_ignore_record)
        self.ignore_vars_entry = ctk.CTkEntry(
            ignore_frame, textvariable=self.ignore_vars_var, font=get_cjk_font(10), corner_radius=8,
            fg_color=Colors.WHITE, text_color=Colors.TEXT_PRIMARY, border_color=Colors.GRAY, width=400,
            placeholder_text=self.t("toast_ignore_vars_hint"),
        )
        self.ignore_vars_entry.pack(fill="x", anchor="w")
        self.ignore_vars_entry.bind("<KeyRelease>", lambda e: self.app.set_toast_ignore_record(self.ignore_vars_var.get()))
        ctk.CTkLabel(
            ignore_frame, text=self.t("toast_ignore_vars_hint"), font=get_cjk_font(9),
            text_color=Colors.TEXT_SECONDARY,
        ).pack(anchor="w", pady=(3, 0))
        self._update_ignore_entry_state()

        for text_key, command in (
            ("export_tyrano_data", self._export_tyrano_data),
            ("import_tyrano_data", self._import_tyrano_data),
            ("check_for_updates", self._check_for_updates),
        ):
            button = ctk.CTkButton(
                button_frame, text=self.t(text_key), command=command, corner_radius=8, fg_color=Colors.WHITE,
                hover_color=Colors.LIGHT_GRAY, border_width=1, border_color=Colors.GRAY,
                text_color=Colors.TEXT_PRIMARY, font=get_cjk_font(10),
            )
            button.pack(fill="x", pady=10)
            if text_key == "check_for_updates":
                self.update_button = button

    def update_language(self, language: str = None) -> None:
        self.container.destroy()
        self._build_ui()

    # ---------- toast 设置 ----------

    def _on_toast_toggle(self) -> None:
        self.app.set_toast_enabled(self.toast_var.get())
        self._update_ignore_entry_state()

    def _update_ignore_entry_state(self) -> None:
        if self.app.toast_enabled:
            self.ignore_vars_entry.configure(
                state="normal", fg_color=Colors.WHITE, text_color=Colors.TEXT_PRIMARY, border_color=Colors.GRAY
            )
        else:
            self.ignore_vars_entry.configure(
                state="disabled", fg_color=Colors.LIGHT_GRAY, text_color=Colors.TEXT_DISABLED,
                border_color=Colors.DARK_GRAY,
            )

    # ---------- 导出 / 导入 ----------

    def _show_error(self, key: str, **kwargs) -> None:
        showerror_relative(self.parent, self.t("error"), self.t(key, **kwargs))

    def _export_tyrano_data(self) -> None:
        """把 tyrano 存档解码后另存为格式化的 JSON"""
        if not self.tyrano_path.exists():
            self._show_error("tyrano_file_not_found")
            return
        try:
            save_data = read_sav(self.tyrano_path)
        except (OSError, ValueError) as e:
            logger.exception("读取tyrano文件失败")
            self._show_error("export_tyrano_failed", error=str(e))
            return

        file_path = filedialog.asksaveasfilename(
            title=self.t("save_file"),
            defaultextension=".json",
            initialfile=TYRANO_JSON_FILENAME,
            filetypes=[(self.t("json_files"), "*.json"), (self.t("all_files"), "*.*")],
        )
        if not file_path:
            return
        try:
            write_text_atomic(file_path, json.dumps(save_data, ensure_ascii=False, indent=2))
        except OSError as e:
            logger.exception("写入导出文件失败")
            self._show_error("export_tyrano_failed", error=str(e))
            return
        showinfo_relative(self.parent, self.t("success"), self.t("export_tyrano_success", path=file_path))

    def _import_tyrano_data(self) -> None:
        """读取 JSON，确认后编码写回 tyrano 存档"""
        file_path = filedialog.askopenfilename(
            title=self.t("select_json_file"),
            filetypes=[(self.t("json_files"), "*.json"), (self.t("all_files"), "*.*")],
        )
        if not file_path:
            return
        try:
            with open(file_path, encoding="utf-8") as f:
                new_data = json.load(f)
        except json.JSONDecodeError as e:
            self._show_error("json_format_error_detail", error=str(e))
            return
        except (OSError, ValueError) as e:
            logger.exception("读取JSON文件失败")
            self._show_error("import_tyrano_failed", error=str(e))
            return
        if not isinstance(new_data, dict) or not new_data:
            self._show_error("import_tyrano_failed", error=f"{Path(file_path).name}: not a JSON object")
            return

        try:
            unchanged = read_sav(self.tyrano_path) == new_data
        except (OSError, ValueError):
            unchanged = False  # 现有存档不存在或已损坏，直接允许导入
        if unchanged:
            showinfo_relative(self.parent, self.t("info"), self.t("tyrano_no_changes"))
            return

        if not askyesno_relative(self.parent, self.t("warning"), self.t("import_tyrano_confirm_1")):
            return
        if not askyesno_relative(self.parent, self.t("warning"), self.t("import_tyrano_confirm_2")):
            return
        try:
            write_sav(self.tyrano_path, new_data)
        except OSError as e:
            logger.exception("保存tyrano数据失败")
            self._show_error("import_tyrano_failed", error=str(e))
            return
        showinfo_relative(self.parent, self.t("success"), self.t("import_tyrano_success"))

    # ---------- 检查更新 ----------

    def _check_for_updates(self) -> None:
        self.update_button.configure(state="disabled")
        run_in_background(self.container, fetch_latest_release, self._on_update_checked)

    def _on_update_checked(self, release, error) -> None:
        self.update_button.configure(state="normal")
        if error is not None:
            self._show_error("update_check_failed", error=str(error))
            return

        latest = release["tag_name"]
        release_url = release.get("html_url")
        if is_newer(latest, VERSION):
            if askyesno_relative(
                self.parent,
                self.t("update_available_title"),
                self.t("update_available", current=VERSION, latest=latest),
            ) and release_url:
                webbrowser.open(release_url)
            return

        lines = [
            self.t("already_latest_version", version=VERSION),
            f"\n{self.t('latest_version_info')}: {latest}",
        ]
        release_date = format_release_date(release.get("published_at", ""))
        if release_date:
            lines.append(f"{self.t('release_date')}: {release_date}")
        showinfo_relative(self.parent, self.t("no_update"), "\n".join(lines))
