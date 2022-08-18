import itertools
import subprocess
from typing import Iterable, List, Literal, TypeVar, Union


def call(args, check=True, stdin=None) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        args,
        capture_output=True,
        check=check,
        text=True,
        stdin=stdin,
    )
    return proc


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
