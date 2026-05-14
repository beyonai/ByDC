"""知识包导入批量写入处理器包。

从单文件拆分到 per-entity 子模块，保持对外 API 不变。
"""

from __future__ import annotations

from datacloud_knowledge.ingestion.owl_import.importer._helpers import _execute_values  # noqa: F401
from datacloud_knowledge.ingestion.owl_import.importer.snowflake import (
    _next_snowflake_ids,  # noqa: F401
)

from ._domain import _batch_process_domain
from ._knowledge import _batch_process_knowledge
from ._library import _batch_process_library
from ._relation import (  # noqa: F401
    _batch_insert_relation_term_names,
    _batch_process_relation,
)
from ._term import (  # noqa: F401
    _batch_process_term,
    _batch_sync_term_names,
    _delete_global_prop_term_names,
)
from ._term_type import _batch_process_term_type

__all__ = [
    "_batch_process_domain",
    "_batch_process_knowledge",
    "_batch_process_library",
    "_batch_process_relation",
    "_batch_process_term",
    "_batch_process_term_type",
]
