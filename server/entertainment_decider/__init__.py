from __future__ import annotations

from pathlib import Path

from flask import (
    Flask,
)

from .web.config import apply_config


def create_app() -> Flask:
    app = Flask(
        import_name=__name__,
        instance_relative_config=True,
        root_path=str(Path(__file__).parent.parent),
    )
    apply_config(app.config)
    print(app.static_folder)
    return app


__all__ = [
    "create_app",
]
