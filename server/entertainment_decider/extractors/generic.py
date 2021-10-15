from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import logging
from typing import Dict, Generic, Optional, TypeVar

from ..models import MediaCollection, MediaElement


T = TypeVar("T")


class SuitableLevel(Enum):

    NO = (False, False)
    FALLBACK = (True, False)
    ALWAYS = (True, True)

    @property
    def can_accept(self):
        return self.value[0]

    @property
    def accept_immediately(self):
        return self.value[1]


class ExtractionError(Exception):
    pass


@dataclass
class ExtractedDataLight:
    object_uri: str
    extractor_name: str
    object_key: str

    def create_media(self) -> MediaElement:
        return MediaElement(
            uri = self.object_uri,
            extractor_name = self.extractor_name,
            extractor_key = self.object_key,
        )

    def create_collection(self) -> MediaCollection:
        return MediaCollection(
            uri = self.object_uri,
            extractor_name = self.extractor_name,
            extractor_key = self.object_key
        )


@dataclass
class ExtractedData(ExtractedDataLight, Generic[T]):
    data: T = dataclasses.field(default=None, repr=False, compare=False)

    @property
    def has_data(self) -> bool:
        return self.data is not None

    def load_media(self) -> Optional[MediaElement]:
        return MediaElement.get(extractor_name=self.extractor_name, extractor_key=self.object_key)

    def load_collection(self) -> Optional[MediaCollection]:
        return MediaCollection.get(extractor_name=self.extractor_name, extractor_key=self.object_key)


@dataclass
class AuthorExtractedData(ExtractedDataLight):
    author_name: str

    @property
    def is_valid(self):
        return len(list(v for _, v in self.__dict__.items() if v is None)) <= 0


E = TypeVar("E", MediaElement, MediaCollection)

class GeneralExtractor(Generic[E, T]):

    name: str

    def __init__(self, name: str):
        self.name = name

    # abstract (for media & collection base classes)

    @staticmethod
    def check_uri(uri: str) -> Optional[E]:
        raise NotImplementedError()

    def _create_object(self, data: ExtractedData[T]) -> E:
        raise NotImplementedError()

    def _load_object(self, data: ExtractedData[T]) -> E:
        raise NotImplementedError()

    # abstract (for specific extractor classes)

    def uri_suitable(self, uri: str) -> SuitableLevel:
        raise NotImplementedError()

    def can_extract_offline(self, uri: str) -> bool:
        return False

    def _cache_expired(self, date: datetime) -> bool:
        return False

    def _extract_offline_only(self, uri: str) -> ExtractedData[T]:
        raise NotImplementedError()

    def _extract_online(self, uri: str) -> ExtractedData[T]:
        raise NotImplementedError()

    def _update_object_raw(self, object: E, data: T):
        raise NotImplementedError()

    def _update_hook(self, object: E, data: ExtractedData[T]):
        return None

    # defined

    def _extract_offline(self, uri: str) -> ExtractedData[T]:
        return self._extract_offline_only(uri) if self.can_extract_offline(uri) else self._extract_online(uri)

    def _extract_required(self, data: ExtractedData[T]) -> ExtractedData[T]:
        if data.has_data:
            return data
        return self._extract_online(data.object_uri)

    def _update_object(self, object: E, data: ExtractedData[T]) -> E:
        object.uri = data.object_uri
        self._update_object_raw(object, data.data)
        self._update_hook(object, data)
        object.last_updated = datetime.now()
        return object

    def update_object(self, object: E, check_cache_expired: bool = True) -> E:
        if object.was_extracted and check_cache_expired and not self._cache_expired(object.last_updated):
            return object
        data = self._extract_online(object.uri)
        logging.debug(f"Updating info for media: {data!r}")
        return self._update_object(object, data)

    def store_object(self, data: ExtractedData[T]) -> E:
        object = self._load_object(data)
        if object:
            logging.debug(f"Found object already in database: {data!r}")
            return object
        data = self._extract_required(data)
        logging.debug(f"Store info for object: {data!r}")
        object = self._create_object(data)
        return self._update_object(object, data)

    def extract_and_store(self, uri: str) -> E:
        object = self.check_uri(uri)
        if object is not None:
            return object
        return self.store_object(self._extract_offline(uri))
