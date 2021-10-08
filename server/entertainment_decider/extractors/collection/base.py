from __future__ import annotations

import logging
from typing import Optional, TypeVar

from ...models import CollectionUriMapping, MediaCollection
from ..generic import ExtractedData, GeneralExtractor


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
                f"Add missing URI mapping entry for uri {uri!r}, " +
                "this should not happen at this point and is considered a bug"
            )
            elem.add_uris((uri,))
            return elem
        return None

    def _create_object(self, data: ExtractedData[T]) -> MediaCollection:
        collection = data.create_collection()
        return collection

    def _load_object(self, data: ExtractedData[T]) -> MediaCollection:
        collection = data.load_collection()
        collection.keep_updated = True
        return collection
