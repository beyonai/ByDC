"""列表术语构建业务逻辑。"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def create_list_term(
    term_name: str,
    term_type_code: str,
    domain_id: str,
    library_id: str | None,
    desc_summary: str | None,
) -> dict:
    """创建列表类术语（如员工、组织等枚举列表）。

    Args:
        term_name: 术语标准名称。
        term_type_code: 术语类型编码，必须属于列表大类（type_category=1）。
        domain_id: 所属领域ID。
        library_id: 所属术语库ID，可为空。
        desc_summary: 术语描述摘要，可为空。

    Returns:
        包含 term_id、term_name、term_type_code 的字典。

    Raises:
        ValueError: term_type_code 不属于列表类型时抛出。
    """
    raise NotImplementedError


async def update_list_term(term_id: str, **kwargs: object) -> dict:
    """更新列表术语属性。

    Args:
        term_id: 术语ID。
        **kwargs: 待更新的字段键值对。

    Returns:
        包含 term_id、term_name、updated_time 的字典。

    Raises:
        KeyError: 术语不存在时抛出。
    """
    raise NotImplementedError


async def delete_list_term(term_id: str) -> None:
    """删除列表术语及其关联关系。

    Args:
        term_id: 术语ID。

    Raises:
        KeyError: 术语不存在时抛出。
    """
    raise NotImplementedError
