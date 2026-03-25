"""对象间关联关系模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Relation:
    """对象间关联关系。"""

    from_object: str
    to_object: str
    cardinality: str
    join_keys: list[dict[str, str]]
    description: str = ""
