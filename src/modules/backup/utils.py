"""
备份模块的工具函数

提供文件大小格式化等通用工具函数
"""


def format_size(size_bytes: int) -> str:
    """
    格式化文件大小为可读格式
    
    Args:
        size_bytes: 文件大小（字节）
        
    Returns:
        格式化后的字符串（如 "1.5 MB"）
    """
    if size_bytes < 0:
        return "0 B"
    
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

