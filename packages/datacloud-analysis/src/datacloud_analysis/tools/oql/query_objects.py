"""QueryObjects 工具实现。

提供本体对象查询功能，支持：列表查询、聚合统计、关系漫游。
结果超出 limit 时自动落文件（workspace_dir 来自 RunnableConfig），
返回 file_id 供前端通过 getFileByPage 命令翻页（不消耗 LLM）。
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from datacloud_analysis.dependencies import (
    get_datasource_registry,
    get_executor,
    get_oql_router,
    get_term_resolver,
)
from datacloud_data_sdk.oql import OQLError, format_oql_error, format_oql_response

logger = logging.getLogger(__name__)


def _write_export_file(
    records: list[dict[str, Any]],
    columns: list[str],
    meta: dict[str, Any],
    workspace_dir: str,
) -> str:
    """将查询结果写入 workspace/exports/ 目录，返回 file_id。

    同时写入 {file_id}.json（数据）和 {file_id}_meta.json（元数据）。
    前端可通过 getFileByPage 命令按页读取，不需要重新调用 LLM。
    """
    exports_dir = Path(workspace_dir) / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4().hex[:12]
    data_file = exports_dir / f"{file_id}.json"
    meta_file = exports_dir / f"{file_id}_meta.json"

    with open(data_file, "w", encoding="utf-8") as f:
        json.dump({"columns": columns, "rows": records}, f, ensure_ascii=False, default=str)

    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump({**meta, "file_id": file_id, "columns": columns}, f, ensure_ascii=False)

    logger.info(
        "query_objects: wrote export file_id=%s rows=%d dir=%s",
        file_id,
        len(records),
        exports_dir,
    )
    return file_id


@tool
def query_objects(
    object_type: str,
    select: Optional[list[str]] = None,
    where: Optional[list[dict[str, Any]]] = None,
    include_links: Optional[list[dict[str, Any]]] = None,
    metrics: Optional[list[dict[str, Any]]] = None,
    group_by: Optional[list[dict[str, Any]]] = None,
    having: Optional[list[dict[str, Any]]] = None,
    order_by: Optional[list[dict[str, str]]] = None,
    limit: int = 100,
    offset: int = 0,
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """查询本体对象或视图的实例列表、详情、聚合统计。

    支持的查询模式：
    1. 列表查询：返回对象实例列表（select + where + include_links）
    2. 聚合查询：有 metrics 字段时走聚合路径（GROUP BY），返回统计指标
    3. 关系漫游：通过 include_links 获取关联对象数据（仅 DB 主对象支持）

    **防幻觉规则**：object_type、属性名、关系名、action_type 必须来自本次注入的
    <ontology_context>，不得自行捏造。收到 OQL_ERR_UNKNOWN_* 错误时根据 message
    修正参数后重试。

    Args:
        object_type: 对象类型名或视图名（必须来自本体注册表）
        select: 返回属性列表，省略则返回全部非计算属性
        where: 行级过滤条件数组，每项格式：
            {"field": "属性名", "op": "操作符", "value": 值}
            支持操作符：eq / ne / gt / gte / lt / lte / in / nin /
                       like / isNull / between / relativeDate
            逻辑分组：{"logic": "or"|"not", "conditions": [...]}
        include_links: 关系漫游路径数组（仅 DB 主对象支持，聚合模式禁用）
            每项：{"path": "关系名或多跳路径(用.分隔)", "select": ["属性"]}
        metrics: 聚合指标数组（有此字段则走聚合路径）
            每项：{"name": "结果列名", "op": "count|sum|avg|max|min|count_distinct",
                   "field": "属性名（count 可省略）"}
        group_by: 分组维度数组（配合 metrics 使用）
            每项：{"field": "属性名", "granularity": "day|week|month|quarter|year（时间字段可选）"}
        having: 聚合后过滤，条件格式同 where，field 引用 metrics 中的 name
        order_by: 排序数组，每项：{"field": "属性名或指标名", "direction": "asc|desc"}
        limit: 返回记录数上限（默认 100，最大 1000）
        offset: 分页偏移量（默认 0）
        config: LangChain RunnableConfig（自动注入，LLM 不传此参数）

    Returns:
        成功::

            {
              "status": "success",
              "tool": "QueryObjects",
              "result": {
                "columns": ["列1", "列2"],
                "rows": [["值1", "值2"], ...],
                "total": 128,
                "returned": 20,
                "pagination": {"limit": 20, "offset": 0, "has_next": true},
                "file_id": "abc123def456"  # 仅当 total > limit 时出现
              }
            }

        错误::

            {"status": "error", "error_code": "OQL_ERR_UNKNOWN_OBJECT_TYPE", "message": "..."}

    Examples:
        列表查询（含 OR 条件）::

            query_objects(
                object_type="航班",
                select=["航班号", "状态", "延误时长"],
                where=[
                    {"field": "状态", "op": "in", "value": ["延误", "取消"]},
                    {"field": "起飞时间", "op": "relativeDate", "value": "this_month"},
                ],
                order_by=[{"field": "延误时长", "direction": "desc"}],
                limit=20,
            )

        聚合统计（按航空公司 + 周分组）::

            query_objects(
                object_type="航班",
                where=[{"field": "状态", "op": "eq", "value": "延误"}],
                metrics=[
                    {"name": "航班总数", "op": "count"},
                    {"name": "平均延误", "op": "avg", "field": "延误时长"},
                ],
                group_by=[
                    {"field": "航空公司"},
                    {"field": "起飞时间", "granularity": "week"},
                ],
                having=[{"field": "航班总数", "op": "gt", "value": 50}],
            )

        关系漫游（查询员工及归属组织）::

            query_objects(
                object_type="员工",
                select=["姓名", "工号"],
                include_links=[
                    {"path": "归属组织", "select": ["组织名称", "级别"]},
                    {"path": "归属组织.上级组织", "select": ["组织名称"]},
                ],
            )
    """
    try:
        # 构建 OQL 参数（内部 key 与 router SDK 保持一致）
        oql_params: dict[str, Any] = {
            "object": object_type,
            "limit": limit,
            "offset": offset,
        }

        if select is not None:
            oql_params["fields"] = select
        if where is not None:
            oql_params["where"] = where
        if include_links is not None:
            oql_params["include_links"] = include_links
        if metrics is not None:
            oql_params["metrics"] = metrics
        if group_by is not None:
            oql_params["group_by"] = group_by
        if having is not None:
            oql_params["having"] = having
        if order_by is not None:
            oql_params["order_by"] = order_by

        # 获取依赖
        router = get_oql_router()
        term_resolver = get_term_resolver()
        executor = get_executor()
        datasource_registry = get_datasource_registry()

        # 调用 OqlRouter
        records = router.route(
            oql_params=oql_params,
            term_resolver=term_resolver,
            executor=executor,
            datasource_registry=datasource_registry,
        )

        # total：当前 SDK 返回 list[dict]，暂用 len(records) 作近似；
        # 若 router 未来支持 total_count，可从响应元数据获取。
        total = len(records)

        response = format_oql_response(
            tool="QueryObjects",
            records=records,
            total=total,
            limit=limit,
            offset=offset,
        )

        # Decision 10.3：结果量 >= limit 时自动落文件，供前端 getFileByPage 翻页
        workspace_dir = (
            ((config or {}).get("configurable") or {}).get("workspace_dir", "")
            or os.environ.get("DATACLOUD_WORKSPACE_DIR", "")
        )
        if workspace_dir and total >= limit and response.get("status") == "success":
            columns = response["result"].get("columns", [])
            try:
                file_id = _write_export_file(
                    records=records,
                    columns=columns,
                    meta={"object_type": object_type, "total": total, "limit": limit},
                    workspace_dir=workspace_dir,
                )
                response["result"]["file_id"] = file_id
            except Exception as exc:
                logger.warning("query_objects: failed to write export file: %s", exc)

        return response

    except OQLError as e:
        return format_oql_error(e)
    except Exception as e:
        return {
            "status": "error",
            "error_code": "INTERNAL_ERROR",
            "message": f"查询执行失败: {e!s}",
            "detail": {"exception_type": type(e).__name__},
        }
