from __future__ import annotations

from abc import abstractproperty
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import (
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
    TypeVar,
)

import magic
import requests
from pony import orm

from .custom_types import Query
from .db import db
from .thumbnails import THUMBNAIL_ALLOWED_TYPES, THUMBNAIL_HEADERS
from .extras import (
    UriHolder,
)
from ..preferences.tag_protocol import TagableProto, TagProto



T = TypeVar("T")


####
## Model Extensions
####


class Tagable(TagableProto["Tag"]):
    ## abstracted

    @abstractproperty
    def orm_assigned_tags(self) -> Query[Tag]:
        """
        Tags which are directly assigned to this object by the user or automatic actions.
        """

    @property
    def orm_inherited_tags(self) -> Query[Tag]:
        """
        Tags, which are inherited by any other means than super/sub-tag relationships.
        This relationship does not declare a distance between this tags and assigned tags.
        """
        return []  # TODO to orm compatible

    @property
    def orm_super_tags(self) -> Query[Tag]:
        """
        Tags, which are inherited only by super/sub-tag relationships.
        This relationship does declare a distance between this tags and assigned tags.
        """
        return []  # TODO to orm compatible

    ## implemented

    @property
    def assigned_tags(self) -> Set[Tag]:
        return set(self.orm_assigned_tags)

    @property
    def inherited_tags(self) -> Set[Tag]:
        return set(self.orm_inherited_tags)

    @property
    def super_tags(self) -> Set[Tag]:
        return set(self.orm_super_tags)

    @property
    def orm_direct_tags(self) -> Query[Tag]:
        return self.orm_assigned_tags + self.orm_inherited_tags

    @property
    def direct_tags(self) -> Set[Tag]:
        return set(self.orm_direct_tags)

    @property
    def all_tags(self) -> Set[Tag]:
        queue: List[Tag] = list(self.direct_tags)
        used: Set[Tag] = set(queue)
        while queue:
            tag = queue.pop(0)
            new_tags = tag.super_tags - used
            queue.extend(new_tags)
            used |= new_tags
        return used


@dataclass
class CollectionStats:
    to_watch_count: int
    ignored_count: int  # but not watched
    watched_count: int

    to_watch_seconds: int
    ignored_seconds: int  # but not watched
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


## Tag & Selection Score's


TEMPORARY_TAGS_IDENTIFIER = (
    "automatic_temporary_tag:82e4509f-e262-463f-8ee5-140ca400ea79"
)
"""random static UUID for identification

This string shall not be parsed and only used as a whole.
"""


class Tag(db.Entity, Tagable, TagProto["Tag"]):
    @classmethod
    def gen_temporary_tag(cls, hint: str) -> Tag:
        """Generates a new, unique and temporary tag. Required for some algorithms."""
        return Tag(
            title=f"[A] {hint}",
            notes=TEMPORARY_TAGS_IDENTIFIER,
            use_for_preferences=True,
        )

    @classmethod
    def scrub_temporary_tags(cls) -> int:
        """Scrubs all temporary tags, which where left over because of errors."""
        count = orm.delete(tag for tag in cls if tag.notes == TEMPORARY_TAGS_IDENTIFIER)
        return count if isinstance(count, int) else 0

    id: int = orm.PrimaryKey(int, auto=True)

    title: str = orm.Required(str)
    notes: Optional[str] = orm.Optional(
        str,
        nullable=True,
    )

    use_for_preferences: bool = orm.Required(bool, default=True)

    tag_keys: Set[TagKey] = orm.Set(lambda: TagKey)

    super_tag_list: Set[Tag] = orm.Set(lambda: Tag, reverse="sub_tag_list")
    sub_tag_list: Set[Tag] = orm.Set(lambda: Tag, reverse="super_tag_list")

    collection_list: Set[MediaCollection] = orm.Set(lambda: MediaCollection)
    media_list: Set[MediaElement] = orm.Set(lambda: MediaElement)

    @property
    def orm_assigned_tags(self) -> Query[Tag]:
        return [self] if self.use_for_preferences else self.super_tag_list

    @property
    def orm_super_tags(self) -> Query[Tag]:
        return self.super_tag_list if self.use_for_preferences else []

    @property
    def info_link(self) -> str:
        return f"/tag/{self.id}"


