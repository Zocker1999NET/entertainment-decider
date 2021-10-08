from __future__ import annotations

from typing import Dict

from ...models import MediaElement
from .base import MediaExtractor
from .ytdl import YtdlMediaExtractor


MEDIA_EXTRACTORS: Dict[str, MediaExtractor] = {
    "ytdl": YtdlMediaExtractor(),
}

def media_extract_uri(extractor_name: str, uri: str) -> MediaElement:
    elem: MediaElement = MediaExtractor.check_uri(uri)
    if not elem:
        elem = MEDIA_EXTRACTORS[extractor_name].extract_and_store(uri)
    return elem
