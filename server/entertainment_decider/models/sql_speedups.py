from __future__ import annotations

from functools import cache
import itertools
from typing import (
    Iterable,
    List,
    Mapping,
    Sequence,
    Tuple,
)

from .entities import (
    MediaElement,
    Tag,
    db,
)
from .sql_helpers import (
    sql_cleanup,
)
from .sql_queries import (
    sql_is_considered,
)


def is_considered(elem_id: int) -> bool:
    return db.exists(
        sql_cleanup(
            f"""
        SELECT elem.id
        FROM {MediaElement._table_} elem
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
        FROM {MediaElement._table_} elem
        WHERE NOT (elem.watched OR elem.ignored)
            AND elem.release_date <= NOW()
            AND ({sql_is_considered("elem.id")})
    """
            )
        )
    }
    return {elem_id: elem_id in res for elem_id in elem_ids}


def get_all_considered(
    order_by: str = "NULL",
    filter_by: str = "true",
) -> List[MediaElement]:
    return MediaElement.select_by_sql(
        sql_cleanup(
            f"""
        SELECT elem.*
        FROM {MediaElement._table_} elem
        WHERE NOT (elem.watched OR elem.ignored)
            AND elem.release_date <= NOW()
            AND {filter_by}
            AND ({sql_is_considered("elem.id")})
        ORDER BY {order_by}
    """
        )
    )


def get_all_elements_tags_recursive() -> Mapping[int, Sequence[Tag]]:
    elem_tag_query: Iterable[Tuple[int, int]] = db.execute(
        """
        WITH RECURSIVE found_tag (mediaelement_id, tag_id) AS
        (
                SELECT mediaelement_tag.mediaelement, mediaelement_tag.tag
                FROM mediaelement_tag
            UNION
                SELECT mediacollectionlink.element, mediacollection_tag.tag
                FROM mediacollectionlink
                JOIN mediacollection_tag ON mediacollectionlink.collection = mediacollection_tag.mediacollection
            UNION
                SELECT found_tag.mediaelement_id, tag_tag.tag_2
                FROM found_tag
                JOIN tag_tag ON found_tag.tag_id = tag_tag.tag
        )
        SELECT found_tag.mediaelement_id, found_tag.tag_id
        FROM found_tag
        JOIN tag ON found_tag.tag_id = tag.id
        WHERE tag.use_for_preferences
        ORDER BY mediaelement_id, tag_id;
    """
    )

    @cache
    def get_tag(tag_id: int) -> Tag:
        return Tag[tag_id]

    return {
        elem_id: [get_tag(tag_id) for _, tag_id in group_iter]
        for elem_id, group_iter in itertools.groupby(
            elem_tag_query, key=lambda row: row[0]
        )
    }
