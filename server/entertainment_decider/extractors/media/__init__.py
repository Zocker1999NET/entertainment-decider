from __future__ import annotations

from typing import Dict


from ...models import MediaElement
from ..helpers import expect_suitable_extractor
from .base import MediaExtractor
from .youtube import YoutubeMediaExtractor
from .ytdl import YtdlMediaExtractor


MEDIA_EXTRACTORS: Dict[str, MediaExtractor] = {
    "youtube": YoutubeMediaExtractor(),
    "ytdl": YtdlMediaExtractor(),
}


def media_expect_extractor(uri: str) -> MediaExtractor:
    return expect_suitable_extractor(
        extractor_list=MEDIA_EXTRACTORS.values(),
        uri=uri,
    )


def media_update(element: MediaElement, check_cache_expired: bool = True):
    ex = media_expect_extractor(element.uri)
    ex.update_object(
        object=element,
        check_cache_expired=check_cache_expired,
    )


def media_extract_uri(uri: str) -> MediaElement:
    elem: MediaElement = MediaExtractor.check_uri(uri)
    if not elem:
        ex = media_expect_extractor(uri)
        elem = ex.extract_and_store(uri)
    return elem
