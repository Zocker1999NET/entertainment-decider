from __future__ import annotations

from datetime import datetime
import itertools
import re
from typing import List, Optional

from pony import orm  # TODO remove
import requests

from ...models import (
    MediaCollection,
    Tag,
)
from ..all.tvmaze import (
    TvmazeEpisodeEmbedded,
    TvmazeShowEmbedded,
    add_embedding,
)
from ..generic import (
    ChangedReport,
    ExtractedDataOnline,
    ExtractedDataOffline,
    SuitableLevel,
)
from .base import CollectionExtractor


class TvmazeCollectionExtractor(CollectionExtractor[TvmazeShowEmbedded]):
    SUPPORTED_PATTERN = re.compile(
        r"""^
            (
                https?://((api|www)\.)?tvmaze\.com
            |
                tvmaze://
            )/shows/
            (?P<show_id>\d+)
            (/.*)?
        $""",
        re.VERBOSE,
    )

    @classmethod
    def __get_show_id(cls, uri: str) -> Optional[int]:
        m = cls.SUPPORTED_PATTERN.search(uri)
        return int(m.group("show_id")) if m else None

    @classmethod
    def __require_show_id(cls, uri: str) -> int:
        show_id = cls.__get_show_id(uri)
        if show_id is None:
            raise Exception(
                f"Expected uri to be extractable for TvmazeCollectionExtractor: {uri}"
            )
        return show_id

    @classmethod
    def __get_show_uri(cls, show_id: str | int) -> str:
        return f"https://www.tvmaze.com/shows/{show_id}"

    @classmethod
    def __get_show_api_uri(cls, show_id: str | int) -> str:
        return f"https://api.tvmaze.com/shows/{show_id}"

    @classmethod
    def __get_show_custom_uri(cls, show_id: str | int) -> str:
        return f"tvmaze:///shows/{show_id}"

    def __init__(self) -> None:
        super().__init__("tvmaze")

    def uri_suitable(self, uri: str) -> SuitableLevel:
        show_id = self.__get_show_id(uri)
        return SuitableLevel.always_or_no(bool(show_id))

    def can_extract_offline(self, uri: str) -> bool:
        return True

    def _cache_expired(self, object: MediaCollection) -> bool:
        last_release_date = orm.max(l.element.release_date for l in object.media_links)
        return (datetime.now() - object.last_updated) > self._calculate_wait_hours(
            last_release_date
        )

    def _extract_offline(self, uri: str) -> ExtractedDataOffline[TvmazeShowEmbedded]:
        show_id = self.__require_show_id(uri)
        return ExtractedDataOffline[TvmazeShowEmbedded](
            extractor_name=self.name,
            object_key=str(show_id),
            object_uri=self.__get_show_uri(show_id),
        )

    def _extract_online(self, uri: str) -> ExtractedDataOnline[TvmazeShowEmbedded]:
        show_id = self.__require_show_id(uri)
        api_uri = self.__get_show_api_uri(show_id)
        res = requests.get(
            url=api_uri,
            params={
                "embed[]": [
                    "episodes",
                ]
            },
        )
        data = res.json()
        return ExtractedDataOnline[TvmazeShowEmbedded](
            extractor_name=self.name,
            object_key=str(show_id),
            object_uri=self.__get_show_uri(show_id),
            data=data,
        )

    def _update_object_raw(
        self,
        object: MediaCollection,
        data: TvmazeShowEmbedded,
    ) -> ChangedReport:
        object.title = f"[tvmaze] {data['name']}"
        object.description = data.get("summary", "")
        object.release_date = datetime.strptime(data["premiered"], "%Y-%m-%d")
        object.set_watch_in_order_auto(True)
        object.add_uris(
            (
                self.__get_show_uri(data["id"]),
                self.__get_show_api_uri(data["id"]),
                self.__get_show_custom_uri(data["id"]),
            )
        )
        for genre in itertools.chain(["Video", data["type"]], data["genres"]):
            tag_list: List[Tag] = list(
                orm.select(tag for tag in Tag if tag.title == genre)
            )
            if len(tag_list) == 1:
                object.tag_list.add(tag_list[0])
        for episode in data["_embedded"]["episodes"]:
            if episode["airstamp"] is not None:
                add_embedding(episode, "show", data)
                self._inject_episode(
                    collection=object,
                    data=ExtractedDataOnline[TvmazeEpisodeEmbedded](
                        extractor_name="tvmaze",
                        object_key=str(episode["id"]),
                        object_uri=f"tvmaze:///episodes/{episode['id']}",
                        data=episode,
                    ),
                    season=episode["season"],
                    episode=episode["number"],
                )
        return ChangedReport.ChangedSome  # TODO improve
