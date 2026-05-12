"""Tests for ComputeExecutor — compute_ontology 分组统计实现（§3.2.3.5 验收用例）。

覆盖：
  用例1  基础分组统计（period month + region self + HAVING + ORDER BY）
  用例2  HAVING 过滤聚合结果
  用例3  派生指标（formula 展开）MAX 统计 + AVG 禁止
  用例4  range 区间分组
  用例5  metrics 为空报错 → UNSUPPORTED_FIELD
  用例6  having.field 非 metrics.as 别名报错 → UNSUPPORTED_FIELD
  用例7  group_op 与字段类型不匹配报错 → UNSUPPORTED_OP
  用例8  账期强制约束——缺失 period 条件报错 → REQUIRED_FILTER_MISSING
  用例9  全表聚合（空 dimensions）
  用例10 拍照指标跨账期 SUM 报错 → UNSUPPORTED_OP

协议变更（§3.2.3 改动点）：
  dimensions[i].field / metrics[i].field / filters[i].field 均填写 field_code（字段编码），
  不再填中文名；执行器不再做 name_to_code 翻译。
  having[i].field 仍为 metrics.as 别名（不变）。
  order_by[i].field 仍为 metrics.as 别名或维度 field_code（不变）。
"""

from __future__ import annotations

import json
import logging

import pytest
from datacloud_data_sdk.executor.compute_executor import ComputeExecutor
from datacloud_data_sdk.executor.param_coercion import coerce_sql_param
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.ontology.models import OntologyField
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager
from datacloud_data_sdk.virtual_action.validator import VirtualActionValidationError

# ─────────────────────────────────────────────────────────────────────────────
# 测试对象本体定义
# ─────────────────────────────────────────────────────────────────────────────


def _ext(property_role: str, rule_type: str, formula: str | None = None) -> str:
    """构造 ext_property JSON 字符串。"""
    d: dict = {"property_role_rule": {"property_role": property_role, "rule_type": rule_type}}
    if formula is not None:
        d["formula"] = formula
    return json.dumps(d)


ENTERPRISE_FIELDS = [
    {
        "field_code": "enterprise_id",
        "field_name": "企业ID",
        "field_type": "INTEGER",
        "source_column": "eid",
        "property_kind": "physical",
        "ext_property": _ext("DIMENSION_ATTR", "id"),
    },
    {
        "field_code": "enterprise_name",
        "field_name": "企业名称",
        "field_type": "STRING",
        "source_column": "ent_name",
        "property_kind": "physical",
        "ext_property": _ext("DIMENSION_ATTR", "name"),
    },
    {
        "field_code": "region_name",
        "field_name": "区域名称",
        "field_type": "STRING",
        "source_column": "region",
        "property_kind": "physical",
        "ext_property": _ext("DIMENSION_ATTR", "name"),
    },
    {
        "field_code": "period",
        "field_name": "账期",
        "field_type": "STRING",
        "source_column": "period",
        "property_kind": "physical",
        "ext_property": _ext("DIMENSION_ATTR", "period"),
    },
    {
        "field_code": "revenue",
        "field_name": "企业收入",
        "field_type": "NUMBER",
        "source_column": "revenue",
        "property_kind": "physical",
        "ext_property": _ext("MEASURE", "indicator"),  # indicator → basic_metric
    },
    {
        "field_code": "scale",
        "field_name": "企业规模",
        "field_type": "STRING",
        "source_column": "scale",
        "property_kind": "physical",
        "ext_property": _ext("DIMENSION_ATTR", "id"),
    },
    {
        "field_code": "tax_rate",
        "field_name": "企业实际税负率",
        "field_type": "NUMBER",
        "source_column": "tax_rate",
        "property_kind": "derived",
        "ext_property": _ext(
            "MEASURE",
            "derived_metric",
            formula="total_tax * 1.0 / total_revenue",
        ),
    },
    {
        "field_code": "beginning_users",
        "field_name": "月初用户数",
        "field_type": "NUMBER",
        "source_column": "beginning_users",
        "property_kind": "physical",
        "ext_property": _ext("MEASURE", "snapshot_metric"),
    },
]

