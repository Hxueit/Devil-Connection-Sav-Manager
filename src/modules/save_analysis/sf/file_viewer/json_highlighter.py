"""JSON语法高亮模块

提供JSON文本的语法高亮功能
"""

import re
import tkinter as tk

from src.utils.styles import Colors, get_mono_font


def apply_json_syntax_highlight(text_widget: tk.Text, content: str) -> None:
    """应用JSON语法高亮
    
    优化：使用单次遍历替代多次正则匹配，提高性能
    
    Args:
        text_widget: 文本widget
        content: 要高亮的JSON内容
    """
    # 清除所有标签
    for tag in ['string', 'keyword', 'number', 'bracket', 'punctuation']:
        text_widget.tag_remove(tag, "1.0", "end")
    
    mono_font = get_mono_font(10)
    
    # 配置标签样式
    text_widget.tag_config('string', foreground='#008000', font=mono_font)
    text_widget.tag_config('keyword', foreground='#0000FF', font=mono_font)
    text_widget.tag_config('number', foreground='#FF0000', font=mono_font)
    text_widget.tag_config('bracket', foreground='#000000', font=(mono_font[0], mono_font[1], "bold"))
    text_widget.tag_config('punctuation', foreground=Colors.TEXT_MUTED, font=mono_font)
    
    # 单次遍历所有模式
    patterns = [
        (r'"[^"]*"', 'string'),
        (r'\b(true|false|null)\b', 'keyword'),
        (r'\b\d+\.?\d*\b', 'number'),
        (r'[{}[\]]', 'bracket'),
        (r'[:,]', 'punctuation'),
    ]
    
    lines = content.split('\n')
    for line_num, line in enumerate(lines, start=1):
        for pattern, tag_name in patterns:
            for match in re.finditer(pattern, line):
                start_pos = f"{line_num}.{match.start()}"
                end_pos = f"{line_num}.{match.end()}"
                text_widget.tag_add(tag_name, start_pos, end_pos)




