"""tyrano 存档（DevilConnection_tyrano_data.sav 等）的读写

供 Tyrano 存档管理、运行时修改等模块使用。
"""
from pathlib import Path
from typing import Any, Dict, Union

from src.utils.sav_io import read_sav, write_sav


class TyranoService:
    def load_tyrano_save_file(self, tyrano_path: Union[str, Path]) -> Any:
        """读取并解码 tyrano 存档

        Raises:
            OSError: 文件不存在或无法读取
            ValueError: 内容不是合法的存档
        """
        return read_sav(tyrano_path)

    def save_tyrano_save_file(self, tyrano_path: Union[str, Path], save_data: Dict[str, Any]) -> None:
        """编码并原子地写入 tyrano 存档"""
        if not save_data:
            raise ValueError("Save data cannot be empty")
        Path(tyrano_path).parent.mkdir(parents=True, exist_ok=True)
        write_sav(tyrano_path, save_data)
