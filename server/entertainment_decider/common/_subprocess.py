import subprocess
from typing import (
    IO,
    Optional,
    Sequence,
)


def call(
    args: Sequence[str],
    check: bool = True,
    stdin: Optional[IO] = None,
) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        args,
        capture_output=True,
        check=check,
        text=True,
        stdin=stdin,
    )
    return proc
