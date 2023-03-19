from __future__ import annotations

from typing import (
    Any,
    Dict,
    List,
    Literal,
    Optional,
    TypeVar,
    TypedDict,
    Union,
)


Weekdays = Union[
    Literal["Monday"],
    Literal["Tuesday"],
    Literal["Wednesday"],
    Literal["Thursday"],
    Literal["Friday"],
    Literal["Saturday"],
    Literal["Sunday"],
]


class TvmazeCountry(TypedDict):
    name: str
    code: str
    timezone: str


class TvmazeEmbeddings(TypedDict, total=False):
    show: TvmazeShow
    seasons: List[TvmazeSeason]
    episodes: List[TvmazeEpisode]


class TvmazeEpisode(TypedDict):
    id: int
    url: str
    name: str
    season: int
    number: int
    type: str
    airdate: str
    airtime: str
    airstamp: str
    runtime: int
    rating: TvmazeRating
    image: TvmazeImage
    summary: str


class TvmazeEpisodeEmbedded(TvmazeEpisode):
    _embedded: TvmazeEmbeddings


class TvmazeExternalIds(TypedDict):
    tvrage: Optional[int]
    thetvdb: Optional[int]
    imdb: Optional[str]


class TvmazeImage(TypedDict):
    medium: Optional[str]
    original: str


def select_best_image(*image_list: TvmazeImage) -> Optional[str]:
    for image in image_list:
        if image is not None:
            found = image.get("original") or image.get("medium")
            if found:
                return found
    return None


class TvmazeNetwork(TypedDict):
    id: int
    name: str
    country: TvmazeCountry
    webChannel: Optional[Any]
    dvdCountry: Optional[TvmazeCountry]


class TvmazeRating(TypedDict):
    average: int


class TvmazeSchedule(TypedDict):
    time: str
    days: List[Weekdays]


class TvmazeSeason(TypedDict):
    id: int
    url: str
    number: int
    name: str
    episodeOrder: int
    premiereDate: str
    endDate: str
    network: TvmazeNetwork
    webChannel: Optional[Any]
    image: TvmazeImage
    summary: str


class TvmazeShow(TypedDict):
    id: int
    url: str
    name: str
    type: str
    language: str
    genres: List[str]
    status: str
    runtime: int
    averageRuntime: int
    premiered: str
    ended: str
    officialSite: str
    schedule: TvmazeSchedule
    rating: TvmazeRating
    weight: int
    externals: TvmazeExternalIds
    image: TvmazeImage
    summary: str
    updated: int


class TvmazeShowEmbedded(TvmazeShow):
    _embedded: TvmazeEmbeddings


T = TypeVar("T", bound=Dict)


def add_embedding(object: T, key: str, value: Any, parent_key: str = "_embedded") -> T:
    if parent_key not in object:
        object[parent_key] = {}
    object[parent_key][key] = value
    return object
