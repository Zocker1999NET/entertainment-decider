from __future__ import annotations

import base64
import dataclasses
from dataclasses import dataclass
from datetime import datetime
import gzip
import json
import math
import logging
import re
from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    NewType,
    Optional,
    Set,
    Tuple,
    TypeVar,
    Union,
)

import magic
import requests
from pony import orm
from pony.orm.core import Query as PonyQuery

from .common import trim

db = orm.Database()


SafeStr = NewType("SafeStr", str)
"""
Use this type for strings which are expected to be safe to insert into SQL statements.
They may be included into a SQL statement by quoting them manually: f"SELECT * FROM '{safe_str}'"

DO NOT CAST STRINGS WHICH MAY BE SET BY USERS TO PREVENT SQL INJECTION ATTACKS.
"""


T = TypeVar("T")


class Query(
    List[T],
    PonyQuery,
):
    """
    This class may be used to reflect PonyQuerys with all their "kind of" list behavior.
    Only use it for type hintings.
    """
    pass


THUMBNAIL_ALLOWED_TYPES = [
    "image/avif",
    "image/jpeg",
    "image/png",
    "image/webp",
]
THUMBNAIL_HEADERS = {
    "Accept": ",".join(THUMBNAIL_ALLOWED_TYPES) + ",*/*;q=0.9",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:91.0) Gecko/20100101 Firefox/91.0",
}
THUMBNAIL_TARGET = 16 / 9


def thumbnail_sort_key(width: int, height: int) -> Tuple:
    return (
        abs((width / height) - THUMBNAIL_TARGET),
        width * height,
    )


####
## Model Extensions
####


@dataclass
class TagRootElement:
    base: Tagable
    children: List[TagTreeElement] = dataclasses.field(default_factory=lambda: [])

    def share_score(self, points: float) -> PreferenceScoreAppender:
        if points == 0 or len(self.children) <= 0:
            return PreferenceScoreAppender()
        single_share = points / len(self.children)
        shares = (child.share_score(single_share) for child in self.children)
        return PreferenceScoreAppender(shares)


@dataclass
class TagTreeElement:
    base: Tag
    children: List[TagTreeElement] = dataclasses.field(default_factory=lambda: [])

    def share_score(self, points: float) -> PreferenceScoreAppender:
        if len(self.children) <= 0:
            return PreferenceScoreAppender(PreferenceScore({self.base: points}))
        children_fraction = len(self.children)
        base_fraction = children_fraction + 1
        single_share = points / (base_fraction + children_fraction)
        base_share = PreferenceScore({self.base: single_share * base_fraction})
        shares = (child.share_score(single_share) for child in self.children)
        return base_share & shares


TagElement = Union[TagRootElement, TagTreeElement]


class Tagable:

    ## abstracted

    @property
    def assigned_tags(self) -> Set[Tag]:
        """
        Tags which are directly assigned to this object by the user or automatic actions.
        """
        raise NotImplementedError("")

    @property
    def inherited_tags(self) -> Set[Tag]:
        """
        Tags, which are inherited by any other means than super/sub-tag relationships.
        This relationship does not declare a distance between this tags and assigned tags.
        """
        return set()

    @property
    def super_tags(self) -> Set[Tag]:
        """
        Tags, which are inherited only by super/sub-tag relationships.
        This relationship does declare a distance between this tags and assigned tags.
        """
        return set()

    ## implemented

    @property
    def direct_tags(self) -> Set[Tag]:
        return self.assigned_tags | self.inherited_tags

    @property
    def __tag_hierachy(self) -> Tuple[TagRootElement, Set[Tag]]:
        root = TagRootElement(
            base=self,
            children=[TagTreeElement(tag) for tag in self.direct_tags],
        )
        stack: List[TagTreeElement] = root.children[:]
        used: Set[Tag] = self.direct_tags
        while len(stack) > 0:
            cur = stack.pop(0)
            for tag in cur.base.super_tags:
                if tag not in used:
                    elem = TagTreeElement(tag)
                    cur.children.append(elem)
                    stack.append(elem)
                    used.add(tag)
        return root, used

    @property
    def tag_hierachy(self) -> TagRootElement:
        return self.__tag_hierachy[0]

    @property
    def all_tags(self) -> Set[Tag]:
        return self.__tag_hierachy[1]


