"""共享辅助：prop term_id 判断与 search_scope 序列化。"""

from __future__ import annotations

import json


def _is_prop_term_id(term_id: str) -> bool:
    """判断 term_id 本身是否为属性术语，而不是属性下的值术语。"""

    parts = term_id.split("#")
    return len(parts) >= 2 and parts[-2] == "prop"


def _term_name_search_scope_payload(search_scope: dict[str, str] | None) -> str:
    """序列化 term_name.search_scope。"""
    return json.dumps(search_scope or {}, ensure_ascii=False)
