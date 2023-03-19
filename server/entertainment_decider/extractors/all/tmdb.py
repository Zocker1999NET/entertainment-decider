from __future__ import annotations

from datetime import datetime
from functools import cached_property
import itertools
import math
from typing import Literal, Optional, Sequence, TypedDict

import tmdbsimple as tmdb


tmdb.API_KEY = "f090bb54758cabf231fb605d3e3e0468"


EXTRACTOR_KEY = ".extractor/org.themoviedb"
EXTRACTOR_NAME = "The Movie DB"

TMDB_DATE_FORMAT = "%Y-%m-%d"
TMDB_REGEX_URI = r"""
    (
        https?://(www\.)?themoviedb\.org
    |
        tmdb://
    )
"""


class TmdbGenreDict(TypedDict):
    id: int
    name: str


class TmdbImageDict(TypedDict):
    aspect_ratio: float
    file_path: str
    height: int
    vote_average: float
    vote_count: int
    width: int


class TmdbKeywordDict(TypedDict):
    id: int
    name: str


class TmdbExternalIdsDict(TypedDict):
    facebook_id: Optional[str]
    imdb_id: Optional[str]
    instagram_id: Optional[str]
    twitter_id: Optional[str]


class TmdbKeywordsDict(TypedDict):
    keywords: Sequence[TmdbKeywordDict]


class TmdbMovieImagesDict(TypedDict):
    backdrops: Sequence[TmdbImageDict]
    posters: Sequence[TmdbImageDict]


class TmdbMovieEntryInfoDict(TypedDict):
    adult: bool
    backdrop_path: Optional[str]
    genre_ids: Sequence[int]
    id: int
    original_language: str
    original_title: str
    overview: str
    release_date: str
    poster_path: str
    popularity: int
    title: str
    video: bool
    vote_average: float
    vote_count: int


class TmdbCollectionInfoDict(TypedDict):
    id: int
    name: str
    overview: str
    poster_path: Optional[str]
    backdrop_path: Optional[str]
    parts: Sequence[TmdbMovieEntryInfoDict]


class TmdbMovieInfoDict(TypedDict):
    external_ids: TmdbExternalIdsDict
    genres: Sequence[TmdbGenreDict]
    keywords: TmdbKeywordsDict
    id: int
    images: TmdbMovieImagesDict
    overview: Optional[str]
    release_date: Optional[str]
    runtime: Optional[int]
    status: Literal[
        "Rumored", "Planned", "In Production", "Post Production", "Released", "Canceled"
    ]
    title: str


class TmdbKeywordInfoDict(TypedDict):
    id: int
    name: str
    movies: TmdbKeywordMoviesDict


class TmdbKeywordMoviesDict(TypedDict):
    page: int
    results: Sequence[TmdbMovieEntryInfoDict]
    total_pages: int
    total_results: int


def select_best_image(images: Sequence[TmdbImageDict]) -> Optional[TmdbImageDict]:
    if len(images) <= 0:
        return None
    return max(
        images, key=lambda i: i["vote_average"] * (math.log10(i["vote_count"] + 1))
    )


class TmdbMovieEntryData:
    def __init__(self, part_dict: TmdbMovieEntryInfoDict):
        self._info = part_dict

    @cached_property
    def release_date(self) -> Optional[datetime]:
        date_str = self._info.get("release_date")
        if not date_str:
            return None
        return datetime.strptime(date_str, TMDB_DATE_FORMAT)

    @property
    def release_date_req(self) -> datetime:
        date = self.release_date
        if date is None:
            raise Exception(f"Expected release_date to be set")
        return date

    @cached_property
    def was_released(self) -> bool:
        return self.release_date is not None and self.release_date <= datetime.now()

    @cached_property
    def tmdb_custom_uri(self) -> str:
        return f"tmdb:///movie/{self.tmdb_id}"

    @cached_property
    def tmdb_id(self) -> int:
        return self._info["id"]


