"""Tests for QueryExecutor — query_ontology 明细检索实现（§3.2.2 验收用例）。

覆盖：
  用例1  基础物理字段查询（name_to_code + AND 过滤 + ORDER BY + LIMIT）
  用例2  空 select 返回全部非 linked 字段
  用例3  派生指标字段 formula 展开（SELECT / WHERE / ORDER BY）
  用例4  filter_relation=OR
  用例5  账期强制约束——缺失账期条件 → REQUIRED_FILTER_MISSING
  用例6  账期强制约束 + filter_relation=OR 冲突 → INVALID
  用例7  不存在字段 → UNSUPPORTED_FIELD
  用例8  非法 op（like 用于 id 字段） → UNSUPPORTED_OP
  用例9  linked 字段拦截 → LINKED_NOT_SUPPORTED
"""

from __future__ import annotations

import json

import pytest

from datacloud_data_sdk.executor.query_executor import QueryExecutor
from datacloud_data_sdk.ontology.loader import OntologyLoader
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
        "ext_property": _ext("MEASURE", "indicator"),  # OWL rule_type=indicator → analytic_kind=basic_metric
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
        "source_column": "tax_rate",  # 物理列（派生公式字段）
        "property_kind": "derived",
        "ext_property": _ext(
            "MEASURE",
            "derived_metric",
            formula="total_tax * 1.0 / total_revenue",
        ),
    },
    {
        "field_code": "linked_park",
        "field_name": "所属园区名称",
        "field_type": "STRING",
        "source_column": "linked_park",
        "property_kind": "linked",
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
        # 无账期字段的对象，用于测试 filter_relation=OR（无 period_required 约束）
        {
            "object_code": "enterprise_simple",
            "object_name": "企业简单信息",
            "source_type": "DB",
            "source_config": {
                "alias": "test_db",
                "db_type": "SQLITE",
                "jdbc_url": "jdbc:sqlite::memory:",
            },
            "table_name": "enterprise_tbl",
            "fields": [
                f for f in ENTERPRISE_FIELDS
                if f["field_code"] not in ("period", "linked_park")
            ],
        },
    ]
}

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def loader() -> OntologyLoader:
    l = OntologyLoader()
    l.load_from_content(ONTOLOGY_CONTENT)
    return l


@pytest.fixture
async def executor_with_data(loader: OntologyLoader):
    """加载本体，创建 SQLite 内存表并插入 4 条测试数据。"""
    ds = DataSourceManager(loader._config.datasource_configs)
    conn = ds.get_connector("test_db")
    await conn.execute(
        "CREATE TABLE enterprise_tbl "
        "(eid INTEGER, ent_name TEXT, region TEXT, period TEXT, "
        "revenue REAL, scale TEXT, total_tax REAL, total_revenue REAL)"
    )
    await conn.execute(
        "INSERT INTO enterprise_tbl VALUES "
        "(1,'亦庄科技','亦庄','2026-01',8000000,'L',200000,8000000),"
        "(2,'通州制造','通州','2026-01',3000000,'M',90000,3000000),"
        "(3,'亦庄智能','亦庄','2026-01',12000000,'L',600000,12000000),"
        "(4,'亦庄新能源','亦庄','2026-02',6000000,'L',180000,6000000)"
    )
    executor = QueryExecutor(loader, ds_manager=ds)
    return executor


# ─────────────────────────────────────────────────────────────────────────────
# 用例1：基础物理字段查询（正常路径）
# ─────────────────────────────────────────────────────────────────────────────

