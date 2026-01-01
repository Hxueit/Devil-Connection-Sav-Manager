"""Tyrano存档分析器

负责读取、解析和管理Tyrano存档数据
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Final, Union

from src.modules.others.tyrano_service import TyranoService
from src.modules.save_analysis.tyrano.constants import (
    TYRANO_SAVES_PER_PAGE,
    TYRANO_SAV_FILENAME
)

logger = logging.getLogger(__name__)

_MIN_PAGE_NUMBER: Final[int] = 1
_MIN_SLOT_COUNT: Final[int] = 0
_DATA_FIELD_KEY: Final[str] = 'data'


class TyranoAnalyzer:
    """Tyrano存档分析器类
    
    负责读取、解析和管理Tyrano存档数据，提供分页功能
    """
    
    def __init__(self, storage_dir: str) -> None:
        """初始化分析器
        
        Args:
            storage_dir: 存储目录路径
            
        Raises:
            ValueError: 如果storage_dir为空字符串
        """
        if not storage_dir:
            raise ValueError("storage_dir cannot be empty")
        
        self.storage_dir: Path = Path(storage_dir)
        self.tyrano_service: TyranoService = TyranoService()
        self.save_data: Optional[Dict[str, Any]] = None
        self.save_slots: List[Dict[str, Any]] = []
        self.current_page: int = 0
        self.total_pages: int = 0
    
    def _reset_state(self) -> None:
        """重置分析器状态到空状态"""
        self.save_data = None
        self.save_slots = []
        self.total_pages = 0
        self.current_page = 0
    
    def _calculate_pagination(self, slot_count: int) -> None:
        """计算分页信息
        
        Args:
            slot_count: 存档槽总数（必须 >= 0）
        """
        if slot_count <= _MIN_SLOT_COUNT:
            self.total_pages = 0
            self.current_page = 0
        else:
            self.total_pages = (slot_count + TYRANO_SAVES_PER_PAGE - 1) // TYRANO_SAVES_PER_PAGE
            self.current_page = _MIN_PAGE_NUMBER
    
    def _extract_save_slots(self, save_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从存档数据中提取存档槽数组
        
        Args:
            save_payload: 存档数据字典
            
        Returns:
            存档槽列表，如果数据无效返回空列表
        """
        if not isinstance(save_payload, dict):
            logger.error("Save data format error: root object is not a dictionary")
            return []
        
        data_field = save_payload.get(_DATA_FIELD_KEY)
        if not isinstance(data_field, list):
            logger.warning("Data field not found in save payload or is not a list")
            return []
        
        # 验证列表中的元素都是字典
        valid_slots = [
            slot for slot in data_field
            if isinstance(slot, dict)
        ]
        
        if len(valid_slots) != len(data_field):
            invalid_count = len(data_field) - len(valid_slots)
            logger.warning(
                "Found %d invalid slot(s) in save data (not dictionaries), filtered out",
                invalid_count
            )
        
        return valid_slots
    
    def _handle_load_error(
        self,
        error: Exception,
        file_path: Path,
        error_type: str
    ) -> None:
        """统一处理加载错误
        
        Args:
            error: 异常对象
            file_path: 文件路径
            error_type: 错误类型描述（英文，用于日志）
        """
        logger.error(
            "Failed to load save file: %s, path: %s, error: %s",
            error_type,
            file_path,
            error,
            exc_info=True
        )
        self._reset_state()
    
    def load_save_file(self) -> bool:
        """加载并解析存档文件
        
        Returns:
            成功返回True，失败返回False
        """
        if not self.storage_dir.exists():
            logger.error("Storage directory does not exist: %s", self.storage_dir)
            self._reset_state()
            return False
        
        if not self.storage_dir.is_dir():
            logger.error("Storage path is not a directory: %s", self.storage_dir)
            self._reset_state()
            return False
        
        tyrano_file_path = self.storage_dir / TYRANO_SAV_FILENAME
        
        if not tyrano_file_path.exists():
            logger.warning("Tyrano save file not found: %s", tyrano_file_path)
            self._reset_state()
            return False
        
        if not tyrano_file_path.is_file():
            logger.error("Tyrano save path is not a file: %s", tyrano_file_path)
            self._reset_state()
            return False
        
        try:
            save_payload = self.tyrano_service.load_tyrano_save_file(tyrano_file_path)
            if not isinstance(save_payload, dict):
                logger.error("Loaded save payload is not a dictionary")
                self._reset_state()
                return False
            
            self.save_data = save_payload
            self.save_slots = self._extract_save_slots(save_payload)
            self._calculate_pagination(len(self.save_slots))
            
            logger.info(
                "Successfully loaded %d save slots, %d pages total",
                len(self.save_slots),
                self.total_pages
            )
            return True
            
        except FileNotFoundError as e:
            self._handle_load_error(e, tyrano_file_path, "FileNotFoundError")
            return False
        except PermissionError as e:
            self._handle_load_error(e, tyrano_file_path, "PermissionError")
            return False
        except OSError as e:
            self._handle_load_error(e, tyrano_file_path, "OSError")
            return False
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._handle_load_error(e, tyrano_file_path, "DecodeError")
            return False
        except ValueError as e:
            self._handle_load_error(e, tyrano_file_path, "ValueError")
            return False
    
    def get_save_slot(self, slot_index: int) -> Optional[Dict[str, Any]]:
        """获取指定索引的存档槽数据
        
        Args:
            slot_index: 存档槽索引（从0开始）
            
        Returns:
            存档槽数据字典，如果索引无效返回None
        """
        if not self.save_slots:
            return None
        
        if slot_index < 0 or slot_index >= len(self.save_slots):
            return None
        
        return self.save_slots[slot_index]
    
    def get_current_page_slots(self) -> List[Optional[Dict[str, Any]]]:
        """获取当前页的存档槽列表
        
        Returns:
            当前页的存档槽列表（可能包含None表示空槽）
        """
        if not self.save_slots or self.current_page < _MIN_PAGE_NUMBER:
            return []
        
        start_index = (self.current_page - _MIN_PAGE_NUMBER) * TYRANO_SAVES_PER_PAGE
        end_index = start_index + TYRANO_SAVES_PER_PAGE
        
        # 确保索引不超出范围
        if start_index >= len(self.save_slots):
            return []
        
        page_slots = self.save_slots[start_index:end_index]
        # 确保返回的列表长度固定为 TYRANO_SAVES_PER_PAGE，不足的用None填充
        while len(page_slots) < TYRANO_SAVES_PER_PAGE:
            page_slots.append(None)
        
        return page_slots
    
    def set_page(self, target_page: int) -> bool:
        """设置当前页码
        
        Args:
            target_page: 目标页码（从1开始）
            
        Returns:
            设置成功返回True，失败返回False
        """
        if target_page < _MIN_PAGE_NUMBER or target_page > self.total_pages:
            return False
        
        self.current_page = target_page
        return True
    
    def go_to_next_page(self) -> bool:
        """跳转到下一页
        
        Returns:
            成功返回True
        """
        self.current_page += 1
        if self.current_page > self.total_pages:
            self.current_page = _MIN_PAGE_NUMBER
        return True
    
    def go_to_prev_page(self) -> bool:
        """跳转到上一页
        
        Returns:
            成功返回True
        """
        self.current_page -= 1
        if self.current_page < _MIN_PAGE_NUMBER:
            self.current_page = self.total_pages
        return True
    
    def has_saves(self) -> bool:
        """检查是否有存档
        
        Returns:
            有存档返回True，否则返回False
        """
        return bool(self.save_slots)
    
    def get_total_saves(self) -> int:
        """获取存档总数
        
        Returns:
            存档总数
        """
        return len(self.save_slots)

