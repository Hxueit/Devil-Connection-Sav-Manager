"""缓存清理窗口：选择清理项后在游戏页面里执行对应的清理脚本"""
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
from src.modules.runtime_modify.dialogs import RuntimeDialog, create_standard_button
from src.modules.runtime_modify.service import evaluate
from src.utils.background import run_in_background
from src.utils.styles import Colors, get_cjk_font



class CleanupJob:
    """一个要执行的清理项"""

    def __init__(self, name: str, script: str, requires_photo_closed: bool = False) -> None:
        self.name = name
        self.script = script
        self.requires_photo_closed = requires_photo_closed


def run_cleanup(ws_url: str, jobs: List[CleanupJob]) -> Dict[str, Any]:
    """依次执行清理脚本（在后台线程调用），返回：

    - {"state_error": 错误信息}：无法检查游戏状态
    - {"cannot_clean": 原因或 None}：游戏正在转场/动画，现在清理会出问题
    - {"items": [(名称, 数量, 错误)], "failed": [(名称, 错误)], "skipped": [名称]}
      数量为 None 表示该项失败；failed 是执行脚本本身出错的项；skipped 是因照片界面打开而跳过的项
    """
    state, error = evaluate(ws_url, JS_CHECK_STATE)
    if error is not None:
        return {"state_error": error}
    if not isinstance(state, dict) or not state.get("canClean"):
        return {"cannot_clean": state.get("reason") if isinstance(state, dict) else None}

    photo_open = False
    if any(job.requires_photo_closed for job in jobs):
        photo, error = evaluate(ws_url, JS_CHECK_PHOTO_OPEN)
        photo_open = error is None and isinstance(photo, dict) and bool(photo.get("isOpen"))

    items: List[Tuple[str, Optional[int], Optional[str]]] = []
    failed: List[Tuple[str, Optional[str]]] = []
    skipped: List[str] = []
    for job in jobs:
        if job.requires_photo_closed and photo_open:
            skipped.append(job.name)
            continue
        result, error = evaluate(ws_url, job.script)
        if error is not None or not isinstance(result, dict):
            # error 为 None 说明返回值不是预期的 {success, count}，由界面显示翻译后的提示
            items.append((job.name, None, error))
            failed.append((job.name, error))
        elif result.get("success"):
            items.append((job.name, int(result.get("count") or 0), None))
        else:
            items.append((job.name, None, result.get("error")))
    return {"items": items, "failed": failed, "skipped": skipped}