async def test_basic_physical_query(executor_with_data: QueryExecutor) -> None:
    """用例1：name_to_code 映射、AND 过滤、ORDER BY、LIMIT 正确执行。"""
    executor = executor_with_data
    result = await executor.execute(
        "enterprise_base",
        {
            "select": ["企业名称", "账期", "企业收入"],
            "filters": [
                {"field": "区域名称", "op": "eq", "value": "亦庄"},
                {"field": "账期",     "op": "eq", "value": "2026-01"},
                {"field": "企业收入", "op": "gte", "value": 5000000},
            ],
            "order_by": [{"field": "企业收入", "direction": "desc"}],
            "limit": 10,
            "offset": 0,
        },
    )
    assert "records" in result
    assert result["total"] == 2  # 亦庄科技(800万) + 亦庄智能(1200万)
    # 按收入降序：亦庄智能在前
    assert result["records"][0]["enterprise_name"] == "亦庄智能"
    assert result["records"][1]["enterprise_name"] == "亦庄科技"
    # meta.columns 使用 field_code 作 name、field_name 作 label
    col_names = [c["name"] for c in result["meta"]["columns"]]
    col_labels = [c["label"] for c in result["meta"]["columns"]]
    assert "enterprise_name" in col_names
    assert "企业名称" in col_labels
    assert result["meta"]["object_code"] == "enterprise_base"


# ─────────────────────────────────────────────────────────────────────────────
# 用例2：空 select 返回全部非 linked 字段
# ─────────────────────────────────────────────────────────────────────────────

async def test_empty_select_returns_all_non_linked(executor_with_data: QueryExecutor) -> None:
    """用例2：不传 select 时返回全部非 linked 字段。"""
    executor = executor_with_data
    result = await executor.execute(
        "enterprise_base",
        {
            "filters": [{"field": "账期", "op": "eq", "value": "2026-01"}],
            "limit": 10,
        },
    )
    col_names = {c["name"] for c in result["meta"]["columns"]}
    assert "enterprise_name" in col_names
    assert "period" in col_names
    assert "revenue" in col_names
    # linked 字段不应出现
    assert "linked_park" not in col_names
    assert result["total"] == 3  # 2026-01 有 3 条


# ─────────────────────────────────────────────────────────────────────────────
# 用例3：派生指标字段 formula 展开
# ─────────────────────────────────────────────────────────────────────────────

async def test_derived_metric_formula_expansion(executor_with_data: QueryExecutor) -> None:
    """用例3：derived_metric 字段在 SELECT / WHERE / ORDER BY 中展开 formula。"""
    executor = executor_with_data
    result = await executor.execute(
        "enterprise_base",
        {
            "select": ["企业名称", "账期", "企业实际税负率"],
            "filters": [
                {"field": "账期",         "op": "eq", "value": "2026-01"},
                # total_tax/total_revenue：亦庄科技=2.5%，通州制造=3%，亦庄智能=5%
                {"field": "企业实际税负率", "op": "gt", "value": 0.025},
            ],
            "order_by": [{"field": "企业实际税负率", "direction": "desc"}],
            "limit": 10,
        },
    )
    # 应返回：通州制造(3%) + 亦庄智能(5%)，按税负率降序
    assert result["total"] == 2
    assert result["records"][0]["enterprise_name"] == "亦庄智能"  # 5% 最高
    # 返回列中有 tax_rate（field_code）
    col_names = {c["name"] for c in result["meta"]["columns"]}
    assert "tax_rate" in col_names


# ─────────────────────────────────────────────────────────────────────────────
# 用例4：filter_relation=OR
# ─────────────────────────────────────────────────────────────────────────────

async def test_filter_relation_or(executor_with_data: QueryExecutor) -> None:
    """用例4：filter_relation=OR 时多个条件取并集（使用无 period_required 的对象）。"""
    executor = executor_with_data
    result = await executor.execute(
        "enterprise_simple",  # 无 period 字段，无 period_required 约束
        {
            "select": ["企业名称", "企业收入"],
            "filters": [
                {"field": "企业收入", "op": "gte", "value": 10000000},  # 亦庄智能
                {"field": "区域名称", "op": "eq",  "value": "通州"},    # 通州制造
            ],
            "filter_relation": "OR",
            "limit": 10,
        },
    )
    names = {r["enterprise_name"] for r in result["records"]}
    assert "亦庄智能" in names
    assert "通州制造" in names