T = TypeVar("T", bound=Tagable)


@dataclass
class PreferenceScore:
    points: Dict[Tag, float] = dataclasses.field(default_factory=lambda: {})

    def __add__(self, other: PreferenceScoreCompatible) -> PreferenceScore:
        return (self & other).calculate()

    def __and__(self, other: PreferenceScoreCompatible) -> PreferenceScoreAppender:
        return PreferenceScoreAppender(self, other)

    def __mul__(self, scalar: float) -> PreferenceScore:
        return PreferenceScore(
            {tag: score * scalar for tag, score in self.points.items()}
        )

    def __neg__(self) -> PreferenceScore:
        return self * -1

    def adapt_score(self, tagable: Tagable, score: float) -> PreferenceScore:
        return (self & tagable.tag_hierachy.share_score(score)).calculate()

    def calculate_score(self, object: Tagable) -> float:
        return math.fsum(
            self.points[tag] for tag in object.all_tags if tag in self.points
        )

    def order_by_score(self, objects: Iterable[T]) -> List[T]:
        return sorted(objects, key=lambda o: self.calculate_score(o))

    def get_first_by_score(self, objects: Iterable[T]) -> List[T]:
        return min(objects, key=lambda o: self.calculate_score(o))

    @classmethod
    def from_json(cls, data: str) -> PreferenceScore:
        dicts: Dict = json.loads(data)
        return cls({Tag[id]: score for id, score in dicts.items()})

    @classmethod
    def from_base64(cls, in_data: str, encoding: str = "utf-8") -> PreferenceScore:
        data = in_data.encode(encoding)
        data = base64.decodebytes(data)
        data = gzip.decompress(data)
        data = data.decode(encoding)
        data = PreferenceScore.from_json(data)
        return data

    def to_json(self) -> str:
        return json.dumps({tag.id: score for tag, score in self.points.items()})

    def to_base64(self, encoding: str = "utf-8") -> str:
        data = self.to_json()
        data = data.encode(encoding)
        data = gzip.compress(
            data=data,
            compresslevel=9,
        )
        data = base64.encodebytes(data)
        data = data.decode(encoding)
        return data


class PreferenceScoreAppender:
    points_list: List[PreferenceScore]

    def __init__(self, *args: PreferenceScoreCompatible):
        self.points_list = []
        for preference in args:
            self.__append(preference)

    def __append(self, preference: PreferenceScoreCompatible):
        if isinstance(preference, PreferenceScore):
            self.points_list.append(preference)
        elif isinstance(preference, PreferenceScoreAppender):
            self.points_list.extend(preference.points_list)
        else:
            for sub_pref in preference:
                self.__append(sub_pref)

    def __and__(self, other: PreferenceScoreCompatible) -> PreferenceScoreAppender:
        return PreferenceScoreAppender(self, other)

    def calculate(self) -> PreferenceScore:
        combined: Dict[Tag, List[float]] = {}
        for preference in self.points_list:
            for tag, score in preference.points.items():
                if tag not in combined:
                    combined[tag] = []
                combined[tag].append(score)
        return PreferenceScore(
            {tag: math.fsum(scores) for tag, scores in combined.items()}
        )


PreferenceScoreCompatibleSimple = Union[PreferenceScore, PreferenceScoreAppender]
PreferenceScoreCompatible = Union[
    PreferenceScoreCompatibleSimple, Iterable[PreferenceScoreCompatibleSimple]
]


