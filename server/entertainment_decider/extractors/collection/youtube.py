from __future__ import annotations

from datetime import datetime
import logging
import re
from typing import Dict

from pony import orm  # TODO remove
import youtubesearchpython

from ...models import MediaCollection
from ..generic import ExtractedData, SuitableLevel
from .base import CollectionExtractor


class YouTubeCollectionExtractor(CollectionExtractor[Dict]):

    __uri_regex = re.compile(
        r"^https?://(www\.)?youtube\.com/(channel/|playlist\?list=)(?P<id>[^/&?]+)"
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
        super().__init__("youtube")

    def uri_suitable(self, uri: str) -> SuitableLevel:
        return SuitableLevel.always_or_no(self.__uri_regex.match(uri) is not None)

    def can_extract_offline(self, uri: str) -> bool:
        return True

    def _cache_expired(self, object: MediaCollection) -> bool:
        last_release_date = orm.max(l.element.release_date for l in object.media_links)
        return (datetime.now() - object.last_updated) > self._calculate_wait_hours(
            last_release_date
        )

    def _extract_offline(self, uri: str) -> ExtractedData[Dict]:
        playlist_id = self.__convert_if_required(self.__get_id(uri))
        return ExtractedData(
            extractor_name=self.name,
            object_key=playlist_id,
            object_uri=uri,
        )

    def _extract_online(self, uri: str) -> ExtractedData[Dict]:
        orig_id = self.__get_id(uri)
        playlist_id = self.__convert_if_required(orig_id)
        playlist_link = f"https://www.youtube.com/playlist?list={playlist_id}"
        is_channel = self.__is_channel_id(playlist_id)
        logging.info(f"Request Youtube playlist {playlist_link!r}")
        playlist = youtubesearchpython.Playlist(playlist_link)
        try:
            while playlist.hasMoreVideos:
                playlist.getNextVideos()
        except Exception as e:
            # TODO improve check of Exception kind if possible
            if is_channel and "invalid status code" in str(e.args[0]).lower():
                # Partial Update on channels can be accepted because newest videos are at the top
                logging.warning(
                    f"Failed to retrieve channel completely, proceed with partial update"
                )
            else:
                raise e
        logging.debug(
            f"Retrieved {len(playlist.videos)} videos from playlist {playlist_link!r}"
        )
        return ExtractedData(
            extractor_name=self.name,
            object_key=playlist_id,
            object_uri=uri,
            data={
                "info": playlist.info["info"],
                "videos": playlist.videos,
            },
        )

    def _update_object_raw(self, object: MediaCollection, data: Dict) -> None:
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
