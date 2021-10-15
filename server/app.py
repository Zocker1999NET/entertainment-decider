####
## Imports
####

from __future__ import annotations

from functools import partial
import logging
import os
from urllib.parse import urlencode, quote_plus
from typing import Any, Callable, Dict, Iterable, Optional, Union

from flask import Flask, jsonify, make_response, request, redirect
from flask.templating import render_template
from markupsafe import Markup
from pony.flask import Pony
from pony import orm

from entertainment_decider import common
from entertainment_decider.models import db, MediaCollection, MediaCollectionLink, MediaElement
from entertainment_decider.extractors.collection import collection_extract_uri
from entertainment_decider.extractors.media import media_extract_uri


####
## Logging Config
####


logging.basicConfig(format = "%(asctime)s === %(message)s", level=logging.DEBUG)


####
## Flask Config
####


flask_app = Flask(__name__)
flask_app.config.update(dict(
    CELERY = dict(
    ),
    DEBUG = True,
    PONY = dict(
        provider = "sqlite",
        filename = "./db.sqlite",
        create_db = True,
    )
))

def environ_bool(value: Union[str, bool]) -> bool:
    if type(value) == bool:
        return value
    return value.strip()[0].lower() in ["1", "t", "y"]

ConfigKeySetter: Callable[[str, Any], Any]
ConfigSingleTranslator = Callable[[Any], Any]
ConfigTranslatorIterable = Iterable[ConfigSingleTranslator]
ConfigTranslatorCreator = Callable[[str], ConfigTranslatorIterable]

def config_suffixer(setter: ConfigKeySetter, prefix: str, lower: bool = True) -> ConfigTranslatorCreator:
    def creator(key: str):
        if not key.startswith(prefix):
            raise Exception(f"Environment key {key!r} is missing suffix {prefix!r}")
        new_key = key[len(prefix):]
        new_key = new_key.lower() if lower else new_key
        return (
            partial(setter, new_key)
        )
    return creator

def celery_config_setter(key: str, val: Any):
    flask_app.config["CELERY"][key] = val

celery_config_same = config_suffixer(celery_config_setter, "CELERY_")

def flask_config_setter(key: str, val: Any):
    flask_app.config[key] = val

flask_config_same = config_suffixer(flask_config_setter, "FLASK_", lower=False)

def pony_config_setter(key: str, val: Any):
    flask_app.config["PONY"][key] = val

pony_config_same = config_suffixer(pony_config_setter, "PONY_")

