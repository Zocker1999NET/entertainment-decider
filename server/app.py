####
## Imports
####

from __future__ import annotations

from functools import partial
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional, Union

from flask import Flask, jsonify, make_response, request
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
    media_list: Iterable[MediaElement] = MediaElement.select().order_by(orm.desc(MediaElement.release_date), MediaElement.id)
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

# TODO add table for failed attempts so these may be resolved afterwards with increasing delays (add to MediaElement with flag "retrieved" and "extractor_cache_date" as date to resolve last try)


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
