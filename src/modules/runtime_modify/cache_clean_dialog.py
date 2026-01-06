"""缓存清理弹窗

提供缓存清理功能的UI界面，允许用户选择清理项并执行清理操作。
"""
import asyncio
import logging
import threading
from typing import Optional, Dict, Any, Callable, List

import customtkinter as ctk
import tkinter as tk

from src.modules.runtime_modify.service import RuntimeModifyService
from src.modules.runtime_modify.cache_clean_scripts import (
    CLEANUP_SCRIPTS,
    SAFE_CLEANUP_ITEMS,
    RISKY_CLEANUP_ITEMS,
    JS_CHECK_STATE,
    JS_CHECK_PHOTO_OPEN,
    JS_SCAN_DANGEROUS_ITEMS,
    generate_cleanup_script
)
from src.utils.styles import Colors, get_cjk_font
from src.utils.ui_utils import set_window_icon
from src.modules.others.utils import center_window

logger = logging.getLogger(__name__)


class CacheCleanDialog(ctk.CTkToplevel):
    """缓存清理弹窗
    
    提供缓存清理功能的交互界面，包含清理项选择和执行功能。
    """
    
    def __init__(
        self,
        parent_window: ctk.CTk,
        service: RuntimeModifyService,
        get_ws_url: Callable[[], Optional[str]],
        translations: Dict[str, Dict[str, str]],
        current_language: str
    ) -> None:
        """初始化缓存清理弹窗
        
        Args:
            parent_window: 父窗口
            service: RuntimeModifyService 实例
            get_ws_url: 获取当前 WebSocket URL 的回调函数
            translations: 翻译字典
            current_language: 当前语言
        """
        super().__init__(parent_window)
        
        self.service = service
        self.get_ws_url = get_ws_url
        self.translations = translations
        self.current_language = current_language
        
        self.checkboxes: Dict[str, ctk.CTkCheckBox] = {}
        self.group_checkboxes: Dict[str, ctk.CTkCheckBox] = {}
        self.execute_button: Optional[ctk.CTkButton] = None
        self.status_text: Optional[ctk.CTkTextbox] = None
        self.scrollable_frame: Optional[ctk.CTkScrollableFrame] = None
        self.dangerous_frame: Optional[ctk.CTkFrame] = None
        self.scan_button: Optional[ctk.CTkButton] = None
        self.scan_hint_label: Optional[ctk.CTkLabel] = None
        
        self._dynamic_scripts: Dict[str, Dict[str, Any]] = {}
        
        self.is_executing = False
        self._executor: Optional[threading.Thread] = None
        self._is_scanning = False
        
        self._configure_window()
        self._init_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)
        
        self.after(50, lambda: set_window_icon(self))
        self.after(200, lambda: set_window_icon(self))
    
    def _configure_window(self) -> None:
        """配置窗口属性"""
        self.title(self.t("cache_clean_dialog_title"))
        self.geometry("550x550")
        self.minsize(500, 450)
        center_window(self)
    
    def t(self, key: str, **kwargs: Any) -> str:
        """翻译函数"""
        text = self.translations.get(self.current_language, {}).get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError):
                logger.debug(f"Translation format error for key '{key}'")
                return text
        return text
    
    def _init_ui(self) -> None:
        """初始化UI"""
        main_container = ctk.CTkFrame(self, fg_color=Colors.WHITE)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        content_frame = ctk.CTkFrame(main_container, fg_color=Colors.WHITE)
        content_frame.pack(fill="both", expand=True)
        
        left_frame = ctk.CTkFrame(content_frame, fg_color=Colors.WHITE)
        left_frame.pack(side="left", fill="y", padx=(0, 10))
        left_frame.pack_propagate(False)
        left_frame.configure(width=120)
        
        self.execute_button = ctk.CTkButton(
            left_frame,
            text=self.t("cache_clean_execute"),
            command=self._on_execute_clicked,
            corner_radius=8,
            fg_color=Colors.WHITE,
            hover_color=Colors.LIGHT_GRAY,
            border_width=1,
            border_color=Colors.GRAY,
            text_color=Colors.TEXT_PRIMARY,
            font=get_cjk_font(11),
            height=35
        )
        self.execute_button.pack(fill="x", pady=(0, 10))
        
        self.status_text = ctk.CTkTextbox(
            left_frame,
            font=get_cjk_font(9),
            fg_color=Colors.LIGHT_GRAY,
            text_color=Colors.TEXT_PRIMARY,
            border_color=Colors.GRAY,
            border_width=1,
            corner_radius=8,
            wrap="word"
        )
        self.status_text.pack(fill="both", expand=True)
        self.status_text.configure(state="disabled")
        self._update_status(self.t("cache_clean_status_ready"))
        
        right_frame = ctk.CTkFrame(content_frame, fg_color=Colors.WHITE)
        right_frame.pack(side="right", fill="both", expand=True)
        
        self.scrollable_frame = ctk.CTkScrollableFrame(
            right_frame,
            fg_color=Colors.WHITE,
            scrollbar_button_color=Colors.GRAY,
            scrollbar_button_hover_color=Colors.LIGHT_GRAY
        )
        self.scrollable_frame.pack(fill="both", expand=True)
        
        self._create_checkboxes()
    
    def _create_checkboxes(self) -> None:
        """创建清理项复选框"""
        if not self.scrollable_frame:
            return
        
        safe_group_label = ctk.CTkLabel(
            self.scrollable_frame,
            text=self.t("cache_clean_safe_group"),
            font=get_cjk_font(11, "bold"),
            text_color=Colors.TEXT_PRIMARY,
            anchor="w"
        )
        safe_group_label.pack(anchor="w", pady=(0, 5))
        
        safe_group_var = tk.BooleanVar(value=True)
        safe_group_checkbox = ctk.CTkCheckBox(
            self.scrollable_frame,
            text=self.t("cache_clean_select_all_safe"),
            variable=safe_group_var,
            command=lambda: self._on_group_toggle("safe", safe_group_var.get()),
            font=get_cjk_font(10),
            text_color=Colors.TEXT_PRIMARY
        )
        safe_group_checkbox.pack(anchor="w", pady=(0, 5))
        self.group_checkboxes["safe"] = safe_group_checkbox
        
        for item_key in SAFE_CLEANUP_ITEMS:
            if item_key not in CLEANUP_SCRIPTS:
                continue
            
            var = tk.BooleanVar(value=True)
            checkbox = ctk.CTkCheckBox(
                self.scrollable_frame,
                text=self.t(f"cache_clean_item_{item_key}"),
                variable=var,
                font=get_cjk_font(10),
                text_color=Colors.TEXT_PRIMARY
            )
            checkbox.pack(anchor="w", padx=(20, 0), pady=(0, 3))
            self.checkboxes[item_key] = checkbox
        
        separator = ctk.CTkFrame(
            self.scrollable_frame,
            height=1,
            fg_color=Colors.GRAY
        )
        separator.pack(fill="x", pady=(10, 10))
        
        risky_group_label = ctk.CTkLabel(
            self.scrollable_frame,
            text=self.t("cache_clean_risky_group"),
            font=get_cjk_font(11, "bold"),
            text_color=Colors.TEXT_PRIMARY,
            anchor="w"
        )
        risky_group_label.pack(anchor="w", pady=(0, 5))
        
        risky_group_var = tk.BooleanVar(value=False)
        risky_group_checkbox = ctk.CTkCheckBox(
            self.scrollable_frame,
            text=self.t("cache_clean_select_all_risky"),
            variable=risky_group_var,
            command=lambda: self._on_group_toggle("risky", risky_group_var.get()),
            font=get_cjk_font(10),
            text_color=Colors.TEXT_PRIMARY
        )
        risky_group_checkbox.pack(anchor="w", pady=(0, 5))
        self.group_checkboxes["risky"] = risky_group_checkbox
        
        for item_key in RISKY_CLEANUP_ITEMS:
            if item_key not in CLEANUP_SCRIPTS:
                continue
            
            var = tk.BooleanVar(value=False)
            checkbox = ctk.CTkCheckBox(
                self.scrollable_frame,
                text=self.t(f"cache_clean_item_{item_key}"),
                variable=var,
                font=get_cjk_font(10),
                text_color=Colors.TEXT_PRIMARY
            )
            checkbox.pack(anchor="w", padx=(20, 0), pady=(0, 3))
            self.checkboxes[item_key] = checkbox
        
        separator3 = ctk.CTkFrame(
            self.scrollable_frame,
            height=1,
            fg_color=Colors.GRAY
        )
        separator3.pack(fill="x", pady=(10, 10))
        
        dangerous_frame = ctk.CTkFrame(
            self.scrollable_frame,
            fg_color=Colors.WHITE
        )
        dangerous_frame.pack(fill="x", pady=(0, 5))
        
        dangerous_group_label = ctk.CTkLabel(
            dangerous_frame,
            text=self.t("cache_clean_all"),
            font=get_cjk_font(11, "bold"),
            text_color=Colors.TEXT_PRIMARY,
            anchor="w"
        )
        dangerous_group_label.pack(anchor="w", padx=0, pady=(0, 5))
        
        self.dangerous_frame = dangerous_frame
        
        self.scan_hint_label = ctk.CTkLabel(
            dangerous_frame,
            text=self.t("cache_clean_scan_hint"),
            font=get_cjk_font(9),
            text_color=Colors.TEXT_SECONDARY,
            anchor="w",
            wraplength=350
        )
        self.scan_hint_label.pack(anchor="w", padx=0, pady=(0, 10))
        
        self.scan_button = ctk.CTkButton(
            dangerous_frame,
            text=self.t("cache_clean_scan_button"),
            command=self._on_scan_clicked,
            font=get_cjk_font(10),
            width=120,
            height=30
        )
        self.scan_button.pack(anchor="w", padx=0, pady=(0, 10))
    
    def _on_group_toggle(self, group: str, checked: bool) -> None:
        """组复选框切换回调"""
        if group == "safe":
            items = SAFE_CLEANUP_ITEMS
        elif group == "risky":
            items = RISKY_CLEANUP_ITEMS
        elif group == "dangerous":
            items = [key for key in self.checkboxes.keys() if key.startswith("dynamic_")]
        else:
            items = []
        
        for item_key in items:
            checkbox = self.checkboxes.get(item_key)
            if not checkbox:
                continue
            
            var = checkbox.cget("variable")
            if isinstance(var, str):
                var = self.nametowidget(var)
            if hasattr(var, 'set'):
                var.set(checked)
    
    def _on_scan_clicked(self) -> None:
        """扫描按钮点击回调"""
        if self._is_scanning:
            return
        
        ws_url = self.get_ws_url()
        if not ws_url:
            self._update_status(self.t("cache_clean_error_no_connection"))
            return
        
        def run_scan():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                self.after(0, lambda: self._update_scan_status(True))
                result = loop.run_until_complete(self._scan_dangerous_items(ws_url))
                self.after(0, lambda: self._on_scan_complete(result))
            except Exception as e:
                logger.error(f"Scan failed: {e}", exc_info=True)
                self.after(0, lambda: self._update_status(
                    self.t("cache_clean_scan_failed").format(error=str(e))
                ))
            finally:
                self.after(0, lambda: self._update_scan_status(False))
                if loop:
                    try:
                        pending_tasks = asyncio.all_tasks(loop)
                        if pending_tasks:
                            for task in pending_tasks:
                                task.cancel()
                            loop.run_until_complete(
                                asyncio.gather(*pending_tasks, return_exceptions=True)
                            )
                        loop.close()
                    except Exception as e:
                        logger.debug(f"Error cleaning up event loop: {e}")
        
        thread = threading.Thread(target=run_scan, daemon=True)
        thread.start()
    
    def _update_scan_status(self, is_scanning: bool) -> None:
        """更新扫描状态"""
        self._is_scanning = is_scanning
        if self.scan_button:
            if is_scanning:
                self.scan_button.configure(text=self.t("cache_clean_scanning"), state="disabled")
            else:
                self.scan_button.configure(text=self.t("cache_clean_scan_button"), state="normal")
    
    async def _scan_dangerous_items(self, ws_url: str) -> List[Dict[str, Any]]:
        """异步扫描危险的清理项
        
        Args:
            ws_url: WebSocket URL
            
        Returns:
            扫描结果列表
        """
        result, error = await self.service.eval_expr(ws_url, JS_SCAN_DANGEROUS_ITEMS)
        if error:
            logger.error(f"Scan error: {error}")
            return []
        
        if isinstance(result, list):
            return result
        return []
    
    def _on_scan_complete(self, items: List[Dict[str, Any]]) -> None:
        """扫描完成回调
        
        Args:
            items: 扫描到的项列表
        """
        if not items:
            if self.scan_hint_label:
                self.scan_hint_label.configure(text=self.t("cache_clean_no_items_found"))
            return
        
        self._clear_dynamic_items()
        self._create_dynamic_items(items)
        
        if self.scan_hint_label:
            self.scan_hint_label.configure(
                text=self.t("cache_clean_items_found_count").format(count=len(items))
            )
    
    def _clear_dynamic_items(self) -> None:
        """清除所有动态创建的项"""
        keys_to_remove = [
            key for key in self.checkboxes.keys()
            if key.startswith("dynamic_")
        ]
        for key in keys_to_remove:
            checkbox = self.checkboxes.pop(key, None)
            if checkbox and checkbox.winfo_exists():
                checkbox.destroy()
        
        self._dynamic_scripts.clear()
    
    def _create_dynamic_items(self, items: List[Dict[str, Any]]) -> None:
        """根据扫描结果动态创建复选框
        
        Args:
            items: 扫描到的项列表
        """
        if not self.dangerous_frame:
            return
        
        for idx, item_info in enumerate(items):
            item_key = f"dynamic_{hash(item_info.get('name', str(idx)))}"
            
            script = generate_cleanup_script(item_info)
            if not script:
                continue
            
            display_name = item_info.get('name', self.t("cache_clean_unknown_item"))
            self._dynamic_scripts[item_key] = {
                'script': script,
                'display_name': display_name
            }
            
            var = tk.BooleanVar(value=False)
            checkbox = ctk.CTkCheckBox(
                self.dangerous_frame,
                text=display_name,
                variable=var,
                font=get_cjk_font(10),
                text_color=Colors.TEXT_PRIMARY
            )
            checkbox.pack(anchor="w", padx=(20, 0), pady=(0, 3))
            self.checkboxes[item_key] = checkbox
    
    def _get_selected_items(self) -> List[str]:
        """获取选中的清理项"""
        selected = []
        for item_key, checkbox in self.checkboxes.items():
            var = checkbox.cget("variable")
            if isinstance(var, str):
                var = self.nametowidget(var)
            if hasattr(var, 'get') and var.get():
                selected.append(item_key)
        return selected
    
    def _on_execute_clicked(self) -> None:
        """执行清理按钮点击回调"""
        if self.is_executing:
            return
        
        selected_items = self._get_selected_items()
        if not selected_items:
            self._update_status(self.t("cache_clean_no_item_selected"))
            return
        
        ws_url = self.get_ws_url()
        if not ws_url:
            self._update_status(self.t("cache_clean_error_no_connection"))
            return
        
        self._execute_cleanup_async(ws_url, selected_items)
    
    def _execute_cleanup_async(self, ws_url: str, selected_items: List[str]) -> None:
        """异步执行清理操作"""
        if self.is_executing:
            return
        
        self.is_executing = True
        if self.execute_button:
            self.execute_button.configure(state="disabled", text=self.t("cache_clean_executing"))
        
        def run_in_thread() -> None:
            """在后台线程中运行异步代码"""
            loop: Optional[asyncio.AbstractEventLoop] = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                result = loop.run_until_complete(
                    self._execute_cleanup(ws_url, selected_items)
                )
                
                self.after(0, lambda: self._on_cleanup_complete(result))
            except Exception as e:
                logger.exception("Error executing cleanup")
                error_msg = {"success": False, "error": str(e)}
                self.after(0, lambda: self._on_cleanup_complete(error_msg))
            finally:
                if loop:
                    try:
                        pending_tasks = asyncio.all_tasks(loop)
                        if pending_tasks:
                            for task in pending_tasks:
                                task.cancel()
                            loop.run_until_complete(
                                asyncio.gather(*pending_tasks, return_exceptions=True)
                            )
                        loop.close()
                    except Exception as e:
                        logger.debug(f"Error cleaning up event loop: {e}")
        
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
        self._executor = thread
    
    async def _execute_cleanup(
        self,
        ws_url: str,
        selected_items: List[str]
    ) -> Dict[str, Any]:
        """执行清理操作
        
        Args:
            ws_url: WebSocket URL
            selected_items: 选中的清理项列表
            
        Returns:
            清理结果字典
        """
        results = {
            "success": True,
            "items": {},
            "total_count": 0,
            "errors": []
        }
        
        self.after(0, lambda: self._update_status(self.t("cache_clean_checking_state")))
        state_result, state_error = await self.service.eval_expr(ws_url, JS_CHECK_STATE)
        
        if state_error:
            error_msg = state_error.get("message", str(state_error))
            return {
                "success": False,
                "error": self.t("cache_clean_error_state_check").format(error=error_msg)
            }
        
        if not isinstance(state_result, dict) or not state_result.get("canClean"):
            reason = state_result.get("reason", self.t("cache_clean_unknown_reason"))
            return {
                "success": False,
                "error": self.t("cache_clean_error_cannot_clean").format(reason=reason)
            }
        
        for item_key in selected_items:
            if item_key.startswith("dynamic_"):
                continue
            
            if item_key not in CLEANUP_SCRIPTS:
                continue
            
            item_info = CLEANUP_SCRIPTS[item_key]
            if item_info.get("requires_photo_closed"):
                photo_result, photo_error = await self.service.eval_expr(ws_url, JS_CHECK_PHOTO_OPEN)
                if not photo_error and isinstance(photo_result, dict) and photo_result.get("isOpen"):
                    item_name = self.t(f"cache_clean_item_{item_key}")
                    results["errors"].append(
                        self.t("cache_clean_error_photo_open").format(item=item_name)
                    )
        
        for item_key in selected_items:
            if item_key.startswith("dynamic_"):
                if item_key not in self._dynamic_scripts:
                    continue
                item_info = self._dynamic_scripts[item_key]
                item_name = item_info.get("display_name", item_key)
                script = item_info.get("script", "")
            else:
                if item_key not in CLEANUP_SCRIPTS:
                    continue
                item_info = CLEANUP_SCRIPTS[item_key]
                item_name = self.t(f"cache_clean_item_{item_key}")
                script = item_info.get("script", "")
            
            if not script:
                continue
            
            self.after(0, lambda name=item_name: self._update_status(
                self.t("cache_clean_cleaning_item").format(item=name)
            ))
            
            result, error = await self.service.eval_expr(ws_url, script)
            
            if error:
                error_msg = error.get("message", str(error))
                results["items"][item_key] = {
                    "success": False,
                    "error": error_msg
                }
                results["errors"].append(f"{item_name}: {error_msg}")
            elif isinstance(result, dict):
                success = result.get("success", False)
                count = result.get("count", 0)
                results["items"][item_key] = {
                    "success": success,
                    "count": count
                }
                if success:
                    results["total_count"] += count
            else:
                error_msg = self.t("cache_clean_error_unexpected_result")
                results["items"][item_key] = {
                    "success": False,
                    "error": error_msg
                }
                results["errors"].append(f"{item_name}: {error_msg}")
        
        return results
    
    def _on_cleanup_complete(self, result: Dict[str, Any]) -> None:
        """清理完成回调"""
        self.is_executing = False
        if self.execute_button:
            self.execute_button.configure(state="normal", text=self.t("cache_clean_execute"))
        
        if not result.get("success"):
            error_msg = result.get("error", self.t("cache_clean_error_unknown"))
            self._update_status(f"{self.t('cache_clean_error')}: {error_msg}")
            return
        
        messages = [self.t("cache_clean_completed"), ""]
        
        total_count = result.get("total_count", 0)
        if total_count > 0:
            messages.extend([
                self.t("cache_clean_total_cleaned").format(count=total_count),
                ""
            ])
        
        items = result.get("items", {})
        for item_key, item_result in items.items():
            if item_key.startswith("dynamic_"):
                item_name = self._dynamic_scripts.get(item_key, {}).get("display_name", item_key)
            else:
                item_name = self.t(f"cache_clean_item_{item_key}")
            
            if item_result.get("success"):
                count = item_result.get("count", 0)
                messages.append(f"  {item_name}: {count}")
            else:
                error = item_result.get("error", self.t("cache_clean_error_unknown_error"))
                messages.append(f"  {item_name}: {self.t('cache_clean_error')} - {error}")
        
        errors = result.get("errors", [])
        if errors:
            messages.extend(["", self.t("cache_clean_warnings")])
            messages.extend(f"  - {error}" for error in errors)
        
        self._update_status("\n".join(messages))
    
    def _update_status(self, message: str) -> None:
        """更新状态显示"""
        if not self.status_text:
            return
        
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", message)
        self.status_text.configure(state="disabled")
    
    def _on_window_close(self) -> None:
        """窗口关闭回调"""
        if self.is_executing and self._executor and self._executor.is_alive():
            pass
        self.destroy()
    
    def update_language(self, language: str) -> None:
        """更新语言
        
        Args:
            language: 新的语言代码
        """
        if not isinstance(language, str) or not language:
            logger.warning(f"Invalid language code: {language}")
            return
        
        if language not in self.translations:
            logger.warning(f"Unsupported language: {language}")
            return
        
        self.current_language = language
        self.title(self.t("cache_clean_dialog_title"))
        
        if self.execute_button:
            text_key = "cache_clean_executing" if self.is_executing else "cache_clean_execute"
            self.execute_button.configure(text=self.t(text_key))