CONFIG_TRANSLATE_TABLE: Dict[str, Union[ConfigTranslatorIterable, ConfigTranslatorCreator]] = {
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
            if new_res is None:
                res = res


####
## Pony init
####


db.bind(**flask_app.config["PONY"])
db.generate_mapping(create_tables=True)

Pony(flask_app)


####
## Return filters
####


@flask_app.template_filter()
def as_link(uri: str):
    uri = Markup.escape(uri)
    return Markup(f'<a href="{uri}">{uri}</a>')

@flask_app.template_filter()
def as_play_link(video_uri: str):
    opts = {
        "video_uri": video_uri,
    }
    play_uri = "entertainment-decider:///player/play?" + urlencode(opts, quote_via=quote_plus)
    return Markup(f'<a class=button href="{play_uri}">Play</a>')

@flask_app.template_filter()
def tenary(b: bool, true_str: str, false_str: str) -> str:
    return true_str if b else false_str


####
## Routes
####


@flask_app.route("/")
def hello_world():
    return '<a href=/collection>Collections</a> & <a href=/media>Media</a>'


@flask_app.route("/collection")
def list_collection():
    collection_list: Iterable[MediaCollection] = MediaCollection.select().order_by(orm.desc(MediaCollection.release_date), MediaCollection.title, MediaCollection.id)
    return render_template("collection_list.htm", collection_list=collection_list)

@flask_app.route("/collection/<int:collection_id>")
def show_collection(collection_id):
    collection: MediaCollection = MediaCollection.get(id=collection_id)
    if collection is None:
        return make_response(f"Not found", 404)
    return render_template(
        "collection_element.htm",
        collection=collection,
        media_links=MediaCollectionLink.sorted(MediaCollectionLink.select(lambda l: l.collection == collection)),
    )

@flask_app.route("/collection/<int:collection_id>", methods = ["POST"])
def update_collection(collection_id):
    collection: MediaCollection = MediaCollection.get(id=collection_id)
    if collection is None:
        return f"Not found", 404
    data: Optional[Dict] = request.get_json()
    if data is None:
        return f"JSON data missing", 400
    for key in data.keys():
        if key not in ["watch_in_order"]:
            return {
                "successful": False,
                "error": {
                    "message": f"Failed to update key {key!r} as this is not allowed to update on a collection",
                },
            }, 400
    for key, value in data.items():
        if key == "watch_in_order":
            collection.watch_in_order = common.update_bool_value(collection.watch_in_order, value)
            collection.watch_in_order_auto = False
    return {
        "successful": True,
        "error": None,
    }, 200


@flask_app.route("/media")
def list_media():
    media_list: Iterable[MediaElement] = orm.select(m for m in MediaElement if not (m.ignored or m.watched)).order_by(orm.desc(MediaElement.release_date), MediaElement.id)
    return render_template("media_list.htm", media_list=list(media_list))

@flask_app.route("/media/length")
def get_media_length():
    c = len(MediaElement.select())
    return f"{c}"

@flask_app.route("/media/<int:media_id>")
def show_media(media_id):
    element: MediaElement = MediaElement.get(id=media_id)
    if element is None:
        return make_response(f"Not found", 404)
    return render_template("media_element.htm", element=element)


@flask_app.route("/debug/test")
def test():
    first: MediaElement = MediaElement.select().first()
    return {
        "data": first.to_dict(),
    }, 200

# TODO add table for failed attempts so these may be resolved afterwards with increasing delays (add to MediaElement with flag "retrieved" and "last_updated" as date to resolve last try)


def redirect_back_or_okay():
    if "redirect" not in request.form:
        return {
            "status": True,
        }, 200
    uri = request.form.get("redirect", type=str)
    if not uri.startswith("/"):
        return "400 Bad Request : Invalid Redirect Specified", 400
    return redirect(uri)

@flask_app.route("/api/collection/list")
def api_collection_list():
    collection_list: Iterable[MediaCollection] = MediaCollection.select()
    return {
        "status": True,
        "data": [{
            "id": collection.id,
            "title": collection.title,
            "release_date": collection.release_date,
            "length": collection.length,
            "progress": collection.progress,
        } for collection in collection_list],
    }, 200

@flask_app.route("/api/collection/<int:collection_id>", methods=["GET", "POST"])
def api_collection_element(collection_id: int):
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
                "media_links": [{
                    "media": {
                        "id": link.element.id,
                        "title": link.element.title,
                    },
                    "season": link.season,
                    "episode": link.episode,
                } for link in collection.media_links]
            }
        }, 200
    elif request.method == "POST":
        data = request.form.to_dict()
        if "redirect" in data:
            del data["redirect"]
        KEY_CONVERTER = {
            "title": str,
            "notes": str,
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
        if "watch_in_order" in data: # TODO move to property
            collection.watch_in_order_auto = False
        collection.set(**{key: KEY_CONVERTER[key](val) for key, val in data.items()})
        return redirect_back_or_okay()
    else:
        return {
            "status": False,
            "error": "405 Method Not Allowed",
        }, 405

@flask_app.route("/api/media/list")
def api_media_list():
    media_list: Iterable[MediaElement] = MediaElement.select()
    return {
        "status": True,
        "data": [{
            "id": media.id,
            "title": media.title,
            "release_date": media.release_date,
            "length": media.length,
            "progress": media.progress,
        } for media in media_list],
    }, 200

@flask_app.route("/api/media/<int:media_id>", methods=["GET", "POST"])
def api_media_element(media_id: int):
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
                "collection_links": [{
                    "collection": {
                        "id": link.collection.id,
                        "title": link.collection.title,
                    },
                    "season": link.season,
                    "episode": link.episode,
                } for link in element.collection_links]
            }
        }, 200
    elif request.method == "POST":
        data = request.form.to_dict()
        if "redirect" in data:
            del data["redirect"]
        KEY_CONVERTER = {
            "title": str,
            "notes": str,
            "progress": int,
            "ignored": environ_bool,
            "watched": environ_bool,
        }
        for key in data:
            if key not in KEY_CONVERTER:
                return {
                    "status": False,
                    "error": f"Cannot set key {key!r} on MediaElement",
                }, 400
        element.set(**{key: KEY_CONVERTER[key](val) for key, val in data.items()})
        return redirect_back_or_okay()
    else:
        return {
            "status": False,
            "error": "405 Method Not Allowed",
        }, 405
