"""调试工具模块

提供存档分析器的调试和错误追踪功能。
此模块可以安全删除，不会影响主程序运行。
"""

import logging
import traceback
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class AnalyzerDebugger:
    """存档分析器调试工具"""
    
    ERROR_PREFIX = "[错误]"
    WARNING_PREFIX = "[警告]"
    INFO_PREFIX = "[信息]"
    
    @staticmethod
    def check_scrollable_components(analyzer) -> Tuple[bool, Optional[str]]:
        """检查左侧区域的关键组件是否存在
        
        Args:
            analyzer: SaveAnalyzer 实例
            
        Returns:
            (is_valid, error_message) 元组
        """
        required_attrs = ('scrollable_frame', 'scrollable_canvas')
        
        for attr_name in required_attrs:
            if not hasattr(analyzer, attr_name):
                error_msg = f"{AnalyzerDebugger.ERROR_PREFIX} {attr_name} 属性不存在"
                logger.error(error_msg)
                return False, error_msg
            
            widget = getattr(analyzer, attr_name)
            if widget is None:
                error_msg = f"{AnalyzerDebugger.ERROR_PREFIX} {attr_name} 为 None"
                logger.error(error_msg)
                return False, error_msg
            
            try:
                if not widget.winfo_exists():
                    error_msg = f"{AnalyzerDebugger.ERROR_PREFIX} {attr_name} 已销毁，无法刷新左侧数据浏览区域"
                    logger.error(error_msg)
                    return False, error_msg
            except (AttributeError, RuntimeError) as e:
                error_msg = f"{AnalyzerDebugger.ERROR_PREFIX} 检查 {attr_name} 时发生异常: {e}"
                logger.exception(error_msg)
                return False, error_msg
        
        return True, None
    
    @staticmethod
    def log_refresh_start() -> None:
        """记录刷新开始"""
        message = f"{AnalyzerDebugger.INFO_PREFIX} 开始刷新存档分析页面..."
        logger.info(message)
        print(message)
    
    @staticmethod
    def log_refresh_complete() -> None:
        """记录刷新完成"""
        message = f"{AnalyzerDebugger.INFO_PREFIX} 存档分析页面刷新完成"
        logger.info(message)
        print(message)
    
    @staticmethod
    def log_children_count(analyzer, count: int) -> None:
        """记录子组件数量
        
        Args:
            analyzer: SaveAnalyzer 实例（未使用，保留用于接口一致性）
            count: 子组件数量
        """
        if count == 0:
            message = f"{AnalyzerDebugger.WARNING_PREFIX} 左侧数据浏览区域加载后没有任何子组件"
            logger.warning(message)
            print(message)
        else:
            message = f"{AnalyzerDebugger.INFO_PREFIX} 左侧数据浏览区域成功加载，包含 {count} 个子组件"
            logger.info(message)
            print(message)
    
    @staticmethod
    def log_display_error(error: Exception, analyzer) -> None:
        """记录显示存档信息时的错误
        
        Args:
            error: 异常对象
            analyzer: SaveAnalyzer 实例
        """
        error_type_name = type(error).__name__
        logger.exception(f"显示存档信息时发生异常: {error_type_name}")
        
        print(f"{AnalyzerDebugger.ERROR_PREFIX} 显示存档信息时发生异常: {error}")
        traceback.print_exc()
        print(f"{AnalyzerDebugger.ERROR_PREFIX} 异常类型: {error_type_name}")
        
        has_scrollable_frame = hasattr(analyzer, 'scrollable_frame')
        print(f"{AnalyzerDebugger.ERROR_PREFIX} scrollable_frame 存在: {has_scrollable_frame}")
        
        if has_scrollable_frame:
            try:
                exists = analyzer.scrollable_frame.winfo_exists()
                print(f"{AnalyzerDebugger.ERROR_PREFIX} scrollable_frame.winfo_exists(): {exists}")
            except (AttributeError, RuntimeError):
                print(f"{AnalyzerDebugger.ERROR_PREFIX} 无法检查 scrollable_frame.winfo_exists()")
    
    @staticmethod
    def check_parent_validity(parent, context: str) -> Tuple[bool, Optional[str]]:
        """检查父容器有效性
        
        Args:
            parent: 父容器对象
            context: 上下文描述
            
        Returns:
            (is_valid, error_message) 元组
        """
        if parent is None:
            error_msg = f"{AnalyzerDebugger.ERROR_PREFIX} {context}: parent 参数为 None"
            logger.error(error_msg)
            return False, error_msg
        
        try:
            if not parent.winfo_exists():
                error_msg = f"{AnalyzerDebugger.ERROR_PREFIX} {context}: parent 已销毁"
                logger.error(error_msg)
                return False, error_msg
        except (AttributeError, RuntimeError) as e:
            error_msg = f"{AnalyzerDebugger.ERROR_PREFIX} {context}: 检查 parent 时发生异常: {e}"
            logger.exception(error_msg)
            return False, error_msg
        
        return True, None
    
    @staticmethod
    def log_sections_rendered(count: int) -> None:
        """记录渲染的 section 数量
        
        Args:
            count: section 数量
        """
        if count == 0:
            message = f"{AnalyzerDebugger.WARNING_PREFIX} display_save_info: 没有成功渲染任何 section"
            logger.warning(message)
            print(message)
        else:
            message = f"{AnalyzerDebugger.INFO_PREFIX} display_save_info: 成功渲染了 {count} 个 section"
            logger.info(message)
            print(message)
    
    @staticmethod
    def log_section_render_error(section_key: str, error: Exception) -> None:
        """记录 section 渲染错误
        
        Args:
            section_key: section 键名
            error: 异常对象
        """
        message = f"{AnalyzerDebugger.ERROR_PREFIX} _render_section: section '{section_key}' 渲染过程中发生未捕获的异常: {error}"
        logger.exception(message)
        print(message)
        traceback.print_exc()
    
    @staticmethod
    def log_section_creation_error(section_key: str, error: Exception) -> None:
        """记录 section 创建错误
        
        Args:
            section_key: section 键名
            error: 异常对象
        """
        message = f"{AnalyzerDebugger.ERROR_PREFIX} _render_section: 创建 section '{section_key}' 时发生异常: {error}"
        logger.exception(message)
        print(message)
        traceback.print_exc()
    
    @staticmethod
    def log_section_field_error(section_key: str, widget_key: str, error: Exception) -> None:
        """记录字段渲染错误
        
        Args:
            section_key: section 键名
            widget_key: widget 键名
            error: 异常对象
        """
        message = f"{AnalyzerDebugger.ERROR_PREFIX} _render_section: section '{section_key}' 渲染字段 '{widget_key}' 时发生异常: {error}"
        logger.exception(message)
        print(message)
        traceback.print_exc()
    
    @staticmethod
    def log_section_warning(section_key: str, message: str) -> None:
        """记录 section 警告
        
        Args:
            section_key: section 键名
            message: 警告消息
        """
        full_message = f"{AnalyzerDebugger.WARNING_PREFIX} _render_section: section '{section_key}': {message}"
        logger.warning(full_message)
        print(full_message)
    
    @staticmethod
    def log_section_fields_rendered(section_key: str, count: int) -> None:
        """记录字段渲染数量
        
        Args:
            section_key: section 键名
            count: 字段数量
        """
        if count == 0:
            message = f"{AnalyzerDebugger.WARNING_PREFIX} _render_section: section '{section_key}' 没有成功渲染任何字段"
            logger.warning(message)
            print(message)
    
    @staticmethod
    def log_tab_change(tab_index: int) -> None:
        """记录标签页切换
        
        Args:
            tab_index: 标签页索引
        """
        message = f"{AnalyzerDebugger.INFO_PREFIX} 切换到标签页索引: {tab_index}"
        logger.info(message)
        print(message)
    
    @staticmethod
    def log_tab_refresh_start() -> None:
        """记录标签页刷新开始"""
        message = f"{AnalyzerDebugger.INFO_PREFIX} 切换到存档分析页面，开始刷新..."
        logger.info(message)
        print(message)
    
    @staticmethod
    def log_tab_refresh_error(error: Exception) -> None:
        """记录标签页刷新错误
        
        Args:
            error: 异常对象
        """
        message = f"{AnalyzerDebugger.ERROR_PREFIX} 刷新存档分析页面时发生异常: {error}"
        logger.exception(message)
        print(message)
        traceback.print_exc()
    
    @staticmethod
    def log_tab_warning(message: str) -> None:
        """记录标签页警告
        
        Args:
            message: 警告消息
        """
        full_message = f"{AnalyzerDebugger.WARNING_PREFIX} {message}"
        logger.warning(full_message)
        print(full_message)


_debugger_instance: Optional[AnalyzerDebugger] = None


def get_debugger() -> Optional[AnalyzerDebugger]:
    """获取调试器实例（如果可用）
    
    Returns:
        AnalyzerDebugger 实例，如果模块不可用则返回 None
    """
    global _debugger_instance
    if _debugger_instance is None:
        try:
            _debugger_instance = AnalyzerDebugger()
        except Exception:
            return None
    return _debugger_instance