class TagKey(db.Entity):
    num_id: int = orm.PrimaryKey(int, auto=True)
    tag_key: str = orm.Required(str, unique=True)
    """Format: <domain>[/<kind>][/<id>]

    These IDs are distinctive of URLs.
    Multiple sub-kinds can be used if required.
    They should not contain unnecceray information
    like names, titles, descriptions, dates
    (or only when part of the one unique ID).

    Domains must be used in reverse domain name notation
    to allow for efficient prefix searches.
    Domains must not start or end with a ".",
    all domains are meant to be absolute.

    Internal identifiers should use "." as domain and should omit the first "/"
    to avoid collisions with TLDs,
    e.g. ".automatic/collection/<id>".

    Identifiers from extractors which want to avoid collisions
    because of multiple ones supporting the same site
    should choose a domain for their own product
    and use the format: <extractor-domain>/<source-domain>[/<kind>][/<id>]
    """
    tag: Tag = orm.Required(Tag)

    @classmethod
    def get_by_prefix(cls, tag_key_prefix: str) -> Set[Tag]:
        key_set = orm.select(
            key for key in cls if key.tag_key.startswith(tag_key_prefix)
        )
        return {key.tag for key in key_set}

    @classmethod
    def get_or_create_tag(
        cls,
        tag_key: str,
        title: Optional[str] = None,
        notes: Optional[str] = None,
        use_for_preferences: bool = False,
        super_tags: Iterable[Tag | str] = [],
    ) -> Tag:
        tag = cls.get_tag(tag_key)
        if tag is not None:
            if title is not None and not tag.title:
                tag.title = title
            if notes is not None and not tag.notes:
                tag.notes = notes
        if tag is None:
            tag = Tag(
                title=title,
                notes=notes,
                use_for_preferences=use_for_preferences,
            )
            cls(
                tag_key=tag_key,
                tag=tag,
            )
        for super_tag_key in super_tags:
            super_tag = cls.get_tag(tag_key=super_tag_key)
            if super_tag is not None:
                tag.super_tag_list.add(super_tag)
        return tag

    @classmethod
    def get_tag(cls, tag_key: Tag | str) -> Optional[Tag]:
        if isinstance(tag_key, Tag):
            return tag_key
        tag: Tag = orm.select(key.tag for key in cls if key.tag_key == tag_key).first()
        return tag if tag is not None else None


## Element <-> Collection Linking


class MediaCollectionLink(db.Entity):
    collection: MediaCollection = orm.Required(lambda: MediaCollection)
    element: MediaElement = orm.Required(lambda: MediaElement)
    orm.PrimaryKey(collection, element)
    season: int = orm.Required(int, default=0)
    episode: int = orm.Required(int, default=0)
    orm.composite_index(season, episode)

    @property
    def element_id(self) -> int:
        return self.element.id

    @property
    def element_release_date(self) -> datetime:
        return self.element.release_date

    @staticmethod
    def sort_key(link: MediaCollectionLink) -> Tuple:
        return (
            link.season,
            link.episode,
            link.element.release_date,
            link.element.id,
        )

    @staticmethod
    def desc_sort_key(link: MediaCollectionLink) -> Tuple:
        """
        Only working for Pony calls
        """
        return (
            orm.desc(link.season),
            orm.desc(link.episode),
            orm.desc(link.element.release_date),
            orm.desc(link.element.id),
        )

    @staticmethod
    def sorted(iterable: Iterable[MediaCollectionLink]) -> List[MediaCollectionLink]:
        return sorted(iterable, key=MediaCollectionLink.sort_key)


## Media Elements


