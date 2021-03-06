from __future__ import annotations

from datetime import datetime
import logging
import re
from typing import List, Optional, TypedDict

from youtubesearchpython import ResultMode, Video

from ...models import MediaElement
from ..generic import AuthorExtractedData, ExtractedData, SuitableLevel
from .base import MediaExtractor


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
    keywords: List[str]
    isLiveContent: bool
    publishDate: str
    uploadDate: str
    isLiveNow: bool
    link: str


class YoutubeMediaExtractor(MediaExtractor[YoutubeVideoData]):

    __uri_regex = re.compile(r"^https?://((www\.)?youtube\.com/watch\?v=|youtu\.be/)(?P<id>[^/&?]+)")

    def __init__(self):
        super().__init__("ytdl")

    def uri_suitable(self, uri: str) -> SuitableLevel:
        return SuitableLevel.always_or_no(self.__uri_regex.match(uri))

    def _get_author_data(self, data: YoutubeVideoData) -> Optional[AuthorExtractedData]:
        return AuthorExtractedData(
            object_uri = data["channel"]["link"],
            extractor_name = self.name,
            object_key = f"author:{data['channel']['id']}",
            author_name = data["channel"]["name"]
        )

    def _extract_online(self, uri: str) -> ExtractedData[YoutubeVideoData]:
        logging.info(f"Request info using youtube_search_python for {uri!r}")
        vid_data: YoutubeVideoData = Video.getInfo(
            videoLink = uri,
            mode = ResultMode.dict,
        )
        return ExtractedData[YoutubeVideoData](
            object_uri=uri,
            extractor_name=self.name,
            object_key=vid_data["id"],
            data=vid_data,
        )

    def _update_object_raw(self, object: MediaElement, data: YoutubeVideoData):
        object.title = f"{data['title']} - {data['channel']['name']}"
        object.release_date = datetime.strptime(data.get("uploadDate") or data["publishDate"], "%Y-%m-%d")
        object.length = int(data["duration"]["secondsText"])
