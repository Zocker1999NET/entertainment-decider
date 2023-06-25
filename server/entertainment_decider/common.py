from datetime import date, datetime
import subprocess
import sys
from typing import (
    IO,
    Iterable,
    Literal,
    Optional,
    Sequence,
    TypeVar,
    Union,
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