ONTOLOGY_CONTENT = {
    "objects": [
        {
            "object_code": "enterprise_base",
            "object_name": "企业基础信息",
            "source_type": "DB",
            "source_config": {
                "alias": "test_db",
                "db_type": "SQLITE",
                "jdbc_url": "jdbc:sqlite::memory:",
            },
            "table_name": "enterprise_tbl",
            "fields": ENTERPRISE_FIELDS,
        },
    ]
}

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def loader() -> OntologyLoader:
    loader_instance = OntologyLoader()
    loader_instance.load_from_content(ONTOLOGY_CONTENT)
    return loader_instance


@pytest.fixture
async def executor_with_data(loader: OntologyLoader):
    """加载本体，创建 SQLite 内存表并插入 4 条测试数据。

    period 使用 'YYYY-MM' 格式（账期字符串，非日期）。
    tax_rate 列不存在，但通过 formula 展开计算。
    """
    ds = DataSourceManager(loader._config.datasource_configs)
    conn = ds.get_connector("test_db")
    await conn.execute(
        "CREATE TABLE enterprise_tbl "
        "(eid INTEGER, ent_name TEXT, region TEXT, period TEXT, "
        "revenue REAL, scale TEXT, total_tax REAL, total_revenue REAL, "
        "beginning_users REAL)"
    )
    await conn.execute(
        "INSERT INTO enterprise_tbl VALUES "
        "(1,'亦庄科技','亦庄','2026-01',8000000,'L',200000,8000000,1000),"
        "(2,'通州制造','通州','2026-01',3000000,'M',90000,3000000,800),"
        "(3,'亦庄智能','亦庄','2026-01',12000000,'L',600000,12000000,2000),"
        "(4,'亦庄新能源','亦庄','2026-02',6000000,'L',180000,6000000,1500)"
    )
    executor = ComputeExecutor(loader, ds_manager=ds)
    return executor


# ─────────────────────────────────────────────────────────────────────────────
# 用例1：基础分组统计
# ─────────────────────────────────────────────────────────────────────────────


async def test_basic_group_stats(executor_with_data: ComputeExecutor) -> None:
    """用例1：按账期+区域分组统计收入和企业数，过滤 2026-01，按总收入降序。
    dimensions[i].field / metrics[i].field / filters[i].field 均传 field_code。
    """
    executor = executor_with_data
    result = await executor.execute(
        "enterprise_base",
        {
            # ★ 新协议：field 传 field_code
            "dimensions": [
                {"field": "period", "group_op": "month"},
                {"field": "region_name", "group_op": "self"},
            ],
            "metrics": [
                {"field": "revenue", "agg": "sum", "as": "total_revenue"},
                {"agg": "count_all", "as": "ent_count"},
            ],
            "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
            "order_by": [{"field": "total_revenue", "direction": "desc"}],
            "limit": 10,
        },
    )
    assert "records" in result
    assert result["meta"]["object_code"] == "enterprise_base"

    records = result["records"]
    # 2026-01 有 亦庄（2条）和 通州（1条）
    assert len(records) == 2

    # 按总收入降序：亦庄(20M) 在前，通州(3M) 在后
    assert records[0]["region_name"] == "亦庄"
    assert records[0]["total_revenue"] == pytest.approx(20_000_000)
    assert records[0]["ent_count"] == 2

    assert records[1]["region_name"] == "通州"
    assert records[1]["total_revenue"] == pytest.approx(3_000_000)
    assert records[1]["ent_count"] == 1

    # meta.columns 应含各维度和指标
    col_names = {c["name"] for c in result["meta"]["columns"]}
    assert "region_name" in col_names
    assert "total_revenue" in col_names
    assert "ent_count" in col_names