def generate_preference_list(
    base: PreferenceScore,
    object_gen: Callable[[], List[MediaElement]],
    score_adapt: float,
    limit: Optional[int] = None,
) -> List[MediaElement]:
    res_ids = list[int]()
    tag_map = dict[MediaCollection, Tag]()
    element_list = object_gen()
    for element in element_list:
        for link in element.collection_links:
            if link.collection not in tag_map:
                tag = Tag(title="Automatic")
                tag.use_for_preferences = True
                link.collection.tag_list.add(tag)
                tag_map[link.collection] = tag
    orm.flush()
    while True:
        if len(element_list) <= 0:
            break
        first_element = base.get_first_by_score(element_list)
        res_ids.append(first_element.id)
        if limit is not None and limit <= len(res_ids):
            break
        first_element.watched = True  # simulative
        base = base.adapt_score(first_element, score_adapt)
        element_list = object_gen()
    orm.rollback()
    return [MediaElement[i] for i in res_ids]


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


class Tag(db.Entity, Tagable):

    id: int = orm.PrimaryKey(int, auto=True)

    title: str = orm.Required(str)
    notes: str = orm.Optional(str)

    use_for_preferences: bool = orm.Required(bool, default=True)

    super_tag_list: Iterable[Tag] = orm.Set(lambda: Tag, reverse="sub_tag_list")
    sub_tag_list: Iterable[Tag] = orm.Set(lambda: Tag, reverse="super_tag_list")

    _collection_list: Iterable[MediaCollection] = orm.Set(lambda: MediaCollection)
    _media_list: Iterable[MediaElement] = orm.Set(lambda: MediaElement)

    @property
    def assigned_tags(self) -> Set[Tag]:
        return {self}

    @property
    def super_tags(self) -> Set[Tag]:
        return set(self.super_tag_list)


## Element <-> Collection Linking


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
    def sort_key(link: MediaCollectionLink) -> Tuple:
        return (
            link.season,
            link.episode,
            link.element.release_date,
            link.element.id,
        )

    @staticmethod
    def sorted(iterable: Iterable[MediaCollectionLink]) -> List[MediaCollectionLink]:
        return sorted(iterable, key=MediaCollectionLink.sort_key)


## Media Elements


class MediaElement(db.Entity, Tagable):

    id: int = orm.PrimaryKey(int, auto=True)
    uri: str = orm.Required(str, unique=True)

    title: str = orm.Optional(str)
    description: str = orm.Optional(orm.LongStr, nullable=True)
    thumbnail: MediaThumbnail = orm.Optional(lambda: MediaThumbnail)
    notes: str = orm.Optional(str)
    release_date: datetime = orm.Optional(datetime, index=True)

    extractor_name: str = orm.Optional(str)
    extractor_key: str = orm.Optional(str)
    orm.composite_index(extractor_name, extractor_key)
    last_updated: datetime = orm.Optional(datetime)

    watched: bool = orm.Required(bool, column="watched", default=False)
    ignored: bool = orm.Required(bool, column="ignored", default=False)
    progress: int = orm.Required(int, default=0)
    length: int = orm.Optional(int)

    tag_list: Iterable[Tag] = orm.Set(lambda: Tag)
    uris: Iterable[MediaUriMapping] = orm.Set(lambda: MediaUriMapping)
    collection_links: Iterable[MediaCollectionLink] = orm.Set(
        lambda: MediaCollectionLink
    )

    blocked_by: Set[MediaElement] = orm.Set(lambda: MediaElement, reverse="is_blocking")
    is_blocking: Set[MediaElement] = orm.Set(lambda: MediaElement, reverse="blocked_by")

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
            return is_considered(self.id)
        if self.skip_over:
            return False
        if self.release_date > datetime.now():
            return False
        if orm.exists(e for e in self.blocked_by if not e.skip_over):
            return False
        ordered_collections: Query[MediaCollection] = orm.select(
            l.collection
            for l in self.collection_links
            if l.collection.watch_in_order
        )
        for collection in ordered_collections:
            next = collection.next_episode
            if next is not None and self != next.element:
                return False
        return True

    @property
    def assigned_tags(self) -> Set[Tag]:
        return set(self.tag_list)

    @property
    def inherited_tags(self) -> Set[Tag]:
        result = set()
        for link in self.collection_links:
            result |= link.collection.direct_tags
        return result

    def merge_to(self, other: MediaElement):
        if self.watched:
            other.watched = True
        if self.ignored:
            other.ignored = True
        if self.progress >= 0 and other.progress <= 0:
            other.progress = self.progress
        for uri_map in self.uris:
            uri_map.element = other
        for link in self.collection_links:
            if not MediaCollectionLink.get(collection=link.collection, element=other):
                link.element = other
        self.delete()  # will also delete still existing uri mappings and collection links
        orm.flush()

    def add_single_uri(self, uri: str) -> bool:
        mapping: MediaUriMapping = MediaUriMapping.get(uri=uri)
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

    def add_uris(self, uri_list: Iterable[str]) -> bool:
        return all(self.add_single_uri(uri) for uri in set(uri_list))

    def before_insert(self):
        self.before_update()

    def before_update(self):
        self.add_single_uri(self.uri)

    @property
    def info_link(self):
        return f"/media/{self.id}"


