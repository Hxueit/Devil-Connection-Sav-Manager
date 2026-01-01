"""截图数据管理模块

负责截图文件的加载、保存和管理，包括截图文件的扫描、
添加、删除、替换等操作
"""

import json
import logging
import urllib.parse
import base64
import tempfile
import time
import random
import string
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Callable, Any
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

# 常量定义
DATE_FORMAT = '%Y/%m/%d %H:%M:%S'
FILE_PREFIX = 'DevilConnection_photo_'
FILE_SUFFIX = '.sav'
THUMB_SUFFIX = '_thumb'
IDS_FILENAME = 'DevilConnection_photo_ids.sav'
ALL_IDS_FILENAME = 'DevilConnection_photo_all_ids.sav'
DEFAULT_THUMB_SIZE = (1280, 960)
THUMB_QUALITY = 90
CACHE_TTL_SECONDS = 5
ID_LENGTH = 8


class ScreenshotManager:
    """截图数据管理类
    
    处理截图索引数据的存储和检索，包括截图文件的扫描、
    添加、删除、替换等操作
    """
    
    def __init__(
        self,
        storage_dir: Optional[str] = None,
        t_func: Optional[Callable[[str], str]] = None
    ) -> None:
        """初始化截图管理器
        
        Args:
            storage_dir: 截图存储目录路径，默认为None
            t_func: 翻译函数，默认为None
        """
        self.storage_dir: Optional[Path] = Path(storage_dir) if storage_dir else None
        self.ids_data: List[Dict[str, str]] = []
        self.all_ids_data: List[str] = []
        self.sav_pairs: Dict[str, List[Optional[str]]] = {}
        self._file_list_cache: Optional[Tuple[Path, Dict[str, List[Optional[str]]]]] = None
        self._file_list_cache_time: float = 0.0
        self._file_list_cache_ttl: float = CACHE_TTL_SECONDS
        self.t = t_func or (lambda key, **kwargs: key.format(**kwargs) if kwargs else key)
    
    def set_storage_dir(self, storage_dir: Optional[str]) -> None:
        """设置存储目录
        
        Args:
            storage_dir: 存储目录路径
        """
        self.storage_dir = Path(storage_dir) if storage_dir else None
        self._file_list_cache = None
    
    def load_and_decode(self, sav_path: Path) -> Any:
        """加载并解码sav文件
        
        Args:
            sav_path: sav文件路径
            
        Returns:
            解码后的JSON数据
            
        Raises:
            OSError: 文件读取失败
            json.JSONDecodeError: JSON解析失败
            ValueError: URL解码失败
        """
        encoded_data = sav_path.read_text(encoding='utf-8').strip()
        unquoted_data = urllib.parse.unquote(encoded_data)
        return json.loads(unquoted_data)
    
    def encode_and_save(self, data: Any, sav_path: Path) -> None:
        """编码并保存数据到sav文件
        
        Args:
            data: 要保存的数据（字典或列表）
            sav_path: 保存路径
            
        Raises:
            OSError: 文件写入失败
        """
        json_str = json.dumps(data, ensure_ascii=False)
        encoded_data = urllib.parse.quote(json_str)
        sav_path.write_text(encoded_data, encoding='utf-8')
    
    def scan_sav_files(self) -> Dict[str, List[Optional[str]]]:
        """扫描存储目录中的截图文件
        
        使用缓存机制避免频繁的文件系统访问
        
        Returns:
            截图ID到文件名的映射字典，格式为 {id: [主文件, 缩略图文件]}
        """
        current_time = time.time()
        
        should_refresh_cache = (
            self._file_list_cache is None or
            current_time - self._file_list_cache_time > self._file_list_cache_ttl or
            (self.storage_dir and self._file_list_cache[0] != self.storage_dir)
        )
        
        if should_refresh_cache:
            self.sav_pairs = {}
            if self.storage_dir and self.storage_dir.exists():
                try:
                    self._scan_directory_for_sav_files()
                    self._file_list_cache = (self.storage_dir, self.sav_pairs.copy())
                    self._file_list_cache_time = current_time
                except OSError as e:
                    logger.error(f"Failed to scan directory {self.storage_dir}: {e}")
                    self.sav_pairs = {}
                    self._file_list_cache = None
        else:
            if self._file_list_cache:
                _, self.sav_pairs = self._file_list_cache
                self.sav_pairs = self.sav_pairs.copy()
        
        return self.sav_pairs
    
    def _scan_directory_for_sav_files(self) -> None:
        """扫描目录中的sav文件并构建映射
        
        Raises:
            OSError: 目录读取失败
        """
        if not self.storage_dir:
            return
        
        for file_path in self.storage_dir.iterdir():
            if not file_path.is_file():
                continue
            
            filename = file_path.name
            if not (filename.startswith(FILE_PREFIX) and filename.endswith(FILE_SUFFIX)):
                continue
            
            screenshot_id = self._extract_screenshot_id(filename)
            if not screenshot_id:
                continue
            
            if screenshot_id not in self.sav_pairs:
                self.sav_pairs[screenshot_id] = [None, None]
            
            if THUMB_SUFFIX in filename:
                self.sav_pairs[screenshot_id][1] = filename
            else:
                self.sav_pairs[screenshot_id][0] = filename
    
    def _extract_screenshot_id(self, filename: str) -> Optional[str]:
        """从文件名提取截图ID
        
        Args:
            filename: 文件名
            
        Returns:
            截图ID，如果无法提取则返回None
        """
        base_name = filename.rsplit(FILE_SUFFIX, 1)[0]
        parts = base_name.split('_')
        
        if len(parts) == 3:
            return parts[2]
        elif len(parts) == 4 and parts[3] == 'thumb':
            return parts[2]
        
        return None
    
    def load_screenshots(self) -> bool:
        """加载截图索引数据
        
        Returns:
            加载成功返回True，否则返回False
        """
        if not self.storage_dir:
            return False
        
        ids_path = self.storage_dir / IDS_FILENAME
        all_ids_path = self.storage_dir / ALL_IDS_FILENAME
        
        if not (ids_path.exists() and all_ids_path.exists()):
            return False
        
        try:
            self.ids_data = self.load_and_decode(ids_path)
            self.all_ids_data = self.load_and_decode(all_ids_path)
            self.scan_sav_files()
            return True
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to load screenshots: {e}", exc_info=True)
            return False
    
    def save_screenshots(self) -> bool:
        """保存截图索引数据
        
        Returns:
            保存成功返回True，否则返回False
        """
        if not self.storage_dir:
            return False
        
        ids_path = self.storage_dir / IDS_FILENAME
        all_ids_path = self.storage_dir / ALL_IDS_FILENAME
        
        try:
            self.encode_and_save(self.ids_data, ids_path)
            self.encode_and_save(self.all_ids_data, all_ids_path)
            return True
        except OSError as e:
            logger.error(f"Failed to save screenshots: {e}", exc_info=True)
            return False
    
    def sort_by_date(self, ascending: bool = True) -> None:
        """按日期排序截图列表
        
        Args:
            ascending: 是否升序排列，默认为True
        """
        try:
            self.ids_data.sort(
                key=lambda item: datetime.strptime(item['date'], DATE_FORMAT),
                reverse=not ascending
            )
            self.all_ids_data = [item['id'] for item in self.ids_data]
            self.save_screenshots()
        except (ValueError, KeyError) as e:
            logger.error(f"Failed to sort screenshots: {e}", exc_info=True)
    
    def move_item(self, from_index: int, to_index: int) -> None:
        """移动截图在列表中的位置
        
        Args:
            from_index: 源位置索引
            to_index: 目标位置索引
        """
        if from_index == to_index:
            return
        
        if not (0 <= from_index < len(self.ids_data) and 0 <= to_index < len(self.ids_data)):
            logger.warning(f"Invalid indices: from={from_index}, to={to_index}, total={len(self.ids_data)}")
            return
        
        moved_item = self.ids_data.pop(from_index)
        self.ids_data.insert(to_index, moved_item)
        self.all_ids_data = [item['id'] for item in self.ids_data]
        self.save_screenshots()
    
    def add_screenshot(
        self,
        screenshot_id: str,
        date_string: str,
        image_path: str
    ) -> Tuple[bool, str]:
        """添加新截图
        
        Args:
            screenshot_id: 新截图的ID
            date_string: 截图日期字符串，格式为 '%Y/%m/%d %H:%M:%S'
            image_path: PNG图片文件路径
            
        Returns:
            (成功标志, 消息字符串) 元组。成功时返回 (True, 成功消息)，
            失败时返回 (False, 错误消息)
        """
        if screenshot_id in self.sav_pairs:
            return False, self.t("id_exists")
        
        if not self.storage_dir:
            return False, self.t("storage_dir_not_set")
        
        image_path_obj = Path(image_path)
        if not image_path_obj.exists():
            return False, self.t("file_not_exist")
        
        self.ids_data.append({"id": screenshot_id, "date": date_string})
        self.all_ids_data.append(screenshot_id)
        
        if not self.save_screenshots():
            return False, self.t("save_failed")
        
        main_sav_path = self.storage_dir / f'{FILE_PREFIX}{screenshot_id}{FILE_SUFFIX}'
        thumb_sav_path = self.storage_dir / f'{FILE_PREFIX}{screenshot_id}{THUMB_SUFFIX}{FILE_SUFFIX}'
        
        thumb_size = self._get_thumb_size()
        
        try:
            self._save_main_image(image_path_obj, main_sav_path)
            self._create_thumbnail(image_path_obj, thumb_sav_path, thumb_size)
            
            self._file_list_cache = None
            self.scan_sav_files()
            
            return True, self.t("success")
        except (OSError, IOError, ValueError, UnidentifiedImageError) as e:
            logger.error(f"Failed to add screenshot: {e}", exc_info=True)
            return False, self.t("file_operation_failed", error=str(e))
    
    def _save_main_image(self, image_path: Path, sav_path: Path) -> None:
        """保存主图片到sav文件
        
        Args:
            image_path: 图片路径
            sav_path: sav文件路径
            
        Raises:
            OSError: 文件操作失败
            ValueError: 图片编码失败
        """
        image_data = image_path.read_bytes()
        png_base64 = base64.b64encode(image_data).decode('utf-8')
        data_uri = f"data:image/png;base64,{png_base64}"
        json_str = json.dumps(data_uri)
        encoded_data = urllib.parse.quote(json_str)
        sav_path.write_text(encoded_data, encoding='utf-8')
    
    def _get_thumb_size(self) -> Tuple[int, int]:
        """从现有文件推断缩略图尺寸
        
        Returns:
            缩略图尺寸 (宽度, 高度)，默认返回 (1280, 960)
        """
        if not self.storage_dir:
            return DEFAULT_THUMB_SIZE
        
        for file_pair in self.sav_pairs.values():
            if file_pair[1] is None:
                continue
            
            thumb_path = self.storage_dir / file_pair[1]
            if not thumb_path.exists():
                continue
            
            thumb_size = self._extract_thumb_size_from_file(thumb_path)
            if thumb_size:
                return thumb_size
        
        return DEFAULT_THUMB_SIZE
    
    def _extract_thumb_size_from_file(self, thumb_path: Path) -> Optional[Tuple[int, int]]:
        """从缩略图文件提取尺寸
        
        Args:
            thumb_path: 缩略图sav文件路径
            
        Returns:
            缩略图尺寸，失败时返回None
        """
        temp_thumb_path = None
        try:
            encoded_data = thumb_path.read_text(encoding='utf-8').strip()
            unquoted_data = urllib.parse.unquote(encoded_data)
            data_uri = json.loads(unquoted_data)
            
            if ';base64,' not in data_uri:
                return None
            
            base64_part = data_uri.split(';base64,', 1)[1]
            image_data = base64.b64decode(base64_part)
            
            temp_thumb_path = Path(tempfile.NamedTemporaryFile(suffix='.jpg', delete=False).name)
            temp_thumb_path.write_bytes(image_data)
            
            with Image.open(temp_thumb_path) as img:
                return img.size
        except (OSError, IOError, json.JSONDecodeError, ValueError, UnidentifiedImageError, base64.binascii.Error) as e:
            logger.debug(f"Failed to extract thumb size from {thumb_path}: {e}")
            return None
        finally:
            if temp_thumb_path and temp_thumb_path.exists():
                try:
                    temp_thumb_path.unlink()
                except OSError as e:
                    logger.debug(f"Failed to remove temp file {temp_thumb_path}: {e}")
    
    def _create_thumbnail(
        self,
        source_path: Path,
        thumb_sav_path: Path,
        thumb_size: Tuple[int, int]
    ) -> None:
        """创建缩略图并保存为sav文件
        
        Args:
            source_path: 源图片路径
            thumb_sav_path: 缩略图sav文件保存路径
            thumb_size: 缩略图尺寸 (宽度, 高度)
            
        Raises:
            OSError: 文件操作失败
            UnidentifiedImageError: 图片格式不支持
        """
        temp_thumb_path = None
        try:
            with Image.open(source_path) as main_img:
                thumbnail_img = main_img.resize(thumb_size, Image.Resampling.BILINEAR)
                thumbnail_img = thumbnail_img.convert('RGB')
                
                temp_thumb_path = Path(tempfile.NamedTemporaryFile(suffix='.jpg', delete=False).name)
                thumbnail_img.save(temp_thumb_path, 'JPEG', quality=THUMB_QUALITY, optimize=True)
            
            jpeg_data = temp_thumb_path.read_bytes()
            jpeg_base64 = base64.b64encode(jpeg_data).decode('utf-8')
            data_uri = f"data:image/jpeg;base64,{jpeg_base64}"
            json_str = json.dumps(data_uri)
            encoded_data = urllib.parse.quote(json_str)
            thumb_sav_path.write_text(encoded_data, encoding='utf-8')
        finally:
            if temp_thumb_path and temp_thumb_path.exists():
                try:
                    temp_thumb_path.unlink()
                except OSError as e:
                    logger.debug(f"Failed to remove temp file {temp_thumb_path}: {e}")
    
    def replace_screenshot(
        self,
        screenshot_id: str,
        new_image_path: str
    ) -> Tuple[bool, str]:
        """替换指定ID的截图
        
        Args:
            screenshot_id: 截图ID
            new_image_path: 新PNG图片文件路径
            
        Returns:
            (成功标志, 消息字符串) 元组。成功时返回 (True, 成功消息)，
            失败时返回 (False, 错误消息)
        """
        if screenshot_id not in self.sav_pairs:
            return False, self.t("screenshot_not_exist")
        
        file_pair = self.sav_pairs[screenshot_id]
        if file_pair[0] is None or file_pair[1] is None:
            return False, self.t("file_missing")
        
        if not self.storage_dir:
            return False, self.t("storage_dir_not_set")
        
        main_sav_path = self.storage_dir / file_pair[0]
        thumb_sav_path = self.storage_dir / file_pair[1]
        
        new_image_path_obj = Path(new_image_path)
        if not new_image_path_obj.exists():
            return False, self.t("file_not_exist")
        
        thumb_size = self._get_thumb_size_from_file(thumb_sav_path)
        
        try:
            self._save_main_image(new_image_path_obj, main_sav_path)
            self._create_thumbnail(new_image_path_obj, thumb_sav_path, thumb_size)
            return True, self.t("success")
        except (OSError, IOError, ValueError, UnidentifiedImageError) as e:
            logger.error(f"Failed to replace screenshot: {e}", exc_info=True)
            return False, self.t("file_operation_failed", error=str(e))
    
    def _get_thumb_size_from_file(self, thumb_sav_path: Path) -> Tuple[int, int]:
        """从缩略图文件获取尺寸
        
        Args:
            thumb_sav_path: 缩略图sav文件路径
            
        Returns:
            缩略图尺寸 (宽度, 高度)，失败时返回默认值 (1280, 960)
        """
        if not thumb_sav_path.exists():
            return DEFAULT_THUMB_SIZE
        
        thumb_size = self._extract_thumb_size_from_file(thumb_sav_path)
        return thumb_size if thumb_size else DEFAULT_THUMB_SIZE
    
    def delete_screenshots(self, screenshot_ids: List[str]) -> int:
        """删除指定ID列表的截图
        
        Args:
            screenshot_ids: 要删除的截图ID列表
            
        Returns:
            成功删除的截图数量
        """
        if not self.storage_dir:
            return 0
        
        deleted_count = 0
        
        for screenshot_id in screenshot_ids:
            file_pair = self.sav_pairs.get(screenshot_id, [None, None])
            main_path = self.storage_dir / file_pair[0] if file_pair[0] else None
            thumb_path = self.storage_dir / file_pair[1] if file_pair[1] else None
            
            if main_path and main_path.exists():
                try:
                    main_path.unlink()
                    deleted_count += 1
                except OSError as e:
                    logger.debug(f"Failed to delete main file {main_path}: {e}")
            
            if thumb_path and thumb_path.exists():
                try:
                    thumb_path.unlink()
                except OSError as e:
                    logger.debug(f"Failed to delete thumb file {thumb_path}: {e}")
            
            # 从数据列表中移除
            self.ids_data = [item for item in self.ids_data if item['id'] != screenshot_id]
            self.all_ids_data = [item_id for item_id in self.all_ids_data if item_id != screenshot_id]
            
            if screenshot_id in self.sav_pairs:
                del self.sav_pairs[screenshot_id]
        
        self.save_screenshots()
        self._file_list_cache = None
        
        return deleted_count
    
    def get_image_data(self, screenshot_id: str) -> Optional[bytes]:
        """获取指定ID截图的图片二进制数据
        
        Args:
            screenshot_id: 截图ID
            
        Returns:
            图片的二进制数据，失败时返回None
        """
        if screenshot_id not in self.sav_pairs:
            return None
        
        main_filename = self.sav_pairs[screenshot_id][0]
        if not main_filename or not self.storage_dir:
            return None
        
        main_sav_path = self.storage_dir / main_filename
        if not main_sav_path.exists():
            return None
        
        try:
            encoded_data = main_sav_path.read_text(encoding='utf-8').strip()
            unquoted_data = urllib.parse.unquote(encoded_data)
            data_uri = json.loads(unquoted_data)
            
            if ';base64,' not in data_uri:
                return None
            
            base64_part = data_uri.split(';base64,', 1)[1]
            return base64.b64decode(base64_part)
        except (OSError, IOError, json.JSONDecodeError, ValueError, KeyError, base64.binascii.Error) as e:
            logger.debug(f"Failed to get image data for {screenshot_id}: {e}")
            return None
    
    def generate_id(self) -> str:
        """生成随机ID
        
        Returns:
            8位随机字符串，包含小写字母和数字
        """
        characters = string.ascii_lowercase + string.digits
        return ''.join(random.choices(characters, k=ID_LENGTH))
    
    def get_current_datetime(self) -> str:
        """获取当前时间字符串
        
        Returns:
            格式化的时间字符串，格式为 '%Y/%m/%d %H:%M:%S'
        """
        return datetime.now().strftime(DATE_FORMAT)
