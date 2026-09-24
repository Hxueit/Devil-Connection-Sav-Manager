"""主窗口的菜单栏和右下角的版本信息"""
import logging
import platform
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from tkinter import Menu, ttk
from typing import Callable, Optional

from src.constants import LATEST_GAME_PATCH_AT_BUILD, VERSION
from src.utils.styles import Colors, get_cjk_font

logger = logging.getLogger(__name__)

LANGUAGE_OPTIONS = [("日本語", "ja_JP"), ("中文", "zh_CN"), ("English", "en_US")]

MENU_COLORS = {
    "light": {"bg": Colors.LIGHT_GRAY, "fg": Colors.TEXT_PRIMARY, "active_bg": Colors.ACCENT_PINK,
              "active_fg": Colors.WHITE},
    "dark": {"bg": "#2D2D2D", "fg": "#FFFFFF", "active_bg": "#3E3E3E", "active_fg": "#FFFFFF"},
}


def detect_windows_theme() -> str:
    """读取 Windows 的深色/浅色模式设置，其他系统一律返回 'light'"""
    if platform.system() != "Windows":
        return "light"
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if value == 1 else "dark"
    except (OSError, ImportError) as e:
        logger.debug(f"检测Windows主题失败: {e}")
        return "light"


class MenuBar:
    """顶部菜单：目录 / Language / Help，颜色跟随 Windows 深浅色主题"""

    MIN_SCALING = 1.25
    MIN_FONT_SIZE = 11

    def __init__(
        self,
        root: tk.Tk,
        t: Callable[[str], str],
        current_language: str,
        on_dir_browse: Callable[[], None],
        on_auto_detect: Callable[[], None],
        on_language_change: Callable[[str], None],
        on_help: Callable[[], None],
    ) -> None:
        self.root = root
        self.t = t
        self.theme = detect_windows_theme()

        # 高 DPI 屏幕上 Tk 默认的缩放偏小
        try:
            if float(root.tk.call("tk", "scaling")) < self.MIN_SCALING:
                root.tk.call("tk", "scaling", self.MIN_SCALING)
        except (tk.TclError, ValueError) as e:
            logger.debug(f"Error setting window scaling: {e}")
        self._apply_menu_options()

        self.menubar = Menu(root)
        root.config(menu=self.menubar)

        self.directory_menu = Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label=t("directory_menu"), menu=self.directory_menu)
        self.directory_menu_index = self.menubar.index("end")
        self.directory_menu.add_command(label=t("browse_dir"), command=on_dir_browse)
        self.directory_menu.add_command(label=t("auto_detect_steam"), command=on_auto_detect)

        self.language_menu = Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Language", menu=self.language_menu)
        self.language_var = tk.StringVar(value=current_language)
        for label, value in LANGUAGE_OPTIONS:
            self.language_menu.add_radiobutton(
                label=label, variable=self.language_var, value=value, command=lambda v=value: on_language_change(v)
            )

        self.help_menu = Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Help", menu=self.help_menu)
        self.help_menu.add_command(label="Help", command=on_help)

    def _apply_menu_options(self) -> None:
        """通过 option 数据库设置菜单的字体和颜色（对之后创建的菜单生效）"""
        base_size = 10
        try:
            base_size = tkfont.nametofont("TkMenuFont").cget("size")
        except tk.TclError:
            pass
        size = max(self.MIN_FONT_SIZE, int(round(base_size * self.MIN_SCALING)))
        family = "Microsoft YaHei UI" if platform.system() == "Windows" else "Arial"
        colors = MENU_COLORS[self.theme]
        options = {
            "*Menu.font": tkfont.Font(family=family, size=size, weight="normal"),
            "*Menu.background": colors["bg"],
            "*Menu.activeBackground": colors["active_bg"],
            "*Menu.activeForeground": colors["active_fg"],
            "*Menu.foreground": colors["fg"],
            "*Menu.borderWidth": 0,
            "*Menu.activeBorderWidth": 3,
            "*Menu.relief": "flat",
            "*Menu.padx": 8,
            "*Menu.pady": 4,
        }
        for option, value in options.items():
            self.root.option_add(option, value)

    def update_language(self, language: str) -> None:
        self.language_var.set(language)
        self.menubar.entryconfig(self.directory_menu_index, label=self.t("directory_menu"))
        self.directory_menu.entryconfig(0, label=self.t("browse_dir"))
        self.directory_menu.entryconfig(1, label=self.t("auto_detect_steam"))

    def update_theme(self) -> None:
        """系统主题改变时重新着色（主窗口每隔几秒调用一次）"""
        theme = detect_windows_theme()
        if theme == self.theme:
            return
        self.theme = theme
        self._apply_menu_options()
        colors = MENU_COLORS[theme]
        for menu in (self.menubar, self.directory_menu, self.language_menu, self.help_menu):
            try:
                menu.configure(
                    bg=colors["bg"], fg=colors["fg"],
                    activebackground=colors["active_bg"], activeforeground=colors["active_fg"],
                )
            except tk.TclError:
                logger.debug(f"更新菜单主题失败: {menu}")