class CacheCleanDialog(RuntimeDialog):
    """左侧是执行按钮和结果，右侧是可勾选的清理项"""

    def __init__(self, parent: tk.Misc, t: Callable[..., str], get_ws_url: Callable[[], Optional[str]]) -> None:
        super().__init__(parent, t, "cache_clean_dialog_title", "550x550", (500, 450))
        self.get_ws_url = get_ws_url

        self._item_vars: Dict[str, tk.BooleanVar] = {}   # 固定清理项 key -> 是否勾选
        # 扫描出的项：(名称, 清理脚本, 是否勾选, 复选框)
        self._dynamic_items: List[Tuple[str, str, tk.BooleanVar, ctk.CTkCheckBox]] = []
        self._is_executing = False

        self._build_ui()

    def _build_ui(self) -> None:
        container = ctk.CTkFrame(self, fg_color=Colors.WHITE)
        container.pack(fill="both", expand=True, padx=10, pady=10)
        content = ctk.CTkFrame(container, fg_color=Colors.WHITE)
        content.pack(fill="both", expand=True)

        left = ctk.CTkFrame(content, fg_color=Colors.WHITE, width=120)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        self.execute_button = create_standard_button(
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
        self._set_status(self.t("cache_clean_status_ready"))

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
            text=self.t("cache_clean_scan_hint"),
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
        return ctk.CTkLabel(
            parent, text=self.t(key), font=get_cjk_font(11, "bold"), text_color=Colors.TEXT_PRIMARY, anchor="w")

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

        self._checkbox(parent, self.t(select_all_key), select_all, command=toggle_all).pack(anchor="w", pady=(0, 5))
        for key, var in zip(scripts, item_vars):
            self._checkbox(parent, self.t(f"cache_clean_item_{key}"), var).pack(anchor="w", padx=(20, 0), pady=(0, 3))
            self._item_vars[key] = var

    # ------------------------------------------------------------ 扫描

    def _on_scan_clicked(self) -> None:
        ws_url = self.get_ws_url()
        if not ws_url:
            self._set_status(self.t("cache_clean_error_no_connection"))
            return
        self.scan_button.configure(text=self.t("cache_clean_scanning"), state="disabled")
        run_in_background(self, lambda: evaluate(ws_url, JS_SCAN_DANGEROUS_ITEMS), self._on_scan_done)

    def _on_scan_done(self, outcome: Any, exc: Optional[BaseException]) -> None:
        self.scan_button.configure(text=self.t("cache_clean_scan_button"), state="normal")
        found, error = outcome if exc is None else (None, str(exc))
        if error is not None:
            self._set_status(self.t("cache_clean_scan_failed").format(error=error))
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

        if self._dynamic_items:
            hint = self.t("cache_clean_items_found_count").format(count=len(self._dynamic_items))
        else:
            hint = self.t("cache_clean_no_items_found")
        self.scan_hint_label.configure(text=hint)

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
            self._set_status(self.t("cache_clean_no_item_selected"))
            return
        ws_url = self.get_ws_url()
        if not ws_url:
            self._set_status(self.t("cache_clean_error_no_connection"))
            return

        self._is_executing = True
        self.execute_button.configure(state="disabled", text=self.t("cache_clean_executing"))
        self._set_status(self.t("cache_clean_checking_state"))
        run_in_background(self, lambda: run_cleanup(ws_url, jobs), self._on_cleanup_done)

    def _on_cleanup_done(self, result: Optional[Dict[str, Any]], exc: Optional[BaseException]) -> None:
        self._is_executing = False
        self.execute_button.configure(state="normal", text=self.t("cache_clean_execute"))
        self._set_status(self._format_result(result, exc))

    def _format_result(self, result: Optional[Dict[str, Any]], exc: Optional[BaseException]) -> str:
        error_prefix = self.t("cache_clean_error")
        if exc is not None:
            return f"{error_prefix}: {exc}"
        if "state_error" in result:
            return f"{error_prefix}: " + self.t("cache_clean_error_state_check").format(error=result["state_error"])
        if "cannot_clean" in result:
            reason = result["cannot_clean"] or self.t("cache_clean_unknown_reason")
            return f"{error_prefix}: " + self.t("cache_clean_error_cannot_clean").format(reason=reason)

        unexpected = self.t("cache_clean_error_unexpected_result")
        failed_names = {name for name, _error in result["failed"]}
        total = sum(count for _name, count, _error in result["items"] if count)
        lines = [self.t("cache_clean_completed"), ""]
        if total > 0:
            lines += [self.t("cache_clean_total_cleaned").format(count=total), ""]
        for name, count, error in result["items"]:
            if count is not None:
                lines.append(f"  {name}: {count}")
            else:
                fallback = unexpected if name in failed_names else self.t("cache_clean_error_unknown_error")
                lines.append(f"  {name}: {error_prefix} - {error or fallback}")

        warnings = [self.t("cache_clean_error_photo_open").format(item=name) for name in result["skipped"]]
        warnings += [f"{name}: {error or unexpected}" for name, error in result["failed"]]
        if warnings:
            lines += ["", self.t("cache_clean_warnings")]
            lines += [f"  - {warning}" for warning in warnings]
        return "\n".join(lines)

    def _set_status(self, message: str) -> None:
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", message)
        self.status_text.configure(state="disabled")

    def update_language(self) -> None:
        super().update_language()
        key = "cache_clean_executing" if self._is_executing else "cache_clean_execute"
        self.execute_button.configure(text=self.t(key))
