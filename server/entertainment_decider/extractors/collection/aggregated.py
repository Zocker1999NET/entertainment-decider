from __future__ import annotations

import re
from typing import List, Set

from pony import orm

from ...models import MediaCollection, MediaCollectionLink, MediaElement
from ..generic import ExtractedData, ExtractedDataLight, SuitableLevel
from .base import CollectionExtractor


class AggregatedCollectionExtractor(CollectionExtractor[List[List[MediaElement]]]):

    __uri_regex = re.compile(r"^aggregated:///(?P<id>\d+(,\d+)*)")

    @classmethod
    def __get_id(cls, uri: str) -> List[int]:
        m = cls.__uri_regex.search(uri)
        if not m:
            raise Exception(f"Failed to parse aggregated collection uri {uri!r}")
        return [int(i) for i in m.group("id").split(",")]

    @classmethod
    def __get_collections(cls, uri: str) -> List[MediaCollection]:
        aggregate_ids = cls.__get_id(uri)
        colls = [MediaCollection[i] for i in aggregate_ids]
        return colls

    def __init__(self) -> None:
        super().__init__("aggregated")

    def uri_suitable(self, uri: str) -> SuitableLevel:
        return SuitableLevel.always_or_no(self.__uri_regex.match(uri) is not None)

    def can_extract_offline(self, uri: str) -> bool:
        return True

    def _cache_expired(self, object: MediaCollection) -> bool:
        colls = self.__get_collections(object.uri)
        for c in colls:
            if c.last_updated is None or object.last_updated <= c.last_updated:
                return True
        return False

    def _extract_offline(self, uri: str) -> ExtractedDataLight:
        coll_id = ",".join(str(i) for i in self.__get_id(uri))
        return ExtractedDataLight(
            extractor_name=self.name,
            object_key=coll_id,
            object_uri=uri,
        )

    def _extract_online(self, uri: str) -> ExtractedData[List[List[MediaElement]]]:
        colls = self.__get_collections(uri)
        coll_id = ",".join(str(c.id) for c in colls)
        return ExtractedData(
            extractor_name=self.name,
            object_key=coll_id,
            object_uri=uri,
            data=[
                [
                    l.element
                    for l in orm.select(l for l in c.media_links).order_by(
                        MediaCollectionLink.sort_key
                    )
                ]
                for c in colls
            ],
        )

    def _update_object_raw(
        self, object: MediaCollection, data: List[List[MediaElement]]
    ) -> None:
        if object.title is None or "[aggregated]" not in object.title:
            object.title = f"[aggregated] {object.uri}"
        object.creator = None
        object.set_watch_in_order_auto(True)
        all_links: Set[int] = set(
            orm.select(link.element.id for link in object.media_links)
        )
        for season, media_list in enumerate(data):
            for episode, media in enumerate(media_list):
                all_links.discard(media.id)
                object.add_episode(
                    media=media,
                    season=season + 1,
                    episode=episode + 1,
                )
        orm.delete(link for link in object.media_links if link.element.id in all_links)
        for uri_link in list(object.uris):
            uri_link.delete()
