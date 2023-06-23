# TODO check that some queries check DB integrity like:
# SELECT e.uri FROM mediaelment e LEFT JOIN mediaurimapping m ON e.uri = m.uri WHERE m.uri IS NULL;
# SELECT e.uri FROM mediacollection e LEFT JOIN collectionurimapping m ON e.uri = m.uri WHERE m.uri IS NULL;

####
# Imports
####

from __future__ import annotations

from datetime import datetime, timedelta
import io
import itertools
import logging
import re
from urllib.parse import urlencode, quote_plus
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
)

from flask import (
    make_response,
    redirect,
    request,
    Response,
    send_file,
    url_for,
)
from flask.templating import render_template
from flask.typing import ResponseReturnValue
from markupsafe import Markup
from pony.flask import Pony
from pony import orm

from entertainment_decider import (
    common,
    create_app,
)
from entertainment_decider.models import (
    MediaCollection,
    MediaCollectionLink,
    MediaElement,
    MediaThumbnail,
    Query,
    Tag,
    are_multiple_considered,
    db,
    get_all_considered,
    setup_custom_tables,
    update_element_lookup_cache,
)
from entertainment_decider.preferences import PreferenceScore, generate_preference_list
from entertainment_decider.extractors.collection import (
    collection_extract_uri,
    collection_update,
)
from entertainment_decider.extractors.media import (
    media_extract_uri,
    media_update,
)
from entertainment_decider.extras import (
    remove_common_trails,
)


T = TypeVar("T")


def adapt_score_list(
    base: Optional[PreferenceScore] = None,
    tag_points_mapping: Dict[int, int] = {},
) -> PreferenceScore:
    o = base or PreferenceScore()
    for tag_id, points in tag_points_mapping.items():
        o = o.adapt_score(Tag[tag_id], points, on_hierachy=False)
    return o


####
# Logging Config
####


logging.basicConfig(
    format="%(asctime)s - %(name)s === %(levelname)s: %(message)s",
    level=logging.DEBUG,
)


####
# Flask Config
####


flask_app = create_app()


def environ_bool(value: Union[str, bool]) -> bool:
    if type(value) == bool:
        return value
    return value.strip()[0].lower() in ["1", "t", "y"]


def environ_int(value: Union[str, int]) -> int:
    if type(value) == int:
        return value
    return int(value)


TIMEDELTA_PATTERN = re.compile(
    r"^(((?P<hours>\d+):)?(?P<minutes>\d+):)?(?P<seconds>\d+)$"
)


def environ_timedelta(value: Union[int, str, timedelta]) -> timedelta:
    if isinstance(value, timedelta):
        return value
    elif isinstance(value, str):
        m = TIMEDELTA_PATTERN.search(value)
        if not m:
            raise Exception(f"Could not parse {value!r} as timestamp")
        return timedelta(
            hours=int(m.group("hours") or 0),
            minutes=int(m.group("minutes") or 0),
            seconds=int(m.group("seconds")),
        )
    elif isinstance(value, int):
        return timedelta(seconds=value)
    else:
        raise Exception(f"Unknown type {type(value)}")


def environ_timedelta_seconds(value: Union[int, str, timedelta]) -> int:
    if isinstance(value, int):
        return value
    return environ_timedelta(value) // timedelta(seconds=1)


####
# Pony init
####


db.bind(**flask_app.config.get_namespace("PONY_"))
db.generate_mapping(create_tables=True)
setup_custom_tables()

Pony(flask_app)


####
# Settings helpers
####


PREFERENCES_SCORE_NAME = "score_adapt"


####
# Return filters
####


@flask_app.template_filter()
def encode_options(opts: Mapping[str, Any]) -> str:
    return urlencode({k: str(v) for k, v in opts.items()}, quote_via=quote_plus)


@flask_app.template_filter()
def first_and_only(list: Sequence[T]) -> Optional[T]:
    return list[0] if len(list) == 1 else None


@flask_app.template_global()
def this_url(changed_args: Mapping[str, str] = {}) -> str:
    if request.endpoint is None:
        raise Exception(
            "this_url can only be used after successful endpoint matching (request.endpoint is still None)"
        )
    view_args = dict(request.view_args or {})
    get_args = request.args.to_dict()
    get_args.update(changed_args)
    return url_for(request.endpoint, **view_args) + (
        f"?{encode_options(get_args)}" if get_args else ""
    )


@flask_app.template_filter()
def as_link(uri: str) -> Markup:
    uri = Markup.escape(uri)
    return Markup(f'<a href="{uri}">{uri}</a>')


@flask_app.template_filter()
def tenary(b: bool, true_str: str, false_str: str) -> str:
    return true_str if b else false_str


