from __future__ import annotations

import cProfile
from functools import wraps
import pstats


LIST_MAX_FUNCTION_COUNT = 40


def profile(fun):
    @wraps(fun)
    def _fun(*args, **kwargs):
        with cProfile.Profile() as pf:
            ret = fun(*args, **kwargs)
        pstats.Stats(pf).sort_stats(pstats.SortKey.CUMULATIVE).print_stats(
            "entertainment_decider",
            LIST_MAX_FUNCTION_COUNT,
        )
        return ret

    return _fun
