from __future__ import annotations

import json
from datetime import datetime
import logging
import subprocess
from typing import Dict, List, Optional

from jsoncache import ApplicationCache

from ...common import call
from ...models import MediaElement
from ..generic import AuthorExtractedData, ExtractedData, ExtractionError
from .base import  MediaExtractor


cache = ApplicationCache(app_name="entertainment-decider-ytdl", create_cache_dir=True, default_max_age=7*86400)
cache.clean_cache()

YTDL_CALL = [
    "yt-dlp",
]


class YtdlErrorException(subprocess.CalledProcessError):
    pass

def ytdl_call(args: List[str]) -> dict:
    proc = call(YTDL_CALL + args, check=False)
    if proc.returncode != 0:
        raise YtdlErrorException(
            returncode=proc.returncode,
            cmd=args,
            output=proc.stdout,
            stderr=proc.stderr,
        )
    return json.loads(proc.stdout.strip())

@cache.cache_json()
def get_video_info(uri: str) -> dict:
    return ytdl_call([
        "--no-playlist",
        "--dump-json",
        uri,
    ])

@cache.cache_json()
def get_playlist_info(uri: str) -> dict:
    return ytdl_call(uri)


class YtdlMediaExtractor(MediaExtractor[Dict]):

    def __init__(self):
        super().__init__("ytdl")

    def _get_author_data(self, data: Dict) -> Optional[AuthorExtractedData]:
        video_extractor_key = data.get("extractor_key") or data["ie_key"]
        author_key = data.get("channel_id") or data.get("uploader_id")
        author_name = data.get("channel") or data.get("uploader") or data.get("uploader_id")
        return AuthorExtractedData(
            object_uri = data.get("channel_url") or data.get("uploader_url"),
            extractor_name = self.name,
            object_key = f"author:{video_extractor_key}:{author_key}" if author_key else None,
            author_name = f"{video_extractor_key}: {author_name}" if author_name else None,
        )

    def _extract_online(self, uri: str, cache: Dict) -> ExtractedData[Dict]:
        if cache:
            logging.debug(f"Use preloaded cache to get infos of video {uri!r}")
            vid_data = cache
        else:
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
            cache=None,
        )

    def _update_object_raw(self, object: MediaElement, data: Dict) -> str:
        object.title = f"{data['title']} - {data['uploader']}" if "uploader" in data else data["title"]
        object.release_date = datetime.strptime(data["upload_date"], "%Y%m%d")
        object.length = int(data["duration"])
