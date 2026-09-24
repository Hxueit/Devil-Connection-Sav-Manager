"""UI组件模块

负责创建菜单栏、版本信息等UI组件。
"""
import logging
import tkinter as tk
from tkinter import Menu
import tkinter.font as tkfont
import platform
from typing import Callable, Optional

from src.utils.styles import Colors, get_cjk_font
from src.constants import VERSION, LATEST_GAME_PATCH_AT_BUILD

logger = logging.getLogger(__name__)


def detect_windows_theme() -> str:
    """检测Windows系统主题模式
    
    Returns:
        'light' 或 'dark'，检测失败时返回 'light'
    """
    if platform.system() != "Windows":
        return 'light'
    
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize'
        ) as key:
            value, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
            return 'light' if value == 1 else 'dark'
    except (FileNotFoundError, OSError, ValueError, ImportError) as e:
        logger.debug(f"检测Windows主题失败: {e}")
        return 'light'


class MenuBar:
    """菜单栏组件类"""
    
    MIN_SCALING = 1.25
    MIN_FONT_SIZE = 11
    
    DARK_MENU_BG = "#2D2D2D"
    DARK_MENU_FG = "#FFFFFF"
    DARK_MENU_ACTIVE_BG = "#3E3E3E"
    DARK_MENU_ACTIVE_FG = "#FFFFFF"
    
    LIGHT_MENU_BG = Colors.LIGHT_GRAY
    LIGHT_MENU_FG = Colors.TEXT_PRIMARY
    LIGHT_MENU_ACTIVE_BG = Colors.ACCENT_PINK
    LIGHT_MENU_ACTIVE_FG = Colors.WHITE
    
    def __init__(self, root: tk.Tk, translate_func: Callable[[str], str], 
                 language_options: list[tuple[str, str]], 
                 current_language: str,
                 on_dir_browse: Callable[[], None],
                 on_auto_detect: Callable[[], None],
                 on_language_change: Callable[[str], None],
                 on_help: Callable[[], None]):
        """初始化菜单栏
        
        Args:
            root: Tkinter根窗口
            translate_func: 翻译函数
            language_options: 语言选项列表
            current_language: 当前语言
            on_dir_browse: 浏览目录回调
            on_auto_detect: 自动检测回调
            on_language_change: 语言切换回调
            on_help: 帮助回调
        """
        self.root = root
        self.translate = translate_func
        self.language_options = language_options
        self.current_language = current_language
        self.on_dir_browse = on_dir_browse
        self.on_auto_detect = on_auto_detect
        self.on_language_change = on_language_change
        self.on_help = on_help
        
        self.current_theme = detect_windows_theme()
        
        self._setup_scaling()
        self._setup_menu_font()
        self._create_menubar()
    
    def _setup_scaling(self) -> None:
        """设置窗口缩放"""
        if not hasattr(self.root, 'tk'):
            return
        
        try:
            current_scaling = float(self.root.tk.call("tk", "scaling"))
            if current_scaling < self.MIN_SCALING:
                self.root.tk.call("tk", "scaling", self.MIN_SCALING)
        except (tk.TclError, ValueError, AttributeError) as e:
            logger.debug(f"Error setting window scaling: {e}")
    
    def _setup_menu_font(self) -> None:
        """设置菜单字体和颜色"""
        base_size = 10
        try:
            base_menu_font = tkfont.nametofont("TkMenuFont")
            base_size = base_menu_font.cget("size")
        except (tk.TclError, AttributeError):
            pass
        
        scaled_size = max(self.MIN_FONT_SIZE, int(round(base_size * self.MIN_SCALING)))
        font_family = "Microsoft YaHei UI" if platform.system() == "Windows" else "Arial"
        
        try:
            menu_font = tkfont.Font(family=font_family, size=scaled_size, weight="normal")
            menu_colors = self._get_theme_colors()
            
            menu_options = {
                "*Menu.font": menu_font,
                "*Menu.background": menu_colors['bg'],
                "*Menu.activeBackground": menu_colors['active_bg'],
                "*Menu.activeForeground": menu_colors['active_fg'],
                "*Menu.foreground": menu_colors['fg'],
                "*Menu.borderWidth": 0,
                "*Menu.activeBorderWidth": 3,
                "*Menu.relief": "flat",
                "*Menu.padx": 8,
                "*Menu.pady": 4
            }
            
            for option, value in menu_options.items():
                self.root.option_add(option, value)
        except (tk.TclError, AttributeError) as e:
            logger.warning(f"设置菜单字体失败: {e}")
    
    def _get_theme_colors(self) -> dict[str, str]:
        """获取当前主题的颜色配置
        
        Returns:
            包含bg、fg、active_bg、active_fg的字典
        """
        if self.current_theme == 'dark':
            return {
                'bg': self.DARK_MENU_BG,
                'fg': self.DARK_MENU_FG,
                'active_bg': self.DARK_MENU_ACTIVE_BG,
                'active_fg': self.DARK_MENU_ACTIVE_FG
            }
        return {
            'bg': self.LIGHT_MENU_BG,
            'fg': self.LIGHT_MENU_FG,
            'active_bg': self.LIGHT_MENU_ACTIVE_BG,
            'active_fg': self.LIGHT_MENU_ACTIVE_FG
        }
    
    def _create_menubar(self) -> None:
        """创建菜单栏"""
        self.menubar = Menu(self.root)
        self.root.config(menu=self.menubar)
        
        self.directory_menu = Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label=self.translate("directory_menu"), menu=self.directory_menu)
        self.directory_menu.add_command(label=self.translate("browse_dir"), command=self.on_dir_browse)
        self.directory_menu.add_command(label=self.translate("auto_detect_steam"), command=self.on_auto_detect)
        
        self.language_menu = Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Language", menu=self.language_menu)
        self.language_var = tk.StringVar(value=self.current_language)
        
        for label, value in self.language_options:
            self.language_menu.add_radiobutton(
                label=label,
                variable=self.language_var,
                value=value,
                command=lambda v=value: self.on_language_change(v)
            )
        
        self.help_menu = Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Help", menu=self.help_menu)
        self.help_menu.add_command(label="Help", command=self.on_help)
    
    def update_language(self, new_language: str) -> None:
        """更新语言
        
        Args:
            new_language: 新语言代码
        """
        self.current_language = new_language
        self.language_var.set(new_language)
        
        self.directory_menu.delete(0, tk.END)
        self.directory_menu.add_command(label=self.translate("browse_dir"), command=self.on_dir_browse)
        self.directory_menu.add_command(label=self.translate("auto_detect_steam"), command=self.on_auto_detect)
        
        self._reorder_directory_menu()
    
    def _reorder_directory_menu(self) -> None:
        """重新排序目录菜单到首位"""
        if not hasattr(self, 'menubar') or not self.menubar:
            return
        
        directory_menu_str = str(self.directory_menu)
        indices_to_delete = []
        
        try:
            menu_count = self.menubar.index(tk.END)
            if menu_count is not None:
                for i in range(menu_count + 1):
                    try:
                        menu_obj = self.menubar.entrycget(i, "menu")
                        if str(menu_obj) == directory_menu_str:
                            indices_to_delete.append(i)
                    except (tk.TclError, IndexError):
                        continue
        except (tk.TclError, AttributeError):
            pass
        
        for idx in sorted(indices_to_delete, reverse=True):
            try:
                self.menubar.delete(idx)
            except (tk.TclError, IndexError):
                pass
        
        try:
            self.menubar.insert_cascade(0, label=self.translate("directory_menu"), menu=self.directory_menu)
        except (tk.TclError, IndexError):
            try:
                self.menubar.entryconfig(0, label=self.translate("directory_menu"))
            except (tk.TclError, IndexError):
                pass
    
    def update_theme(self) -> None:
        """更新菜单主题"""
        new_theme = detect_windows_theme()
        if new_theme == self.current_theme:
            return
        
        self.current_theme = new_theme
        self._setup_menu_font()
        self._apply_theme_to_menus()
    
    def _apply_theme_to_menus(self) -> None:
        """将当前主题应用到所有菜单"""
        menu_colors = self._get_theme_colors()
        menus_to_update = [
            getattr(self, 'menubar', None),
            getattr(self, 'directory_menu', None),
            getattr(self, 'language_menu', None),
            getattr(self, 'help_menu', None)
        ]
        
        for menu in menus_to_update:
            if menu and self._is_menu_valid(menu):
                try:
                    menu.configure(
                        bg=menu_colors['bg'],
                        fg=menu_colors['fg'],
                        activebackground=menu_colors['active_bg'],
                        activeforeground=menu_colors['active_fg']
                    )
                except tk.TclError:
                    logger.debug(f"更新菜单主题失败: {menu}")
    
    def _is_menu_valid(self, menu: Menu) -> bool:
        """检查菜单是否有效
        
        Args:
            menu: 要检查的菜单对象
            
        Returns:
            如果菜单有效返回True，否则返回False
        """
        try:
            return menu.winfo_exists()
        except (tk.TclError, AttributeError):
            return False


