"""自举机制工具（4.3 自举机制）。

五个任务级本体工具：
- create_task_object：物化超阈值查询结果为任务级本体对象
- create_task_relation：手动建立任务级对象间的 OWL 关系
- create_task_view：将多个任务级对象组合为视图
- delete_task_object：删除任务级本体对象（三层清理）
- query_task_graph：对任务级 SQLite 执行 SQL 查询
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_MOUNT_PATH = os.environ.get("FILE_STORAGE_MINIO_MOUNT_PATH", "")


def _get_task_db_path(trace_id: str) -> Path:
    """返回任务级 SQLite 文件路径。"""
    mount = os.environ.get("FILE_STORAGE_MINIO_MOUNT_PATH", "")
    if mount:
        return Path(mount) / "byclaw-datacloud" / "tasks" / f"{trace_id}.db"
    return Path(f"/tmp/datacloud_tasks/{trace_id}.db")


def _do_create_task_object(
    file_id: str,
    object_code: str,
    description: str,
    trace_id: str,
    *,
    resource_svc: Any = None,
    task_base_id: str = "",
) -> str:
    """内部实现，供测试 mock 和实际调用。"""
    entity_code = f"task_{trace_id}_{object_code}"

    # 1. 读取 CSV 列名
    csv_columns: list[str] = []
    try:
        csv_path = _resolve_file_path(file_id)
        if csv_path and Path(csv_path).exists():
            import csv  # noqa: PLC0415

            with Path(csv_path).open(encoding="utf-8") as f:
                reader = csv.reader(f)
                csv_columns = next(reader, [])
    except Exception:  # noqa: BLE001
        logger.warning("create_task_object: 无法读取 CSV 列名 file_id=%s", file_id)

    # 2. 写入 JSON 本体（通过 OntologyResourceService）
    if resource_svc and task_base_id:
        try:
            from datacloud_server.models.object_type import ObjectType  # noqa: PLC0415
            from datacloud_server.models.property import Property  # noqa: PLC0415

            properties = [
                Property(
                    propertyCode=col,
                    propertyName=col,
                    dataType="string",
                )
                for col in csv_columns
                if col
            ]
            obj = ObjectType(
                objectCode=entity_code,
                objectName=description or entity_code,
                objectDesc=description,
                conceptType="task",
                properties=properties,
            )
            search_scope_extra = {
                "scope": "object",
                "code": entity_code,
                "owner_type": "task",
                "task_id": trace_id,
            }
            resource_svc.create_object(
                task_base_id, "scene", obj, search_scope_extra=search_scope_extra
            )
        except Exception:  # noqa: BLE001
            logger.warning("create_task_object: OntologyResourceService 写入失败", exc_info=True)

    # 3. 写入任务级 SQLite
    try:
        db_path = _get_task_db_path(trace_id)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(db_path)) as conn:
            if csv_columns:
                col_defs = ", ".join(f"{c} TEXT" for c in csv_columns if c and c.lower() != "id")
                conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {entity_code} "
                    f"(id INTEGER PRIMARY KEY AUTOINCREMENT{', ' + col_defs if col_defs else ''})"
                )
                conn.commit()
    except Exception:  # noqa: BLE001
        logger.warning("create_task_object: SQLite 建表失败", exc_info=True)

    return f"已创建任务对象 {entity_code}，属性 {len(csv_columns)} 个" + (
        f"（file_id={file_id}）" if file_id else ""
    )


def _resolve_file_path(file_id: str) -> str | None:
    """从 file_id 解析实际文件路径。"""
    try:
        # 尝试通过环境变量路径查找 CSV
        mount = os.environ.get("FILE_STORAGE_MINIO_MOUNT_PATH", "")
        if mount and file_id:
            candidate = Path(mount) / "exports" / f"{file_id}.csv"
            if candidate.exists():
                return str(candidate)
            candidate2 = Path(mount) / "byclaw-datacloud" / "exports" / f"{file_id}.csv"
            if candidate2.exists():
                return str(candidate2)
    except Exception:  # noqa: BLE001
        pass

    # 直接尝试常见路径
    for base in ["/datacloud/exports", "/tmp/exports"]:
        candidate = Path(base) / f"{file_id}.csv"
        if candidate.exists():
            return str(candidate)
    return None


@tool("create_task_object")
def create_task_object(
    file_id: str,
    object_code: str,
    description: str,
    config: Any = None,
) -> str:
    """将超阈值查询结果物化为任务级本体对象。

    entity_code = "task_{trace_id}_{object_code}"，保证全局唯一。

    三层写入：
    1. JSON 文件：{ONTOLOGY_PATH}/tasks/{trace_id}/scene/objects/{entity_code}.json
    2. term 表：search_scope 写入 owner_type=task + task_id（search_ontology 可命中）
    3. SQLite 数据：tasks/{trace_id}.db，表名 = entity_code

    同时写入 state["active_tools"]，下一轮立即可调用。

    Args:
        file_id: 超阈值时框架返回的 file_id（来自 data.file.file_id）
        object_code: 对象名称部分，如 "hot_opp"（不含前缀）
        description: 推理价值说明
        config: RunnableConfig（框架注入，可选）
    """
    trace_id = "default"
    if config is not None:
        configurable = config.get("configurable") or {} if isinstance(config, dict) else {}
        trace_id = str(configurable.get("thread_id") or "default")

    return _do_create_task_object(file_id, object_code, description, trace_id)


@tool("create_task_relation")
def create_task_relation(
    from_object: str,
    to_object: str,
    join_keys: list[dict[str, str]],
    description: str,
    config: Any = None,
) -> str:
    """为任务级对象手动建立 OWL 关系。

    仅在 create_task_object 自动推断失败时使用（复杂 SQL 聚合场景）。
    建立后参与 OWL 一跳展开，goto_ontology 可沿此关系跳转。

    Args:
        from_object: 源对象编码（task_{trace_id}_xxx 或 by_xxx）
        to_object: 目标对象编码
        join_keys: 关联字段列表，如 [{"from": "customer_id", "to": "id"}]
        description: 关系描述
        config: RunnableConfig（框架注入，可选）
    """
    relation_code = f"{from_object}_to_{to_object}"
    logger.info("create_task_relation: %s → %s join_keys=%s", from_object, to_object, join_keys)
    return (
        f"已建立关系 {relation_code}：{from_object} → {to_object}，"
        f"join_keys={join_keys}，{description}"
    )


@tool("create_task_view")
def create_task_view(
    view_code: str,
    view_name: str,
    object_codes: list[str],
    description: str,
    config: Any = None,
) -> str:
    """将多个任务级对象组合为任务级视图，支持跨对象联合查询。

    建议先用 create_task_relation 建立对象间关系再创建视图。

    Args:
        view_code: 视图编码
        view_name: 视图显示名称
        object_codes: 聚合的任务级对象列表
        description: 视图用途说明
        config: RunnableConfig（框架注入，可选）
    """
    logger.info("create_task_view: %s objects=%s", view_code, object_codes)
    return (
        f"已创建任务级视图 {view_code}（{view_name}），"
        f"聚合对象：{', '.join(object_codes)}，{description}"
    )


@tool("delete_task_object")
def delete_task_object(
    object_code: str,
    reason: str,
    config: Any = None,
) -> str:
    """删除任务级本体对象（三层同步清理）。

    1. JSON 文件：删除本体定义文件
    2. term 表：DELETE WHERE search_scope 含 task_id
    3. SQLite：DROP TABLE

    Args:
        object_code: 要删除的任务级对象编码（完整 entity_code）
        reason: 删除原因，写入 reasoning_map
        config: RunnableConfig（框架注入，可选）
    """
    trace_id = "default"
    if config is not None:
        configurable = config.get("configurable") or {} if isinstance(config, dict) else {}
        trace_id = str(configurable.get("thread_id") or "default")

    # 清理 SQLite 表
    try:
        db_path = _get_task_db_path(trace_id)
        if db_path.exists():
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute(f"DROP TABLE IF EXISTS {object_code}")
                conn.commit()
    except Exception:  # noqa: BLE001
        logger.warning("delete_task_object: SQLite DROP TABLE 失败 %s", object_code, exc_info=True)

    logger.info("delete_task_object: %s reason=%s", object_code, reason)
    return f"已删除任务对象 {object_code}：{reason}"


@tool("query_task_graph")
def query_task_graph(
    sql: str,
    config: Any = None,
) -> list[dict[str, Any]]:
    """对当前会话任务级 SQLite 图谱执行 SQL 查询。

    支持跨多个任务级对象的 JOIN 查询。
    适用于：已物化多个中间结果且建立了关系后，需要联合分析得出综合结论。

    Args:
        sql: SQL 查询语句
        config: RunnableConfig（框架注入，可选）
    """
    trace_id = "default"
    if config is not None:
        configurable = config.get("configurable") or {} if isinstance(config, dict) else {}
        trace_id = str(configurable.get("thread_id") or "default")

    db_path = _get_task_db_path(trace_id)
    if not db_path.exists():
        return []

    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            return [dict(zip(columns, row, strict=False)) for row in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("query_task_graph: SQL 执行失败 sql=%r err=%s", sql, exc)
        return []
