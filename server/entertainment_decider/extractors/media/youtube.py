from __future__ import annotations

from datetime import datetime
import logging
import re
from typing import Optional

from yt_dlp import YoutubeDL  # type: ignore

from ...extras import (
    multi_strptime,
)
from ...models import (
    MediaElement,
    MediaThumbnail,
    thumbnail_sort_key,
)
from ..all.youtube import (
    EXTRACTOR_KEY,
    EXTRACTOR_NAME,
    YoutubeVideoData,
    get_video_tags,
)
from ..generic import (
    AuthorExtractedData,
    ChangedReport,
    ExtractedDataOnline,
    ExtractionError,
    SuitableLevel,
)
from .base import MediaExtractor


YTDLP_OPTS = {
    "check_formats": False,
}


class YoutubeMediaExtractor(MediaExtractor[YoutubeVideoData]):
    __uri_regex = re.compile(
        r"""^
        https?://(
            ((
                www
                |
                m
            )\.)?youtube(-nocookie)?\.com/(
                watch\?v=
                |
                embed/
                |
                shorts/
            )|
            youtu\.be/
        )(?P<id>[^/&?]+)
        /?(\#.*)?
    $""",
        re.VERBOSE,
    )

    def __init__(self) -> None:
        super().__init__(
            name="youtube",
            key=EXTRACTOR_KEY,
            long_name=EXTRACTOR_NAME,
        )

    def uri_suitable(self, uri: str) -> SuitableLevel:
        return SuitableLevel.always_or_no(self.__uri_regex.match(uri) is not None)

    def _get_author_data(self, data: YoutubeVideoData) -> Optional[AuthorExtractedData]:
        return AuthorExtractedData(
            object_uri=data["channel"]["link"],
            extractor_name=self.name,
            object_key=f"author:{data['channel']['id']}",
            author_name=data["channel"]["name"],
        )

    def _extract_online(self, uri: str) -> ExtractedDataOnline[YoutubeVideoData]:
        logging.info(f"Request info using youtube_search_python for {uri!r}")
        uri_match = self.__uri_regex.match(uri)
        if not uri_match:
            raise Exception(f"URI not suitable: {uri!r}")
        id = uri_match.group("id")
        try:
            with YoutubeDL(YTDLP_OPTS) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={id}",
                    download=False,
                )
                vid_data = self.__adapt_ytdlp_format(ydl.sanitize_info(info))
        except Exception as e:
            raise ExtractionError() from e
        if vid_data["isLiveNow"]:
            raise ExtractionError("Video is live, so pass extraction")
        return ExtractedDataOnline[YoutubeVideoData](
            object_uri=uri,
            extractor_name=self.name,
            object_key=vid_data["id"],
            data=vid_data,
        )

    def _update_object_raw(
        self,
        object: MediaElement,
        data: YoutubeVideoData,
    ) -> ChangedReport:
        object.title = f"{data['title']} - {data['channel']['name']}"
        object.description = data.get("description")
        if data.get("thumbnails"):
            best_thumb = min(
                data["thumbnails"],
                key=lambda thumb: thumbnail_sort_key(thumb["width"], thumb["height"]),
            )
            object.thumbnail = MediaThumbnail.from_uri(best_thumb["url"])
        object.release_date = multi_strptime(
            data.get("uploadDate") or data["publishDate"],
            "%Y-%m-%dT%H:%M:%S%:z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d",
            "%Y%m%d",
        )
        object.length = int(data["duration"]["secondsText"])
        for tag in get_video_tags(data):
            object.tag_list.add(tag)
        object.primary_uri = f"https://www.youtube.com/watch?v={data['id']}"
        object.add_uris(
            (
                f"https://youtu.be/{data['id']}",
                f"https://youtube.com/watch?v={data['id']}",
            )
        )
        return ChangedReport.ChangedSome  # TODO improve

    @staticmethod
    def __adapt_ytdlp_format(ytdlp_info) -> YoutubeVideoData:
        return {
            "id": ytdlp_info["id"],
            "title": ytdlp_info["title"],
            # TODO keep as int
            "duration": {"secondsText": str(ytdlp_info["duration"])},
            "viewCount": {"text": str(ytdlp_info["view_count"])},
            # only supply best thumbnail available
            "thumbnails": [
                {
                    "url": ytdlp_info["thumbnail"],
                    "height": 1,
                    "width": 1,
                }
            ],
            "description": ytdlp_info["description"],
            "channel": {
                "name": ytdlp_info["channel"],
                "id": ytdlp_info["channel_id"],
                "link": ytdlp_info["channel_url"],
            },
            "allowRatings": False,  # faked, unknown, unimportant, TODO remove
            "averageRating": ytdlp_info["average_rating"],
            "keywords": ytdlp_info["tags"],
            "isLiveContent": ytdlp_info["was_live"],
            "uploadDate": ytdlp_info["upload_date"],
            "isLiveNow": ytdlp_info["is_live"],
            "link": ytdlp_info["webpage_url"],
        }
