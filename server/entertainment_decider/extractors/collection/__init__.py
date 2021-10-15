from __future__ import annotations

from typing import Dict

from ...config import app_config
from ...models import MediaCollection
from ..helpers import expect_suitable_extractor
from .base import CollectionExtractor
from .tt_rss import TtRssCollectionExtractor, TtRssConnectionParameter
from .youtube import YouTubeCollectionExtractor


tt_rss_params = TtRssConnectionParameter(**app_config["extractors"]["tt_rss"])
COLLECTION_EXTRACTORS: Dict[str, CollectionExtractor] = {
    "tt-rss": TtRssCollectionExtractor(params=tt_rss_params, label_filter=-1033),
    "youtube": YouTubeCollectionExtractor(),
}

def collection_extract_uri(uri: str) -> MediaCollection:
    elem: MediaCollection = CollectionExtractor.check_uri(uri)
    ex = expect_suitable_extractor(COLLECTION_EXTRACTORS.values(), uri)
    if not elem:
        elem = ex.extract_and_store(uri)
    else:
        ex.update_object(elem, check_cache_expired=False)
    return elem
