# translations.py
# Translation dictionary for DevilConnection Screenshot Tool

TRANSLATIONS = {
    "zh_CN": {
        # Window title
        "window_title": "恶魔连结截图管理工具",
        
        # Directory selection
        "select_storage_dir": "选择_storage/目录:",
        "not_selected": "未选择",
        "browse_dir": "浏览目录",
        "dir_error": "目录必须以/_storage结尾！",
        
        # Screenshot list
        "screenshot_list": "截图列表:",
        "preview": "预览",
        "refresh": "⟳",
        "sort_asc": "正序",
        "sort_desc": "倒序",
        "list_header": "ID - 文件名 - 时间",
        
        # Buttons
        "add_new": "+ 新增截图",
        "replace_selected": "⇋ 替换选中截图",
        "delete_selected": "✖ 删除选中截图",
        "export_image": "导出图片",
        "batch_export": "批量导出图片",
        
        # Error messages
        "error": "错误",
        "success": "成功",
        "warning": "警告",
        "missing_files": "缺少ids.sav或all_ids.sav！",
        "select_dir_first": "请先选择目录！",
        "select_screenshot": "请选择一个截图！",
        "invalid_selection": "无效的选择！",
        "file_missing": "文件缺失，无法替换！",
        "file_not_found": "无法找到截图文件！",
        "file_not_exist": "文件不存在！",
        "file_missing_text": "文件缺失",
        "file_not_exist_text": "文件不存在",
        "missing_main_file": "缺失主文件",
        "preview_failed": "预览失败",
        "export_failed": "导出失败",
        "save_failed": "保存失败: {error}",
        
        # Sort related
        "confirm_sort": "确认排序",
        "sort_warning": "注意:改变该排序也会改变截图在游戏画廊中的显示顺序，是否确定？",
        "sort_asc_success": "已按正序排序并保存！",
        "sort_desc_success": "已按倒序排序并保存！",
        
        # Replace related
        "replace_warning": "警告：确认替换",
        "replace_confirm_text": "你即将进行以下替换操作：",
        "replace_confirm_question": "是否确认替换（是/否）？",
        "replace_yes": "是(Y)",
        "replace_no": "否(N)",
        "yes_button": "是(Y)",
        "no_button": "否(N)",
        "replace_success": "替换 {id} 完成！",
        "select_new_image": "选择新图片文件",
        
        # Add new related
        "add_new_title": "新增截图设置",
        "id_label": "ID (留空随机生成):",
        "date_label": "时间 (格式: YYYY/MM/DD HH:MM:SS, 留空当前时间):",
        "confirm": "确认",
        "invalid_date_format": "时间格式无效！使用 YYYY/MM/DD HH:MM:SS",
        "id_exists": "ID 已存在！",
        "add_success": "新增 {id} 完成！",
        "select_new_png": "选择新PNG",
        "file_extension_warning": "你选择的是{filename}，请确认该文件是图片文件，若非图片文件将无法增添至游戏内",
        
        # Delete related
        "delete_confirm": "确认删除",
        "delete_select_error": "请选择要删除的截图！\n\n注意: 请在左侧复选框中选择要删除的截图",
        "delete_confirm_single": "你确定要删除 {id} 的截图（包括索引）吗？",
        "delete_confirm_multiple": "你确定要删除 {count} 个截图（包括索引）吗？\n选中的ID: {ids}",
        "delete_ok": "确定",
        "delete_cancel": "取消",
        "delete_success": "已删除 {count} 个截图！",
        "delete_warning": "没有成功删除任何文件！",
        
        # Export related
        "select_export_format": "选择导出格式",
        "select_image_format": "选择图片格式:",
        "save_image": "保存图片",
        "save_zip": "保存ZIP文件",
        "export_success": "图片已保存到:\n{path}",
        "batch_export_error": "请选择要导出的截图！",
        "batch_export_success": "成功导出 {count} 张图片到ZIP文件！",
        "batch_export_failed": "失败: {count} 张",
        "batch_export_error_all": "没有成功导出任何图片！",
        "batch_export_fail": "批量导出失败: {error}",
        
        # Language switch
        "language": "语言",
        "chinese": "中文",
        "english": "English",
        
        # Directory menu
        "directory_menu": "目录选择",
        "select_dir_hint": "请在左上角目录选择选择游戏的_storage路径",
    },
    
    "en_US": {
        # Window title
        "window_title": "Devil Connection Screenshot Tool",
        
        # Directory selection
        "select_storage_dir": "Select _storage/ directory:",
        "not_selected": "Not selected",
        "browse_dir": "Browse Directory",
        "dir_error": "Directory must end with /_storage!",
        
        # Screenshot list
        "screenshot_list": "Screenshot List:",
        "preview": "Preview",
        "refresh": "⟳",
        "sort_asc": "↑↑Asc.",
        "sort_desc": "↓↓Desc.",
        "list_header": "ID - Filename - Time",
        
        # Buttons
        "add_new": "+ Add Screenshot",
        "replace_selected": "⇋ Replace Selected",
        "delete_selected": "✖ Delete Selected",
        "export_image": "Export Image",
        "batch_export": "Batch Export",
        
        # Error messages
        "error": "Error",
        "success": "Success",
        "warning": "Warning",
        "missing_files": "Missing ids.sav or all_ids.sav!",
        "select_dir_first": "Please select directory first!",
        "select_screenshot": "Please select a screenshot!",
        "invalid_selection": "Invalid selection!",
        "file_missing": "Files missing, cannot replace!",
        "file_not_found": "Cannot find screenshot file!",
        "file_not_exist": "File does not exist!",
        "file_missing_text": "File missing",
        "file_not_exist_text": "File does not exist",
        "missing_main_file": "Missing main file",
        "preview_failed": "Preview failed",
        "export_failed": "Export failed",
        "save_failed": "Save failed: {error}",
        
        # Sort related
        "confirm_sort": "Confirm Sort",
        "sort_warning": "Note: Changing this order will also change the display order in the game gallery. Are you sure?",
        "sort_asc_success": "Sorted in ascending order and saved!",
        "sort_desc_success": "Sorted in descending order and saved!",
        
        # Replace related
        "replace_warning": "Warning: Confirm Replace",
        "replace_confirm_text": "You are about to perform the following replacement:",
        "replace_confirm_question": "Confirm replacement (Yes/No)?",
        "replace_yes": "Yes",
        "replace_no": "No",
        "yes_button": "Yes",
        "no_button": "No",
        "replace_success": "Replacement of {id} completed!",
        "select_new_image": "Select New Image File",
        
        # Add new related
        "add_new_title": "Add Screenshot Settings",
        "id_label": "ID (leave empty for random):",
        "date_label": "Time (format: YYYY/MM/DD HH:MM:SS, leave empty for current time):",
        "confirm": "Confirm",
        "invalid_date_format": "Invalid time format! Use YYYY/MM/DD HH:MM:SS",
        "id_exists": "ID already exists!",
        "add_success": "Added {id} completed!",
        "select_new_png": "Select New PNG",
        "file_extension_warning": "You selected {filename}, please confirm this file is an image file. If it's not an image file, it cannot be added to the game",
        
        # Delete related
        "delete_confirm": "Confirm Delete",
        "delete_select_error": "Please select screenshots to delete.\n\nNote: Please use the checkboxes on the left to select screenshots to delete",
        "delete_confirm_single": "Are you sure you want to delete the screenshot {id} (including index)?",
        "delete_confirm_multiple": "Are you sure you want to delete {count} screenshots (including index)?\nSelected IDs: {ids}",
        "delete_ok": "OK",
        "delete_cancel": "Cancel",
        "delete_success": "Deleted {count} screenshots!",
        "delete_warning": "No files were successfully deleted!",
        
        # Export related
        "select_export_format": "Select Export Format",
        "select_image_format": "Select image format:",
        "save_image": "Save Image",
        "save_zip": "Save ZIP File",
        "export_success": "Image saved to:\n{path}",
        "batch_export_error": "Please select screenshots to export!",
        "batch_export_success": "Successfully exported {count} images to ZIP file!",
        "batch_export_failed": "Failed: {count} images",
        "batch_export_error_all": "No images were successfully exported!",
        "batch_export_fail": "Batch export failed: {error}",
        
        # Language switch
        "language": "Language",
        "chinese": "中文",
        "english": "English",
        
        # Directory menu
        "directory_menu": "Directory",
        "select_dir_hint": "Please select the game's _storage path from Directory menu in the top left corner",
    }
}

