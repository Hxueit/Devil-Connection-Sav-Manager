"""存档分析器主类

作为协调器，整合布局管理、widget管理、数据渲染和业务逻辑。
此模块专注于协调各个子模块，不包含具体的UI创建或数据处理逻辑。
"""

import logging
import tkinter as tk
from tkinter import ttk
from typing import Dict, Any, Optional, Callable, Set, List

from src.constants import TOTAL_OMAKES, TOTAL_GALLERY, TOTAL_NG_SCENE, LATEST_GAME_PATCH_AT_BUILD, TOTAL_ENDINGS, STICKER_ID_RANGES
from src.utils.styles import get_cjk_font, Colors

from .config import get_field_configs_with_callbacks
from .save_data_service import load_save_file, compute_shared_data
from .statistics.panel import StatisticsPanel
from .save_file_viewer import SaveFileViewer
from .requirements_viewer import RequirementsViewer
from .layout_manager import LayoutManager
from .widget_manager import WidgetManager
from .data_renderer import DataRenderer

try:
    from .debug import get_debugger
    _debugger = get_debugger()
except ImportError:
    _debugger = None

logger = logging.getLogger(__name__)

# 常量
DEFAULT_WINDOW_WIDTH = 800
WIDTH_RATIO = 2 / 3


def _validate_scrollable_components(analyzer: 'SaveAnalyzer') -> bool:
    """验证可滚动组件是否有效
    
    Args:
        analyzer: SaveAnalyzer实例
        
    Returns:
        组件是否有效
    """
    if not hasattr(analyzer, 'scrollable_frame') or not analyzer.scrollable_frame:
        return False
    if not analyzer.scrollable_frame.winfo_exists():
        return False
    if not hasattr(analyzer, 'scrollable_canvas') or not analyzer.scrollable_canvas:
        return False
    if not analyzer.scrollable_canvas.winfo_exists():
        return False
    return True


