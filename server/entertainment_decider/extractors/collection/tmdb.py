from __future__ import annotations

from datetime import datetime
import re
from typing import ClassVar, Iterable, List, Optional, TypeVar

from pony import orm

from ...models import MediaCollection
from ..all.tmdb import (
    TmdbCollectionData,
    TMDB_REGEX_URI,
    TmdbKeywordData,
)
from ..generic import (
    ChangedReport,
    ExtractedDataOnline,
    ExtractedDataOffline,
    SuitableLevel,
)
from .base import CollectionExtractor


T = TypeVar("T")


class TmdbBaseExtractor(CollectionExtractor[T]):
    TMDB_CLASS: ClassVar[str]

    SUPPORTED_PATTERN = re.compile(
        rf"""^
        {TMDB_REGEX_URI}
        /(?P<class>[a-z]+)/
        (?P<id>\d+)
        (?!\d)
        (-[^/]+)?
        (/movie)?
        /?
    $""",
        re.VERBOSE,
    )

    @classmethod
    def _get_id(cls, uri: str) -> Optional[int]:
        m = cls.SUPPORTED_PATTERN.search(uri)
        return int(m.group("id")) if m and m.group("class") == cls.TMDB_CLASS else None

    def __init__(self) -> None:
        super().__init__("tmdb")

    def uri_suitable(self, uri: str) -> SuitableLevel:
        id = self._get_id(uri)
        return SuitableLevel.always_or_no(bool(id))

    def can_extract_offline(self, uri: str) -> bool:
        return True

    def _cache_expired(self, object: MediaCollection) -> bool:
        last_release_date = orm.max(l.element.release_date for l in object.media_links)
        return (datetime.now() - object.last_updated) > (
            self._calculate_wait_hours(last_release_date) * 7 * 24
        )

    def _extract_offline(self, uri: str) -> ExtractedDataOffline[T]:
        id = self._get_id(uri)
        return ExtractedDataOffline[T](
            extractor_name=self.name,
            object_key=f"{self.TMDB_CLASS}:{id}",
            object_uri=uri,
        )


class TmdbCollectionExtractor(TmdbBaseExtractor[TmdbCollectionData]):
    TMDB_CLASS = "collection"

    def _extract_online(self, uri: str) -> ExtractedDataOnline[TmdbCollectionData]:
        id = self._get_id(uri)
        data = TmdbCollectionData.from_id(id)
        return ExtractedDataOnline(
            extractor_name=self.name,
            object_key=f"{self.TMDB_CLASS}:{id}",
            object_uri=uri,
            data=data,
        )

    def _update_object_raw(
        self,
        object: MediaCollection,
        data: TmdbCollectionData,
    ) -> ChangedReport:
        # extract data
        object.title = f"[tmdb] [{self.TMDB_CLASS}] {data.title}"
        object.description = data.description or ""
        object.release_date = data.release_date
        object.set_watch_in_order_auto(True)
        object.add_uris((data.tmdb_custom_uri,))
        parts = sorted(
            (part for part in data.parts if part.was_released),
            key=lambda p: p.release_date,
        )
        for index, movie in enumerate(parts):
            element = self._add_episode(
                collection=object,
                uri=movie.tmdb_custom_uri,
                episode=index + 1,
            )
            if element:
                orm.commit()
        return ChangedReport.ChangedSome  # TODO improve


class TmdbKeywordExtractor(TmdbBaseExtractor[TmdbKeywordData]):
    TMDB_CLASS = "keyword"

    def _extract_online(self, uri: str) -> ExtractedDataOnline[TmdbKeywordData]:
        id = self._get_id(uri)
        data = TmdbKeywordData.from_id(id)
        return ExtractedDataOnline(
            extractor_name=self.name,
            object_key=f"{self.TMDB_CLASS}:{id}",
            object_uri=uri,
            data=data,
        )

    def _update_object_raw(
        self,
        object: MediaCollection,
        data: TmdbKeywordData,
    ) -> ChangedReport:
        # extract data
        object.title = f"[tmdb] [{self.TMDB_CLASS}] {data.title}"
        object.release_date = data.release_date
        object.set_watch_in_order_auto(True)
        object.add_uris((data.tmdb_custom_uri,))
        parts = sorted(
            (part for part in data.parts if part.was_released),
            key=lambda p: p.release_date,
        )
        for index, movie in enumerate(parts):
            element = self._add_episode(
                collection=object,
                uri=movie.tmdb_custom_uri,
                episode=index + 1,
            )
            if element:
                orm.commit()
        return ChangedReport.ChangedSome  # TODO improve
