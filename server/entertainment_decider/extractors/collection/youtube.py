from __future__ import annotations

from collections.abc import (
    Collection,
)
from datetime import datetime
import logging
import re
from typing import (
    TypedDict,
)

from pony import orm  # TODO remove
from yt_dlp import YoutubeDL

from ...models import MediaCollection
from ..all.youtube import (
    EXTRACTOR_KEY,
    EXTRACTOR_NAME,
)
from ..generic import (
    ChangedReport,
    ExtractedDataOnline,
    ExtractedDataOffline,
    SuitableLevel,
)
from .base import CollectionExtractor


YTDLP_OPTS = {
    "extract_flat": "in_playlist",
}


class PlaylistChannel(TypedDict):
    name: str
    id: str


class PlaylistMetadata(TypedDict):
    id: str
    title: str
    channel: PlaylistChannel
    link: str


class PlaylistVideo(TypedDict):
    id: str


class PlaylistData(TypedDict):
    info: PlaylistMetadata
    videos: Collection[PlaylistVideo]


class YouTubeCollectionExtractor(CollectionExtractor[PlaylistData]):
    __uri_regex = re.compile(
        r"""^
        https?://
            ((
                www
                |
                m
            )\.)?youtube\.com/(
                channel/
                |
                playlist\?list=
            )
            (?P<id>[^/&?]+)
        """,
        re.VERBOSE,
    )

    @classmethod
    def __get_id(cls, uri: str) -> str:
        m = cls.__uri_regex.search(uri)
        if not m:
            raise Exception(f"Failed to parse Youtube collection uri {uri!r}")
        return m.group("id")

    @staticmethod
    def __is_channel_id(collection_id: str) -> bool:
        return collection_id.startswith("UC") or collection_id.startswith("UU")

    @staticmethod
    def __convert_channel_id(channel_id: str) -> str:
        if channel_id.startswith("UU"):
            return channel_id
        if channel_id.startswith("UC"):
            return f"UU{channel_id[2:]}"
        raise Exception(f"Got not valid channel id: {channel_id!r}")

    @classmethod
    def __convert_if_required(cls, collection_id: str) -> str:
        if cls.__is_channel_id(collection_id):
            return cls.__convert_channel_id(collection_id)
        return collection_id

    def __init__(self) -> None:
        super().__init__(
            key=EXTRACTOR_KEY,
            long_name=EXTRACTOR_NAME,
            name="youtube",
        )

    def uri_suitable(self, uri: str) -> SuitableLevel:
        return SuitableLevel.always_or_no(self.__uri_regex.match(uri) is not None)

    def can_extract_offline(self, uri: str) -> bool:
        return True

    def _cache_expired(self, object: MediaCollection) -> bool:
        last_release_date = orm.max(l.element.release_date for l in object.media_links)
        return (datetime.now() - object.last_updated) > self._calculate_wait_hours(
            last_release_date
        )

    def _extract_offline(self, uri: str) -> ExtractedDataOffline[PlaylistData]:
        playlist_id = self.__convert_if_required(self.__get_id(uri))
        return ExtractedDataOffline[PlaylistData](
            extractor_name=self.name,
            object_key=playlist_id,
            object_uri=uri,
        )

    def _extract_online(self, uri: str) -> ExtractedDataOnline[PlaylistData]:
        orig_id = self.__get_id(uri)
        playlist_id = self.__convert_if_required(orig_id)
        playlist_link = f"https://www.youtube.com/playlist?list={playlist_id}"
        logging.info(f"Request Youtube playlist {playlist_link!r}")
        with YoutubeDL(YTDLP_OPTS) as ydl:
            info = ydl.extract_info(
                playlist_link,
                download=False,
            )
            playlist = self.__adapt_ytdlp_format(ydl.sanitize_info(info))
        logging.debug(
            f"Retrieved {len(playlist['videos'])} videos from playlist {playlist_link!r}"
        )
        return ExtractedDataOnline[PlaylistData](
            extractor_name=self.name,
            object_key=playlist_id,
            object_uri=uri,
            data=playlist,
        )

    def _update_object_raw(
        self,
        object: MediaCollection,
        data: PlaylistData,
    ) -> ChangedReport:
        info = data["info"]
        is_channel = self.__is_channel_id(info["id"])
        object.title = (
            f"[channel] [{self.name}] {info['channel']['name']}"
            if is_channel
            else f"[playlist] {info['channel']['name']}: {info['title']}"
        )
        object.description = data.get("description")
        object.add_single_uri(info["link"])
        video_list = data["videos"]
        object.set_watch_in_order_auto(not is_channel)
        if is_channel:
            video_list = reversed(video_list)
            object.sorting_method = 1  # TODO sort channels by date
        for index, video in enumerate(video_list):
            video_url = f"https://www.youtube.com/watch?v={video['id']}"
            element = self._add_episode(
                collection=object,
                uri=video_url,
                episode=index + 1,
            )
            if element:
                orm.commit()  # so progress is stored
        object.release_date = (
            object.first_released_episode.element.release_date
            if len(object.media_links) > 0
            else None
        )
        # creator exists in most cases as videos were already processed
        # if not, creator is not that important
        object.creator = (
            object
            if is_channel
            else CollectionExtractor.check_uri(
                f"https://www.youtube.com/channel/{info['channel']['id']}"
            )
        )
        return ChangedReport.ChangedSome  # TODO improve

    @staticmethod
    def __adapt_ytdlp_format(ytdlp_info) -> PlaylistData:
        return {
            "info": {
                "id": ytdlp_info["id"],
                "title": ytdlp_info["title"],
                "channel": {
                    "id": ytdlp_info["channel_id"],
                    "name": ytdlp_info["channel"],
                },
                "link": ytdlp_info["webpage_url"],
            },
            "videos": [
                {
                    "id": elem["id"],
                }
                for elem in ytdlp_info["entries"]
            ],
        }