# ─────────────────────────────────────────────────────────────────────────────
# 用例2：HAVING 过滤聚合结果
# ─────────────────────────────────────────────────────────────────────────────


async def test_having_filter(executor_with_data: ComputeExecutor) -> None:
    """用例2：HAVING total_revenue >= 15M，仅 亦庄(20M) 通过，通州(3M) 被过滤。
    field 传 field_code。
    """
    executor = executor_with_data
    result = await executor.execute(
        "enterprise_base",
        {
            # ★ field_code
            "dimensions": [{"field": "region_name", "group_op": "self"}],
            "metrics": [{"field": "revenue", "agg": "sum", "as": "total_revenue"}],
            "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
            "having": [{"field": "total_revenue", "op": "gte", "value": 15_000_000}],
            "order_by": [{"field": "total_revenue", "direction": "desc"}],
        },
    )
    records = result["records"]
    assert len(records) == 1
    assert records[0]["region_name"] == "亦庄"
    assert records[0]["total_revenue"] == pytest.approx(20_000_000)


# ─────────────────────────────────────────────────────────────────────────────
# 用例3：派生指标（formula 展开）统计
# ─────────────────────────────────────────────────────────────────────────────


async def test_derived_metric_formula_max(executor_with_data: ComputeExecutor) -> None:
    """用例3：derived_metric 字段在 metrics 中展开 formula，MAX 聚合正确执行。
    metrics[i].field 传 field_code（tax_rate）。

    设计约束：derived_metric 只允许 max/min，不允许 sum/avg（§3.2.3.2）。
    亦庄最大税负率：max(200000/8000000, 600000/12000000) = max(0.025, 0.05) = 0.05
    通州：0.03
    having max_tax_rate > 0.03 → 仅 亦庄 通过
    """
    executor = executor_with_data
    result = await executor.execute(
        "enterprise_base",
        {
            # ★ field_code
            "dimensions": [{"field": "region_name", "group_op": "self"}],
            "metrics": [{"field": "tax_rate", "agg": "max", "as": "max_tax_rate"}],
            "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
            "having": [{"field": "max_tax_rate", "op": "gt", "value": 0.03}],
            "order_by": [{"field": "max_tax_rate", "direction": "desc"}],
        },
    )
    records = result["records"]
    assert len(records) == 1
    assert records[0]["region_name"] == "亦庄"
    assert records[0]["max_tax_rate"] == pytest.approx(0.05)


async def test_derived_metric_avg_raises(executor_with_data: ComputeExecutor) -> None:
    """用例3b：derived_metric 不允许 avg，应报 UNSUPPORTED_OP（§3.2.3.2）。
    metrics[i].field 传 field_code。
    """
    executor = executor_with_data
    with pytest.raises(VirtualActionValidationError) as exc_info:
        await executor.execute(
            "enterprise_base",
            {
                # ★ field_code
                "dimensions": [{"field": "region_name", "group_op": "self"}],
                "metrics": [{"field": "tax_rate", "agg": "avg", "as": "avg_rate"}],
                "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
            },
        )
    assert exc_info.value.error_code == "VIRTUAL_ACTION_ERR_UNSUPPORTED_OP"


# ─────────────────────────────────────────────────────────────────────────────
# 用例4：range 区间分组
# ─────────────────────────────────────────────────────────────────────────────