class VersionInfo:
    """版本信息组件类"""
    
    _GENTLE_SHAKE_OFFSETS = [2, -2, 1, -1, 0, -1, 1, -2, 2, 0]
    _SHAKE_STEP_DELAY_MS = 50
    _SHAKE_COLOR_BRIGHT = "#ff4d7a"
    _SHAKE_COLOR_NORMAL = "#ff6b9d"
    
    def __init__(self, root: tk.Tk, translate_func: Callable[[str], str]):
        """初始化版本信息组件
        
        Args:
            root: Tkinter根窗口
            translate_func: 翻译函数
        """
        self.root = root
        self.translate = translate_func
        self.update_label: Optional[tk.Label] = None
        self.update_label_wrapper: Optional[tk.Frame] = None
        self._shake_animation_job: Optional[str] = None
        self._shake_index = 0
        self._original_padx = 0
        
        self._create_version_frame()
    
    def _create_version_frame(self) -> None:
        """创建版本信息框架"""
        self.version_frame = tk.Frame(self.root, bg=Colors.LIGHT_GRAY)
        self.version_frame.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)
        
        version_text = self.translate("version_info").replace("[VERSION]", VERSION).replace(
            "[LATEST_GAME_PATCH_AT_BUILD]", LATEST_GAME_PATCH_AT_BUILD
        )
        
        from tkinter import ttk
        self.version_info_label = ttk.Label(
            self.version_frame,
            text=version_text,
            style="Gray.TLabel",
            foreground=Colors.TEXT_MUTED,
            font=get_cjk_font(9)
        )
        self.version_info_label.pack(side="bottom", anchor="e")
    
    def update_text(self) -> None:
        """更新版本信息文本"""
        version_text = self.translate("version_info").replace("[VERSION]", VERSION).replace(
            "[LATEST_GAME_PATCH_AT_BUILD]", LATEST_GAME_PATCH_AT_BUILD
        )
        self.version_info_label.config(text=version_text)
        
        if self.update_label and self._is_widget_valid(self.update_label):
            update_text = self.translate("update_available_label")
            self.update_label.config(text=update_text)
    
    def show(self) -> None:
        """显示版本信息"""
        self.version_frame.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)
    
    def hide(self) -> None:
        """隐藏版本信息"""
        self.version_frame.place_forget()
        if self.update_label_wrapper and self.update_label_wrapper.winfo_viewable():
            self.update_label_wrapper.pack_forget()
        self._stop_shake_animation()
    
    def create_update_label(self, release_url: str) -> None:
        """创建更新提示标签
        
        Args:
            release_url: 发布页面URL
        """
        if self.update_label is not None:
            return
        
        import webbrowser
        from tkinter import ttk
        
        update_text = self.translate("update_available_label")
        update_color = self._SHAKE_COLOR_NORMAL
        
        self.update_label_wrapper = tk.Frame(self.version_frame, bg=Colors.LIGHT_GRAY)
        self.update_label_wrapper.pack(side="bottom", anchor="e", pady=(0, 2))
        self._original_padx = 0
        
        self.update_label = ttk.Label(
            self.update_label_wrapper,
            text=update_text,
            style="Gray.TLabel",
            foreground=update_color,
            font=get_cjk_font(11, "bold"),
            cursor="hand2"
        )
        self.update_label.pack()
        
        def on_update_click(event):
            webbrowser.open(release_url)
        
        self.update_label.bind("<Button-1>", on_update_click)
        
        def on_enter(event):
            self._stop_shake_animation()
            self.update_label.configure(foreground=self._SHAKE_COLOR_BRIGHT)
        
        def on_leave(event):
            self.update_label.configure(foreground=update_color)
            self._start_shake_animation()
        
        self.update_label.bind("<Enter>", on_enter)
        self.update_label.bind("<Leave>", on_leave)
        
        self._start_shake_animation()
    
    def show_update_label(self) -> None:
        """显示更新标签"""
        if self.update_label_wrapper and not self.update_label_wrapper.winfo_viewable():
            self.update_label_wrapper.pack(side="bottom", anchor="e", pady=(0, 2))
            self._start_shake_animation()
    
    def hide_update_label(self) -> None:
        """隐藏更新标签"""
        if self.update_label_wrapper and self.update_label_wrapper.winfo_viewable():
            self.update_label_wrapper.pack_forget()
        self._stop_shake_animation()
    
    def _start_shake_animation(self) -> None:
        """启动抖动动画"""
        if self._shake_animation_job is not None:
            return
        
        if not self.update_label_wrapper or not self.update_label:
            return
        
        if not self._is_widget_valid(self.update_label_wrapper):
            return
        
        self._shake_index = 0
        self._shake_step()
    
    def _shake_step(self) -> None:
        """执行一帧抖动动画"""
        if (not self.update_label_wrapper or 
            not self.update_label or
            not self._is_widget_valid(self.update_label_wrapper)):
            self._shake_animation_job = None
            return
        
        offset = self._GENTLE_SHAKE_OFFSETS[self._shake_index]
        new_padx = max(0, self._original_padx + offset)
        
        try:
            self.update_label_wrapper.pack_configure(padx=new_padx)
        except tk.TclError:
            self._shake_animation_job = None
            return
        
        color = self._SHAKE_COLOR_BRIGHT if abs(offset) >= 2 else self._SHAKE_COLOR_NORMAL
        if self._is_widget_valid(self.update_label):
            try:
                self.update_label.configure(foreground=color)
            except tk.TclError:
                pass
        
        self._shake_index = (self._shake_index + 1) % len(self._GENTLE_SHAKE_OFFSETS)
        
        try:
            self._shake_animation_job = self.root.after(
                self._SHAKE_STEP_DELAY_MS,
                self._shake_step
            )
        except (tk.TclError, AttributeError):
            self._shake_animation_job = None
    
    def _is_widget_valid(self, widget: tk.Widget) -> bool:
        """检查组件是否有效
        
        Args:
            widget: 要检查的组件
            
        Returns:
            如果组件有效返回True，否则返回False
        """
        try:
            return widget.winfo_exists()
        except (tk.TclError, AttributeError):
            return False
    
    def _stop_shake_animation(self) -> None:
        """停止抖动动画"""
        if self._shake_animation_job is not None:
            try:
                self.root.after_cancel(self._shake_animation_job)
            except (tk.TclError, ValueError):
                pass
            self._shake_animation_job = None
        
        if self.update_label_wrapper and self._is_widget_valid(self.update_label_wrapper):
            try:
                self.update_label_wrapper.pack_configure(padx=self._original_padx)
            except tk.TclError:
                pass
        
        if self.update_label and self._is_widget_valid(self.update_label):
            try:
                self.update_label.configure(foreground=self._SHAKE_COLOR_NORMAL)
            except tk.TclError:
                pass

