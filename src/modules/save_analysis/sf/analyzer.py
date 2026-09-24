"""sf 存档分析页（主窗口第一个标签页）

左侧：按分区列出 DevilConnection_sf.sav 中的各项数据（fields.SECTIONS）
右侧：统计面板（statistics_panel）和「查看存档文件」按钮

refresh() 会重新读取存档。分区结构不变时只更新 StringVar 里的文字，
不重建控件，避免闪烁和滚动位置跳动；进入/离开狂信徒路线时分区顺序和颜色
都会变化，这时整体重建。
"""

import logging
import tkinter as tk
from dataclasses import dataclass
from tkinter import Scrollbar, ttk
from typing import Any, Callable, Dict, List, Optional, Tuple

import customtkinter as ctk

from src.constants import LATEST_GAME_PATCH_AT_BUILD, STICKER_ID_RANGES, TOTAL_ENDINGS, TOTAL_NG_SCENE
from src.constants import SF_SAVE_FILENAME
from src.utils.styles import Colors, get_cjk_font

from .fields import (
    FANATIC_SECTION_KEY,
    SECTIONS,
    Field,
    Section,
    compute_shared_data,
    field_value,
    load_save_file,
    section_order,
)
from .requirements_viewer import show_requirements
from .save_file_viewer import DEFAULT_SF_COLLAPSED_FIELDS, SaveFileViewer, ViewerConfig
from .statistics_panel import StatisticsPanel

logger = logging.getLogger(__name__)

LEFT_WIDTH_RATIO = 2 / 3
DEFAULT_WINDOW_WIDTH = 800
FANATIC_TEXT_COLOR = "#8b0000"
TITLE_COLOR = "#000000"
TOOLTIP_ICON_COLOR = "blue"
LABEL_WRAPLENGTH = 400


@dataclass
class _Row:
    """一行「标签: 值」的可变文字"""
    label_var: tk.StringVar
    value_var: tk.StringVar
    tooltip_var: Optional[tk.StringVar] = None


