#!/usr/bin/env python3

import argparse
import os
from pathlib import Path
from string import Template
import subprocess
from typing import (
    Any,
    Callable,
    Dict,
    Optional,
    TypeAlias,
)
import urllib.parse as url


def cmd_player_play(
    video_uri: str,
    start: Optional[str] = None,
    speed: Optional[str] = None,
) -> None:
    print(f"Play video {video_uri}")
    subprocess.Popen(
        args=[
            e
            for e in [
                str(Path("~/bin/mpvctl").expanduser()),
                "add",
                video_uri,
                # f"start={start}" if start is not None else None + "," + f"speed={speed}" if speed is not None else None,
            ]
            if e is not None
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


URI_SCHEME = "entertainment-decider"
CommandDict: TypeAlias = Dict[str, "CommandType"]
CommandType: TypeAlias = CommandDict | Callable[..., None]
URI_COMMANDS: CommandDict = {
    "player": {
        "play": cmd_player_play,
    },
}


def execute_uri_command(uri: str) -> Any:
    parts = url.urlparse(uri, scheme=URI_SCHEME, allow_fragments=False)
    if parts.scheme != URI_SCHEME:
        if parts.scheme in {"http", "https"}:
            return cmd_player_play(uri)
        raise Exception(f"Cannot parse URI's with scheme {parts.scheme!r}")
    path = parts.path.strip("/").split("/")
    options = dict(url.parse_qsl(parts.query))

    def unknown_cmd() -> None:
        raise Exception(f"Unknown command {parts.path}")

    current: Any = URI_COMMANDS
    for path_name in path:
        if callable(current) or path_name not in current:
            return unknown_cmd()
        current = current[path_name]
    if not callable(current):
        return unknown_cmd()
    return current(**options)


def misc_generate_desktop() -> None:
    template_path = os.getenv("STREAMLINED_DESKTOP_TEMPLATE") or "./entry.desktop"
    with Path(template_path).open("r") as fh:
        temp = Template(fh.read())
    print(temp.substitute(name="Entertainment Decider", exec_path=str(Path(__file__).resolve())))


MISC_COMMANDS: Dict[str, Callable[..., None]] = {
    "generate-desktop-file": misc_generate_desktop,
}


def execute_misc_cmd(cmd: str) -> None:
    if cmd not in MISC_COMMANDS:
        raise Exception(f"Unknown misc command {cmd!r}")
    return MISC_COMMANDS[cmd]()


def main() -> None:
    parser = argparse.ArgumentParser(prog="entertainment-decider")
    subparsers = parser.add_subparsers()
    # uri parser
    uri_parser = subparsers.add_parser("exec")
    uri_parser.add_argument("uri", type=str)
    uri_parser.set_defaults(parser_cmd=execute_uri_command)
    # misc parser
    misc_parser = subparsers.add_parser("misc")
    misc_parser.add_argument("cmd", type=str, choices=list(MISC_COMMANDS.keys()))
    misc_parser.set_defaults(parser_cmd=execute_misc_cmd)
    # parse args
    args = parser.parse_args()
    cmd = args.parser_cmd
    d = vars(args)
    del d["parser_cmd"]
    cmd(**d)


if __name__ == "__main__":
    main()
