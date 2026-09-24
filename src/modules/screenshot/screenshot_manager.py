"""截图文件的读写

游戏把每张截图存成两个文件：
    DevilConnection_photo_<id>.sav        主图（PNG 的 data URI）
    DevilConnection_photo_<id>_thumb.sav  缩略图（JPEG 的 data URI）
另有两个索引文件决定画廊里有哪些截图、按什么顺序显示：
    DevilConnection_photo_ids.sav         [{"id": ..., "date": ...}, ...]
    DevilConnection_photo_all_ids.sav     [id, ...]

写入顺序保证索引永远不会指向不存在的文件：
    新增/替换：先写图片文件，最后写索引
    删除：先写索引，再删图片文件（删不掉的文件只是游戏不再引用的孤儿文件）
"""

import logging
import random
import string
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image

from src.modules.screenshot.image_processor import bytes_to_data_uri, data_uri_to_bytes
from src.utils.sav_io import read_sav, write_sav

logger = logging.getLogger(__name__)

DATE_FORMAT = '%Y/%m/%d %H:%M:%S'
FILE_PREFIX = 'DevilConnection_photo_'
FILE_SUFFIX = '.sav'
THUMB_SUFFIX = '_thumb'
IDS_FILENAME = 'DevilConnection_photo_ids.sav'
ALL_IDS_FILENAME = 'DevilConnection_photo_all_ids.sav'
DEFAULT_THUMB_SIZE = (1280, 960)
THUMB_QUALITY = 90


def parse_screenshot_filename(filename: str) -> Optional[Tuple[str, bool]]:
    """从文件名解析出 (截图ID, 是否缩略图)，不是截图文件时返回 None"""
    if not (filename.startswith(FILE_PREFIX) and filename.endswith(FILE_SUFFIX)) or filename == IDS_FILENAME:
        return None
    parts = filename[:-len(FILE_SUFFIX)].split('_')
    if len(parts) == 3:
        return parts[2], False
    if len(parts) == 4 and parts[3] == 'thumb':
        return parts[2], True
    return None


def encode_main_image(image_bytes: bytes) -> str:
    """把任意格式的图片转成游戏主图用的 PNG data URI

    游戏按 image/png 读取主图，所以 JPG/WEBP/GIF 等要先转成真正的 PNG；
    本来就是 PNG（包括 APNG）的直接使用原始字节。
    """
    with Image.open(BytesIO(image_bytes)) as img:
        if img.format == "PNG":
            return bytes_to_data_uri(image_bytes, "image/png")
        if img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
            img = img.convert("RGBA")
        buffer = BytesIO()
        img.save(buffer, "PNG")
    return bytes_to_data_uri(buffer.getvalue(), "image/png")


def encode_thumbnail(image_bytes: bytes, size: Tuple[int, int]) -> str:
    """生成缩略图的 JPEG data URI"""
    with Image.open(BytesIO(image_bytes)) as img:
        thumb = img.resize(size, Image.Resampling.BILINEAR).convert('RGB')
    buffer = BytesIO()
    thumb.save(buffer, 'JPEG', quality=THUMB_QUALITY, optimize=True)
    return bytes_to_data_uri(buffer.getvalue(), "image/jpeg")