class SaveAnalyzer:
    """sf 存档分析页"""

    def __init__(self, parent: tk.Widget, storage_dir: str, t: Callable[..., str]) -> None:
        self.window = parent
        self.storage_dir = storage_dir
        self.t = t  # 翻译函数，总是返回当前语言的文字
        self.save_data: Optional[Dict[str, Any]] = None

        self.window.update_idletasks()
        window_width = self.window.winfo_width()
        self._width = int((window_width if window_width > 1 else DEFAULT_WINDOW_WIDTH) * LEFT_WIDTH_RATIO)

        # 当前左侧显示的分区是按哪种路线建的；None 表示还没有显示存档数据
        self._rendered_route: Optional[bool] = None
        self._rows: Dict[str, _Row] = {}
        self._translatable: List[Tuple[tk.Widget, str]] = []   # 语言切换时需要更新文字的标题/按钮/提示
        self._var_name_labels: List[Tuple[ttk.Label, ttk.Label]] = []  # (变量名标签, 它前面的标签)

        self.show_var_names_var = tk.BooleanVar(value=False)
        self._build_layout()
        self.window.after_idle(self.refresh)

    def _tr(self, key: str) -> str:
        """翻译并替换 [GAMEPATCH_DATE] 占位符"""
        return self.t(key).replace("[GAMEPATCH_DATE]", LATEST_GAME_PATCH_AT_BUILD)

    # ---------------------------------------------------------------- 布局

    def _build_layout(self) -> None:
        control_frame = tk.Frame(self.window, bg=Colors.WHITE)
        control_frame.pack(fill="x", padx=10, pady=5)
        self.show_var_names_checkbox = ttk.Checkbutton(
            control_frame, text=self.t("show_var_names"), variable=self.show_var_names_var,
            command=self.toggle_var_names_display)
        self.show_var_names_checkbox.pack(side="left", padx=5)
        self.refresh_button = ttk.Button(control_frame, text=self.t("refresh"), command=self.refresh,
                                         name="refresh")
        self.refresh_button.pack(side="right", padx=5)

        main_container = tk.Frame(self.window, bg=Colors.WHITE, highlightthickness=0, takefocus=0)
        main_container.pack(fill="both", expand=True)
        paned = tk.PanedWindow(main_container, orient="horizontal", sashwidth=0, bg=Colors.WHITE,
                               sashrelief="flat")
        paned.pack(side="left", fill="both", expand=True)

        left_frame = tk.Frame(paned, bg=Colors.WHITE, highlightthickness=0, takefocus=0)
        paned.add(left_frame, width=800, minsize=400)
        self.scrollable_canvas = ctk.CTkCanvas(left_frame, bg=Colors.WHITE)
        self.scrollable_frame = tk.Frame(self.scrollable_canvas, bg=Colors.WHITE, highlightthickness=0,
                                         takefocus=0, width=self._width)
        self.scrollable_frame.bind("<Configure>", lambda e: self._update_scrollregion())
        self.scrollable_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.scrollable_canvas.pack(fill="both", expand=True)

        right_frame = tk.Frame(paned, bg=Colors.WHITE)
        paned.add(right_frame, width=400, minsize=200)

        # 左右比例固定为 2:1，禁止拖动分隔条
        def keep_ratio(event: Optional[tk.Event] = None) -> None:
            if paned.winfo_width() > 1:
                paned.paneconfig(left_frame, width=int(paned.winfo_width() * 0.67))

        for sequence in ("<Button-1>", "<B1-Motion>", "<ButtonRelease-1>"):
            paned.bind(sequence, lambda e: "break")
        paned.bind("<Configure>", lambda e: self.window.after_idle(keep_ratio))
        keep_ratio()

        scrollbar = Scrollbar(main_container, orient="vertical", command=self.scrollable_canvas.yview)
        self.scrollable_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        self.window.bind("<Configure>", self._on_window_configure)
        self._bind_mousewheel(left_frame)

        self.statistics_panel = StatisticsPanel(right_frame, self.storage_dir, self.t)
        button_frame = tk.Frame(right_frame, bg=Colors.WHITE)
        button_frame.pack(side="bottom", fill="x", pady=(0, 10))
        self.view_file_button = ttk.Button(button_frame, text=self.t("view_save_file"),
                                           command=self.show_save_file_viewer)
        self.view_file_button.pack(pady=5)

    def _on_window_configure(self, event: tk.Event) -> None:
        if event.widget is self.window:
            self.window.after_idle(self._update_width)

    def _update_width(self) -> None:
        if not self.scrollable_canvas.winfo_exists():
            return
        window_width = self.window.winfo_width()
        if window_width > 1:
            self._width = max(1, int(window_width * LEFT_WIDTH_RATIO))
            self.scrollable_canvas.config(width=self._width)
            self.scrollable_frame.config(width=self._width)

    def _update_scrollregion(self) -> None:
        bbox = self.scrollable_canvas.bbox("all")
        if bbox:
            self.scrollable_canvas.configure(scrollregion=bbox)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if event.delta:
            self.scrollable_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif event.num == 4:
            self.scrollable_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.scrollable_canvas.yview_scroll(1, "units")

    def _bind_mousewheel(self, widget: tk.Misc) -> None:
        """滚轮事件只发给鼠标下的控件，所以要绑定到左侧的每个子控件上"""
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(sequence, self._on_mousewheel)
        for child in widget.winfo_children():
            self._bind_mousewheel(child)

    # ---------------------------------------------------------------- 刷新

    def refresh(self) -> None:
        """重新读取存档并更新页面（也用于语言切换）"""
        if not self.scrollable_frame.winfo_exists():
            return
        self.show_var_names_checkbox.config(text=self.t("show_var_names"))
        self.refresh_button.config(text=self.t("refresh"))
        self.view_file_button.config(text=self.t("view_save_file"))
        self._update_width()

        try:
            save_data = load_save_file(self.storage_dir)
        except FileNotFoundError:
            logger.info("%s not found in %s", SF_SAVE_FILENAME, self.storage_dir)
            self._show_load_error(self.t("save_file_not_found"))
            return
        except (OSError, ValueError) as e:
            logger.error("Failed to load %s: %s", SF_SAVE_FILENAME, e, exc_info=True)
            self._show_load_error(f"{self.t('error')}: {SF_SAVE_FILENAME}\n{e}")
            return

        self.save_data = save_data
        computed = compute_shared_data(save_data)
        fanatic = computed["is_fanatic_route"]
        if self._rendered_route is None or self._rendered_route != fanatic:
            self._build_sections(save_data, computed)
        else:
            self._update_sections(save_data, computed)
        self.window.after_idle(self._update_scrollregion)
        self.window.after_idle(lambda: self.statistics_panel.update(save_data))

    def _show_load_error(self, message: str) -> None:
        """读取失败时：还没显示过数据就显示错误信息；已经显示过则保留旧数据"""
        self.save_data = None
        if self._rendered_route is not None:
            return
        self._clear_sections()
        ttk.Label(self.scrollable_frame, text=message, font=get_cjk_font(12), foreground="red",
                  wraplength=self._width, justify="left").pack(pady=20)

    # ---------------------------------------------------------------- 分区

    def _clear_sections(self) -> None:
        for child in self.scrollable_frame.winfo_children():
            child.destroy()
        self._rows.clear()
        self._translatable.clear()
        self._var_name_labels.clear()
        self._rendered_route = None

    def _build_sections(self, save_data: Dict[str, Any], computed: Dict[str, Any]) -> None:
        self._clear_sections()
        fanatic = computed["is_fanatic_route"]
        for key in section_order(fanatic):
            section = SECTIONS[key]
            color = FANATIC_TEXT_COLOR if fanatic and key == FANATIC_SECTION_KEY else None
            content = self._create_section(section, color)
            for field in section.fields:
                self._create_row(content, field, field_value(field, save_data, computed, self.t), color)
            if section.hint_key:
                hint = ttk.Label(content, text=self._tr(section.hint_key), font=get_cjk_font(9),
                                 foreground="gray", wraplength=int(self._width * 0.85), justify="left")
                hint.pack(anchor="w", padx=5, pady=(5, 0))
                self._translatable.append((hint, section.hint_key))
        self._rendered_route = fanatic
        self._bind_mousewheel(self.scrollable_frame)

    def _update_sections(self, save_data: Dict[str, Any], computed: Dict[str, Any]) -> None:
        for widget, key in self._translatable:
            widget.config(text=self._tr(key))
        for section in SECTIONS.values():
            for field in section.fields:
                row = self._rows[field.label_key]
                row.label_var.set(f"{self.t(field.label_key)}:")
                row.value_var.set(field_value(field, save_data, computed, self.t))
                if row.tooltip_var is not None:
                    row.tooltip_var.set(self._tr(field.tooltip_key))

    def _create_section(self, section: Section, color: Optional[str]) -> tk.Frame:
        """创建带边框的分区，返回放内容的 Frame"""
        frame = tk.Frame(self.scrollable_frame, bg=Colors.WHITE, relief="ridge", borderwidth=2)
        frame.pack(fill="x", padx=10, pady=5)
        if section.button_text_key:
            header = tk.Frame(frame, bg=Colors.WHITE)
            header.pack(fill="x", padx=5, pady=5)
            title = ttk.Label(header, text=self.t(section.key), font=get_cjk_font(12, "bold"),
                              wraplength=int(self._width * 0.6), justify="left")
            title.pack(side="left", padx=5)
            button = ttk.Button(header, text=self.t(section.button_text_key),
                                command=self._requirement_commands()[section.key])
            button.pack(side="right", padx=5)
            self._translatable.append((button, section.button_text_key))
        else:
            title = ttk.Label(frame, text=self.t(section.key), font=get_cjk_font(12, "bold"),
                              wraplength=int(self._width * 0.9), justify="left",
                              foreground=color or TITLE_COLOR)
            title.pack(anchor="w", padx=5, pady=5)
        self._translatable.append((title, section.key))

        content = tk.Frame(frame, bg=Colors.WHITE)
        content.pack(fill="x", padx=10, pady=5)
        return content

    def _create_row(self, parent: tk.Frame, field: Field, value: str, color: Optional[str]) -> None:
        """一行「[变量名] 标签: 值 ℹ」，点击 ℹ 展开/收起说明"""
        tooltip_text = self._tr(field.tooltip_key) if field.tooltip_key else ""
        has_tooltip = bool(field.tooltip_key) and not (field.tooltip_optional and not tooltip_text)

        container = tk.Frame(parent, bg=Colors.WHITE)
        container.pack(fill="x", padx=5, pady=2)
        if has_tooltip:
            line = tk.Frame(container, bg=Colors.WHITE)
            line.pack(fill="x")
        else:
            line = container

        row = _Row(tk.StringVar(value=f"{self.t(field.label_key)}:"), tk.StringVar(value=value))
        label = ttk.Label(line, textvariable=row.label_var, font=get_cjk_font(10),
                          wraplength=LABEL_WRAPLENGTH, foreground=color)
        label.pack(side="left", padx=5)
        if field.var_name:
            var_label = ttk.Label(line, text=f"[{field.var_name}]", font=get_cjk_font(9), foreground="gray")
            if self.show_var_names_var.get():
                var_label.pack(side="left", padx=2, before=label)
            self._var_name_labels.append((var_label, label))
        ttk.Label(line, textvariable=row.value_var, font=get_cjk_font(10), wraplength=int(self._width * 0.7),
                  justify="left", foreground=color).pack(side="left", padx=5, fill="x", expand=True)

        if has_tooltip:
            icon = ttk.Label(line, text="ℹ", font=get_cjk_font(10, "bold"),
                             foreground=color or TOOLTIP_ICON_COLOR, cursor="hand2")
            icon.pack(side="left", padx=2)
            tooltip_frame = tk.Frame(container, bg=Colors.WHITE)
            row.tooltip_var = tk.StringVar(value=tooltip_text)
            ttk.Label(tooltip_frame, textvariable=row.tooltip_var, font=get_cjk_font(9), foreground="gray",
                      wraplength=int(self._width * 0.85), justify="left").pack(anchor="w", padx=15, pady=2)

            def toggle_tooltip(event: tk.Event) -> None:
                if tooltip_frame.winfo_viewable():
                    tooltip_frame.pack_forget()
                else:
                    tooltip_frame.pack(fill="x", padx=5, pady=2)

            icon.bind("<Button-1>", toggle_tooltip)

        self._rows[field.label_key] = row

    def toggle_var_names_display(self) -> None:
        show = self.show_var_names_var.get()
        for var_label, label in self._var_name_labels:
            if show:
                var_label.pack(side="left", padx=2, before=label)
            else:
                var_label.pack_forget()

    # ---------------------------------------------------------------- 按钮

    def _requirement_commands(self) -> Dict[str, Callable[[], None]]:
        return {
            "endings_statistics": self.show_endings_requirements,
            "stickers_statistics": self.show_stickers_requirements,
            "omakes_statistics": self.show_ng_scene_requirements,
        }

    def show_endings_requirements(self) -> None:
        data = self.save_data or {}
        items = [(str(i), self.t(f"END{i}_unlock_cond")) for i in range(1, TOTAL_ENDINGS + 1)]
        collected = {str(e) for e in data.get("collectedEndings", [])}
        show_requirements(self.window, self.t, "endings_statistics", items, collected, "END", "ending")

    def show_stickers_requirements(self) -> None:
        data = self.save_data or {}
        ids = [str(i) for start, end in STICKER_ID_RANGES for i in range(start, end)]
        items = [(i, self.t(f"STICKER{i}_unlock_cond")) for i in ids]
        collected = {str(s) for s in data.get("sticker", [])}
        show_requirements(self.window, self.t, "stickers_statistics", items, collected, "#", "sticker")

    def show_ng_scene_requirements(self) -> None:
        # NG 场景没有编号，卡片标题直接用场景名
        unlocked = set((self.save_data or {}).get("ngScene", []))
        items = []
        collected = set()
        for scene_id in TOTAL_NG_SCENE:
            name = self.t(f"ng_scene_{scene_id}")
            items.append((name, self.t(f"ng_scene_{scene_id}_unlock_cond")))
            if scene_id in unlocked:
                collected.add(name)
        show_requirements(self.window, self.t, "omakes_statistics", items, collected, "", "ng_scene")

    def show_save_file_viewer(self) -> None:
        if not self.save_data:
            return
        config = ViewerConfig(
            collapsed_fields=DEFAULT_SF_COLLAPSED_FIELDS,
            show_collapse_checkbox=True,
            show_hint_label=True,
            show_enable_edit_checkbox=True,
            enable_edit_by_default=False,
            on_save_callback=lambda edited: self.refresh(),
        )
        SaveFileViewer.open_or_focus(
            viewer_id=f"sf:{self.storage_dir}",
            window=self.window,
            storage_dir=self.storage_dir,
            save_data=self.save_data,
            t_func=self.t,
            on_close_callback=self.refresh,
            viewer_config=config,
        )