class MediaElement(db.Entity, UriHolder, Tagable):
    ### columns

    id: int = orm.PrimaryKey(
        int,
        auto=True,
    )
    __uri: str = orm.Required(
        str,
        column="uri",
        unique=True,
    )

    title: str = orm.Optional(str)
    description: Optional[str] = orm.Optional(
        orm.LongStr,
        nullable=True,
    )
    thumbnail: Optional[MediaThumbnail] = orm.Optional(
        lambda: MediaThumbnail,
        nullable=True,
    )
    notes: str = orm.Optional(str)
    release_date: datetime = orm.Optional(
        datetime,
        index=True,
    )

    extractor_name: str = orm.Optional(str)
    extractor_key: str = orm.Optional(str)
    orm.composite_index(extractor_name, extractor_key)
    last_updated: datetime = orm.Optional(datetime)

    watched: bool = orm.Required(
        bool,
        column="watched",
        default=False,
        index=False,  # does not need index because of composite index below
    )
    ignored: bool = orm.Required(
        bool,
        column="ignored",
        default=False,
        index=True,
    )
    orm.composite_index(watched, ignored)
    progress: int = orm.Required(
        int,
        default=0,
    )
    length: int = orm.Optional(int)

    tag_list: Set[Tag] = orm.Set(
        lambda: Tag,
    )
    __uri_list: Set[MediaUriMapping] = orm.Set(
        lambda: MediaUriMapping,
    )
    collection_links: Set[MediaCollectionLink] = orm.Set(
        lambda: MediaCollectionLink,
    )

    blocked_by: Set[MediaElement] = orm.Set(
        lambda: MediaElement,
        reverse="is_blocking",
    )
    is_blocking: Set[MediaElement] = orm.Set(
        lambda: MediaElement,
        reverse="blocked_by",
    )

    @classmethod
    def new(
        cls,
        *,
        extractor_name: str,
        extractor_key: str,
        uri: str,
    ) -> MediaElement:
        return cls(
            extractor_name=extractor_name,
            extractor_key=extractor_key,
            _MediaElement__uri=uri,  # manual mangling for MediaElement
        )

    ### for UriHolder

    @property
    def _primary_uri(self) -> str:
        return self.__uri

    def _set_primary_uri(self, uri: str) -> bool:
        action = super()._set_primary_uri(uri)
        if action:
            # do nothing if action already applied
            return True
        self.__uri = uri
        return True

    @property
    def _uri_set(self) -> Set[str]:
        return {m.uri for m in self.__uri_list}

    def _clear_uri_set(self) -> None:
        self.__uri_list = set()

    def _add_uri_to_set(self, uri: str) -> bool:
        action = super()._add_uri_to_set(uri)
        if action:
            # do nothing if action already applied
            return True
        mapping: Optional[MediaUriMapping] = MediaUriMapping.get(uri=uri)
        if not mapping:
            logging.debug(f"Add URI mapping {uri!r} to media {self.id!r}")
            MediaUriMapping(
                uri=uri,
                element=self,
            )
            return True
        if mapping.element != self:
            raise Exception(
                f"URI duplicated for two different media's: {uri}"
            )  # TODO may replace with merge call
        return False

    def _remove_uri_from_set(self, uri: str) -> bool:
        action = super()._remove_uri_from_set(uri)
        if action:
            # do nothing if action already applied
            return True
        mapping: Optional[MediaUriMapping] = MediaUriMapping.get(
            uri=uri,
            element=self,
        )
        if not mapping:
            return False
        mapping.delete()
        return True

    ### for Tagable

    @property
    def orm_assigned_tags(self) -> Query[Tag]:
        return self.tag_list

    @property
    def orm_inherited_tags(self) -> Query[Tag]:
        # TODO: return orm.select(tag for link in self.collection_links for tag in link.collection.orm_direct_tags)
        return [
            tag for link in self.collection_links for tag in link.collection.direct_tags
        ]

    ### properties

    @property
    def was_extracted(self) -> bool:
        return self.last_updated is not None

    @property
    def _left_length(self) -> int:
        return self.length - self.progress

    @property
    def left_length(self) -> int:
        return 0 if self.watched else self._left_length

    @property
    def started(self) -> bool:
        return not self.skip_over and self.progress != 0

    @property
    def average_release_per_week(self) -> float:
        return (
            orm.avg(
                link.collection.average_release_per_week
                for link in self.collection_links
                if link.collection.watch_in_order
            )
            or 0
        )

    @property
    def average_release_per_week_now(self) -> float:
        return (
            orm.avg(
                link.collection.average_release_per_week_now
                for link in self.collection_links
                if link.collection.watch_in_order
            )
            or 0
        )

    @property
    def ignored_recursive(self) -> bool:
        return (
            orm.count(
                link
                for link in self.collection_links
                if link.collection.ignored == True
            )
            > 0
        )

    @property
    def ignored_any(self) -> bool:
        return self.ignored or self.ignored_recursive

    @property
    def skip_over(self) -> bool:
        return self.ignored or self.watched

    @property
    def can_considered(self) -> bool:
        DIRECT_SQL = True
        if DIRECT_SQL:
            # import here because of circular dependency
            from .sql_speedups import is_considered

            return is_considered(self.id)
        if self.skip_over:
            return False
        if self.release_date > datetime.now():
            return False
        if orm.exists(e for e in self.blocked_by if not e.skip_over):
            return False
        ordered_collections: Query[MediaCollection] = orm.select(
            l.collection for l in self.collection_links if l.collection.watch_in_order
        )
        for collection in ordered_collections:
            next = collection.next_episode
            if next is not None and self != next.element:
                return False
        return True

    @property
    def detected_creators(self) -> Query[MediaCollectionLink]:
        return orm.select(
            link for link in self.collection_links if link.collection.is_creator
        )

    @property
    def detected_playlists(self) -> Query[MediaCollectionLink]:
        return orm.select(
            link for link in self.collection_links if link.collection.watch_in_order
        )

    @property
    def info_link(self) -> str:
        return f"/media/{self.id}"

    ### methods

    def merge_to(self, other: MediaElement) -> None:
        if self.watched:
            other.watched = True
        if self.ignored:
            other.ignored = True
        if self.progress >= 0 and other.progress <= 0:
            other.progress = self.progress
        for uri_map in self.__uri_list:
            uri_map.element = other
        for link in self.collection_links:
            if not MediaCollectionLink.get(collection=link.collection, element=other):
                link.element = other
        self.delete()  # will also delete still existing uri mappings and collection links
        orm.flush()

    def before_insert(self) -> None:
        self.before_update()

    def before_update(self) -> None:
        self.add_single_uri(self.__uri)

    ### static

    @staticmethod
    def sort_key(element: MediaElement) -> Tuple:
        return (
            element.release_date,
            element.id,
        )


