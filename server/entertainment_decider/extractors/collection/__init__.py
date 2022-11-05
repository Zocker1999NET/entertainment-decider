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
    "tt-rss": TtRssCollectionExtractor(
        params=tt_rss_params,
        label_filter=-1033,
    ),
    "youtube": YouTubeCollectionExtractor(),
}


def collection_expect_extractor(uri: str) -> CollectionExtractor:
    return expect_suitable_extractor(
        extractor_list=COLLECTION_EXTRACTORS.values(),
        uri=uri,
    )


def collection_update(
    collection: MediaCollection,
    check_cache_expired: bool = True,
) -> None:
    ex = collection_expect_extractor(collection.uri)
    ex.update_object(
        object=collection,
        check_cache_expired=check_cache_expired,
    )


def collection_extract_uri(uri: str) -> MediaCollection:
    elem: MediaCollection = CollectionExtractor.check_uri(uri)
    ex = collection_expect_extractor(uri)
    if not elem:
        elem = ex.extract_and_store(uri)
    else:
        ex.update_object(elem, check_cache_expired=False)
    return elem
