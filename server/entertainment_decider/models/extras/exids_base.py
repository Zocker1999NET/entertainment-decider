from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Optional,
    Protocol,
    Tuple,
    Type,
    TypeAlias,
    TypeVar,
    TypedDict,
    Unpack,
)

from pony import orm


WIKIDATA_PROPERTY_PREFIX = "org.wikidata/property"

T = TypeVar("T")


# attributes & docstrings need to be synced (manually)
# all occassions are tagged with SYNC:ExIdKey:Properties


ExIdKeyTuple: TypeAlias = Tuple[bool, str]


class ExIdKeyDict(TypedDict):
    # SYNC:ExIdKey:Properties
    wikidata_prop: bool
    """
    `True` if key_name is a wikidata property,
    `False` if key_name is a canonical key name.
    """
    key_name: str
    """
    key name for external identifier

    Should be used externally.
    Should be unique worldwide, but one per external identifier.

    Can either be a Wikidata property id (starting with `P`),
    otherwise a canonical key names (see `docs/canonical_exids.md`).
    """


class ExIdKeyData(Protocol):
    # SYNC:ExIdKey:Properties
    wikidata_prop: bool
    """
    `True` if key_name is a wikidata property,
    `False` if key_name is a canonical key name.
    """
    key_name: str
    """
    key name for external identifier

    Should be used externally.
    Should be unique worldwide, but one per external identifier.

    Can either be a Wikidata property id (starting with `P`),
    otherwise a canonical key names (see `docs/canonical_exids.md`).
    """

    @property
    def key_map(self) -> ExIdKeyDict:
        # SYNC:ExIdKey:Properties
        return {
            "wikidata_prop": self.wikidata_prop,
            "key_name": self.key_name,
        }

    @property
    def key_data_copy(self) -> ExIdKeyData:
        return pack_ExIdKey(key_data=self.key_map)

    @property
    def key_str(self) -> str:
        # SYNC:ExIdKey:Properties
        return (
            WIKIDATA_PROPERTY_PREFIX + ":" if self.wikidata_prop else ""
        ) + self.key_name


ExIdKeyCompatible: TypeAlias = ExIdKeyTuple | ExIdKeyDict | ExIdKeyData


@dataclass
class ExIdKey_Native(ExIdKeyData):
    """implementer of ExIdKeyProto as dataclass"""

    # SYNC:ExIdKey:Properties
    wikidata_prop: bool
    """
    `True` if key_name is a wikidata property,
    `False` if key_name is a canonical key name.
    """
    key_name: str
    """
    key name for external identifier

    Should be used externally.
    Should be unique worldwide, but one per external identifier.

    Can either be a Wikidata property id (starting with `P`),
    otherwise a canonical key names (see `docs/canonical_exids.md`).
    """


def new_ExIdKey(**kwargs: Unpack[ExIdKeyDict]) -> ExIdKeyData:
    return ExIdKey_Native(**kwargs)


def pack_ExIdKey(key_data: ExIdKeyCompatible) -> ExIdKeyData:
    if isinstance(key_data, tuple):
        # SYNC:ExIdKey:Properties
        return ExIdKey_Native(wikidata_prop=key_data[0], key_name=key_data[1])
    if isinstance(key_data, dict):
        return ExIdKey_Native(**key_data)
    return key_data


class ExIdKey_Columns(ExIdKeyData):
    """implementer of ExIdKeyProto for Pony tables"""

    # SYNC:ExIdKey:Properties
    wikidata_prop: bool = orm.Required(bool)
    """
    `True` if key_name is a wikidata property,
    `False` if key_name is a canonical key name.
    """
    key_name: str = orm.Required(str)
    """
    key name for external identifier

    Should be used externally.
    Should be unique worldwide, but one per external identifier.

    Can either be a Wikidata property id (starting with `P`),
    otherwise a canonical key names (see `docs/canonical_exids.md`).
    """
    orm.composite_key(wikidata_prop, key_name)

    @classmethod
    def get_by_data(cls: Type[T], key_data: ExIdKeyCompatible) -> Optional[T]:
        d = pack_ExIdKey(key_data)
        # SYNC:ExIdKey:Properties
        return cls.get(
            wikidata_prop=d.wikidata_prop,
            key_name=d.key_name,
        )

    def update_from_key_map(self, key_data: ExIdKeyCompatible) -> bool:
        data = pack_ExIdKey(key_data=key_data)
        if not self.needs_update(key_data=data):
            return False
        # SYNC:ExIdKey:Properties
        self.wikidata_prop = data.wikidata_prop
        self.key_name = data.key_name
        return True

    def needs_update(self, key_data: ExIdKeyCompatible) -> bool:
        data = pack_ExIdKey(key_data=key_data)
        # SYNC:ExIdKey:Properties
        return any(
            (
                self.wikidata_prop == data.wikidata_prop,
                self.key_name == data.key_name,
            )
        )
