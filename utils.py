"""工具函数模块"""
import os


def set_window_icon(window):
    """设置窗口图标"""
    try:
        # 获取脚本所在目录
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, "icon.ico")
        if os.path.exists(icon_path):
            window.iconbitmap(icon_path)
    except Exception:
        # 如果设置图标失败，忽略错误
        pass

