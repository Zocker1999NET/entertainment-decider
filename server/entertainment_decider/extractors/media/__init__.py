from __future__ import annotations

from typing import Dict

from ...models import MediaElement
from ..helpers import expect_suitable_extractor
from .base import MediaExtractor
from .ytdl import YtdlMediaExtractor


MEDIA_EXTRACTORS: Dict[str, MediaExtractor] = {
    "ytdl": YtdlMediaExtractor(),
}

def media_extract_uri(uri: str) -> MediaElement:
    elem: MediaElement = MediaExtractor.check_uri(uri)
    if not elem:
        elem = expect_suitable_extractor(MEDIA_EXTRACTORS.values(), uri).extract_and_store(uri)
    return elem
