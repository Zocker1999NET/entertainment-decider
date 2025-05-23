from __future__ import annotations

from datetime import (
    datetime,
)
from logging import (
    INFO,
    Logger,
)

log = Logger(__name__)


def multi_strptime(text: str, *format: str, log_level: int = INFO) -> datetime:
    log.debug(f"try multi_strptime on {text!r} with {format!r}")
    for fmt in format:
        try:
            return datetime.strptime(text, fmt)
        except:
            log.log(
                level=log_level,
                msg=f"failed multi_strptime on {text!r} with {fmt!r}, continue",
            )
    raise ValueError(f"failed all multi_strptime on {text!r} with {format!r}")