TIMEDELTA_FORMAT = (
    timedelta(hours=1),
    timedelta(minutes=1),
)


@flask_app.template_filter("timedelta")
def _filter_timedelta(seconds: Optional[int]) -> Optional[str]:
    if seconds is None:
        return None
    delta = timedelta(seconds=seconds)
    ret = ""
    for unit in TIMEDELTA_FORMAT:
        if ret or unit <= delta:
            unit_size = delta // unit
            delta -= unit * unit_size
            if ret:
                ret += f"{unit_size:02}:"
            else:
                ret += f"{unit_size}:"
    ret += f"{delta.seconds:02}"
    return ret


YEAR_MEAN_LENGTH_DAYS = 365.2425
TIME_SINCE_FORMAT = {
    timedelta(hours=1): "hour",
    timedelta(days=1): "day",
    timedelta(days=7): "week",
    timedelta(days=YEAR_MEAN_LENGTH_DAYS / 12): "month",
}
TIME_SINCE_ORDER = sorted(TIME_SINCE_FORMAT.keys())
TIME_SINCE_MAX_REL = timedelta(days=YEAR_MEAN_LENGTH_DAYS)


@flask_app.template_filter()
def time_since(date: datetime) -> str:
    if date is None:
        return None
    now = datetime.now()
    missing_time = common.date_to_datetime(date.date()) == date
    if missing_time:
        now = common.date_to_datetime(now.date())
    passed = now - date
    if not (timedelta() <= passed < TIME_SINCE_MAX_REL):
        # return short format
        return date.strftime("%Y-%m")
    last_thres = None
    for threshold in TIME_SINCE_ORDER:
        if passed < threshold:
            break
        last_thres = threshold
    if last_thres is not None:
        passed_thres = passed // last_thres
        return f"{passed_thres} {TIME_SINCE_FORMAT[last_thres]}{'s' if passed_thres > 1 else ''}"
    return "today" if missing_time else "now"


@flask_app.template_filter("are_considered")
def _template_are_multiple_considered(elem_ids: Iterable[int]) -> Mapping[int, bool]:
    return are_multiple_considered(elem_ids)


####
# Routes
####


def _parse_cs_ids(cs_ids: str) -> List[int] | None:
    try:
        return [int(i) for i in cs_ids.split(",")]
    except ValueError as e:
        return None


def _select_ids(cls: Type[T], ids: Iterable[int]) -> Query[T]:
    return orm.select(o for o in cls if o.id in ids)


@flask_app.teardown_request
def merge_query_stats(*_: Any, **__: Any) -> None:
    db.merge_local_stats()


@flask_app.route("/")
def dashboard() -> ResponseReturnValue:
    # config
    began_limit = 8
    pinned_limit = 16
    media_limit = 24
    already_listed = set[MediaElement]()
    # for began videos
    began_videos: Iterable[MediaElement] = orm.select(
        m for m in MediaElement if m.started
    ).order_by(MediaElement.release_date, MediaElement.title, MediaElement.id)
    began_videos = list(common.limit_iter(began_videos, began_limit))
    already_listed.update(began_videos)
    # for links from pinned collections
    pinned_collections: Iterable[MediaCollection] = orm.select(
        m for m in MediaCollection if m.pinned and not m.ignored
    ).order_by(MediaCollection.release_date, MediaCollection.title, MediaCollection.id)
    links_from_pinned_collections_set = set[MediaCollectionLink]()
    for coll in pinned_collections:
        next_link = coll.next_episode
        if (
            next_link is not None
            and next_link not in links_from_pinned_collections_set
            and next_link.element not in already_listed
            and next_link.element.can_considered
        ):
            links_from_pinned_collections_set.add(next_link)
    links_from_pinned_collections = sorted(
        links_from_pinned_collections_set,
        key=lambda l: l.element.release_date,
    )[:pinned_limit]
    already_listed.update(link.element for link in links_from_pinned_collections)
    # for media
    media_list: Iterable[MediaElement] = get_all_considered(
        order_by="elem.release_date DESC, elem.id",
    )
    limited_media = common.limit_iter(media_list, media_limit)
    # render
    return render_template(
        "dashboard.htm",
        began_videos=began_videos,
        links_from_pinned_collections=links_from_pinned_collections,
        media_list=limited_media,
    )


def _list_collections(collections: Iterable[MediaCollection]) -> ResponseReturnValue:
    return render_template(
        "collection_list.htm",
        collection_list=list(collections),
    )


def _list_collections_by_filter(
    filter: Callable[[MediaCollection], bool] = lambda _: True,
) -> ResponseReturnValue:
    collection_list: Iterable[MediaCollection] = orm.select(
        c for c in MediaCollection if filter(c)
    ).order_by(
        orm.desc(MediaCollection.release_date),
        MediaCollection.title,
        MediaCollection.id,
    )
    return _list_collections(collection_list)


