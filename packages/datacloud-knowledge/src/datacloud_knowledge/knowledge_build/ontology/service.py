"""本体术语构建业务逻辑。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def create_ontology_term(
    term_name: str,
    term_type_code: str,
    domain_id: str,
    library_id: str | None,
    owl_doc_id: str | None,
    desc_summary: str | None,
) -> dict[str, Any]:
    """创建本体术语（VIEW / OBJ / ACTION / FUNC / PARAM / PROP）。

    Args:
        term_name: 术语标准名称。
        term_type_code: 术语类型编码，必须属于本体大类（type_category=3）。
        domain_id: 所属领域ID。
        library_id: 所属术语库ID，可为空。
        owl_doc_id: OWL 本体定义文件ID，可为空。
        desc_summary: 术语描述摘要，可为空。

    Returns:
        包含 term_id、term_name、term_type_code 的字典。

    Raises:
        ValueError: term_type_code 不属于本体类型时抛出。
    """
    raise NotImplementedError


async def update_ontology_term(term_id: str, **kwargs: object) -> dict[str, Any]:
    """更新本体术语属性。

    Args:
        term_id: 术语ID。
        **kwargs: 待更新的字段键值对（term_name / desc_summary / owl_doc_id 等）。

    Returns:
        包含 term_id、term_name、updated_time 的字典。

    Raises:
        KeyError: 术语不存在时抛出。
    """
    raise NotImplementedError


async def delete_ontology_term(term_id: str) -> None:
    """删除本体术语及其关联关系。

    Args:
        term_id: 术语ID。

    Raises:
        KeyError: 术语不存在时抛出。
    """
    raise NotImplementedError
