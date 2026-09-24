"""sf 存档分析页的数据部分（不涉及界面）

- load_save_file: 读取 DevilConnection_sf.sav
- compute_shared_data: 计算各分区共用的统计数据（结局、贴纸、角色……）
- SECTIONS: 左侧各分区及其字段的定义
- field_value: 算出某个字段要显示的值
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.constants import SF_SAVE_FILENAME
from src.constants import (
    STICKER_ID_RANGES,
    TOTAL_CHARACTERS,
    TOTAL_ENDINGS,
    TOTAL_GALLERY,
    TOTAL_NG_SCENE,
    TOTAL_OMAKES,
    TOTAL_STICKERS,
)
from src.utils.sav_io import read_sav

logger = logging.getLogger(__name__)



def load_save_file(storage_dir: str) -> Dict[str, Any]:
    """读取 sf 存档

    Raises:
        FileNotFoundError: 文件不存在
        OSError: 无法读取
        ValueError: 内容损坏（不是合法的 URL 编码 JSON 对象）
    """
    data = read_sav(Path(storage_dir) / SF_SAVE_FILENAME)
    if not isinstance(data, dict):
        raise ValueError(f"{SF_SAVE_FILENAME} 的内容不是 JSON 对象")
    return data


def get_nested_value(data: Dict[str, Any], path: str) -> Any:
    """按 'memory.name' 这样的路径取值，路径不存在时返回 None"""
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def is_fanatic_route(save_data: Dict[str, Any]) -> bool:
    """kill 或 killed 为 1 表示当前处于狂信徒路线"""
    return save_data.get("kill") == 1 or save_data.get("killed") == 1


def _numeric_order(item: Any) -> int:
    text = str(item)
    return int(text) if text.isdigit() else 999


def compute_shared_data(save_data: Dict[str, Any]) -> Dict[str, Any]:
    """计算各分区共用的数据，避免每个字段各算一遍"""
    endings = set(save_data.get("endings", []))
    collected_endings = set(save_data.get("collectedEndings", []))

    stickers = set(save_data.get("sticker", []))
    all_sticker_ids = {i for start, end in STICKER_ID_RANGES for i in range(start, end)}

    # 游戏里偶尔会写入空字符串，忽略
    characters = {c for c in save_data.get("characters", []) if c and c.strip()}
    collected_characters = {c for c in save_data.get("collectedCharacters", []) if c and c.strip()}

    collected_omakes = set(save_data.get("omakes", []))
    total_omakes = set(TOTAL_OMAKES)

    return {
        "is_fanatic_route": is_fanatic_route(save_data),
        "endings": endings,
        "collected_endings": collected_endings,
        "missing_endings": sorted(endings - collected_endings, key=_numeric_order),
        "stickers": stickers,
        "missing_stickers": sorted(all_sticker_ids - stickers),
        "characters": characters,
        "collected_characters": collected_characters,
        "missing_characters": sorted(characters - collected_characters),
        "collected_omakes": collected_omakes,
        "total_omakes_set": total_omakes,
        "missing_omakes": sorted(total_omakes - collected_omakes, key=_numeric_order),
        "total_gallery_set": set(TOTAL_GALLERY),
        "total_ng_scene_set": set(TOTAL_NG_SCENE),
    }


# 计算函数的参数：(存档数据, compute_shared_data 的结果, 翻译函数)
ValueFunc = Callable[[Dict[str, Any], Dict[str, Any], Callable[[str], str]], Any]


@dataclass
class Field:
    """左侧分区中的一行「标签: 值」"""
    label_key: str                        # 标签的翻译键，同时作为这一行的唯一标识
    path: Optional[str] = None            # 直接读取的存档路径；不填 compute 时显示该值
    default: Any = 0                      # 存档里没有该变量时显示的值
    compute: Optional[ValueFunc] = None   # 需要计算的字段
    var_name: Optional[str] = None        # 勾选「显示变量名」时显示在标签前的 [变量名]
    tooltip_key: Optional[str] = None     # 有值时行尾显示可点击的 ℹ，点开显示该说明
    tooltip_optional: bool = False        # 说明翻译为空时不显示 ℹ


@dataclass
class Section:
    key: str                              # 同时是标题的翻译键
    fields: List[Field]
    button_text_key: Optional[str] = None  # 有值时标题右侧显示按钮（查看达成条件）
    hint_key: Optional[str] = None        # 分区底部的灰色提示


def _var(path: str, **kwargs: Any) -> Field:
    """直接显示存档变量的字段：变量名就是路径"""
    return Field(path=path, var_name=path, **kwargs)


def _join(items: List[Any], t: Callable[[str], str]) -> str:
    return ", ".join(str(i) for i in items) if items else t("none")


def _gender(sd: Dict[str, Any], cd: Dict[str, Any], t: Callable[[str], str]) -> str:
    value = get_nested_value(sd, "memory.seibetu")
    return {1: t("gender_male"), 2: t("gender_female")}.get(value, t("not_set"))


FANATIC_SECTION_KEY = "fanatic_related"

SECTIONS: Dict[str, Section] = {s.key: s for s in [
    Section(FANATIC_SECTION_KEY, [
        _var("NEO", label_key="neo_value", tooltip_key="neo_value_tooltip"),
        _var("Lamia_noroi", label_key="lamia_curse"),
        _var("trauma", label_key="trauma_value"),
        _var("killWarning", label_key="kill_warning"),
        _var("killed", label_key="killed", tooltip_key="killed_tooltip",
             compute=lambda sd, cd, t: t("variable_not_exist") if sd.get("killed") is None else sd["killed"]),
        _var("kill", label_key="kill_count", tooltip_key="kill_count_tooltip"),
    ]),
    Section("endings_statistics", [
        Field("total_endings", compute=lambda sd, cd, t: TOTAL_ENDINGS),
        Field("current_collected_endings", var_name="endings",
              compute=lambda sd, cd, t: len(cd["endings"])),
        Field("total_collected_endings", var_name="collectedEndings",
              tooltip_key="total_collected_endings_tooltip",
              compute=lambda sd, cd, t: len(cd["collected_endings"])),
        Field("missing_endings", compute=lambda sd, cd, t: (
            f"{len(cd['missing_endings'])}: {_join(cd['missing_endings'], t)}"
            if cd["missing_endings"] else t("none"))),
    ], button_text_key="view_requirements"),
    Section("stickers_statistics", [
        Field("total_stickers", compute=lambda sd, cd, t: TOTAL_STICKERS),
        Field("collected_stickers", var_name="sticker", compute=lambda sd, cd, t: len(cd["stickers"])),
        Field("missing_stickers_count", compute=lambda sd, cd, t: len(cd["missing_stickers"])),
        Field("missing_stickers", compute=lambda sd, cd, t: _join(cd["missing_stickers"], t)),
    ], button_text_key="view_requirements"),
    Section("characters_statistics", [
        Field("total_characters", compute=lambda sd, cd, t: TOTAL_CHARACTERS),
        Field("current_collected_characters", var_name="characters",
              compute=lambda sd, cd, t: len(cd["characters"])),
        Field("total_collected_characters", var_name="collectedCharacters",
              tooltip_key="total_collected_characters_tooltip",
              compute=lambda sd, cd, t: len(cd["collected_characters"])),
        Field("missing_characters", compute=lambda sd, cd, t: _join(cd["missing_characters"], t)),
    ]),
    Section("omakes_statistics", [
        Field("total_omakes", compute=lambda sd, cd, t: len(cd["total_omakes_set"])),
        Field("collected_omakes", var_name="omakes", compute=lambda sd, cd, t: len(cd["collected_omakes"])),
        Field("missing_omakes", compute=lambda sd, cd, t: _join(cd["missing_omakes"], t)),
        Field("gallery_count", var_name="gallery",
              compute=lambda sd, cd, t: f"{len(sd.get('gallery', []))}/{len(cd['total_gallery_set'])}"),
        Field("ng_scene_count", var_name="ngScene", tooltip_key="ng_scene_count_tooltip",
              tooltip_optional=True,
              compute=lambda sd, cd, t: f"{len(sd.get('ngScene', []))}/{len(cd['total_ng_scene_set'])}"),
    ], button_text_key="ng_scene_quick_check"),
    Section("game_statistics", [
        _var("wholeTotalMP", label_key="total_mp"),
        _var("judgeCounts.perfect", label_key="judge_perfect"),
        _var("judgeCounts.good", label_key="judge_good"),
        _var("judgeCounts.bad", label_key="judge_bad"),
        _var("secretEndOpen", label_key="secret_end_open"),
        _var("trueCount", label_key="true_count"),
        _var("epilogue", label_key="epilogue_count"),
        _var("loopCount", label_key="loop_count"),
        _var("loopRecord", label_key="loop_record", tooltip_key="loop_record_tooltip"),
    ]),
    Section("character_info", [
        _var("memory.name", label_key="character_name",
             compute=lambda sd, cd, t: get_nested_value(sd, "memory.name") or t("not_set")),
        _var("memory.seibetu", label_key="character_gender", compute=_gender),
        _var("memory.hutanari", label_key="hutanari"),
        _var("memory.cameraEnable", label_key="camera_enable"),
        _var("memory.yubiwa", label_key="yubiwa"),
    ]),
    Section("other_info", [
        _var("saveListNo", label_key="save_list_no"),
        # 相册页码从 0 开始，显示时 +1
        _var("albumPageNo", label_key="album_page_no",
             compute=lambda sd, cd, t: (sd.get("albumPageNo") or 0) + 1),
        _var("system.autosave", label_key="autosave_enabled", default=False),
        _var("fullscreen", label_key="fullscreen", default=False),
    ], hint_key="other_info_hint"),
]}


def section_order(fanatic_route: bool) -> List[str]:
    """分区显示顺序：狂信徒路线时「狂信徒相关」放最前，否则放在「角色信息」之前"""
    order = [key for key in SECTIONS if key != FANATIC_SECTION_KEY]
    if fanatic_route:
        return [FANATIC_SECTION_KEY, *order]
    index = order.index("character_info")
    return [*order[:index], FANATIC_SECTION_KEY, *order[index:]]


def field_value(field: Field, save_data: Dict[str, Any], computed: Dict[str, Any],
                t: Callable[[str], str]) -> str:
    """字段显示的文本；存档里的值类型异常时退回显示原始值"""
    raw = get_nested_value(save_data, field.path) if field.path else None
    try:
        if field.compute is not None:
            value = field.compute(save_data, computed, t)
        else:
            value = field.default if raw is None else raw
    except (TypeError, ValueError, KeyError, AttributeError) as e:
        logger.warning("Failed to compute field %s: %s", field.label_key, e)
        value = "" if raw is None else raw
    return str(value)