@flask_app.route("/collection")
def list_collection() -> ResponseReturnValue:
    return _list_collections_by_filter(lambda coll: coll.is_root_collection)


@flask_app.route("/collection/all")
def list_collection_all() -> ResponseReturnValue:
    return _list_collections_by_filter()


@flask_app.route("/collection/extract")
def extract_collection() -> ResponseReturnValue:
    return render_template("collection_extract.htm")


@flask_app.route("/collection/overview")
def list_collection_overview() -> ResponseReturnValue:
    data = request.args.to_dict()
    ids = _parse_cs_ids(data.get("ids", "NULL"))
    if not ids:
        return {
            "status": False,
            "error": {
                "msg": "Could not parse id list",
                "data": {
                    "ids": data.get("ids"),
                },
            },
        }
    return _list_collections(_select_ids(MediaCollection, ids))


@flask_app.route("/collection/to_watch")
def list_collections_with_unwatched() -> ResponseReturnValue:
    return _list_collections_by_filter(
        lambda coll: coll.is_root_collection and not coll.ignored and not coll.completed
    )


@flask_app.route("/collection/pinned")
def list_pinned_collection() -> ResponseReturnValue:
    collection_list: Iterable[MediaCollection] = orm.select(
        c for c in MediaCollection if c.pinned
    ).order_by(
        orm.desc(MediaCollection.release_date),
        MediaCollection.title,
        MediaCollection.id,
    )
    return render_template("collection_list.htm", collection_list=collection_list)


@flask_app.route("/collection/<int:collection_id>")
def show_collection(collection_id: int) -> ResponseReturnValue:
    SMALL_COLLECTION_MAX_COUNT = 100
    collection: MediaCollection = MediaCollection.get(id=collection_id)
    if collection is None:
        return make_response(f"Not found", 404)
    media_links = (
        MediaCollectionLink.sorted(
            MediaCollectionLink.select(lambda l: l.collection == collection)
        )
        if orm.count(collection.media_links) <= SMALL_COLLECTION_MAX_COUNT
        else None
    )
    media_titles = (
        remove_common_trails([link.element.title for link in media_links])
        if media_links is not None
        else None
    )
    return render_template(
        "collection_element.htm",
        collection=collection,
        media_links=media_links,
        media_titles=media_titles,
    )


@flask_app.route("/collection/<int:collection_id>/episodes")
def show_collection_episodes(collection_id: int) -> ResponseReturnValue:
    collection: MediaCollection = MediaCollection.get(id=collection_id)
    if collection is None:
        return make_response(f"Not found", 404)
    media_links = MediaCollectionLink.sorted(
        MediaCollectionLink.select(lambda l: l.collection == collection)
    )
    media_titles = remove_common_trails([link.element.title for link in media_links])
    return render_template(
        "collection_episodes.htm",
        collection=collection,
        media_links=media_links,
        media_titles=media_titles,
    )


@flask_app.route("/media")
def list_media() -> ResponseReturnValue:
    media_list: Iterable[MediaElement] = get_all_considered(
        "elem.release_date DESC, elem.id"
    )
    return render_template(
        "media_list.htm",
        media_list=common.limit_iter(media_list, 100),
        check_considered=False,
    )


@flask_app.route("/media/short")
@flask_app.route("/media/short/<int:seconds>")
def list_short_media(seconds: int = 10 * 60) -> ResponseReturnValue:
    media_list: Iterable[MediaElement] = get_all_considered(
        filter_by=f"(length - progress) <= {seconds}",
        order_by="elem.release_date DESC, elem.id",
    )
    return render_template(
        "media_list.htm",
        media_list=list(itertools.islice(media_list, 100)),
        check_considered=False,
    )


@flask_app.route("/media/long")
@flask_app.route("/media/long/<int:seconds>")
def list_long_media(seconds: int = 10 * 60) -> ResponseReturnValue:
    media_list: Iterable[MediaElement] = get_all_considered(
        filter_by=f"{seconds} <= (length - progress)",
        order_by="elem.release_date DESC, elem.id",
    )
    return render_template(
        "media_list.htm",
        media_list=list(itertools.islice(media_list, 100)),
        check_considered=False,
    )


@flask_app.route("/media/overview")
def list_media_overview() -> ResponseReturnValue:
    data = request.args.to_dict()
    ids = _parse_cs_ids(data.get("ids", "NULL"))
    if not ids:
        return {
            "status": False,
            "error": {
                "msg": "Could not parse id list",
                "data": {
                    "ids": data.get("ids"),
                },
            },
        }
    return render_template(
        "media_list.htm",
        media_list=_select_ids(MediaElement, ids),
        check_considered=False,
    )