class SaveAnalyzer:
    """存档分析器类，用于显示和分析游戏存档数据"""
    
    TOTAL_OMAKES = TOTAL_OMAKES
    TOTAL_GALLERY = TOTAL_GALLERY
    TOTAL_NG_SCENE = TOTAL_NG_SCENE
    
    def __init__(
        self,
        parent: tk.Widget,
        storage_dir: str,
        translations: Dict[str, Dict[str, str]],
        current_language: str
    ) -> None:
        """初始化存档分析器
        
        Args:
            parent: 父窗口widget
            storage_dir: 存档文件目录
            translations: 翻译字典
            current_language: 当前语言代码
        """
        self.parent = parent
        self.storage_dir = storage_dir
        self.translations = translations
        self.current_language = current_language
        self.window = parent
        
        # 初始化窗口宽度
        cached_width = self._calculate_initial_width()
        
        # 创建widget管理器
        self.show_var_names_var = tk.BooleanVar(value=False)
        self.widget_manager = WidgetManager(self.show_var_names_var)
        
        # 创建布局管理器
        self.layout_manager = LayoutManager(
            self.window,
            cached_width,
            self._update_scrollregion_callback
        )
        
        # 创建数据渲染器
        self.data_renderer = DataRenderer(
            self.widget_manager,
            cached_width,
            self.t,
            self._get_field_configs
        )
        
        # 创建UI布局
        main_container, left_frame, right_frame, canvas, scrollable_frame = \
            self.layout_manager.create_main_layout(self._create_control_frame)
        
        self.scrollable_frame = scrollable_frame
        self.scrollable_canvas = canvas
        self._left_frame = left_frame
        self._right_frame = right_frame
        
        # 创建统计面板和需求查看器
        self.statistics_panel = StatisticsPanel(self.window, self.storage_dir, self.t)
        self.requirements_viewer = RequirementsViewer(self.window, self.t)
        
        # 创建统计面板UI
        self.create_statistics_panel(right_frame)
        
        # 创建查看文件按钮
        self._create_view_file_button(right_frame)
        
        # 初始化状态
        self._is_initialized = False
        self.save_data: Optional[Dict[str, Any]] = None
        self._stats_container: Optional[tk.Widget] = None
        
        # 延迟刷新
        self.window.after_idle(self.refresh)
    
    def _calculate_initial_width(self) -> int:
        """计算初始宽度
        
        Returns:
            缓存的宽度值
        """
        self.window.update_idletasks()
        window_width = self.window.winfo_width()
        if window_width <= 1:
            window_width = DEFAULT_WINDOW_WIDTH
        return int(window_width * WIDTH_RATIO)
    
    def _create_control_frame(self, control_frame: tk.Frame) -> None:
        """创建控制面板
        
        Args:
            control_frame: 控制面板容器
        """
        self.show_var_names_checkbox = ttk.Checkbutton(
            control_frame,
            text=self.t("show_var_names"),
            variable=self.show_var_names_var,
            command=self.toggle_var_names_display
        )
        self.show_var_names_checkbox.pack(side="left", padx=5)
        
        self.refresh_button = ttk.Button(
            control_frame,
            text=self.t("refresh"),
            command=self.refresh,
            name="refresh"
        )
        self.refresh_button.pack(side="right", padx=5)
    
    def _create_view_file_button(self, parent: tk.Widget) -> None:
        """创建查看文件按钮
        
        Args:
            parent: 父容器
        """
        button_frame = tk.Frame(parent, bg=Colors.WHITE)
        button_frame.pack(side="bottom", fill="x", pady=(0, 10))
        self.view_file_button = ttk.Button(
            button_frame,
            text=self.t("view_save_file"),
            command=self.show_save_file_viewer
        )
        self.view_file_button.pack(pady=5)
    
    def _update_scrollregion_callback(self, retry_key: str) -> None:
        """更新滚动区域的回调函数
        
        Args:
            retry_key: 重试键
        """
        self.layout_manager.update_scrollregion(
            retry_key,
            canvas=self.scrollable_canvas,
            scrollable_frame=self.scrollable_frame
        )
    
    def _get_field_configs(self) -> Dict[str, Any]:
        """获取字段配置（带回调绑定）
        
        Returns:
            包含所有section配置的字典
        """
        return get_field_configs_with_callbacks(
            endings_callback=lambda sd, cd: lambda: self.show_endings_requirements(
                sd, cd["endings"], cd["collected_endings"], cd["missing_endings"]
            ),
            stickers_callback=lambda sd, cd: lambda: self.show_stickers_requirements(
                sd, cd["stickers"], cd["collected_stickers"], cd["missing_stickers"]
            ),
            ng_scene_callback=lambda sd, cd: lambda: self.show_ng_scene_requirements(sd)
        )
    
    def toggle_var_names_display(self) -> None:
        """切换变量名显示状态"""
        self.widget_manager.toggle_var_names_display()
    
    def refresh(self) -> None:
        """刷新存档分析页面：重新加载存档并更新显示（支持增量更新）"""
        if not _validate_scrollable_components(self):
            if _debugger:
                is_valid, error_msg = _debugger.check_scrollable_components(self)
                if not is_valid and error_msg:
                    logger.warning(error_msg)
            return
        
        # 更新UI文本
        self._update_ui_texts()
        
        # 加载存档数据
        self.save_data = load_save_file(self.storage_dir)
        
        if self.save_data:
            try:
                self._display_save_info(self.save_data)
            except (KeyError, ValueError, TypeError, AttributeError) as e:
                logger.error(f"Failed to display save info: {e}", exc_info=True)
                if _debugger:
                    _debugger.log_display_error(e, self)
                # 不重新抛出异常，避免崩溃
            except Exception as e:
                logger.error(f"Unexpected error displaying save info: {e}", exc_info=True)
                if _debugger:
                    _debugger.log_display_error(e, self)
                raise
        else:
            self._show_save_file_not_found()
            self.save_data = None
    
    def _update_ui_texts(self) -> None:
        """更新UI文本（用于语言切换）"""
        if hasattr(self, 'show_var_names_checkbox'):
            self.show_var_names_checkbox.config(text=self.t("show_var_names"))
        if hasattr(self, 'refresh_button'):
            self.refresh_button.config(text=self.t("refresh"))
        if hasattr(self, 'view_file_button'):
            self.view_file_button.config(text=self.t("view_save_file"))
        
        # 更新section标题
        for key, widget_info in list(self.widget_manager._section_title_widgets.items()):
            title_label = widget_info.get('title_label')
            button = widget_info.get('button')
            title_key = widget_info.get('title_key')
            
            if title_label and title_label.winfo_exists() and title_key:
                title_label.config(text=self.t(title_key))
            
            if button and button.winfo_exists() and widget_info.get('button_text_key'):
                button.config(text=self.t(widget_info['button_text_key']))
        
        # 更新提示标签
        for hint_info in self.widget_manager._hint_labels:
            label = hint_info.get('label')
            text_key = hint_info.get('text_key')
            if label and label.winfo_exists() and text_key:
                hint_text = self.t(text_key)
                # 替换占位符
                if "[GAMEPATCH_DATE]" in hint_text:
                    hint_text = hint_text.replace("[GAMEPATCH_DATE]", LATEST_GAME_PATCH_AT_BUILD)
                label.config(text=hint_text)
        
        # 更新tooltip文本（用于语言切换）
        configs = self._get_field_configs()
        for section_key, section_config in configs.items():
            for field_config in section_config.get("fields", []):
                if field_config.get("has_tooltip"):
                    tooltip_key = field_config.get("tooltip_key")
                    widget_key = field_config.get("widget_key")
                    if tooltip_key and widget_key:
                        tooltip_text = self.t(tooltip_key)
                        # 替换占位符
                        if "[GAMEPATCH_DATE]" in tooltip_text:
                            tooltip_text = tooltip_text.replace("[GAMEPATCH_DATE]", LATEST_GAME_PATCH_AT_BUILD)
                        # 更新tooltip StringVar
                        self.widget_manager.update_tooltip_var(widget_key, tooltip_text)
    
    def _display_save_info(self, save_data: Dict[str, Any]) -> None:
        """显示存档信息（支持增量更新）
        
        Args:
            save_data: 存档数据字典
        """
        if not self._validate_scrollable_frame():
            return
        
        self._update_canvas_width()
        
        # 尝试增量更新
        if self._is_initialized:
            if self._try_incremental_update(save_data):
                return
        
        # 完整重建
        self._rebuild_all_sections(save_data)
    
    def _validate_scrollable_frame(self) -> bool:
        """验证可滚动frame是否有效
        
        Returns:
            frame是否有效
        """
        if _debugger:
            is_valid, error_msg = _debugger.check_parent_validity(
                self.scrollable_frame,
                "display_save_info"
            )
            if not is_valid:
                if error_msg:
                    logger.warning(error_msg)
                return False
            return True
        
        if self.scrollable_frame is None or not self.scrollable_frame.winfo_exists():
            return False
        return True
    
    def _update_canvas_width(self) -> None:
        """更新canvas宽度"""
        if not self.window.winfo_exists():
            return
        
        try:
            window_width = self.window.winfo_width()
            if window_width > 1:
                width = int(window_width * WIDTH_RATIO)
                self.layout_manager.cached_width = width
                self.data_renderer.cached_width = width
                if self.scrollable_frame and self.scrollable_frame.winfo_exists():
                    self.scrollable_frame.config(width=width)
        except (AttributeError, tk.TclError) as e:
            logger.warning(f"Failed to update canvas width: {e}")
    
    def _try_incremental_update(self, save_data: Dict[str, Any]) -> bool:
        """尝试增量更新
        
        Args:
            save_data: 存档数据字典
            
        Returns:
            是否成功进行增量更新
        """
        try:
            computed_data = compute_shared_data(
                save_data,
                self.TOTAL_OMAKES,
                self.TOTAL_GALLERY,
                self.TOTAL_NG_SCENE
            )
            is_fanatic_route = computed_data["is_fanatic_route"]
            
            is_initialized_ref = {'value': self._is_initialized}
            success = self.data_renderer.update_incremental(
                save_data,
                computed_data,
                is_fanatic_route,
                self.scrollable_frame,
                is_initialized_ref
            )
            self._is_initialized = is_initialized_ref['value']
            
            if success:
                self.window.after_idle(
                    lambda: self._update_scrollregion_callback("display_save_info")
                )
                self.window.after_idle(
                    lambda: self._update_statistics_panel_safe(save_data)
                )
                return True
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Incremental update failed, falling back to full rebuild: {e}")
            self._is_initialized = False
        except Exception as e:
            logger.error(f"Unexpected error during incremental update: {e}", exc_info=True)
            self._is_initialized = False
        
        return False
    
    def _rebuild_all_sections(self, save_data: Dict[str, Any]) -> None:
        """完整重建所有sections
        
        Args:
            save_data: 存档数据字典
        """
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        self.widget_manager.clear_all()
        
        try:
            computed_data = compute_shared_data(
                save_data,
                self.TOTAL_OMAKES,
                self.TOTAL_GALLERY,
                self.TOTAL_NG_SCENE
            )
            is_fanatic_route = computed_data["is_fanatic_route"]
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Failed to compute shared data: {e}", exc_info=True)
            if _debugger:
                _debugger.log_display_error(e, self)
            return
        
        rendered_count = self.data_renderer.render_all_sections(
            self.scrollable_frame,
            save_data,
            computed_data,
            is_fanatic_route
        )
        
        if _debugger:
            _debugger.log_sections_rendered(rendered_count)
        
        # 重新绑定滚轮事件到新创建的widget
        self.layout_manager.rebind_mousewheel_to_frame(self.scrollable_frame)
        
        self.window.after_idle(
            lambda: self._update_scrollregion_callback("display_save_info")
        )
        
        self._is_initialized = True
        
        self.window.after_idle(
            lambda: self.window.after_idle(
                lambda: self._update_statistics_panel_safe(save_data)
            )
        )
    
    def _update_statistics_panel_safe(self, save_data: Dict[str, Any]) -> None:
        """安全地更新统计面板
        
        Args:
            save_data: 存档数据字典
        """
        if self._stats_container and self._stats_container.winfo_exists():
            self.update_statistics_panel(self._stats_container, save_data)
        elif self._right_frame and self._right_frame.winfo_exists():
            self.create_statistics_panel(self._right_frame)
            if self._stats_container and self._stats_container.winfo_exists():
                self.update_statistics_panel(self._stats_container, save_data)
    
    def _show_save_file_not_found(self) -> None:
        """显示存档文件未找到的错误信息"""
        if not self._is_initialized:
            try:
                for widget in self.scrollable_frame.winfo_children():
                    widget.destroy()
                error_label = ttk.Label(
                    self.scrollable_frame,
                    text=self.t("save_file_not_found"),
                    font=get_cjk_font(12),
                    foreground="red"
                )
                error_label.pack(pady=20)
            except (AttributeError, tk.TclError) as e:
                logger.warning(f"Failed to show save file not found message: {e}")
    
    def t(self, key: str, **kwargs: Any) -> str:
        """翻译函数
        
        Args:
            key: 翻译键
            **kwargs: 格式化参数
        
        Returns:
            翻译后的文本
        """
        text = self.translations[self.current_language].get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text
    
    def create_statistics_panel(self, parent: tk.Widget) -> None:
        """创建统计面板（委托给StatisticsPanel模块）
        
        Args:
            parent: 父容器
        """
        self._stats_container = self.statistics_panel.create(parent)
    
    def update_statistics_panel(
        self,
        parent: tk.Widget,
        save_data: Dict[str, Any]
    ) -> None:
        """更新统计面板（委托给StatisticsPanel模块）
        
        Args:
            parent: 父容器
            save_data: 存档数据
        """
        self.statistics_panel.update(parent, save_data)
    
    def show_save_file_viewer(self) -> None:
        """显示存档文件查看器窗口（委托给SaveFileViewer模块）"""
        if not self.save_data:
            return
        
        def on_close() -> None:
            self._is_initialized = False
            self.widget_manager.clear_all()
            self.refresh()
        
        def on_save(edited_data: Dict[str, Any]) -> None:
            """保存时刷新界面"""
            self._is_initialized = False
            self.widget_manager.clear_all()
            self.refresh()
        
        from src.modules.save_analysis.sf.save_file_viewer import ViewerConfig, DEFAULT_SF_COLLAPSED_FIELDS
        
        config = ViewerConfig(
            collapsed_fields=DEFAULT_SF_COLLAPSED_FIELDS,
            show_collapse_checkbox=True,
            show_hint_label=True,
            show_enable_edit_checkbox=True,
            enable_edit_by_default=False,
            on_save_callback=on_save
        )
        
        SaveFileViewer.open_or_focus(
            viewer_id=f"sf:{self.storage_dir}",
            window=self.window,
            storage_dir=self.storage_dir,
            save_data=self.save_data,
            t_func=self.t,
            on_close_callback=on_close,
            viewer_config=config
        )
    
    def show_endings_requirements(
        self,
        save_data: Dict[str, Any],
        endings: Set[int],
        collected_endings: Set[int],
        missing_endings: List[int]
    ) -> None:
        """显示结局达成条件窗口（委托给RequirementsViewer模块）
        
        Args:
            save_data: 存档数据
            endings: 所有结局集合
            collected_endings: 已收集结局集合
            missing_endings: 缺失结局列表
        """
        all_ending_ids = [str(i) for i in range(1, TOTAL_ENDINGS + 1)]
        collected_endings_set = set(str(e) for e in collected_endings)
        
        items = [
            (ending_id, self.t(f"END{ending_id}_unlock_cond"))
            for ending_id in all_ending_ids
        ]
        
        self.requirements_viewer.show(
            title_key="endings_statistics",
            hint_key="missing_endings",
            items=items,
            collected_set=collected_endings_set,
            id_prefix="END",
            window_title_suffix="endings",
            is_sticker=False
        )
    
    def show_stickers_requirements(
        self,
        save_data: Dict[str, Any],
        stickers: Set[int],
        collected_stickers: List[int],
        missing_stickers: List[int]
    ) -> None:
        """显示贴纸达成条件窗口（委托给RequirementsViewer模块）
        
        Args:
            save_data: 存档数据
            stickers: 所有贴纸集合
            collected_stickers: 已收集贴纸列表
            missing_stickers: 缺失贴纸列表
        """
        all_sticker_ids = []
        for start, end in STICKER_ID_RANGES:
            all_sticker_ids.extend(str(i) for i in range(start, end))
        
        collected_stickers_set = set(str(s) for s in collected_stickers)
        
        items = [
            (sticker_id, self.t(f"STICKER{sticker_id}_unlock_cond"))
            for sticker_id in all_sticker_ids
        ]
        
        self.requirements_viewer.show(
            title_key="stickers_statistics",
            hint_key="missing_stickers_count",
            items=items,
            collected_set=collected_stickers_set,
            id_prefix="#",
            window_title_suffix="stickers",
            is_sticker=True
        )
    
    def show_ng_scene_requirements(self, save_data: Dict[str, Any]) -> None:
        """显示NG场景解锁条件窗口
        
        Args:
            save_data: 存档数据
        """
        ng_scene_list = save_data.get("ngScene", [])
        collected_ng_scene_set = set(ng_scene_list)
        
        all_ng_scene_ids = self.TOTAL_NG_SCENE
        
        items = []
        name_to_id_map = {}
        for ng_scene_id in all_ng_scene_ids:
            ng_scene_name_key = f"ng_scene_{ng_scene_id}"
            ng_scene_name = self.t(ng_scene_name_key)
            condition_text = self.t(f"{ng_scene_name_key}_unlock_cond")
            items.append((ng_scene_name, condition_text))
            name_to_id_map[ng_scene_name] = ng_scene_id
        
        collected_ng_scene_names_set = {
            name
            for name, scene_id in name_to_id_map.items()
            if scene_id in collected_ng_scene_set
        }
        
        self.requirements_viewer.show(
            title_key="omakes_statistics",
            hint_key="ng_scene_count",
            items=items,
            collected_set=collected_ng_scene_names_set,
            id_prefix="",
            window_title_suffix="ng_scenes",
            is_sticker=False,
            is_ng_scene=True
        )
