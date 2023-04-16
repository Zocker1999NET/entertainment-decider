from __future__ import annotations

import re
from typing import (
    Iterable,
)


SQL_WHITESPACE_PATTERN = re.compile(r"(\s|\n)+")


def sql_cleanup(sql: str) -> str:
    return SQL_WHITESPACE_PATTERN.sub(" ", sql).strip()


def sql_where_in(id: str, id_list: Iterable[str | int]) -> str:
    return f"{id} IN ({','.join(str(i) for i in id_list)})"
