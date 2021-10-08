from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Dict, Iterable, List, Optional, Set

from pony import orm

db = orm.Database()


####
## Model Extensions
####


@dataclass
class CollectionStats:

    to_watch_count: int
    ignored_count: int # but not watched
    watched_count: int

    to_watch_seconds: int
    ignored_seconds: int # but not watched
    watched_seconds: int

    @property
    def full_count(self) -> int:
        return self.to_watch_count + self.ignored_count + self.watched_count

    @property
    def full_seconds(self) -> int:
        return self.to_watch_seconds + self.ignored_seconds + self.watched_seconds

    @classmethod
    def from_collection(cls, collection: MediaCollection) -> CollectionStats:
        to_watch_count = 0
        ignored_count = 0
        watched_count = 0
        to_watch_seconds = 0
        ignored_seconds = 0
        watched_seconds = 0
        for link in collection.media_links:
            media = link.element
            if media.watched:
                watched_count += 1
                watched_seconds += media.length
            else:
                watched_seconds += media.progress
                if media.ignored:
                    ignored_count += 1
                    ignored_seconds += media.left_length
                else:
                    to_watch_count += 1
                    to_watch_seconds += media.left_length
        return CollectionStats(
            to_watch_count=to_watch_count,
            ignored_count=ignored_count,
            watched_count=watched_count,
            to_watch_seconds=to_watch_seconds,
            ignored_seconds=ignored_seconds,
            watched_seconds=watched_seconds,
        )


####
## Models
####


class Tag(db.Entity):

    id: int = orm.PrimaryKey(int, auto=True)

    title: str = orm.Required(str)
    notes: str = orm.Optional(str)

    use_for_preferences: bool = orm.Required(bool, default=True)

    _collection_list: Iterable[MediaCollection] = orm.Set(lambda: MediaCollection)
    _media_list: Iterable[MediaElement] = orm.Set(lambda: MediaElement)


class MediaCollectionLink(db.Entity):

    collection: MediaCollection = orm.Required(lambda: MediaCollection)
    element: MediaElement = orm.Required(lambda: MediaElement)
    orm.PrimaryKey(collection, element)
    season: int = orm.Required(int, default=0)
    episode: int = orm.Required(int, default=0)
    orm.composite_index(season, episode)

    @property
    def element_id(self):
        return self.element.id

    @property
    def element_release_date(self):
        return self.element.release_date

    @staticmethod
    def sorted(iterable: Iterable[MediaCollectionLink]) -> List[MediaCollectionLink]:
        return sorted(iterable, key=lambda m: (m.season, m.episode, m.element_release_date, m.element_id))
    natural_order = (season, episode, element_release_date, element_id) # unusuable due to ponyorm, see https://github.com/ponyorm/pony/issues/612


class MediaElement(db.Entity):

    id: int = orm.PrimaryKey(int, auto=True)
    uri: str = orm.Required(str, unique=True)

    title: str = orm.Optional(str)
    notes: str = orm.Optional(str)
    release_date: datetime = orm.Optional(datetime)

    extractor_name: str = orm.Required(str)
    extractor_key: str = orm.Required(str)
    orm.composite_key(extractor_name, extractor_key)
    last_updated: datetime = orm.Optional(datetime)

    watched: bool = orm.Required(bool, default=False)
    ignored: bool = orm.Required(bool, default=False)
    progress: int = orm.Required(int, default=0)
    length: int = orm.Optional(int)

    tag_list : Iterable[Tag] = orm.Set(lambda: Tag)
    _uris: Iterable[MediaUriMapping] = orm.Set(lambda: MediaUriMapping)
    collection_links: Iterable[MediaCollectionLink] = orm.Set(lambda: MediaCollectionLink)

    @property
    def left_length(self) -> int:
        return self.length - self.progress

    @property
    def ignored_recursive(self) -> bool:
        links = orm.select(link for link in MediaCollectionLink if link.episode == self and link.collection.ignored == True)
        return len(links) > 0

    @property
    def ignored_any(self) -> bool:
        return self.ignored or self.ignored_recursive

    @property
    def skip_over(self) -> bool:
        return self.ignored or self.watched

    @property
    def can_considered(self) -> bool:
        if self.skip_over:
            return False
        for link in self.collection_links:
            if link.collection.watch_in_order and self != link.collection.next_episode.element:
                return False
        return True

    @property
    def inherited_tags(self) -> Set[Tag]:
        result = set()
        for link in self.collection_links:
            result |= link.collection.all_tags
        return result

    @property
    def all_tags(self) -> Iterable[Tag]:
        return set(self.tag_list) | self.inherited_tags

    def merge_to(self, other: MediaElement):
        if self.watched:
            other.watched = True
        if self.ignored:
            other.ignored = True
        if self.progress >= 0 and other.progress <= 0:
            other.progress = self.progress
        for uri_map in self._uris:
            uri_map.element = other
        for link in self.collection_links:
            if not MediaCollectionLink.get(collection=link.collection, element=other):
                link.element = other
        self.delete() # will also delete still existing uri mappings and collection links
        orm.flush()

    def add_uris(self, uri_list: Iterable[str]):
        for uri in set(uri_list):
            mapping: MediaUriMapping = MediaUriMapping.get(uri=uri)
            if not mapping:
                logging.debug(f"Add URI mapping {uri!r} to media {self.id!r}")
                MediaUriMapping(
                    uri=uri,
                    element=self,
                )
                continue
            if mapping.element != self:
                raise Exception(f"URI duplicated for two different media's: {uri}") # TODO may replace with merge call
        orm.flush()

    @property
    def info_link(self):
        return f"/media/{self.id}"


