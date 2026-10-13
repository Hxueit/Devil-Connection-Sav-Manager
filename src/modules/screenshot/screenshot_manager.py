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

from PIL import Image

from src.utils.images import bytes_to_data_uri, data_uri_to_bytes
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


def parse_screenshot_filename(filename: str) -> tuple[str, bool] | None:
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


def encode_thumbnail(image_bytes: bytes, size: tuple[int, int]) -> str:
    with Image.open(BytesIO(image_bytes)) as img:
        thumb = img.resize(size, Image.Resampling.BILINEAR).convert('RGB')
    buffer = BytesIO()
    thumb.save(buffer, 'JPEG', quality=THUMB_QUALITY, optimize=True)
    return bytes_to_data_uri(buffer.getvalue(), "image/jpeg")


def generate_id() -> str:
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))


def current_datetime() -> str:
    return datetime.now().strftime(DATE_FORMAT)


def is_valid_date(date_string: str) -> bool:
    try:
        datetime.strptime(date_string, DATE_FORMAT)
        return True
    except ValueError:
        return False


class ScreenshotError(Exception):
    """key 是翻译键（如 "id_exists"），detail 对应翻译文字里的 {error}"""

    def __init__(self, key: str, detail: str = "") -> None:
        super().__init__(f"{key}: {detail}" if detail else key)
        self.key = key
        self.detail = detail


class ScreenshotManager:

    def __init__(self, storage_dir: str | None = None) -> None:
        self.storage_dir: Path | None = Path(storage_dir) if storage_dir else None
        self.ids_data: list[dict[str, str]] = []
        self.all_ids_data: list[str] = []
        # {截图ID: [主文件名, 缩略图文件名]}，缺失的文件为 None
        self.sav_pairs: dict[str, list[str | None]] = {}


    def load_screenshots(self) -> bool:
        """缺少索引文件或读取失败时返回 False"""
        ids_path = self.storage_dir / IDS_FILENAME
        all_ids_path = self.storage_dir / ALL_IDS_FILENAME
        if not (ids_path.exists() and all_ids_path.exists()):
            return False
        try:
            ids_data = read_sav(ids_path)
            all_ids_data = read_sav(all_ids_path)
            file_names = [path.name for path in self.storage_dir.iterdir() if path.is_file()]
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
        self.sav_pairs = {}
        for name in file_names:
            parsed = parse_screenshot_filename(name)
            if parsed:
                screenshot_id, is_thumb = parsed
                self.sav_pairs.setdefault(screenshot_id, [None, None])[1 if is_thumb else 0] = name
        return True

    def file_path(self, screenshot_id: str, thumb: bool = False) -> Path | None:
        pair = self.sav_pairs.get(screenshot_id)
        name = pair and pair[1 if thumb else 0]
        return self.storage_dir / name if name else None

    def get_image_data(self, screenshot_id: str) -> bytes | None:
        path = self.file_path(screenshot_id)
        return read_image_file(path) if path else None


    def _replace_index(self, ids_data: list[dict[str, str]], all_ids_data: list[str] | None = None) -> None:
        """写入失败时内存中的索引不变；all_ids_data 省略时按 ids_data 的顺序重建"""
        if all_ids_data is None:
            all_ids_data = [item['id'] for item in ids_data]
        write_sav(self.storage_dir / IDS_FILENAME, ids_data)
        write_sav(self.storage_dir / ALL_IDS_FILENAME, all_ids_data)
        self.ids_data, self.all_ids_data = ids_data, all_ids_data

    def sort_by_date(self, ascending: bool = True) -> None:
        self._replace_index(sorted(
            self.ids_data,
            key=lambda item: datetime.strptime(item['date'], DATE_FORMAT),
            reverse=not ascending,
        ))

    def move_item(self, from_index: int, to_index: int) -> None:
        new_order = list(self.ids_data)
        new_order.insert(to_index, new_order.pop(from_index))
        self._replace_index(new_order)

    def _write_image_files(self, screenshot_id: str, image_path: Path,
                           thumb_size: tuple[int, int]) -> list[Path]:
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

    def add_screenshot(self, screenshot_id: str, date_string: str, image_path: str) -> None:
        """失败时抛出 ScreenshotError，索引和文件都保持原样"""
        if screenshot_id in self.sav_pairs:
            raise ScreenshotError("id_exists")
        if not self.storage_dir:
            raise ScreenshotError("storage_dir_not_set")
        try:
            written = self._write_image_files(screenshot_id, Path(image_path), self._existing_thumb_size())
        except (OSError, ValueError) as e:  # PIL 的 UnidentifiedImageError 是 OSError 的子类
            raise ScreenshotError("file_operation_failed", str(e)) from e

        try:
            self._replace_index(self.ids_data + [{"id": screenshot_id, "date": date_string}],
                                self.all_ids_data + [screenshot_id])
        except OSError as e:
            del self.sav_pairs[screenshot_id]
            for path in written:
                path.unlink(missing_ok=True)
            raise ScreenshotError("save_failed", str(e)) from e

    def replace_screenshot(self, screenshot_id: str, new_image_path: str) -> None:
        thumb_path = self.file_path(screenshot_id, thumb=True)
        if not self.file_path(screenshot_id) or not thumb_path:
            raise ScreenshotError("file_missing")
        try:
            self._write_image_files(screenshot_id, Path(new_image_path), thumb_image_size(thumb_path) or DEFAULT_THUMB_SIZE)
        except (OSError, ValueError) as e:
            raise ScreenshotError("file_operation_failed", str(e)) from e

    def delete_screenshots(self, screenshot_ids: list[str]) -> list[str]:
        """返回删除失败的文件名（它们已经不在索引里了）；索引保存失败时抛出 OSError，什么都不变"""
        to_delete = set(screenshot_ids)
        self._replace_index(
            [item for item in self.ids_data if item['id'] not in to_delete],
            [item_id for item_id in self.all_ids_data if item_id not in to_delete],
        )

        failed: list[str] = []
        for screenshot_id in screenshot_ids:
            for name in self.sav_pairs.pop(screenshot_id, [None, None]):
                if not name:
                    continue
                try:
                    (self.storage_dir / name).unlink(missing_ok=True)
                except OSError:
                    failed.append(name)
        return failed

    def _existing_thumb_size(self) -> tuple[int, int]:
        for screenshot_id in self.sav_pairs:
            thumb_path = self.file_path(screenshot_id, thumb=True)
            size = thumb_image_size(thumb_path) if thumb_path else None
            if size:
                return size
        return DEFAULT_THUMB_SIZE


def open_sav_image(sav_path: Path) -> Image.Image:
    return Image.open(BytesIO(data_uri_to_bytes(read_sav(sav_path))))


def read_image_file(sav_path: Path) -> bytes | None:
    try:
        return data_uri_to_bytes(read_sav(sav_path))
    except (OSError, ValueError):
        return None


def load_resized_image(sav_path: Path, size: tuple[int, int],
                       resample: Image.Resampling = Image.Resampling.BILINEAR) -> Image.Image | None:
    try:
        with open_sav_image(sav_path) as img:
            return img.resize(size, resample)
    except (OSError, ValueError):
        return None


def thumb_image_size(thumb_path: Path) -> tuple[int, int] | None:
    """读取缩略图文件的图片尺寸（只解析文件头，不解码像素）"""
    try:
        with open_sav_image(thumb_path) as img:
            return img.size
    except (OSError, ValueError):
        return None