@flask_app.route("/media/unsorted")
def list_unsorted_media() -> ResponseReturnValue:
    media_list: Iterable[MediaElement] = orm.select(
        m for m in MediaElement if len(m.collection_links) == 0
    ).order_by(orm.desc(MediaElement.release_date), MediaElement.id)
    return render_template(
        "media_list.htm",
        media_list=media_list,
        check_considered=True,
    )


@flask_app.route("/media/extract")
def extract_media() -> ResponseReturnValue:
    return render_template("media_extract.htm")


@flask_app.route("/media/<int:media_id>")
def show_media(media_id: int) -> ResponseReturnValue:
    element: MediaElement = MediaElement.get(id=media_id)
    if element is None:
        return make_response(f"Not found", 404)
    return render_template("media_element.htm", element=element)


@flask_app.route("/media/<int:media_id>/thumbnail")
def show_media_thumb(media_id: int) -> ResponseReturnValue:
    element: MediaElement = MediaElement.get(id=media_id)
    if element is None:
        # do send only 404 (not default thumbnail) as element does not exist (so cannot even have default)
        return make_response(f"Not found", 404)
    if element.thumbnail is None:
        # TODO send 404 along default thumbnail
        return redirect("/static/thumbnail_missing.webp")
    return redirect(
        url_for(
            endpoint=show_thumb.__name__,
            thumbnail_id=element.thumbnail.id,
        )
    )


@flask_app.route("/thumbnail/<int:thumbnail_id>")
def show_thumb(thumbnail_id: int) -> ResponseReturnValue:
    thumbnail: MediaThumbnail = MediaThumbnail.get(id=thumbnail_id)
    if thumbnail is None:
        # do send only 404 (not default thumbnail) as invalid id was requested
        return make_response(f"Not found", 404)
    thumb_cache = thumbnail.receive()
    # TODO do not load data from database until send_file requires that
    return send_file(
        io.BytesIO(thumb_cache.access_data()),
        mimetype=thumb_cache.mime_type,
        etag=True,
        as_attachment=False,
        last_modified=thumb_cache.last_downloaded,
        max_age=24 * 60 * 60,
    )


@flask_app.route("/recommendations/short_filler")
def recommend_short_filler() -> ResponseReturnValue:
    return render_template(
        "recommendations_simple.htm",
        mode_name="Short Fillers",
        media_list=generate_preference_list(
            object_gen=lambda: get_all_considered(
                filter_by="length <= 15*60",
                order_by="elem.release_date DESC",
            ),
            score_adapt=1,
            limit=24,
        ),
    )


@flask_app.route("/recommendations/series_episode")
def recommend_series_episode() -> ResponseReturnValue:
    return render_template(
        "recommendations_simple.htm",
        mode_name="Series Episodes",
        media_list=generate_preference_list(
            object_gen=lambda: get_all_considered(
                filter_by="15*60 <= length and length <= 45*60",
                order_by="elem.release_date DESC",
            ),
            score_adapt=1,
            limit=16,
        ),
    )


@flask_app.route("/recommendations/movie_like")
def recommend_movie_like() -> ResponseReturnValue:
    return render_template(
        "recommendations_simple.htm",
        mode_name="Movie Like",
        media_list=generate_preference_list(
            object_gen=lambda: get_all_considered(
                filter_by="45*60 <= length",
                order_by="elem.release_date DESC",
            ),
            score_adapt=1,
            limit=16,
        ),
    )


@flask_app.route("/recommendations/based_on/media/<int:media_id>")
@flask_app.route("/media/<int:media_id>/recommendations")
def recommend_on_media(media_id: int) -> ResponseReturnValue:
    MEDIA_COUNT = 10
    SCORE_ADAPT = 1
    media_base = MediaElement[media_id]
    # to ensure all shown videos have similarity to selected one
    base = PreferenceScore().adapt_score(media_base, -(MEDIA_COUNT * SCORE_ADAPT) - 1)
    return render_template(
        "recommendations_simple.htm",
        mode_name=f'"{media_base.title}"',
        media_list=generate_preference_list(
            object_gen=lambda: get_all_considered("elem.release_date DESC"),
            score_adapt=SCORE_ADAPT,
            base=base,
            limit=MEDIA_COUNT,
        ),
    )


