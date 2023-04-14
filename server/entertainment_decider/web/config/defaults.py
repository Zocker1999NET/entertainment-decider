from __future__ import annotations


class _Config:
    pass


class DebugConfig(_Config):
    PONY_CREATE_DB = True
    PONY_FILENAME = "./db.sqlite"
    PONY_PROVIDER = "sqlite"


class TestingConfig(_Config):
    pass


class ProductionConfig(_Config):
    pass


__all__ = [
    "DebugConfig",
    "ProductionConfig",
    "TestingConfig",
]