class TmdbCollectionData:
    @classmethod
    def from_id(cls, collection_id: int) -> TmdbCollectionData:
        return cls(tmdb.Collections(collection_id))

    def __init__(self, collection_obj: tmdb.Collections):
        self.obj = collection_obj

    @cached_property
    def _info(self) -> TmdbCollectionInfoDict:
        return self.obj.info()  # type: ignore

    @cached_property
    def description(self) -> Optional[str]:
        return self._info.get("overview")

    @cached_property
    def parts(self) -> Sequence[TmdbMovieEntryData]:
        return [TmdbMovieEntryData(part) for part in self._info["parts"]]

    @cached_property
    def release_date(self) -> Optional[datetime]:
        return min(
            (part.release_date for part in self.parts if part.release_date is not None)
        )

    @cached_property
    def title(self) -> str:
        return self._info["name"]

    @cached_property
    def tmdb_custom_uri(self) -> str:
        return f"tmdb:///collection/{self.tmdb_id}"

    @cached_property
    def tmdb_id(self) -> int:
        return self._info["id"]


class TmdbKeywordData:
    @classmethod
    def from_id(cls, keyword_id: int) -> TmdbKeywordData:
        return cls(tmdb.Keywords(keyword_id))

    def __init__(self, keyword_obj: tmdb.Keywords):
        self.obj = keyword_obj

    @cached_property
    def _info(self) -> TmdbKeywordInfoDict:
        return self.obj.info(append_to_response="movies")  # type: ignore

    @cached_property
    def description(self) -> Optional[str]:
        return None

    @cached_property
    def parts(self) -> Sequence[TmdbMovieEntryData]:
        movies_first = self._info["movies"]
        follow_pages: Sequence[TmdbKeywordMoviesDict] = [
            self.obj.movies(page=i)
            for i in range(2, movies_first["total_pages"] + 1, 1)
        ]
        all_results = itertools.chain(
            movies_first["results"],
            (part for page in follow_pages for part in page["results"]),
        )
        return [TmdbMovieEntryData(part) for part in all_results]

    @cached_property
    def release_date(self) -> Optional[datetime]:
        return min(
            (part.release_date for part in self.parts if part.release_date is not None)
        )

    @cached_property
    def title(self) -> str:
        return self._info["name"]

    @cached_property
    def tmdb_custom_uri(self) -> str:
        return f"tmdb:///keyword/{self.tmdb_id}"

    @cached_property
    def tmdb_id(self) -> int:
        return self._info["id"]


class TmdbMovieData:
    @classmethod
    def from_id(cls, movie_id: int) -> TmdbMovieData:
        return cls(tmdb.Movies(movie_id))

    def __init__(self, movie_obj: tmdb.Movies):
        self.obj = movie_obj

    @cached_property
    def _info(self) -> TmdbMovieInfoDict:
        return self.obj.info(append_to_response="external_ids,images,keywords")  # type: ignore

    @cached_property
    def description(self) -> Optional[str]:
        return self._info.get("overview")

    @cached_property
    def genres(self) -> Sequence[str]:
        return [genre["name"] for genre in self._info["genres"]]

    @cached_property
    def imdb_id(self) -> Optional[str]:
        return self._info["external_ids"].get("imdb_id")

    @cached_property
    def imdb_custom_uri(self) -> Optional[str]:
        if self.imdb_id is None:
            return None
        return f"imdb:///{self.imdb_id}"

    @cached_property
    def length(self) -> Optional[int]:
        "Length of the movie in seconds"
        runtime_min = self._info.get("runtime")
        if runtime_min is None:
            return None
        return runtime_min * 60

    @cached_property
    def release_date(self) -> Optional[datetime]:
        date_str = self._info.get("release_date")
        if not date_str:
            return None
        return datetime.strptime(date_str, TMDB_DATE_FORMAT)

    @cached_property
    def was_released(self) -> bool:
        return (
            self.release_date is not None
            and self.release_date <= datetime.now()
            and self.length is not None
            and self.length > 0
        )

    @cached_property
    def thumbnail_uri(self) -> Optional[str]:
        all_images = self._info["images"]
        image = select_best_image(all_images["backdrops"]) or select_best_image(
            all_images["posters"]
        )
        return (
            f"https://image.tmdb.org/t/p/original{image['file_path']}"
            if image
            else None
        )

    @cached_property
    def title(self) -> str:
        return self._info["title"]

    @cached_property
    def tmdb_custom_uri(self) -> str:
        return f"tmdb:///movie/{self.tmdb_id}"

    @cached_property
    def tmdb_short_uri(self) -> str:
        return f"https://www.themoviedb.org/movie/{self.tmdb_id}"

    @cached_property
    def tmdb_id(self) -> int:
        return self._info["id"]