@flask_app.route("/recommendations/adaptive")
def recommend_adaptive() -> ResponseReturnValue:
    score_adapt = request.args.get("score_adapt", default=2, type=int)
    preferences = request.cookies.get(
        key=PREFERENCES_SCORE_NAME,
        default=PreferenceScore(),
        type=PreferenceScore.from_base64,
    ) * (1 if score_adapt > 0 else -1 if score_adapt < 0 else 0)
    if "max_length" not in request.args:
        # ask for max length before calculating to save time
        return render_template(
            "recommendations_adaptive.htm",
            max_length=0,
            score_adapt=score_adapt,
            preferences=preferences,
            media_list=None,
        )
    max_length = request.args.get("max_length", default=0, type=int)
    preference_list = generate_preference_list(
        object_gen=lambda: get_all_considered(
            order_by="elem.release_date DESC",
            filter_by=f"(length - progress) <= {max_length * 60}"
            if max_length > 0
            else "true",
        ),
        score_adapt=score_adapt,
        base=preferences,
        limit=32,
    )
    resp = make_response(
        render_template(
            "recommendations_adaptive.htm",
            max_length=max_length,
            score_adapt=score_adapt,
            preferences=preferences,
            media_list=preference_list,
        )
    )
    return resp


@flask_app.route("/maintenance")
def maintenance_page() -> ResponseReturnValue:
    return render_template("maintenance/main.htm")


def cookies_rating(negative: bool) -> ResponseReturnValue:
    media_id = request.form.get("media_id", default=None, type=str)
    element = MediaElement.get(id=media_id) if media_id else None
    if element is None:
        return "Not found", 404
    preferences = request.cookies.get(
        key=PREFERENCES_SCORE_NAME,
        default=PreferenceScore(),
        type=PreferenceScore.from_base64,
    ).adapt_score(element, score=3 if negative else -3)
    resp = redirect_back_or_okay()
    resp.set_cookie(PREFERENCES_SCORE_NAME, preferences.to_base64())
    return resp


@flask_app.route("/cookies/rating/positive", methods=["POST"])
def cookies_rating_positive() -> ResponseReturnValue:
    return cookies_rating(False)


@flask_app.route("/cookies/rating/negative", methods=["POST"])
def cookies_rating_negative() -> ResponseReturnValue:
    return cookies_rating(True)


@flask_app.route("/cookies/rating/reset", methods=["POST"])
def cookies_rating_reset() -> ResponseReturnValue:
    resp = redirect_back_or_okay()
    resp.delete_cookie(key=PREFERENCES_SCORE_NAME)
    return resp


@flask_app.route("/api/refresh/collections", methods=["POST"])
def refresh_collections() -> ResponseReturnValue:
    collection_ids = set[int](
        orm.select(c.id for c in MediaCollection if c.keep_updated)
    )
    errors = []
    changed_colls = list[int]()
    for coll_id in collection_ids:
        coll = MediaCollection[coll_id]
        try:
            change_state = collection_update(coll)
            orm.commit()
            if change_state.may_has_changed:
                changed_colls.append(coll_id)
        # TODO make Exception more specific
        except Exception as e:
            orm.rollback()
            errors.append(
                {
                    "collection": {
                        "id": coll.id,
                        "title": coll.title,
                        "uri": coll.primary_uri,
                    },
                    "error": {
                        "args": repr(e.args),
                    },
                },
            )
    update_element_lookup_cache(changed_colls)
    if errors:
        return (
            {
                "status": False,
                "error": {
                    "msg": "Failed to update all collections successfully",
                    "data": errors,
                },
            },
            501,
        )
    return redirect_back_or_okay()


@flask_app.route("/api/refresh/collection/<int:collection_id>", methods=["POST"])
def force_refresh_collection(collection_id: int) -> ResponseReturnValue:
    coll: MediaCollection = MediaCollection.get(id=collection_id)
    if coll is None:
        return "404 Not Found", 404
    state = collection_update(coll, check_cache_expired=False)
    if state.may_has_changed:
        update_element_lookup_cache((coll.id,))
    return redirect_back_or_okay()


@flask_app.route("/api/refresh/media/<int:media_id>", methods=["POST"])
def force_refresh_media(media_id: int) -> ResponseReturnValue:
    elem: MediaElement = MediaElement.get(id=media_id)
    if elem is None:
        return "404 Not Found", 404
    media_update(elem, check_cache_expired=False)
    return redirect_back_or_okay()


@flask_app.route("/stats")
def show_stats() -> ResponseReturnValue:
    elements: List[MediaElement] = MediaElement.select()
    collections: List[MediaCollection] = MediaCollection.select()
    return render_template(
        "stats/main.htm",
        stats={
            "last_updated": orm.max(c.last_updated for c in collections),
            "media": {
                "known": orm.count(elements),
                "known_seconds": orm.sum(m.length for m in elements),
                "watched": orm.count(m for m in elements if m.watched),
                "watched_seconds": orm.sum(
                    (m.length if m.watched else m.progress)
                    for m in elements
                    if m.watched
                ),
                "ignored": orm.count(m for m in elements if m.ignored),
                "ignored_seconds": orm.sum(
                    m.length - m.progress for m in elements if m.ignored
                ),
                "to_watch": orm.count(
                    m for m in elements if not m.ignored and not m.watched
                ),
                "to_watch_seconds": orm.sum(
                    m.length - m.progress
                    for m in elements
                    if not m.ignored and not m.watched
                ),
            },
        },
    )


