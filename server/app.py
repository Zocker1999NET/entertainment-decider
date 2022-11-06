####
# Imports
####

from __future__ import annotations

from datetime import datetime, timedelta
from functools import partial
import io
import itertools
import logging
import os
from pathlib import Path
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
    Set,
    Type,
    TypeVar,
    Union,
)

from flask import (
    Flask,
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

from entertainment_decider import common
from entertainment_decider.models import (
    PreferenceScore,
    Query,
    Tag,
    are_multiple_considered,
    db,
    MediaCollection,
    MediaCollectionLink,
    MediaElement,
    generate_preference_list,
    get_all_considered,
    setup_custom_tables,
    update_element_lookup_cache,
)
from entertainment_decider.extractors.collection import (
    collection_extract_uri,
    collection_update,
)
from entertainment_decider.extractors.media import (
    media_extract_uri,
    media_update,
)
from entertainment_decider.extras import remove_common_trails


T = TypeVar("T")


####
# Logging Config
####


logging.basicConfig(format="%(asctime)s === %(message)s", level=logging.DEBUG)


####
# Flask Config
####


DEBUG_DATABASE = False

flask_app = Flask(
    __name__,
    static_folder=str(Path(__file__).parent / "static"),
)
flask_app.config.update(
    dict(
        CELERY=dict(),
        DEBUG=True,
        PONY=dict(
            provider="sqlite",
            filename="./db.sqlite",
            create_db=True,
        )
        if DEBUG_DATABASE
        else dict(),
    )
)


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


ConfigKeySetter = Callable[[str, Any], None]
ConfigSingleTranslator = Callable[[Any], Any]
ConfigTranslatorIterable = Iterable[ConfigSingleTranslator]
ConfigTranslatorCreator = Callable[[str], ConfigTranslatorIterable]


def config_suffixer(
    setter: ConfigKeySetter,
    prefix: str,
    lower: bool = True,
) -> ConfigTranslatorCreator:
    def creator(key: str) -> ConfigTranslatorIterable:
        if not key.startswith(prefix):
            raise Exception(f"Environment key {key!r} is missing suffix {prefix!r}")
        new_key = key[len(prefix) :]
        new_key = new_key.lower() if lower else new_key
        return (partial(setter, new_key),)

    return creator


def celery_config_setter(key: str, val: Any) -> None:
    flask_app.config["CELERY"][key] = val


celery_config_same = config_suffixer(celery_config_setter, "CELERY_")


def flask_config_setter(key: str, val: Any) -> None:
    flask_app.config[key] = val


flask_config_same = config_suffixer(flask_config_setter, "FLASK_", lower=False)


def pony_config_setter(key: str, val: Any) -> None:
    flask_app.config["PONY"][key] = val


pony_config_same = config_suffixer(pony_config_setter, "PONY_")

CONFIG_TRANSLATE_TABLE: Dict[
    str, Union[ConfigTranslatorIterable, ConfigTranslatorCreator]
] = {
    "CELERY_BROKER_URL": celery_config_same,
    "CELERY_RESULT_BACKEND": celery_config_same,
    "FLASK_DEBUG": (
        environ_bool,
        partial(flask_config_setter, "DEBUG"),
    ),
    "PONY_PROVIDER": pony_config_same,
    "PONY_FILENAME": pony_config_same,
    "PONY_CREATE_DB": (
        environ_bool,
        partial(pony_config_setter, "create_db"),
    ),
    "PONY_HOST": pony_config_same,
    "PONY_PORT": (
        environ_int,
        partial(pony_config_setter, "port"),
    ),
    "PONY_DATABASE": pony_config_same,
    "PONY_DB": pony_config_same,
    "PONY_USER": pony_config_same,
    "PONY_PASSWORD": pony_config_same,
    "PONY_PASSWD": pony_config_same,
    "PONY_DSN": pony_config_same,
}

for key, val in os.environ.items():
    trans = CONFIG_TRANSLATE_TABLE.get(key)
    if trans is not None:
        trans = trans(key) if callable(trans) else trans
        res: Any = val
        for caller in trans:
            new_res = caller(res)
            if new_res is not None:
                res = new_res


####
# Pony init
####


db.bind(**flask_app.config["PONY"])
db.generate_mapping(create_tables=True)
setup_custom_tables()

Pony(flask_app)


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
    timedelta(days=YEAR_MEAN_LENGTH_DAYS): "year",
}
TIME_SINCE_ORDER = sorted(TIME_SINCE_FORMAT.keys())


@flask_app.template_filter()
def time_since(date: datetime) -> str:
    if date is None:
        return None
    now = datetime.now()
    missing_time = common.date_to_datetime(date.date()) == date
    if missing_time:
        now = common.date_to_datetime(now.date())
    passed = now - date
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
        # TODO add default thumbnail if not found
        return make_response(f"Not found", 404)
    if element.thumbnail is None:
        return redirect("/static/thumbnail_missing.webp")
    thumb = element.thumbnail
    # TODO do not load data from database until send_file requires that
    return send_file(
        io.BytesIO(thumb.receive_data()),
        mimetype=thumb.mime_type,
        etag=True,
        as_attachment=False,
        last_modified=thumb.last_downloaded,
        max_age=24 * 60 * 60,
    )


@flask_app.route("/api/refresh/collections", methods=["POST"])
def refresh_collections() -> ResponseReturnValue:
    collection_ids = set[int](
        orm.select(c.id for c in MediaCollection if c.keep_updated)
    )
    errors = []
    failed_colls = set[int]()
    for coll_id in collection_ids:
        try:
            coll = MediaCollection[coll_id]
            collection_update(coll)
            orm.commit()
        # TODO make Exception more specific
        except Exception as e:
            orm.rollback()
            failed_colls.add(coll_id)
            coll = MediaCollection[coll_id]
            errors.append(
                {
                    "collection": {
                        "id": coll.id,
                        "title": coll.title,
                        "uri": coll.uri,
                    },
                    "error": {
                        "args": repr(e.args),
                    },
                },
            )
    # TODO detect changed collections properly to speed up cache rebuild
    # meaning check if collection really changed
    update_element_lookup_cache(collection_ids - failed_colls)
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
    collection_update(coll, check_cache_expired=False)
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
