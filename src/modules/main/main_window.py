"""主窗口

选择 _storage 目录后，SF 存档分析和截图管理页立即创建，
其余标签页等用户第一次切换过去时才创建（懒加载），避免启动时卡顿。
"""
import locale
import logging
import os
import webbrowser
from tkinter import filedialog, ttk
from typing import Callable, Optional

import customtkinter as ctk

from src.constants import VERSION
from src.modules.backup.backup_restore_ui import BackupRestoreTab
from src.modules.main.save_change_monitor import ChangeNotifier, SaveChangeMonitor, parse_ignored_vars
from src.modules.main.steam_detector import auto_detect_storage
from src.modules.main.ui_components import MenuBar, VersionInfo
from src.modules.main.update_checker import fetch_latest_release, is_newer
from src.modules.others.tab import OthersTab
from src.modules.runtime_modify.tab import RuntimeModifyTab
from src.modules.save_analysis.sf.analyzer import SaveAnalyzer
from src.modules.save_analysis.tyrano.analyzer import TyranoAnalyzer
from src.modules.save_analysis.tyrano.save_viewer import TyranoSaveViewer
from src.modules.screenshot.screenshot_ui import ScreenshotManagerUI
from src.utils.background import run_in_background
from src.utils.styles import Colors, get_cjk_font, init_styles
from src.utils.toast import Toast
from src.utils.translations import TRANSLATIONS
from src.utils.ui_utils import set_window_icon, showinfo_relative, showwarning_relative

logger = logging.getLogger(__name__)

# 标签页顺序（索引）和标题的翻译键
SF_TAB, SCREENSHOT_TAB, BACKUP_TAB, TYRANO_TAB, RUNTIME_TAB, OTHERS_TAB = range(6)
TAB_TITLE_KEYS = [
    "sf_save_analyzer_tab",
    "screenshot_management_tab",
    "backup_restore_tab",
    "tyrano_save_management_tab",
    "runtime_modify_tab",
    "others_tab",
]
LAZY_TABS = (BACKUP_TAB, TYRANO_TAB, RUNTIME_TAB, OTHERS_TAB)

TYRANO_PREWARM_DELAY_MS = 2400  # 选择目录后稍等再在后台预读 Tyrano 存档，不和界面创建抢时间
THEME_CHECK_INTERVAL_MS = 5000
DEFAULT_TOAST_IGNORE_RECORD = "record, initialVars"
HELP_URL = "https://github.com/Hxueit/Devil-Connection-Sav-Manager"


def detect_system_language() -> str:
    """根据环境变量或系统区域设置选择界面语言，默认英文"""
    candidates = [os.environ.get(name) for name in ("APP_LANG", "LANGUAGE", "LANG", "LC_ALL", "LC_MESSAGES")]
    try:
        candidates.append(locale.getlocale()[0])
    except ValueError:
        pass
    if os.name == "nt":
        try:
            import ctypes
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            candidates.append(locale.windows_locale.get(lang_id))
        except (AttributeError, OSError):
            pass
    for candidate in candidates:
        code = (candidate or "").lower()
        # Windows 上 getlocale() 返回的是 "Chinese (Simplified)_China" 这种名字
        if code.startswith(("zh", "chinese")):
            return "zh_CN"
        if code.startswith(("ja", "japanese")):
            return "ja_JP"
        if code.startswith(("en", "english")):
            return "en_US"
    return "en_US"


