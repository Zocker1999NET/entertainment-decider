from __future__ import annotations

import logging
from typing import (
    List,
    Mapping,
)

from pony import orm

from .custom_types import SafeStr
from .entities import (
    db,
)
from .sql_helpers import (
    sql_cleanup,
    sql_where_in,
)
from .sql_names import (
    COLLECTION_TABLE,
    COLLECTION_LINK_TABLE,
    ELEMENT_TABLE,
    ELEMENT_BLOCKING_CACHE_TABLE,
)
from ..common import trim
from ..extras import LazyValue


CUSTOM_TABLE_DEFINITIONS: Mapping[SafeStr, LazyValue[str]] = {
    SafeStr(table_name): lambda: trim(table_sql())
    for table_name, table_sql in {
        ELEMENT_BLOCKING_CACHE_TABLE: lambda: f"""
            CREATE TABLE {ELEMENT_BLOCKING_CACHE_TABLE}(
                collection INT(11) NOT NULL,
                element1 INT(11) NOT NULL,
                element2 INT(11) NOT NULL
            ) SELECT
                c.id AS collection,
                l1.element AS element1,
                l2.element AS element2
            FROM
                {COLLECTION_TABLE} c
            INNER JOIN {COLLECTION_LINK_TABLE} l1 ON
                c.id = l1.collection
            INNER JOIN {COLLECTION_LINK_TABLE} l2 ON
                c.id = l2.collection
            INNER JOIN {ELEMENT_TABLE} e1 ON
                l1.element = e1.id
            INNER JOIN {ELEMENT_TABLE} e2 ON
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
                `{ELEMENT_BLOCKING_CACHE_TABLE}` ADD PRIMARY KEY(`element1`, `element2`, `collection`);
            ALTER TABLE
                `{ELEMENT_BLOCKING_CACHE_TABLE}` ADD INDEX(`collection`);
        """,
    }.items()
}


def table_exists(table_name: SafeStr) -> bool:
    return db.provider.table_exists(
        connection=db.get_connection(),
        table_name=table_name,
    )


@orm.db_session
def setup_custom_tables() -> None:
    """
    Creates & fills custom tables (especially cache tables) if they do not exist.
    This should not destroy already existing data and should behave indempotent.
    """
    for table_name, table_sql in CUSTOM_TABLE_DEFINITIONS.items():
        if not table_exists(table_name):
            db.execute(table_sql())


def update_element_lookup_cache(collection_ids: List[int] = []):
    logging.info(
        f"Rebuild {ELEMENT_BLOCKING_CACHE_TABLE} for {len(collection_ids) if collection_ids else 'all'} collections …"
    )

    def filter_clause(c_id: str):
        return sql_where_in(c_id, collection_ids) if collection_ids else "true"

    orm.flush()
    sql = [
        f"""
            DELETE QUICK FROM {ELEMENT_BLOCKING_CACHE_TABLE}
            WHERE {filter_clause("collection")};
        """,
        f"""
            INSERT INTO {ELEMENT_BLOCKING_CACHE_TABLE} (collection, element1, element2) SELECT
                c.id AS collection,
                l1.element AS element1,
                l2.element AS element2
            FROM
                {COLLECTION_TABLE} c
            INNER JOIN {COLLECTION_LINK_TABLE} l1 ON
                c.id = l1.collection
            INNER JOIN {COLLECTION_LINK_TABLE} l2 ON
                c.id = l2.collection
            INNER JOIN {ELEMENT_TABLE} e1 ON
                l1.element = e1.id
            INNER JOIN {ELEMENT_TABLE} e2 ON
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
