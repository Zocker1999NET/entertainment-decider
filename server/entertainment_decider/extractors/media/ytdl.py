from __future__ import annotations

from datetime import datetime
import logging
import re
from typing import Dict, Optional


from ...models import (
    MediaElement,
    MediaThumbnail,
    thumbnail_sort_key,
)
from ..all.ytdl import get_video_info, YtdlErrorException
from ..generic import AuthorExtractedData, ExtractedData, ExtractionError, SuitableLevel
from .base import MediaExtractor


class YtdlMediaExtractor(MediaExtractor[Dict]):

    SUPPORTED_PATTERN = re.compile(
        r"""^
        https?://
    """,
        re.VERBOSE,
    )

    def __init__(self):
        super().__init__("ytdl")

    def uri_suitable(self, uri: str) -> SuitableLevel:
        return SuitableLevel.fallback_or_no(bool(self.SUPPORTED_PATTERN.search(uri)))

    def _get_author_data(self, data: Dict) -> Optional[AuthorExtractedData]:
        video_extractor_key = data.get("extractor_key") or data["ie_key"]
        author_key = data.get("channel_id") or data.get("uploader_id")
        author_name = (
            data.get("channel") or data.get("uploader") or data.get("uploader_id")
        )
        return AuthorExtractedData(
            object_uri=data.get("channel_url") or data.get("uploader_url"),
            extractor_name=self.name,
            object_key=f"author:{video_extractor_key}:{author_key}"
            if author_key
            else None,
            author_name=f"[{video_extractor_key.lower()}] {author_name}"
            if author_name
            else None,
        )

    def _extract_online(self, uri: str) -> ExtractedData[Dict]:
        logging.info(f"Request info using youtube-dl for {uri!r}")
        try:
            vid_data = get_video_info(uri)
        except YtdlErrorException as e:
            raise ExtractionError from e
        if vid_data.get("is_live", False):
            raise ExtractionError("Video is live, so pass extraction")
        ytdl_extractor_key = vid_data.get("extractor_key") or vid_data["ie_key"]
        ytdl_video_id = vid_data["id"]
        return ExtractedData[Dict](
            object_uri=uri,
            extractor_name=self.name,
            object_key=f"{ytdl_extractor_key}:{ytdl_video_id}",
            data=vid_data,
        )

    def _update_object_raw(self, object: MediaElement, data: Dict) -> str:
        object.title = (
            f"{data['title']} - {data['uploader']}"
            if "uploader" in data
            else data["title"]
        )
        object.description = data.get("description")
        thumb_list = (
            [
                thumb
                for thumb in data["thumbnails"]
                if "width" in thumb and "height" in thumb
            ]
            if "thumbnails" in data
            else None
        )
        if thumb_list:
            best_thumb = min(
                thumb_list,
                key=lambda thumb: thumbnail_sort_key(thumb["width"], thumb["height"]),
            )
            object.thumbnail = MediaThumbnail.from_uri(best_thumb["url"])
        elif data.get("thumbnail"):
            object.thumbnail = MediaThumbnail.from_uri(data["thumbnail"])
        object.release_date = datetime.strptime(data["upload_date"], "%Y%m%d")
        object.length = int(data["duration"])