async def test_range_bucket_grouping(executor_with_data: ComputeExecutor) -> None:
    """用例4：按收入区间统计企业数，2026-01 收入 8M/3M/12M 分别落入不同区间。
    dimensions[i].field / filters[i].field 传 field_code。
    """
    executor = executor_with_data
    result = await executor.execute(
        "enterprise_base",
        {
            "dimensions": [
                {
                    # ★ field_code
                    "field": "revenue",
                    "group_op": "range",
                    "buckets": [
                        {"from": None, "to": 1_000_000, "label": "100万以下"},
                        {"from": 1_000_000, "to": 5_000_000, "label": "100-500万"},
                        {"from": 5_000_000, "to": None, "label": "500万以上"},
                    ],
                }
            ],
            "metrics": [{"agg": "count_all", "as": "ent_count"}],
            # ★ field_code
            "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
            "order_by": [{"field": "ent_count", "direction": "desc"}],
        },
    )
    records = result["records"]
    # 500万以上: 8M + 12M → count=2; 100-500万: 3M → count=1
    assert len(records) == 2
    counts = {r["revenue_range"]: r["ent_count"] for r in records}
    assert counts["500万以上"] == 2
    assert counts["100-500万"] == 1
    # 按数量降序，500万以上在前
    assert records[0]["revenue_range"] == "500万以上"


# ─────────────────────────────────────────────────────────────────────────────
# 用例4b：JSON null having/dimensions 容错
# ─────────────────────────────────────────────────────────────────────────────


async def test_compute_accepts_json_null_having_and_dimensions(
    executor_with_data: ComputeExecutor,
) -> None:
    """JSON null 映射为 Python None 时，不得对 having/dimensions 做 ``for ... in None``。
    metrics[i].field / filters[i].field 传 field_code。
    """

    executor = executor_with_data
    result = await executor.execute(
        "enterprise_base",
        {
            "dimensions": None,
            # ★ field_code
            "metrics": [{"field": "revenue", "agg": "sum", "as": "total_revenue"}],
            "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
            "having": None,
        },
    )
    assert len(result["records"]) == 1
    assert result["records"][0]["total_revenue"] == pytest.approx(23_000_000)


async def test_metrics_func_alias_normalized_like_agg(executor_with_data: ComputeExecutor) -> None:
    """LLM 误用 ``func`` 代替 ``agg`` 时，校验与 SQL 应与使用 ``agg`` 一致。
    field 传 field_code。
    """

    executor = executor_with_data
    result = await executor.execute(
        "enterprise_base",
        {
            # ★ field_code
            "dimensions": [{"field": "region_name", "group_op": "self"}],
            "metrics": [{"field": "revenue", "func": "sum", "as": "total_revenue"}],
            "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
            "order_by": [{"field": "total_revenue", "direction": "desc"}],
        },
    )
    records = result["records"]
    assert len(records) == 2
    assert records[0]["region_name"] == "亦庄"
    assert records[0]["total_revenue"] == pytest.approx(20_000_000)
    assert records[1]["region_name"] == "通州"
    assert records[1]["total_revenue"] == pytest.approx(3_000_000)