# ─────────────────────────────────────────────────────────────────────────────
# 用例5：账期强制约束——缺失账期条件
# ─────────────────────────────────────────────────────────────────────────────

async def test_period_required_missing(executor_with_data: QueryExecutor) -> None:
    """用例5：对象含 period 字段（period_required），未传账期条件 → REQUIRED_FILTER_MISSING。"""
    executor = executor_with_data
    with pytest.raises(VirtualActionValidationError) as exc_info:
        await executor.execute(
            "enterprise_base",
            {
                "filters": [{"field": "区域名称", "op": "eq", "value": "亦庄"}],
                "limit": 10,
            },
        )
    assert exc_info.value.error_code == "VIRTUAL_ACTION_ERR_REQUIRED_FILTER_MISSING"


# ─────────────────────────────────────────────────────────────────────────────
# 用例6：账期强制约束 + filter_relation=OR 冲突
# ─────────────────────────────────────────────────────────────────────────────

async def test_period_required_with_or_relation_conflict(executor_with_data: QueryExecutor) -> None:
    """用例6：含 period_required 的对象使用 filter_relation=OR → INVALID。"""
    executor = executor_with_data
    with pytest.raises(VirtualActionValidationError) as exc_info:
        await executor.execute(
            "enterprise_base",
            {
                "filters": [
                    {"field": "账期",     "op": "eq",  "value": "2026-01"},
                    {"field": "企业收入", "op": "gte", "value": 5000000},
                ],
                "filter_relation": "OR",
                "limit": 10,
            },
        )
    assert exc_info.value.error_code == "VIRTUAL_ACTION_ERR_INVALID"


# ─────────────────────────────────────────────────────────────────────────────
# 用例7：不存在字段
# ─────────────────────────────────────────────────────────────────────────────

async def test_nonexistent_field(executor_with_data: QueryExecutor) -> None:
    """用例7：select 中包含对象未声明的字段名 → UNSUPPORTED_FIELD。"""
    executor = executor_with_data
    with pytest.raises(VirtualActionValidationError) as exc_info:
        await executor.execute(
            "enterprise_base",
            {
                "select": ["企业名称", "不存在字段"],
                "filters": [{"field": "账期", "op": "eq", "value": "2026-01"}],
                "limit": 5,
            },
        )
    assert exc_info.value.error_code == "VIRTUAL_ACTION_ERR_UNSUPPORTED_FIELD"


# ─────────────────────────────────────────────────────────────────────────────
# 用例8：非法 op（like 用于 id 类字段）
# ─────────────────────────────────────────────────────────────────────────────

async def test_invalid_op_for_id_field(executor_with_data: QueryExecutor) -> None:
    """用例8：对 id 类字段（企业ID）使用 like → UNSUPPORTED_OP。"""
    executor = executor_with_data
    with pytest.raises(VirtualActionValidationError) as exc_info:
        await executor.execute(
            "enterprise_base",
            {
                "filters": [
                    {"field": "账期",   "op": "eq",   "value": "2026-01"},
                    {"field": "企业ID", "op": "like", "value": "BJ%"},
                ],
                "limit": 5,
            },
        )
    assert exc_info.value.error_code == "VIRTUAL_ACTION_ERR_UNSUPPORTED_OP"


# ─────────────────────────────────────────────────────────────────────────────
# 用例9：linked 字段拦截
# ─────────────────────────────────────────────────────────────────────────────

async def test_linked_field_blocked(executor_with_data: QueryExecutor) -> None:
    """用例9：select 中包含 property_kind=linked 的字段 → LINKED_NOT_SUPPORTED。"""
    executor = executor_with_data
    with pytest.raises(VirtualActionValidationError) as exc_info:
        await executor.execute(
            "enterprise_base",
            {
                "select": ["企业名称", "所属园区名称"],
                "filters": [{"field": "账期", "op": "eq", "value": "2026-01"}],
                "limit": 5,
            },
        )
    assert exc_info.value.error_code == "VIRTUAL_ACTION_ERR_LINKED_NOT_SUPPORTED"