class MediaUriMapping(db.Entity):

    id: int = orm.PrimaryKey(int, auto=True)
    uri: str = orm.Required(str, unique=True)
    element: MediaElement = orm.Required(MediaElement)


class MediaCollection(db.Entity):

    id: int = orm.PrimaryKey(int, auto=True)
    uri: str = orm.Required(str, unique=True)

    title: str = orm.Optional(str)
    notes: str = orm.Optional(str)
    release_date: datetime = orm.Optional(datetime)

    extractor_name: str = orm.Required(str)
    extractor_key: str = orm.Required(str)
    orm.composite_key(extractor_name, extractor_key)
    last_updated: datetime = orm.Optional(datetime)

    keep_updated: bool = orm.Required(bool, default=False)
    watch_in_order_auto: bool = orm.Required(bool, default=True)

    ignored: bool = orm.Required(bool, default=False)
    watch_in_order: bool = orm.Required(bool, default=True)

    tag_list: Iterable[Tag] = orm.Set(lambda: Tag)
    _uris: Iterable[CollectionUriMapping] = orm.Set(lambda: CollectionUriMapping)
    media_links: Iterable[MediaCollectionLink] = orm.Set(MediaCollectionLink)

    @property
    def next_episode(self) -> Optional[MediaCollectionLink]:
        #return orm \
        #    .select(link for link in self.media_links if not link.element.watched) \
        #    .order_by(*MediaCollectionLink.natural_order) \
        #    .first()
        episodes = MediaCollectionLink.sorted(orm.select(link for link in self.media_links if not link.element.watched and not link.element.ignored))
        return episodes[0] if len(episodes) > 0 else None

    @property
    def completed(self) -> bool:
        return self.next_episode is None

    @property
    def all_tags(self) -> Iterable[Tag]:
        return self.tag_list

    @property
    def stats(self) -> CollectionStats:
        return CollectionStats.from_collection(self)

    def add_episode(self, media: MediaElement, season: int = 0, episode: int = 0) -> MediaCollectionLink:
        link: MediaCollectionLink = MediaCollectionLink.get(collection=self, element=media)
        if link is None:
            link = MediaCollectionLink(collection=self, element=media)
        link.season, link.episode = season, episode
        orm.flush()
        return link

    def add_uris(self, uri_list: Iterable[str]):
        for uri in set(uri_list):
            mapping: CollectionUriMapping = CollectionUriMapping.get(uri=uri)
            if not mapping:
                logging.debug(f"Add URI mapping {uri!r} to collection {self.id!r}")
                CollectionUriMapping(
                    uri=uri,
                    element=self,
                )
                continue
            if mapping.element != self:
                raise Exception(f"URI duplicated for two different collections's: {uri}") # TODO may replace with merge call
        orm.flush()

    @property
    def info_link(self):
        return f"/collection/{self.id}"


class CollectionUriMapping(db.Entity):

    id: int = orm.PrimaryKey(int, auto=True)
    uri: str = orm.Required(str, unique=True)
    element: MediaCollection = orm.Required(MediaCollection)
