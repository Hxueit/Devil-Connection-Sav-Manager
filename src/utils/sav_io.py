""".sav 文件读写

游戏的 .sav 是 URL 编码后的 JSON 文本。写入时先写到同目录的临时文件，
再用 os.replace 原子替换，避免写到一半崩溃/断电时留下被截断的存档。
"""

import json
import os
import stat
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any, Union


def encode_sav(data: Any) -> str:
    """把数据编码为 .sav 文本"""
    return urllib.parse.quote(json.dumps(data, ensure_ascii=False))


def write_text_atomic(path: Union[str, Path], text: str) -> None:
    """原子地写入文本文件：要么完整写入新内容，要么保持原文件不变"""
    path = Path(path)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            # mkstemp 创建的文件权限是 0600，沿用原文件的权限
            os.chmod(tmp_path, stat.S_IMODE(path.stat().st_mode))
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_sav(path: Union[str, Path], data: Any) -> None:
    """编码并原子地写入 .sav 文件"""
    write_text_atomic(path, encode_sav(data))