class MediaThumbnail(db.Entity):

    id: int = orm.PrimaryKey(int, auto=True)
    uri: str = orm.Required(str, unique=True)
    last_downloaded: datetime = orm.Optional(datetime, default=None, nullable=True)
    last_accessed: datetime = orm.Optional(datetime, default=None, nullable=True)
    mime_type: str = orm.Optional(str, default="")
    data: bytes = orm.Optional(bytes, default=None, nullable=True, lazy=True)

    elements: Set[MediaElement] = orm.Set(lambda: MediaElement)

    @classmethod
    def from_uri(cls, uri: str) -> MediaThumbnail:
        return cls.get(uri=uri) or MediaThumbnail(uri=uri)

    def access(self):
        self.last_accessed = datetime.now()

    def download(self) -> bool:
        res = requests.get(url=self.uri, headers=THUMBNAIL_HEADERS)
        mime = magic.from_buffer(res.content, mime=True)
        if mime not in THUMBNAIL_ALLOWED_TYPES:
            return False
        self.mime_type = mime
        self.data = res.content
        self.last_downloaded = datetime.now()
        return True

    def prepare(self) -> bool:
        if self.last_downloaded is not None:
            return True
        return self.download()

    def access_data(self):
        self.prepare()
        self.access()

    def receive_data(self) -> bytes:
        self.access_data()
        return self.data


class MediaUriMapping(db.Entity):

    id: int = orm.PrimaryKey(int, auto=True)
    uri: str = orm.Required(str, unique=True)
    element: MediaElement = orm.Required(MediaElement)


## Media Collections


class MediaCollection(db.Entity, Tagable):

    id: int = orm.PrimaryKey(int, auto=True)
    uri: str = orm.Required(str, unique=True)

    title: str = orm.Optional(str)
    notes: str = orm.Optional(str)
    release_date: datetime = orm.Optional(datetime)
    creator: MediaCollection = orm.Optional(lambda: MediaCollection, nullable=True)

    extractor_name: str = orm.Optional(str)
    extractor_key: str = orm.Optional(str)
    orm.composite_index(extractor_name, extractor_key)
    last_updated: datetime = orm.Optional(datetime)

    keep_updated: bool = orm.Required(bool, default=False)
    watch_in_order_auto: bool = orm.Required(bool, default=True)

    pinned: bool = orm.Required(bool, default=False)
    ignored: bool = orm.Required(bool, default=False)
    watch_in_order: bool = orm.Required(bool, default=True)

    tag_list: Iterable[Tag] = orm.Set(lambda: Tag)
    uris: Iterable[CollectionUriMapping] = orm.Set(lambda: CollectionUriMapping)
    media_links: Iterable[MediaCollectionLink] = orm.Set(MediaCollectionLink)
    created_collections: Set[MediaCollection] = orm.Set(lambda: MediaCollection)

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
    def completed(self) -> bool:
        return self.__to_watch_episodes().count() <= 0

    @property
    def assigned_tags(self) -> Set[Tag]:
        return set(self.tag_list)

    @property
    def stats(self) -> CollectionStats:
        return CollectionStats.from_collection(self)

    def add_episode(
        self, media: MediaElement, season: int = 0, episode: int = 0
    ) -> MediaCollectionLink:
        link: MediaCollectionLink = MediaCollectionLink.get(
            collection=self, element=media
        )
        if link is None:
            link = MediaCollectionLink(collection=self, element=media)
        link.season, link.episode = season, episode
        orm.flush()
        return link

    def add_single_uri(self, uri: str) -> bool:
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

    def add_uris(self, uri_list: Iterable[str]) -> bool:
        return all(self.add_single_uri(uri) for uri in set(uri_list))

    def before_insert(self):
        self.before_update()

    def before_update(self):
        self.add_single_uri(self.uri)

    @property
    def info_link(self):
        return f"/collection/{self.id}"


