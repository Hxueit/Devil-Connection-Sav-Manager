import tkinter as tk
from tkinter import filedialog, messagebox, Listbox, Scrollbar, Toplevel, Entry, Button, Label
from tkinter import ttk
from PIL import Image
from PIL import ImageTk
import base64
import json
import urllib.parse
import os
import random
import string
from datetime import datetime
import tempfile
import zipfile
import shutil
import sv_ttk

class SavTool:
    def __init__(self, root):
        self.root = root
        self.root.title("DevilConnection Screenshot Tool")
        self.root.geometry("800x600")
        
        # 应用 sun valley 亮色主题
        sv_ttk.set_theme("light")

        # 路径选择
        ttk.Label(root, text="选择_storage/目录:").pack(pady=5)
        self.dir_label = ttk.Label(root, text="未选择", width=100)
        self.dir_label.pack()
        ttk.Button(root, text="浏览目录", command=self.select_dir).pack(pady=5)

        # 截图列表
        list_header_frame = tk.Frame(root)
        list_header_frame.pack(pady=5, fill="x")
        list_header_frame.columnconfigure(0, weight=1)  
        list_header_frame.columnconfigure(2, weight=1)  
        
        left_spacer = tk.Frame(list_header_frame)
        left_spacer.grid(row=0, column=0, sticky="ew")
        
        # 左侧：标题（全选复选框会在Treeview的header中）
        left_header = tk.Frame(list_header_frame)
        left_header.grid(row=0, column=1)
        ttk.Label(left_header, text="截图列表:").pack(side="left", padx=5)
        
        # 右侧区域
        right_area = tk.Frame(list_header_frame)
        right_area.grid(row=0, column=2, sticky="ew")
        right_area.columnconfigure(0, weight=1) 
        
        right_spacer = tk.Frame(right_area)
        right_spacer.grid(row=0, column=0, sticky="ew")
        
        # 右侧按钮区域
        button_container = tk.Frame(right_area)
        button_container.grid(row=0, column=1, sticky="e")
        ttk.Button(button_container, text="⟳", command=self.load_screenshots, width=3).pack(side="left", padx=2)
        ttk.Button(button_container, text="正序", command=self.sort_ascending).pack(side="left", padx=2)
        ttk.Button(button_container, text="倒序", command=self.sort_descending).pack(side="left", padx=2)
        
        # 创建包含预览和列表的容器
        list_frame = tk.Frame(root)
        list_frame.pack(pady=5)
        
        # 预览区域（左侧）
        preview_frame = tk.Frame(list_frame)
        preview_frame.pack(side="left", padx=5)
        ttk.Label(preview_frame, text="预览", font=("Arial", 10)).pack()

        # 限制预览Label的大小
        preview_container = tk.Frame(preview_frame, width=160, height=120, bg="lightgray", relief="sunken")
        preview_container.pack()
        preview_container.pack_propagate(False) 
        self.preview_label = Label(preview_container, bg="lightgray")
        self.preview_label.pack(fill="both", expand=True)
        self.preview_photo = None
        
        # 导出图片按钮（初始隐藏）
        self.export_button = ttk.Button(preview_frame, text="导出图片", command=self.export_image)
        self.export_button.pack(pady=5)
        self.export_button.pack_forget()
        
        # 批量导出图片按钮（初始隐藏）
        self.batch_export_button = ttk.Button(preview_frame, text="批量导出图片", command=self.batch_export_images)
        self.batch_export_button.pack(pady=5)
        self.batch_export_button.pack_forget() 
        
        # 列表区域（右侧）
        list_right_frame = tk.Frame(list_frame)
        list_right_frame.pack(side="right")
        
        # 使用Treeview替代Listbox，支持复选框
        tree_frame = tk.Frame(list_right_frame)
        tree_frame.pack(side="left", fill="both", expand=True)
        
        scrollbar = Scrollbar(tree_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        
        # 使用两列：select列用于复选框，info列用于信息
        self.tree = ttk.Treeview(tree_frame, columns=("select", "info"), show="headings", height=15)
        # 隐藏#0列（tree列）
        self.tree.heading("#0", text="", anchor="w")
        self.tree.column("#0", width=0, stretch=False, minwidth=0)
        
        # 复选框列（标题是全选复选框）
        self.tree.heading("select", text="☐", anchor="center", command=self.toggle_select_all)
        self.tree.column("select", width=40, stretch=False, anchor="center")
        
        # 信息列
        self.tree.heading("info", text="ID - 文件名 - 时间", anchor="w")
        self.tree.column("info", width=600, stretch=True)
        
        # 配置tag样式用于显示带颜色的箭头指示器
        # 使用tag_configure来设置不同tag的颜色
        self.tree.tag_configure("DragIndicatorUp", foreground="#85A9A5")
        self.tree.tag_configure("DragIndicatorDown", foreground="#D06CAA")
        
        scrollbar.config(command=self.tree.yview)
        self.tree.config(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        
        # 存储复选框状态 {item_id: BooleanVar}
        self.checkbox_vars = {}
        
        # 绑定选择事件（用于预览）
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        
        # 拖拽相关变量
        self.drag_start_item = None
        self.drag_start_y = None
        self.is_dragging = False
        
        # 箭头指示器相关变量
        self.drag_indicators = []  # 存储当前显示的指示器信息 [(item_id, original_text, after_id), ...]
        
        # 绑定事件：统一处理点击事件，先检查复选框，再处理拖拽
        self.tree.bind('<Button-1>', self.on_button1_click)
        self.tree.bind('<B1-Motion>', self.on_drag_motion)
        self.tree.bind('<ButtonRelease-1>', self.on_drag_end)

        # 操作按钮
        button_frame = ttk.Frame(root)
        button_frame.pack(pady=5)
        ttk.Button(button_frame, text="+ 新增截图", command=self.add_new).pack(side='left', padx=5)
        self.replace_button = ttk.Button(button_frame, text="⇋ 替换选中截图", command=self.replace_selected)
        self.replace_button.pack(side='left', padx=5)
        ttk.Button(button_frame, text="✖ 删除选中截图", command=self.delete_selected).pack(side='left', padx=5)

        self.storage_dir = None
        self.ids_data = []
        self.all_ids_data = []
        self.sav_pairs = {}  # {id: (main_sav, thumb_sav)}

    def select_dir(self):
        dir_path = filedialog.askdirectory()
        if dir_path and dir_path.endswith('/_storage'):
            self.storage_dir = dir_path
            self.dir_label.config(text=dir_path)
            self.load_screenshots()
            # 更新批量导出按钮状态
            self.update_batch_export_button()
        else:
            messagebox.showerror("错误", "目录必须以/_storage结尾！")

    def load_screenshots(self):
        if not self.storage_dir:
            return

        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')

        if not (os.path.exists(ids_path) and os.path.exists(all_ids_path)):
            messagebox.showerror("错误", "缺少ids.sav或all_ids.sav！")
            return

        # 加载 ids 和 all_ids
        self.ids_data = self.load_and_decode(ids_path)
        self.all_ids_data = self.load_and_decode(all_ids_path)

        # 扫描 sav 对
        self.sav_pairs = {}
        for file in os.listdir(self.storage_dir):
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

        # 更新列表
        # 清除所有项目
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.checkbox_vars.clear()
        
        # 添加复选框和项目
        for item in self.ids_data:
            id_str = item['id']
            date_str = item['date']
            main_file = self.sav_pairs.get(id_str, [None, None])[0] or "缺失主文件"
            display = f"{id_str} - {main_file} - {date_str}"
            
            # 创建复选框变量
            var = tk.BooleanVar()
            var.trace('w', lambda *args, v=var, iid=id_str: self.on_checkbox_change(v, iid))
            
            # 插入Treeview项目（select列显示复选框，info列显示信息）
            item_id = self.tree.insert("", tk.END, text="", values=("", display), tags=(id_str,))
            self.checkbox_vars[item_id] = (var, id_str)
            
            # 更新复选框显示
            self.update_checkbox_display(item_id)
        
        # 更新全选标题显示
        self.update_select_all_header()

    def sort_ascending(self):
        """按时间正序排序"""
        if not self.storage_dir:
            messagebox.showerror("错误", "请先选择目录！")
            return
        
        # 确认对话框
        result = messagebox.askyesno(
            "确认排序",
            "注意:改变该排序也会改变截图在游戏画廊中的显示顺序，是否确定？",
            icon='warning'
        )
        
        if not result:
            return
        
        # 按时间正序排序
        self.ids_data.sort(key=lambda x: datetime.strptime(x['date'], '%Y/%m/%d %H:%M:%S'), reverse=False)
        
        # 更新all_ids_data的顺序
        self.all_ids_data = [item['id'] for item in self.ids_data]
        
        # 保存到文件
        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
        self.encode_and_save(self.ids_data, ids_path)
        self.encode_and_save(self.all_ids_data, all_ids_path)
        
        # 重新加载列表以更新显示
        self.load_screenshots()
        
        messagebox.showinfo("成功", "已按正序排序并保存！")

    def sort_descending(self):
        """按时间倒序排序"""
        if not self.storage_dir:
            messagebox.showerror("错误", "请先选择目录！")
            return
        
        # 确认对话框
        result = messagebox.askyesno(
            "确认排序",
            "注意:改变该排序也会改变截图在游戏画廊中的显示顺序，是否确定？",
            icon='warning'
        )
        
        if not result:
            return
        
        # 按时间倒序排序
        self.ids_data.sort(key=lambda x: datetime.strptime(x['date'], '%Y/%m/%d %H:%M:%S'), reverse=True)
        
        # 更新all_ids_data的顺序
        self.all_ids_data = [item['id'] for item in self.ids_data]
        
        # 保存到文件
        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
        self.encode_and_save(self.ids_data, ids_path)
        self.encode_and_save(self.all_ids_data, all_ids_path)
        
        # 重新加载列表以更新显示
        self.load_screenshots()
        
        messagebox.showinfo("成功", "已按倒序排序并保存！")

    def update_checkbox_display(self, item_id):
        """更新复选框显示"""
        if item_id in self.checkbox_vars:
            var, id_str = self.checkbox_vars[item_id]
            checkbox_text = "☑" if var.get() else "☐"
            # 更新select列的值
            current_values = list(self.tree.item(item_id, "values"))
            if len(current_values) >= 2:
                current_values[0] = checkbox_text
                self.tree.item(item_id, values=tuple(current_values))
    
    def on_checkbox_change(self, var, id_str):
        """复选框状态变化时的处理"""
        # 更新显示
        for item_id, (v, iid) in self.checkbox_vars.items():
            if iid == id_str:
                self.update_checkbox_display(item_id)
                break
        
        # 更新全选复选框状态
        self.update_select_all_state()
        
        # 更新按钮状态
        self.update_button_states()
        
        # 更新批量导出按钮显示
        self.update_batch_export_button()
    
    def update_select_all_state(self):
        """更新全选复选框状态"""
        # 更新标题显示
        self.update_select_all_header()
    
    def toggle_select_all(self):
        """全选/取消全选"""
        # 检查当前是否全选
        if not self.checkbox_vars:
            return
        
        all_selected = all(var.get() for var, _ in self.checkbox_vars.values())
        select_all = not all_selected  # 切换状态
        
        for var, _ in self.checkbox_vars.values():
            var.set(select_all)
        # 更新所有复选框显示
        for item_id in self.checkbox_vars.keys():
            self.update_checkbox_display(item_id)
        # 更新标题显示
        self.update_select_all_header()
        self.update_button_states()
        self.update_batch_export_button()
    
    def update_select_all_header(self):
        """更新全选标题显示"""
        if not self.checkbox_vars:
            self.tree.heading("select", text="☐", anchor="center", command=self.toggle_select_all)
            return
        
        all_selected = all(var.get() for var, _ in self.checkbox_vars.values())
        checkbox_text = "☑" if all_selected else "☐"
        self.tree.heading("select", text=checkbox_text, anchor="center", command=self.toggle_select_all)
    
    def get_selected_ids(self):
        """获取所有选中的ID列表"""
        selected_ids = []
        for var, id_str in self.checkbox_vars.values():
            if var.get():
                selected_ids.append(id_str)
        return selected_ids
    
    def get_selected_count(self):
        """获取选中的数量"""
        return len(self.get_selected_ids())
    
    def update_button_states(self):
        """更新按钮状态"""
        selected_count = self.get_selected_count()
        # 如果选择了大于等于2个，禁用替换按钮
        if selected_count >= 2:
            self.replace_button.config(state="disabled")
        else:
            self.replace_button.config(state="normal")
    
    def update_batch_export_button(self):
        """更新批量导出按钮显示"""
        if not self.storage_dir:
            self.batch_export_button.pack_forget()
            return
        
        selected_count = self.get_selected_count()
        if selected_count > 0:
            self.batch_export_button.pack(pady=5)
        else:
            self.batch_export_button.pack_forget()
    
    def on_tree_select(self, event):
        """处理Treeview选择事件，显示预览"""
        selected = self.tree.selection()
        if not selected:
            # 清空预览
            self.preview_label.config(image='', bg="lightgray")
            self.preview_photo = None
            # 隐藏导出按钮
            self.export_button.pack_forget()
            return
        
        item_id = selected[0]
        if item_id in self.checkbox_vars:
            _, id_str = self.checkbox_vars[item_id]
            self.show_preview(id_str)
            # 显示导出按钮
            self.export_button.pack(pady=5)
    
    def on_button1_click(self, event):
        """统一处理Button-1点击事件：先检查复选框，再处理拖拽"""
        region = self.tree.identify_region(event.x, event.y)
        
        # 检查是否是复选框点击
        if region == "cell":
            column = self.tree.identify_column(event.x)  # 只传x坐标
            # 检查是否是select列（复选框列）
            # ***即使#0列被隐藏，仍然存在，所以select列是#1*** ★
            # 为了兼容性，也检查x坐标范围（select列宽度是40）
            if column == "#1" or (event.x < 40 and event.x > 0):
                item_id = self.tree.identify_row(event.y)
                if item_id and item_id in self.checkbox_vars:
                    var, _ = self.checkbox_vars[item_id]
                    var.set(not var.get())
                    # 阻止后续事件处理（包括拖拽和选择）
                    return "break"
        elif region == "heading":
            column = self.tree.identify_column(event.x)
            if column == "#1" or (event.x < 40 and event.x > 0): 
                # toggle_select_all 已经在 heading 的 command 中处理了
                # 不返回 "break"，让 command 回调正常执行
                # 但阻止拖拽
                self.drag_start_item = None
                return
        
        # 如果不是复选框点击，则处理拖拽
        # 获取鼠标点击位置对应的列表项
        item = self.tree.identify_row(event.y)
        if item:
            self.drag_start_item = item
            self.drag_start_y = event.y
            self.is_dragging = False

    def on_drag_motion(self, event):
        """拖拽过程中，检测是否真的在拖拽"""
        if self.drag_start_item is not None:
            # 检测鼠标是否移动了至少5像素
            if abs(event.y - self.drag_start_y) > 5:
                self.is_dragging = True
                # 获取当前鼠标位置对应的列表项（用于视觉反馈，但不做高亮处理）
                # Treeview的set方法只能设置列值，不能设置自定义属性
                # 如果需要高亮效果，可以使用tags和样式，但会增加复杂度
                # 这里暂时移除高亮功能，因为拖拽功能本身已经正常工作

    def on_drag_end(self, event):
        """结束拖拽，移动项目并保存顺序"""
        if self.drag_start_item is None:
            return
        
        # 如果没有真正拖拽（只是单击），不执行移动操作
        if not self.is_dragging:
            self.drag_start_item = None
            self.drag_start_y = None
            self.is_dragging = False
            return
        
        # 获取目标位置
        end_item = self.tree.identify_row(event.y)
        
        if not end_item or end_item == self.drag_start_item:
            self.drag_start_item = None
            self.drag_start_y = None
            self.is_dragging = False
            return
        
        # 获取起始和目标索引
        children = list(self.tree.get_children())
        start_index = children.index(self.drag_start_item)
        end_index = children.index(end_item)
        
        # 清除之前的箭头指示器
        self.clear_drag_indicators()
        
        # 移动Treeview中的项目
        item_values = self.tree.item(self.drag_start_item)
        moved_item_id = item_values['tags'][0] if item_values['tags'] else None
        
        # 获取目标位置原来的item ID（用于显示箭头）
        target_original_id = None
        if end_item:
            target_item_values = self.tree.item(end_item)
            target_original_id = target_item_values['tags'][0] if target_item_values['tags'] else None
        
        # 保存复选框状态和值
        checkbox_data = None
        checkbox_text = ""
        if self.drag_start_item in self.checkbox_vars:
            checkbox_data = self.checkbox_vars.pop(self.drag_start_item)
            var, _ = checkbox_data
            checkbox_text = "☑" if var.get() else "☐"
        
        # 保存当前值
        current_values = list(item_values['values'])
        
        # 删除项目
        self.tree.delete(self.drag_start_item)
        
        # 重新获取children列表（因为删除了一个项目，索引会变化）
        children = list(self.tree.get_children())
        
        # 重新插入到目标位置
        # 注意：删除后，如果向下移动，end_index需要减1（因为删除了start_index的项目）
        if end_index > start_index:
            # 向下移动：删除后，目标位置索引减1
            insert_index = end_index - 1
            if insert_index < 0:
                insert_index = 0
            if insert_index < len(children):
                # 在指定位置之前插入
                new_item = self.tree.insert("", insert_index, text=item_values['text'], values=tuple(current_values), tags=item_values['tags'])
            else:
                # 插入到末尾
                new_item = self.tree.insert("", tk.END, text=item_values['text'], values=tuple(current_values), tags=item_values['tags'])
        else:
            # 向上移动：目标位置不变
            if end_index < len(children):
                new_item = self.tree.insert("", end_index, text=item_values['text'], values=tuple(current_values), tags=item_values['tags'])
            else:
                new_item = self.tree.insert("", tk.END, text=item_values['text'], values=tuple(current_values), tags=item_values['tags'])
        
        # 恢复复选框状态
        if checkbox_data:
            self.checkbox_vars[new_item] = checkbox_data
            self.update_checkbox_display(new_item)
        
        # 同步更新ids_data和all_ids_data的顺序
        moved_item = self.ids_data.pop(start_index)
        self.ids_data.insert(end_index, moved_item)
        
        # 更新all_ids_data的顺序
        new_all_ids_order = [item['id'] for item in self.ids_data]
        self.all_ids_data = new_all_ids_order
        
        # 保存更新后的顺序到文件
        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
        self.encode_and_save(self.ids_data, ids_path)
        self.encode_and_save(self.all_ids_data, all_ids_path)
        
        # 保存移动的item的ID（用于重新加载后恢复选择）
        moved_id = moved_item_id  
        
        # 记录移动方向（用于显示箭头指示器）
        is_moving_down = end_index > start_index
        
        # 重新加载列表以更新显示
        self.load_screenshots()
        
        # 恢复选择：根据ID找到新的item
        moved_item = None
        target_item = None
        if moved_id:
            children = list(self.tree.get_children())
            for tree_item_id in children:
                item_tags = self.tree.item(tree_item_id, "tags")
                if item_tags and item_tags[0] == moved_id:
                    moved_item = tree_item_id
                    self.tree.selection_set(tree_item_id)
                    # 滚动到选中项
                    self.tree.see(tree_item_id)
                elif target_original_id and item_tags and item_tags[0] == target_original_id:
                    target_item = tree_item_id
        
        # 显示箭头指示器
        if moved_item:
            # 被移动的项：向下移动显示↓↓↓（绿色），向上移动显示↑↑↑（粉色）
            self.show_drag_indicator_on_item(moved_item, not is_moving_down)
        if target_item and target_item != moved_item:
            # 目标位置的项：向下移动显示↑↑↑（绿色），向上移动显示↓↓↓（粉色）
            self.show_drag_indicator_on_item(target_item, is_moving_down)
        
        self.drag_start_item = None
        self.drag_start_y = None
        self.is_dragging = False
    
    def clear_drag_indicators(self):
        """清除所有箭头指示器"""
        for item_id, original_text, after_id in self.drag_indicators:
            try:
                # 取消定时器
                if after_id:
                    self.root.after_cancel(after_id)
                # 恢复原始文本
                if self.tree.exists(item_id):
                    current_values = list(self.tree.item(item_id, "values"))
                    if len(current_values) >= 2:
                        # 移除箭头前缀，恢复原始文本
                        info_text = current_values[1]
                        # 移除箭头前缀（↑↑↑或↓↓↓）
                        if info_text.startswith("↑↑↑"):
                            info_text = info_text[3:].lstrip()
                        elif info_text.startswith("↓↓↓"):
                            info_text = info_text[3:].lstrip()
                        current_values[1] = info_text
                        self.tree.item(item_id, values=tuple(current_values))
                        # 移除tag
                        current_tags = list(self.tree.item(item_id, "tags"))
                        if "DragIndicatorUp" in current_tags:
                            current_tags.remove("DragIndicatorUp")
                        if "DragIndicatorDown" in current_tags:
                            current_tags.remove("DragIndicatorDown")
                        self.tree.item(item_id, tags=tuple(current_tags))
            except:
                pass
        self.drag_indicators.clear()
    
    def show_drag_indicator_on_item(self, item_id, show_up_arrows):
        """在指定item的名字前显示箭头指示器"""
        if not self.tree.exists(item_id):
            return
        
        # 获取当前值
        current_values = list(self.tree.item(item_id, "values"))
        if len(current_values) < 2:
            return
        
        original_text = current_values[1]  # 保存原始文本
        
        # 确定箭头符号和颜色
        if show_up_arrows:
            # 显示↑↑↑（粉色 #D06CAA）
            arrow_prefix = "↑↑↑"
            style_tag = "DragIndicatorDown"  # 注意：向上箭头用粉色tag
        else:
            # 显示↓↓↓（绿色 #85A9A5）
            arrow_prefix = "↓↓↓"
            style_tag = "DragIndicatorUp"  # 注意：向下箭头用绿色tag
        
        # 在名字前添加箭头
        new_text = f"{arrow_prefix} {original_text}"
        current_values[1] = new_text
        
        # 更新item
        current_tags = list(self.tree.item(item_id, "tags"))
        if style_tag not in current_tags:
            current_tags.append(style_tag)
        self.tree.item(item_id, values=tuple(current_values), tags=tuple(current_tags))
        
        # 设置15秒后自动清除
        def remove_indicator():
            try:
                if self.tree.exists(item_id):
                    current_values = list(self.tree.item(item_id, "values"))
                    if len(current_values) >= 2:
                        info_text = current_values[1]
                        # 移除箭头前缀
                        if info_text.startswith("↑↑↑"):
                            info_text = info_text[3:].lstrip()
                        elif info_text.startswith("↓↓↓"):
                            info_text = info_text[3:].lstrip()
                        current_values[1] = info_text
                        self.tree.item(item_id, values=tuple(current_values))
                        # 移除tag
                        current_tags = list(self.tree.item(item_id, "tags"))
                        if "DragIndicatorUp" in current_tags:
                            current_tags.remove("DragIndicatorUp")
                        if "DragIndicatorDown" in current_tags:
                            current_tags.remove("DragIndicatorDown")
                        self.tree.item(item_id, tags=tuple(current_tags))
                # 从列表中移除
                self.drag_indicators = [(iid, orig, aid) for iid, orig, aid in self.drag_indicators if iid != item_id]
            except:
                pass
        
        after_id = self.root.after(15000, remove_indicator)  # 15秒后移除
        
        # 记录指示器信息
        self.drag_indicators.append((item_id, original_text, after_id))

    def show_preview(self, id_str):
        """显示指定ID的预览图片"""
        if not self.storage_dir or id_str not in self.sav_pairs:
            self.preview_label.config(image='', bg="lightgray")
            self.preview_photo = None
            return
        
        main_file = self.sav_pairs[id_str][0]
        if not main_file:
            self.preview_label.config(image='', bg="lightgray", text="文件缺失")
            self.preview_photo = None
            return
        
        main_sav = os.path.join(self.storage_dir, main_file)
        if not os.path.exists(main_sav):
            self.preview_label.config(image='', bg="lightgray", text="文件不存在")
            self.preview_photo = None
            return
        
        temp_png = None
        try:
            # 解码主 .sav 获取 PNG 数据
            with open(main_sav, 'r', encoding='utf-8') as f:
                encoded = f.read().strip()
            unquoted = urllib.parse.unquote(encoded)
            data_uri = json.loads(unquoted)
            b64_part = data_uri.split(';base64,', 1)[1]
            img_data = base64.b64decode(b64_part)
            
            # 保存到临时 PNG 文件
            temp_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
            with open(temp_png, 'wb') as f:
                f.write(img_data)
            
            # 加载图片
            img = Image.open(temp_png)
            # 拉伸到4:3比例(实际游戏内显示也会拉成这样)
            preview_img = img.resize((160, 120), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(preview_img)
            
            # 更新预览Label
            self.preview_label.config(image=photo, bg="white", text="")
            self.preview_photo = photo 
            
            img.close()
        except Exception as e:
            # 出错时显示错误信息
            self.preview_label.config(image='', bg="lightgray", text="预览失败")
            self.preview_photo = None
        finally:
            # 清理临时文件
            if temp_png and os.path.exists(temp_png):
                try:
                    os.remove(temp_png)
                except:
                    pass

    def load_and_decode(self, sav_path):
        with open(sav_path, 'r', encoding='utf-8') as f:
            encoded = f.read().strip()
        unquoted = urllib.parse.unquote(encoded)
        return json.loads(unquoted)

    def encode_and_save(self, data, sav_path):
        json_str = json.dumps(data)
        encoded = urllib.parse.quote(json_str)
        with open(sav_path, 'w', encoding='utf-8') as f:
            f.write(encoded)

    def replace_selected(self):
        # 获取选中的ID（通过Treeview选择或复选框）
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror("错误", "请选择一个截图！")
            return
        
        item_id = selected[0]
        if item_id not in self.checkbox_vars:
            messagebox.showerror("错误", "无效的选择！")
            return
        
        _, id_str = self.checkbox_vars[item_id]

        if id_str not in self.sav_pairs or self.sav_pairs[id_str][0] is None or self.sav_pairs[id_str][1] is None:
            messagebox.showerror("错误", "文件缺失，无法替换！")
            return

        new_png = filedialog.askopenfilename(title="选择新图片文件")
        if not new_png:
            return

        main_sav = os.path.join(self.storage_dir, self.sav_pairs[id_str][0])
        thumb_sav = os.path.join(self.storage_dir, self.sav_pairs[id_str][1])
        
        confirmed = False
        
        # 解码主 .sav 获取 PNG 数据
        with open(main_sav, 'r', encoding='utf-8') as f:
            encoded = f.read().strip()
        unquoted = urllib.parse.unquote(encoded)
        data_uri = json.loads(unquoted)
        b64_part = data_uri.split(';base64,', 1)[1]
        img_data = base64.b64decode(b64_part)

        # 保存到临时 PNG 文件
        temp_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
        with open(temp_png, 'wb') as f:
            f.write(img_data)

        # 确认替换窗口
        popup = Toplevel(self.root)
        popup.title("警告：确认替换")
        ttk.Label(popup, text="你即将进行以下替换操作：", font=("Arial", 12)).pack(pady=10)
        
        # 图片对比区域
        image_frame = tk.Frame(popup)
        image_frame.pack(pady=10)
        
        # 原图片（左侧）
        orig_img = Image.open(temp_png)
        orig_preview = orig_img.resize((400, 300), Image.Resampling.LANCZOS)  
        orig_photo = ImageTk.PhotoImage(orig_preview)
        orig_label = Label(image_frame, image=orig_photo)  # 显示图片的Label保持tk.Label
        orig_label.pack(side="left", padx=10)
        popup.orig_photo = orig_photo 
        orig_img.close()
        
        ttk.Label(image_frame, text="→", font=("Arial", 24)).pack(side="left", padx=10)
        
        # 新图片（右侧）
        new_img = Image.open(new_png)
        new_preview = new_img.resize((400, 300), Image.Resampling.LANCZOS) 
        new_photo = ImageTk.PhotoImage(new_preview)
        new_label = Label(image_frame, image=new_photo)  # 显示图片的Label保持tk.Label
        new_label.pack(side="left", padx=10)
        popup.new_photo = new_photo 
        new_img.close()

        ttk.Label(popup, text="是否确认替换（是/否）？").pack(pady=10)

        def yes():
            popup.destroy()
            nonlocal confirmed
            confirmed = True 
            self.replace_sav(main_sav, thumb_sav, new_png) 

        def no():
            popup.destroy()
            return  

        ttk.Button(popup, text="是", command=yes).pack(side="left", padx=10)
        ttk.Button(popup, text="否", command=no).pack(side="right", padx=10)
        popup.grab_set()
        self.root.wait_window(popup)
        os.remove(temp_png)  # 无论如何清理
        if not confirmed:
            return
        self.replace_sav(main_sav, thumb_sav, new_png)
        messagebox.showinfo("成功", f"替换 {id_str} 完成！")
        self.load_screenshots()

    def replace_sav(self, main_sav, thumb_sav, new_png):
        temp_thumb = None
        try:
            # 提取原thumb尺寸
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
            thumb_size = thumb_orig.size
            thumb_orig.close()  

            # 新主sav (PNG)
            with open(new_png, 'rb') as f:
                png_b64 = base64.b64encode(f.read()).decode('utf-8')
            new_main_uri = f"data:image/png;base64,{png_b64}"
            new_main_json = json.dumps(new_main_uri)
            new_main_encoded = urllib.parse.quote(new_main_json)
            with open(main_sav, 'w', encoding='utf-8') as f:
                f.write(new_main_encoded)

            # 新thumb JPEG
            main_img = Image.open(new_png)
            new_thumb = main_img.resize(thumb_size, Image.Resampling.LANCZOS)
            new_thumb = new_thumb.convert('RGB')
            new_thumb.save(temp_thumb, 'JPEG', quality=90, optimize=True)
            main_img.close()  # 显式关闭图像对象，释放文件句柄
            with open(temp_thumb, 'rb') as f:
                jpeg_b64 = base64.b64encode(f.read()).decode('utf-8')
            new_thumb_uri = f"data:image/jpeg;base64,{jpeg_b64}"
            new_thumb_json = json.dumps(new_thumb_uri)
            new_thumb_encoded = urllib.parse.quote(new_thumb_json)
            with open(thumb_sav, 'w', encoding='utf-8') as f:
                f.write(new_thumb_encoded)
        finally:
            if temp_thumb and os.path.exists(temp_thumb):
                try:
                    os.remove(temp_thumb)
                except:
                    pass

    def add_new(self):
        new_png = filedialog.askopenfilename(title="选择新PNG")
        if not new_png:
            return

        # 弹出窗口输入 ID 和 date
        popup = Toplevel(self.root)
        popup.title("新增截图设置")
        popup.geometry("400x200")

        ttk.Label(popup, text="ID (留空随机生成):").pack(pady=5)
        id_entry = ttk.Entry(popup, width=50)
        id_entry.pack()

        ttk.Label(popup, text="时间 (格式: YYYY/MM/DD HH:MM:SS, 留空当前时间):").pack(pady=5)
        date_entry = ttk.Entry(popup, width=50)
        date_entry.pack()

        def confirm():
            new_id = id_entry.get().strip() or ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            new_date = date_entry.get().strip() or datetime.now().strftime('%Y/%m/%d %H:%M:%S')

            try:
                # 验证 date 格式
                datetime.strptime(new_date, '%Y/%m/%d %H:%M:%S')
            except ValueError:
                messagebox.showerror("错误", "时间格式无效！使用 YYYY/MM/DD HH:MM:SS")
                return

            if new_id in self.sav_pairs:
                messagebox.showerror("错误", "ID 已存在！")
                return

            # 更新ids
            self.ids_data.append({"id": new_id, "date": new_date})
            ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
            self.encode_and_save(self.ids_data, ids_path)

            # 更新all_ids
            self.all_ids_data.append(new_id)
            all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
            self.encode_and_save(self.all_ids_data, all_ids_path)

            # 生成新sav对
            main_sav_name = f'DevilConnection_photo_{new_id}.sav'
            thumb_sav_name = f'DevilConnection_photo_{new_id}_thumb.sav'
            main_sav = os.path.join(self.storage_dir, main_sav_name)
            thumb_sav = os.path.join(self.storage_dir, thumb_sav_name)
            thumb_size = (1280, 960)
            valid_thumb_found = False
            for pair in self.sav_pairs.values():
                if pair[1] is not None:
                    first_thumb = os.path.join(self.storage_dir, pair[1])
                    with open(first_thumb, 'r', encoding='utf-8') as f:
                        encoded = f.read().strip()
                    unquoted = urllib.parse.unquote(encoded)
                    data_uri = json.loads(unquoted)
                    b64_part = data_uri.split(';base64,', 1)[1]
                    img_data = base64.b64decode(b64_part)
                    temp_thumb_size = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False).name
                    with open(temp_thumb_size, 'wb') as f:
                        f.write(img_data)
                    thumb_orig = Image.open(temp_thumb_size)
                    thumb_size = thumb_orig.size
                    thumb_orig.close() 
                    os.remove(temp_thumb_size)
                    valid_thumb_found = True
                    break

            # 生成文件
            temp_thumb = None
            try:
                # 新主sav (PNG)
                with open(new_png, 'rb') as f:
                    png_b64 = base64.b64encode(f.read()).decode('utf-8')
                new_main_uri = f"data:image/png;base64,{png_b64}"
                new_main_json = json.dumps(new_main_uri)
                new_main_encoded = urllib.parse.quote(new_main_json)
                with open(main_sav, 'w', encoding='utf-8') as f:
                    f.write(new_main_encoded)

                # 新thumb JPEG
                main_img = Image.open(new_png)
                new_thumb = main_img.resize(thumb_size, Image.Resampling.LANCZOS)
                new_thumb = new_thumb.convert('RGB')
                main_img.close() 
                temp_thumb = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False).name
                new_thumb.save(temp_thumb, 'JPEG', quality=90, optimize=True)
                with open(temp_thumb, 'rb') as f:
                    jpeg_b64 = base64.b64encode(f.read()).decode('utf-8')
                new_thumb_uri = f"data:image/jpeg;base64,{jpeg_b64}"
                new_thumb_json = json.dumps(new_thumb_uri)
                new_thumb_encoded = urllib.parse.quote(new_thumb_json)
                with open(thumb_sav, 'w', encoding='utf-8') as f:
                    f.write(new_thumb_encoded)
            finally:
                if temp_thumb and os.path.exists(temp_thumb):
                    try:
                        os.remove(temp_thumb)
                    except:
                        pass

            popup.destroy()
            messagebox.showinfo("成功", f"新增 {new_id} 完成！")
            # 取消所有选择
            for var, _ in self.checkbox_vars.values():
                var.set(False)
            for item_id in self.checkbox_vars.keys():
                self.update_checkbox_display(item_id)
            self.update_select_all_header()
            self.update_button_states()
            self.update_batch_export_button()
            self.load_screenshots()

        ttk.Button(popup, text="确认", command=confirm).pack(pady=20)
        
    def delete_selected(self):
        # 获取所有选中的ID（通过复选框）
        selected_ids = self.get_selected_ids()
        if not selected_ids:
            messagebox.showerror("错误", "请选择要删除的截图！")
            return
        
        # 确认删除对话框
        if len(selected_ids) == 1:
            confirm_msg = f"你确定要删除 {selected_ids[0]} 的截图（包括索引）吗？"
        else:
            confirm_msg = f"你确定要删除 {len(selected_ids)} 个截图（包括索引）吗？\n选中的ID: {', '.join(selected_ids[:5])}{'...' if len(selected_ids) > 5 else ''}"
        
        popup = Toplevel(self.root)
        popup.title("确认删除")
        ttk.Label(popup, text=confirm_msg).pack(pady=10)

        confirmed = False

        def yes():
            nonlocal confirmed
            confirmed = True
            popup.destroy()

        def no():
            popup.destroy()

        ttk.Button(popup, text="确定", command=yes).pack(side="left", padx=10)
        ttk.Button(popup, text="取消", command=no).pack(side="right", padx=10)

        popup.grab_set()
        self.root.wait_window(popup)

        if not confirmed:
            return

        # 删除所有选中的截图
        deleted_count = 0
        for id_str in selected_ids:
            # 删除文件（如果存在）
            pair = self.sav_pairs.get(id_str, [None, None])
            main_path = os.path.join(self.storage_dir, pair[0]) if pair[0] else None
            thumb_path = os.path.join(self.storage_dir, pair[1]) if pair[1] else None
            if main_path and os.path.exists(main_path):
                try:
                    os.remove(main_path)
                    deleted_count += 1
                except:
                    pass
            if thumb_path and os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except:
                    pass

            # 从索引移除
            self.ids_data = [item for item in self.ids_data if item['id'] != id_str]
            self.all_ids_data = [item for item in self.all_ids_data if item != id_str]

            # 移除本地缓存（如果存在）
            if id_str in self.sav_pairs:
                del self.sav_pairs[id_str]

        # 保存更新
        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        self.encode_and_save(self.ids_data, ids_path)
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
        self.encode_and_save(self.all_ids_data, all_ids_path)

        if deleted_count > 0:
            messagebox.showinfo("成功", f"已删除 {deleted_count} 个截图！")
        else:
            messagebox.showwarning("警告", "没有成功删除任何文件！")
        
        # 取消所有选择
        for var, _ in self.checkbox_vars.values():
            var.set(False)
        self.update_select_all_header()
        self.update_button_states()
        self.update_batch_export_button()
        self.load_screenshots()
    
    def export_image(self):
        """导出选中的截图"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror("错误", "请选择一个截图！")
            return
        
        item_id = selected[0]
        if item_id not in self.checkbox_vars:
            messagebox.showerror("错误", "无效的选择！")
            return
        
        _, id_str = self.checkbox_vars[item_id]
        
        if not self.storage_dir or id_str not in self.sav_pairs:
            messagebox.showerror("错误", "无法找到截图文件！")
            return
        
        main_file = self.sav_pairs[id_str][0]
        if not main_file:
            messagebox.showerror("错误", "文件缺失！")
            return
        
        main_sav = os.path.join(self.storage_dir, main_file)
        if not os.path.exists(main_sav):
            messagebox.showerror("错误", "文件不存在！")
            return
        
        # 解码图片数据
        try:
            with open(main_sav, 'r', encoding='utf-8') as f:
                encoded = f.read().strip()
            unquoted = urllib.parse.unquote(encoded)
            data_uri = json.loads(unquoted)
            b64_part = data_uri.split(';base64,', 1)[1]
            img_data = base64.b64decode(b64_part)
            
            # 保存到临时PNG文件
            temp_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
            with open(temp_png, 'wb') as f:
                f.write(img_data)
            
            # 打开图片
            img = Image.open(temp_png)
            
            # 弹出格式选择对话框
            format_window = Toplevel(self.root)
            format_window.title("选择导出格式")
            format_window.geometry("300x150")
            
            selected_format = tk.StringVar(value="png")
            
            ttk.Label(format_window, text="选择图片格式:").pack(pady=10)
            format_frame = tk.Frame(format_window)
            format_frame.pack(pady=10)
            
            ttk.Radiobutton(format_frame, text="PNG", variable=selected_format, value="png").pack(side="left", padx=10)
            ttk.Radiobutton(format_frame, text="JPEG", variable=selected_format, value="jpeg").pack(side="left", padx=10)
            ttk.Radiobutton(format_frame, text="WebP", variable=selected_format, value="webp").pack(side="left", padx=10)
            
            def confirm_export():
                nonlocal img, temp_png
                format_window.destroy()
                format = selected_format.get()
                
                # 获取原始文件名（不含.sav后缀）
                base_name = os.path.splitext(main_file)[0]
                
                # 根据格式设置文件扩展名和保存选项
                if format == "png":
                    filetypes = [("PNG files", "*.png"), ("All files", "*.*")]
                    default_ext = ".png"
                    default_filename = base_name + ".png"
                elif format == "jpeg":
                    filetypes = [("JPEG files", "*.jpg"), ("All files", "*.*")]
                    default_ext = ".jpg"
                    default_filename = base_name + ".jpg"
                else:  # webp
                    filetypes = [("WebP files", "*.webp"), ("All files", "*.*")]
                    default_ext = ".webp"
                    default_filename = base_name + ".webp"
                
                # 弹出保存对话框
                save_path = filedialog.asksaveasfilename(
                    title="保存图片",
                    defaultextension=default_ext,
                    filetypes=filetypes,
                    initialfile=default_filename
                )
                
                if not save_path:
                    img.close()
                    os.remove(temp_png)
                    return
                
                try:
                    # 根据格式保存图片
                    if format == "png":
                        img.save(save_path, "PNG")
                    elif format == "jpeg":
                        # JPEG需要RGB模式
                        if img.mode != "RGB":
                            img = img.convert("RGB")
                        img.save(save_path, "JPEG", quality=95)
                    else:  # webp
                        img.save(save_path, "WebP", quality=95)
                    
                    messagebox.showinfo("成功", f"图片已保存到:\n{save_path}")
                except Exception as e:
                    messagebox.showerror("错误", f"保存失败: {str(e)}")
                finally:
                    img.close()
                    if os.path.exists(temp_png):
                        os.remove(temp_png)
            
            def on_close():
                """窗口关闭时的清理函数"""
                nonlocal img, temp_png
                try:
                    img.close()
                except:
                    pass
                try:
                    if os.path.exists(temp_png):
                        os.remove(temp_png)
                except:
                    pass
                format_window.destroy()
            
            ttk.Button(format_window, text="确定", command=confirm_export).pack(pady=10)
            format_window.protocol("WM_DELETE_WINDOW", on_close)
            format_window.grab_set()
            
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {str(e)}")
    
    def batch_export_images(self):
        """批量导出选中的截图到ZIP文件"""
        selected_ids = self.get_selected_ids()
        if not selected_ids:
            messagebox.showerror("错误", "请选择要导出的截图！")
            return
        
        if not self.storage_dir:
            messagebox.showerror("错误", "请先选择目录！")
            return
        
        # 弹出格式选择对话框
        format_window = Toplevel(self.root)
        format_window.title("选择导出格式")
        format_window.geometry("300x150")
        
        selected_format = tk.StringVar(value="png")
        
        ttk.Label(format_window, text="选择图片格式:").pack(pady=10)
        format_frame = tk.Frame(format_window)
        format_frame.pack(pady=10)
        
        ttk.Radiobutton(format_frame, text="PNG", variable=selected_format, value="png").pack(side="left", padx=10)
        ttk.Radiobutton(format_frame, text="JPEG", variable=selected_format, value="jpeg").pack(side="left", padx=10)
        ttk.Radiobutton(format_frame, text="WebP", variable=selected_format, value="webp").pack(side="left", padx=10)
        
        def confirm_batch_export():
            format_window.destroy()
            format = selected_format.get()
            
            # 根据格式设置文件扩展名
            if format == "png":
                default_ext = ".png"
                file_ext = "png"
            elif format == "jpeg":
                default_ext = ".jpg"
                file_ext = "jpg"
            else:  # webp
                default_ext = ".webp"
                file_ext = "webp"
            
            # 弹出保存对话框
            save_path = filedialog.asksaveasfilename(
                title="保存ZIP文件",
                defaultextension=".zip",
                filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
                initialfile="DevilConnectionSSPack.zip"
            )
            
            if not save_path:
                return
            
            try:
                # 创建临时目录存放图片
                temp_dir = tempfile.mkdtemp()
                exported_count = 0
                failed_count = 0
                
                # 导出每张图片
                for id_str in selected_ids:
                    if id_str not in self.sav_pairs:
                        failed_count += 1
                        continue
                    
                    main_file = self.sav_pairs[id_str][0]
                    if not main_file:
                        failed_count += 1
                        continue
                    
                    main_sav = os.path.join(self.storage_dir, main_file)
                    if not os.path.exists(main_sav):
                        failed_count += 1
                        continue
                    
                    try:
                        # 解码图片数据
                        with open(main_sav, 'r', encoding='utf-8') as f:
                            encoded = f.read().strip()
                        unquoted = urllib.parse.unquote(encoded)
                        data_uri = json.loads(unquoted)
                        b64_part = data_uri.split(';base64,', 1)[1]
                        img_data = base64.b64decode(b64_part)
                        
                        # 保存到临时PNG文件
                        temp_png = os.path.join(temp_dir, f"{id_str}.png")
                        with open(temp_png, 'wb') as f:
                            f.write(img_data)
                        
                        # 打开图片并转换格式
                        img = Image.open(temp_png)
                        
                        # 根据格式保存
                        output_filename = f"{id_str}.{file_ext}"
                        output_path = os.path.join(temp_dir, output_filename)
                        
                        if format == "png":
                            img.save(output_path, "PNG")
                        elif format == "jpeg":
                            if img.mode != "RGB":
                                img = img.convert("RGB")
                            img.save(output_path, "JPEG", quality=95)
                        else:  # webp
                            img.save(output_path, "WebP", quality=95)
                        
                        img.close()
                        os.remove(temp_png)  # 删除临时PNG
                        exported_count += 1
                    except Exception as e:
                        failed_count += 1
                        continue
                
                # 创建ZIP文件
                if exported_count > 0:
                    with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for filename in os.listdir(temp_dir):
                            file_path = os.path.join(temp_dir, filename)
                            if os.path.isfile(file_path):
                                zipf.write(file_path, filename)
                    
                    # 清理临时目录
                    shutil.rmtree(temp_dir)
                    
                    success_msg = f"成功导出 {exported_count} 张图片到ZIP文件！"
                    if failed_count > 0:
                        success_msg += f"\n失败: {failed_count} 张"
                    messagebox.showinfo("成功", success_msg)
                else:
                    # 清理临时目录
                    shutil.rmtree(temp_dir)
                    messagebox.showerror("错误", "没有成功导出任何图片！")
                    
            except Exception as e:
                messagebox.showerror("错误", f"批量导出失败: {str(e)}")
        
        ttk.Button(format_window, text="确定", command=confirm_batch_export).pack(pady=10)
        format_window.grab_set()
        

if __name__ == "__main__":
    root = tk.Tk()
    app = SavTool(root)
    root.mainloop()