@flask_app.route("/stats/queries")
def show_stats_queries() -> ResponseReturnValue:
    stats = sorted(db.global_stats.values(), key=lambda s: s.sum_time, reverse=True)
    return render_template(
        "stats/queries.htm",
        stats=stats,
    )


@flask_app.route("/tag")
def show_tag() -> ResponseReturnValue:
    tag_list: List[Tag] = Tag.select()
    return render_template(
        "tag_list.htm",
        tag_list=tag_list,
    )


@flask_app.route("/debug/test")
def test() -> ResponseReturnValue:
    first: MediaElement = MediaElement.select().first()
    return {
        "data": first.to_dict(),
    }, 200


# TODO add table for failed attempts so these may be resolved afterwards with increasing delays (add to MediaElement with flag "retrieved" and "last_updated" as date to resolve last try)


def redirect_back_or_okay() -> Response:
    if "redirect" not in request.form:
        return make_response(
            {
                "status": True,
            },
            200,
        )
    uri = request.form.get("redirect", type=str)
    if uri is None:
        raise Exception(f"IllegalState: uri should be set as checked before, but isn't")
    if not uri.startswith("/"):
        return make_response(
            "400 Bad Request : Invalid Redirect Specified",
            400,
        )
    return redirect(uri)


@flask_app.route("/api/collection/list")
def api_collection_list() -> ResponseReturnValue:
    collection_list: Iterable[MediaCollection] = MediaCollection.select()
    return {
        "status": True,
        "data": [
            {
                "id": collection.id,
                "title": collection.title,
                "release_date": collection.release_date,
                "length": collection.length,
                "progress": collection.progress,
            }
            for collection in collection_list
        ],
    }, 200


@flask_app.route("/api/collection/extract", methods=["POST"])
def api_collection_extract() -> ResponseReturnValue:
    data = request.form.to_dict()
    if "uri" not in data:
        return {
            "status": False,
            "error": f"Missing uri value to extract",
        }
    c = collection_extract_uri(data["uri"])
    orm.flush()
    if c:
        update_element_lookup_cache([c.id])
    if c and environ_bool(data.get("redirect_to_object", False)):
        return redirect(c.info_link)
    return redirect_back_or_okay()


@flask_app.route("/api/collection/extract/mass", methods=["POST"])
def api_collection_extract_mass() -> ResponseReturnValue:
    data = request.form.to_dict()
    if "uris" not in data:
        return {
            "status": False,
            "error": f"Missing uri value to extract",
        }
    uris = [
        u
        for u in (u.strip() for u in data["uris"].replace("\r\n", "\n").split("\n"))
        if u and not u.startswith("#")
    ]
    coll_ids = list[int]()
    errors = []
    for u in uris:
        try:
            coll = collection_extract_uri(u)
            coll_ids.append(coll.id)
            orm.commit()
        except Exception as e:
            orm.rollback()
            errors.append(
                {
                    "uri": u,
                    "error": {
                        "type": repr(type(e)),
                        "args": repr(e.args),
                    },
                }
            )
    if errors:
        return {
            "status": False,
            "successful_collections": coll_ids,
            "error": {
                "msg": "Failed to update all collections successfully",
                "data": errors,
            },
        }, 501
    if coll_ids:
        update_element_lookup_cache(coll_ids)
    if coll_ids and environ_bool(data.get("redirect_to_overview", False)):
        return redirect(
            "/collection/overview?ids=" + ",".join(str(i) for i in coll_ids)
        )
    return {
        "status": True,
        "successful_collections": coll_ids,
    }


