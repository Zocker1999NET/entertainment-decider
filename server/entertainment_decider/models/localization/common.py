from __future__ import annotations


class LocalizationError(Exception):
    def __init__(self, identifier: str | int, kind: str):
        super().__init__(f"Couldn't find {kind} with {identifier!r}")
