from datetime import date, datetime
from typing import (
    Optional,
)


def date_to_datetime(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)


def to_just_number(name: str) -> Optional[int]:
    try:
        return int(name)
    except ValueError:
        return None
