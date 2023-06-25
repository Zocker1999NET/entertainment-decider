from typing import (
    Literal,
)


def update_bool_value(
    old_value: bool,
    new_value: bool | Literal["toggle"],
) -> bool:
    if new_value == "toggle":
        return not old_value
    if type(new_value) != bool:
        raise Exception(
            f'Invalid type of new_value: Expected bool or literal "toggle", got type={type(new_value)!r}, value={new_value!r}'
        )
    return new_value
