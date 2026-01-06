"""主窗口模块"""
import logging
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, ttk
from typing import List, Optional

import customtkinter as ctk

from src.modules.backup.backup_restore_ui import BackupRestoreTab
from src.modules.main.change_notifier import ChangeNotifier
from src.modules.main.file_monitor import FileMonitor
from src.modules.main.language_service import LanguageService
from src.modules.main.save_data_comparator import SaveDataComparator
from src.modules.main.save_file_service import SaveFileService
from src.modules.main.steam_detector import SteamDetector
from src.modules.main.ui_components import MenuBar, VersionInfo
from src.modules.main.update_checker import UpdateChecker
from src.modules.others.tab import OthersTab
from src.modules.runtime_modify.tab import RuntimeModifyTab
from src.modules.save_analysis.sf.analyzer import SaveAnalyzer
from src.modules.save_analysis.tyrano.analyzer import TyranoAnalyzer
from src.modules.save_analysis.tyrano.save_viewer import TyranoSaveViewer
from src.modules.screenshot import ScreenshotManagerUI
from src.utils.loading_animation import LoadingAnimationController
from src.utils.styles import Colors, get_cjk_font, init_styles
from src.utils.toast import Toast
from src.utils.translations import TRANSLATIONS
from src.utils.ui_utils import (
    set_window_icon,
    showerror_relative,
    showinfo_relative,
    showwarning_relative,
)

logger = logging.getLogger(__name__)


