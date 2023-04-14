from __future__ import annotations

from typing import (
    Mapping,
    Optional,
    Tuple,
    Type,
    TypeAlias,
)


# type aliases


TypeSet: TypeAlias = Tuple[Type, ...]
TypeLike: TypeAlias = Type | TypeSet


# exceptions


class ConfigValidationError(Exception):
    key: str


class ConfigMissingRequiredError(ConfigValidationError):
    def __init__(self, *, key: str) -> None:
        super().__init__(f"Missing configuration value for key {key!r}")
        self.key = key


class ConfigInvalidTypeError(ConfigValidationError):
    key: str
    types: TypeSet

    def __init__(self, *, key: str, types: TypeLike, got_type: Type) -> None:
        self.key = key
        self.types = self.__parse_type_like(types)
        super().__init__(
            f"Required configuration value for key {key!r} to be of either {self.type_list}; got type {got_type}."
        )

    @staticmethod
    def __parse_type_like(types: TypeLike) -> TypeSet:
        if isinstance(types, tuple):
            return types
        return (types,)

    @property
    def type_list(self) -> str:
        return ", ".join(str(t) for t in self.types)


# methods


_REQUIRED_KEYS: Mapping[str, Optional[TypeLike]] = {
    "PONY_PROVIDER": str,
    "SECRET_KEY": (bytes, str),
}


_OPTIONAL_KEYS: Mapping[str, Optional[TypeLike]] = {
    "PONY_CHARSET": str,
    "PONY_CREATE_DB": bool,
    "PONY_DATABASE": str,
    "PONY_DB": str,
    "PONY_DSN": str,
    "PONY_FILENAME": str,
    "PONY_HOST": str,
    "PONY_PASSWD": str,
    "PONY_PASSWORD": str,
    "PONY_PORT": int,
    "PONY_USER": str,
}


def validate_config(config: Mapping) -> None:
    for required, key_list in {True: _REQUIRED_KEYS, False: _OPTIONAL_KEYS}.items():
        for key, types in key_list.items():
            check_value(
                config=config,
                key=key,
                types=types,
                required=required,
            )


def check_value(
    config: Mapping, key: str, types: Optional[TypeLike] = None, required: bool = True
) -> None:
    if key not in config:
        if required:
            raise ConfigMissingRequiredError(
                key=key,
            )
        return
    if types is None:
        return
    value = config[key]
    if not isinstance(value, types):
        raise ConfigInvalidTypeError(
            key=key,
            types=types,
            got_type=type(value),
        )
