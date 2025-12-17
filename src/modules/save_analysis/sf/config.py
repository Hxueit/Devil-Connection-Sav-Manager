"""字段配置模块

定义存档分析器中所有section的字段配置，包括字段路径、格式化函数、UI显示选项等。
这些配置用于动态生成UI组件和格式化数据。
"""

from typing import Dict, Any, Optional, Callable
from src.utils.styles import Colors


def get_field_configs():
    """返回所有section的字段配置字典
    
    Returns:
        包含所有section配置的字典。每个section包含：
        - section_type: section类型（"section" 或 "section_with_button"）
        - title_key: 标题的翻译键
        - fields: 字段列表，每个字段包含：
            - widget_key: widget标识键
            - data_path: 数据路径（支持点号分隔的嵌套路径）
            - label_key: 标签的翻译键
            - var_name: 变量名（可选）
            - formatter: 格式化函数
            - has_tooltip: 是否有提示信息
            - tooltip_key: 提示信息的翻译键
            - is_computed: 是否为计算字段
            - is_dynamic: 是否为动态字段
            - is_list: 是否为列表字段
            - text_color: 文字颜色（可选）
    """
    return {
        "fanatic_related": {
            "section_type": "section",
            "title_key": "fanatic_related",
            "bg_color": Colors.WHITE,
            "text_color": None,  # 条件：is_fanatic_route 时动态设置为深红色
            "fields": [
                {
                    "widget_key": "NEO",
                    "data_path": "NEO",
                    "label_key": "neo_value",
                    "var_name": "NEO",
                    "formatter": lambda v: v if v is not None else 0,
                    "has_tooltip": True,
                    "tooltip_key": "neo_value_tooltip",
                    "text_color": None
                },
                {
                    "widget_key": "Lamia_noroi",
                    "data_path": "Lamia_noroi",
                    "label_key": "lamia_curse",
                    "var_name": "Lamia_noroi",
                    "formatter": lambda v: v if v is not None else 0,
                    "text_color": None
                },
                {
                    "widget_key": "trauma",
                    "data_path": "trauma",
                    "label_key": "trauma_value",
                    "var_name": "trauma",
                    "formatter": lambda v: v if v is not None else 0,
                    "text_color": None
                },
                {
                    "widget_key": "killWarning",
                    "data_path": "killWarning",
                    "label_key": "kill_warning",
                    "var_name": "killWarning",
                    "formatter": lambda v: v if v is not None else 0,
                    "text_color": None
                },
                {
                    "widget_key": "killed",
                    "data_path": "killed",
                    "label_key": "killed",
                    "var_name": "killed",
                    "formatter": lambda v, t=None: t("variable_not_exist") if v is None and t else (v if v is not None else "variable_not_exist"),
                    "has_tooltip": True,
                    "tooltip_key": "killed_tooltip",
                    "text_color": None
                },
                {
                    "widget_key": "kill",
                    "data_path": "kill",
                    "label_key": "kill_count",
                    "var_name": "kill",
                    "formatter": lambda v: v if v is not None else 0,
                    "has_tooltip": True,
                    "tooltip_key": "kill_count_tooltip",
                    "text_color": None
                }
            ]
        },
        "endings_statistics": {
            "section_type": "section_with_button",
            "title_key": "endings_statistics",
            "button_text_key": "view_requirements",
            "button_command_factory": None,  # 将在运行时设置
            "fields": [
                {
                    "widget_key": "endings.count",
                    "data_path": "endings",
                    "label_key": "total_endings",
                    "var_name": "endings",
                    "formatter": lambda v, cd: len(cd["endings"]),
                    "is_computed": True
                },
                {
                    "widget_key": "collectedEndings.count",
                    "data_path": "collectedEndings",
                    "label_key": "collected_endings",
                    "var_name": "collectedEndings",
                    "formatter": lambda v, cd: len(cd["collected_endings"]),
                    "is_computed": True
                },
                {
                    "widget_key": "missing_endings",
                    "data_path": None,
                    "label_key": "missing_endings",
                    "var_name": None,
                    "formatter": lambda sd, cd, t=None: f"{len(cd['missing_endings'])}: {', '.join(cd['missing_endings'])}" if cd['missing_endings'] else (t("none") if t else "none"),
                    "is_computed": True,
                    "is_dynamic": True
                }
            ]
        },
        "stickers_statistics": {
            "section_type": "section_with_button",
            "title_key": "stickers_statistics",
            "button_text_key": "view_requirements",
            "button_command_factory": None,  # 将在运行时设置
            "fields": [
                {
                    "widget_key": "stickers.total",
                    "data_path": None,
                    "label_key": "total_stickers",
                    "var_name": None,
                    "formatter": lambda v, cd: 132,
                    "is_computed": True
                },
                {
                    "widget_key": "sticker.count",
                    "data_path": "sticker",
                    "label_key": "collected_stickers",
                    "var_name": "sticker",
                    "formatter": lambda v, cd: len(cd["stickers"]),
                    "is_computed": True
                },
                {
                    "widget_key": "missing_stickers.count",
                    "data_path": None,
                    "label_key": "missing_stickers_count",
                    "var_name": None,
                    "formatter": lambda v, cd: len(cd["missing_stickers"]),
                    "is_computed": True
                },
                {
                    "widget_key": "missing_stickers",
                    "data_path": None,
                    "label_key": "missing_stickers",
                    "var_name": None,
                    "formatter": lambda sd, cd, t=None: ", ".join(str(s) for s in cd["missing_stickers"]) if cd["missing_stickers"] else (t("none") if t else "none"),
                    "is_computed": True,
                    "is_dynamic": True
                }
            ]
        },
        "characters_statistics": {
            "section_type": "section",
            "title_key": "characters_statistics",
            "fields": [
                {
                    "widget_key": "characters.count",
                    "data_path": "characters",
                    "label_key": "total_characters",
                    "var_name": "characters",
                    "formatter": lambda v, cd: max(0, len(cd["characters"])),
                    "is_computed": True
                },
                {
                    "widget_key": "collectedCharacters.count",
                    "data_path": "collectedCharacters",
                    "label_key": "collected_characters",
                    "var_name": "collectedCharacters",
                    "formatter": lambda v, cd: max(0, len(cd["collected_characters"])),
                    "is_computed": True
                },
                {
                    "widget_key": "missing_characters",
                    "data_path": None,
                    "label_key": "missing_characters",
                    "var_name": None,
                    "formatter": lambda v, cd: cd["missing_characters"],
                    "is_computed": True,
                    "is_list": True,
                    "is_dynamic": True
                }
            ]
        },
        "omakes_statistics": {
            "section_type": "section_with_button",
            "title_key": "omakes_statistics",
            "button_text_key": "ng_scene_quick_check",
            "button_command_factory": None,  # 将在运行时设置
            "fields": [
                {
                    "widget_key": "omakes.count",
                    "data_path": "omakes",
                    "label_key": "total_omakes",
                    "var_name": None,
                    "formatter": lambda v, cd: len(cd["total_omakes_set"]),
                    "is_computed": True
                },
                {
                    "widget_key": "collected_omakes.count",
                    "data_path": "omakes",
                    "label_key": "collected_omakes",
                    "var_name": "omakes",
                    "formatter": lambda v, cd: len(cd["collected_omakes"]),
                    "is_computed": True
                },
                {
                    "widget_key": "missing_omakes",
                    "data_path": None,
                    "label_key": "missing_omakes",
                    "var_name": None,
                    "formatter": lambda sd, cd, t=None: ', '.join(cd["missing_omakes"]) if cd["missing_omakes"] else (t("none") if t else "none"),
                    "is_computed": True,
                    "is_dynamic": True
                },
                {
                    "widget_key": "gallery.count",
                    "data_path": "gallery",
                    "label_key": "gallery_count",
                    "var_name": "gallery",
                    "formatter": lambda sd, cd: f"{len(sd.get('gallery', []))}/{len(cd['total_gallery_set'])}",
                    "is_computed": True
                },
                {
                    "widget_key": "ngScene.count",
                    "data_path": "ngScene",
                    "label_key": "ng_scene_count",
                    "var_name": "ngScene",
                    "formatter": lambda sd, cd: f"{len(sd.get('ngScene', []))}/{len(cd['total_ng_scene_set'])}",
                    "has_tooltip": True,
                    "tooltip_key": "ng_scene_count_tooltip",
                    "is_computed": True,
                    "tooltip_optional": True
                }
            ]
        },
        "game_statistics": {
            "section_type": "section",
            "title_key": "game_statistics",
            "fields": [
                {
                    "widget_key": "wholeTotalMP",
                    "data_path": "wholeTotalMP",
                    "label_key": "total_mp",
                    "var_name": "wholeTotalMP",
                    "formatter": lambda v: v if v is not None else 0
                },
                {
                    "widget_key": "judgeCounts.perfect",
                    "data_path": "judgeCounts.perfect",
                    "label_key": "judge_perfect",
                    "var_name": "judgeCounts.perfect",
                    "formatter": lambda v: v if v is not None else 0
                },
                {
                    "widget_key": "judgeCounts.good",
                    "data_path": "judgeCounts.good",
                    "label_key": "judge_good",
                    "var_name": "judgeCounts.good",
                    "formatter": lambda v: v if v is not None else 0
                },
                {
                    "widget_key": "judgeCounts.bad",
                    "data_path": "judgeCounts.bad",
                    "label_key": "judge_bad",
                    "var_name": "judgeCounts.bad",
                    "formatter": lambda v: v if v is not None else 0
                },
                {
                    "widget_key": "secretEndOpen",
                    "data_path": "secretEndOpen",
                    "label_key": "secret_end_open",
                    "var_name": "secretEndOpen",
                    "formatter": lambda v: v if v is not None else 0
                },
                {
                    "widget_key": "trueCount",
                    "data_path": "trueCount",
                    "label_key": "true_count",
                    "var_name": "trueCount",
                    "formatter": lambda v: v if v is not None else 0
                },
                {
                    "widget_key": "epilogue",
                    "data_path": "epilogue",
                    "label_key": "epilogue_count",
                    "var_name": "epilogue",
                    "formatter": lambda v: v if v is not None else 0
                },
                {
                    "widget_key": "loopCount",
                    "data_path": "loopCount",
                    "label_key": "loop_count",
                    "var_name": "loopCount",
                    "formatter": lambda v: v if v is not None else 0
                },
                {
                    "widget_key": "loopRecord",
                    "data_path": "loopRecord",
                    "label_key": "loop_record",
                    "var_name": "loopRecord",
                    "formatter": lambda v: v if v is not None else 0,
                    "has_tooltip": True,
                    "tooltip_key": "loop_record_tooltip"
                }
            ]
        },
        "character_info": {
            "section_type": "section",
            "title_key": "character_info",
            "fields": [
                {
                    "widget_key": "memory.name",
                    "data_path": "memory.name",
                    "label_key": "character_name",
                    "var_name": "memory.name",
                    "formatter": lambda v, t=None: v if v else (t("not_set") if t else "not_set")
                },
                {
                    "widget_key": "memory.seibetu",
                    "data_path": "memory.seibetu",
                    "label_key": "character_gender",
                    "var_name": "memory.seibetu",
                    "formatter": lambda v, t=None: (t("gender_male") if t else "male") if v == 1 else (t("gender_female") if t else "female") if v == 2 else (t("not_set") if t else "not_set")
                },
                {
                    "widget_key": "memory.hutanari",
                    "data_path": "memory.hutanari",
                    "label_key": "hutanari",
                    "var_name": "memory.hutanari",
                    "formatter": lambda v: v if v is not None else 0
                },
                {
                    "widget_key": "memory.cameraEnable",
                    "data_path": "memory.cameraEnable",
                    "label_key": "camera_enable",
                    "var_name": "memory.cameraEnable",
                    "formatter": lambda v: v if v is not None else 0
                },
                {
                    "widget_key": "memory.yubiwa",
                    "data_path": "memory.yubiwa",
                    "label_key": "yubiwa",
                    "var_name": "memory.yubiwa",
                    "formatter": lambda v: v if v is not None else 0
                }
            ]
        },
        "other_info": {
            "section_type": "section",
            "title_key": "other_info",
            "fields": [
                {
                    "widget_key": "saveListNo",
                    "data_path": "saveListNo",
                    "label_key": "save_list_no",
                    "var_name": "saveListNo",
                    "formatter": lambda v: v if v is not None else 0
                },
                {
                    "widget_key": "albumPageNo",
                    "data_path": "albumPageNo",
                    "label_key": "album_page_no",
                    "var_name": "albumPageNo",
                    "formatter": lambda v: (v if v is not None else 0) + 1  # 相册页码从0开始，显示时+1
                },
                {
                    "widget_key": "desu",
                    "data_path": "desu",
                    "label_key": "desu",
                    "var_name": "desu",
                    "formatter": lambda v: v if v is not None else 0
                },
                {
                    "widget_key": "system.autosave",
                    "data_path": "system.autosave",
                    "label_key": "autosave_enabled",
                    "var_name": "system.autosave",
                    "formatter": lambda v: v if v is not None else False
                },
                {
                    "widget_key": "fullscreen",
                    "data_path": "fullscreen",
                    "label_key": "fullscreen",
                    "var_name": "fullscreen",
                    "formatter": lambda v: v if v is not None else False
                }
            ],
            "has_hint": True,
            "hint_key": "other_info_hint"
        }
    }


def get_field_configs_with_callbacks(
    endings_callback: Optional[Callable] = None,
    stickers_callback: Optional[Callable] = None,
    ng_scene_callback: Optional[Callable] = None
) -> Dict[str, Any]:
    """返回所有section的字段配置字典，支持运行时绑定回调
    
    Args:
        endings_callback: 结局统计按钮的回调函数工厂
        stickers_callback: 贴纸统计按钮的回调函数工厂
        ng_scene_callback: NG场景统计按钮的回调函数工厂
    
    Returns:
        包含所有section配置的字典，已设置button_command_factory
    """
    configs = get_field_configs()
    
    if endings_callback and "endings_statistics" in configs:
        configs["endings_statistics"]["button_command_factory"] = endings_callback
    
    if stickers_callback and "stickers_statistics" in configs:
        configs["stickers_statistics"]["button_command_factory"] = stickers_callback
    
    if ng_scene_callback and "omakes_statistics" in configs:
        configs["omakes_statistics"]["button_command_factory"] = ng_scene_callback
    
    return configs

