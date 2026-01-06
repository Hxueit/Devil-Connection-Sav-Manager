"""通用可拖拽列表组件

提供轻量级的可拖拽排序列表功能，不依赖特定业务逻辑
"""

import logging
from typing import Optional, List, Callable, Any, Dict
import tkinter as tk
from tkinter import ttk

logger = logging.getLogger(__name__)


class DraggableList:
    """通用可拖拽列表组件
    
    提供Treeview的拖拽排序功能，不依赖特定业务逻辑
    """
    
    DRAG_THRESHOLD: int = 5
    
    def __init__(
        self,
        parent: tk.Widget,
        root: tk.Tk,
        data_items: List[Any],
        format_item: Callable[[Any, int], str],
        on_order_changed: Optional[Callable[[List[int]], None]] = None,
        get_cjk_font: Optional[Callable[[int], Any]] = None,
        colors_class: Optional[type] = None,
        translation_func: Optional[Callable[[str], str]] = None
    ) -> None:
        """初始化可拖拽列表
        
        Args:
            parent: 父容器
            root: 根窗口
            data_items: 数据项列表
            format_item: 格式化函数，接收(item, index)返回显示文本
            on_order_changed: 顺序改变回调，接收新索引列表
            get_cjk_font: 字体获取函数，可选
            colors_class: 颜色常量类，可选
        """
        if parent is None:
            raise ValueError("parent cannot be None")
        if root is None:
            raise ValueError("root cannot be None")
        if data_items is None:
            raise ValueError("data_items cannot be None")
        if format_item is None:
            raise ValueError("format_item cannot be None")
        
        self.parent = parent
        self.root = root
        self.data_items = data_items
        self.format_item = format_item
        self.on_order_changed = on_order_changed
        self.get_cjk_font = get_cjk_font or (lambda size: ("Arial", size))
        self.Colors = colors_class
        self.translate = translation_func or (lambda key: key)
        
        # 拖拽状态
        self.drag_start_item: Optional[str] = None
        self.drag_start_y: Optional[int] = None
        self.is_dragging: bool = False
        self.drag_target_item: Optional[str] = None
        self.current_indicator_target: Optional[str] = None
        self.current_indicator_position: Optional[int] = None
        
        # UI组件
        self.tree: Optional[ttk.Treeview] = None
        self.scrollbar: Optional[ttk.Scrollbar] = None
        self.drag_indicator_line: Optional[tk.Frame] = None
        
        # 当前顺序（索引列表）
        self._current_order: List[int] = list(range(len(data_items)))
        
        # 高亮相关
        self._highlighted_item: Optional[str] = None
        self._highlight_timer: Optional[str] = None
        
        self._create_ui()
        self._populate_list()
    
    def _create_ui(self) -> None:
        """创建UI组件"""
        # 创建框架
        frame = tk.Frame(self.parent)
        frame.pack(fill="both", expand=True)
        
        # 创建滚动条
        self.scrollbar = ttk.Scrollbar(frame, orient="vertical")
        self.scrollbar.pack(side="right", fill="y")
        
        # 创建Treeview
        tree_style = ttk.Style(self.root)
        tree_style.configure("Draggable.Treeview", rowheight=26, padding=(0, 6))
        
        self.tree = ttk.Treeview(
            frame,
            columns=("content",),
            show="headings",
            style="Draggable.Treeview",
            yscrollcommand=self.scrollbar.set
        )
        
        # 配置列
        self.tree.heading("#0", text="", anchor="w")
        self.tree.column("#0", width=0, stretch=False, minwidth=0)
        
        self.tree.heading("content", text="", anchor="w")
        self.tree.column("content", width=800, stretch=True)
        
        # 配置标签样式
        if self.Colors:
            self.tree.tag_configure("Dragging", background="#E3F2FD", foreground="#1976D2")
            # 高亮标签：淡蓝色背景
            self.tree.tag_configure("Highlighted", background="#E1F5FE", foreground="#01579B")
            page_header_font = self.get_cjk_font(10, "bold") if callable(self.get_cjk_font) else ("Arial", 10, "bold")
            self.tree.tag_configure("PageHeader", 
                foreground=self.Colors.TEXT_SECONDARY if hasattr(self.Colors, 'TEXT_SECONDARY') else "gray",
                font=page_header_font)
        else:
            self.tree.tag_configure("Dragging", background="#E3F2FD", foreground="#1976D2")
            # 高亮标签：淡蓝色背景
            self.tree.tag_configure("Highlighted", background="#E1F5FE", foreground="#01579B")
            self.tree.tag_configure("PageHeader", foreground="gray", font=("Arial", 10, "bold"))
        
        self.tree.pack(side="left", fill="both", expand=True)
        self.scrollbar.config(command=self.tree.yview)
        
        # 创建拖拽指示线
        self.drag_indicator_line = tk.Frame(frame, bg="black", height=3)
        self.drag_indicator_line.place_forget()
        
        # 绑定事件
        self.tree.bind('<Button-1>', self._on_button1_click)
        self.tree.bind('<B1-Motion>', self._on_drag_motion)
        self.tree.bind('<ButtonRelease-1>', self._on_drag_end)
    
    def _populate_list(self) -> None:
        """填充列表数据"""
        if not self.tree:
            return
        
        # 清空现有项
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 每页的项数（tyrano存档每页6个）
        items_per_page = 6
        page_number = 1
        item_count = 0
        
        # 按当前顺序添加项
        for idx in self._current_order:
            # 每页开始时添加页面标记
            if item_count % items_per_page == 0:
                self._insert_page_header(page_number)
            
            if idx < len(self.data_items):
                item = self.data_items[idx]
                text = self.format_item(item, idx)
                # 确保文本不为空（处理无存档的情况）
                if not text or text.strip() == "":
                    text = self.translate("tyrano_no_save") if hasattr(self, 'translate') else "无存档"
                item_id = self.tree.insert("", "end", text="", values=(text,), tags=(str(idx),))
                item_count += 1
                
                # 每页结束时增加页码
                if item_count % items_per_page == 0:
                    page_number += 1
    
    def _insert_page_header(self, page_number: int) -> None:
        """插入页面标记行
        
        Args:
            page_number: 页码
        """
        if not self.tree:
            return
        
        page_text = f"{self.translate('page')} {page_number}"
        try:
            self.tree.insert("", "end", text="", values=(page_text,), tags=("PageHeader",))
        except (tk.TclError, AttributeError):
            pass
    
    def _is_valid_item(self, item_id: str) -> bool:
        """检查项目是否为有效的数据项（非页眉）
        
        Args:
            item_id: Treeview项目ID
            
        Returns:
            如果是有效数据项返回True，否则返回False
        """
        if not item_id or not self.tree:
            return False
        
        try:
            if not self.tree.exists(item_id):
                return False
            
            item_tags = self.tree.item(item_id, "tags")
            if not item_tags:
                return True
            
            return "PageHeader" not in item_tags
        except (tk.TclError, AttributeError):
            return False
    
    def _on_button1_click(self, event: tk.Event) -> Optional[str]:
        """处理Button-1点击事件"""
        if not self.tree:
            return None
        
        item = self.tree.identify_row(event.y)
        if item and self._is_valid_item(item):
            self.drag_start_item = item
            self.drag_start_y = event.y
            self._reset_drag_state()
        
        return None
    
    def _on_drag_motion(self, event: tk.Event) -> None:
        """处理拖拽移动事件"""
        if not self.tree or self.drag_start_item is None:
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
    
    def _on_drag_end(self, event: tk.Event) -> None:
        """处理拖拽结束事件"""
        if not self.tree:
            return
        
        self._remove_dragging_tag()
        self._clear_drag_indicator()
        
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
    
    def _should_process_drag(self) -> bool:
        """检查是否应该处理拖拽"""
        if not self.tree or self.drag_start_item is None:
            return False
        
        if not self.is_dragging:
            return False
        
        try:
            return self.tree.exists(self.drag_start_item)
        except (tk.TclError, AttributeError):
            return False
    
    def _perform_drag_move(self, end_item: str) -> None:
        """执行拖拽移动操作"""
        if not self.tree:
            return
        
        try:
            children = list(self.tree.get_children())
            if self.drag_start_item not in children or end_item not in children:
                logger.warning("Drag items not found in tree children")
                return
            
            # 计算数据项在树中的实际索引（排除页面标记行）
            start_data_index = self._get_data_index_from_tree(children, self.drag_start_item)
            end_data_index = self._get_data_index_from_tree(children, end_item)
            
            if start_data_index is None or end_data_index is None:
                logger.warning("Failed to get data indices")
                return
            
            # 从当前顺序中取出要移动的索引
            moved_data_idx = self._current_order.pop(start_data_index)
            
            # 计算插入位置（如果向下移动，需要调整索引）
            if end_data_index > start_data_index:
                insert_pos = end_data_index
            else:
                insert_pos = end_data_index
            
            # 插入到新位置
            self._current_order.insert(insert_pos, moved_data_idx)
            
            # 重新填充列表以反映新顺序
            self._populate_list()
            
            # 高亮被移动的项目
            self._highlight_moved_item(insert_pos)
            
            # 调用回调
            if self.on_order_changed:
                self.on_order_changed(self._current_order.copy())
                
        except (tk.TclError, AttributeError, ValueError, IndexError) as e:
            logger.error(f"Failed to perform drag move: {e}", exc_info=True)
    
    def _get_data_index_from_tree(self, children: List[str], item_id: str) -> Optional[int]:
        """从树子项列表中获取数据项的索引（排除页面标记行）
        
        Args:
            children: 树的所有子项列表
            item_id: 要查找的项目ID
            
        Returns:
            数据项索引，如果未找到或不是数据项则返回None
        """
        data_count = 0
        for child_id in children:
            if child_id == item_id:
                # 检查是否是页面标记行
                try:
                    tags = self.tree.item(child_id, "tags")
                    if tags and "PageHeader" in tags:
                        return None
                    return data_count
                except (tk.TclError, AttributeError):
                    return None
            
            # 只计算非页面标记行的项
            try:
                tags = self.tree.item(child_id, "tags")
                if not tags or "PageHeader" not in tags:
                    data_count += 1
            except (tk.TclError, AttributeError):
                pass
        
        return None
    
    def _highlight_moved_item(self, data_index: int) -> None:
        """高亮被移动的项目
        
        Args:
            data_index: 被移动项目在新顺序中的索引
        """
        if not self.tree:
            return
        
        # 清除之前的高亮
        if self._highlighted_item:
            try:
                if self.tree.exists(self._highlighted_item):
                    tags = list(self.tree.item(self._highlighted_item, "tags"))
                    if "Highlighted" in tags:
                        tags.remove("Highlighted")
                        self.tree.item(self._highlighted_item, tags=tags)
            except (tk.TclError, AttributeError):
                pass
        
        # 取消之前的定时器
        if self._highlight_timer:
            try:
                self.root.after_cancel(self._highlight_timer)
            except (tk.TclError, ValueError):
                pass
            self._highlight_timer = None
        
        # 找到对应的树项
        children = list(self.tree.get_children())
        data_count = 0
        target_item = None
        
        for child_id in children:
            try:
                tags = self.tree.item(child_id, "tags")
                if not tags or "PageHeader" not in tags:
                    if data_count == data_index:
                        target_item = child_id
                        break
                    data_count += 1
            except (tk.TclError, AttributeError):
                continue
        
        if target_item:
            try:
                # 添加高亮标签
                tags = list(self.tree.item(target_item, "tags"))
                if "Highlighted" not in tags:
                    tags.append("Highlighted")
                    self.tree.item(target_item, tags=tags)
                
                self._highlighted_item = target_item
                
                # 滚动到可见位置
                self.tree.see(target_item)
                
                # 3秒后自动清除高亮
                def clear_highlight():
                    try:
                        if self._highlighted_item and self.tree.exists(self._highlighted_item):
                            tags = list(self.tree.item(self._highlighted_item, "tags"))
                            if "Highlighted" in tags:
                                tags.remove("Highlighted")
                                self.tree.item(self._highlighted_item, tags=tags)
                    except (tk.TclError, AttributeError):
                        pass
                    self._highlighted_item = None
                    self._highlight_timer = None
                
                self._highlight_timer = self.root.after(3000, clear_highlight)
            except (tk.TclError, AttributeError):
                pass
    
    def _calculate_drag_direction(self, target_item: str, event_y: int) -> bool:
        """计算拖拽方向"""
        if not self.tree or not self.drag_start_item:
            return True
        
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
        """显示拖动指示线"""
        if not self.tree or not self.drag_indicator_line:
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
    
    def _apply_dragging_tag(self) -> None:
        """应用拖拽标签"""
        if not self.tree or not self.drag_start_item:
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
        if not self.tree or not self.drag_start_item:
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
    
    def _reset_drag_state(self) -> None:
        """重置拖拽状态"""
        self.drag_target_item = None
        self.is_dragging = False
    
    def get_current_order(self) -> List[int]:
        """获取当前顺序（索引列表）"""
        return self._current_order.copy()
    
    def set_order(self, new_order: List[int]) -> None:
        """设置新的顺序"""
        if len(new_order) != len(self.data_items):
            logger.warning(f"Order length mismatch: {len(new_order)} != {len(self.data_items)}")
            return
        
        self._current_order = new_order.copy()
        self._populate_list()

