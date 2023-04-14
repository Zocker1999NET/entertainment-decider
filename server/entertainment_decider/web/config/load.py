from __future__ import annotations

from flask import (
    Config,
)

from .defaults import (
    DebugConfig,
    ProductionConfig,
    TestingConfig,
)


FLASK_DEBUG_KEY = "DEBUG"
FLASK_TESTING_KEY = "TESTING"

ENV_FLASK_PREFIX = "FLASK"
ENV_OTHER_NAMESPACES = [
    "CELERY",
    "PONY",
]


def load_config(config: Config) -> None:
    _load_defaults(config)
    _load_from_env(config)


def _load_defaults(config: Config) -> None:
    defaults = (
        DebugConfig
        if config.get(FLASK_DEBUG_KEY, False)
        else TestingConfig
        if config.get(FLASK_TESTING_KEY, False)
        else ProductionConfig
    )
    config.from_object(defaults())


def _load_from_env(config: Config) -> None:
    config.from_prefixed_env(
        prefix="FLASK",
    )
    for prefix in ENV_OTHER_NAMESPACES:
        config.from_prefixed_env(
            prefix=prefix,
            trim_prefix=False,
        )
