"""缓存清理窗口：选择清理项后在游戏页面里执行对应的清理脚本"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import customtkinter as ctk
import tkinter as tk

from src.modules.runtime_modify.cache_clean_scripts import (
    JS_CHECK_PHOTO_OPEN,
    JS_CHECK_STATE,
    JS_SCAN_DANGEROUS_ITEMS,
    REQUIRES_PHOTO_CLOSED,
    RISKY_CLEANUP_SCRIPTS,
    SAFE_CLEANUP_SCRIPTS,
    generate_cleanup_script,
)
from src.modules.runtime_modify.dialogs import RuntimeDialog, set_textbox_text
from src.modules.runtime_modify.service import CdpError, evaluate
from src.utils.background import run_in_background
from src.utils.styles import Colors, get_cjk_font, white_button


@dataclass
class CleanupJob:
    """一个要执行的清理项"""
    name: str
    script: str
    requires_photo_closed: bool = False


@dataclass
class CleanupItemResult:
    """一个清理项的结果；count 为 None 表示失败

    script_failed 为 True 表示脚本本身出错或返回值不对（除了逐项显示，还会列在「警告」里）。
    """
    name: str
    count: Optional[int]
    error: Optional[str] = None
    script_failed: bool = False


@dataclass
class CleanupResult:
    items: List[CleanupItemResult] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)    # 因照片界面打开而跳过的项


class CannotCleanNowError(Exception):
    """游戏正在转场/动画，现在清理会出问题；reason 是游戏给出的原因（可能为 None）"""

    def __init__(self, reason: Optional[str]) -> None:
        super().__init__(reason or "")
        self.reason = reason


def run_cleanup(ws_url: str, jobs: List[CleanupJob]) -> CleanupResult:
    """依次执行清理脚本（在后台线程调用）

    Raises:
        CdpError: 无法检查游戏状态
        CannotCleanNowError: 游戏现在不能清理
    """
    state = evaluate(ws_url, JS_CHECK_STATE)
    if not isinstance(state, dict) or not state.get("canClean"):
        raise CannotCleanNowError(state.get("reason") if isinstance(state, dict) else None)

    photo_open = False
    if any(job.requires_photo_closed for job in jobs):
        try:
            photo = evaluate(ws_url, JS_CHECK_PHOTO_OPEN)
            photo_open = isinstance(photo, dict) and bool(photo.get("isOpen"))
        except CdpError:
            pass

    result = CleanupResult()
    for job in jobs:
        if job.requires_photo_closed and photo_open:
            result.skipped.append(job.name)
            continue
        try:
            outcome = evaluate(ws_url, job.script)
        except CdpError as e:
            result.items.append(CleanupItemResult(job.name, None, str(e), script_failed=True))
            continue
        if not isinstance(outcome, dict):
            # 返回值不是预期的 {success, count}，由界面显示翻译后的提示
            result.items.append(CleanupItemResult(job.name, None, script_failed=True))
        elif outcome.get("success"):
            result.items.append(CleanupItemResult(job.name, int(outcome.get("count") or 0)))
        else:
            result.items.append(CleanupItemResult(job.name, None, outcome.get("error")))
    return result


class CacheCleanDialog(RuntimeDialog):
    """左侧是执行按钮和结果，右侧是可勾选的清理项"""

    def __init__(self, parent: tk.Misc, t: Callable[..., str], get_ws_url: Callable[[], Optional[str]]) -> None:
        super().__init__(parent, t, "cache_clean_dialog_title", "550x550", (500, 450))
        self.get_ws_url = get_ws_url

        self._item_vars: Dict[str, tk.BooleanVar] = {}   # 固定清理项 key -> 是否勾选
        # 扫描出的项：(名称, 清理脚本, 是否勾选, 复选框)
        self._dynamic_items: List[Tuple[str, str, tk.BooleanVar, ctk.CTkCheckBox]] = []
        # 文字固定的控件及其翻译键，切换语言时逐个更新
        self._translated_widgets: List[Tuple[Any, str]] = []
        self._status_key: Optional[str] = None   # 状态栏显示的是固定提示时记下它的键，结果文字则为 None
        self._is_executing = False
        self._is_scanning = False
        self._found_count: Optional[int] = None  # 扫描到的项数；还没扫描时为 None

        self._build_ui()

    def _build_ui(self) -> None:
        container = ctk.CTkFrame(self.window, fg_color=Colors.WHITE)
        container.pack(fill="both", expand=True, padx=10, pady=10)
        content = ctk.CTkFrame(container, fg_color=Colors.WHITE)
        content.pack(fill="both", expand=True)

        left = ctk.CTkFrame(content, fg_color=Colors.WHITE, width=120)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        self.execute_button = white_button(
            left, self.t("cache_clean_execute"), self._on_execute_clicked, font=get_cjk_font(11), height=35)
        self.execute_button.pack(fill="x", pady=(0, 10))

        self.status_text = ctk.CTkTextbox(
            left,
            font=get_cjk_font(9),
            fg_color=Colors.LIGHT_GRAY,
            text_color=Colors.TEXT_PRIMARY,
            border_color=Colors.GRAY,
            border_width=1,
            corner_radius=8,
            wrap="word",
        )
        self.status_text.pack(fill="both", expand=True)
        self._show_status_key("cache_clean_status_ready")

        right = ctk.CTkFrame(content, fg_color=Colors.WHITE)
        right.pack(side="right", fill="both", expand=True)
        items_frame = ctk.CTkScrollableFrame(
            right,
            fg_color=Colors.WHITE,
            scrollbar_button_color=Colors.GRAY,
            scrollbar_button_hover_color=Colors.LIGHT_GRAY,
        )
        items_frame.pack(fill="both", expand=True)

        self._add_group(items_frame, "cache_clean_safe_group", "cache_clean_select_all_safe",
                        SAFE_CLEANUP_SCRIPTS, checked=True)
        ctk.CTkFrame(items_frame, height=1, fg_color=Colors.GRAY).pack(fill="x", pady=(10, 10))
        self._add_group(items_frame, "cache_clean_risky_group", "cache_clean_select_all_risky",
                        RISKY_CLEANUP_SCRIPTS, checked=False)
        ctk.CTkFrame(items_frame, height=1, fg_color=Colors.GRAY).pack(fill="x", pady=(10, 10))

        # 「全部」分组：扫描后才列出可清理的项
        self.dangerous_frame = ctk.CTkFrame(items_frame, fg_color=Colors.WHITE)
        self.dangerous_frame.pack(fill="x", pady=(0, 5))
        self._group_label(self.dangerous_frame, "cache_clean_all").pack(anchor="w", pady=(0, 5))
        self.scan_hint_label = ctk.CTkLabel(
            self.dangerous_frame,
            text=self._scan_hint(),
            font=get_cjk_font(9),
            text_color=Colors.TEXT_SECONDARY,
            anchor="w",
            wraplength=350,
        )
        self.scan_hint_label.pack(anchor="w", pady=(0, 10))
        self.scan_button = ctk.CTkButton(
            self.dangerous_frame,
            text=self.t("cache_clean_scan_button"),
            command=self._on_scan_clicked,
            font=get_cjk_font(10),
            width=120,
            height=30,
        )
        self.scan_button.pack(anchor="w", pady=(0, 10))

    def _group_label(self, parent: tk.Misc, key: str) -> ctk.CTkLabel:
        label = ctk.CTkLabel(
            parent, text=self.t(key), font=get_cjk_font(11, "bold"), text_color=Colors.TEXT_PRIMARY, anchor="w")
        self._translated_widgets.append((label, key))
        return label

    def _checkbox(self, parent: tk.Misc, text: str, var: tk.BooleanVar, **kwargs) -> ctk.CTkCheckBox:
        return ctk.CTkCheckBox(
            parent, text=text, variable=var, font=get_cjk_font(10), text_color=Colors.TEXT_PRIMARY, **kwargs)

    def _add_group(self, parent: tk.Misc, title_key: str, select_all_key: str, scripts: Dict[str, str],
                   checked: bool) -> None:
        """一个分组：标题、「全选」复选框、每个清理项的复选框"""
        self._group_label(parent, title_key).pack(anchor="w", pady=(0, 5))

        item_vars = [tk.BooleanVar(value=checked) for _ in scripts]
        select_all = tk.BooleanVar(value=checked)

        def toggle_all() -> None:
            for var in item_vars:
                var.set(select_all.get())

        checkbox = self._checkbox(parent, self.t(select_all_key), select_all, command=toggle_all)
        checkbox.pack(anchor="w", pady=(0, 5))
        self._translated_widgets.append((checkbox, select_all_key))
        for key, var in zip(scripts, item_vars):
            item_key = f"cache_clean_item_{key}"
            checkbox = self._checkbox(parent, self.t(item_key), var)
            checkbox.pack(anchor="w", padx=(20, 0), pady=(0, 3))
            self._translated_widgets.append((checkbox, item_key))
            self._item_vars[key] = var

    # ------------------------------------------------------------ 扫描

    def _scan_hint(self) -> str:
        if self._found_count is None:
            return self.t("cache_clean_scan_hint")
        if self._found_count == 0:
            return self.t("cache_clean_no_items_found")
        return self.t("cache_clean_items_found_count", count=self._found_count)

    def _on_scan_clicked(self) -> None:
        ws_url = self.get_ws_url()
        if not ws_url:
            self._show_status_key("cache_clean_error_no_connection")
            return
        self._is_scanning = True
        self.scan_button.configure(text=self.t("cache_clean_scanning"), state="disabled")
        run_in_background(self.window, lambda: evaluate(ws_url, JS_SCAN_DANGEROUS_ITEMS), self._on_scan_done)

    def _on_scan_done(self, found: Any, error: Optional[BaseException]) -> None:
        self._is_scanning = False
        self.scan_button.configure(text=self.t("cache_clean_scan_button"), state="normal")
        if error is not None:
            self._show_status(self.t("cache_clean_scan_failed", error=str(error)))
            return

        for *_rest, checkbox in self._dynamic_items:
            checkbox.destroy()
        self._dynamic_items.clear()

        for item in found if isinstance(found, list) else []:
            script = generate_cleanup_script(item)
            if not script:
                continue
            name = item.get("name") or self.t("cache_clean_unknown_item")
            var = tk.BooleanVar(value=False)
            checkbox = self._checkbox(self.dangerous_frame, name, var)
            checkbox.pack(anchor="w", padx=(20, 0), pady=(0, 3))
            self._dynamic_items.append((name, script, var, checkbox))

        self._found_count = len(self._dynamic_items)
        self.scan_hint_label.configure(text=self._scan_hint())

    # ------------------------------------------------------------ 执行

    def _selected_jobs(self) -> List[CleanupJob]:
        jobs = []
        for key, var in self._item_vars.items():
            if var.get():
                script = SAFE_CLEANUP_SCRIPTS.get(key) or RISKY_CLEANUP_SCRIPTS[key]
                jobs.append(CleanupJob(self.t(f"cache_clean_item_{key}"), script, key in REQUIRES_PHOTO_CLOSED))
        for name, script, var, _checkbox in self._dynamic_items:
            if var.get():
                jobs.append(CleanupJob(name, script))
        return jobs

    def _on_execute_clicked(self) -> None:
        if self._is_executing:
            return
        jobs = self._selected_jobs()
        if not jobs:
            self._show_status_key("cache_clean_no_item_selected")
            return
        ws_url = self.get_ws_url()
        if not ws_url:
            self._show_status_key("cache_clean_error_no_connection")
            return

        self._is_executing = True
        self.execute_button.configure(state="disabled", text=self.t("cache_clean_executing"))
        self._show_status_key("cache_clean_checking_state")
        run_in_background(self.window, lambda: run_cleanup(ws_url, jobs), self._on_cleanup_done)

    def _on_cleanup_done(self, result: Optional[CleanupResult], error: Optional[BaseException]) -> None:
        self._is_executing = False
        self.execute_button.configure(state="normal", text=self.t("cache_clean_execute"))
        self._show_status(self._format_result(result, error))

    def _format_result(self, result: Optional[CleanupResult], error: Optional[BaseException]) -> str:
        error_prefix = self.t("cache_clean_error")
        if isinstance(error, CannotCleanNowError):
            reason = error.reason or self.t("cache_clean_unknown_reason")
            return f"{error_prefix}: " + self.t("cache_clean_error_cannot_clean", reason=reason)
        if isinstance(error, CdpError):
            return f"{error_prefix}: " + self.t("cache_clean_error_state_check", error=str(error))
        if error is not None:
            return f"{error_prefix}: {error}"

        unexpected = self.t("cache_clean_error_unexpected_result")
        total = sum(item.count for item in result.items if item.count)
        lines = [self.t("cache_clean_completed"), ""]
        if total > 0:
            lines += [self.t("cache_clean_total_cleaned", count=total), ""]
        for item in result.items:
            if item.count is not None:
                lines.append(f"  {item.name}: {item.count}")
            else:
                fallback = unexpected if item.script_failed else self.t("cache_clean_error_unknown_error")
                lines.append(f"  {item.name}: {error_prefix} - {item.error or fallback}")

        warnings = [self.t("cache_clean_error_photo_open", item=name) for name in result.skipped]
        warnings += [f"{item.name}: {item.error or unexpected}" for item in result.items if item.script_failed]
        if warnings:
            lines += ["", self.t("cache_clean_warnings")]
            lines += [f"  - {warning}" for warning in warnings]
        return "\n".join(lines)

    def _show_status_key(self, key: str) -> None:
        """显示一条固定提示（切换语言时会重新翻译）"""
        set_textbox_text(self.status_text, self.t(key))
        self._status_key = key

    def _show_status(self, message: str) -> None:
        set_textbox_text(self.status_text, message)
        self._status_key = None

    def update_language(self) -> None:
        super().update_language()
        for widget, key in self._translated_widgets:
            widget.configure(text=self.t(key))
        self.execute_button.configure(text=self.t("cache_clean_executing" if self._is_executing else "cache_clean_execute"))
        self.scan_button.configure(text=self.t("cache_clean_scanning" if self._is_scanning else "cache_clean_scan_button"))
        self.scan_hint_label.configure(text=self._scan_hint())
        if self._status_key is not None:
            set_textbox_text(self.status_text, self.t(self._status_key))
