""".sav 文件读写。文件内容是 URL 编码后的 JSON"""

import contextlib
import json
import os
import stat
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

PathLike = str | Path


def decode_sav(text: str) -> Any:
    return json.loads(urllib.parse.unquote(text.strip()))


def encode_sav(data: Any) -> str:
    """把 Python 对象编码成 .sav 文件的文本

    和游戏自己写入的格式完全一致：JSON.stringify（紧凑、不转义非 ASCII 字符）
    再 encodeURIComponent（除 A-Z a-z 0-9 - _ . ! ~ * ' ( ) 外都转义）。
    """
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return urllib.parse.quote(text, safe="!~*'()")


def read_sav(path: PathLike) -> Any:
    return decode_sav(Path(path).read_text(encoding="utf-8"))


def write_text_atomic(path: PathLike, text: str) -> None:
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
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def write_sav(path: PathLike, data: Any) -> None:
    write_text_atomic(path, encode_sav(data))
