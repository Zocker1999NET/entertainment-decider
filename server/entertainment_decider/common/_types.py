from __future__ import annotations

from collections.abc import (
    Sequence,
    Mapping,
)
from typing import (
    TypeAlias,
)


JsonMappingKey: TypeAlias = str | int | float
"""type for use in JSON mappings as key"""
JsonLeaf: TypeAlias = JsonMappingKey | bool | None
"""object natively mapping to JSON as values excluding containers"""

JsonMapping: TypeAlias = Mapping[JsonMappingKey, "JsonRepr"]
"""mapping natively mapping to JSON"""
JsonList: TypeAlias = Sequence["JsonRepr"]
"""list natively mapping to JSON"""
JsonContainer: TypeAlias = JsonList | JsonMapping
"""container natively mapping to JSON"""

JsonRepr: TypeAlias = JsonContainer | JsonLeaf
"""object natively mapping to JSON"""
