"""调试沙箱执行器 — 在 debug.db 中运行 Action 脚本。

注入命名空间：
    Q  — QueryWrapper 工厂（链式条件构造器）
    A  — AggWrapper 工厂（链式聚合构造器）
    {entity_code}_mapper — DebugMapper 实例
    {EntityClass}        — 实体 dataclass（带 F 内部类）
    params               — Action 入参 dict

调试执行与正式执行共享同一套 ScriptExecutor 逻辑，仅数据源不同：
  - 调试：DebugLoader（SQLite debug.db）
  - 正式：ProductionMapper（真实数据源）
"""

from __future__ import annotations

import logging
import sqlite3
import time
import traceback
from pathlib import Path
from typing import Any

from datacloud_data_sdk.wrappers import AggWrapper, QueryWrapper

logger = logging.getLogger(__name__)

_SQLITE_TYPE_MAP: dict[str, str] = {
    "STRING": "TEXT",
    "INTEGER": "INTEGER",
    "FLOAT": "REAL",
    "BOOLEAN": "INTEGER",
    "DATE": "TEXT",
}


# ── DebugLoader (SQLite backed) ───────────────────────────────────────────────


class DebugLoader:
    """基于工作区 debug.db 的 Mapper 后端，支持 QueryWrapper 和 AggWrapper。"""

    def __init__(self, db_path: Path, all_fields: dict[str, list[dict[str, Any]]]) -> None:
        self._db_path = db_path
        self._all_fields = all_fields
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """确保所有对象的 SQLite 表已创建。"""
        with sqlite3.connect(self._db_path) as conn:
            for entity_code, fields in self._all_fields.items():
                col_defs = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
                for f in fields:
                    col_name = f.get("property_code", "")
                    if not col_name or col_name.lower() == "id":
                        continue
                    sqlite_type = _SQLITE_TYPE_MAP.get(f.get("data_type", "STRING"), "TEXT")
                    col_defs.append(f"{col_name} {sqlite_type}")
                ddl = f"CREATE TABLE IF NOT EXISTS {entity_code} ({', '.join(col_defs)})"
                conn.execute(ddl)
            conn.commit()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _run_query(self, entity_code: str, payload: dict[str, Any]) -> dict[str, Any]:
        """执行 QueryWrapper 查询，返回 {records, total, meta}。"""
        where, params = self._payload_to_where(payload)
        order_clause = self._payload_to_order(payload)
        limit_clause, extra_params = self._payload_to_limit(payload)

        count_sql = f"SELECT COUNT(*) FROM {entity_code} WHERE {where}"
        data_sql = f"SELECT * FROM {entity_code} WHERE {where}{order_clause}{limit_clause}"

        with self._conn() as conn:
            total_row = conn.execute(count_sql, params).fetchone()
            total = int(total_row[0]) if total_row else 0
            rows = conn.execute(data_sql, params + extra_params).fetchall()

        records = [dict(r) for r in rows]
        cols = [{"name": k} for k in (records[0].keys() if records else [])]
        return {"records": records, "total": total, "meta": {"columns": cols, "total": total}}

    def _run_agg(self, entity_code: str, payload: dict[str, Any]) -> dict[str, Any]:
        """执行 AggWrapper 聚合，返回 {records, total, meta}。"""
        aggregates: list[dict[str, str]] = payload.get("aggregates", [])
        group_fields: list[str] = payload.get("group_by", [])
        order_fields: list[list[Any]] = payload.get("order_by", [])
        limit_n: int | None = payload.get("limit")
        where_payload: dict[str, Any] | None = payload.get("where")

        if not aggregates:
            return {"records": [], "total": 0, "meta": {"columns": [], "total": 0}}

        select_parts: list[str] = []
        for agg in aggregates:
            func = agg["func"]
            field = agg["field"]
            alias = agg.get("as", field)
            select_parts.append(f'{func}({field}) AS "{alias}"')
        for gf in group_fields:
            select_parts.append(gf)

        where_clause = "1=1"
        where_params: list[Any] = []
        if where_payload:
            where_clause, where_params = self._payload_to_where(where_payload)

        group_clause = f" GROUP BY {', '.join(group_fields)}" if group_fields else ""

        order_parts: list[str] = []
        for field, desc in order_fields:
            direction = "DESC" if desc else "ASC"
            order_parts.append(f"{field} {direction}")
        order_clause = f" ORDER BY {', '.join(order_parts)}" if order_parts else ""

        limit_clause = f" LIMIT {limit_n}" if limit_n else ""

        sql = (
            f"SELECT {', '.join(select_parts)} FROM {entity_code}"
            f" WHERE {where_clause}{group_clause}{order_clause}{limit_clause}"
        )
        with self._conn() as conn:
            rows = conn.execute(sql, where_params).fetchall()

        records = [dict(r) for r in rows]
        cols = [{"name": k} for k in (records[0].keys() if records else [])]
        return {
            "records": records,
            "total": len(records),
            "meta": {"columns": cols, "total": len(records)},
        }

    @staticmethod
    def _payload_to_where(payload: dict[str, Any]) -> tuple[str, list[Any]]:
        """提取 QueryWrapper payload 中的 WHERE 子句。"""
        q = QueryWrapper()
        q._conditions = [tuple(c) for c in payload.get("conditions", [])]  # type: ignore[misc]
        return q.to_where_sql()

    @staticmethod
    def _payload_to_order(payload: dict[str, Any]) -> str:
        order_fields: list[list[Any]] = payload.get("order_by", [])
        if not order_fields:
            return ""
        parts = [f"{f} {'DESC' if d else 'ASC'}" for f, d in order_fields]
        return f" ORDER BY {', '.join(parts)}"

    @staticmethod
    def _payload_to_limit(payload: dict[str, Any]) -> tuple[str, list[Any]]:
        page: int = payload.get("page", 1) or 1
        page_size: int | None = payload.get("page_size")
        limit_n: int | None = payload.get("limit")
        if limit_n:
            return f" LIMIT {limit_n}", []
        if page_size:
            offset = (page - 1) * page_size
            return f" LIMIT {page_size} OFFSET {offset}", []
        return "", []

    def select_by_id(self, entity_code: str, id: int) -> dict[str, Any] | None:
        sql = f"SELECT * FROM {entity_code} WHERE id = ?"
        with self._conn() as conn:
            row = conn.execute(sql, [id]).fetchone()
        return dict(row) if row else None

    def insert(self, entity_code: str, data: dict[str, Any]) -> int:
        data.pop("id", None)
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        sql = f"INSERT INTO {entity_code} ({cols}) VALUES ({placeholders})"
        with self._conn() as conn:
            cursor = conn.execute(sql, list(data.values()))
            conn.commit()
            return cursor.lastrowid or 0

    def update_by_id(self, entity_code: str, data: dict[str, Any]) -> bool:
        id_val = data.pop("id", None)
        if not id_val:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in data)
        sql = f"UPDATE {entity_code} SET {set_clause} WHERE id = ?"
        with self._conn() as conn:
            cursor = conn.execute(sql, list(data.values()) + [id_val])
            conn.commit()
            return cursor.rowcount > 0

    def delete_by_id(self, entity_code: str, id: int) -> bool:
        sql = f"DELETE FROM {entity_code} WHERE id = ?"
        with self._conn() as conn:
            cursor = conn.execute(sql, [id])
            conn.commit()
            return cursor.rowcount > 0

    def query(self, entity_code: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run_query(entity_code, payload)

    def query_one(self, entity_code: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        result = self._run_query(entity_code, payload)
        records: list[dict[str, Any]] = result.get("records", [])
        return records[0] if records else None

    def count(self, entity_code: str, payload: dict[str, Any]) -> int:
        return int(self._run_query(entity_code, payload).get("total", 0))

    def aggregate(self, entity_code: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run_agg(entity_code, payload)


# ── Dynamic entity / mapper class builders ────────────────────────────────────


def _to_class_name(entity_code: str) -> str:
    return "".join(part.capitalize() for part in entity_code.split("_"))


def _build_entity_class(entity_code: str, fields: list[dict[str, Any]]) -> type:
    """动态构建带 F 内部类的实体 dataclass。"""
    annotations: dict[str, Any] = {"id": "int | None"}
    defaults: dict[str, Any] = {"id": None}
    f_attrs: dict[str, str] = {"id": "id"}

    for f in fields:
        code = f.get("property_code", "")
        if not code or code.lower() == "id":
            continue
        annotations[code] = "Any | None"
        defaults[code] = None
        f_attrs[code] = code

    f_class = type("F", (), {**f_attrs})

    def to_dict(self: Any) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None and k != "__class__"}

    cls_attrs: dict[str, Any] = {
        "__annotations__": annotations,
        "to_dict": to_dict,
        "F": f_class,
        **defaults,
    }

    # Build as plain class with __init__ using defaults
    def __init__(self: Any, **kwargs: Any) -> None:
        for key, default in defaults.items():
            setattr(self, key, kwargs.get(key, default))

    cls_attrs["__init__"] = __init__
    class_name = _to_class_name(entity_code)
    return type(class_name, (), cls_attrs)


def _build_mapper_class(entity_code: str, entity_cls: type, loader: DebugLoader) -> Any:
    """动态构建 Mapper 实例（绑定到 loader 和 entity_cls）。"""

    class DebugMapper:
        def __init__(self) -> None:
            self._loader = loader
            self._entity_code = entity_code
            self._entity_cls = entity_cls

        async def select_by_id(self, id: int) -> Any:
            row = self._loader.select_by_id(self._entity_code, id)
            return self._entity_cls(**row) if row else None

        async def insert(self, obj: Any) -> Any:
            new_id = self._loader.insert(self._entity_code, obj.to_dict())
            obj.id = new_id
            return obj

        async def update_by_id(self, obj: Any) -> bool:
            return self._loader.update_by_id(self._entity_code, obj.to_dict())

        async def delete_by_id(self, id: int) -> bool:
            return self._loader.delete_by_id(self._entity_code, id)

        async def select(self, q: QueryWrapper) -> dict[str, Any]:
            return self._loader.query(self._entity_code, q.to_payload())

        async def select_one(self, q: QueryWrapper) -> Any:
            row = self._loader.query_one(self._entity_code, q.to_payload())
            return self._entity_cls(**row) if row else None

        async def count(self, q: QueryWrapper) -> int:
            return self._loader.count(self._entity_code, q.to_payload())

        async def agg(self, a: AggWrapper) -> dict[str, Any]:
            return self._loader.aggregate(self._entity_code, a.to_payload())

    mapper = DebugMapper()
    mapper.__class__.__name__ = f"{_to_class_name(entity_code)}Mapper"
    return mapper


# ── Main executor ─────────────────────────────────────────────────────────────


def run_action_debug(
    script: str,
    params: dict[str, Any],
    db_path: Path,
    all_fields: dict[str, list[dict[str, Any]]],
    user_code: str = "",
    user_name: str = "",
) -> dict[str, Any]:
    """在沙箱中执行 Action 脚本并返回结果或完整 traceback。

    与正式执行共享同一套 ScriptExecutor 逻辑，差异仅在数据源：
    通过 extra_namespace 注入 DebugMapper（SQLite debug.db），
    覆盖 ScriptExecutor 默认注入的 ProductionMapper。

    Args:
        script: execute(params) 函数源代码
        params: Action 入参 dict
        db_path: debug.db 路径
        all_fields: {entity_code: [field_def, ...]} 全部对象字段
        user_code: 当前用户 code（注入到 InvocationContext，脚本可通过 context.user_id 获取）
        user_name: 当前用户显示名（注入到 context.extras["user_name"]）

    Returns:
        成功: {"ok": True, "result": {...}, "elapsed_ms": N}
        失败: {"ok": False, "error": "...", "traceback": "...", "elapsed_ms": N}
    """
    import asyncio

    from datacloud_data_sdk.context import InvocationContext
    from datacloud_data_sdk.executor.script_executor import ScriptExecutor

    loader = DebugLoader(db_path, all_fields)

    extra_namespace: dict[str, Any] = {}
    for entity_code, fields in all_fields.items():
        entity_cls = _build_entity_class(entity_code, fields)
        mapper = _build_mapper_class(entity_code, entity_cls, loader)
        extra_namespace[f"{entity_code}_mapper"] = mapper
        extra_namespace[_to_class_name(entity_code)] = entity_cls

    executor = ScriptExecutor(ontology_loader=None)

    t0 = time.monotonic()
    try:
        extras: dict[str, Any] = {}
        if user_name:
            extras["user_name"] = user_name

        with InvocationContext(
            user_id=user_code,
            extras=extras or None,
        ):
            result = asyncio.run(
                executor.execute(
                    script,
                    params,
                    action_code="<debug>",
                    extra_namespace=extra_namespace,
                )
            )
        elapsed = round((time.monotonic() - t0) * 1000, 2)
        return {"ok": True, "result": result, "elapsed_ms": elapsed}
    except Exception:
        elapsed = round((time.monotonic() - t0) * 1000, 2)
        tb = traceback.format_exc()
        err_lines = [line for line in tb.splitlines() if line.strip()]
        last_error = err_lines[-1] if err_lines else "未知错误"
        return {
            "ok": False,
            "error": last_error,
            "traceback": tb,
            "elapsed_ms": elapsed,
        }
