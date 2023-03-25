from __future__ import annotations

import re
from typing import Optional

from ...models import (
    MediaElement,
    MediaThumbnail,
)
from ..all.tmdb import (
    EXTRACTOR_KEY,
    EXTRACTOR_NAME,
    TMDB_REGEX_URI,
    TmdbMovieData,
)
from ..generic import (
    ChangedReport,
    ExtractedDataOnline,
    ExtractedDataOffline,
    ExtractionError,
    SuitableLevel,
)
from .base import MediaExtractor


class TmdbMovieMediaExtractor(MediaExtractor[TmdbMovieData]):
    SUPPORTED_PATTERN = re.compile(
        rf"""^
            {TMDB_REGEX_URI}
            /movie/
            (?P<movie_id>\d+)
            (?!\d)
            (-[^/]+)?
            /?
        $""",
        re.VERBOSE,
    )

    @classmethod
    def __get_movie_id(cls, uri: str) -> Optional[int]:
        m = cls.SUPPORTED_PATTERN.search(uri)
        return int(m.group("movie_id")) if m else None

    def __init__(self) -> None:
        super().__init__(
            key=EXTRACTOR_KEY,
            long_name=EXTRACTOR_NAME,
            name="tmdb",
        )

    def uri_suitable(self, uri: str) -> SuitableLevel:
        movie_id = self.__get_movie_id(uri)
        return SuitableLevel.always_or_no(bool(movie_id))

    def can_extract_offline(self, uri: str) -> bool:
        return True

    def _extract_offline(self, uri: str) -> ExtractedDataOffline[TmdbMovieData]:
        movie_id = self.__get_movie_id(uri)
        return ExtractedDataOffline[TmdbMovieData](
            extractor_name=self.name,
            object_key=str(movie_id),
            object_uri=uri,
        )

    def _extract_online(self, uri: str) -> ExtractedDataOnline[TmdbMovieData]:
        movie_id = self.__get_movie_id(uri)
        data = TmdbMovieData.from_id(movie_id)
        return ExtractedDataOnline[TmdbMovieData](
            extractor_name=self.name,
            object_key=f"movie:{movie_id}",
            object_uri=uri,
            data=data,
        )

    def _update_object_raw(
        self,
        object: MediaElement,
        data: TmdbMovieData,
    ) -> ChangedReport:
        # sanity check
        if not data.was_released:
            raise ExtractionError(
                f"Could not extract {object.uri!r} because of missing data probably due to not being released yet"
            )
        # extract data
        object.title = data.title
        object.description = data.description or ""
        object.thumbnail = (
            MediaThumbnail.from_uri(data.thumbnail_uri) if data.thumbnail_uri else None
        )
        object.release_date = data.release_date
        object.length = data.length
        object.add_uris(
            (
                data.imdb_custom_uri,
                data.tmdb_custom_uri,
                data.tmdb_short_uri,
            )
        )
        for tag in data.get_tags(data):
            object.tag_list.add(tag)
        return ChangedReport.ChangedSome  # TODO improve
