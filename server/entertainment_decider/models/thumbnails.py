from typing import Tuple


THUMBNAIL_ALLOWED_TYPES = [
    "image/avif",
    "image/jpeg",
    "image/png",
    "image/webp",
]
THUMBNAIL_HEADERS = {
    "Accept": ",".join(THUMBNAIL_ALLOWED_TYPES) + ",*/*;q=0.9",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:91.0) Gecko/20100101 Firefox/91.0",
}
THUMBNAIL_TARGET = 16 / 9


def thumbnail_sort_key(width: int, height: int) -> Tuple:
    return (
        abs((width / height) - THUMBNAIL_TARGET),
        width * height,
    )
