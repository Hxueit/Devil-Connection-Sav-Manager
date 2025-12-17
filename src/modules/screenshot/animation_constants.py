"""动画相关常量定义

定义提示动画的参数和配置。
"""

# 抖动动画配置
SHAKE_OFFSETS = [4, -4, 3, -3, 2, -2, 1, -1, 0]  # 抖动序列：逐渐减弱
SHAKE_STEP_DELAY_MS = 25  # 每步间隔（毫秒）
SHAKE_COLOR_RESTORE_DELAY_MS = 300  # 颜色恢复延迟（毫秒）

# 提示颜色
HINT_COLOR_ORANGE = "#FF6B35"  # 红橙色

# 样式名称
CHECKBOX_STYLE_NORMAL = "Screenshot.TCheckbutton"
CHECKBOX_STYLE_HINT = "ScreenshotHint.TCheckbutton"

