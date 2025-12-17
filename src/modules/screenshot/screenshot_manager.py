"""截图数据管理模块

负责截图文件的加载、保存和管理，包括截图文件的扫描、
添加、删除、替换等操作
"""

import os
import json
import urllib.parse
import base64
import tempfile
import time
import random
import string
from datetime import datetime
from PIL import Image


class ScreenshotManager:
    """截图数据管理类
    
    处理截图索引数据的存储和检索，包括截图文件的扫描、
    添加、删除、替换等操作
    """
    
    def __init__(self, storage_dir=None, t_func=None):
        """初始化截图管理器
        
        Args:
            storage_dir: 截图存储目录路径，默认为None
            t_func: 翻译函数，默认为None
        """
        self.storage_dir = storage_dir
        self.ids_data = []
        self.all_ids_data = []
        self.sav_pairs = {}
        self._file_list_cache = None
        self._file_list_cache_time = 0
        self._file_list_cache_ttl = 5
        self.t = t_func or (lambda key, **kwargs: key.format(**kwargs) if kwargs else key)
    
    def set_storage_dir(self, storage_dir):
        """设置存储目录
        
        Args:
            storage_dir: 存储目录路径
        """
        self.storage_dir = storage_dir
        self._file_list_cache = None
    
    def load_and_decode(self, sav_path):
        """加载并解码sav文件
        
        Args:
            sav_path: sav文件路径
            
        Returns:
            解码后的JSON数据
        """
        with open(sav_path, 'r', encoding='utf-8') as f:
            encoded = f.read().strip()
        unquoted = urllib.parse.unquote(encoded)
        return json.loads(unquoted)

    def encode_and_save(self, data, sav_path):
        """编码并保存数据到sav文件
        
        Args:
            data: 要保存的数据（字典或列表）
            sav_path: 保存路径
        """
        json_str = json.dumps(data)
        encoded = urllib.parse.quote(json_str)
        with open(sav_path, 'w', encoding='utf-8') as f:
            f.write(encoded)
    
    def scan_sav_files(self):
        """扫描存储目录中的截图文件
        
        使用缓存机制避免频繁的文件系统访问
        
        Returns:
            dict: 截图ID到文件名的映射字典，格式为 {id: [主文件, 缩略图文件]}
        """
        current_time = time.time()
        
        if (self._file_list_cache is None or 
            current_time - self._file_list_cache_time > self._file_list_cache_ttl or
            self._file_list_cache[0] != self.storage_dir):
            self.sav_pairs = {}
            if self.storage_dir:
                try:
                    file_list = os.listdir(self.storage_dir)
                    for file in file_list:
                        if file.startswith('DevilConnection_photo_') and file.endswith('.sav'):
                            base_name = file.rsplit('.sav', 1)[0]
                            parts = base_name.split('_')
                            if len(parts) == 3:
                                id_str = parts[2]
                                if id_str not in self.sav_pairs:
                                    self.sav_pairs[id_str] = [None, None]
                                self.sav_pairs[id_str][0] = file
                            elif len(parts) == 4 and parts[3] == 'thumb':
                                id_str = parts[2]
                                if id_str not in self.sav_pairs:
                                    self.sav_pairs[id_str] = [None, None]
                                self.sav_pairs[id_str][1] = file
                    
                    self._file_list_cache = (self.storage_dir, self.sav_pairs.copy())
                    self._file_list_cache_time = current_time
                except OSError:
                    self.sav_pairs = {}
                    self._file_list_cache = None
        else:
            _, self.sav_pairs = self._file_list_cache
            self.sav_pairs = self.sav_pairs.copy()
        
        return self.sav_pairs
    
    def load_screenshots(self):
        """加载截图索引数据
        
        Returns:
            bool: 加载成功返回True，否则返回False
        """
        if not self.storage_dir:
            return False
        
        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
        
        if not (os.path.exists(ids_path) and os.path.exists(all_ids_path)):
            return False
        
        self.ids_data = self.load_and_decode(ids_path)
        self.all_ids_data = self.load_and_decode(all_ids_path)
        self.scan_sav_files()
        return True
    
    def save_screenshots(self):
        """保存截图索引数据
        
        Returns:
            bool: 保存成功返回True，否则返回False
        """
        if not self.storage_dir:
            return False
        
        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
        
        self.encode_and_save(self.ids_data, ids_path)
        self.encode_and_save(self.all_ids_data, all_ids_path)
        return True
    
    def sort_by_date(self, ascending=True):
        """按日期排序截图列表
        
        Args:
            ascending: 是否升序排列，默认为True
        """
        self.ids_data.sort(
            key=lambda x: datetime.strptime(x['date'], '%Y/%m/%d %H:%M:%S'),
            reverse=not ascending
        )
        self.all_ids_data = [item['id'] for item in self.ids_data]
        self.save_screenshots()
    
    def move_item(self, from_index, to_index):
        """移动截图在列表中的位置
        
        Args:
            from_index: 源位置索引
            to_index: 目标位置索引
        """
        if from_index == to_index:
            return
        moved_item = self.ids_data.pop(from_index)
        self.ids_data.insert(to_index, moved_item)
        self.all_ids_data = [item['id'] for item in self.ids_data]
        self.save_screenshots()
    
    def add_screenshot(self, new_id, new_date, new_png_path):
        """添加新截图
        
        Args:
            new_id: 新截图的ID
            new_date: 截图日期字符串，格式为 '%Y/%m/%d %H:%M:%S'
            new_png_path: PNG图片文件路径
            
        Returns:
            tuple: (成功标志, 消息字符串)。成功时返回 (True, "添加成功")，
                   失败时返回 (False, 错误消息)
        """
        if new_id in self.sav_pairs:
            return False, self.t("id_exists")
        
        self.ids_data.append({"id": new_id, "date": new_date})
        self.all_ids_data.append(new_id)
        self.save_screenshots()
        
        main_sav_name = f'DevilConnection_photo_{new_id}.sav'
        thumb_sav_name = f'DevilConnection_photo_{new_id}_thumb.sav'
        main_sav = os.path.join(self.storage_dir, main_sav_name)
        thumb_sav = os.path.join(self.storage_dir, thumb_sav_name)
        
        thumb_size = self._get_thumb_size()
        
        try:
            with open(new_png_path, 'rb') as f:
                png_b64 = base64.b64encode(f.read()).decode('utf-8')
            new_main_uri = f"data:image/png;base64,{png_b64}"
            new_main_json = json.dumps(new_main_uri)
            new_main_encoded = urllib.parse.quote(new_main_json)
            with open(main_sav, 'w', encoding='utf-8') as f:
                f.write(new_main_encoded)
            
            self._create_thumbnail(new_png_path, thumb_sav, thumb_size)
            
            self._file_list_cache = None
            self.scan_sav_files()
            
            return True, "添加成功"
        except (OSError, IOError, ValueError) as e:
            return False, self.t("file_operation_failed", error=str(e))
    
    def _get_thumb_size(self):
        """从现有文件推断缩略图尺寸
        
        Returns:
            tuple: 缩略图尺寸 (宽度, 高度)，默认返回 (1280, 960)
        """
        thumb_size = (1280, 960)
        for pair in self.sav_pairs.values():
            if pair[1] is not None:
                first_thumb = os.path.join(self.storage_dir, pair[1])
                if not os.path.exists(first_thumb):
                    continue
                try:
                    with open(first_thumb, 'r', encoding='utf-8') as f:
                        encoded = f.read().strip()
                    unquoted = urllib.parse.unquote(encoded)
                    data_uri = json.loads(unquoted)
                    b64_part = data_uri.split(';base64,', 1)[1]
                    img_data = base64.b64decode(b64_part)
                    temp_thumb = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False).name
                    with open(temp_thumb, 'wb') as f:
                        f.write(img_data)
                    thumb_orig = Image.open(temp_thumb)
                    thumb_size = thumb_orig.size
                    thumb_orig.close()
                    if os.path.exists(temp_thumb):
                        os.remove(temp_thumb)
                    break
                except (OSError, IOError, ValueError, Exception):
                    continue
        return thumb_size
    
    def _create_thumbnail(self, source_path, thumb_sav_path, thumb_size):
        """创建缩略图并保存为sav文件
        
        Args:
            source_path: 源图片路径
            thumb_sav_path: 缩略图sav文件保存路径
            thumb_size: 缩略图尺寸 (宽度, 高度)
        """
        temp_thumb = None
        try:
            main_img = Image.open(source_path)
            new_thumb = main_img.resize(thumb_size, Image.Resampling.BILINEAR)
            new_thumb = new_thumb.convert('RGB')
            temp_thumb = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False).name
            new_thumb.save(temp_thumb, 'JPEG', quality=90, optimize=True)
            main_img.close()
            new_thumb.close()
            
            with open(temp_thumb, 'rb') as f:
                jpeg_b64 = base64.b64encode(f.read()).decode('utf-8')
            new_thumb_uri = f"data:image/jpeg;base64,{jpeg_b64}"
            new_thumb_json = json.dumps(new_thumb_uri)
            new_thumb_encoded = urllib.parse.quote(new_thumb_json)
            with open(thumb_sav_path, 'w', encoding='utf-8') as f:
                f.write(new_thumb_encoded)
        finally:
            if temp_thumb and os.path.exists(temp_thumb):
                try:
                    os.remove(temp_thumb)
                except OSError:
                    pass
    
    def replace_screenshot(self, id_str, new_png_path):
        """替换指定ID的截图
        
        Args:
            id_str: 截图ID
            new_png_path: 新PNG图片文件路径
            
        Returns:
            tuple: (成功标志, 消息字符串)。成功时返回 (True, "添加成功")，
                   失败时返回 (False, 错误消息)
        """
        if id_str not in self.sav_pairs:
            return False, self.t("screenshot_not_exist")
        
        pair = self.sav_pairs[id_str]
        if pair[0] is None or pair[1] is None:
            return False, self.t("file_missing")
        
        main_sav = os.path.join(self.storage_dir, pair[0])
        thumb_sav = os.path.join(self.storage_dir, pair[1])
        
        thumb_size = self._get_thumb_size_from_file(thumb_sav)
        
        try:
            with open(new_png_path, 'rb') as f:
                png_b64 = base64.b64encode(f.read()).decode('utf-8')
            new_main_uri = f"data:image/png;base64,{png_b64}"
            new_main_json = json.dumps(new_main_uri)
            new_main_encoded = urllib.parse.quote(new_main_json)
            with open(main_sav, 'w', encoding='utf-8') as f:
                f.write(new_main_encoded)
            
            self._create_thumbnail(new_png_path, thumb_sav, thumb_size)
            
            return True, "替换成功"
        except (OSError, IOError, ValueError) as e:
            return False, self.t("file_operation_failed", error=str(e))
    
    def _get_thumb_size_from_file(self, thumb_sav):
        """从缩略图文件获取尺寸
        
        Args:
            thumb_sav: 缩略图sav文件路径
            
        Returns:
            tuple: 缩略图尺寸 (宽度, 高度)，失败时返回默认值 (1280, 960)
        """
        temp_thumb = None
        try:
            if not os.path.exists(thumb_sav):
                return (1280, 960)
            with open(thumb_sav, 'r', encoding='utf-8') as f:
                encoded = f.read().strip()
            unquoted = urllib.parse.unquote(encoded)
            data_uri = json.loads(unquoted)
            b64_part = data_uri.split(';base64,', 1)[1]
            img_data = base64.b64decode(b64_part)
            temp_thumb = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False).name
            with open(temp_thumb, 'wb') as f:
                f.write(img_data)
            thumb_orig = Image.open(temp_thumb)
            size = thumb_orig.size
            thumb_orig.close()
            return size
        except (OSError, IOError, ValueError, Exception):
            return (1280, 960)
        finally:
            if temp_thumb and os.path.exists(temp_thumb):
                try:
                    os.remove(temp_thumb)
                except OSError:
                    pass
    
    def delete_screenshots(self, id_list):
        """删除指定ID列表的截图
        
        Args:
            id_list: 要删除的截图ID列表
            
        Returns:
            int: 成功删除的截图数量
        """
        deleted_count = 0
        for id_str in id_list:
            pair = self.sav_pairs.get(id_str, [None, None])
            main_path = os.path.join(self.storage_dir, pair[0]) if pair[0] else None
            thumb_path = os.path.join(self.storage_dir, pair[1]) if pair[1] else None
            
            if main_path and os.path.exists(main_path):
                try:
                    os.remove(main_path)
                    deleted_count += 1
                except OSError:
                    pass
            if thumb_path and os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except OSError:
                    pass
            
            self.ids_data = [item for item in self.ids_data if item['id'] != id_str]
            self.all_ids_data = [item for item in self.all_ids_data if item != id_str]
            
            if id_str in self.sav_pairs:
                del self.sav_pairs[id_str]
        
        self.save_screenshots()
        self._file_list_cache = None
        
        return deleted_count
    
    def get_image_data(self, id_str):
        """获取指定ID截图的图片二进制数据
        
        Args:
            id_str: 截图ID
            
        Returns:
            bytes: 图片的二进制数据，失败时返回None
        """
        if id_str not in self.sav_pairs:
            return None
        
        main_file = self.sav_pairs[id_str][0]
        if not main_file:
            return None
        
        main_sav = os.path.join(self.storage_dir, main_file)
        if not os.path.exists(main_sav):
            return None
        
        try:
            with open(main_sav, 'r', encoding='utf-8') as f:
                encoded = f.read().strip()
            unquoted = urllib.parse.unquote(encoded)
            data_uri = json.loads(unquoted)
            b64_part = data_uri.split(';base64,', 1)[1]
            return base64.b64decode(b64_part)
        except (OSError, IOError, ValueError, KeyError):
            return None
    
    def generate_id(self):
        """生成随机ID
        
        Returns:
            str: 8位随机字符串，包含小写字母和数字
        """
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    
    def get_current_datetime(self):
        """获取当前时间字符串
        
        Returns:
            str: 格式化的时间字符串，格式为 '%Y/%m/%d %H:%M:%S'
        """
        return datetime.now().strftime('%Y/%m/%d %H:%M:%S')

