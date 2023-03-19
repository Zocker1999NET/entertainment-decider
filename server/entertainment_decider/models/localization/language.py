from __future__ import annotations

from typing import Literal, Optional, TypedDict

from pycountry import languages  # type: ignore

from ..entities import Tag, TagKey
from .common import LocalizationError


def get_language_tag(identifier: str) -> Tag:
    language = find_language(identifier)
    if language is None:
        raise LocalizationError(identifier=identifier, kind="language")
    TagKey.get_or_create_tag(  # ensure it is created
        ".localization/language",
        title="Languages",
        notes="Collection for all language tags",
        use_for_preferences=False,
    )
    return TagKey.get_or_create_tag(
        f".localization/language/{language.alpha_3.lower()}",
        title=language.common_name,
        notes="Language",
        use_for_preferences=True,
        super_tags=[".localization/language"],
    )


def find_language(identifier: str) -> Optional[Language]:
    return Language(languages.lookup(identifier)._fields)


class Language:
    __data: _LanguageData

    def __init__(self, language_data: _LanguageData) -> None:
        self.__data = language_data

    @property
    def alpha_2(self) -> str:
        return self.__data["alpha_2"]

    @property
    def alpha_3(self) -> str:
        return self.__data["alpha_3"]

    @property
    def scope(self) -> str:
        return self.__data["scope"]

    @property
    def type(self) -> str:
        return self.__data["type"]

    @property
    def legacy_bibliographic(self) -> str:
        return self.__get_first("bibliographic", "alpha_3")

    @property
    def name(self) -> str:
        return self.__get_first("name", "common_name")

    @property
    def common_name(self) -> str:
        return self.__get_first("common_name", "name")

    def __get_first(
        self,
        *keys: Literal[
            "alpha_3",
            "bibliographic",
            "common_name",
            "name",
        ],
    ) -> str:
        for k in keys:
            if k in self.__data:
                return self.__data[k]
        raise AttributeError(self.__data)


class _LanguageDataTotal(TypedDict):
    alpha_3: str
    name: str
    scope: str
    type: str


class _LanguageData(_LanguageDataTotal, total=False):
    alpha_2: str
    bibliographic: str
    common_name: str
    inverted_name: str
