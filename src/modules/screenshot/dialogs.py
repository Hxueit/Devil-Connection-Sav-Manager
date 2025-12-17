"""对话框组件模块

提供截图管理相关的对话框功能，包括添加、替换、导出等对话框
"""

import os
import json
import urllib.parse
import base64
import tempfile
import threading
import zipfile
from datetime import datetime
from io import BytesIO
import tkinter as tk
from tkinter import filedialog, messagebox, Toplevel, Label, Entry
from tkinter import ttk
from PIL import Image
from PIL import ImageTk
from src.modules.screenshot.constants import VALID_IMAGE_EXTENSIONS
from src.utils.ui_utils import showinfo_relative, showwarning_relative, showerror_relative, askyesno_relative
from src.utils.styles import Colors


class ScreenshotDialogs:
    """截图对话框管理类"""
    
    def __init__(self, root, storage_dir, screenshot_manager, t_func, get_cjk_font, Colors, set_window_icon, 
                 translations, current_language, load_screenshots_callback, show_status_indicator_callback):
        """初始化对话框管理器
        
        Args:
            root: 根窗口
            storage_dir: 存储目录
            screenshot_manager: 截图管理器实例
            t_func: 翻译函数
            get_cjk_font: 字体获取函数
            Colors: 颜色常量类
            set_window_icon: 窗口图标设置函数
            translations: 翻译字典
            current_language: 当前语言
            load_screenshots_callback: 加载截图列表的回调函数
            show_status_indicator_callback: 显示状态指示器的回调函数
        """
        self.root = root
        self.storage_dir = storage_dir
        self.screenshot_manager = screenshot_manager
        self.t = t_func
        self.get_cjk_font = get_cjk_font
        self.Colors = Colors
        self.set_window_icon = set_window_icon
        self.translations = translations
        self.current_language = current_language
        self.load_screenshots_callback = load_screenshots_callback
        self.show_status_indicator_callback = show_status_indicator_callback
    
    def show_add_dialog(self):
        """显示添加新截图对话框"""
        new_png_path = filedialog.askopenfilename(
            title=self.t("select_new_image"),
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.apng"), ("PNG files", "*.png"), ("GIF files", "*.gif"), ("APNG files", "*.apng"), ("All files", "*.*")]
        )
        
        if not new_png_path:
            return
        
        filename = os.path.basename(new_png_path)
        ext = os.path.splitext(filename)[1].lower()
        is_valid_image = ext in ['.png', '.jpg', '.jpeg', '.gif', '.apng']
        
        is_4_3_ratio = False
        if is_valid_image:
            try:
                img = Image.open(new_png_path)
                try:
                    width, height = img.size
                    expected_height = width * 3 / 4
                    if abs(height - expected_height) <= 30:
                        is_4_3_ratio = True
                finally:
                    img.close()
            except Exception:
                pass
        
        dialog = Toplevel(self.root)
        dialog.title(self.t("add_new_title"))
        window_height = 300
        if not is_valid_image:
            window_height += 80
        if not is_4_3_ratio and is_valid_image:
            window_height += 80
        dialog.geometry(f"400x{window_height}")
        dialog.configure(bg=self.Colors.WHITE)
        self.set_window_icon(dialog)
        dialog.transient(self.root)
        dialog.grab_set()
        
        if not is_valid_image:
            warning_label = tk.Label(dialog, text=self.t("file_extension_warning", filename=filename), 
                                    fg=Colors.TEXT_WARNING_PINK, font=self.get_cjk_font(10), 
                                    wraplength=380, justify="left", bg=self.Colors.WHITE)
            warning_label.pack(pady=5, padx=10, anchor="w")
        
        if not is_4_3_ratio and is_valid_image:
            aspect_warning_label = tk.Label(dialog, text=self.t("aspect_ratio_warning"), 
                                           fg=Colors.TEXT_WARNING_AQUA, font=self.get_cjk_font(10), 
                                           wraplength=380, justify="left", bg=self.Colors.WHITE)
            aspect_warning_label.pack(pady=5, padx=10, anchor="w")
        
        id_frame = ttk.Frame(dialog, style="White.TFrame")
        id_frame.pack(pady=10, padx=20, fill='x')
        id_label = tk.Label(id_frame, text=self.t("id_label"),
                           font=self.get_cjk_font(10), fg=self.Colors.TEXT_PRIMARY, bg=self.Colors.WHITE)
        id_label.pack(anchor='w')
        id_entry = Entry(id_frame, width=40)
        id_entry.pack(fill='x', pady=(5, 0))
        
        date_frame = ttk.Frame(dialog, style="White.TFrame")
        date_frame.pack(pady=10, padx=20, fill='x')
        date_label = tk.Label(date_frame, text=self.t("date_label"),
                             font=self.get_cjk_font(10), fg=self.Colors.TEXT_PRIMARY, bg=self.Colors.WHITE)
        date_label.pack(anchor='w')
        date_entry = Entry(date_frame, width=40)
        date_entry.pack(fill='x', pady=(5, 0))
        
        button_frame = ttk.Frame(dialog, style="White.TFrame")
        button_frame.pack(pady=10)
        
        def confirm_add():
            new_id = id_entry.get().strip()
            date_str = date_entry.get().strip()
            
            if not new_id:
                new_id = self.screenshot_manager.generate_id()
            
            if new_id in self.screenshot_manager.sav_pairs:
                showerror_relative(self.root, self.t("error"), self.t("id_exists"))
                return
            
            if not date_str:
                date_str = self.screenshot_manager.get_current_datetime()
            else:
                try:
                    datetime.strptime(date_str, '%Y/%m/%d %H:%M:%S')
                except ValueError:
                    showerror_relative(self.root, self.t("error"), self.t("invalid_date_format"))
                    return
            
            if not is_valid_image:
                result = askyesno_relative(self.root,
                    self.t("warning"),
                    self.t("file_extension_warning").format(filename=filename)
                )
                if not result:
                    dialog.destroy()
                    return
            
            success, message = self.screenshot_manager.add_screenshot(new_id, date_str, new_png_path)
            
            if success:
                showinfo_relative(self.root, self.t("success"), self.t("add_success").format(id=new_id))
                self.load_screenshots_callback()
                self.show_status_indicator_callback(new_id, is_new=True)
            else:
                showerror_relative(self.root, self.t("error"), message)
            
            dialog.destroy()
        
        ttk.Button(button_frame, text=self.t("confirm"), command=confirm_add).pack(side='left', padx=5)
        ttk.Button(button_frame, text=self.t("delete_cancel"), command=dialog.destroy).pack(side='left', padx=5)
        
        id_entry.bind('<Return>', lambda e: confirm_add())
        date_entry.bind('<Return>', lambda e: confirm_add())
        id_entry.focus()
    
    def show_replace_dialog(self, id_str, checkbox_vars, tree):
        """显示替换截图对话框
        
        Args:
            id_str: 截图ID
            checkbox_vars: 复选框变量字典
            tree: Treeview组件
        """
        pair = self.screenshot_manager.sav_pairs.get(id_str, [None, None])
        if pair[0] is None or pair[1] is None:
            showerror_relative(self.root, self.t("error"), self.t("file_missing"))
            return
        
        main_sav = os.path.join(self.storage_dir, pair[0])
        thumb_sav = os.path.join(self.storage_dir, pair[1])
        
        if not os.path.exists(main_sav) or not os.path.exists(thumb_sav):
            showerror_relative(self.root, self.t("error"), self.t("file_not_exist"))
            return
        
        new_png_path = filedialog.askopenfilename(
            title=self.t("select_new_image"),
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.apng"), ("PNG files", "*.png"), ("GIF files", "*.gif"), ("APNG files", "*.apng"), ("All files", "*.*")]
        )
        
        if not new_png_path:
            return
        
        file_ext = os.path.splitext(new_png_path)[1].lower()
        filename = os.path.basename(new_png_path)
        is_valid_image = file_ext in VALID_IMAGE_EXTENSIONS
        
        temp_png = None
        try:
            with open(main_sav, 'r', encoding='utf-8') as f:
                encoded = f.read().strip()
            unquoted = urllib.parse.unquote(encoded)
            data_uri = json.loads(unquoted)
            b64_part = data_uri.split(';base64,', 1)[1]
            img_data = base64.b64decode(b64_part)
            
            temp_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
            with open(temp_png, 'wb') as f:
                f.write(img_data)
        except (OSError, IOError, ValueError, KeyError) as e:
            messagebox.showerror(self.t("error"), self.t("file_not_found"))
            return
        
        popup = Toplevel(self.root)
        popup.title(self.t("replace_warning"))
        popup.geometry("900x500")
        popup.configure(bg=self.Colors.WHITE)
        self.set_window_icon(popup)
        popup.transient(self.root)
        popup.grab_set()
        
        if not is_valid_image:
            warning_label = tk.Label(popup, text=self.t("file_extension_warning", filename=filename), 
                                    fg=Colors.TEXT_WARNING_PINK, font=self.get_cjk_font(10), 
                                    wraplength=600, justify="left", bg=self.Colors.WHITE)
            warning_label.pack(pady=5, padx=10, anchor="w")
        
        confirm_label = tk.Label(popup, text=self.t("replace_confirm_text"), 
                                font=self.get_cjk_font(12), fg=self.Colors.TEXT_PRIMARY, bg=self.Colors.WHITE)
        confirm_label.pack(pady=10)
        
        image_frame = tk.Frame(popup, bg=self.Colors.WHITE)
        image_frame.pack(pady=10)
        
        orig_img = None
        orig_photo = None
        try:
            orig_img = Image.open(temp_png)
            orig_preview = orig_img.resize((400, 300), Image.Resampling.BILINEAR)
            orig_photo = ImageTk.PhotoImage(orig_preview)
            orig_label = Label(image_frame, image=orig_photo, bg=self.Colors.WHITE)
            orig_label.pack(side="left", padx=10)
            popup.orig_photo = orig_photo
        except Exception as e:
            error_label = Label(image_frame, text=self.t("preview_failed"), fg="red", 
                              font=self.get_cjk_font(12), bg=self.Colors.WHITE)
            error_label.pack(side="left", padx=10)
            popup.orig_photo = None
        finally:
            if orig_img:
                orig_img.close()
                if 'orig_preview' in locals():
                    orig_preview.close()
        
        arrow_label = tk.Label(image_frame, text="→", font=self.get_cjk_font(24),
                              fg=self.Colors.TEXT_PRIMARY, bg=self.Colors.WHITE)
        arrow_label.pack(side="left", padx=10)
        
        new_img = None
        new_photo = None
        try:
            new_img = Image.open(new_png_path)
            new_preview = new_img.resize((400, 300), Image.Resampling.BILINEAR)
            new_photo = ImageTk.PhotoImage(new_preview)
            new_label = Label(image_frame, image=new_photo, bg=self.Colors.WHITE)
            new_label.pack(side="left", padx=10)
            popup.new_photo = new_photo
        except Exception as e:
            error_label = Label(image_frame, text=self.t("preview_failed"), fg="red", 
                              font=self.get_cjk_font(12), bg=self.Colors.WHITE)
            error_label.pack(side="left", padx=10)
            popup.new_photo = None
        finally:
            if new_img:
                new_img.close()
                if 'new_preview' in locals():
                    new_preview.close()
        
        question_label = tk.Label(popup, text=self.t("replace_confirm_question"),
                                  font=self.get_cjk_font(10), fg=self.Colors.TEXT_PRIMARY, bg=self.Colors.WHITE)
        question_label.pack(pady=10)
        
        confirmed = False
        
        def yes():
            nonlocal confirmed
            confirmed = True
            popup.destroy()
        
        def no():
            popup.destroy()
        
        button_frame = tk.Frame(popup, bg=self.Colors.WHITE)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text=self.t("replace_yes"), command=yes).pack(side="left", padx=10)
        ttk.Button(button_frame, text=self.t("replace_no"), command=no).pack(side="right", padx=10)
        
        popup.bind('<Return>', lambda e: yes())
        popup.bind('<Escape>', lambda e: no())
        
        self.root.wait_window(popup)
        
        if temp_png and os.path.exists(temp_png):
            try:
                os.remove(temp_png)
            except OSError:
                pass
        
        if not confirmed:
            return
        
        success, message = self._replace_sav(main_sav, thumb_sav, new_png_path)
        
        if success:
            showinfo_relative(self.root, self.t("success"), self.t("replace_success").format(id=id_str))
            self.load_screenshots_callback()
            self.show_status_indicator_callback(id_str, is_new=False)
        else:
            showerror_relative(self.root, self.t("error"), message)
    
    def _replace_sav(self, main_sav, thumb_sav, new_png):
        """替换sav文件"""
        try:
            success, message = self.screenshot_manager.replace_screenshot(
                os.path.basename(main_sav).replace('DevilConnection_photo_', '').replace('.sav', ''),
                new_png
            )
            return success, message
        except Exception as e:
            return False, str(e)
    
    def show_export_dialog(self, id_str):
        """显示导出图片对话框
        
        Args:
            id_str: 截图ID
        """
        image_data = self.screenshot_manager.get_image_data(id_str)
        if not image_data:
            messagebox.showerror(self.t("error"), self.t("file_not_found"))
            return
        
        format_dialog = Toplevel(self.root)
        format_dialog.title(self.t("select_export_format"))
        format_dialog.geometry("300x200")
        format_dialog.configure(bg=self.Colors.WHITE)
        self.set_window_icon(format_dialog)
        format_dialog.transient(self.root)
        format_dialog.grab_set()
        
        format_var = tk.StringVar(value="png")
        
        format_label = tk.Label(format_dialog, text=self.t("select_image_format"),
                               font=self.get_cjk_font(10),
                               fg=self.Colors.TEXT_PRIMARY,
                               bg=self.Colors.WHITE)
        format_label.pack(pady=10)
        
        format_frame = ttk.Frame(format_dialog, style="White.TFrame")
        format_frame.pack(pady=10)
        ttk.Radiobutton(format_frame, text="PNG", variable=format_var, value="png").pack(side='left', padx=10)
        ttk.Radiobutton(format_frame, text="JPEG", variable=format_var, value="jpeg").pack(side='left', padx=10)
        ttk.Radiobutton(format_frame, text="WebP", variable=format_var, value="webp").pack(side='left', padx=10)
        
        def confirm_export():
            format_choice = format_var.get()
            format_dialog.destroy()
            
            if format_choice == "png":
                filetypes = [("PNG files", "*.png"), ("All files", "*.*")]
                defaultextension = ".png"
                default_filename = f"{id_str}.png"
            elif format_choice == "jpeg":
                filetypes = [("JPEG files", "*.jpg"), ("All files", "*.*")]
                defaultextension = ".jpg"
                default_filename = f"{id_str}.jpg"
            else:
                filetypes = [("WebP files", "*.webp"), ("All files", "*.*")]
                defaultextension = ".webp"
                default_filename = f"{id_str}.webp"
            
            save_path = filedialog.asksaveasfilename(
                title=self.t("save_image"),
                defaultextension=defaultextension,
                filetypes=filetypes,
                initialfile=default_filename
            )
            
            if not save_path:
                return
            
            try:
                temp_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
                with open(temp_png, 'wb') as f:
                    f.write(image_data)
                
                img = Image.open(temp_png)
                try:
                    if format_choice == "png":
                        img.save(save_path, "PNG")
                    elif format_choice == "jpeg":
                        if img.mode != "RGB":
                            img = img.convert("RGB")
                        img.save(save_path, "JPEG", quality=95)
                    else:
                        img.save(save_path, "WebP", quality=95)
                    showinfo_relative(self.root, self.t("success"), self.t("export_success").format(path=save_path))
                finally:
                    img.close()
                    if os.path.exists(temp_png):
                        try:
                            os.remove(temp_png)
                        except OSError:
                            pass
            except Exception as e:
                showerror_relative(self.root, self.t("error"), self.t("export_failed") + f": {str(e)}")
        
        button_frame = ttk.Frame(format_dialog)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text=self.t("confirm"), command=confirm_export).pack(side='left', padx=5)
        ttk.Button(button_frame, text=self.t("delete_cancel"), command=format_dialog.destroy).pack(side='left', padx=5)
    
    def show_batch_export_dialog(self, selected_ids):
        """显示批量导出对话框
        
        Args:
            selected_ids: 选中的截图ID列表
        """
        format_dialog = Toplevel(self.root)
        format_dialog.title(self.t("select_export_format"))
        format_dialog.geometry("300x200")
        format_dialog.configure(bg=self.Colors.WHITE)
        self.set_window_icon(format_dialog)
        format_dialog.transient(self.root)
        format_dialog.grab_set()
        
        format_var = tk.StringVar(value="png")
        
        format_label = tk.Label(format_dialog, text=self.t("select_image_format"),
                               font=self.get_cjk_font(10),
                               fg=self.Colors.TEXT_PRIMARY,
                               bg=self.Colors.WHITE)
        format_label.pack(pady=10)
        
        format_frame = ttk.Frame(format_dialog, style="White.TFrame")
        format_frame.pack(pady=10)
        ttk.Radiobutton(format_frame, text="PNG", variable=format_var, value="png").pack(side='left', padx=10)
        ttk.Radiobutton(format_frame, text="JPEG", variable=format_var, value="jpeg").pack(side='left', padx=10)
        ttk.Radiobutton(format_frame, text="WebP", variable=format_var, value="webp").pack(side='left', padx=10)
        
        def confirm_batch_export():
            format_choice = format_var.get()
            format_dialog.destroy()
            
            save_path = filedialog.asksaveasfilename(
                title=self.t("save_zip"),
                defaultextension=".zip",
                filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
                initialfile="DevilConnectionSSPack.zip"
            )
            
            if not save_path:
                return
            
            progress_window = Toplevel(self.root)
            progress_window.title(self.t("batch_export_progress"))
            progress_window.geometry("450x200")
            progress_window.configure(bg=self.Colors.WHITE)
            self.set_window_icon(progress_window)
            progress_window.transient(self.root)
            progress_window.grab_set()
            
            progress_window.protocol("WM_DELETE_WINDOW", lambda: None)
            
            progress_label = tk.Label(progress_window, text=self.t("exporting_images"), 
                                     font=self.get_cjk_font(10), 
                                     fg=self.Colors.TEXT_PRIMARY, bg=self.Colors.WHITE)
            progress_label.pack(pady=10)
            
            progress_bar = ttk.Progressbar(progress_window, length=350, mode='determinate')
            progress_bar.pack(pady=10, padx=20, fill="x")
            progress_bar['maximum'] = len(selected_ids)
            progress_bar['value'] = 0
            
            status_label = tk.Label(progress_window, text="0/{}".format(len(selected_ids)), 
                                   font=self.get_cjk_font(9), 
                                   fg=self.Colors.TEXT_PRIMARY, bg=self.Colors.WHITE)
            status_label.pack(pady=5)
            
            success_label = tk.Label(progress_window, text="", font=self.get_cjk_font(10), 
                                    bg=self.Colors.WHITE, fg="green")
            
            close_button = ttk.Button(progress_window, text=self.t("close"), 
                                     command=progress_window.destroy)
            
            def update_progress(current, total, exported, failed):
                """更新进度条"""
                progress_bar['value'] = current
                status_label.config(text=f"{current}/{total}")
                progress_window.update_idletasks()
            
            def show_success(exported_count, failed_count):
                """显示成功信息"""
                progress_bar.pack_forget()
                status_label.pack_forget()
                progress_label.config(text="")
                
                success_msg = self.t("batch_export_success", count=exported_count) if "batch_export_success" in self.translations.get(self.current_language, {}) else f"成功导出 {exported_count} 张图片到ZIP文件！"
                if failed_count > 0:
                    failed_msg = self.t("batch_export_failed", count=failed_count) if "batch_export_failed" in self.translations.get(self.current_language, {}) else f"失败: {failed_count} 张"
                    success_msg += "\n" + failed_msg
                
                success_label.config(text=success_msg)
                success_label.pack(pady=20)
                close_button.pack(pady=10)
                
                progress_window.protocol("WM_DELETE_WINDOW", progress_window.destroy)
            
            def show_error(error_msg):
                """显示错误信息"""
                progress_bar.pack_forget()
                status_label.pack_forget()
                progress_label.config(text="", fg="red")
                progress_label.config(text=error_msg, fg="red")
                close_button.pack(pady=10)
                progress_window.protocol("WM_DELETE_WINDOW", progress_window.destroy)
            
            def export_in_thread():
                """在后台线程中执行导出"""
                try:
                    exported_count = 0
                    failed_count = 0
                    current = 0
                    
                    with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for idx, id_str in enumerate(selected_ids):
                            image_data = self.screenshot_manager.get_image_data(id_str)
                            if image_data:
                                try:
                                    temp_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
                                    with open(temp_png, 'wb') as f:
                                        f.write(image_data)
                                    
                                    img = Image.open(temp_png)
                                    try:
                                        output = BytesIO()
                                        if format_choice == "png":
                                            img.save(output, "PNG")
                                            ext = ".png"
                                        elif format_choice == "jpeg":
                                            if img.mode != "RGB":
                                                img = img.convert("RGB")
                                            img.save(output, "JPEG", quality=95)
                                            ext = ".jpg"
                                        else:
                                            img.save(output, "WebP", quality=95)
                                            ext = ".webp"
                                        
                                        zipf.writestr(f"{id_str}{ext}", output.getvalue())
                                        exported_count += 1
                                    finally:
                                        img.close()
                                        if os.path.exists(temp_png):
                                            try:
                                                os.remove(temp_png)
                                            except OSError:
                                                pass
                                except Exception as e:
                                    failed_count += 1
                            else:
                                failed_count += 1
                            
                            current = idx + 1
                            progress_window.after(0, update_progress, current, len(selected_ids), exported_count, failed_count)
                    
                    if exported_count > 0:
                        progress_window.after(0, show_success, exported_count, failed_count)
                    else:
                        error_msg = self.t("batch_export_error_all") if "batch_export_error_all" in self.translations.get(self.current_language, {}) else "没有成功导出任何图片！"
                        progress_window.after(0, show_error, error_msg)
                except Exception as e:
                    error_msg = self.t("export_failed") + f": {str(e)}"
                    progress_window.after(0, show_error, error_msg)
            
            thread = threading.Thread(target=export_in_thread, daemon=True)
            thread.start()
        
        button_frame = ttk.Frame(format_dialog)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text=self.t("confirm"), command=confirm_batch_export).pack(side='left', padx=5)
        ttk.Button(button_frame, text=self.t("delete_cancel"), command=format_dialog.destroy).pack(side='left', padx=5)

