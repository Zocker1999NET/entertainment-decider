from __future__ import annotations

from typing import Literal, Optional, TypedDict

from pycountry import countries  # type: ignore

from ..entities import Tag, TagKey
from .common import LocalizationError


def get_country_tag(identifier: str | int) -> Tag:
    country = find_country(identifier)
    if country is None:
        raise LocalizationError(identifier=identifier, kind="country")
    TagKey.get_or_create_tag(  # ensure it is created
        ".localization/country",
        title="Countries",
        notes="Collection for all country tags",
        use_for_preferences=False,
    )
    return TagKey.get_or_create_tag(
        f".localization/country/{country.alpha_3.lower()}",
        title=country.common_name,
        notes="Country",
        use_for_preferences=True,
        super_tags=[".localization/country"],
    )


def find_country(identifier: str | int) -> Optional[Country]:
    if isinstance(identifier, int):
        if identifier < 0:
            return None
        identifier = str(identifier)
    return Country(countries.lookup(identifier)._fields)


class Country:
    __data: _CountryData

    def __init__(self, country_data: _CountryData) -> None:
        self.__data = country_data

    @property
    def alpha_2(self) -> str:
        return self.__data["alpha_2"]

    @property
    def alpha_3(self) -> str:
        return self.__data["alpha_3"]

    @property
    def flag(self) -> str:
        return self.__data["flag"]

    @property
    def numeric(self) -> str:
        return self.__data["numeric"]

    @property
    def name(self) -> str:
        return self.__get_first("name", "common_name", "official_name")

    @property
    def common_name(self) -> str:
        return self.__get_first("common_name", "name", "official_name")

    @property
    def official_name(self) -> str:
        return self.__get_first("official_name", "name", "common_name")

    def __get_first(
        self,
        *keys: Literal[
            "common_name",
            "name",
            "official_name",
        ],
    ) -> str:
        for k in keys:
            if k in self.__data:
                return self.__data[k]
        raise AttributeError(self.__data)


class _CountryDataTotal(TypedDict):
    alpha_2: str
    alpha_3: str
    flag: str
    name: str
    numeric: str


class _CountryData(_CountryDataTotal, total=False):
    common_name: str
    official_name: str
