"""备份文件操作：创建、扫描、还原、删除、重命名

备份是 _storage 文件夹的 zip 压缩包，放在 _storage 同级的 dcsm_backups 文件夹里。
压缩包内额外有一个 dcsmINFO.txt，第一行是创建时间，用于在列表中排序和显示。
这里的函数都不碰界面，可以在后台线程中调用；失败时抛出异常。
"""
import io
import logging
import os
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from src.constants import VERSION

logger = logging.getLogger(__name__)

BACKUP_DIR_NAME = "dcsm_backups"
BACKUP_INFO_FILENAME = "dcsmINFO.txt"
REQUIRED_SAVE_FILES = ["DevilConnection_sf.sav", "DevilConnection_tyrano_data.sav"]
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
COMPRESSION_LEVEL = 7


@dataclass
class BackupInfo:
    zip_path: Path
    timestamp: Optional[datetime]  # INFO 文件缺失或无法解析时为 None
    has_info: bool
    file_size: int


def get_backup_dir(storage_dir: Path) -> Path:
    return (Path(storage_dir).parent / BACKUP_DIR_NAME).resolve()


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{max(size_bytes, 0)} B"
    for unit in ("KB", "MB", "GB"):
        size_bytes /= 1024
        if size_bytes < 1024 or unit == "GB":
            return f"{size_bytes:.2f} {unit}"


def _list_files(storage_dir: Path) -> List[Path]:
    return sorted(p for p in Path(storage_dir).rglob("*") if p.is_file())


