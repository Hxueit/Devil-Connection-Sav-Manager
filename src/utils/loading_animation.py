"""加载动画控制器模块

提供可复用的加载动画功能，用于在加载过程中显示动态的"加载中..."效果。
"""

from typing import Any, List, Optional
import tkinter as tk


class LoadingAnimationController:
    """加载动画控制器
    
    管理多个标签的加载动画效果，实现"加载中..." -> "加载中." -> "加载中.." -> "加载中..."的循环动画。
    """
    
    # 动画状态
    STATE_IDLE = 0
    STATE_RUNNING = 1
    
    def __init__(self, root_widget: tk.Widget, interval_ms: int = 500):
        """初始化加载动画控制器
        
        Args:
            root_widget: Tkinter根窗口或父组件（用于after调用）
            interval_ms: 动画帧间隔（毫秒），默认500ms
        """
        self.root = root_widget
        self.interval_ms = interval_ms
        self.state = self.STATE_IDLE
        self.animation_job: Optional[str] = None
        self.target_labels: List[tk.Widget] = []
        self.dots_index = 0
        self.dots_patterns = ["...", ".", ".."]  # 从3个点开始，然后变成1个点，再变成2个点，循环
        self.base_text_cache: Optional[str] = None
        self.translate_func = None
    
    def set_translate_func(self, translate_func: Optional[Any]) -> None:
        """设置翻译函数
        
        Args:
            translate_func: 翻译函数，接受key参数，返回翻译后的文本；如果为None则使用默认文本
        """
        self.translate_func = translate_func
        self.base_text_cache = None  # 清除缓存，下次重新获取
    
    def _get_base_text(self) -> str:
        """获取基础文本（去掉末尾的点）
        
        Returns:
            基础文本，如"加载中"、"Loading"、"読み込み中"
        """
        if self.base_text_cache is not None:
            return self.base_text_cache
        
        if not self.translate_func:
            return "Loading"
        
        # 获取完整翻译文本
        full_text = self.translate_func("loading")
        
        # 移除末尾的点（可能有1-3个点）
        base_text = full_text.rstrip(".")
        
        # 缓存结果
        self.base_text_cache = base_text
        return base_text
    
    def start(self, target_labels: List[tk.Widget]) -> None:
        """启动动画
        
        Args:
            target_labels: 目标标签列表，这些标签将显示动画效果
        """
        if self.state == self.STATE_RUNNING:
            return  # 已运行，避免重复启动
        
        self.state = self.STATE_RUNNING
        self.target_labels = [label for label in target_labels if label is not None]
        self.dots_index = 0
        self.base_text_cache = None  # 清除缓存，重新获取基础文本
        
        # 立即更新第一帧
        self._update_frame()
    
    def _update_frame(self) -> None:
        """更新当前帧"""
        if self.state != self.STATE_RUNNING:
            return
        
        # 获取基础文本和当前点模式
        base_text = self._get_base_text()
        dots = self.dots_patterns[self.dots_index]
        full_text = f"{base_text}{dots}"
        
        # 更新所有标签
        valid_labels = []
        for label in self.target_labels:
            if label and hasattr(label, 'winfo_exists') and label.winfo_exists():
                try:
                    label.configure(text=full_text)
                    valid_labels.append(label)
                except (tk.TclError, AttributeError):
                    # 标签已销毁，跳过
                    pass
        
        # 更新有效标签列表
        self.target_labels = valid_labels
        
        # 如果所有标签都无效，停止动画
        if not self.target_labels:
            self.stop()
            return
        
        # 循环索引
        self.dots_index = (self.dots_index + 1) % len(self.dots_patterns)
        
        # 调度下一帧
        self.animation_job = self.root.after(
            self.interval_ms,
            self._update_frame
        )
    
    def stop(self) -> None:
        """停止动画"""
        if self.state == self.STATE_IDLE:
            return
        
        self.state = self.STATE_IDLE
        
        # 取消待执行的动画任务
        if self.animation_job:
            try:
                self.root.after_cancel(self.animation_job)
            except (tk.TclError, ValueError):
                # 任务可能已经执行或窗口已关闭
                pass
            self.animation_job = None
        
        # 清空目标标签列表
        self.target_labels = []
    
    def is_running(self) -> bool:
        """检查动画是否正在运行
        
        Returns:
            如果动画正在运行返回True，否则返回False
        """
        return self.state == self.STATE_RUNNING

