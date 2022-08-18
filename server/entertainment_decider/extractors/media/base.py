from __future__ import annotations

import logging
from typing import Dict, Optional, TypeVar

from ...models import MediaCollection, MediaElement, MediaUriMapping
from ..generic import AuthorExtractedData, ExtractedData, GeneralExtractor
from ..collection.base import CollectionExtractor


T = TypeVar("T")


class MediaExtractor(GeneralExtractor[MediaElement, T]):

    # abstract

    def _get_author_data(self, data: Dict) -> Optional[AuthorExtractedData]:
        return None

    # defined

    @staticmethod
    def check_uri(uri: str) -> Optional[MediaElement]:
        mapping: MediaUriMapping = MediaUriMapping.get(uri=uri)
        if mapping:
            return mapping.element
        elem: MediaElement = MediaElement.get(uri=uri)
        if elem:
            logging.warning(
                f"Add missing URI mapping entry for uri {uri!r}, "
                + "this should not happen at this point and is considered a bug"
            )
            elem.add_single_uri(uri)
            return elem
        return None

    def _create_object(self, data: ExtractedData[T]) -> MediaElement:
        return data.create_media()

    def _load_object(self, data: ExtractedData[T]) -> MediaElement:
        return data.load_media()

    def __create_author_collection(
        self, author_data: AuthorExtractedData
    ) -> MediaCollection:
        collection = author_data.create_collection()
        collection.keep_updated = False
        collection.watch_in_order = False
        return collection

    def __lookup_author_collection(
        self, author_data: AuthorExtractedData
    ) -> Optional[MediaCollection]:
        return CollectionExtractor.check_uri(
            uri=author_data.object_uri,
        ) or MediaCollection.get(
            extractor_name=author_data.extractor_name,
            extractor_key=author_data.object_key,
        )

    def __get_author_collection(
        self, author_data: AuthorExtractedData
    ) -> MediaCollection:
        collection = self.__lookup_author_collection(author_data)
        if collection is None:
            collection = self.__create_author_collection(author_data)
        if not collection.title or collection.title.startswith("[author] "):
            collection.title = (
                f"[author] [{author_data.extractor_name}] {author_data.author_name}"
            )
        return collection

    def __add_to_author_collection(self, element: MediaElement, data: Dict):
        author_data = self._get_author_data(data)
        if author_data is None or not author_data.is_valid:
            return
        collection = self.__get_author_collection(author_data)
        collection.add_episode(element)

    def _update_hook(self, object: MediaElement, data: ExtractedData[T]):
        self.__add_to_author_collection(object, data.data)