@flask_app.route("/api/collection/<int:collection_id>", methods=["GET", "POST"])
def api_collection_element(collection_id: int) -> ResponseReturnValue:
    collection: MediaCollection = MediaCollection.get(id=collection_id)
    if collection is None:
        return {
            "status": False,
            "error": f"Object not found",
        }, 404
    if request.method == "GET":
        return {
            "status": True,
            "data": {
                "id": collection.id,
                "title": collection.title,
                "notes": collection.notes,
                "release_date": collection.release_date,
                "ignored": collection.ignored,
                "media_links": [
                    {
                        "media": {
                            "id": link.element.id,
                            "title": link.element.title,
                        },
                        "season": link.season,
                        "episode": link.episode,
                    }
                    for link in collection.media_links
                ],
            },
        }, 200
    elif request.method == "POST":
        data = request.form.to_dict()
        if "redirect" in data:
            del data["redirect"]
        if data.get("reset_ignored_marks", False):
            for m in orm.select(
                l.element for l in collection.media_links if l.element.ignored
            ):
                m.watched = False
                m.ignored = False
            del data["reset_ignored_marks"]
        if data.get("reset_marks", False):
            for m in orm.select(
                l.element for l in collection.media_links if l.element.skip_over
            ):
                m.watched = False
                m.ignored = False
            del data["reset_marks"]
        if "mark_unmarked_as" in data:
            val = data["mark_unmarked_as"]
            query = orm.select(
                l.element for l in collection.media_links if not l.element.skip_over
            )
            if val == "watched":
                for m in query:
                    m.watched = True
            elif val == "ignored":
                for m in query:
                    m.ignored = True
            del data["mark_unmarked_as"]
        KEY_CONVERTER: Mapping[str, Callable[[str], Any]] = {
            "title": str,
            "notes": str,
            "pinned": environ_bool,
            "ignored": environ_bool,
            "keep_updated": environ_bool,
            "watch_in_order": environ_bool,
        }
        for key in data:
            if key not in KEY_CONVERTER:
                return {
                    "status": False,
                    "error": f"Cannot set key {key!r} on MediaCollection",
                }, 400
        collection.set(**{key: KEY_CONVERTER[key](val) for key, val in data.items()})
        if "watch_in_order" in data:  # TODO move both to property inside class
            collection.watch_in_order_auto = False
            update_element_lookup_cache([collection.id])
        return redirect_back_or_okay()
    else:
        return {
            "status": False,
            "error": "405 Method Not Allowed",
        }, 405


@flask_app.route("/api/collection/<int:collection_id>", methods=["DELETE"])
@flask_app.route("/api/collection/<int:collection_id>/delete", methods=["POST"])
def api_collection_delete(collection_id: int) -> ResponseReturnValue:
    collection: MediaCollection = MediaCollection.get(id=collection_id)
    if collection is None:
        return {
            "status": False,
            "error": f"Object not found",
        }, 404
    collection.delete()
    return redirect_back_or_okay()


@flask_app.route("/api/media/list")
def api_media_list() -> ResponseReturnValue:
    media_list: Iterable[MediaElement] = MediaElement.select()
    return {
        "status": True,
        "data": [
            {
                "id": media.id,
                "title": media.title,
                "release_date": media.release_date,
                "length": media.length,
                "progress": media.progress,
            }
            for media in media_list
        ],
    }, 200


@flask_app.route("/api/media/extract", methods=["POST"])
def api_media_extract() -> ResponseReturnValue:
    data = request.form.to_dict()
    if "uri" not in data:
        return {
            "status": False,
            "error": f"Missing uri value to extract",
        }
    m = media_extract_uri(data["uri"])
    orm.flush()
    if m and environ_bool(data.get("redirect_to_object", False)):
        return redirect(m.info_link)
    return redirect_back_or_okay()


@flask_app.route("/api/media/extract/mass", methods=["POST"])
def api_media_extract_mass() -> ResponseReturnValue:
    data = request.form.to_dict()
    if "uris" not in data:
        return {
            "status": False,
            "error": f"Missing uri value to extract",
        }
    uris = [
        u
        for u in (u.strip() for u in data["uris"].replace("\r\n", "\n").split("\n"))
        if u and not u.startswith("#")
    ]
    media_ids = list[int]()
    errors = []
    for u in uris:
        try:
            media = media_extract_uri(u)
            media_ids.append(media.id)
            orm.commit()
        except Exception as e:
            orm.rollback()
            errors.append(
                {
                    "uri": u,
                    "error": {
                        "type": repr(type(e)),
                        "args": repr(e.args),
                    },
                }
            )
    if errors:
        return {
            "status": False,
            "successful_medias": media_ids,
            "error": {
                "msg": "Failed to update all medias successfully",
                "data": errors,
            },
        }, 501
    if media_ids and environ_bool(data.get("redirect_to_overview", False)):
        return redirect("/media/overview?ids=" + ",".join(str(i) for i in media_ids))
    return {
        "status": True,
        "successful_medias": media_ids,
    }


