from __future__ import annotations

from datetime import datetime
import re
from typing import Optional

import requests

from ...models import MediaElement, MediaThumbnail
from ..all.tvmaze import TvmazeEpisodeEmbedded, select_best_image
from ..generic import ExtractedData, ExtractedDataLight, ExtractionError, SuitableLevel
from .base import MediaExtractor


class TvmazeMediaExtractor(MediaExtractor[TvmazeEpisodeEmbedded]):

    SUPPORTED_PATTERN = re.compile(
        r"""^
            (
                https?://((api|www)\.)?tvmaze\.com
            |
                tvmaze://
            )/episodes/
            (?P<episode_id>\d+)
            (/.*)?
        $""",
        re.VERBOSE,
    )

    @classmethod
    def __get_episode_id(cls, uri: str) -> Optional[int]:
        m = cls.SUPPORTED_PATTERN.search(uri)
        return int(m.group("episode_id")) if m else None

    @classmethod
    def __get_episode_uri(cls, episode_id: str | int) -> str:
        return f"https://www.tvmaze.com/episodes/{episode_id}"

    @classmethod
    def __get_episode_api_uri(cls, episode_id: str | int) -> str:
        return f"https://api.tvmaze.com/episodes/{episode_id}"

    @classmethod
    def __get_episode_custom_uri(cls, episode_id: str | int) -> str:
        return f"tvmaze:///episodes/{episode_id}"

    def __init__(self) -> None:
        super().__init__("tvmaze")

    def uri_suitable(self, uri: str) -> SuitableLevel:
        episode_id = self.__get_episode_id(uri)
        return SuitableLevel.always_or_no(bool(episode_id))

    def can_extract_offline(self, uri: str) -> bool:
        return True

    def _extract_offline(self, uri: str) -> ExtractedDataLight:
        episode_id = self.__get_episode_id(uri)
        return ExtractedDataLight(
            extractor_name=self.name,
            object_key=str(episode_id),
            object_uri=uri,
        )

    def _extract_online(self, uri: str) -> ExtractedData[TvmazeEpisodeEmbedded]:
        episode_id = self.__get_episode_id(uri)
        if episode_id is None:
            raise Exception(f"Expected {uri!r} to be extractable")
        api_uri = self.__get_episode_api_uri(episode_id)
        res = requests.get(
            url=api_uri,
            params={
                "embed[]": [
                    "show",
                ]
            },
        )
        data = res.json()
        return ExtractedData(
            extractor_name=self.name,
            object_key=str(episode_id),
            object_uri=uri,
            data=data,
        )

    def _update_object_raw(
        self, object: MediaElement, data: TvmazeEpisodeEmbedded
    ) -> None:
        # sanity check
        airstamp = data.get("airstamp")
        if airstamp is None:  # not released yet
            raise ExtractionError(
                f"Could not extract {object.uri!r} because of missing data probably due to not being released yet"
            )
        # extract data
        show = data["_embedded"]["show"]
        title = data.get("name")
        if not title:
            title = f"Season {data['season']} - Episode {data['number']}"
        object.title = f"{title} - {show['name']}"
        object.description = data.get("summary")
        thumbnail_uri = select_best_image(data.get("image"), show.get("image"))
        object.thumbnail = (
            MediaThumbnail.from_uri(thumbnail_uri) if thumbnail_uri else None
        )
        object.release_date = datetime.strptime(airstamp, "%Y-%m-%dT%H:%M:%S%z")
        object.length = (
            data.get("runtime")
            or show.get("runtime")
            or show.get("averageRuntime")
            or 0
        ) * 60
        object.add_uris(
            (
                self.__get_episode_uri(data["id"]),
                self.__get_episode_api_uri(data["id"]),
                self.__get_episode_custom_uri(data["id"]),
            )
        )
