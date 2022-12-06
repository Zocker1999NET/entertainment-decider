from __future__ import annotations

from typing import Dict, Tuple


from ...config import app_config
from ...models import MediaCollection
from ..generic import ChangedReport
from ..helpers import expect_suitable_extractor
from .base import CollectionExtractor
from .aggregated import AggregatedCollectionExtractor
from .tt_rss import TtRssCollectionExtractor, TtRssConnectionParameter
from .tmdb import TmdbCollectionExtractor, TmdbKeywordExtractor
from .tvmaze import TvmazeCollectionExtractor
from .youtube import YouTubeCollectionExtractor


tt_rss_params = TtRssConnectionParameter(**app_config["extractors"]["tt_rss"])
COLLECTION_EXTRACTORS: Dict[str, CollectionExtractor] = {
    "aggregated": AggregatedCollectionExtractor(),
    "tt-rss": TtRssCollectionExtractor(
        params=tt_rss_params,
        label_filter=-1033,
        mark_as_read=True,
    ),
    "tmdb": TmdbCollectionExtractor(),
    "tmdb-keyword": TmdbKeywordExtractor(),
    "tvmaze": TvmazeCollectionExtractor(),
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
) -> ChangedReport:
    ex = collection_expect_extractor(collection.uri)
    return ex.update_object(
        object=collection,
        check_cache_expired=check_cache_expired,
    )


def collection_extract_uri_new(uri: str) -> Tuple[bool, MediaCollection]:
    elem = CollectionExtractor.check_uri(uri)
    if not elem:
        return True, collection_expect_extractor(uri).extract_and_store(uri)
    return False, elem


def collection_extract_uri(uri: str) -> MediaCollection:
    new_obj, elem = collection_extract_uri_new(uri)
    if not new_obj:
        ex = collection_expect_extractor(uri)
        ex.update_object(elem, check_cache_expired=False)
    return elem
