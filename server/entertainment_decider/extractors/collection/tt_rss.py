from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Optional

from pony import orm # TODO remove

from ...models import MediaCollection
from ..all.tt_rss import HeadlineList, TtRssConnectionParameter, TtRssUri
from ..generic import ExtractedData, ExtractionError, SuitableLevel
from ..media import media_extract_uri
from .base import CollectionExtractor


class TtRssCollectionExtractor(CollectionExtractor[HeadlineList]):

    __params: TtRssConnectionParameter
    __label_filter: Optional[int]
    __mark_as_read: bool

    def __init__(self,
        params: TtRssConnectionParameter,
        mark_as_read: bool = False,
        label_filter: Optional[int] = None,
    ):
        super().__init__("tt-rss")
        self.__params = params
        self.__label_filter = label_filter
        self.__mark_as_read = mark_as_read

    def __decode_uri(self, uri: str) -> TtRssUri:
        return TtRssUri.from_str_uri(uri)

    def uri_suitable(self, uri: str) -> SuitableLevel:
        return SuitableLevel.ALWAYS if TtRssUri.uri_suitable(uri) else SuitableLevel.NO

    def can_extract_offline(self, uri: str) -> bool:
        return True

    def _cache_expired(self, date: datetime) -> bool:
        return (datetime.now() - date) > timedelta(minutes=10)

    def _extract_offline(self, uri: str) -> ExtractedData[HeadlineList]:
        return ExtractedData(
            extractor_name=self.name,
            object_key=uri,
            object_uri=uri,
        )

    def _extract_online(self, uri: str) -> ExtractedData[HeadlineList]:
        rss_uri = self.__decode_uri(uri)
        logging.info(f"Extract collection from tt-rss: {uri!r}")
        data = rss_uri.request(self.__params, order_by="feed_dates", view_mode="unread")
        if self.__label_filter is not None:
            print([headline.labels for headline in data])
            data = [
                headline for headline in data
                if self.__label_filter in (label_marker[0] for label_marker in headline.labels)
            ]
        if self.__mark_as_read:
            parameters = {
                "article_ids": ",".join(str(headline.feedId) for headline in data),
                "field": "2", # unread
                "mode": "0", # false
            }
            raise NotImplementedError("Cannot set articles as read with tinytinypy for now") # TODO
        return ExtractedData(
            extractor_name=self.name,
            object_key=uri,
            object_uri=uri,
            data=data,
        )

    def _update_object_raw(self, object: MediaCollection, data: HeadlineList) -> str:
        if not object.title:
            object.title = object.uri
        logging.debug(f"Got {len(data)} headlines")
        for headline in data:
            logging.debug(f"Add to collection {headline.url!r}")
            try:
                object.add_episode(media_extract_uri(headline.url))
                orm.commit()
            except ExtractionError:
                logging.warning(f"Failed while extracting media {headline.url!r}", exc_info=True)
        if object.watch_in_order_auto:
            object.watch_in_order = False # no order available