class MediaThumbnail(db.Entity):
    id: int = orm.PrimaryKey(
        int,
        auto=True,
    )
    uri: str = orm.Required(
        str,
        unique=True,
    )

    __cache_obj: MediaThumbnailCache = orm.Optional(
        lambda: MediaThumbnailCache,
        nullable=True,
    )
    elements: Set[MediaElement] = orm.Set(lambda: MediaElement)

    @classmethod
    def from_uri(cls, uri: str) -> MediaThumbnail:
        return cls.get(uri=uri) or MediaThumbnail(uri=uri)

    def receive(self) -> MediaThumbnailCache:
        return self.__cache_obj or MediaThumbnailCache.download(self)


class MediaThumbnailCache(db.Entity):
    thumbnail: MediaThumbnail = orm.PrimaryKey(
        lambda: MediaThumbnail,
        auto=False,
    )
    last_downloaded: datetime = orm.Required(
        datetime,
    )
    last_accessed: datetime = orm.Optional(
        datetime,
        nullable=True,
    )
    mime_type: str = orm.Required(
        str,
    )
    _data: bytes = orm.Required(
        bytes,
        column="data",
        lazy=True,  # do not always preload huge image data
    )

    @classmethod
    def download(cls, thumbnail: MediaThumbnail) -> MediaThumbnailCache:
        res = requests.get(url=thumbnail.uri, headers=THUMBNAIL_HEADERS)
        mime = magic.from_buffer(res.content, mime=True)
        if mime not in THUMBNAIL_ALLOWED_TYPES:
            raise Exception(f"Couldn't download thumbnail: {thumbnail.uri}")
        now = datetime.now()
        return cls(
            thumbnail=thumbnail,
            last_downloaded=now,
            mime_type=mime,
            _data=res.content,
        )

    def access_data(self) -> bytes:
        self.last_accessed = datetime.now()
        return self._data


