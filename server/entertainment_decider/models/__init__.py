from .cache_tables import (
    setup_custom_tables,
    update_element_lookup_cache,
)

from .custom_types import (
    Query,
    SafeStr,
)

from .db import (
    db,
)

from .entities import (
    CollectionStats,
    CollectionUriMapping,
    MediaCollection,
    MediaCollectionLink,
    MediaElement,
    MediaThumbnail,
    MediaThumbnailCache,
    MediaUriMapping,
    Tag,
    Tagable,
    TagKey,
)

from .predefined_tags import (
    predefined_movie_tag,
    predefined_series_tag,
    predefined_video_tag,
)

from .sql_speedups import (
    are_multiple_considered,
    get_all_considered,
    get_all_elements_tags_recursive,
)

from .thumbnails import (
    thumbnail_sort_key,
)


__all__ = [
    "CollectionStats",
    "CollectionUriMapping",
    "MediaCollection",
    "MediaCollectionLink",
    "MediaElement",
    "MediaThumbnail",
    "MediaThumbnailCache",
    "MediaUriMapping",
    "Query",
    "SafeStr",
    "Tag",
    "Tagable",
    "TagKey",
    "are_multiple_considered",
    "db",
    "get_all_considered",
    "get_all_elements_tags_recursive",
    "predefined_movie_tag",
    "predefined_series_tag",
    "predefined_video_tag",
    "setup_custom_tables",
    "thumbnail_sort_key",
    "update_element_lookup_cache",
]
