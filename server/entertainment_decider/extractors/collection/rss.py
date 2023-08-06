from __future__ import annotations

from pony import orm  # TODO remove
import requests
from rss_parser import Parser
from rss_parser.models.rss import RSS

from ...models import MediaCollection
from ..generic import (
    ChangedReport,
    ExtractedDataOnline,
    ExtractedDataOffline,
    SuitableLevel,
)
from .base import CollectionExtractor


class RssCollectionExtractor(CollectionExtractor[RSS]):
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

    def _extract_offline(self, uri: str) -> ExtractedDataOffline[RSS]:
        cuted = self.__get_uri(uri)
        return ExtractedDataOffline[RSS](
            extractor_name=self.name,
            object_key=cuted,
            object_uri=uri,
        )

    def _extract_online(self, uri: str) -> ExtractedDataOnline[RSS]:
        cuted = self.__get_uri(uri)
        res = requests.get(cuted)
        parser = Parser()
        data = parser.parse(data=res.text)
        return ExtractedDataOnline[RSS](
            extractor_name=self.name,
            object_key=cuted,
            object_uri=uri,
            data=data,
        )

    def _update_object_raw(
        self,
        object: MediaCollection,
        data: RSS,
    ) -> ChangedReport:
        object.title = f"[rss] {data.channel.title.content.strip()}"
        object.description = data.channel.description.content
        object.set_watch_in_order_auto(True)
        object.add_single_uri(
            self.__get_uri(object.primary_uri)
        )  # add url without prefix if required
        for item in data.channel.items:
            element = self._add_episode(
                collection=object,
                uri=item.link.content,
            )
            if element:
                orm.commit()
        return ChangedReport.ChangedSome  # TODO improve
