import re
from typing import Sequence


def common_prefix(elements: Sequence[str]) -> str:
    if len(elements) <= 1:
        return ""
    test = re.compile(r"^[^\w]$")
    s1 = min(elements)
    s2 = max(elements)
    i = 0
    min_l = min(len(s1), len(s2))
    if min_l <= 0:
        return ""
    for i in range(min_l):
        if s1[i] != s2[i]:
            break
    else:
        i += 1
    while i > 0 and not test.match(s1[i - 1]):
        i -= 1
    return s1[:i]


def common_suffix(elements: Sequence[str]) -> str:
    return common_prefix([s[::-1] for s in elements])[::-1]


def remove_prefix(elements: Sequence[str]) -> Sequence[str]:
    pre = len(common_prefix(elements))
    return [s[pre:] for s in elements]


def remove_suffix(elements: Sequence[str]) -> Sequence[str]:
    suf = len(common_suffix(elements))
    return [s[::-1][suf:][::-1] for s in elements]


def remove_common_trails(elements: Sequence[str]) -> Sequence[str]:
    return remove_prefix(remove_suffix(elements))
