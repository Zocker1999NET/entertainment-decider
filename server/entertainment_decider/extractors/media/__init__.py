from __future__ import annotations

from typing import Dict, Tuple


from ...models import MediaElement
from ..helpers import expect_suitable_extractor
from .base import MediaExtractor
from .tmdb import TmdbMovieMediaExtractor
from .tvmaze import TvmazeMediaExtractor
from .youtube import YoutubeMediaExtractor
from .ytdl import YtdlMediaExtractor


MEDIA_EXTRACTORS: Dict[str, MediaExtractor] = {
    "tmdb": TmdbMovieMediaExtractor(),
    "tvmaze": TvmazeMediaExtractor(),
    "youtube": YoutubeMediaExtractor(),
    "ytdl": YtdlMediaExtractor(),
}


def media_expect_extractor(uri: str) -> MediaExtractor:
    return expect_suitable_extractor(
        extractor_list=MEDIA_EXTRACTORS.values(),
        uri=uri,
    )


def media_update(element: MediaElement, check_cache_expired: bool = True) -> None:
    ex = media_expect_extractor(element.primary_uri)
    ex.update_object(
        object=element,
        check_cache_expired=check_cache_expired,
    )


def media_extract_uri_new(uri: str) -> Tuple[bool, MediaElement]:
    elem = MediaExtractor.check_uri(uri)
    if not elem:
        return True, media_expect_extractor(uri).extract_and_store(uri)
    return False, elem


# exists to mirror collection_extract_uri
def media_extract_uri(uri: str) -> MediaElement:
    _, elem = media_extract_uri_new(uri)
    return elem
