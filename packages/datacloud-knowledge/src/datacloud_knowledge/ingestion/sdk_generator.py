"""SDK 生成器 — 为工作区对象生成 Python dataclass + Mapper + F 内部类。

生成的 SDK 结构：
    @dataclass
    class TravelApplication:
        id: int | None = None
        status: str | None = None
        ...

        class F:
            id = "id"
            status = "status"
            ...

    class TravelApplicationMapper:
        def select_by_id(self, id: int) -> TravelApplication | None: ...
        def insert(self, obj: TravelApplication) -> TravelApplication: ...
        def update_by_id(self, obj: TravelApplication) -> bool: ...
        def delete_by_id(self, id: int) -> bool: ...
        def select(self, q) -> dict: ...
        def select_one(self, q) -> TravelApplication | None: ...
        def count(self, q) -> int: ...
        def agg(self, a) -> dict: ...
        # Per-DIMENSION field: select_by_<field>(value)
        # Per-MEASURE field: sum_<field>(q=None), avg_<field>(q=None)
"""

from __future__ import annotations

import textwrap
from typing import Any

_PYTHON_TYPE_MAP: dict[str, str] = {
    "STRING": "str",
    "INTEGER": "int",
    "FLOAT": "float",
    "BOOLEAN": "bool",
    "DATE": "str",
}

_DEFAULT_MAP: dict[str, str] = {
    "STRING": '""',
    "INTEGER": "0",
    "FLOAT": "0.0",
    "BOOLEAN": "False",
    "DATE": '""',
}


def _to_class_name(entity_code: str) -> str:
    """snake_case → CamelCase."""
    return "".join(part.capitalize() for part in entity_code.split("_"))


def _py_type(data_type: str) -> str:
    return _PYTHON_TYPE_MAP.get(data_type, "str")


def _py_default(data_type: str) -> str:
    return _DEFAULT_MAP.get(data_type, "None")


def _render_dataclass(class_name: str, fields: list[dict[str, Any]]) -> str:
    """生成 @dataclass 类体（不含 F 内部类）。"""
    lines: list[str] = [
        "@dataclass",
        f"class {class_name}:",
        '    """实体数据类。"""',
        "    id: int | None = None",
    ]
    for f in fields:
        code = f.get("property_code", "")
        if not code or code.lower() == "id":
            continue
        dt = f.get("data_type", "STRING")
        py_t = _py_type(dt)
        lines.append(f"    {code}: {py_t} | None = None")

    lines.append("")
    lines.append("    def to_dict(self) -> dict:")
    lines.append("        return {k: v for k, v in self.__dict__.items() if v is not None}")

    return "\n".join(lines)


def _render_f_class(fields: list[dict[str, Any]]) -> str:
    """生成 F 内部类（字段名常量）。"""
    lines: list[str] = [
        "    class F:",
        '        """字段名常量，用于 QueryWrapper / AggWrapper，避免拼写错误。"""',
        '        id = "id"',
    ]
    for f in fields:
        code = f.get("property_code", "")
        if not code or code.lower() == "id":
            continue
        lines.append(f'        {code} = "{code}"')
    return "\n".join(lines)


