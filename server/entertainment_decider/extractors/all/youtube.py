from __future__ import annotations

from typing import (
    List,
    NewType,
    TypedDict,
)


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