class SavTool:
    """存档管理工具主窗口"""

    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        self.language = detect_system_language()
        self.storage_dir: Optional[str] = None

        # 各标签页的内容，选择目录后才创建
        self.save_analyzer: Optional[SaveAnalyzer] = None
        self.screenshot_manager_ui: Optional[ScreenshotManagerUI] = None
        self.backup_restore_tab: Optional[BackupRestoreTab] = None
        self.tyrano_tab: Optional[TyranoSaveViewer] = None
        self.runtime_modify_tab: Optional[RuntimeModifyTab] = None
        self.others_tab: Optional[OthersTab] = None
        self._pending_tabs: set = set()  # 还没创建的懒加载标签页
        self._prewarmed_tyrano: Optional[TyranoAnalyzer] = None

        # 存档变动提示（在「其他」页中开关）
        self.toast_enabled = False
        self.toast_ignore_record = DEFAULT_TOAST_IGNORE_RECORD
        self.save_monitor: Optional[SaveChangeMonitor] = None
        self.change_notifier = ChangeNotifier(root, self.t)

        root.title(self.t("window_title"))
        root.geometry("750x600")
        root.minsize(750, 600)
        set_window_icon(root)
        init_styles(root)
        root.configure(bg=Colors.LIGHT_GRAY)

        self.menubar = MenuBar(
            root, self.t, self.language,
            on_dir_browse=self.select_dir,
            on_auto_detect=self.auto_detect_steam,
            on_language_change=self.change_language,
            on_help=lambda: webbrowser.open(HELP_URL),
        )

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tab_frames = []
        self.hint_labels = []
        for title_key in TAB_TITLE_KEYS:
            frame = ctk.CTkFrame(self.notebook, fg_color=Colors.LIGHT_GRAY)
            self.notebook.add(frame, text=self.t(title_key))
            self.tab_frames.append(frame)
            self.hint_labels.append(self._create_hint_label(frame))

        self.version_info = VersionInfo(root, self.t)

        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.notebook.select(0)
        run_in_background(root, self._fetch_release_quietly, self._on_update_checked)
        root.after(THEME_CHECK_INTERVAL_MS, self._check_theme)

    def t(self, key: str, **kwargs) -> str:
        """翻译函数：返回当前语言的文字，找不到时返回 key 本身。各标签页共用这一个函数"""
        text = TRANSLATIONS[self.language].get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError):
                return text
        return text

    @staticmethod
    def _run_safely(what: str, action: Callable[[], object]) -> None:
        """执行某个标签页的操作；出错只记日志，不影响其他标签页和后续步骤"""
        try:
            action()
        except Exception:
            logger.exception(f"{what} failed")

    def _create_hint_label(self, frame: ctk.CTkFrame) -> ctk.CTkLabel:
        """「请先选择目录」提示"""
        label = ctk.CTkLabel(
            frame, text=self.t("select_dir_hint"), text_color=Colors.TEXT_HINT,
            font=get_cjk_font(12, "bold"), fg_color="transparent",
        )
        label.pack(pady=50)
        return label

    @staticmethod
    def _fetch_release_quietly():
        """启动时的静默更新检查（后台线程），离线等错误只记日志"""
        try:
            return fetch_latest_release()
        except (OSError, ValueError) as e:
            logger.debug(f"Update check failed: {e}")
            return None

    def _on_update_checked(self, release, error) -> None:
        """有新版本时在右下角显示提示"""
        if release and is_newer(release["tag_name"], VERSION) and release.get("html_url"):
            self.version_info.create_update_label(release["html_url"])

    def _check_theme(self) -> None:
        try:
            self.menubar.update_theme()
        except Exception as e:
            logger.debug(f"检查主题变化失败: {e}")
        self.root.after(THEME_CHECK_INTERVAL_MS, self._check_theme)

    def _current_tab(self) -> int:
        return self.notebook.index(self.notebook.select())

    # ---------- 选择目录 ----------

    def select_dir(self) -> None:
        dir_path = filedialog.askdirectory()
        if not dir_path:
            return
        if not dir_path.endswith(("/_storage", "\\_storage")):
            showwarning_relative(self.root, self.t("warning"), self.t("dir_warning"))
        self._load_storage_dir(dir_path)

    def auto_detect_steam(self) -> None:
        storage_path = auto_detect_storage()
        if storage_path:
            self._load_storage_dir(storage_path)
        else:
            showinfo_relative(self.root, self.t("warning"), self.t("steam_detect_not_found"))

    def _load_storage_dir(self, storage_dir: str) -> None:
        """切换到新的存档目录：重建 SF 分析页和截图页，其余标签页标记为待创建"""
        self.storage_dir = storage_dir
        for index in LAZY_TABS:
            self._teardown_lazy_tab(index)
        self._prewarmed_tyrano = None
        self._update_version_info_visibility()

        self.hint_labels[SCREENSHOT_TAB].pack_forget()
        if self.screenshot_manager_ui is None:
            self._run_safely("Create screenshot tab", self._create_screenshot_tab)
        else:
            self.screenshot_manager_ui.set_storage_dir(storage_dir)
            self._run_safely("Reload screenshots", self.screenshot_manager_ui.load_screenshots)

        self._clear_frame(SF_TAB)
        self.hint_labels[SF_TAB].pack_forget()
        self.save_analyzer = None
        self._run_safely("Create SF analyzer tab", self._create_sf_tab)

        self._pending_tabs = set(LAZY_TABS)
        self._restart_save_monitor()
        self._create_tab_if_pending(self._current_tab())
        self.root.after(TYRANO_PREWARM_DELAY_MS, self._prewarm_tyrano)

    def _create_screenshot_tab(self) -> None:
        self.screenshot_manager_ui = ScreenshotManagerUI(
            self.tab_frames[SCREENSHOT_TAB], self.root, self.storage_dir, self.t
        )

    def _create_sf_tab(self) -> None:
        self.save_analyzer = SaveAnalyzer(self.tab_frames[SF_TAB], self.storage_dir, self.t)

    def _clear_frame(self, index: int) -> None:
        """销毁标签页里的内容，保留提示标签和 CTkFrame 自己用来画背景的 canvas"""
        frame = self.tab_frames[index]
        keep = (self.hint_labels[index], getattr(frame, "_canvas", None))
        for widget in frame.winfo_children():
            if not any(widget is k for k in keep):
                widget.destroy()

    def _teardown_lazy_tab(self, index: int) -> None:
        """销毁已创建的懒加载标签页，下次切换过去时按当前目录重新创建

        否则再次选择目录后，旧页面会显示旧目录的数据，运行时修改页的状态轮询和热键也不会停止。
        """
        if index == BACKUP_TAB:
            self.backup_restore_tab = None
        elif index == TYRANO_TAB:
            if self.tyrano_tab is not None:
                self._run_safely("Clean up Tyrano tab", self.tyrano_tab.cleanup)
            self.tyrano_tab = None
        elif index == RUNTIME_TAB:
            if self.runtime_modify_tab is not None:
                # 换目录不应该关掉正在运行的游戏
                self._run_safely(
                    "Clean up runtime modify tab", lambda: self.runtime_modify_tab.cleanup(stop_game=False)
                )
            self.runtime_modify_tab = None
        elif index == OTHERS_TAB:
            self.others_tab = None
        self._clear_frame(index)
        self.hint_labels[index].pack(pady=50)
        self._pending_tabs.add(index)

    # ---------- 懒加载 ----------

    def on_tab_changed(self, event=None) -> None:
        index = self._current_tab()
        logger.debug(f"切换到标签页索引: {index}")
        created = self._create_tab_if_pending(index)
        if index == SF_TAB and self.save_analyzer is not None:
            self._run_safely("Refresh SF analyzer tab", self.save_analyzer.refresh)
        elif index == BACKUP_TAB and self.backup_restore_tab is not None and not created:
            self._run_safely("Refresh backup list", self.backup_restore_tab.refresh_backup_list)
        self._update_version_info_visibility()

    def _create_tab_if_pending(self, index: int) -> bool:
        """第一次切换到懒加载标签页时创建它；返回这次是否新建了"""
        if not self.storage_dir or index not in self._pending_tabs:
            return False
        self._pending_tabs.discard(index)
        self.hint_labels[index].pack_forget()
        create = {
            BACKUP_TAB: self._create_backup_tab,
            TYRANO_TAB: self._create_tyrano_tab,
            RUNTIME_TAB: self._create_runtime_tab,
            OTHERS_TAB: self._create_others_tab,
        }[index]
        self._run_safely(f"Create {TAB_TITLE_KEYS[index]}", create)
        return True

    def _create_backup_tab(self) -> None:
        self.backup_restore_tab = BackupRestoreTab(
            self.tab_frames[BACKUP_TAB], self.root, self.storage_dir, self.t,
            on_restore_start=self._on_restore_start, on_restore_done=self._on_restore_done,
        )

    def _create_tyrano_tab(self) -> None:
        analyzer = self._prewarmed_tyrano
        self._prewarmed_tyrano = None
        if analyzer is None:
            analyzer = TyranoAnalyzer(self.storage_dir)
            analyzer.load_save_file()
        self.tyrano_tab = TyranoSaveViewer(self.tab_frames[TYRANO_TAB], analyzer, self.t, self.root)

    def _create_runtime_tab(self) -> None:
        self.runtime_modify_tab = RuntimeModifyTab(self.tab_frames[RUNTIME_TAB], self.storage_dir, self.t, self.root)

    def _create_others_tab(self) -> None:
        self.others_tab = OthersTab(self.tab_frames[OTHERS_TAB], self)

    def _prewarm_tyrano(self) -> None:
        """在后台预读 Tyrano 存档，用户切到该页时就不用再等文件读取"""
        storage_dir = self.storage_dir
        if TYRANO_TAB not in self._pending_tabs or self._prewarmed_tyrano is not None:
            return

        def load() -> TyranoAnalyzer:
            analyzer = TyranoAnalyzer(storage_dir)
            analyzer.load_save_file()
            return analyzer

        def done(analyzer, error) -> None:
            # 预读期间用户可能换了目录或已经打开了该页，这时结果作废
            if error is None and storage_dir == self.storage_dir and TYRANO_TAB in self._pending_tabs:
                self._prewarmed_tyrano = analyzer

        run_in_background(self.root, load, done)

    # ---------- 还原备份 ----------

    def _on_restore_start(self) -> None:
        # 还原时 _storage 会被短暂改名，暂停监控以免误报「AB INITIO」
        if self.save_monitor:
            self.save_monitor.stop()

    def _on_restore_done(self, success: bool) -> None:
        self._restart_save_monitor()
        if not success:
            return
        # 存档文件已被替换：刷新已打开的页面，Tyrano 页丢弃旧数据重新创建
        if self.screenshot_manager_ui is not None:
            self._run_safely("Reload screenshots", self.screenshot_manager_ui.load_screenshots)
        if self.save_analyzer is not None:
            self._run_safely("Refresh SF analyzer tab", lambda: self.save_analyzer.refresh(force=True))
        self._prewarmed_tyrano = None
        if self.tyrano_tab is not None:
            self._teardown_lazy_tab(TYRANO_TAB)

    # ---------- 存档变动提示 ----------

    def set_toast_enabled(self, enabled: bool) -> None:
        self.toast_enabled = enabled
        self._restart_save_monitor()

    def set_toast_ignore_record(self, text: str) -> None:
        self.toast_ignore_record = text
        if self.save_monitor:
            self.save_monitor.ignored_vars = parse_ignored_vars(text)

    def _restart_save_monitor(self) -> None:
        """只有开启了 toast 时才监控存档"""
        if self.save_monitor:
            self.save_monitor.stop()
            self.save_monitor = None
        if self.toast_enabled and self.storage_dir:
            self.save_monitor = SaveChangeMonitor(
                self.root, self.storage_dir, parse_ignored_vars(self.toast_ignore_record),
                on_change=self.change_notifier.show, on_ab_initio=self._show_ab_initio,
            )
            self.save_monitor.start()

    def _show_ab_initio(self) -> None:
        """_storage 被整个删除时（游戏的「AB INITIO」）显示蓝色提示"""
        toast = Toast(self.root, "AB INITIO", duration=30000, fade_in=200, fade_out=200)
        # message_text 是底层的 tk.Text（CTkTextbox 的 tag 不能设置字体）
        text = toast.message_text
        text.config(state="normal")
        text.delete("1.0", "end")
        text.tag_configure("ab_initio_blue", foreground=Colors.TEXT_INFO_BRIGHT, font=get_cjk_font(12, "bold"))
        text.insert("1.0", "AB INITIO", "ab_initio_blue")
        text.config(state="disabled")

    # ---------- 语言 ----------

    def change_language(self, lang: str) -> None:
        if lang not in TRANSLATIONS:
            return
        self.language = lang
        self.menubar.update_language(lang)
        self.root.title(self.t("window_title"))
        self.version_info.update_text()
        for index, title_key in enumerate(TAB_TITLE_KEYS):
            self.notebook.tab(index, text=self.t(title_key))
        for label in self.hint_labels:
            label.configure(text=self.t("select_dir_hint"))

        # 每个标签页单独更新：某一页出错不影响其他页
        if self.screenshot_manager_ui is not None:
            self._run_safely("Update screenshot tab texts", self.screenshot_manager_ui.update_ui_texts)
            self._run_safely("Reload screenshots", self.screenshot_manager_ui.load_screenshots)
        if self.backup_restore_tab is not None:
            self._run_safely("Update backup tab texts", self.backup_restore_tab.update_ui_texts)
        if self.runtime_modify_tab is not None:
            self._run_safely("Update runtime modify tab texts", self.runtime_modify_tab.update_language)
        if self.others_tab is not None:
            self._run_safely("Update others tab texts", lambda: self.others_tab.update_language(lang))
        if self.save_analyzer is not None:
            self._run_safely("Update SF analyzer tab texts", self.save_analyzer.update_language)
        if self.tyrano_tab is not None:
            self._run_safely("Update Tyrano tab texts", self.tyrano_tab.update_ui_texts)

    # ---------- 其他 ----------

    def _update_version_info_visibility(self) -> None:
        """版本信息只在未选择目录时和「其他」页显示"""
        if self.storage_dir is None or self._current_tab() == OTHERS_TAB:
            self.version_info.show()
        else:
            self.version_info.hide()

    def on_closing(self) -> None:
        if self.save_monitor:
            self.save_monitor.stop()
        if self.tyrano_tab is not None:
            self._run_safely("Clean up Tyrano tab", self.tyrano_tab.cleanup)
        if self.runtime_modify_tab is not None:
            self._run_safely("Clean up runtime modify tab", self.runtime_modify_tab.cleanup)
        self.root.destroy()