class MediaUriMapping(db.Entity):
    id: int = orm.PrimaryKey(int, auto=True)
    uri: str = orm.Required(str, unique=True)
    element: MediaElement = orm.Required(MediaElement)


## Media Collections


class MediaCollection(db.Entity, UriHolder, Tagable):
    ### columns

    id: int = orm.PrimaryKey(
        int,
        auto=True,
    )
    __uri: str = orm.Required(
        str,
        column="uri",
        unique=True,
    )

    title: str = orm.Optional(str)
    description: str = orm.Optional(
        orm.LongStr,
        nullable=True,
    )
    notes: str = orm.Optional(str)
    release_date: Optional[datetime] = orm.Optional(
        datetime,
        nullable=True,
    )
    creator: Optional[MediaCollection] = orm.Optional(
        lambda: MediaCollection,
        nullable=True,
    )

    extractor_name: str = orm.Optional(str)
    extractor_key: str = orm.Optional(str)
    orm.composite_index(extractor_name, extractor_key)
    last_updated: datetime = orm.Optional(datetime)

    keep_updated: bool = orm.Required(
        bool,
        default=False,
        index=True,
    )
    watch_in_order_auto: bool = orm.Required(
        bool,
        default=True,
    )
    sorting_method: int = orm.Required(
        int,
        default=0,
    )

    pinned: bool = orm.Required(
        bool,
        default=False,
        index=True,
    )
    ignored: bool = orm.Required(
        bool,
        default=False,
    )
    watch_in_order: bool = orm.Required(
        bool,
        default=True,
        index=True,
    )

    tag_list: Set[Tag] = orm.Set(
        lambda: Tag,
    )
    __uri_set: Set[CollectionUriMapping] = orm.Set(
        lambda: CollectionUriMapping,
    )
    media_links: Set[MediaCollectionLink] = orm.Set(
        MediaCollectionLink,
    )
    created_collections: Set[MediaCollection] = orm.Set(
        lambda: MediaCollection,
    )

    @classmethod
    def new(
        cls,
        *,
        extractor_name: str,
        extractor_key: str,
        uri: str,
    ) -> MediaCollection:
        return cls(
            extractor_name=extractor_name,
            extractor_key=extractor_key,
            _MediaCollection__uri=uri,  # manual mangling for MediaCollection
        )

    ### for UriHolder

    @property
    def _primary_uri(self) -> str:
        return self.__uri

    def _set_primary_uri(self, uri: str) -> bool:
        action = super()._set_primary_uri(uri)
        if action:
            # do nothing if action already applied
            return True
        self.__uri = uri
        return True

    @property
    def _uri_set(self) -> Set[str]:
        return {m.uri for m in self.__uri_set}

    def _clear_uri_set(self) -> None:
        self.__uri_set = set()

    def _add_uri_to_set(self, uri: str) -> bool:
        action = super()._add_uri_to_set(uri)
        if action:
            # do nothing if action already applied
            return True
        mapping: CollectionUriMapping = CollectionUriMapping.get(uri=uri)
        if not mapping:
            logging.debug(f"Add URI mapping {uri!r} to collection {self.id!r}")
            CollectionUriMapping(
                uri=uri,
                element=self,
            )
            return True
        if mapping.element != self:
            raise Exception(
                f"URI duplicated for two different collections's: {uri}"
            )  # TODO may replace with merge call
        return False

    def _remove_uri_from_set(self, uri: str) -> bool:
        action = super()._remove_uri_from_set(uri)
        if action:
            # do nothing if action already applied
            return True
        mapping: Optional[CollectionUriMapping] = CollectionUriMapping.get(
            uri=uri,
            element=self,
        )
        if not mapping:
            return False
        mapping.delete()
        return True

    ### for Tagable

    @property
    def orm_assigned_tags(self) -> Query[Tag]:
        return self.tag_list

    ### properties

    @property
    def is_creator(self) -> bool:
        return self == self.creator

    @property
    def has_creator(self) -> bool:
        return self.creator is not None

    @property
    def is_root_collection(self) -> bool:
        return self.is_creator or not self.has_creator

    @property
    def was_extracted(self) -> bool:
        return self.last_updated is not None

    @property
    def count(self) -> int:
        return orm.count(self.media_links)

    @property
    def full_length(self) -> int:
        return orm.sum(link.element.length for link in self.media_links)

    @property
    def first_episode(self) -> Optional[MediaCollectionLink]:
        return (
            orm.select(l for l in self.media_links)
            .order_by(MediaCollectionLink.sort_key)
            .first()
        )

    @property
    def last_episode(self) -> Optional[MediaCollectionLink]:
        return (
            orm.select(l for l in self.media_links)
            .order_by(MediaCollectionLink.desc_sort_key)
            .first()
        )

    @property
    def first_released_episode(self) -> Optional[MediaCollectionLink]:
        return (
            orm.select(l for l in self.media_links)
            .order_by(lambda l: l.element.release_date)
            .first()
        )

    @property
    def last_released_episode(self) -> Optional[MediaCollectionLink]:
        # return orm \
        #    .select(l for l in self.media_links) \
        #    .order_by(lambda l: orm.desc(l.element.release_date)) \
        #    .first()
        return (
            orm.select(l for l in self.media_links)
            .order_by(lambda l: orm.desc(l.element.release_date))
            .first()
        )

    @property
    def last_release_date_to_watch(self) -> Optional[datetime]:
        return orm.max(
            (
                l.element.release_date
                for l in self.media_links
                if not l.element.skip_over
            ),
            default=None,
        )

    def __to_watch_episodes(self) -> Query | Iterable[MediaCollectionLink]:
        return orm.select(
            link for link in self.media_links if not link.element.skip_over
        )

    @property
    def next_episode(self) -> Optional[MediaCollectionLink]:
        return (
            orm.select(link for link in self.media_links if not link.element.skip_over)
            .order_by(MediaCollectionLink.sort_key)
            .first()
        )

    @property
    def to_watch_count(self) -> int:
        return self.__to_watch_episodes().count()

    @property
    def completed(self) -> bool:
        return self.to_watch_count <= 0

    @property
    def average_release_per_week(self) -> float:
        return (
            (
                self.full_length
                / (
                    (
                        (
                            (
                                self.last_released_episode.element.release_date
                                - self.first_released_episode.element.release_date
                            )
                            * (self.count / (self.count - 1))
                        )
                        / timedelta(days=7)
                    )
                    or 1
                )
            )
            if self.count >= 2
            else self.full_length
        )

    @property
    def average_release_per_week_now(self) -> float:
        return self.full_length / (
            (
                (datetime.now() - self.first_released_episode.element.release_date)
                / timedelta(days=7)
            )
            or 1
        )

    @property
    def stats(self) -> CollectionStats:
        return CollectionStats.from_collection(self)

    @property
    def info_link(self) -> str:
        return f"/collection/{self.id}"

    ### methods

    def set_watch_in_order_auto(self, watch_in_order: bool) -> None:
        if self.watch_in_order_auto:
            self.watch_in_order = watch_in_order

    def add_episode(
        self,
        media: MediaElement,
        season: int = 0,
        episode: int = 0,
    ) -> Optional[MediaCollectionLink]:
        link: MediaCollectionLink = MediaCollectionLink.get(
            collection=self, element=media
        )
        change = False
        if link is None:
            change = True
            link = MediaCollectionLink(collection=self, element=media)
        if (link.season, link.episode) != (season, episode) and (season, episode) != (
            0,
            0,
        ):
            change = True
            link.season, link.episode = season, episode
        if self.ignored and not media.skip_over:
            change = True
            media.ignored = True
        if change:
            orm.flush()
            return link
        return None

    def before_insert(self) -> None:
        self.before_update()

    def before_update(self) -> None:
        self.add_single_uri(self.__uri)


class CollectionUriMapping(db.Entity):
    id: int = orm.PrimaryKey(int, auto=True)
    uri: str = orm.Required(str, unique=True)
    element: MediaCollection = orm.Required(MediaCollection)
