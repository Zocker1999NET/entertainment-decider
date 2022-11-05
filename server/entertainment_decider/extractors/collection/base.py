from __future__ import annotations

from datetime import datetime, timedelta
import logging
import math
from typing import Optional, TypeVar

from ...models import (
    CollectionUriMapping,
    MediaCollection,
    MediaElement,
)
from ..generic import ExtractedData, ExtractionError, GeneralExtractor
from ..media import media_extract_uri


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
        logging.debug(f"Add to collection {collection.title!r} media {uri!r} (Season {season}, Episode {episode})")
        try:
            element = media_extract_uri(uri)
        except ExtractionError:
            logging.warning(f"Failed while extracting media {uri!r}", exc_info=True)
            return None
        collection.add_episode(
            media=element,
            season=season,
            episode=episode,
        )
        return element
