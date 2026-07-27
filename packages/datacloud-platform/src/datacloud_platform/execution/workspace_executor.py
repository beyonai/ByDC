"""工作区 Action 调试沙箱执行器。

在 SQLite debug.db 中运行 Action 脚本，注入与正式执行一致的命名空间：
    Q  — QueryWrapper 工厂（链式条件构造器）
    A  — AggWrapper 工厂（链式聚合构造器）
    {entity_code}_mapper — DebugMapper 实例
    {EntityClass}        — 实体动态类（带 F 内部类和 to_dict）
    params               — Action 入参 dict
    context              — InvocationContext（当前请求上下文）
    httpx                — HTTP 客户端模块（如果已安装）

与正式执行共享同一套脚本执行逻辑，仅数据源不同：
  - 调试：DebugLoader（SQLite debug.db）
  - 正式：由上层注入生产环境 Mapper
"""

from __future__ import annotations

import asyncio
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
    """基于 SQLite 的 Mapper 后端，支持 QueryWrapper 和 AggWrapper。

    实现与 ProductionMapper 相同的方法签名，Action 脚本无需区分环境。
    """

    def __init__(
        self, db_path: Path, all_fields: dict[str, list[dict[str, Any]]]
    ) -> None:
        self._db_path = db_path
        self._all_fields = all_fields
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """确保所有对象的 SQLite 表已创建（幂等）。"""
        with sqlite3.connect(str(self._db_path)) as conn:
            for entity_code, fields in self._all_fields.items():
                col_defs = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
                for f in fields:
                    col_name = f.get("property_code", "")
                    if not col_name or col_name.lower() == "id":
                        continue
                    sqlite_type = _SQLITE_TYPE_MAP.get(
                        f.get("data_type", "STRING"), "TEXT"
                    )
                    col_defs.append(f"{col_name} {sqlite_type}")
                ddl = (
                    f"CREATE TABLE IF NOT EXISTS {entity_code} ({', '.join(col_defs)})"
                )
                conn.execute(ddl)
            conn.commit()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # ── CRUD ────────────────────────────────────────────────────────────────

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

    # ── Query / Agg ─────────────────────────────────────────────────────────

    def query(self, entity_code: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run_query(entity_code, payload)

    def query_one(
        self, entity_code: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        result = self._run_query(entity_code, payload)
        records: list[dict[str, Any]] = result.get("records", [])
        return records[0] if records else None

    def count(self, entity_code: str, payload: dict[str, Any]) -> int:
        return int(self._run_query(entity_code, payload).get("total", 0))

    def aggregate(self, entity_code: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run_agg(entity_code, payload)

    # ── Internal ────────────────────────────────────────────────────────────

    def _run_query(self, entity_code: str, payload: dict[str, Any]) -> dict[str, Any]:
        where, params = self._payload_to_where(payload)
        order_clause = self._payload_to_order(payload)
        limit_clause, extra_params = self._payload_to_limit(payload)

        count_sql = f"SELECT COUNT(*) FROM {entity_code} WHERE {where}"
        data_sql = (
            f"SELECT * FROM {entity_code} WHERE {where}{order_clause}{limit_clause}"
        )

        with self._conn() as conn:
            total_row = conn.execute(count_sql, params).fetchone()
            total = int(total_row[0]) if total_row else 0
            rows = conn.execute(data_sql, params + extra_params).fetchall()

        records = [dict(r) for r in rows]
        cols = [{"name": k} for k in (records[0].keys() if records else [])]
        return {
            "records": records,
            "total": total,
            "meta": {"columns": cols, "total": total},
        }

    def _run_agg(self, entity_code: str, payload: dict[str, Any]) -> dict[str, Any]:
        aggregates: list[dict[str, str]] = payload.get("aggregates", [])
        group_fields: list[str] = payload.get("group_by", [])
        order_fields: list[list[Any]] = payload.get("order_by", [])
        limit_n: int | None = payload.get("limit")
        where_payload: dict[str, Any] | None = payload.get("where")

        if not aggregates:
            return {
                "records": [],
                "total": 0,
                "meta": {"columns": [], "total": 0},
            }

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
    def _payload_to_where(
        payload: dict[str, Any],
    ) -> tuple[str, list[Any]]:
        q = QueryWrapper()
        q._conditions = [tuple(c) for c in payload.get("conditions", [])]
        return q.to_where_sql()

    @staticmethod
    def _payload_to_order(payload: dict[str, Any]) -> str:
        order_fields: list[list[Any]] = payload.get("order_by", [])
        if not order_fields:
            return ""
        parts = [f"{f} {'DESC' if d else 'ASC'}" for f, d in order_fields]
        return f" ORDER BY {', '.join(parts)}"

    @staticmethod
    def _payload_to_limit(
        payload: dict[str, Any],
    ) -> tuple[str, list[Any]]:
        page: int = payload.get("page", 1) or 1
        page_size: int | None = payload.get("page_size")
        limit_n: int | None = payload.get("limit")
        if limit_n:
            return f" LIMIT {limit_n}", []
        if page_size:
            offset = (page - 1) * page_size
            return f" LIMIT {page_size} OFFSET {offset}", []
        return "", []


# ── Dynamic entity / mapper builders ──────────────────────────────────────────


def _to_class_name(entity_code: str) -> str:
    """snake_case → PascalCase."""
    return "".join(part.capitalize() for part in entity_code.split("_"))


def _build_entity_class(entity_code: str, fields: list[dict[str, Any]]) -> type:
    """动态构建带 F 内部类和 to_dict 的实体类。"""
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

    def to_dict(self: Any) -> dict[str, Any]:  # noqa: N807
        return {
            k: v for k, v in self.__dict__.items() if v is not None and k != "__class__"
        }

    def __init__(self: Any, **kwargs: Any) -> None:  # noqa: N807
        for key, default in defaults.items():
            setattr(self, key, kwargs.get(key, default))

    cls_attrs: dict[str, Any] = {
        "__annotations__": annotations,
        "__init__": __init__,
        "to_dict": to_dict,
        "F": f_class,
        **defaults,
    }
    return type(_to_class_name(entity_code), (), cls_attrs)


def _build_mapper(entity_code: str, entity_cls: type, loader: DebugLoader) -> Any:
    """动态构建绑定到 loader 的 Mapper 实例。"""

    class DebugMapper:
        def __init__(self) -> None:
            self._loader = loader
            self._entity_code = entity_code
            self._entity_cls = entity_cls

        async def select_by_id(self, id: int) -> Any:  # noqa: A002
            row = self._loader.select_by_id(self._entity_code, id)
            return self._entity_cls(**row) if row else None

        async def insert(self, obj: Any) -> Any:
            new_id = self._loader.insert(self._entity_code, obj.to_dict())
            obj.id = new_id
            return obj

        async def update_by_id(self, obj: Any) -> bool:
            return self._loader.update_by_id(self._entity_code, obj.to_dict())

        async def delete_by_id(self, id: int) -> bool:  # noqa: A002
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


# ── WorkspaceScriptExecutor ───────────────────────────────────────────────────


class WorkspaceScriptExecutor:
    """工作区 Action 脚本执行器。

    在 ScriptExecutor 基础能力之上叠加：
    - Q/A 链式构造器注入（QueryWrapper / AggWrapper）
    - 实体类 + Mapper 自动构建注入
    - 调试模式（SQLite sandbox）与正式模式统一接口
    - InvocationContext 支持
    """

    @staticmethod
    async def execute_debug(
        script: str,
        params: dict[str, Any],
        db_path: Path,
        all_fields: dict[str, list[dict[str, Any]]],
        user_code: str = "",
        user_name: str = "",
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """在 SQLite 沙箱中执行 Action 脚本。

        Args:
            script: execute(params) 函数源代码。
            params: Action 入参 dict。
            db_path: debug.db 文件路径。
            all_fields: {entity_code: [field_def, ...]} 全部作用域内对象字段。
            user_code: 当前用户标识，为兼容现有调用接口保留。
            user_name: 当前用户显示名，为兼容现有调用接口保留。
            timeout: 脚本执行超时秒数。

        Returns:
            成功: {"ok": True, "result": {...}, "elapsed_ms": N}
            失败: {"ok": False, "error": "...", "traceback": "...", "elapsed_ms": N}
        """
        loader = DebugLoader(db_path, all_fields)

        # 构建注入命名空间
        extra_namespace: dict[str, Any] = {
            "Q": QueryWrapper(),
            "A": AggWrapper(),
            "params": params,
        }
        for entity_code, fields in all_fields.items():
            entity_cls = _build_entity_class(entity_code, fields)
            mapper = _build_mapper(entity_code, entity_cls, loader)
            extra_namespace[f"{entity_code}_mapper"] = mapper
            extra_namespace[_to_class_name(entity_code)] = entity_cls

        t0 = time.monotonic()
        try:
            result = await _safe_execute(script, params, extra_namespace, timeout)
            elapsed = round((time.monotonic() - t0) * 1000, 2)
            return {"ok": True, "result": result, "elapsed_ms": elapsed}
        except _ScriptError as exc:
            elapsed = round((time.monotonic() - t0) * 1000, 2)
            return {
                "ok": False,
                "error": str(exc),
                "traceback": exc.traceback,
                "elapsed_ms": elapsed,
            }
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


# ── Internal ──────────────────────────────────────────────────────────────────


class _ScriptError(Exception):
    """脚本执行异常，携带 traceback。"""

    def __init__(self, message: str, traceback_str: str = "") -> None:
        super().__init__(message)
        self.traceback = traceback_str


async def _safe_execute(
    script: str,
    params: dict[str, Any],
    extra_namespace: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    """安全编译并执行脚本，注入 extra_namespace。"""
    namespace: dict[str, Any] = {**extra_namespace}

    # 注入 httpx（可选）
    try:
        import httpx

        namespace["httpx"] = httpx
    except ImportError:
        pass

    # 注入 context
    try:
        from datacloud_data_sdk.context import get_current_context

        namespace["context"] = get_current_context()
    except Exception:
        namespace["context"] = None

    # 编译脚本
    try:
        compiled = compile(script, "<action:debug>", "exec")
    except SyntaxError as exc:
        raise _ScriptError(
            f"SyntaxError: {exc}",
            traceback.format_exc(),
        ) from exc

    # 执行脚本（将函数定义加载到 namespace）
    try:
        exec(compiled, namespace)  # noqa: S102
    except Exception as exc:
        raise _ScriptError(
            f"脚本编译错误: {exc}",
            traceback.format_exc(),
        ) from exc

    execute_fn = namespace.get("execute")
    if execute_fn is None or not callable(execute_fn):
        raise _ScriptError(
            "脚本必须定义 `def execute(params: dict) -> dict` 函数",
        )

    # 调用 execute 函数
    try:
        if asyncio.iscoroutinefunction(execute_fn):
            result = await asyncio.wait_for(execute_fn(params), timeout=timeout)
        else:
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, execute_fn, params),
                timeout=timeout,
            )
    except TimeoutError:
        raise _ScriptError(
            f"脚本执行超时（{timeout}秒）",
        )
    except Exception as exc:
        raise _ScriptError(
            f"脚本执行错误: {exc}",
            traceback.format_exc(),
        ) from exc

    if not isinstance(result, dict):
        raise _ScriptError(
            f"execute() 必须返回 dict，实际返回 {type(result).__name__}",
        )

    return result
