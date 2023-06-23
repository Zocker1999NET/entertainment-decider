from datetime import date, datetime
import itertools
import subprocess
import sys
from typing import (
    IO,
    Iterable,
    Iterator,
    List,
    Literal,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    overload,
)


def all_same(iterable: Iterable) -> bool:
    it = iter(iterable)
    first = next(it)
    return all(first == elem for elem in it)


def call(
    args: Sequence[str],
    check: bool = True,
    stdin: Optional[IO] = None,
) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        args,
        capture_output=True,
        check=check,
        text=True,
        stdin=stdin,
    )
    return proc


# source: https://peps.python.org/pep-0257/#handling-docstring-indentation
def trim(docstring: str) -> str:
    """
    Trim strings like docstrings are trimmed following PEP 257
    """
    if not docstring:
        return ""
    # Convert tabs to spaces (following the normal Python rules)
    # and split into a list of lines:
    lines = docstring.expandtabs().splitlines()
    # Determine minimum indentation (first line doesn't count):
    indent = sys.maxsize
    for line in lines[1:]:
        stripped = line.lstrip()
        if stripped:
            indent = min(indent, len(line) - len(stripped))
    # Remove indentation (first line is special):
    trimmed = [lines[0].strip()]
    if indent < sys.maxsize:
        for line in lines[1:]:
            trimmed.append(line[indent:].rstrip())
    # Strip off trailing and leading blank lines:
    while trimmed and not trimmed[-1]:
        trimmed.pop()
    while trimmed and not trimmed[0]:
        trimmed.pop(0)
    # Return a single string:
    return "\n".join(trimmed)


def update_bool_value(
    old_value: bool, new_value: Union[bool, Literal["toggle"]]
) -> bool:
    if new_value == "toggle":
        return not old_value
    if type(new_value) != bool:
        raise Exception(
            f'Invalid type of new_value: Expected bool or literal "toggle", got type={type(new_value)!r}, value={new_value!r}'
        )
    return new_value


T = TypeVar("T")


def limit_iter(iter: Iterable[T], limit: int) -> List[T]:
    return list(itertools.islice(iter, limit))


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


def date_to_datetime(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)