def estimate_compressed_size(storage_dir: Path) -> int:
    """压缩前 10% 的文件测出压缩率，再按总大小估算整个备份的大小"""
    files = [(p, p.stat().st_size) for p in _list_files(storage_dir)]
    if not files:
        return 0
    total_size = sum(size for _, size in files)
    sample = files[:max(1, len(files) // 10)]
    sample_size = sum(size for _, size in sample)
    if sample_size == 0:
        return int(total_size * 0.7)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=COMPRESSION_LEVEL) as zf:
        for path, _ in sample:
            zf.write(path, path.name)
    ratio = min(1.0, max(0.1, len(buffer.getvalue()) / sample_size))
    return int(total_size * ratio)


def create_backup(storage_dir: Path, progress: Optional[Callable[[int, int], None]] = None) -> Path:
    """把 _storage 打包成新的备份文件，返回备份路径

    先写到 .partial 临时文件，全部成功后才改名成 .zip，
    所以失败时不会在备份列表里留下残缺的压缩包。任何文件无法读取都算失败。
    progress(current, total) 会在后台线程中被调用。
    """
    storage_dir = Path(storage_dir)
    if not storage_dir.is_dir():
        raise FileNotFoundError(storage_dir)
    backup_dir = get_backup_dir(storage_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    stem = f"DC_storage_backup_{now:%Y%m%d_%H%M%S}"
    backup_path = backup_dir / f"{stem}.zip"
    counter = 1
    while backup_path.exists():  # 同一秒内再次备份时不覆盖已有的
        backup_path = backup_dir / f"{stem}_{counter}.zip"
        counter += 1

    info_text = (
        f"{now.strftime(TIMESTAMP_FORMAT)}\n"
        f"This backup .zip was created using https://github.com/Hxueit/Devil-Connection-Sav-Manager/\n"
        f"ver:{VERSION}\n"
    )
    files = _list_files(storage_dir)
    total = len(files) + 1
    partial_path = backup_path.with_name(backup_path.name + ".partial")
    try:
        with zipfile.ZipFile(partial_path, "w", zipfile.ZIP_DEFLATED, compresslevel=COMPRESSION_LEVEL) as zf:
            zf.writestr(BACKUP_INFO_FILENAME, info_text)
            if progress:
                progress(1, total)
            for index, path in enumerate(files, start=2):
                zf.write(path, path.relative_to(storage_dir))
                if progress:
                    progress(index, total)
        os.replace(partial_path, backup_path)
    except BaseException:
        try:
            partial_path.unlink()
        except OSError:
            pass
        raise
    return backup_path


def _read_backup_timestamp(zip_path: Path):
    """返回 (时间戳, 是否有 INFO 文件)"""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            if BACKUP_INFO_FILENAME not in zf.namelist():
                return None, False
            with zf.open(BACKUP_INFO_FILENAME) as f:
                first_line = f.readline().decode("utf-8").strip()
        return datetime.strptime(first_line, TIMESTAMP_FORMAT), True
    except ValueError:  # 时间格式不对 / 编码错误
        return None, True
    except (zipfile.BadZipFile, OSError) as e:
        logger.warning(f"无法读取备份文件: {zip_path}, 错误: {e}")
        return None, False


def scan_backups(backup_dir: Path) -> List[BackupInfo]:
    """列出备份：有时间戳的按时间倒序排在前面，其余排在后面"""
    backup_dir = Path(backup_dir)
    if not backup_dir.is_dir():
        return []
    dated, undated = [], []
    for zip_path in backup_dir.glob("*.zip"):
        if not zip_path.is_file():
            continue
        timestamp, has_info = _read_backup_timestamp(zip_path)
        info = BackupInfo(zip_path, timestamp, has_info, zip_path.stat().st_size)
        (dated if timestamp else undated).append(info)
    dated.sort(key=lambda b: b.timestamp, reverse=True)
    return dated + undated


def missing_required_files(zip_path: Path) -> List[str]:
    """返回备份中缺少的必需存档文件"""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
    except (zipfile.BadZipFile, OSError) as e:
        logger.error(f"无法打开zip文件: {zip_path}, 错误: {e}")
        return list(REQUIRED_SAVE_FILES)
    return [name for name in REQUIRED_SAVE_FILES if name not in names]


def restore_backup(zip_path: Path, storage_dir: Path) -> None:
    """用备份替换 _storage

    先校验并完整解压到同级临时目录，全部成功后再与 _storage 交换，
    任何一步失败都不会动到现有的 _storage。
    """
    storage_dir = Path(storage_dir)
    staging_dir = storage_dir.with_name(f".{storage_dir.name}.restoring")
    old_dir = storage_dir.with_name(f".{storage_dir.name}.old")

    try:
        with zipfile.ZipFile(zip_path) as zf:
            bad_member = zf.testzip()
            if bad_member is not None:
                raise zipfile.BadZipFile(f"Corrupted file in backup: {bad_member}")
            shutil.rmtree(staging_dir, ignore_errors=True)
            staging_dir.mkdir(parents=True)
            for member in zf.namelist():
                if member != BACKUP_INFO_FILENAME:
                    zf.extract(member, staging_dir)
    except BaseException:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    # Windows 下游戏正在运行、文件被占用时重命名会失败
    shutil.rmtree(old_dir, ignore_errors=True)
    try:
        if storage_dir.exists():
            storage_dir.rename(old_dir)
        try:
            staging_dir.rename(storage_dir)
        except OSError:
            if old_dir.exists():
                old_dir.rename(storage_dir)
            raise
    except OSError:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    shutil.rmtree(old_dir, ignore_errors=True)


def delete_backup(zip_path: Path) -> None:
    """删除备份；备份文件夹空了就一并删除"""
    zip_path = Path(zip_path)
    zip_path.unlink()
    try:
        zip_path.parent.rmdir()  # 只有空文件夹才会删除成功
    except OSError:
        pass


def rename_backup(zip_path: Path, new_name: str) -> Path:
    """重命名备份（自动补 .zip），返回新路径"""
    zip_path = Path(zip_path)
    if not new_name.endswith(".zip"):
        new_name += ".zip"
    new_path = zip_path.with_name(new_name)
    if new_path.exists() and new_path != zip_path:
        raise FileExistsError(new_path)
    zip_path.rename(new_path)
    return new_path
