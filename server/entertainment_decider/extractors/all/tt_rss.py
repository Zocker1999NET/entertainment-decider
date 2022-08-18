from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import partial
import logging
import re
from typing import Dict, List, Optional
import urllib.parse as url

from tinytinypy import Connection
from tinytinypy.main import Headline


logger = logging.getLogger(__name__)


@dataclass
class TtRssConnectionParameter:
    host: str
    username: str
    password: str
    proto: str = "https"
    endpoint: str = "/api/"


TT_RSS_CONNECTION: Connection = None

HeadlineList = List[Headline]


def _build_connection(params: TtRssConnectionParameter) -> Connection:
    global TT_RSS_CONNECTION
    if TT_RSS_CONNECTION is None:
        TT_RSS_CONNECTION = Connection(
            proto=params.proto, host=params.host, endpoint=params.endpoint
        )
    if not TT_RSS_CONNECTION.isLoggedIn():
        TT_RSS_CONNECTION.login(username=params.username, password=params.password)
    return TT_RSS_CONNECTION


def get_headlines(params: TtRssConnectionParameter, **kwargs) -> HeadlineList:
    conn = _build_connection(params)
    if "limit" in kwargs:
        kwargs["limit"] = int(kwargs["limit"])
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Request headlines from tt-rss: {kwargs!r}")
    headlines = conn.getHeadlines(**kwargs)
    logger.debug(f"Got {len(headlines)} headlines from tt-rss using: {kwargs!r}")
    return headlines


class TtRssUriKind(Enum):
    ALL = ("all", lambda id: get_headlines)
    CATEGORY = ("category", lambda id: partial(get_headlines, cat_id=id))
    FEED = ("feed", lambda id: partial(get_headlines, feed_id=id))

    @property
    def path_name(self) -> str:
        return self.value[0]

    @property
    def request(self):
        return self.value[1]

    @classmethod
    def from_path_name(cls, name: str) -> "TtRssUriKind":
        for e in cls:
            if e.path_name.lower() == name.lower():
                return e
        raise KeyError()


@dataclass
class TtRssUri:

    supported_kinds = "|".join(re.escape(n.path_name.lower()) for n in TtRssUriKind)
    scheme = "tt-rss"
    path_re = re.compile(
        rf"^/((?P<all>all)|(?P<kind>{supported_kinds})/(?P<id>-?\d+))/?$"
    )

    kind: TtRssUriKind
    id: Optional[str]
    options: Dict[str, str]

    @classmethod
    def uri_suitable(cls, uri: str) -> bool:
        parts = url.urlparse(uri)
        return parts.scheme == cls.scheme

    @classmethod
    def from_str_uri(cls, uri: str) -> "TtRssUri":
        parts = url.urlparse(uri, scheme=cls.scheme)
        if parts.scheme != cls.scheme:
            raise Exception(f"Invalid scheme for tt-rss uri: {parts.scheme!r}")
        if (parts.netloc, parts.params, parts.fragment) != ("", "", ""):
            raise Exception(f"tt-rss uris do not accept netloc, params and fragments")
        m = cls.path_re.search(parts.path)
        if m is None:
            raise Exception(f"Could not parse path of tt-rss uri: {parts.path!r}")
        return TtRssUri(
            kind=TtRssUriKind.ALL
            if m.group("all")
            else TtRssUriKind.from_path_name(m.group("kind")),
            id=m.group("id"),
            options={
                single[0]: single[1]
                for single in (single.split("=") for single in parts.query.split("&"))
            }
            if parts.query
            else {},
        )

    def request(self, params: TtRssConnectionParameter, **kwargs) -> HeadlineList:
        return self.kind.request(self.id)(params, **self.options, **kwargs)
