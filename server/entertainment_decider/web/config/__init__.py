from .load import load_config
from .validate import validate_config

from flask import (
    Config,
)


def apply_config(config: Config) -> None:
    load_config(config)
    validate_config(config)


__all__ = [
    "apply_config",
]
