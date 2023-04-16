from __future__ import annotations

from .entities import (
    MediaCollection,
    MediaCollectionLink,
    MediaElement,
)
from .sql_helpers import (
    sql_cleanup,
)
from .sql_names import (
    ELEMENT_BLOCKING_CACHE_TABLE,
)


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
                FROM {ELEMENT_BLOCKING_CACHE_TABLE} c
                        INNER JOIN {MediaElement._table_} m2 ON c.element1 = m2.id
                WHERE c.element2 = {elem_id} AND NOT (m2.watched OR m2.ignored)
            """
            if use_cache
            else f"""
                SELECT *
                FROM {MediaElement._table_} look_elem
                        INNER JOIN {MediaCollectionLink._table_} link ON link.element = look_elem.id
                        INNER JOIN {MediaCollection._table_} coll ON coll.id = link.collection
                        INNER JOIN {MediaCollectionLink._table_} coll_link ON coll_link.collection = coll.id
                        INNER JOIN {MediaElement._table_} coll_elem ON coll_elem.id = coll_link.element
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
                        INNER JOIN {MediaElement._table_} m ON m_m.mediaelement = m.id
                WHERE m_m.mediaelement_2 = {elem_id} AND NOT (m.watched OR m.ignored)
            )
        """
    )