class VersionInfo:
    """右下角的版本号；有新版本时在上方显示一个会轻轻抖动的「有更新」链接"""

    SHAKE_OFFSETS = [2, -2, 1, -1, 0, -1, 1, -2, 2, 0]
    SHAKE_STEP_MS = 50
    COLOR_BRIGHT = "#ff4d7a"
    COLOR_NORMAL = "#ff6b9d"

    def __init__(self, root: tk.Tk, t: Callable[[str], str]) -> None:
        self.root = root
        self.t = t
        self.update_label: Optional[ttk.Label] = None
        self.update_label_wrapper: Optional[tk.Frame] = None
        self._shake_job: Optional[str] = None
        self._shake_index = 0

        self.version_frame = tk.Frame(root, bg=Colors.LIGHT_GRAY)
        self.version_label = ttk.Label(
            self.version_frame, text=self._version_text(), style="Gray.TLabel",
            foreground=Colors.TEXT_MUTED, font=get_cjk_font(9),
        )
        self.version_label.pack(side="bottom", anchor="e")
        self.show()

    def _version_text(self) -> str:
        return self.t("version_info", version=VERSION, patch_date=LATEST_GAME_PATCH_AT_BUILD)

    def update_text(self) -> None:
        self.version_label.config(text=self._version_text())
        if self.update_label is not None:
            self.update_label.config(text=self.t("update_available_label"))

    def show(self) -> None:
        self.version_frame.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)
        self._start_shake()

    def hide(self) -> None:
        self.version_frame.place_forget()
        self._stop_shake()

    def create_update_label(self, release_url: str) -> None:
        """显示「有更新」链接，点击后在浏览器打开发布页"""
        if self.update_label is not None:
            return
        self.update_label_wrapper = tk.Frame(self.version_frame, bg=Colors.LIGHT_GRAY)
        self.update_label_wrapper.pack(side="bottom", anchor="e", pady=(0, 2))
        self.update_label = ttk.Label(
            self.update_label_wrapper, text=self.t("update_available_label"), style="Gray.TLabel",
            foreground=self.COLOR_NORMAL, font=get_cjk_font(11, "bold"), cursor="hand2",
        )
        self.update_label.pack()
        self.update_label.bind("<Button-1>", lambda e: webbrowser.open(release_url))
        self.update_label.bind("<Enter>", self._on_enter)
        self.update_label.bind("<Leave>", lambda e: self._start_shake())
        if self.version_frame.winfo_ismapped():
            self._start_shake()

    def _on_enter(self, event=None) -> None:
        self._stop_shake()
        self.update_label.configure(foreground=self.COLOR_BRIGHT)

    def _start_shake(self) -> None:
        if self._shake_job is None and self.update_label is not None:
            self._shake_index = 0
            self._shake_step()

    def _shake_step(self) -> None:
        offset = self.SHAKE_OFFSETS[self._shake_index]
        try:
            self.update_label_wrapper.pack_configure(padx=max(0, offset))
            self.update_label.configure(foreground=self.COLOR_BRIGHT if abs(offset) >= 2 else self.COLOR_NORMAL)
        except tk.TclError:
            self._shake_job = None
            return
        self._shake_index = (self._shake_index + 1) % len(self.SHAKE_OFFSETS)
        self._shake_job = self.root.after(self.SHAKE_STEP_MS, self._shake_step)

    def _stop_shake(self) -> None:
        if self._shake_job is not None:
            self.root.after_cancel(self._shake_job)
            self._shake_job = None
        if self.update_label is not None:
            try:
                self.update_label_wrapper.pack_configure(padx=0)
                self.update_label.configure(foreground=self.COLOR_NORMAL)
            except tk.TclError:
                pass
