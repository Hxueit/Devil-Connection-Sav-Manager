"""Treeview 拖拽排序

TreeDragReorder  给任意 Treeview 加上「按住一行拖到另一行」的排序手势（截图列表使用）
DraggableList    基于它的现成可排序列表（Tyrano 存档重排对话框使用）
"""

from typing import Any, Callable, List, Optional

import tkinter as tk
from tkinter import ttk

from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import widget_alive

DRAG_THRESHOLD = 5  # 鼠标移动超过这么多像素才算开始拖拽
HIGHLIGHT_MS = 3000


class TreeDragReorder:
    """把 Treeview 上的拖拽手势翻译成 on_drop(from_index, to_index)

    index 只数「数据行」（is_data_row 返回 True 的行），页眉之类的辅助行不计。
    拖动时被拖的行加上 "Dragging" 标签，目标位置显示一条黑色指示线。
    事件用 add="+" 绑定：如果调用方先绑定的 <Button-1> 返回 "break"，这里就不会开始拖拽。
    """

    def __init__(self, tree: ttk.Treeview, is_data_row: Callable[[str], bool],
                 on_drop: Callable[[int, int], None], can_drag: Callable[[], bool] = lambda: True) -> None:
        self.tree = tree
        self.is_data_row = is_data_row
        self.on_drop = on_drop
        self.can_drag = can_drag
        self._start_item: Optional[str] = None
        self._start_y = 0
        self._dragging = False
        # 指示线放在 Treeview 的父容器里，用 place 叠在树上面
        self._line = tk.Frame(tree.master, bg="black", height=3)

        tree.tag_configure("Dragging", background="#E3F2FD", foreground="#1976D2")
        tree.bind('<Button-1>', self._on_press, add="+")
        tree.bind('<B1-Motion>', self._on_motion, add="+")
        tree.bind('<ButtonRelease-1>', self._on_release, add="+")

    def _is_row(self, item: str) -> bool:
        return bool(item) and self.tree.exists(item) and self.is_data_row(item)

    def _on_press(self, event: tk.Event) -> None:
        item = self.tree.identify_row(event.y)
        self._start_item = item if self._is_row(item) else None
        self._start_y = event.y
        self._dragging = False

    def _on_motion(self, event: tk.Event) -> None:
        if self._start_item is None:
            return
        if not self.can_drag():
            self._finish()
            return
        if not self._dragging:
            if abs(event.y - self._start_y) <= DRAG_THRESHOLD:
                return
            self._dragging = True
            self._set_dragging_tag(True)

        target = self.tree.identify_row(event.y)
        bbox = self.tree.bbox(target) if target != self._start_item and self._is_row(target) else None
        if not bbox:
            self._line.place_forget()
            return
        _, y, _, height = bbox
        children = self.tree.get_children()
        below = children.index(target) > children.index(self._start_item)
        self._line.place(x=self.tree.winfo_x(), y=self.tree.winfo_y() + (y + height if below else y),
                         width=self.tree.winfo_width(), height=3)
        self._line.lift()

    def _on_release(self, event: tk.Event) -> None:
        start, was_dragging = self._start_item, self._dragging
        self._finish()
        if not was_dragging or start is None or not self.tree.exists(start) or not self.can_drag():
            return
        target = self.tree.identify_row(event.y)
        if target != start and self._is_row(target):
            self.on_drop(self.data_index(start), self.data_index(target))

    def _finish(self) -> None:
        self._set_dragging_tag(False)
        self._line.place_forget()
        self._start_item = None
        self._dragging = False

    def _set_dragging_tag(self, on: bool) -> None:
        item = self._start_item
        if not item or not self.tree.exists(item):
            return
        tags = [tag for tag in self.tree.item(item, "tags") if tag != "Dragging"]
        if on:
            tags.append("Dragging")
        self.tree.item(item, tags=tags)

    def data_index(self, item: str) -> int:
        """item 是第几个数据行"""
        index = 0
        for child in self.tree.get_children():
            if child == item:
                return index
            if self.is_data_row(child):
                index += 1
        raise ValueError(f"{item} is not in the tree")


class DraggableList:
    """可拖拽排序的列表，每 items_per_page 项插入一行页码

    format_item(数据, 原始索引) 返回每一行显示的文字。
    顺序用「原始索引列表」表示，改变后调用 on_order_changed(新顺序)。
    """

    def __init__(
        self,
        parent: tk.Widget,
        root: tk.Tk,
        data_items: List[Any],
        format_item: Callable[[Any, int], str],
        on_order_changed: Callable[[List[int]], None],
        t: Callable[..., str],
        items_per_page: int = 6,
    ) -> None:
        self.root = root
        self.data_items = data_items
        self.format_item = format_item
        self.on_order_changed = on_order_changed
        self.t = t
        self.items_per_page = items_per_page
        self._current_order: List[int] = list(range(len(data_items)))
        self._highlight_timer: Optional[str] = None

        frame = tk.Frame(parent)
        frame.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        ttk.Style(root).configure("Draggable.Treeview", rowheight=26, padding=(0, 6))
        self.tree = ttk.Treeview(frame, columns=("content",), show="headings",
                                 style="Draggable.Treeview", yscrollcommand=scrollbar.set)
        self.tree.heading("content", text="", anchor="w")
        self.tree.column("content", width=800, stretch=True)
        self.tree.tag_configure("Highlighted", background="#E1F5FE", foreground="#01579B")
        self.tree.tag_configure("PageHeader", foreground=Colors.TEXT_SECONDARY,
                                font=get_cjk_font(10, "bold"))
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.tree.yview)

        self._drag = TreeDragReorder(self.tree, self._is_data_row, self._move)
        self._populate_list()

    def _is_data_row(self, item: str) -> bool:
        return "PageHeader" not in self.tree.item(item, "tags")

    def _populate_list(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for count, idx in enumerate(self._current_order):
            if count % self.items_per_page == 0:
                page_text = f"{self.t('page')} {count // self.items_per_page + 1}"
                self.tree.insert("", "end", values=(page_text,), tags=("PageHeader",))
            text = self.format_item(self.data_items[idx], idx)
            self.tree.insert("", "end", values=(text,))

    def _move(self, from_index: int, to_index: int) -> None:
        self._current_order.insert(to_index, self._current_order.pop(from_index))
        self._populate_list()
        self._highlight(to_index)
        self.on_order_changed(self._current_order.copy())

    def _highlight(self, data_index: int) -> None:
        """高亮刚移动的行，3 秒后恢复"""
        if self._highlight_timer:
            self.root.after_cancel(self._highlight_timer)
        rows = [item for item in self.tree.get_children() if self._is_data_row(item)]
        item = rows[data_index]
        self.tree.item(item, tags=(*self.tree.item(item, "tags"), "Highlighted"))
        self.tree.see(item)

        def clear() -> None:
            self._highlight_timer = None
            if widget_alive(self.tree) and self.tree.exists(item):
                tags = [tag for tag in self.tree.item(item, "tags") if tag != "Highlighted"]
                self.tree.item(item, tags=tags)

        self._highlight_timer = self.root.after(HIGHLIGHT_MS, clear)
