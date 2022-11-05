from __future__ import annotations

import logging
from typing import Iterable, Optional, TypeVar

from .generic import ExtractionError, GeneralExtractor


T = TypeVar("T", bound=GeneralExtractor)


def search_suitable_extractor(extractor_list: Iterable[T], uri: str) -> Optional[T]:
    best_bet: Optional[T] = None
    for extractor in extractor_list:
        match = extractor.uri_suitable(uri)
        if match.accept_immediately:
            logging.debug(f"Accept {extractor.name} immediataly for {uri!r}")
            return extractor
        if match.can_accept and best_bet is None:
            best_bet = extractor
    if best_bet:
        logging.debug(f"Accept {best_bet.name} as fallback for {uri!r}")
    else:
        logging.debug(f"None found for {uri!r}")
    return best_bet


def expect_suitable_extractor(extractor_list: Iterable[T], uri: str) -> T:
    extractor = search_suitable_extractor(extractor_list, uri)
    if extractor is None:
        raise ExtractionError(f"No suitable extractor found for uri {uri!r}")
    return extractor
