from typing import (
    Callable,
    Optional,
    Sequence,
    TypeVar,
)


T = TypeVar("T")
K = TypeVar("K")


def search_source_by_keys(
    source: Callable[[K], Optional[T]],
    all_keys: Sequence[K],
) -> Optional[T]:
    """
    tries <all_keys> in <source> and returns first result `!= None`, otherwise `None`
    """
    for key in all_keys:
        item = source(key)
        if item is not None:
            return item
    return None
