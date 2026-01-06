"""图片缓存模块

提供双层图片缓存（L1原始图片 + L2缩略图），使用LRU策略
"""

import logging
from collections import OrderedDict
from typing import Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

L1_CACHE_MAX_SIZE: int = 50
L2_CACHE_MAX_SIZE: int = 500


class ImageCache:
    """双层图片缓存（L1原始图片 + L2缩略图，LRU策略）"""
    
    def __init__(self, l1_max_size: int = L1_CACHE_MAX_SIZE, l2_max_size: int = L2_CACHE_MAX_SIZE) -> None:
        """初始化双层缓存
        
        Args:
            l1_max_size: L1缓存最大容量
            l2_max_size: L2缓存最大容量
            
        Raises:
            ValueError: 当缓存大小小于等于0时
        """
        if l1_max_size <= 0 or l2_max_size <= 0:
            raise ValueError(f"Cache size must be positive, got l1={l1_max_size}, l2={l2_max_size}")
        
        self._l1_cache: OrderedDict[str, Image.Image] = OrderedDict()
        self._l1_max_size: int = l1_max_size
        self._l2_cache: OrderedDict[Tuple[str, Tuple[int, int]], Image.Image] = OrderedDict()
        self._l2_max_size: int = l2_max_size
    
    def get_original(self, img_hash: str) -> Optional[Image.Image]:
        """从L1缓存获取原始图片
        
        Args:
            img_hash: 图片数据的MD5哈希值
            
        Returns:
            缓存的原始PIL Image对象，如果不存在返回None
        """
        if not img_hash:
            return None
        
        image = self._l1_cache.get(img_hash)
        if image is not None:
            self._l1_cache.move_to_end(img_hash)
            return image
        return None
    
    def put_original(self, img_hash: str, image: Image.Image) -> None:
        """存入L1缓存（原始图片）
        
        Args:
            img_hash: 图片数据的MD5哈希值
            image: 原始PIL Image对象
        """
        if not img_hash or image is None:
            return
        
        if img_hash in self._l1_cache:
            self._l1_cache.move_to_end(img_hash)
            return
        
        if len(self._l1_cache) >= self._l1_max_size:
            self._l1_cache.popitem(last=False)
        
        self._l1_cache[img_hash] = image
    
    def get_thumbnail(self, img_hash: str, size: Tuple[int, int]) -> Optional[Image.Image]:
        """从L2缓存获取缩略图
        
        Args:
            img_hash: 图片数据的MD5哈希值
            size: 缩略图尺寸
            
        Returns:
            缓存的缩略图PIL Image对象，如果不存在返回None
        """
        if not img_hash or not size or size[0] <= 0 or size[1] <= 0:
            return None
        
        key = (img_hash, size)
        thumbnail = self._l2_cache.get(key)
        if thumbnail is not None:
            self._l2_cache.move_to_end(key)
            return thumbnail
        return None
    
    def put_thumbnail(self, img_hash: str, size: Tuple[int, int], image: Image.Image) -> None:
        """存入L2缓存（缩略图）
        
        Args:
            img_hash: 图片数据的MD5哈希值
            size: 缩略图尺寸
            image: 缩略图PIL Image对象
        """
        if not img_hash or not size or size[0] <= 0 or size[1] <= 0 or image is None:
            return
        
        key = (img_hash, size)
        
        if key in self._l2_cache:
            self._l2_cache.move_to_end(key)
            return
        
        if len(self._l2_cache) >= self._l2_max_size:
            self._l2_cache.popitem(last=False)
        
        self._l2_cache[key] = image
    
    def clear(self) -> None:
        """清空所有缓存"""
        self._l1_cache.clear()
        self._l2_cache.clear()


