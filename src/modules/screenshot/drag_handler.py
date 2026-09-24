"""拖拽处理模块

负责处理截图列表中的拖拽排序功能，包括拖拽开始、移动、结束等
事件处理，以及拖拽指示器的显示和清除。
"""

import logging
from typing import Optional, Tuple, List, Callable, TYPE_CHECKING, Any
import tkinter as tk
from tkinter import ttk

if TYPE_CHECKING:
    from src.modules.screenshot.edit_mode_manager import EditModeManager

logger = logging.getLogger(__name__)


class DragHandler:
    """拖拽处理器
    
    管理Treeview中项目的拖拽排序功能。
    """
    
    DRAG_THRESHOLD: int = 5
    INDICATOR_TIMEOUT_MS: int = 15000
    
    def __init__(
        self,
        tree: ttk.Treeview,
        root: tk.Tk,
        checkbox_manager: Any,
        screenshot_manager: Any,
        load_screenshots_callback: Callable[[], None],
        update_checkbox_display_callback: Callable[[str], None],
        edit_mode_manager: Optional["EditModeManager"] = None,
        gallery_refresh_callback: Optional[Callable[[int, int], None]] = None
    ) -> None:
        """初始化拖拽处理器
        
        Args:
            tree: Treeview组件实例
            root: 根窗口实例
            checkbox_manager: 复选框管理器实例
            screenshot_manager: 截图管理器实例
            load_screenshots_callback: 加载截图列表的回调函数
            update_checkbox_display_callback: 更新复选框显示的回调函数
            edit_mode_manager: 编辑模式管理器实例，可选
            gallery_refresh_callback: 画廊刷新回调函数，接收(start_index, end_index)参数，可选
        """
        if tree is None:
            raise ValueError("tree cannot be None")
        if root is None:
            raise ValueError("root cannot be None")
        if screenshot_manager is None:
            raise ValueError("screenshot_manager cannot be None")
        
        self.tree = tree
        self.root = root
        self.checkbox_manager = checkbox_manager
        self.screenshot_manager = screenshot_manager
        self.load_screenshots_callback = load_screenshots_callback
        self.update_checkbox_display_callback = update_checkbox_display_callback
        self.edit_mode_manager = edit_mode_manager
        self.gallery_refresh_callback = gallery_refresh_callback
        
        self.drag_start_item: Optional[str] = None
        self.drag_start_y: Optional[int] = None
        self.is_dragging: bool = False
        self.drag_target_item: Optional[str] = None
        self.current_indicator_target: Optional[str] = None
        self.current_indicator_position: Optional[int] = None
        
        self.drag_indicators: List[Tuple[str, str, Optional[int]]] = []
        self.drag_indicator_line: Optional[tk.Frame] = None
    
    def setup_drag_indicator_line(self, parent_frame: tk.Frame) -> None:
        """设置拖拽指示线
        
        Args:
            parent_frame: 父框架
        """
        self.drag_indicator_line = tk.Frame(parent_frame, bg="black", height=3)
        self.drag_indicator_line.place_forget()
    
    def handle_button1_click(self, event: tk.Event) -> Optional[str]:
        """处理Button-1点击事件：检查复选框或初始化拖拽
        
        Args:
            event: 鼠标事件
            
        Returns:
            如果需要阻止默认行为则返回"break"，否则返回None
        """
        region = self.tree.identify_region(event.x, event.y)
        
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == "#1" or (0 < event.x < 40):
                item_id = self.tree.identify_row(event.y)
                if item_id and self._is_valid_item(item_id):
                    var = self.checkbox_manager.get_checkbox_var(item_id)
                    if var is not None:
                        var.set(not var.get())
                        return "break"
        elif region == "heading":
            column = self.tree.identify_column(event.x)
            if column == "#1" or (0 < event.x < 40):
                self._reset_drag_state()
                return None
        
        item = self.tree.identify_row(event.y)
        if item and self._is_valid_item(item):
            self.drag_start_item = item
            self.drag_start_y = event.y
            self._reset_drag_state()
        
        return None
    
    def handle_drag_motion(self, event: tk.Event) -> None:
        """处理拖拽移动事件
        
        Args:
            event: 鼠标移动事件
        """
        if self.drag_start_item is None:
            return
        
        if not self._is_edit_mode_enabled():
            self._reset_drag_state()
            self._clear_drag_indicator()
            return
        
        drag_start_y = self.drag_start_y
        if drag_start_y is None:
            return
        
        if abs(event.y - drag_start_y) <= self.DRAG_THRESHOLD:
            return
        
        self.is_dragging = True
        self._apply_dragging_tag()
        
        target_item = self.tree.identify_row(event.y)
        self.drag_target_item = target_item
        
        if target_item and target_item != self.drag_start_item:
            if not self._is_valid_item(target_item):
                self._clear_drag_indicator()
                return
            
            is_dragging_down = self._calculate_drag_direction(target_item, event.y)
            self._show_drag_indicator_line(target_item, is_dragging_down)
        else:
            self._clear_drag_indicator()
    
    def handle_drag_end(self, event: tk.Event) -> None:
        """处理拖拽结束事件
        
        Args:
            event: 鼠标释放事件
        """
        self._remove_dragging_tag()
        self._clear_drag_indicator()
        
        if not self._is_edit_mode_enabled():
            self._reset_drag_state()
            return
        
        if not self._should_process_drag():
            self._reset_drag_state()
            return
        
        end_item = self.drag_target_item or self.tree.identify_row(event.y)
        if not end_item or end_item == self.drag_start_item:
            self._reset_drag_state()
            return
        
        if not self._is_valid_item(end_item):
            self._reset_drag_state()
            return
        
        self._perform_drag_move(end_item)
        self._reset_drag_state()
    
    def _is_valid_item(self, item_id: str) -> bool:
        """检查项目是否为有效的数据项（非页眉）
        
        Args:
            item_id: Treeview项目ID
            
        Returns:
            如果是有效数据项返回True，否则返回False
        """
        if not item_id:
            return False
        
        try:
            if not self.tree.exists(item_id):
                return False
        except (tk.TclError, AttributeError):
            return False
        
        try:
            item_tags = self.tree.item(item_id, "tags")
            if not item_tags:
                return True
            
            return "PageHeaderLeft" not in item_tags and "PageHeaderRight" not in item_tags
        except (tk.TclError, AttributeError):
            return False
    
    def _reset_drag_state(self) -> None:
        """重置拖拽状态"""
        self.drag_target_item = None
        self.is_dragging = False
    
    def _apply_dragging_tag(self) -> None:
        """应用拖拽标签"""
        if not self.drag_start_item:
            return
        
        try:
            if not self.tree.exists(self.drag_start_item):
                return
            
            current_tags = list(self.tree.item(self.drag_start_item, "tags"))
            if "Dragging" not in current_tags:
                current_tags.append("Dragging")
                self.tree.item(self.drag_start_item, tags=tuple(current_tags))
        except (tk.TclError, AttributeError) as e:
            logger.debug(f"Failed to apply dragging tag: {e}")
    
    def _remove_dragging_tag(self) -> None:
        """移除拖拽标签"""
        if not self.drag_start_item:
            return
        
        try:
            if not self.tree.exists(self.drag_start_item):
                return
            
            start_tags = list(self.tree.item(self.drag_start_item, "tags"))
            if "Dragging" in start_tags:
                start_tags.remove("Dragging")
                self.tree.item(self.drag_start_item, tags=tuple(start_tags))
        except (tk.TclError, AttributeError) as e:
            logger.debug(f"Failed to remove dragging tag: {e}")
    
    def _calculate_drag_direction(self, target_item: str, event_y: int) -> bool:
        """计算拖拽方向
        
        Args:
            target_item: 目标项目ID
            event_y: 鼠标Y坐标
            
        Returns:
            如果向下拖拽返回True，否则返回False
        """
        try:
            children = list(self.tree.get_children())
            if self.drag_start_item in children and target_item in children:
                start_index = children.index(self.drag_start_item)
                target_index = children.index(target_item)
                return target_index > start_index
            
            if self.drag_start_item:
                try:
                    if not self.tree.exists(self.drag_start_item):
                        return True
                    
                    start_bbox = self.tree.bbox(self.drag_start_item)
                    if start_bbox:
                        return event_y > start_bbox[1] + start_bbox[3] / 2
                except (tk.TclError, AttributeError):
                    pass
        except (tk.TclError, AttributeError):
            pass
        
        return True
    
    def _show_drag_indicator_line(self, target_item: str, is_dragging_down: bool) -> None:
        """显示拖动指示线
        
        Args:
            target_item: 目标项目ID
            is_dragging_down: 是否向下拖拽
        """
        if not self.drag_indicator_line:
            return
        
        try:
            if not self.tree.exists(target_item):
                return
            
            bbox = self.tree.bbox(target_item)
            if not bbox:
                return
            
            _, y, width, height = bbox
            tree_x = self.tree.winfo_x()
            tree_y = self.tree.winfo_y()
            
            line_y = tree_y + (y + height if is_dragging_down else y)
            
            if (self.current_indicator_target == target_item and
                self.current_indicator_position == line_y):
                tree_width = self.tree.winfo_width()
                self.drag_indicator_line.place(x=tree_x, y=line_y, width=tree_width, height=3)
                self.drag_indicator_line.lift()
                return
            
            self.current_indicator_target = target_item
            self.current_indicator_position = line_y
            tree_width = self.tree.winfo_width()
            self.drag_indicator_line.place(x=tree_x, y=line_y, width=tree_width, height=3)
            self.drag_indicator_line.lift()
        except (tk.TclError, AttributeError) as e:
            logger.debug(f"Failed to show drag indicator line: {e}")
    
    def _clear_drag_indicator(self) -> None:
        """清除拖拽指示线"""
        if self.drag_indicator_line:
            try:
                self.drag_indicator_line.place_forget()
            except (tk.TclError, AttributeError):
                pass
        
        self.current_indicator_target = None
        self.current_indicator_position = None
    
    def _is_edit_mode_enabled(self) -> bool:
        """检查编辑模式是否已启用
        
        Returns:
            如果编辑模式已启用返回True，否则返回False
        """
        return (self.edit_mode_manager is not None and
                self.edit_mode_manager.is_enabled)
    
    def _should_process_drag(self) -> bool:
        """检查是否应该处理拖拽
        
        Returns:
            如果应该处理返回True，否则返回False
        """
        if self.drag_start_item is None:
            return False
        
        if not self.is_dragging:
            return False
        
        try:
            return self.tree.exists(self.drag_start_item)
        except (tk.TclError, AttributeError):
            return False
    
    def _perform_drag_move(self, end_item: str) -> None:
        """执行拖拽移动操作
        
        Args:
            end_item: 目标项目ID
        """
        try:
            children = list(self.tree.get_children())
            if self.drag_start_item not in children or end_item not in children:
                logger.warning("Drag items not found in tree children")
                return
            
            start_tree_index = children.index(self.drag_start_item)
            end_tree_index = children.index(end_item)
            
            start_index = self._get_data_index(children, start_tree_index)
            end_index = self._get_data_index(children, end_tree_index)
            
            self.clear_drag_indicators()
            
            item_values = self.tree.item(self.drag_start_item)
            moved_item_id = item_values['tags'][0] if item_values.get('tags') else None
            checkbox_data = self.checkbox_manager.unregister_checkbox(self.drag_start_item)
            
            current_values = list(item_values.get('values', []))
            self.tree.delete(self.drag_start_item)
            children = list(self.tree.get_children())
            
            insert_index = end_tree_index if end_tree_index > start_tree_index else end_tree_index
            insert_index = max(0, min(insert_index, len(children)))
            
            new_item = self.tree.insert(
                "",
                insert_index,
                text=item_values.get('text', ''),
                values=tuple(current_values),
                tags=item_values.get('tags', ())
            )
            
            if checkbox_data:
                var, id_str = checkbox_data
                self.checkbox_manager.register_checkbox(new_item, id_str)
                self.update_checkbox_display_callback(new_item)
            
            self.screenshot_manager.move_item(start_index, end_index)
            is_moving_down = end_index > start_index
            
            self.load_screenshots_callback()
            
            if self.gallery_refresh_callback:
                try:
                    self.gallery_refresh_callback(start_index, end_index)
                except Exception as e:
                    logger.warning(f"Gallery refresh callback failed: {e}")
            
            if moved_item_id:
                moved_item = self._find_item_by_id(moved_item_id)
                if moved_item:
                    try:
                        self.tree.selection_set(moved_item)
                        self.tree.see(moved_item)
                        self.show_drag_indicator_on_item(moved_item, not is_moving_down)
                    except (tk.TclError, AttributeError) as e:
                        logger.debug(f"Failed to select moved item: {e}")
            
            children = list(self.tree.get_children())
            start_tree_idx_after_reload = self._get_tree_index_after_reload(children, start_index)
            if start_tree_idx_after_reload < len(children):
                item_at_start_pos = children[start_tree_idx_after_reload]
                try:
                    item_tags = self.tree.item(item_at_start_pos, "tags")
                    if item_tags and item_tags[0] != moved_item_id:
                        self.show_drag_indicator_on_item(item_at_start_pos, is_moving_down)
                except (tk.TclError, AttributeError) as e:
                    logger.debug(f"Failed to show indicator at start position: {e}")
        except (tk.TclError, AttributeError, ValueError, IndexError) as e:
            logger.error(f"Failed to perform drag move: {e}", exc_info=True)
    
    def _get_data_index(self, children: List[str], tree_index: int) -> int:
        """根据树索引计算数据索引
        
        Args:
            children: 所有子项目列表
            tree_index: 树索引
            
        Returns:
            数据索引
        """
        data_index = 0
        for i in range(tree_index):
            if i >= len(children):
                break
            
            item_id = children[i]
            try:
                item_tags = self.tree.item(item_id, "tags")
                if item_tags and ("PageHeaderLeft" not in item_tags and "PageHeaderRight" not in item_tags):
                    data_index += 1
            except (tk.TclError, AttributeError):
                pass
        
        return data_index
    
    def _get_tree_index_after_reload(self, children: List[str], data_index: int) -> int:
        """重新加载后根据数据索引计算树索引
        
        Args:
            children: 所有子项目列表
            data_index: 数据索引
            
        Returns:
            树索引
        """
        data_count = 0
        for i, item_id in enumerate(children):
            try:
                item_tags = self.tree.item(item_id, "tags")
                if item_tags and ("PageHeaderLeft" not in item_tags and "PageHeaderRight" not in item_tags):
                    if data_count == data_index:
                        return i
                    data_count += 1
            except (tk.TclError, AttributeError):
                pass
        
        return len(children)
    
    def _find_item_by_id(self, id_str: str) -> Optional[str]:
        """根据ID字符串查找项目
        
        Args:
            id_str: 截图ID字符串
            
        Returns:
            项目ID，如果不存在则返回None
        """
        try:
            for tree_item_id in self.tree.get_children():
                try:
                    item_tags = self.tree.item(tree_item_id, "tags")
                    if item_tags and item_tags[0] == id_str:
                        return tree_item_id
                except (tk.TclError, AttributeError):
                    continue
        except (tk.TclError, AttributeError):
            pass
        
        return None
    
    def clear_drag_indicators(self) -> None:
        """清除所有箭头指示器"""
        for item_id, original_text, after_id in self.drag_indicators:
            if after_id:
                try:
                    if self.root.winfo_exists():
                        self.root.after_cancel(after_id)
                except (ValueError, AttributeError, tk.TclError):
                    pass
            
            try:
                if self.tree.exists(item_id):
                    self._remove_indicator_from_item(item_id)
            except (tk.TclError, AttributeError):
                pass
        
        self.drag_indicators.clear()
    
    def show_drag_indicator_on_item(self, item_id: str, show_up_arrows: bool) -> None:
        """在指定item的名字前显示箭头指示器
        
        Args:
            item_id: Treeview项目ID
            show_up_arrows: 是否显示向上箭头，False显示向下箭头
        """
        try:
            if not self.tree.exists(item_id):
                return
            
            current_values = list(self.tree.item(item_id, "values"))
            if len(current_values) < 2:
                return
            
            original_text = current_values[1]
            
            if original_text.startswith("↑↑↑"):
                original_text = original_text[3:].lstrip()
            elif original_text.startswith("↓↓↓"):
                original_text = original_text[3:].lstrip()
            
            arrow_prefix = "↑↑↑" if show_up_arrows else "↓↓↓"
            style_tag = "DragIndicatorDown" if show_up_arrows else "DragIndicatorUp"
            
            new_text = f"{arrow_prefix} {original_text}"
            current_values[1] = new_text
            
            current_tags = list(self.tree.item(item_id, "tags"))
            if style_tag not in current_tags:
                current_tags.append(style_tag)
            
            self.tree.item(item_id, values=tuple(current_values), tags=tuple(current_tags))
            
            after_id = self.root.after(
                self.INDICATOR_TIMEOUT_MS,
                lambda: self._remove_indicator_from_item(item_id)
            )
            self.drag_indicators.append((item_id, original_text, after_id))
        except (tk.TclError, AttributeError, IndexError) as e:
            logger.debug(f"Failed to show drag indicator on item: {e}")
    
    def _remove_indicator_from_item(self, item_id: str) -> None:
        """从指定项目移除指示器
        
        Args:
            item_id: Treeview项目ID
        """
        try:
            if not self.tree.exists(item_id):
                return
            
            current_values = list(self.tree.item(item_id, "values"))
            if len(current_values) >= 2:
                info_text = current_values[1]
                if info_text.startswith("↑↑↑"):
                    info_text = info_text[3:].lstrip()
                elif info_text.startswith("↓↓↓"):
                    info_text = info_text[3:].lstrip()
                current_values[1] = info_text
                self.tree.item(item_id, values=tuple(current_values))
                
                current_tags = list(self.tree.item(item_id, "tags"))
                if "DragIndicatorUp" in current_tags:
                    current_tags.remove("DragIndicatorUp")
                if "DragIndicatorDown" in current_tags:
                    current_tags.remove("DragIndicatorDown")
                self.tree.item(item_id, tags=tuple(current_tags))
            
            self.drag_indicators = [
                (iid, orig, aid) for iid, orig, aid in self.drag_indicators
                if iid != item_id
            ]
        except (tk.TclError, AttributeError, IndexError) as e:
            logger.debug(f"Failed to remove indicator from item: {e}")
