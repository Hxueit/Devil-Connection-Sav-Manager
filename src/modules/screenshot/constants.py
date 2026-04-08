"""截图模块常量定义"""

PREVIEW_WIDTH = 240
PREVIEW_HEIGHT = 180

GALLERY_SIZE_PRESETS = [
    {
        'image_size': (150, 112),
        'window_size': '800x600',
        'placeholder_size': (150, 112)
    },
    {
        'image_size': (175, 131),
        'window_size': '900x675',
        'placeholder_size': (175, 131)
    },
    {
        'image_size': (200, 150),
        'window_size': '1000x750',
        'placeholder_size': (200, 150)
    },
    {
        'image_size': (250, 187),
        'window_size': '1200x900',
        'placeholder_size': (250, 187)
    },
    {
        'image_size': (300, 225),
        'window_size': '1400x1050',
        'placeholder_size': (300, 225)
    }
]

GALLERY_ROWS_PER_PAGE = 3
GALLERY_COLS_PER_PAGE = 4
GALLERY_IMAGES_PER_PAGE = GALLERY_ROWS_PER_PAGE * GALLERY_COLS_PER_PAGE

VALID_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.apng', '.tiff', '.tif', '.ico'}

# 画廊刷新操作类型
GALLERY_OPERATION_ADD = "add"
GALLERY_OPERATION_REPLACE = "replace"
GALLERY_OPERATION_DELETE = "delete"

