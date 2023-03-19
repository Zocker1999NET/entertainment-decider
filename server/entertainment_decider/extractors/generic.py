from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime
import enum
from enum import Enum
import logging
from typing import Generic, Optional, TypeVar

from ..models import (
    MediaCollection,
    MediaElement,
    Tag,
    TagKey,
)


T = TypeVar("T")


class ChangedReport(Enum):
    StayedSame = enum.auto()
    """Declares that the action did not change anything.

    This requires that really nothing changed. If unsure, use ChangedSome.
    """
    ChangedSome = enum.auto()
    """Declares that something (might) have changed.

    It is not required that something really changed,
    this could also mean that there is currently no better way to determine if something really changed.
    """

    @property
    def may_has_changed(self) -> bool:
        return self != self.StayedSame


class SuitableLevel(Enum):
    NO = (False, False)
    FALLBACK = (True, False)
    ALWAYS = (True, True)

    @property
    def can_accept(self) -> bool:
        return self.value[0]

    @property
    def accept_immediately(self) -> bool:
        return self.value[1]

    @staticmethod
    def always_or_no(value: bool) -> SuitableLevel:
        return SuitableLevel.ALWAYS if value else SuitableLevel.NO

    @staticmethod
    def always_or_fallback(value: bool) -> SuitableLevel:
        return SuitableLevel.ALWAYS if value else SuitableLevel.FALLBACK

    @staticmethod
    def fallback_or_no(value: bool) -> SuitableLevel:
        return SuitableLevel.FALLBACK if value else SuitableLevel.NO


class ExtractionError(Exception):
    pass


@dataclass
class ExtractedDataLight:
    object_uri: str
    extractor_name: str
    object_key: str

    def create_media(self) -> MediaElement:
        return MediaElement(
            uri=self.object_uri,
            extractor_name=self.extractor_name,
            extractor_key=self.object_key,
        )

    def create_collection(self) -> MediaCollection:
        return MediaCollection(
            uri=self.object_uri,
            extractor_name=self.extractor_name,
            extractor_key=self.object_key,
        )

    def load_media(self) -> Optional[MediaElement]:
        return MediaElement.get(
            extractor_name=self.extractor_name,
            extractor_key=self.object_key,
        )

    def load_collection(self) -> Optional[MediaCollection]:
        return MediaCollection.get(
            extractor_name=self.extractor_name,
            extractor_key=self.object_key,
        )


@dataclass
class ExtractedDataOffline(ExtractedDataLight, Generic[T]):
    data: Optional[T] = dataclasses.field(default=None, repr=False, compare=False)

    @property
    def has_data(self) -> bool:
        return self.data is not None

    @property
    def online_type(self) -> ExtractedDataOnline[T]:
        if self.data is None:
            raise Exception("Explicit type requires data to be set")
        return ExtractedDataOnline[T](
            object_uri=self.object_uri,
            extractor_name=self.extractor_name,
            object_key=self.object_key,
            data=self.data,
        )


@dataclass
class ExtractedDataOnline(ExtractedDataOffline[T]):
    data: T = dataclasses.field(repr=False, compare=False)

    @property
    def has_data(self) -> bool:
        return True

    @property
    def online_type(self) -> ExtractedDataOnline[T]:
        return self


@dataclass
class AuthorExtractedData(ExtractedDataLight):
    author_name: str

    @property
    def is_valid(self) -> bool:
        return len(list(v for _, v in self.__dict__.items() if v is None)) <= 0


E = TypeVar("E", MediaElement, MediaCollection)


class GeneralExtractor(Generic[E, T]):
    name: str
    """legacy name for database entries"""
    long_name: str
    """(long) name for human readable titles / descriptions"""
    key: str
    """key for tag key (prefixes) and further database usage, replaces name"""

    def __init__(
        self,
        *,
        key: str,
        long_name: str,
        name: str,
    ):
        self.key = key
        self.long_name = long_name
        self.name = name

    # abstract (for media & collection base classes)

    @staticmethod
    def check_uri(uri: str) -> Optional[E]:
        raise NotImplementedError()

    def _create_object(self, data: ExtractedDataOffline[T]) -> E:
        raise NotImplementedError()

    def _load_object(self, data: ExtractedDataOffline[T]) -> Optional[E]:
        raise NotImplementedError()

    # abstract (for specific extractor classes)

    def uri_suitable(self, uri: str) -> SuitableLevel:
        raise NotImplementedError()

    def can_extract_offline(self, uri: str) -> bool:
        return False

    def _cache_expired(self, object: E) -> bool:
        return False

    def _extract_offline_only(self, uri: str) -> ExtractedDataOffline[T]:
        raise NotImplementedError()

    def _extract_online(self, uri: str) -> ExtractedDataOnline[T]:
        raise NotImplementedError()

    def _update_object_raw(self, object: E, data: T) -> ChangedReport:
        raise NotImplementedError()

    def _update_hook(self, object: E, data: ExtractedDataOnline[T]) -> None:
        return None

    # defined

    def _extract_offline(self, uri: str) -> ExtractedDataOffline[T]:
        return (
            self._extract_offline_only(uri)
            if self.can_extract_offline(uri)
            else self._extract_online(uri)
        )

    def _extract_required(
        self, data: ExtractedDataOffline[T]
    ) -> ExtractedDataOnline[T]:
        if data.has_data:
            return data.online_type
        return self._extract_online(data.object_uri)

    def _update_object(self, object: E, data: ExtractedDataOnline[T]) -> ChangedReport:
        object.uri = data.object_uri
        object.tag_list.add(self._get_extractor_tag())
        self._update_object_raw(object, data.data)
        self._update_hook(object, data)
        object.last_updated = datetime.now()
        return ChangedReport.ChangedSome  # TODO improve

    def update_object(
        self,
        object: E,
        check_cache_expired: bool = True,
    ) -> ChangedReport:
        if (
            object.was_extracted
            and check_cache_expired
            and not self._cache_expired(object)
        ):
            logging.debug(
                f"Skip info for element as already extracted and cache valid: {object.title!r}"
            )
            return ChangedReport.StayedSame
        data = self._extract_online(object.uri)
        logging.debug(f"Updating info for media: {data!r}")
        return self._update_object(object, data)

    def inject_object(self, data: ExtractedDataOnline[T]) -> E:
        object = self._load_object(data)
        data = self._extract_required(data)
        if object is None:
            logging.debug(f"Store info for object: {data!r}")
            object = self._create_object(data)
        self._update_object(object, data)
        return object

    def store_object(self, data: ExtractedDataOffline[T]) -> E:
        object = self._load_object(data)
        if object is not None:
            logging.debug(f"Found object already in database: {data!r}")
            return object
        full_data = self._extract_required(data)
        logging.debug(f"Store info for object: {full_data!r}")
        object = self._create_object(full_data)
        self._update_object(object, full_data)
        return object

    def extract_and_store(self, uri: str) -> E:
        object = self.check_uri(uri)
        if object is not None:
            return object
        return self.store_object(self._extract_offline(uri))

    def _get_extractor_tag(self) -> Tag:
        return TagKey.get_or_create_tag(
            tag_key=self.key,
            title=f"[Extractor] {self.long_name}",
            use_for_preferences=True,
        )