def _render_mapper(class_name: str, entity_code: str, fields: list[dict[str, Any]]) -> str:
    """生成 Mapper 类。"""
    mapper_name = f"{class_name}Mapper"

    # Collect semantic (DIMENSION) and stat (MEASURE) fields for shortcuts
    dimension_fields: list[str] = []
    measure_fields: list[str] = []
    for f in fields:
        code = f.get("property_code", "")
        if not code or code.lower() == "id":
            continue
        role_rule = (f.get("ext_property") or {}).get("property_role_rule", {})
        role = role_rule.get("property_role", "")
        if role == "DIMENSION":
            dimension_fields.append(code)
        elif role == "MEASURE":
            measure_fields.append(code)

    body: list[str] = [
        f"class {mapper_name}:",
        f'    """Mapper for {class_name}. Injected as {entity_code}_mapper in Action scripts."""',
        "",
        "    def __init__(self, loader: Any) -> None:",
        "        self._loader = loader",
        "",
        f"    def select_by_id(self, id: int) -> {class_name} | None:",
        '        """按主键查询单条记录。"""',
        "        result = self._loader.select_by_id(",
        f'            "{entity_code}", id',
        "        )",
        f"        return {class_name}(**result) if result else None",
        "",
        f"    def insert(self, obj: {class_name}) -> {class_name}:",
        '        """插入记录，返回含自增 id 的实体。"""',
        "        new_id = self._loader.insert(",
        f'            "{entity_code}", obj.to_dict()',
        "        )",
        "        obj.id = new_id",
        "        return obj",
        "",
        f"    def update_by_id(self, obj: {class_name}) -> bool:",
        '        """按 id 更新记录。"""',
        f'        return self._loader.update_by_id(            "{entity_code}", obj.to_dict()',
        "        )",
        "",
        "    def delete_by_id(self, id: int) -> bool:",
        '        """按主键删除记录。"""',
        f'        return self._loader.delete_by_id(            "{entity_code}", id',
        "        )",
        "",
        "    def select(self, q: Any) -> dict[str, Any]:",
        '        """条件查询，返回 {records, total, meta}。"""',
        "        return self._loader.query("
        f'            "{entity_code}", q.to_payload() if hasattr(q, "to_payload") else q',
        "        )",
        "",
        f"    def select_one(self, q: Any) -> {class_name} | None:",
        '        """条件查询第一条，返回实体或 None。"""',
        "        result = self._loader.query_one(",
        f'            "{entity_code}", q.to_payload() if hasattr(q, "to_payload") else q',
        "        )",
        f"        return {class_name}(**result) if result else None",
        "",
        "    def count(self, q: Any) -> int:",
        '        """条件计数。"""',
        "        return self._loader.count("
        f'            "{entity_code}", q.to_payload() if hasattr(q, "to_payload") else q',
        "        )",
        "",
        "    def agg(self, a: Any) -> dict[str, Any]:",
        '        """聚合查询，返回 {records, total, meta}。"""',
        "        return self._loader.aggregate("
        f'            "{entity_code}", a.to_payload() if hasattr(a, "to_payload") else a',
        "        )",
    ]

    # Semantic shortcuts: select_by_<field>
    for field_code in dimension_fields:
        dt = next(
            (f.get("data_type", "STRING") for f in fields if f.get("property_code") == field_code),
            "STRING",
        )
        py_t = _py_type(dt)
        body += [
            "",
            f"    def select_by_{field_code}(self, value: {py_t}) -> dict[str, Any]:",
            f'        """按 {field_code} 查询记录列表。"""',
            f"        return self.select(Q.eq({class_name}.F.{field_code}, value))",
        ]

    # Stat shortcuts: sum_<field>, avg_<field>
    for field_code in measure_fields:
        body += [
            "",
            f"    def sum_{field_code}(self, q: Any = None) -> float:",
            f'        """对 {field_code} 求和。"""',
            f"        wrapper = A.sum({class_name}.F.{field_code})",
            "        if q is not None:",
            "            wrapper = wrapper.where(q)",
            "        result = self.agg(wrapper)",
            '        rows = result.get("records", [])',
            f'        return float(rows[0].get("{field_code}", 0)) if rows else 0.0',
            "",
            f"    def avg_{field_code}(self, q: Any = None) -> float:",
            f'        """对 {field_code} 求平均。"""',
            f"        wrapper = A.avg({class_name}.F.{field_code})",
            "        if q is not None:",
            "            wrapper = wrapper.where(q)",
            "        result = self.agg(wrapper)",
            '        rows = result.get("records", [])',
            f'        return float(rows[0].get("{field_code}", 0)) if rows else 0.0',
        ]

    return "\n".join(body)


def generate_mapper_sdk(
    entity_code: str,
    entity_name: str,
    fields: list[dict[str, Any]],
) -> str:
    """生成完整的 SDK 源代码字符串。

    Args:
        entity_code: 实体编码（snake_case）
        entity_name: 实体中文名
        fields: 字段定义列表

    Returns:
        可执行的 Python 源代码字符串
    """
    class_name = _to_class_name(entity_code)

    header = textwrap.dedent(f"""\
        # AUTO-GENERATED SDK — {entity_name} ({entity_code})
        # 请勿手动修改，由 ontology-builder batch-submit 自动生成
        from __future__ import annotations

        from dataclasses import dataclass
        from typing import Any

        # Q / A 由执行环境注入，此处仅做类型占位
        try:
            Q  # noqa: F821
            A  # noqa: F821
        except NameError:
            Q = None  # type: ignore[assignment]
            A = None  # type: ignore[assignment]
    """)

    dataclass_block = _render_dataclass(class_name, fields)
    f_class_block = _render_f_class(fields)
    mapper_block = _render_mapper(class_name, entity_code, fields)

    # Combine: dataclass body + F inner class
    entity_block = dataclass_block + "\n\n" + f_class_block

    return "\n\n".join([header, entity_block, "", mapper_block])
