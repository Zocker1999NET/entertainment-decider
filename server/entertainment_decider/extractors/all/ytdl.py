from __future__ import annotations

import json
import subprocess
from typing import List

from jsoncache import ApplicationCache

from ...common import call


cache = ApplicationCache(
    app_name="entertainment-decider-ytdl",
    create_cache_dir=True,
    default_max_age=86400,
)
cache.clean_cache()

YTDL_CALL = [
    "yt-dlp",
]


class YtdlErrorException(subprocess.CalledProcessError):
    pass


def ytdl_call(args: List[str]) -> dict:
    proc = call(YTDL_CALL + args, check=False)
    if proc.returncode != 0:
        raise YtdlErrorException(
            returncode=proc.returncode,
            cmd=args,
            output=proc.stdout,
            stderr=proc.stderr,
        )
    return json.loads(proc.stdout.strip())


@cache.cache_json()
def get_video_info(uri: str) -> dict:
    return ytdl_call(
        [
            "--no-playlist",
            "--dump-json",
            uri,
        ]
    )


@cache.cache_json()
def get_playlist_info(uri: str) -> dict:
    return ytdl_call(
        [
            "--yes-playlist",
            "--dump-single-json",
            uri,
        ]
    )
