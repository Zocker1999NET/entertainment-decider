from typing import (
    Callable,
    TypeAlias,
    TypeVar,
)


T = TypeVar("T")


LazyValue: TypeAlias = Callable[[], T]


__all__ = [
    "LazyValue",
]
