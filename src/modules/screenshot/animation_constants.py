"""「开启修改」复选框提示动画的参数（src/utils/hint_animation.py 和存档查看器也在用）"""

SHAKE_OFFSETS = [4, -4, 3, -3, 2, -2, 1, -1, 0]  # 左右抖动的偏移，逐渐减弱
SHAKE_STEP_DELAY_MS = 25
SHAKE_COLOR_RESTORE_DELAY_MS = 300

HINT_COLOR_ORANGE = "#FF6B35"

CHECKBOX_STYLE_NORMAL = "Screenshot.TCheckbutton"
CHECKBOX_STYLE_HINT = "ScreenshotHint.TCheckbutton"
