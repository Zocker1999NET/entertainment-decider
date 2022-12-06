from __future__ import annotations

from typing import List, NewType, TypeVar

from pony.orm.core import Query as PonyQuery


SafeStr = NewType("SafeStr", str)
"""
Use this type for strings which are expected to be safe to insert into SQL statements.
They may be included into a SQL statement by quoting them manually: f"SELECT * FROM '{safe_str}'"

DO NOT CAST STRINGS WHICH MAY BE SET BY USERS TO PREVENT SQL INJECTION ATTACKS.
"""


T = TypeVar("T")


class Query(
    List[T],
    PonyQuery,
):
    """
    This class may be used to reflect PonyQuerys with all their "kind of" list behavior.
    Only use it for type hintings.
    """

    pass
