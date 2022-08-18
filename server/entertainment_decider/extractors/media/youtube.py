from __future__ import annotations

from datetime import datetime
import logging
import re
from typing import List, Optional, TypedDict

from youtubesearchpython import ResultMode, Video

from ...models import (
    MediaElement,
    MediaThumbnail,
    thumbnail_sort_key,
)
from ..generic import (
    AuthorExtractedData,
    ExtractedData,
    SuitableLevel,
)
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

    __uri_regex = re.compile(
        r"""^
        https?://(
            (www\.)?youtube(-nocookie)?\.com/(
                watch\?v=
                |
                embed/
                |
                shorts/
            )|
            youtu\.be/
        )(?P<id>[^/&?]+)
    $""",
        re.VERBOSE,
    )

    def __init__(self):
        super().__init__("youtube")

    def uri_suitable(self, uri: str) -> SuitableLevel:
        return SuitableLevel.always_or_no(self.__uri_regex.match(uri))

    def _get_author_data(self, data: YoutubeVideoData) -> Optional[AuthorExtractedData]:
        return AuthorExtractedData(
            object_uri=data["channel"]["link"],
            extractor_name=self.name,
            object_key=f"author:{data['channel']['id']}",
            author_name=data["channel"]["name"],
        )

    def _extract_online(self, uri: str) -> ExtractedData[YoutubeVideoData]:
        logging.info(f"Request info using youtube_search_python for {uri!r}")
        uri_match = self.__uri_regex.match(uri)
        if not uri_match:
            raise Exception(f"URI not suitable: {uri!r}")
        id = uri_match.group("id")
        vid_data: YoutubeVideoData = Video.getInfo(
            videoLink=f"https://www.youtube.com/watch?v={id}",
            mode=ResultMode.dict,
        )
        return ExtractedData[YoutubeVideoData](
            object_uri=uri,
            extractor_name=self.name,
            object_key=vid_data["id"],
            data=vid_data,
        )

    def _update_object_raw(self, object: MediaElement, data: YoutubeVideoData):
        object.title = f"{data['title']} - {data['channel']['name']}"
        object.description = data.get("description")
        if data.get("thumbnails"):
            best_thumb = min(
                data["thumbnails"],
                key=lambda thumb: thumbnail_sort_key(thumb["width"], thumb["height"]),
            )
            object.thumbnail = MediaThumbnail.from_uri(best_thumb["url"])
        object.release_date = datetime.strptime(
            data.get("uploadDate") or data["publishDate"], "%Y-%m-%d"
        )
        object.length = int(data["duration"]["secondsText"])
        object.uri = f"https://www.youtube.com/watch?v={data['id']}"
        object.add_uris(
            (
                f"https://youtu.be/{data['id']}",
                f"https://youtube.com/watch?v={data['id']}",
            )
        )