@flask_app.route("/api/media/<int:media_id>", methods=["GET", "POST"])
def api_media_element(media_id: int) -> ResponseReturnValue:
    element: MediaElement = MediaElement.get(id=media_id)
    if element is None:
        return {
            "status": False,
            "error": f"Object not found",
        }, 404
    if request.method == "GET":
        return {
            "status": True,
            "data": {
                "id": element.id,
                "title": element.title,
                "notes": element.notes,
                "release_date": element.release_date,
                "length": element.length,
                "progress": element.progress,
                "ignored": element.ignored,
                "watched": element.watched,
                "can_considered": element.can_considered,
                "collection_links": [
                    {
                        "collection": {
                            "id": link.collection.id,
                            "title": link.collection.title,
                        },
                        "season": link.season,
                        "episode": link.episode,
                    }
                    for link in element.collection_links
                ],
            },
        }, 200
    elif request.method == "POST":
        data = request.form.to_dict()
        if "redirect" in data:
            del data["redirect"]
        KEY_CONVERTER: Mapping[str, Callable[[str], Any]] = {
            "title": str,
            "notes": str,
            "progress": environ_timedelta_seconds,
            "ignored": environ_bool,
            "watched": environ_bool,
        }
        for key in data:
            if key not in KEY_CONVERTER:
                return {
                    "status": False,
                    "error": f"Cannot set key {key!r} on MediaElement",
                }, 400
        parsed_data = {key: KEY_CONVERTER[key](val) for key, val in data.items()}
        element.set(**parsed_data)
        resp = redirect_back_or_okay()
        return resp
    else:
        return {
            "status": False,
            "error": "405 Method Not Allowed",
        }, 405


@flask_app.route("/api/media/add_blocking", methods=["POST"])
def api_media_add_blocking() -> ResponseReturnValue:
    data = request.form.to_dict()
    blocked_by_id = data.get("blocked_by")
    is_blocking_id = data.get("is_blocking")
    blocked_by: Optional[MediaElement] = (
        MediaElement.get(id=blocked_by_id) if blocked_by_id else None
    )
    is_blocking: Optional[MediaElement] = (
        MediaElement.get(id=is_blocking_id) if is_blocking_id else None
    )
    if not blocked_by or not is_blocking:
        return {
            "status": False,
            "error": f"Object not found",
        }, 404
    blocked_by.is_blocking.add(is_blocking)
    return redirect_back_or_okay()


@flask_app.route("/api/media/remove_blocking", methods=["POST"])
def api_media_remove_blocking() -> ResponseReturnValue:
    data = request.form.to_dict()
    blocked_by_id = data.get("blocked_by")
    is_blocking_id = data.get("is_blocking")
    blocked_by: Optional[MediaElement] = (
        MediaElement.get(id=blocked_by_id) if blocked_by_id else None
    )
    is_blocking: Optional[MediaElement] = (
        MediaElement.get(id=is_blocking_id) if is_blocking_id else None
    )
    if not blocked_by or not is_blocking:
        return {
            "status": False,
            "error": f"Object not found",
        }, 404
    blocked_by.is_blocking.remove(is_blocking)
    return redirect_back_or_okay()


def _api_media_set_x(call: Callable[[MediaElement], Any]) -> ResponseReturnValue:
    data = request.form.to_dict()
    ids = _parse_cs_ids(data.get("ids", "NULL"))
    if not ids:
        return {
            "status": False,
            "error": {
                "msg": "Could not parse id list",
                "data": {
                    "ids": data.get("ids"),
                },
            },
        }
    for m in _select_ids(MediaElement, ids):
        call(m)
    return redirect_back_or_okay()


@flask_app.route("/api/media/set_watched", methods=["POST"])
def api_media_set_watched() -> ResponseReturnValue:
    def call(m: MediaElement) -> None:
        m.watched = True
        m.ignored = False  # TODO move into class

    return _api_media_set_x(call)


@flask_app.route("/api/media/set_ignored", methods=["POST"])
def api_media_set_ignored() -> ResponseReturnValue:
    def call(m: MediaElement) -> None:
        m.watched = False  # TODO move into class
        m.ignored = True

    return _api_media_set_x(call)


@flask_app.route("/api/media/set_dependent", methods=["POST"])
def api_media_set_dependent() -> ResponseReturnValue:
    data = request.form.to_dict()
    ids = _parse_cs_ids(data.get("ids", "NULL"))
    if not ids:
        return {
            "status": False,
            "error": {
                "msg": "Could not parse id list",
                "data": {
                    "ids": data.get("ids"),
                },
            },
        }
    elements: Query[MediaElement] = _select_ids(MediaElement, ids).order_by(
        MediaElement.release_date
    )
    for last, cur in common.iter_lookahead(common.fix_iter(elements)):
        last.is_blocking.add(cur)
    return redirect_back_or_okay()


@flask_app.route("/api/tag/delete_temporary", methods=["POST"])
def api_tag_delete_temporary() -> ResponseReturnValue:
    Tag.scrub_temporary_tags()
    return redirect_back_or_okay()
