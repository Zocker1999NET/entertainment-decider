from __future__ import annotations

from .entities import (
    Tag,
    TagKey,
)


def predefined_video_tag() -> Tag:
    return TagKey.get_or_create_tag(
        tag_key=".kind/video",
        title="Video",
        use_for_preferences=True,
    )


def predefined_movie_tag() -> Tag:
    return TagKey.get_or_create_tag(
        tag_key=".kind/video/movie",
        title="Movie",
        use_for_preferences=True,
        super_tags=[
            predefined_video_tag(),
        ],
    )


def predefined_series_tag() -> Tag:
    return TagKey.get_or_create_tag(
        tag_key=".kind/video/series",
        title="Series",
        use_for_preferences=True,
        super_tags=[
            predefined_video_tag(),
        ],
    )
