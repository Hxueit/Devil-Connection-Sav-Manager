import tkinter as tk
from tkinter import ttk, Scrollbar
import json
import urllib.parse
import os
from translations import TRANSLATIONS
from utils import set_window_icon


class SaveAnalyzer:
    def __init__(self, parent, storage_dir, translations, current_language):
        self.parent = parent
        self.storage_dir = storage_dir
        self.translations = translations
        self.current_language = current_language
        
        # 创建窗口
        self.window = tk.Toplevel(parent)
        self.window.title(self.t("save_analyzer_title"))
        self.window.geometry("800x600")
        
        # 设置窗口图标
        set_window_icon(self.window)
        
        # 创建滚动区域
        canvas = tk.Canvas(self.window, bg="white")
        scrollbar = Scrollbar(self.window, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="white")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 加载并解析存档
        save_data = self.load_save_file()
        if save_data:
            self.display_save_info(scrollable_frame, save_data)
        else:
            error_label = ttk.Label(scrollable_frame, text=self.t("save_file_not_found"), 
                                   font=("Arial", 12), foreground="red")
            error_label.pack(pady=20)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 绑定鼠标滚轮
        def on_mousewheel(event):
            try:
                if event.delta:
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                else:
                    if event.num == 4:
                        canvas.yview_scroll(-1, "units")
                    elif event.num == 5:
                        canvas.yview_scroll(1, "units")
            except:
                pass
        
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        canvas.bind_all("<Button-4>", on_mousewheel)
        canvas.bind_all("<Button-5>", on_mousewheel)
        
        def on_window_close():
            try:
                canvas.unbind_all("<MouseWheel>")
                canvas.unbind_all("<Button-4>")
                canvas.unbind_all("<Button-5>")
            except:
                pass
            self.window.destroy()
        
        self.window.protocol("WM_DELETE_WINDOW", on_window_close)
    
    def t(self, key, **kwargs):
        """翻译函数"""
        text = self.translations[self.current_language].get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text
    
    def load_save_file(self):
        """加载并解码存档文件"""
        sf_path = os.path.join(self.storage_dir, 'DevilConnection_sf.sav')
        if not os.path.exists(sf_path):
            return None
        
        try:
            with open(sf_path, 'r', encoding='utf-8') as f:
                encoded = f.read().strip()
            unquoted = urllib.parse.unquote(encoded)
            return json.loads(unquoted)
        except Exception as e:
            return None
    
    def create_section(self, parent, title):
        """创建带标题的分区"""
        section_frame = tk.Frame(parent, bg="white", relief="ridge", borderwidth=2)
        section_frame.pack(fill="x", padx=10, pady=5)
        
        title_label = ttk.Label(section_frame, text=title, font=("Arial", 12, "bold"))
        title_label.pack(anchor="w", padx=5, pady=5)
        
        content_frame = tk.Frame(section_frame, bg="white")
        content_frame.pack(fill="x", padx=10, pady=5)
        
        return content_frame
    
    def add_info_line(self, parent, label, value):
        """添加信息行"""
        line_frame = tk.Frame(parent, bg="white")
        line_frame.pack(fill="x", padx=5, pady=2)
        
        label_widget = ttk.Label(line_frame, text=label + ":", font=("Arial", 10))
        label_widget.pack(side="left", padx=5)
        
        value_widget = ttk.Label(line_frame, text=str(value), font=("Arial", 10))
        value_widget.pack(side="left", padx=5)
    
    def add_list_info(self, parent, label, items):
        """添加列表信息，显示完整列表"""
        line_frame = tk.Frame(parent, bg="white")
        line_frame.pack(fill="x", padx=5, pady=2)
        
        label_widget = ttk.Label(line_frame, text=label + ":", font=("Arial", 10))
        label_widget.pack(side="left", padx=5)
        
        if len(items) == 0:
            value_widget = ttk.Label(line_frame, text=self.t("none"), font=("Arial", 10), 
                                     foreground="gray")
            value_widget.pack(side="left", padx=5)
        else:
            value_text = ", ".join(str(item) for item in items)
            value_widget = ttk.Label(line_frame, text=value_text, font=("Arial", 10))
            value_widget.pack(side="left", padx=5)
    
    def display_save_info(self, parent, save_data):
        """显示存档信息"""
        # 基本信息
        basic_section = self.create_section(parent, self.t("basic_info"))
        
        # 上次存档名字
        memory = save_data.get("memory", {})
        save_name = memory.get("name", self.t("not_set"))
        self.add_info_line(basic_section, self.t("last_save_name"), save_name)
        
        # 存档列表编号和相册页码
        save_list_no = save_data.get("saveListNo", 0)
        album_page_no = save_data.get("albumPageNo", 0)
        self.add_info_line(basic_section, self.t("save_list_no"), save_list_no)
        self.add_info_line(basic_section, self.t("album_page_no"), album_page_no)
        
        # 结局统计
        endings_section = self.create_section(parent, self.t("endings_statistics"))
        
        endings = set(save_data.get("endings", []))
        collected_endings = set(save_data.get("collectedEndings", []))
        endings_count = len(endings)
        collected_endings_count = len(collected_endings)
        missing_endings = sorted(endings - collected_endings, key=lambda x: int(x) if x.isdigit() else 999)
        
        self.add_info_line(endings_section, self.t("total_endings"), endings_count)
        self.add_info_line(endings_section, self.t("collected_endings"), collected_endings_count)
        if missing_endings:
            self.add_info_line(endings_section, self.t("missing_endings"), 
                             f"{len(missing_endings)}: {', '.join(missing_endings)}")
        else:
            self.add_info_line(endings_section, self.t("missing_endings"), self.t("none"))
        
        # 小剧场统计
        omakes_section = self.create_section(parent, self.t("omakes_statistics"))
        
        omakes = set(save_data.get("omakes", []))
        omakes_count = len(omakes)
        collected_omakes = omakes & collected_endings  # 已收集的小剧场
        collected_omakes_count = len(collected_omakes)
        missing_omakes = sorted(omakes - collected_endings, key=lambda x: int(x) if x.isdigit() else 999)
        
        self.add_info_line(omakes_section, self.t("total_omakes"), omakes_count)
        self.add_info_line(omakes_section, self.t("collected_omakes"), collected_omakes_count)
        if missing_omakes:
            self.add_info_line(omakes_section, self.t("missing_omakes"), 
                             f"{len(missing_omakes)}: {', '.join(missing_omakes)}")
        else:
            self.add_info_line(omakes_section, self.t("missing_omakes"), self.t("none"))
        
        # 角色统计
        characters_section = self.create_section(parent, self.t("characters_statistics"))
        
        characters = set(save_data.get("characters", []))
        collected_characters = set(save_data.get("collectedCharacters", []))
        characters_count = len(characters)
        collected_characters_count = len(collected_characters)
        missing_characters = sorted(characters - collected_characters)
        
        self.add_info_line(characters_section, self.t("total_characters"), characters_count)
        self.add_info_line(characters_section, self.t("collected_characters"), collected_characters_count)
        if missing_characters:
            self.add_list_info(characters_section, self.t("missing_characters"), missing_characters)
        else:
            self.add_info_line(characters_section, self.t("missing_characters"), self.t("none"))
        
        # 贴纸统计
        stickers_section = self.create_section(parent, self.t("stickers_statistics"))
        
        stickers = set(save_data.get("sticker", []))
        # 总共132个贴纸，编号1-133，没有82
        all_sticker_ids = set(range(1, 82)) | set(range(83, 134))  # 1-81, 83-133
        stickers_count = len(stickers)
        total_stickers = 132
        missing_stickers = sorted(all_sticker_ids - stickers)
        
        self.add_info_line(stickers_section, self.t("total_stickers"), total_stickers)
        self.add_info_line(stickers_section, self.t("collected_stickers"), stickers_count)
        self.add_info_line(stickers_section, self.t("missing_stickers_count"), len(missing_stickers))
        if missing_stickers:
            self.add_info_line(stickers_section, self.t("missing_stickers"), 
                             ", ".join(str(s) for s in missing_stickers))
        else:
            self.add_info_line(stickers_section, self.t("missing_stickers"), self.t("none"))
        
        # 游戏统计
        stats_section = self.create_section(parent, self.t("game_statistics"))
        
        whole_total_mp = save_data.get("wholeTotalMP", 0)
        self.add_info_line(stats_section, self.t("total_mp"), whole_total_mp)
        
        judge_counts = save_data.get("judgeCounts", {})
        perfect = judge_counts.get("perfect", 0)
        good = judge_counts.get("good", 0)
        bad = judge_counts.get("bad", 0)
        self.add_info_line(stats_section, self.t("judge_perfect"), perfect)
        self.add_info_line(stats_section, self.t("judge_good"), good)
        self.add_info_line(stats_section, self.t("judge_bad"), bad)
        
        neo = save_data.get("NEO", 0)
        kill = save_data.get("kill", 0)
        epilogue = save_data.get("epilogue", 0)
        self.add_info_line(stats_section, self.t("neo_value"), neo)
        self.add_info_line(stats_section, self.t("kill_count"), kill)
        self.add_info_line(stats_section, self.t("epilogue_count"), epilogue)
        
        loop_count = save_data.get("loopCount", 0)
        total_loop_count = save_data.get("totalLoopCount", 0)
        self.add_info_line(stats_section, self.t("loop_count"), loop_count)
        self.add_info_line(stats_section, self.t("total_loop_count"), total_loop_count)
        
        # 其他信息
        other_section = self.create_section(parent, self.t("other_info"))
        
        gallery = save_data.get("gallery", [])
        gallery_count = len(gallery)
        self.add_info_line(other_section, self.t("gallery_count"), gallery_count)
        if gallery:
            self.add_list_info(other_section, self.t("gallery_items"), gallery)
        
        ng_scene = save_data.get("ngScene", [])
        ng_scene_count = len(ng_scene)
        self.add_info_line(other_section, self.t("ng_scene_count"), ng_scene_count)
        if ng_scene:
            self.add_list_info(other_section, self.t("ng_scene_items"), ng_scene)
        
        true_count = save_data.get("trueCount", 0)
        self.add_info_line(other_section, self.t("true_count"), true_count)
        
        autosave = save_data.get("system", {}).get("autosave", False)
        self.add_info_line(other_section, self.t("autosave_enabled"), 
                          self.t("yes") if autosave else self.t("no"))

