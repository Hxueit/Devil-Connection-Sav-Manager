import re
import string

from src.utils.translations import TRANSLATIONS


def test_languages_have_identical_keys():
    reference = set(TRANSLATIONS["zh_CN"])
    for lang, table in TRANSLATIONS.items():
        assert set(table) == reference, lang


def test_format_placeholders_match_across_languages():
    # 各语言的 {占位符} 必须一致，否则 .format() 会在某种语言下抛 KeyError
    formatter = string.Formatter()

    def fields(text):
        try:
            return {name for _, name, _, _ in formatter.parse(text) if name}
        except ValueError:
            return set(re.findall(r"\{(\w+)\}", text))

    for key, text in TRANSLATIONS["zh_CN"].items():
        for lang, table in TRANSLATIONS.items():
            assert fields(table[key]) == fields(text), f"{lang}:{key}"
