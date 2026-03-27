from __future__ import annotations

import contextlib
import hashlib
from typing import BinaryIO


def md5_of_stream(stream: BinaryIO, chunk_size: int = 1024 * 1024) -> str:
    """Compute md5 hex digest for a readable binary stream.

    If the stream is seekable, its position will be restored to where it was before hashing.
    """

    hasher = hashlib.md5()  # noqa: S324
    try:
        pos = stream.tell()
        seekable = True
    except Exception:
        pos = 0
        seekable = False

    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        hasher.update(chunk)

    if seekable:
        with contextlib.suppress(Exception):
            stream.seek(pos)

    return hasher.hexdigest()