class CollectionUriMapping(db.Entity):

    id: int = orm.PrimaryKey(int, auto=True)
    uri: str = orm.Required(str, unique=True)
    element: MediaCollection = orm.Required(MediaCollection)


SQL_WHITESPACE_PATTERN = re.compile(r"(\s|\n)+")


def sql_cleanup(sql: str) -> str:
    return SQL_WHITESPACE_PATTERN.sub(" ", sql).strip()


def sql_where_in(id: str, id_list: Iterable[str | int]) -> str:
    return f"{id} IN ({','.join(str(i) for i in id_list)})"


# TODO reducing cache table to only contain videos not watched/ignored (not huge speedup)
# TODO add bool for (not)? blocking to direct dependencies (similar to above) (not huge speedup)
def sql_is_considered(elem_id: str, use_cache: bool = True) -> str:
    # NOT EXISTS seems worlds better then making a OUTER JOIN
    return sql_cleanup(
        f"""
            NOT EXISTS (
        """
        + (
            f"""
                SELECT c.element2
                FROM element_lookup_cache c
                        INNER JOIN mediaelement m2 ON c.element1 = m2.id
                WHERE c.element2 = {elem_id} AND NOT (m2.watched OR m2.ignored)
            """
            if use_cache
            else f"""
                SELECT *
                FROM mediaelement look_elem
                        INNER JOIN mediacollectionlink link ON link.element = look_elem.id
                        INNER JOIN mediacollection coll ON coll.id = link.collection
                        INNER JOIN mediacollectionlink coll_link ON coll_link.collection = coll.id
                        INNER JOIN mediaelement coll_elem ON coll_elem.id = coll_link.element
                WHERE look_elem.id = {elem_id}
                    AND coll.watch_in_order
                    AND NOT (coll_elem.watched OR coll_elem.ignored)
                    AND (coll_link.season, coll_link.episode, coll_elem.release_date, coll_elem.id) < (link.season, link.episode, look_elem.release_date, look_elem.id)
            """
        )
        + f"""
            ) AND NOT EXISTS (
                SELECT *
                FROM mediaelement_mediaelement m_m
                        INNER JOIN mediaelement m ON m_m.mediaelement = m.id
                WHERE m_m.mediaelement_2 = {elem_id} AND NOT (m.watched OR m.ignored)
            )
        """
    )


def is_considered(elem_id: int) -> bool:
    return db.exists(
        sql_cleanup(
            f"""
        SELECT elem.id
        FROM mediaelement elem
        WHERE elem.id = {elem_id}
            AND NOT (elem.watched OR elem.ignored)
            AND elem.release_date <= NOW()
            AND ({sql_is_considered('elem.id')})
    """
        )
    )


def are_multiple_considered(elem_ids: Iterable[int]) -> Mapping[int, bool]:
    res = {
        r[0]
        for r in db.execute(
            sql_cleanup(
                f"""
        SELECT elem.id
        FROM mediaelement elem
        WHERE NOT (elem.watched OR elem.ignored)
            AND elem.release_date <= NOW()
            AND ({sql_is_considered("elem.id")})
    """
            )
        )
    }
    return {elem_id: elem_id in res for elem_id in elem_ids}