class SavTool:
    """存档管理工具主窗口类（重构版）"""
    
    def __init__(self, root):
        """初始化主窗口
        
        Args:
            root: Tkinter根窗口对象
        """
        self.root = root
        self.translations = TRANSLATIONS
        
        # 初始化服务
        self.language_service = LanguageService(self.translations)
        self.update_checker = UpdateChecker()
        self.steam_detector = SteamDetector()
        self.save_file_service = SaveFileService()
        self.data_comparator = SaveDataComparator("record, initialVars")
        # change_notifier 将在 _initialize_components 中初始化，因为需要 self.t
        self.change_notifier: Optional[ChangeNotifier] = None
        
        # 初始化UI组件
        self.menubar_component: Optional[MenuBar] = None
        self.version_info_component: Optional[VersionInfo] = None
        
        # 初始化窗口
        self.root.title(self.t("window_title"))
        self.root.geometry("850x600")
        self.root.minsize(750, 600)
        
        set_window_icon(self.root)
        self.style = init_styles(self.root)
        
        if hasattr(self.root, 'configure'):
            try:
                self.root.configure(bg=Colors.LIGHT_GRAY)
            except (tk.TclError, AttributeError) as e:
                logger.debug(f"Error configuring root background: {e}")
        
        # 创建UI
        self._create_menubar()
        self._create_main_interface()
        self._initialize_components()
        self._create_version_info()
        self._bind_events()
        self.notebook.select(0)
        self._check_for_updates_on_startup()
    
    def t(self, key: str, **kwargs) -> str:
        """翻译函数，支持格式化字符串
        
        Args:
            key: 翻译键
            **kwargs: 格式化参数
            
        Returns:
            翻译后的文本
        """
        return self.language_service.translate(key, **kwargs)
    
    def _create_menubar(self) -> None:
        """创建菜单栏"""
        language_options = self.language_service.get_supported_languages()
        
        self.menubar_component = MenuBar(
            self.root,
            self.t,
            language_options,
            self.language_service.current_language,
            self.select_dir,
            self.auto_detect_steam,
            self.change_language,
            self.show_help
        )
    
    def _create_main_interface(self) -> None:
        """创建主界面"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)
        
        tab_configs = [
            ("sf_save_analyzer_tab", "analyzer_frame", "analyzer_hint_label"),
            ("screenshot_management_tab", "screenshot_frame", "screenshot_hint_label"),
            ("backup_restore_tab", "backup_restore_frame", "backup_restore_hint_label"),
            ("tyrano_save_management_tab", "tyrano_frame", "tyrano_hint_label"),
            ("runtime_modify_tab", "runtime_modify_frame", "runtime_modify_hint_label"),
            ("others_tab", "others_frame", "others_hint_label")
        ]
        
        for tab_text, frame_attr, hint_attr in tab_configs:
            frame = ctk.CTkFrame(self.notebook, fg_color=Colors.LIGHT_GRAY)
            self.notebook.add(frame, text=self.t(tab_text))
            setattr(self, frame_attr, frame)
            
            hint_label = ctk.CTkLabel(
                frame,
                text=self.t("select_dir_hint"),
                text_color=Colors.TEXT_HINT,
                font=get_cjk_font(12, "bold"),
                fg_color="transparent"
            )
            hint_label.pack(pady=50)
            setattr(self, hint_attr, hint_label)
    
    def _initialize_components(self) -> None:
        """初始化组件状态"""
        self.save_analyzer: Optional[SaveAnalyzer] = None
        self.tyrano_tab: Optional[TyranoSaveViewer] = None
        self.backup_restore_tab: Optional[BackupRestoreTab] = None
        self.runtime_modify_tab: Optional[RuntimeModifyTab] = None
        self.others_tab: Optional[OthersTab] = None
        self.screenshot_manager_ui: Optional[ScreenshotManagerUI] = None
        
        self.storage_dir: Optional[str] = None
        self.file_monitor: Optional[FileMonitor] = None
        
        self.toast_enabled: bool = False
        self.toast_ignore_record: str = "record, initialVars"
        
        # 初始化变更通知器（需要 self.t）
        self.change_notifier = ChangeNotifier(self.root, self.t)
        
        # 初始化加载动画控制器
        self.loading_animation = LoadingAnimationController(self.root, interval_ms=500)
        self.loading_animation.set_translate_func(self.t)
        
        # 加载状态管理
        self._is_loading = False
        self._cancel_loading = False
    
    def _create_version_info(self) -> None:
        """创建右下角版本信息标签"""
        self.version_info_component = VersionInfo(self.root, self.t)
    
    def _check_for_updates_on_startup(self) -> None:
        """启动时自动检测更新"""
        def on_update_check(has_update: bool, latest_version: Optional[str], release_url: Optional[str]):
            if has_update and release_url:
                self.version_info_component.create_update_label(release_url)
                if self._should_show_version_info():
                    self.version_info_component.show_update_label()
        
        self.update_checker.check_for_updates_async(on_update_check)
    
    def _bind_events(self) -> None:
        """绑定事件"""
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def change_language(self, lang: str) -> None:
        """切换语言
        
        Args:
            lang: 语言代码
        """
        if not self.language_service.change_language(lang):
            return
        
        if self.menubar_component:
            self.menubar_component.update_language(lang)
        
        try:
            self.update_ui_texts()
        except Exception as e:
            logger.error(f"Language switch error: {e}", exc_info=True)
        
        if self.save_analyzer is not None:
            try:
                self.save_analyzer.current_language = lang
                self.save_analyzer.refresh()
            except Exception as e:
                logger.error(f"Save analyzer language update error: {e}", exc_info=True)
        
        if self.tyrano_tab is not None:
            try:
                self.tyrano_tab.update_ui_texts()
            except Exception as e:
                logger.error(f"Tyrano tab language update error: {e}", exc_info=True)
    
    def update_toast_ignore_record(self, ignore_record: str) -> None:
        """更新toast忽略变量列表
        
        Args:
            ignore_record: 忽略变量列表（逗号分隔）
        """
        self.toast_ignore_record = ignore_record
        if self.data_comparator:
            self.data_comparator.set_ignored_vars(ignore_record)
    
    def init_save_analyzer(self) -> None:
        """初始化存档分析界面"""
        if not self.storage_dir:
            return
        
        # 检查是否取消加载
        if self._cancel_loading:
            return
        
        for widget in self.analyzer_frame.winfo_children():
            widget.destroy()
        
        # 检查是否取消加载
        if self._cancel_loading:
            return
        
        self.save_analyzer = SaveAnalyzer(
            self.analyzer_frame, 
            self.storage_dir, 
            self.translations, 
            self.language_service.current_language
        )
    
    def init_tyrano_tab(self) -> None:
        """初始化tyrano存档管理标签页"""
        if not self.storage_dir:
            return
        
        # 检查是否取消加载
        if self._cancel_loading:
            return
        
        # 清理旧的标签页实例（如果存在）
        if self.tyrano_tab is not None:
            try:
                self.tyrano_tab.cleanup()
            except Exception as e:
                logger.debug(f"清理旧的tyrano标签页时出错: {e}")
        
        # 检查是否取消加载
        if self._cancel_loading:
            return
        
        # 隐藏提示标签
        self.tyrano_hint_label.pack_forget()
        for widget in self.tyrano_frame.winfo_children():
            widget.destroy()
        
        # 检查是否取消加载
        if self._cancel_loading:
            return
        
        # 创建分析器
        analyzer = TyranoAnalyzer(self.storage_dir)
        
        # 检查是否取消加载（在文件读取前）
        if self._cancel_loading:
            return
        
        if not analyzer.load_save_file():
            # 检查是否取消加载（文件读取后）
            if self._cancel_loading:
                return
            # 加载失败，显示错误信息
            error_label = ctk.CTkLabel(
                self.tyrano_frame,
                text=self.t("tyrano_load_failed"),
                text_color=Colors.TEXT_SECONDARY,
                font=get_cjk_font(12),
                fg_color="transparent"
            )
            error_label.pack(pady=50)
            self.tyrano_tab = None
            return
        
        # 检查是否取消加载（文件读取成功后）
        if self._cancel_loading:
            return
        
        # 创建查看器
        self.tyrano_tab = TyranoSaveViewer(
            self.tyrano_frame,
            analyzer,
            self.t,
            get_cjk_font,
            Colors,
            self.root
        )
    
    def init_runtime_modify(self) -> None:
        """初始化运行时修改标签页"""
        if not self.storage_dir:
            return
        
        # 检查是否取消加载
        if self._cancel_loading:
            return
        
        # 清理旧的标签页实例（如果存在）
        if self.runtime_modify_tab is not None:
            try:
                self.runtime_modify_tab.cleanup()
            except Exception as e:
                logger.debug(f"清理旧的运行时修改标签页时出错: {e}")
        
        # 检查是否取消加载
        if self._cancel_loading:
            return
        
        self.runtime_modify_hint_label.pack_forget()
        for widget in self.runtime_modify_frame.winfo_children():
            widget.destroy()
        
        # 检查是否取消加载
        if self._cancel_loading:
            return
        
        self.runtime_modify_tab = RuntimeModifyTab(
            self.runtime_modify_frame,
            self.storage_dir,
            self.translations,
            self.language_service.current_language,
            self.root
        )
    
    def init_others_tab(self) -> None:
        """初始化其他功能标签页"""
        if not self.storage_dir:
            return
        
        # 检查是否取消加载
        if self._cancel_loading:
            return
        
        self.others_hint_label.pack_forget()
        for widget in self.others_frame.winfo_children():
            widget.destroy()
        
        # 检查是否取消加载
        if self._cancel_loading:
            return
        
        self.others_tab = OthersTab(
            self.others_frame, 
            self.storage_dir, 
            self.translations, 
            self.language_service.current_language, 
            self
        )
    
    def init_backup_restore(self) -> None:
        """初始化备份/还原界面"""
        if not self.storage_dir:
            return
        
        # 检查是否取消加载
        if self._cancel_loading:
            return
        
        # 定义还原成功后的回调函数
        def on_restore_success():
            """还原成功后的回调，刷新其他组件"""
            if self.storage_dir:
                if self.screenshot_manager_ui is not None:
                    self.screenshot_manager_ui.load_screenshots()
                if self.save_analyzer:
                    self.save_analyzer.refresh()
        
        # 检查是否取消加载
        if self._cancel_loading:
            return
        
        self.backup_restore_tab = BackupRestoreTab(
            self.backup_restore_frame,
            self.root,
            self.storage_dir,
            self.translations,
            self.language_service.current_language,
            self.t,
            on_restore_success
        )
    
    def on_tab_changed(self, event=None) -> None:
        """处理 tab 切换事件"""
        if not hasattr(self, 'notebook') or not self.notebook:
            return
        
        try:
            current_tab = self.notebook.index(self.notebook.select())
            
            # 可选调试输出
            try:
                from src.modules.save_analysis.sf.debug import get_debugger
                debugger = get_debugger()
                if debugger:
                    debugger.log_tab_change(current_tab)
            except ImportError:
                pass
            
            if current_tab == 0 and self.save_analyzer is not None:
                try:
                    from src.modules.save_analysis.sf.debug import get_debugger
                    debugger = get_debugger()
                    if debugger:
                        debugger.log_tab_refresh_start()
                except ImportError:
                    pass
                
                try:
                    self.save_analyzer.refresh()
                    try:
                        from src.modules.save_analysis.sf.debug import get_debugger
                        debugger = get_debugger()
                        if debugger:
                            debugger.log_refresh_complete()
                    except ImportError:
                        pass
                except Exception as e:
                    try:
                        from src.modules.save_analysis.sf.debug import get_debugger
                        debugger = get_debugger()
                        if debugger:
                            debugger.log_tab_refresh_error(e)
                    except ImportError:
                        pass
            elif current_tab == 0 and self.save_analyzer is None:
                try:
                    from src.modules.save_analysis.sf.debug import get_debugger
                    debugger = get_debugger()
                    if debugger:
                        debugger.log_tab_warning("切换到存档分析页面，但 save_analyzer 为 None")
                except ImportError:
                    pass
            elif current_tab == 2 and self.backup_restore_tab is not None:
                self.backup_restore_tab.refresh_backup_list()
            elif current_tab == 4:
                # 运行时修改标签页
                pass
            
            self._update_version_info_visibility()
        except (tk.TclError, AttributeError, ValueError) as e:
            logger.debug(f"Error in tab changed handler: {e}")
    
    def _start_file_monitor(self) -> None:
        """启动存档文件监控"""
        if not self.storage_dir:
            return
        
        if self.file_monitor:
            self.file_monitor.stop()
        
        self.save_file_service.set_storage_dir(self.storage_dir)
        self.data_comparator.set_ignored_vars(self.toast_ignore_record)
        
        def on_change(changes: List[str]) -> None:
            if self.toast_enabled and self.change_notifier:
                self.root.after(0, lambda: self.change_notifier.show_change_notification(changes))
        
        def on_ab_initio() -> None:
            self.root.after(0, self._trigger_ab_initio)
        
        self.file_monitor = FileMonitor(
            self.storage_dir,
            self.save_file_service,
            self.data_comparator,
            on_change,
            on_ab_initio
        )
        self.file_monitor.start()
    
    def _trigger_ab_initio(self) -> None:
        """触发AB INITIO事件：显示蓝色toast"""
        toast_message = "AB INITIO"
        toast = Toast(
            self.root,
            toast_message,
            duration=30000,
            fade_in=200,
            fade_out=200
        )
        toast.message_text.config(state="normal")
        toast.message_text.delete("1.0", "end")
        toast.message_text.tag_configure(
            "ab_initio_blue", 
            foreground=Colors.TEXT_INFO_BRIGHT, 
            font=get_cjk_font(12, "bold")
        )
        toast.message_text.insert("1.0", toast_message, "ab_initio_blue")
        toast.message_text.config(state="disabled")
    
    def on_closing(self) -> None:
        """窗口关闭事件处理"""
        # 如果正在加载，请求取消并等待完成
        if self._is_loading:
            logger.info("窗口关闭请求：正在加载中，请求取消加载")
            self._cancel_loading = True
            
            # 等待加载完成，最多等待3秒
            timeout = 3.0
            start_time = time.time()
            while self._is_loading and (time.time() - start_time) < timeout:
                self.root.update_idletasks()
                time.sleep(0.1)
            
            if self._is_loading:
                logger.warning("窗口关闭：加载操作超时，强制关闭")
            else:
                logger.info("窗口关闭：加载操作已取消")
        
        # 停止加载动画
        if hasattr(self, 'loading_animation'):
            self.loading_animation.stop()
        # 停止文件监控
        if self.file_monitor:
            self.file_monitor.stop()
        # 清理tyrano标签页
        if hasattr(self, 'tyrano_tab') and self.tyrano_tab:
            try:
                self.tyrano_tab.cleanup()
            except Exception as e:
                logger.debug(f"清理tyrano标签页时出错: {e}")
        # 清理运行时修改标签页（关闭游戏进程和定时任务）
        if hasattr(self, 'runtime_modify_tab') and self.runtime_modify_tab:
            try:
                self.runtime_modify_tab.cleanup()
            except Exception as e:
                logger.debug(f"清理运行时修改标签页时出错: {e}")
        self.root.destroy()
    
    def show_save_analyzer(self) -> None:
        """切换到存档分析 tab"""
        if not self.storage_dir:
            showerror_relative(self.root, self.t("error"), self.t("select_dir_hint"))
            return
        
        if self.save_analyzer is None:
            self.init_save_analyzer()
        self.notebook.select(0)
    
    def show_help(self) -> None:
        """浏览器打开GitHub页面"""
        webbrowser.open("https://github.com/Hxueit/Devil-Connection-Sav-Manager")
    
    def update_ui_texts(self) -> None:
        """更新所有UI文本"""
        self.root.title(self.t("window_title"))
        
        if self.version_info_component:
            self.version_info_component.update_text()
        
        if hasattr(self, 'notebook') and self.notebook:
            try:
                self.notebook.tab(0, text=self.t("sf_save_analyzer_tab"))
                self.notebook.tab(1, text=self.t("screenshot_management_tab"))
                self.notebook.tab(2, text=self.t("backup_restore_tab"))
                self.notebook.tab(3, text=self.t("tyrano_save_management_tab"))
                self.notebook.tab(4, text=self.t("runtime_modify_tab"))
                self.notebook.tab(5, text=self.t("others_tab"))
            except (tk.TclError, IndexError):
                pass
        
        if hasattr(self, 'analyzer_hint_label') and self.analyzer_hint_label:
            if self.analyzer_hint_label.winfo_exists():
                self.analyzer_hint_label.configure(text=self.t("select_dir_hint"))
        
        if hasattr(self, 'screenshot_hint_label') and self.screenshot_hint_label:
            if self.screenshot_hint_label.winfo_exists():
                self.screenshot_hint_label.configure(text=self.t("select_dir_hint"))
        
        if hasattr(self, 'backup_restore_hint_label') and self.backup_restore_hint_label:
            if self.backup_restore_hint_label.winfo_exists():
                self.backup_restore_hint_label.configure(text=self.t("select_dir_hint"))
        
        if hasattr(self, 'tyrano_hint_label') and self.tyrano_hint_label:
            if self.tyrano_hint_label.winfo_exists():
                self.tyrano_hint_label.configure(text=self.t("select_dir_hint"))
        
        if hasattr(self, 'runtime_modify_hint_label') and self.runtime_modify_hint_label:
            if self.runtime_modify_hint_label.winfo_exists():
                self.runtime_modify_hint_label.configure(text=self.t("select_dir_hint"))
        
        if hasattr(self, 'others_hint_label') and self.others_hint_label:
            if self.others_hint_label.winfo_exists():
                self.others_hint_label.configure(text=self.t("select_dir_hint"))
        
        if self.screenshot_manager_ui is not None:
            self.screenshot_manager_ui.update_ui_texts()
        
        if self.backup_restore_tab is not None:
            self.backup_restore_tab.update_ui_texts()
        
        if self.storage_dir and self.screenshot_manager_ui is not None:
            self.screenshot_manager_ui.load_screenshots()
        
        if self.runtime_modify_tab is not None:
            self.runtime_modify_tab.update_language(self.language_service.current_language)
        
        if self.runtime_modify_tab is not None:
            self.runtime_modify_tab.update_language(self.language_service.current_language)
        
        if self.others_tab is not None:
            self.others_tab.update_language(self.language_service.current_language)
        
        if self.backup_restore_tab is not None:
            self.backup_restore_tab.update_language(self.language_service.current_language)
    
    def _should_show_version_info(self) -> bool:
        """判断是否应该显示版本信息"""
        if self.storage_dir is None:
            return True
        
        if hasattr(self, 'notebook') and self.notebook:
            try:
                current_tab = self.notebook.index(self.notebook.select())
                return current_tab == 5
            except (tk.TclError, AttributeError, ValueError):
                return False
        return False
    
    def _update_version_info_visibility(self) -> None:
        """更新版本信息标签的显示/隐藏状态"""
        should_show = self._should_show_version_info()
        
        if self.version_info_component:
            if should_show:
                self.version_info_component.show()
            else:
                self.version_info_component.hide()
    
    def _update_all_hint_labels_loading(self) -> None:
        """更新所有提示标签为"加载中..."状态，并启动动态动画"""
        hint_labels = []
        hint_label_attrs = [
            'analyzer_hint_label',
            'screenshot_hint_label',
            'backup_restore_hint_label',
            'tyrano_hint_label',
            'runtime_modify_hint_label',
            'others_hint_label'
        ]
        
        # 收集所有有效的标签
        for label_attr in hint_label_attrs:
            if hasattr(self, label_attr):
                label = getattr(self, label_attr)
                if label and label.winfo_exists():
                    # 确保标签可见
                    label.pack(pady=50)
                    hint_labels.append(label)
        
        # 启动动画
        if hint_labels:
            self.loading_animation.start(hint_labels)
    
    def select_dir(self) -> None:
        """选择目录"""
        dir_path = filedialog.askdirectory()
        if dir_path:
            if not (dir_path.endswith('/_storage') or dir_path.endswith('\\_storage')):
                showwarning_relative(self.root, self.t("warning"), self.t("dir_warning"))
            self.storage_dir = dir_path
            # 设置加载状态
            self._is_loading = True
            self._cancel_loading = False
            try:
                # 在开始加载前，更新所有提示标签为"加载中..."
                self._update_all_hint_labels_loading()
                self._update_version_info_visibility()
                self.screenshot_hint_label.pack_forget()
                if self.screenshot_manager_ui is None:
                    self.screenshot_manager_ui = ScreenshotManagerUI(
                        self.screenshot_frame, 
                        self.root, 
                        self.storage_dir,
                        self.translations, 
                        self.language_service.current_language, 
                        self.t
                    )
                else:
                    self.screenshot_manager_ui.set_storage_dir(self.storage_dir)
                    self.screenshot_manager_ui.load_screenshots()
                
                # 检查是否取消加载
                if self._cancel_loading:
                    return
                
                self.init_save_analyzer()
                
                # 检查是否取消加载
                if self._cancel_loading:
                    return
                
                self.init_tyrano_tab()
                
                # 检查是否取消加载
                if self._cancel_loading:
                    return
                
                self.init_backup_restore()
                
                # 检查是否取消加载
                if self._cancel_loading:
                    return
                
                self.init_runtime_modify()
                
                # 检查是否取消加载
                if self._cancel_loading:
                    return
                
                self.init_others_tab()
                
                # 检查是否取消加载
                if self._cancel_loading:
                    return
                
                self._start_file_monitor()
            finally:
                # 加载完成后停止动画并清除加载状态
                self.loading_animation.stop()
                self._is_loading = False
    
    def auto_detect_steam(self) -> None:
        """自动检测Steam游戏目录并设置"""
        storage_path = self.steam_detector.auto_detect_storage()
        
        if storage_path:
            self.storage_dir = storage_path
            # 设置加载状态
            self._is_loading = True
            self._cancel_loading = False
            try:
                # 在开始加载前，更新所有提示标签为"加载中..."
                self._update_all_hint_labels_loading()
                self._update_version_info_visibility()
                self.screenshot_hint_label.pack_forget()
                if self.screenshot_manager_ui is None:
                    self.screenshot_manager_ui = ScreenshotManagerUI(
                        self.screenshot_frame, 
                        self.root, 
                        self.storage_dir,
                        self.translations, 
                        self.language_service.current_language, 
                        self.t
                    )
                else:
                    self.screenshot_manager_ui.set_storage_dir(self.storage_dir)
                    self.screenshot_manager_ui.load_screenshots(silent=True)
                
                # 检查是否取消加载
                if self._cancel_loading:
                    return
                
                self.init_save_analyzer()
                
                # 检查是否取消加载
                if self._cancel_loading:
                    return
                
                self.init_tyrano_tab()
                
                # 检查是否取消加载
                if self._cancel_loading:
                    return
                
                self.init_backup_restore()
                
                # 检查是否取消加载
                if self._cancel_loading:
                    return
                
                self.init_runtime_modify()
                
                # 检查是否取消加载
                if self._cancel_loading:
                    return
                
                self.init_others_tab()
                
                # 检查是否取消加载
                if self._cancel_loading:
                    return
                
                self._start_file_monitor()
            finally:
                # 加载完成后停止动画并清除加载状态
                self.loading_animation.stop()
                self._is_loading = False
        else:
            showinfo_relative(self.root, self.t("warning"), self.t("steam_detect_not_found"))


if __name__ == "__main__":
    root = ctk.CTk()
    app = SavTool(root)
    root.mainloop()

