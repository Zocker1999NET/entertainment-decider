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
        # this method is the reason for this class
        # some iterators miss it and so are not Iterable without this proxy
        return self

    def __next__(self) -> T:
        return next(self.__it)


def fix_iter(iterable: Iterable[T]) -> Iterable[T]:
    """
    wraps the iterator of iterable
    into a simple proxy Iterator/Iterable implementation.

    Required in weird edgecases,
    where the iterator of an iterable is not an iterable.
    """
    return _IterFixer(iter(iterable))


# lookahead on Iterables


@overload
def iter_lookahead(
    iterable: Iterable[T],
    get_first: Literal[False] = False,
    get_last: Literal[False] = False,
) -> Iterable[Tuple[T, T]]:
    """
    allows iterating over <iterable> while also getting the last/next item

    The pairs are given as a Tuple and so can be split:
    ```python
    for last, cur in iter_lookahead(iterable): ...
    ```

    The first and last tuple will contain the first / last two entries, so that
    - `iterable[0]` only appears in `last` and not in `cur`
    - `iterable[-1]` only appears in `cur` and not in `last`

    You can change that behavior with <get_first>/<get_last>.
    """
    ...


@overload
def iter_lookahead(
    iterable: Iterable[T],
    get_first: Literal[True],
    get_last: Literal[False] = False,
) -> Iterable[Tuple[None, T] | Tuple[T, T]]:
    """
    allows iterating over <iterable> while also getting the last/next item

    The pairs are given as a Tuple and so can be split:
    ```python
    for last, cur in iter_lookahead(iterable): ...
    ```

    - The first tuple will look like `(None, cur)`,
      so that `iterable[0]` will appear in both `cur` and `last`.
    - The last tuple will contain the last two entries,
      so that `iterable[-1]` only appears in `cur` and not in `last`.

    You can change that behavior with <get_first>/<get_last>.
    """
    ...


@overload
def iter_lookahead(
    iterable: Iterable[T],
    get_first: Literal[False] = False,
    get_last: Literal[True] = True,  #  <- default only to satisfy python
) -> Iterable[Tuple[T, T] | Tuple[T, None]]:
    """
    allows iterating over <iterable> while also getting the last/next item

    The pairs are given as a Tuple and so can be split:
    ```python
    for last, cur in iter_lookahead(iterable): ...
    ```

    - The first tuple will contain the first two entries,
      so that `iterable[0]` only appears in `cur` and not in `last`.
    - The last tuple will look like `(last, None)`,
      so that `iterable[-1]` will appear in both `cur` and `last`.

    You can change that behavior with <get_first>/<get_last>.
    """
    ...


@overload
def iter_lookahead(
    iterable: Iterable[T],
    get_first: Literal[True],
    get_last: Literal[True],
) -> Iterable[Tuple[None, T] | Tuple[T, T] | Tuple[T, None]]:
    """
    allows iterating over <iterable> while also getting the last/next item

    The pairs are given as a Tuple and so can be split:
    ```python
    for last, cur in iter_lookahead(iterable): ...
    ```

    The first / last tuple will look like `(None, T)` / `(T, None)`,
    so that both `iterable[0]` and `iterable[-1]`
    will both appear in `cur` and `last`.

    You can change that behavior with <get_first>/<get_last>.
    """
    ...


def iter_lookahead(
    iterable: Iterable[T],
    get_first: bool = False,
    get_last: bool = False,
) -> Iterable[Tuple[None, T] | Tuple[T, T] | Tuple[T, None]]:
    """
    allows iterating over <iterable> while also getting the last/next item

    The pairs are given as a Tuple and so can be split:
    ```python
    for last, cur in iter_lookahead(iterable): ...
    ```

    The behavior for the border cases can be configured.
    If <get_first> is True, the first tuple will be `(None, last)`.
    If <get_last> is True, the last tuple will be `(cur, None)`.
    Otherwise, both values will be set at the borders respectively.
    See the docstrings for the overloaded methods.
    """
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
    """gets the first <limit> elements of <iter> and puts them in a list"""
    return list(itertools.islice(iter, limit))
