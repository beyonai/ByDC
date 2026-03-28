from __future__ import annotations

from typing import TYPE_CHECKING, BinaryIO, Protocol

if TYPE_CHECKING:
    from datacloud_knowledge.file_store.types import JsonDict, PutOutcome


class FileStorageBackend(Protocol):
    def exists(self, md5: str) -> bool: ...

    def put(self, directory: str, md5: str, stream: BinaryIO, meta: JsonDict) -> PutOutcome: ...

    def get(self, md5: str) -> tuple[BinaryIO, JsonDict]: ...

    def get_meta(self, md5: str) -> JsonDict: ...