def get_all_considered(
    order_by: str = "NULL", filter_by: str = "true"
) -> List[MediaElement]:
    return MediaElement.select_by_sql(
        sql_cleanup(
            f"""
        SELECT elem.*
        FROM mediaelement elem
        WHERE NOT (elem.watched OR elem.ignored)
            AND elem.release_date <= NOW()
            AND {filter_by}
            AND ({sql_is_considered("elem.id")})
        ORDER BY {order_by}
    """
        )
    )


def update_element_lookup_cache(collection_ids: List[int] = []):
    logging.info(
        f"Rebuild element_lookup_cache for {len(collection_ids) if collection_ids else 'all'} collections …"
    )

    def filter_clause(c_id: str):
        return sql_where_in(c_id, collection_ids) if collection_ids else "true"

    orm.flush()
    sql = [
        f"""
            DELETE QUICK FROM element_lookup_cache
            WHERE {filter_clause("collection")};
        """,
        f"""
            INSERT INTO element_lookup_cache (collection, element1, element2) SELECT
                c.id AS collection,
                l1.element AS element1,
                l2.element AS element2
            FROM
                mediacollection c
            INNER JOIN mediacollectionlink l1 ON
                c.id = l1.collection
            INNER JOIN mediacollectionlink l2 ON
                c.id = l2.collection
            INNER JOIN mediaelement e1 ON
                l1.element = e1.id
            INNER JOIN mediaelement e2 ON
                l2.element = e2.id
            WHERE
                (
                    l1.season,
                    l1.episode,
                    e1.release_date,
                    e1.id
                ) <(
                    l2.season,
                    l2.episode,
                    e2.release_date,
                    e2.id
                ) AND c.watch_in_order
                AND {filter_clause("c.id")}
            GROUP BY
                collection,
                element1,
                element2
        """,
    ]
    for q in sql:
        db.execute(sql_cleanup(q))


####
## Custom Table Framework
####


# TODO replace fixed table names with dynamic resolved ones
CUSTOM_TABLE_DEFINITIONS: Mapping[SafeStr, str] = {
    SafeStr(table_name): trim(table_sql)
    for table_name, table_sql in {
        "element_lookup_cache": """
            CREATE TABLE element_lookup_cache(
                collection INT(11) NOT NULL,
                element1 INT(11) NOT NULL,
                element2 INT(11) NOT NULL
            ) SELECT
                c.id AS collection,
                l1.element AS element1,
                l2.element AS element2
            FROM
                mediacollection c
            INNER JOIN mediacollectionlink l1 ON
                c.id = l1.collection
            INNER JOIN mediacollectionlink l2 ON
                c.id = l2.collection
            INNER JOIN mediaelement e1 ON
                l1.element = e1.id
            INNER JOIN mediaelement e2 ON
                l2.element = e2.id
            WHERE
                (
                    l1.season,
                    l1.episode,
                    e1.release_date,
                    e1.id
                ) <(
                    l2.season,
                    l2.episode,
                    e2.release_date,
                    e2.id
                ) AND c.watch_in_order
            GROUP BY
                collection,
                element1,
                element2;
            ALTER TABLE
                `element_lookup_cache` ADD PRIMARY KEY(`element1`, `element2`, `collection`);
            ALTER TABLE
                `element_lookup_cache` ADD INDEX(`collection`);
        """,
    }
}


def table_exists(table_name: SafeStr) -> bool:
    # TODO may be mariadb specific
    return db.exists(f"SHOW TABLE STATUS WHERE Name = '{table_name}'")


def setup_custom_tables():
    """
    Creates & fills custom tables (especially cache tables) if they do not exist.
    This should not destroy already existing data and should behave indempotent.
    """
    for table_name, table_sql in CUSTOM_TABLE_DEFINITIONS.items():
        if not table_exists(table_name):
            db.execute(table_sql)
