from __future__ import annotations

from typing import Callable, Iterable, Protocol, TypeAlias, TypeVar


# cannot bind TagProto to itself: TagProto[T]
T = TypeVar("T", bound="TagProto", covariant=True)  # type: ignore


class TagableProto(Protocol[T]):
    @property
    def all_tags(self) -> Iterable[T]:
        ...

    @property
    def direct_tags(self) -> Iterable[T]:
        ...

    @property
    def super_tags(self) -> Iterable[T]:
        ...


class TagProto(TagableProto[T], Protocol):
    @property
    def id(self) -> int:
        ...

    @property
    def use_for_preferences(self) -> bool:
        ...


TagGetter: TypeAlias = Callable[[int], T]
