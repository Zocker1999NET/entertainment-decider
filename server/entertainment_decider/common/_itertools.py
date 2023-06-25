import itertools
from typing import (
    Iterable,
    Iterator,
    List,
    Literal,
    Tuple,
    TypeVar,
    overload,
)


T = TypeVar("T")


# fix Iterables


class _IterFixer(Iterator[T]):
    __it: Iterator[T]

    def __init__(self, it: Iterator[T]) -> None:
        super().__init__()
        self.__it = it

    def __iter__(self) -> Iterator[T]:
        return self

    def __next__(self) -> T:
        return next(self.__it)


def fix_iter(iterable: Iterable[T]) -> Iterable[T]:
    return _IterFixer(iter(iterable))


# lookahead on Iterables


@overload
def iter_lookahead(
    iterable: Iterable[T],
    get_first: Literal[False] = False,
    get_last: Literal[False] = False,
) -> Iterable[Tuple[T, T]]:
    ...


@overload
def iter_lookahead(
    iterable: Iterable[T],
    get_first: Literal[True],
    get_last: Literal[False] = False,
) -> Iterable[Tuple[None, T] | Tuple[T, T]]:
    ...


@overload
def iter_lookahead(
    iterable: Iterable[T],
    get_first: Literal[False] = False,
    get_last: Literal[True] = True,  #  <- default only to satisfy python
) -> Iterable[Tuple[T, T] | Tuple[T, None]]:
    ...


@overload
def iter_lookahead(
    iterable: Iterable[T],
    get_first: Literal[True],
    get_last: Literal[True],
) -> Iterable[Tuple[None, T] | Tuple[T, T] | Tuple[T, None]]:
    ...


def iter_lookahead(
    iterable: Iterable[T],
    get_first: bool = False,
    get_last: bool = False,
) -> Iterable[Tuple[None, T] | Tuple[T, T] | Tuple[T, None]]:
    it = iter(iterable)
    last = next(it)
    if get_first:
        yield None, last
    for cur in it:
        yield last, cur
        last = cur
    if get_last:
        yield last, None


# limit Iterables


def limit_iter(iter: Iterable[T], limit: int) -> List[T]:
    return list(itertools.islice(iter, limit))