def generate_id() -> str:
    """生成 8 位随机 ID（小写字母+数字）"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))


def current_datetime() -> str:
    return datetime.now().strftime(DATE_FORMAT)


def is_valid_date(date_string: str) -> bool:
    try:
        datetime.strptime(date_string, DATE_FORMAT)
        return True
    except ValueError:
        return False


class ScreenshotManager:
    """截图索引和图片文件的管理（不涉及界面）"""

    def __init__(self, storage_dir: Optional[str] = None,
                 t_func: Optional[Callable[..., str]] = None) -> None:
        self.storage_dir: Optional[Path] = Path(storage_dir) if storage_dir else None
        self.ids_data: List[Dict[str, str]] = []
        self.all_ids_data: List[str] = []
        # {截图ID: [主文件名, 缩略图文件名]}，缺失的文件为 None
        self.sav_pairs: Dict[str, List[Optional[str]]] = {}
        self.t = t_func or (lambda key, **kwargs: key.format(**kwargs) if kwargs else key)

    def set_storage_dir(self, storage_dir: Optional[str]) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir else None

    # ---------- 读取 ----------

    def _scan_files(self) -> None:
        """扫描存储目录，重建 sav_pairs"""
        self.sav_pairs = {}
        if not self.storage_dir or not self.storage_dir.is_dir():
            return
        try:
            for file_path in self.storage_dir.iterdir():
                parsed = parse_screenshot_filename(file_path.name)
                if parsed and file_path.is_file():
                    screenshot_id, is_thumb = parsed
                    pair = self.sav_pairs.setdefault(screenshot_id, [None, None])
                    pair[1 if is_thumb else 0] = file_path.name
        except OSError as e:
            logger.error(f"Failed to scan directory {self.storage_dir}: {e}")
            self.sav_pairs = {}

    def load_screenshots(self) -> bool:
        """读取两个索引文件并扫描图片文件，缺少索引文件或读取失败时返回 False"""
        if not self.storage_dir:
            return False
        ids_path = self.storage_dir / IDS_FILENAME
        all_ids_path = self.storage_dir / ALL_IDS_FILENAME
        if not (ids_path.exists() and all_ids_path.exists()):
            return False
        try:
            ids_data = read_sav(ids_path)
            all_ids_data = read_sav(all_ids_path)
        except (OSError, ValueError) as e:
            logger.error(f"Failed to load screenshots: {e}", exc_info=True)
            return False
        # ids.sav 应是 [{"id": ..., "date": ...}, ...]，all_ids.sav 应是 id 列表；格式不对就当作读取失败
        if not (isinstance(ids_data, list) and isinstance(all_ids_data, list)
                and all(isinstance(item, dict) and isinstance(item.get("id"), str) for item in ids_data)):
            logger.error("Unexpected screenshot index format in %s", self.storage_dir)
            return False
        self.ids_data = ids_data
        self.all_ids_data = all_ids_data
        self._scan_files()
        return True

    def file_path(self, screenshot_id: str, thumb: bool = False) -> Optional[Path]:
        """截图文件的路径；文件不存在时返回 None"""
        pair = self.sav_pairs.get(screenshot_id)
        name = pair and pair[1 if thumb else 0]
        if not name or not self.storage_dir:
            return None
        return self.storage_dir / name

    def get_image_data(self, screenshot_id: str) -> Optional[bytes]:
        """读取主图的图片字节，失败时返回 None"""
        path = self.file_path(screenshot_id)
        return read_image_file(path) if path else None

    # ---------- 写入 ----------

    def _save_index(self) -> None:
        """写入两个索引文件（失败时抛出 OSError）"""
        write_sav(self.storage_dir / IDS_FILENAME, self.ids_data)
        write_sav(self.storage_dir / ALL_IDS_FILENAME, self.all_ids_data)

    def _replace_index(self, ids_data: List[Dict[str, str]], all_ids_data: Optional[List[str]] = None) -> None:
        """保存新的索引内容；写入失败时内存中的索引保持不变并抛出 OSError

        all_ids_data 省略时按 ids_data 的顺序重建。
        """
        old = self.ids_data, self.all_ids_data
        self.ids_data = ids_data
        self.all_ids_data = [item['id'] for item in ids_data] if all_ids_data is None else all_ids_data
        try:
            self._save_index()
        except OSError:
            self.ids_data, self.all_ids_data = old
            raise

    def sort_by_date(self, ascending: bool = True) -> None:
        """按日期排序并保存

        Raises:
            ValueError/KeyError: 有截图的日期格式不对
            OSError: 保存失败
        """
        self._replace_index(sorted(
            self.ids_data,
            key=lambda item: datetime.strptime(item['date'], DATE_FORMAT),
            reverse=not ascending,
        ))

    def move_item(self, from_index: int, to_index: int) -> None:
        """把一张截图移动到新位置并保存（保存失败时抛出 OSError）"""
        if from_index == to_index:
            return
        if not (0 <= from_index < len(self.ids_data) and 0 <= to_index < len(self.ids_data)):
            logger.warning(f"Invalid indices: from={from_index}, to={to_index}, total={len(self.ids_data)}")
            return
        new_order = list(self.ids_data)
        new_order.insert(to_index, new_order.pop(from_index))
        self._replace_index(new_order)

    def _write_image_files(self, screenshot_id: str, image_path: Path,
                           thumb_size: Tuple[int, int]) -> List[Path]:
        """把图片编码后写成主图和缩略图两个文件，返回写入的路径"""
        image_bytes = image_path.read_bytes()
        # 两个文件都编码成功后再写，避免只写了一半
        main_uri = encode_main_image(image_bytes)
        thumb_uri = encode_thumbnail(image_bytes, thumb_size)
        main_path = self.storage_dir / f'{FILE_PREFIX}{screenshot_id}{FILE_SUFFIX}'
        thumb_path = self.storage_dir / f'{FILE_PREFIX}{screenshot_id}{THUMB_SUFFIX}{FILE_SUFFIX}'
        write_sav(main_path, main_uri)
        write_sav(thumb_path, thumb_uri)
        self.sav_pairs[screenshot_id] = [main_path.name, thumb_path.name]
        return [main_path, thumb_path]

    def add_screenshot(self, screenshot_id: str, date_string: str, image_path: str) -> Tuple[bool, str]:
        """新增截图，返回 (是否成功, 提示消息)"""
        if screenshot_id in self.sav_pairs:
            return False, self.t("id_exists")
        if not self.storage_dir:
            return False, self.t("storage_dir_not_set")
        image_path_obj = Path(image_path)
        if not image_path_obj.exists():
            return False, self.t("file_not_exist")

        try:
            written = self._write_image_files(screenshot_id, image_path_obj, self._existing_thumb_size())
        except (OSError, ValueError) as e:  # PIL 的 UnidentifiedImageError 是 OSError 的子类
            logger.error(f"Failed to add screenshot: {e}", exc_info=True)
            return False, self.t("file_operation_failed", error=str(e))

        self.ids_data.append({"id": screenshot_id, "date": date_string})
        self.all_ids_data.append(screenshot_id)
        try:
            self._save_index()
        except OSError as e:
            logger.error(f"Failed to save screenshot index: {e}", exc_info=True)
            self.ids_data.pop()
            self.all_ids_data.pop()
            self.sav_pairs.pop(screenshot_id, None)
            for path in written:
                path.unlink(missing_ok=True)
            return False, self.t("save_failed", error=str(e))
        return True, self.t("success")

    def replace_screenshot(self, screenshot_id: str, new_image_path: str) -> Tuple[bool, str]:
        """用新图片替换已有截图（沿用原缩略图的尺寸），返回 (是否成功, 提示消息)"""
        main_path = self.file_path(screenshot_id)
        thumb_path = self.file_path(screenshot_id, thumb=True)
        if screenshot_id not in self.sav_pairs:
            return False, self.t("screenshot_not_exist")
        if not main_path or not thumb_path:
            return False, self.t("file_missing")
        new_path = Path(new_image_path)
        if not new_path.exists():
            return False, self.t("file_not_exist")

        try:
            self._write_image_files(screenshot_id, new_path, thumb_image_size(thumb_path) or DEFAULT_THUMB_SIZE)
        except (OSError, ValueError) as e:
            logger.error(f"Failed to replace screenshot: {e}", exc_info=True)
            return False, self.t("file_operation_failed", error=str(e))
        return True, self.t("success")

    def delete_screenshots(self, screenshot_ids: List[str]) -> List[str]:
        """从索引中移除截图并删除文件

        Returns:
            删除失败的文件名列表（这些文件已不在索引里，游戏不会再用到）
        Raises:
            OSError: 索引保存失败，此时什么都没有改变
        """
        to_delete = set(screenshot_ids)
        self._replace_index(
            [item for item in self.ids_data if item['id'] not in to_delete],
            [item_id for item_id in self.all_ids_data if item_id not in to_delete],
        )

        failed: List[str] = []
        for screenshot_id in screenshot_ids:
            for name in self.sav_pairs.pop(screenshot_id, [None, None]):
                if not name:
                    continue
                try:
                    (self.storage_dir / name).unlink(missing_ok=True)
                except OSError as e:
                    logger.warning(f"Failed to delete {name}: {e}")
                    failed.append(name)
        return failed

    def _existing_thumb_size(self) -> Tuple[int, int]:
        """新截图的缩略图尺寸与已有的缩略图保持一致"""
        for screenshot_id in self.sav_pairs:
            thumb_path = self.file_path(screenshot_id, thumb=True)
            size = thumb_image_size(thumb_path) if thumb_path else None
            if size:
                return size
        return DEFAULT_THUMB_SIZE


def read_image_file(sav_path: Path) -> Optional[bytes]:
    """读取截图 .sav 文件里的图片字节，失败时返回 None"""
    try:
        return data_uri_to_bytes(read_sav(sav_path))
    except (OSError, ValueError) as e:
        logger.debug(f"Failed to read image from {sav_path}: {e}")
        return None


def thumb_image_size(thumb_path: Path) -> Optional[Tuple[int, int]]:
    """读取缩略图文件的图片尺寸（只解析文件头，不解码像素）"""
    data = read_image_file(thumb_path)
    if not data:
        return None
    try:
        with Image.open(BytesIO(data)) as img:
            return img.size
    except OSError:
        return None
