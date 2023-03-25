from __future__ import annotations

from pony import orm  # TODO remove
import requests
from rss_parser import Parser
from rss_parser.models import RSSFeed

from ...models import MediaCollection
from ..generic import (
    ChangedReport,
    ExtractedDataOnline,
    ExtractedDataOffline,
    SuitableLevel,
)
from .base import CollectionExtractor


class RssCollectionExtractor(CollectionExtractor[RSSFeed]):
    PROTOCOL_PREFIX = "rss+"
    SUPPORTED_PROTOCOLS = [
        "http://",
        "https://",
    ]

    @classmethod
    def __get_uri(cls, uri: str) -> str:
        return (
            uri[len(cls.PROTOCOL_PREFIX) :]
            if uri.startswith(cls.PROTOCOL_PREFIX)
            else uri
        )

    def __init__(self) -> None:
        super().__init__(
            key=".extractor/.rss",
            long_name="RSS Feed",
            name="rss",
        )

    def uri_suitable(self, uri: str) -> SuitableLevel:
        cuted = self.__get_uri(uri)
        for proto in self.SUPPORTED_PROTOCOLS:
            if cuted.startswith(proto):
                return SuitableLevel.always_or_fallback(uri != cuted)
        return SuitableLevel.NO

    def can_extract_offline(self, uri: str) -> bool:
        return True

    def _extract_offline(self, uri: str) -> ExtractedDataOffline[RSSFeed]:
        cuted = self.__get_uri(uri)
        return ExtractedDataOffline[RSSFeed](
            extractor_name=self.name,
            object_key=cuted,
            object_uri=uri,
        )

    def _extract_online(self, uri: str) -> ExtractedDataOnline[RSSFeed]:
        cuted = self.__get_uri(uri)
        res = requests.get(cuted)
        parser = Parser(xml=res.content)
        data = parser.parse()
        return ExtractedDataOnline[RSSFeed](
            extractor_name=self.name,
            object_key=cuted,
            object_uri=uri,
            data=data,
        )

    def _update_object_raw(
        self,
        object: MediaCollection,
        data: RSSFeed,
    ) -> ChangedReport:
        object.title = f"[rss] {data.title.strip()}"
        object.description = data.description
        object.set_watch_in_order_auto(True)
        object.add_single_uri(
            self.__get_uri(object.uri)
        )  # add url without prefix if required
        for item in data.feed:
            element = self._add_episode(
                collection=object,
                uri=item.link,
            )
            if element:
                orm.commit()
        return ChangedReport.ChangedSome  # TODO improve
