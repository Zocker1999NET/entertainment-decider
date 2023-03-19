from __future__ import annotations

from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Literal,
    NewType,
    Optional,
    TypeVar,
    TypedDict,
    Union,
)

from ...models import Tag, TagKey
from ...models.localization import (
    get_country_tag as get_country_tag_by_code,
    get_language_tag,
)


EXTRACTOR_KEY = ".extractor/com.tvmaze"
EXTRACTOR_NAME = "TVMaze"


GenreName = NewType("GenreName", str)
NetworkId = NewType("NetworkId", int)
ShowTypeName = NewType("ShowTypeName", str)
WebChannelId = NewType("WebChannelId", int)


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
    id: NetworkId
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
    network: Optional[TvmazeNetwork]
    webChannel: Optional[TvmazeWebChannel]
    image: TvmazeImage
    summary: str


class TvmazeShow(TypedDict):
    id: int
    url: str
    name: str
    type: ShowTypeName
    language: str
    genres: List[GenreName]
    status: str
    runtime: int
    averageRuntime: int
    premiered: str
    ended: str
    officialSite: str
    schedule: TvmazeSchedule
    rating: TvmazeRating
    weight: int
    network: Optional[TvmazeNetwork]
    webChannel: Optional[TvmazeWebChannel]
    dvdCountry: Optional[TvmazeCountry]
    externals: TvmazeExternalIds
    image: TvmazeImage
    summary: str
    updated: int


class TvmazeShowEmbedded(TvmazeShow):
    _embedded: TvmazeEmbeddings


class TvmazeWebChannel(TypedDict):
    id: WebChannelId
    name: str
    country: TvmazeCountry
    dvdCountry: Optional[TvmazeCountry]


T = TypeVar("T", bound=Dict)


def add_embedding(object: T, key: str, value: Any, parent_key: str = "_embedded") -> T:
    if parent_key not in object:
        object[parent_key] = {}
    object[parent_key][key] = value
    return object


# Tag related stuff


GENRE_PREFIX = f"{EXTRACTOR_KEY}/genre"
NETWORK_PREFIX = f"{EXTRACTOR_KEY}/network"
SHOW_TYPE_PREFIX = f"{EXTRACTOR_KEY}/show_type"
WEB_CHANNEL_PREFIX = f"{EXTRACTOR_KEY}/web_channel"


## multi tag generators


def get_show_tags(show: TvmazeShow) -> Iterable[Tag]:
    general_video_tag = TagKey.get_tag(".kind/video")
    if general_video_tag is not None:
        yield general_video_tag
    yield get_show_type_tag(show["type"])
    yield get_language_tag(show["language"])
    for genre in show["genres"]:
        yield get_genre_tag(genre)
    network = show["network"]
    if network is not None:
        yield from get_all_network_tags(network)
    web_channel = show["webChannel"]
    if web_channel is not None:
        yield from get_all_web_channel_tags(web_channel)


def get_all_network_tags(network: TvmazeNetwork) -> Iterable[Tag]:
    country = network["country"]
    if country is not None:
        yield get_country_tag(country)
    yield get_network_tag(network)


def get_all_web_channel_tags(web_channel: TvmazeWebChannel) -> Iterable[Tag]:
    country = web_channel["country"]
    if country is not None:
        yield get_country_tag(country)
    yield get_web_channel_tag(web_channel)


## single tag generators


def get_country_tag(country: TvmazeCountry) -> Tag:
    return get_country_tag_by_code(country["code"])


def get_genre_tag(genre_name: GenreName) -> Tag:
    return get_any_tag(
        category_key=GENRE_PREFIX,
        category_name="Genre",
        element_key=genre_name.lower(),
        element_name=genre_name,
    )


def get_network_tag(network: TvmazeNetwork) -> Tag:
    return get_any_tag(
        category_key=NETWORK_PREFIX,
        category_name="Network",
        element_key=str(network["id"]),
        element_name=network["name"],
    )


def get_show_type_tag(show_type_name: ShowTypeName) -> Tag:
    return get_any_tag(
        category_key=SHOW_TYPE_PREFIX,
        category_name="Show Type",
        element_key=show_type_name.lower(),
        element_name=show_type_name,
    )


def get_web_channel_tag(web_channel: TvmazeWebChannel) -> Tag:
    return get_any_tag(
        category_key=WEB_CHANNEL_PREFIX,
        category_name="Web Channel",
        element_key=str(web_channel["id"]),
        element_name=web_channel["name"],
    )


def get_any_tag(
    *,
    category_key: str,
    category_name: str,
    element_key: str,
    element_name: str,
) -> Tag:
    TagKey.get_or_create_tag(
        tag_key=category_key,
        title=f"[{EXTRACTOR_NAME}] {category_name}",
        use_for_preferences=False,
    )
    return TagKey.get_or_create_tag(
        tag_key=f"{category_key}/{element_key}",
        title=f"[{EXTRACTOR_NAME}] [{category_name}] {element_name}",
        use_for_preferences=True,
        super_tags=[
            category_key,
        ],
    )
