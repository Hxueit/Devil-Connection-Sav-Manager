"""编辑模式管理模块

负责管理截图管理界面的编辑模式状态，控制修改操作的启用/禁用。
"""

from typing import Callable, List, Set
import logging

logger = logging.getLogger(__name__)


class EditModeManager:
    """编辑模式管理器
    
    管理编辑模式的启用/禁用状态，并提供统一的接口来控制修改操作的可用性。
    """
    
    def __init__(self, initial_state: bool = False) -> None:
        """初始化编辑模式管理器
        
        Args:
            initial_state: 初始状态，默认为False（禁用编辑模式）
        """
        self._is_enabled: bool = initial_state
        self._state_change_callbacks: List[Callable[[bool], None]] = []
    
    @property
    def is_enabled(self) -> bool:
        """获取当前编辑模式状态
        
        Returns:
            如果编辑模式已启用返回True，否则返回False
        """
        return self._is_enabled
    
    def enable(self) -> None:
        """启用编辑模式"""
        if not self._is_enabled:
            self._is_enabled = True
            self._notify_state_change()
            logger.debug("Edit mode enabled")
    
    def disable(self) -> None:
        """禁用编辑模式"""
        if self._is_enabled:
            self._is_enabled = False
            self._notify_state_change()
            logger.debug("Edit mode disabled")
    
    def toggle(self) -> bool:
        """切换编辑模式状态
        
        Returns:
            切换后的状态
        """
        if self._is_enabled:
            self.disable()
        else:
            self.enable()
        return self._is_enabled
    
    def register_state_change_callback(self, callback: Callable[[bool], None]) -> None:
        """注册状态变化回调函数
        
        Args:
            callback: 状态变化时调用的回调函数，接收一个bool参数表示新状态
            
        Raises:
            TypeError: 如果callback不是可调用对象
        """
        if not callable(callback):
            raise TypeError("Callback must be callable")
        if callback not in self._state_change_callbacks:
            self._state_change_callbacks.append(callback)
    
    def unregister_state_change_callback(self, callback: Callable[[bool], None]) -> None:
        """取消注册状态变化回调函数
        
        Args:
            callback: 要移除的回调函数
        """
        try:
            self._state_change_callbacks.remove(callback)
        except ValueError:
            pass
    
    def _notify_state_change(self) -> None:
        """通知所有注册的回调函数状态已改变"""
        for callback in self._state_change_callbacks:
            try:
                callback(self._is_enabled)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}", exc_info=True)

