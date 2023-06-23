from __future__ import annotations

from traceback import format_exception
from typing import Dict


def gen_api_error(exc: Exception) -> Dict:
    return {
        "type": repr(type(exc)),
        "args": repr(exc.args),
        "traceback": list(format_exception(exc)),
    }