async def test_order_by_metric_field_maps_to_aggregate_expr(
    executor_with_data: ComputeExecutor,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """聚合查询中原始指标字段用于排序时，应映射到聚合表达式而非裸列。"""

    caplog.set_level(logging.WARNING, logger="datacloud_data_sdk.sql_executor.data_source_manager")
    executor = executor_with_data
    await executor.execute(
        "enterprise_base",
        {
            "dimensions": [{"field": "region_name", "group_op": "self"}],
            "metrics": [{"field": "revenue", "agg": "sum", "as": "total_revenue"}],
            "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
            "order_by": [{"field": "revenue", "direction": "desc"}],
        },
    )

    sql_logs = [record.message for record in caplog.records if "SQL:" in record.message]
    assert any('ORDER BY SUM("revenue") DESC' in msg for msg in sql_logs)
    assert all('ORDER BY "revenue" DESC' not in msg for msg in sql_logs)


async def test_order_by_metric_field_ambiguity_raises(executor_with_data: ComputeExecutor) -> None:
    """同一 raw 指标字段对应多个聚合表达式时，应在执行前报业务异常。"""

    with pytest.raises(VirtualActionValidationError, match="对应多个指标表达式"):
        await executor_with_data.execute(
            "enterprise_base",
            {
                "dimensions": [{"field": "region_name", "group_op": "self"}],
                "metrics": [
                    {"field": "revenue", "agg": "sum", "as": "total_revenue"},
                    {"field": "revenue", "agg": "max", "as": "max_revenue"},
                ],
                "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
                "order_by": [{"field": "revenue", "direction": "desc"}],
            },
        )


async def test_order_by_raw_metric_field_maps_to_aggregate_expr(
    executor_with_data: ComputeExecutor,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """聚合查询的 order_by 允许原始指标 field_code，在唯一映射时转为聚合表达式。"""

    executor = executor_with_data
    caplog.set_level(logging.WARNING, logger="datacloud_data_sdk.sql_executor.data_source_manager")

    result = await executor.execute(
        "enterprise_base",
        {
            "dimensions": [{"field": "region_name", "group_op": "self"}],
            "metrics": [{"field": "revenue", "agg": "sum", "as": "total_revenue"}],
            "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
            "order_by": [{"field": "revenue", "direction": "desc"}],
        },
    )

    sql_logs = [record.message for record in caplog.records if "SQL:" in record.message]
    assert any('ORDER BY SUM("revenue") DESC' in msg for msg in sql_logs)
    assert all('ORDER BY "revenue" DESC' not in msg for msg in sql_logs)
    assert result["records"][0]["region_name"] == "亦庄"


async def test_order_by_raw_metric_field_ambiguity_raises(
    executor_with_data: ComputeExecutor,
) -> None:
    """当同一原始指标字段对应多个聚合表达式时，必须要求 LLM 使用别名消歧。"""

    with pytest.raises(VirtualActionValidationError, match="多个指标表达式") as exc_info:
        await executor_with_data.execute(
            "enterprise_base",
            {
                "dimensions": [{"field": "region_name", "group_op": "self"}],
                "metrics": [
                    {"field": "revenue", "agg": "sum", "as": "total_revenue"},
                    {"field": "revenue", "agg": "max", "as": "max_revenue"},
                ],
                "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
                "order_by": [{"field": "revenue", "direction": "desc"}],
            },
        )

    assert exc_info.value.error_code == "VIRTUAL_ACTION_ERR_UNSUPPORTED_FIELD"


# ─────────────────────────────────────────────────────────────────────────────
# 用例5：metrics 为空报错
# ─────────────────────────────────────────────────────────────────────────────


async def test_empty_metrics_raises(executor_with_data: ComputeExecutor) -> None:
    """用例5：metrics 为空 → VirtualActionValidationError UNSUPPORTED_FIELD。
    field 传 field_code。
    """
    with pytest.raises(VirtualActionValidationError) as exc_info:
        await executor_with_data.execute(
            "enterprise_base",
            {
                # ★ field_code
                "dimensions": [{"field": "region_name", "group_op": "self"}],
                "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
            },
        )
    assert exc_info.value.error_code == "VIRTUAL_ACTION_ERR_UNSUPPORTED_FIELD"


# ─────────────────────────────────────────────────────────────────────────────
# 用例6：having.field 非 metrics.as 别名报错
# ─────────────────────────────────────────────────────────────────────────────


async def test_having_field_not_alias_raises(executor_with_data: ComputeExecutor) -> None:
    """用例6：having.field 使用了 field_code 而非 metrics.as 别名 → UNSUPPORTED_FIELD。
    metrics[i].field / filters[i].field / dimensions[i].field 传 field_code。
    having.field 必须是 metrics.as 别名，此处故意传 field_code（revenue）触发报错。
    """
    with pytest.raises(VirtualActionValidationError) as exc_info:
        await executor_with_data.execute(
            "enterprise_base",
            {
                # ★ field_code
                "dimensions": [{"field": "region_name", "group_op": "self"}],
                "metrics": [{"field": "revenue", "agg": "sum", "as": "total_revenue"}],
                # having.field 故意填 field_code（revenue）而非别名（total_revenue）→ 应报错
                "having": [{"field": "revenue", "op": "gte", "value": 10_000_000}],
                "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
            },
        )
    assert exc_info.value.error_code == "VIRTUAL_ACTION_ERR_UNSUPPORTED_FIELD"


# ─────────────────────────────────────────────────────────────────────────────
# 用例7：group_op 与字段类型不匹配报错
# ─────────────────────────────────────────────────────────────────────────────


async def test_invalid_group_op_for_id_field(executor_with_data: ComputeExecutor) -> None:
    """用例7：对 id 类型字段（enterprise_id）使用 month 分组方式 → UNSUPPORTED_OP。
    dimensions[i].field 传 field_code。
    """
    with pytest.raises(VirtualActionValidationError) as exc_info:
        await executor_with_data.execute(
            "enterprise_base",
            {
                # ★ field_code
                "dimensions": [{"field": "enterprise_id", "group_op": "month"}],
                "metrics": [{"agg": "count_all", "as": "cnt"}],
                "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
            },
        )
    assert exc_info.value.error_code == "VIRTUAL_ACTION_ERR_UNSUPPORTED_OP"


# ─────────────────────────────────────────────────────────────────────────────
# 用例8：账期强制约束——缺失 period 条件报错
# ─────────────────────────────────────────────────────────────────────────────


async def test_period_required_missing(executor_with_data: ComputeExecutor) -> None:
    """用例8：对象含 period_required，未传账期过滤条件 → REQUIRED_FILTER_MISSING。
    dimensions[i].field / metrics[i].field 传 field_code。
    """
    with pytest.raises(VirtualActionValidationError) as exc_info:
        await executor_with_data.execute(
            "enterprise_base",
            {
                # ★ field_code；无 filters → 无账期条件
                "dimensions": [{"field": "region_name", "group_op": "self"}],
                "metrics": [{"field": "revenue", "agg": "sum", "as": "total_revenue"}],
            },
        )
    assert exc_info.value.error_code == "VIRTUAL_ACTION_ERR_REQUIRED_FILTER_MISSING"


# ─────────────────────────────────────────────────────────────────────────────
# 用例9：全表聚合（空 dimensions）
# ─────────────────────────────────────────────────────────────────────────────


async def test_global_aggregation_no_dimensions(executor_with_data: ComputeExecutor) -> None:
    """用例9：不传 dimensions，直接对所有 2026-01 行聚合总收入和行数。
    metrics[i].field / filters[i].field 传 field_code。
    """
    executor = executor_with_data
    result = await executor.execute(
        "enterprise_base",
        {
            # ★ field_code
            "metrics": [
                {"field": "revenue", "agg": "sum", "as": "total_revenue"},
                {"agg": "count_all", "as": "ent_count"},
            ],
            "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
        },
    )
    records = result["records"]
    assert len(records) == 1  # 全表聚合只有一行结果
    assert records[0]["total_revenue"] == pytest.approx(23_000_000)  # 8M + 3M + 12M
    assert records[0]["ent_count"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# 用例10：拍照指标跨账期 SUM 报错
# ─────────────────────────────────────────────────────────────────────────────


async def test_snapshot_metric_cross_period_sum_raises(executor_with_data: ComputeExecutor) -> None:
    """用例10：snapshot_metric 字段 + period 出现在 dimensions + agg=sum → UNSUPPORTED_OP。
    dimensions[i].field / metrics[i].field / filters[i].field 传 field_code。
    """
    with pytest.raises(VirtualActionValidationError) as exc_info:
        await executor_with_data.execute(
            "enterprise_base",
            {
                # ★ field_code
                "dimensions": [{"field": "period", "group_op": "month"}],
                "metrics": [{"field": "beginning_users", "agg": "sum", "as": "total_users"}],
                "filters": [{"field": "period", "op": "between", "value": ["2026-01", "2026-02"]}],
            },
        )
    assert exc_info.value.error_code == "VIRTUAL_ACTION_ERR_UNSUPPORTED_OP"
    assert "月初用户数" in str(exc_info.value)
    assert "跨账期" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────────────
# 协议边界：中文名不再被接受（§3.2.3 改动点 核心约束）
# ─────────────────────────────────────────────────────────────────────────────


async def test_chinese_name_in_dimensions_rejected(executor_with_data: ComputeExecutor) -> None:
    """协议边界：dimensions[i].field 传中文名（旧协议）→ UNSUPPORTED_FIELD 或 UNSUPPORTED_OP。
    执行器不再做 name_to_code 翻译，中文名在 field_map 中不存在。
    """
    with pytest.raises(VirtualActionValidationError) as exc_info:
        await executor_with_data.execute(
            "enterprise_base",
            {
                # ★ 故意传中文名（旧协议），新协议应拒绝
                "dimensions": [{"field": "区域名称", "group_op": "self"}],
                "metrics": [{"field": "revenue", "agg": "sum", "as": "total_revenue"}],
                "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
            },
        )
    assert exc_info.value.error_code in (
        "VIRTUAL_ACTION_ERR_UNSUPPORTED_FIELD",
        "VIRTUAL_ACTION_ERR_UNSUPPORTED_OP",
    )


async def test_chinese_name_in_metrics_rejected(executor_with_data: ComputeExecutor) -> None:
    """协议边界：metrics[i].field 传中文名（旧协议）→ UNSUPPORTED_FIELD。
    执行器不再做翻译，中文名在 field_map 中查不到。
    """
    with pytest.raises(VirtualActionValidationError) as exc_info:
        await executor_with_data.execute(
            "enterprise_base",
            {
                "dimensions": [{"field": "region_name", "group_op": "self"}],
                # ★ 故意传中文名（旧协议）
                "metrics": [{"field": "企业收入", "agg": "sum", "as": "total_revenue"}],
                "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
            },
        )
    assert exc_info.value.error_code == "VIRTUAL_ACTION_ERR_UNSUPPORTED_FIELD"


async def test_chinese_name_in_filters_rejected(executor_with_data: ComputeExecutor) -> None:
    """协议边界：filters[i].field 传中文名（旧协议）→ 账期约束报错或字段不存在。
    执行器不再做翻译，中文名在 field_map 中找不到 period 字段 → 账期约束未满足。
    """
    with pytest.raises(VirtualActionValidationError) as exc_info:
        await executor_with_data.execute(
            "enterprise_base",
            {
                "dimensions": [{"field": "region_name", "group_op": "self"}],
                "metrics": [{"field": "revenue", "agg": "sum", "as": "total_revenue"}],
                # ★ 故意传中文名（旧协议）；"账期" 在 field_map 中找不到 → period_required 未满足
                "filters": [{"field": "账期", "op": "eq", "value": "2026-01"}],
            },
        )
    assert exc_info.value.error_code in (
        "VIRTUAL_ACTION_ERR_UNSUPPORTED_FIELD",
        "VIRTUAL_ACTION_ERR_REQUIRED_FILTER_MISSING",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 用例11：指标类字段（analytic_kind=basic_metric/snapshot_metric 等）不允许
#         出现在 dimensions 中 → VIRTUAL_ACTION_ERR_UNSUPPORTED_OP
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "metric_field_code",
    [
        "revenue",  # analytic_kind=basic_metric（rule_type="indicator"）
        "beginning_users",  # analytic_kind=snapshot_metric
        "tax_rate",  # analytic_kind=derived_metric
    ],
)
async def test_metric_field_in_dimensions_rejected(
    loader: OntologyLoader,
    metric_field_code: str,
) -> None:
    """用例11：指标类字段以 self 方式放入 dimensions 时，校验层必须拦截并报 UNSUPPORTED_OP。

    group_op 缺失等同于 self。校验在 SQL 执行前触发，无需实际数据（不使用 executor_with_data）。
    """
    executor = ComputeExecutor(loader)
    with pytest.raises(VirtualActionValidationError) as exc_info:
        await executor.execute(
            "enterprise_base",
            {
                "dimensions": [{"field": metric_field_code}],  # 无 group_op → self
                "metrics": [{"agg": "count_all", "as": "cnt"}],
                "filters": [{"field": "period", "op": "eq", "value": "2026-01"}],
            },
        )
    assert exc_info.value.error_code == "VIRTUAL_ACTION_ERR_UNSUPPORTED_OP"
    assert metric_field_code in str(exc_info.value)




# ─────────────────────────────────────────────────────────────────────────────
# 时间字段格式化回归
# ─────────────────────────────────────────────────────────────────────────────


def test_coerce_sql_param_keeps_string_dates_and_parses_native_dates() -> None:
    """STRING 时间串保持原样，DATE/DATETIME 按格式解析。"""
    day_field = OntologyField(
        field_code="day",
        field_name="日期",
        field_type="STRING",
        data_format="yyyyMMdd",
        analytic_kind="datetime",
    )
    date_field = OntologyField(
        field_code="create_date",
        field_name="创建日期",
        field_type="DATE",
        data_format="yyyy-MM-dd",
        analytic_kind="datetime",
    )
    datetime_field = OntologyField(
        field_code="create_time",
        field_name="创建时间",
        field_type="DATETIME",
        data_format="yyyy-MM-dd HH:mm:ss",
        analytic_kind="datetime",
    )

    assert coerce_sql_param("20260131", day_field) == "20260131"
    assert coerce_sql_param("2026-01-31", date_field).isoformat() == "2026-01-31"
    assert coerce_sql_param("2026-01-31 08:09:10", datetime_field).isoformat() == "2026-01-31T08:09:10"


@pytest.mark.asyncio
async def test_string_date_grouping_uses_data_format() -> None:
    """STRING + yyyyMMdd 的 day 字段按月分组时应生成字符串分组 SQL。"""
    ontology = {
        "objects": [
            {
                "object_code": "string_day_object",
                "object_name": "字符串日期对象",
                "source_type": "DB",
                "source_config": {
                    "alias": "test_db",
                    "db_type": "SQLITE",
                    "jdbc_url": "jdbc:sqlite::memory:",
                },
                "table_name": "day_tbl",
                "fields": [
                    {
                        "field_code": "day",
                        "field_name": "日期",
                        "field_type": "STRING",
                        "data_format": "yyyyMMdd",
                        "source_column": "day",
                        "property_kind": "physical",
                        "ext_property": json.dumps({
                            "property_role_rule": {"property_role": "DIMENSION", "rule_type": "datetime"}
                        }),
                    },
                    {
                        "field_code": "revenue",
                        "field_name": "收入",
                        "field_type": "NUMBER",
                        "source_column": "revenue",
                        "property_kind": "physical",
                        "ext_property": json.dumps({
                            "property_role_rule": {"property_role": "MEASURE", "rule_type": "basic_metric"}
                        }),
                    },
                ],
            }
        ]
    }
    loader = OntologyLoader()
    loader.load_from_content(ontology)
    ds = DataSourceManager(loader._config.datasource_configs)
    conn = ds.get_connector("test_db")
    await conn.execute(
        "CREATE TABLE day_tbl (day TEXT, revenue REAL)"
    )
    await conn.execute(
        "INSERT INTO day_tbl VALUES ('20260101', 10.0), ('20260102', 20.0), ('20260201', 30.0)"
    )
    executor = ComputeExecutor(loader, ds_manager=ds)
    result = await executor.execute(
        "string_day_object",
        {
            "dimensions": [{"field": "day", "group_op": "month"}],
            "metrics": [{"field": "revenue", "agg": "sum", "as": "total_revenue"}],
            "filters": [{"field": "day", "op": "between", "value": ["20260101", "20260228"]}],
            "order_by": [{"field": "day_month", "direction": "asc"}],
        },
    )
    assert result["records"][0]["day_month"] == "2026-01"
    assert result["records"][0]["total_revenue"] == pytest.approx(30.0)
