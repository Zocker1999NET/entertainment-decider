from __future__ import annotations

from typing import (
    Iterable,
    List,
    NewType,
    TypedDict,
)

from ...models import Tag, TagKey


EXTRACTOR_KEY = ".extractor/com.youtube"

KEYWORD_PREFIX = f"{EXTRACTOR_KEY}/keyword"


Keyword = NewType("Keyword", str)


class YoutubeDuration(TypedDict):
    secondsText: str


class YoutubeViewCount(TypedDict):
    text: str


class YoutubeThumbnailData(TypedDict):
    url: str
    width: int
    height: int


class YoutubeChannelData(TypedDict):
    name: str
    id: str
    link: str


class YoutubeVideoData(TypedDict):
    id: str
    title: str
    duration: YoutubeDuration
    viewCount: YoutubeViewCount
    thumbnails: List[YoutubeThumbnailData]
    description: str
    channel: YoutubeChannelData
    allowRatings: bool
    averageRating: float
    keywords: List[Keyword]
    isLiveContent: bool
    publishDate: str
    uploadDate: str
    isLiveNow: bool
    link: str


def get_video_tags(video: YoutubeVideoData) -> Iterable[Tag]:
    keyword_list = video.get("keywords")
    if keyword_list is not None:
        for keyword in keyword_list:
            yield get_keyword_tag(keyword)


def get_keyword_tag(keyword: Keyword) -> Tag:
    TagKey.get_or_create_tag(
        tag_key=KEYWORD_PREFIX,
        title=f"[{EXTRACTOR_NAME}] Keyword",
        use_for_preferences=False,
    )
    return TagKey.get_or_create_tag(
        tag_key=f"{KEYWORD_PREFIX}/{keyword.lower()}",
        title=f"[{EXTRACTOR_NAME}] [Keyword] {keyword}",
        use_for_preferences=True,
        super_tags=[
            KEYWORD_PREFIX,
        ],
    )
