from __future__ import annotations

from datetime import datetime, timedelta
import logging
import math
from typing import Any, Callable, Mapping, Optional, TypeVar

from pony import orm

from ...models import (
    CollectionUriMapping,
    MediaCollection,
    MediaCollectionLink,
    MediaElement,
)
from ..generic import ExtractedData, ExtractionError, GeneralExtractor


T = TypeVar("T")


class CollectionExtractor(GeneralExtractor[MediaCollection, T]):
    @staticmethod
    def check_uri(uri: str) -> Optional[MediaCollection]:
        mapping: CollectionUriMapping = CollectionUriMapping.get(uri=uri)
        if mapping:
            return mapping.element
        elem: MediaCollection = MediaCollection.get(uri=uri)
        if elem:
            logging.warning(
                f"Add missing URI mapping entry for uri {uri!r}, "
                + "this should not happen at this point and is considered a bug"
            )
            elem.add_single_uri(uri)
            return elem
        return None

    @staticmethod
    def _calculate_wait_hours(
        last_release_date: datetime,
        growth_rate: float = 3.25508,  # estimated for approriate cache timeout times (every 12 hours for 10 days old playlist)
    ) -> timedelta:
        days_since = max((datetime.now() - last_release_date) // timedelta(days=1), 1)
        wait_units = math.log(days_since, growth_rate)
        wait_hours = (wait_units + 1) * 4
        return timedelta(hours=wait_hours)

    def __configure_collection(self, collection: MediaCollection) -> None:
        collection.keep_updated = True

    def _create_object(self, data: ExtractedData[T]) -> MediaCollection:
        collection = data.create_collection()
        self.__configure_collection(collection)
        return collection

    def _load_object(self, data: ExtractedData[T]) -> MediaCollection:
        collection = data.load_collection()
        if collection:
            self.__configure_collection(collection)
        return collection

    def _add_episode(
        self,
        collection: MediaCollection,
        uri: str,
        season: int = 0,
        episode: int = 0,
    ) -> Optional[MediaElement]:
        # to avoid circular dependency
        # sadly do not know where
        from ..media import media_extract_uri

        try:
            element = media_extract_uri(uri)
        except ExtractionError:
            logging.warning(f"Failed while extracting media {uri!r}", exc_info=True)
            return None
        link = collection.add_episode(
            media=element,
            season=season,
            episode=episode,
        )
        if link is not None:
            logging.debug(
                f"Add to collection {collection.title!r} media {uri!r} (Season {season}, Episode {episode})"
            )
        return element

    def _inject_episode(
        self,
        collection: MediaCollection,
        data: ExtractedData[Any],
        season: int = 0,
        episode: int = 0,
    ) -> Optional[MediaElement]:
        from ..media import media_expect_extractor

        extractor = media_expect_extractor(data.object_uri)
        if data.extractor_name != extractor.name:
            raise Exception(
                f"Expected extractor {data.extractor_name!r} for uri {data.object_uri!r}, instead got {extractor.name!r}"
            )
        try:
            element = extractor.inject_object(data)
        except ExtractionError:
            logging.warning(
                f"Failed while extracting media {data.object_uri!r} while injecting from {collection.uri!r}",
                exc_info=True,
            )
            return None
        link = collection.add_episode(
            media=element,
            season=season,
            episode=episode,
        )
        if link:
            logging.debug(
                f"Add to collection {collection.title!r} media {data.object_uri!r} (Season {season}, Episode {episode})"
            )
        return element

    def _sort_episodes(self, coll: MediaCollection) -> None:
        sorting_methods: Mapping[int, Callable[[MediaCollectionLink], Any]] = {
            1: lambda l: l.element.release_date,
        }
        method = sorting_methods.get(coll.sorting_method)
        if method is None:
            return
        logging.debug(f"Sort collection by type {coll.sorting_method}")
        for index, link in enumerate(
            orm.select(l for l in coll.media_links).order_by(method)
        ):
            link.season = 0
            link.episode = index + 1

    def _update_hook(self, object: MediaCollection, data: ExtractedData[T]) -> None:
        self._sort_episodes(object)
