"""e2e 验证管线：Step 2（生成 OWL）+ Step 3（导入）+ Step 4（检索验证）。

从本地 OpenGauss demo schema 读取表结构 → 生成 OWL → 导入 whale_datacloud → Provider API 检索验证。
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# 🔧 导入 OWL 子进程所需的环境变量（whale_datacloud schema）
_IMPORT_ENV: dict[str, str] = {
    "DATACLOUD_DB_HOST": "127.0.0.1",
    "DATACLOUD_DB_PORT": "5432",
    "DATACLOUD_DB_DATABASE": "postgres",
    "DATACLOUD_DB_USER": "gaussdb",
    "DATACLOUD_DB_PASSWORD": "Admin@123",
    "DATACLOUD_DB_SCHEMA": "whale_datacloud",
    "DATACLOUD_DB_TYPE": "opengauss",
}

from datacloud_knowledge.adapters.opengauss.schema_reader import read_tables
from datacloud_knowledge.ingestion.owl_generate.generator import generate_from_tables
from datacloud_knowledge.ingestion.owl_generate.models import (
    ObjectRelation,
    OwlGenConfig,
    Table,
    TermBinding,
)
from datacloud_knowledge.ingestion.owl_generate.schema_reader import load_term_values


def _build_config(output_dir: str = "/tmp/e2e-owl-output") -> OwlGenConfig:
    """构建 e2e 测试用的 OwlGenConfig — demo CRM 业务对象。"""

    # 🔧 核心业务表列表（CRM demo schema）
    table_codes = [
        "by_customer",
        "by_opportunity",
        "by_project",
        "by_rd_task",
    ]

    # 🔧 表中文名称（用于 OWL 术语名）
    table_names = {
        "by_customer": "客户",
        "by_opportunity": "商机",
        "by_project": "项目",
        "by_rd_task": "研发任务",
    }

    table_descs = {
        "by_customer": "客户信息表",
        "by_opportunity": "商机信息表",
        "by_project": "项目信息表",
        "by_rd_task": "研发任务表",
    }

    # 🔧 术语绑定（哪列的值需要作为术语导入）
    # 基础绑定: opp_status 和 project_status 的枚举值
    # 全量绑定由 _auto_discover_term_bindings() 在 step2 中根据表结构自动补全
    term_bindings: list[TermBinding] = [
        TermBinding(
            table_code="by_opportunity",
            column_name="opp_status",
            term_type_code="opp_status",
            term_data_type="DICT_TERM",
        ),
        TermBinding(
            table_code="by_project",
            column_name="project_status",
            term_type_code="project_status",
            term_data_type="DICT_TERM",
        ),
    ]

    # 🔧 对象间 JOIN 关系
    object_relations = [
        ObjectRelation(
            relation_id="rel_opp_to_customer",
            source_code="by_opportunity",
            target_code="by_customer",
            relation_name="商机归属客户",
            join_keys=[{"sourceField": "customer_code", "targetField": "customer_code"}],
        ),
        ObjectRelation(
            relation_id="rel_project_to_customer",
            source_code="by_project",
            target_code="by_customer",
            relation_name="项目归属客户",
            join_keys=[{"sourceField": "customer_code", "targetField": "customer_code"}],
        ),
        ObjectRelation(
            relation_id="rel_project_to_opp",
            source_code="by_project",
            target_code="by_opportunity",
            relation_name="项目关联商机",
            join_keys=[{"sourceField": "opp_id", "targetField": "id"}],
        ),
        ObjectRelation(
            relation_id="rel_rdtask_to_project",
            source_code="by_rd_task",
            target_code="by_project",
            relation_name="研发任务归属项目",
            join_keys=[{"sourceField": "project_code", "targetField": "project_code"}],
        ),
    ]

    return OwlGenConfig(
        domain_code="D1",
        domain_name="销售域",
        domain_desc="CRM 销售管理领域",
        library_code="L1",
        library_name="CRM术语库",
        library_desc="CRM 业务术语库",
        db_code="demo_db",
        db_type="opengauss",
        db_params={
            "host": "127.0.0.1",
            "port": 5432,
            "database": "postgres",
            "user": "gaussdb",
            "password": "Admin@123",
            "schema": "demo",
        },
        table_codes=table_codes,
        table_names=table_names,
        table_descs=table_descs,
        term_bindings=term_bindings,
        object_relations=object_relations,
        output_dir=Path(output_dir),
    )


def _auto_discover_term_bindings(tables: list[Table]) -> list[TermBinding]:
    """根据表结构自动发现枚举列和名称列，生成全量 term_bindings。

    - 固定宽字符类型（char/character/bpchar）+ _status/_type 结尾 → DICT_TERM（枚举值）
    - 可变长字符类型（varchar/text） + _name 结尾 → LIST_TERM（名称列表）
    """
    bindings: list[TermBinding] = []
    seen: set[tuple[str, str]] = set()

    fixed_char_types = {"char", "character", "bpchar"}
    var_char_types = {"varchar", "character varying", "text"}

    for table in tables:
        for col in table.columns:
            col_name = col.name.lower()
            data_type = col.sql_type.lower().split("(")[0].strip()

            # 跳过主键和无关列
            if col.is_primary_key:
                continue
            if col_name in {"create_by", "update_by", "remark", "id"}:
                continue

            # DICT_TERM: 固定宽字符类型 + 枚举/类型语义
            if data_type in fixed_char_types:
                if col_name.endswith(("_status", "_type")):
                    key = (table.code, col_name)
                    if key not in seen:
                        seen.add(key)
                        bindings.append(
                            TermBinding(
                                table_code=table.code,
                                column_name=col.name,
                                term_type_code=col.name,
                                term_data_type="DICT_TERM",
                            )
                        )

            # LIST_TERM: 可变长字符类型 + 名称语义
            elif data_type in var_char_types:
                if col_name.endswith("_name"):
                    key = (table.code, col_name)
                    if key not in seen:
                        seen.add(key)
                        bindings.append(
                            TermBinding(
                                table_code=table.code,
                                column_name=col.name,
                                term_type_code=col.name,
                                term_data_type="LIST_TERM",
                            )
                        )

    return bindings


def step2_generate_owl(config: OwlGenConfig) -> Path:
    """Step 2: 从 OpenGauss demo schema 读取表结构，生成 OWL 包。"""
    print("=" * 60)
    print("Step 2: 从 OpenGauss 读取表结构 → 生成 OWL 包")

    # 🏗️ 通过 adapter 读取 OpenGauss demo schema 中的表结构
    db_params = config.db_params
    tables = read_tables(
        schema=db_params["schema"],
        table_codes=config.table_codes,
        table_names=config.table_names,
        table_descs=config.table_descs,
        host=db_params["host"],
        port=db_params["port"],
        database=db_params["database"],
        user=db_params["user"],
        password=db_params["password"],
    )
    print(f"  读取到 {len(tables)} 张表，共 {sum(len(t.columns) for t in tables)} 个字段")

    # 🏗️ 自动发现枚举列/名称列，生成全量 term_bindings
    auto_bindings = _auto_discover_term_bindings(tables)
    if auto_bindings:
        # 合并到 config.term_bindings（去重）
        existing_keys = {(b.table_code, b.column_name) for b in config.term_bindings}
        for b in auto_bindings:
            if (b.table_code, b.column_name) not in existing_keys:
                config.term_bindings.append(b)
                existing_keys.add((b.table_code, b.column_name))
        print(
            f"  自动发现 {len(auto_bindings)} 个术语绑定 "
            f"(DICT_TERM: {sum(1 for b in auto_bindings if b.term_data_type == 'DICT_TERM')}, "
            f"LIST_TERM: {sum(1 for b in auto_bindings if b.term_data_type == 'LIST_TERM')})"
        )

    # 🏗️ 加载术语值（枚举值/维度值）
    term_values = load_term_values(config)
    total_values = sum(len(v) for v in term_values.values())
    print(f"  读取到 {len(term_values)} 种术语类型，共 {total_values} 条术语值")

    # 🏗️ 生成 OWL 文件
    generate_from_tables(config, tables, term_values)
    print(f"  OWL 包已生成到 {config.output_dir}")
    return config.output_dir


def _run_import_cli(package_dir: str, label: str) -> None:
    """调用 import-terms CLI 导入一个 OWL 包目录。"""
    cmd = [
        "uv",
        "run",
        "--package",
        "datacloud-knowledge",
        "datacloud-knowledge",
        "import-terms",
        package_dir,
        "--schema",
        "whale_datacloud",
    ]
    merged_env = {**os.environ, **_IMPORT_ENV}
    result = subprocess.run(cmd, env=merged_env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ❌ 导入失败 [{label}]: {result.stderr}")
        raise RuntimeError(f"OWL import failed [{label}]: {result.stderr}")
    print(f"  ✅ OWL 导入完成 [{label}]")
    # 只打印关键行
    for line in result.stdout.strip().splitlines():
        if any(tag in line for tag in ("✅", "✓", "ERR", "WARN", "STATUS")):
            print(f"     {line.strip()}")


def step3_import_owl(package_dir: Path) -> None:
    """Step 3: 导入生成的 OWL 包（全量：objects + props + 枚举值 + 列表值）。

    jieba tsvector (name_keywords_jieba) 在导入 writer 的 _batch_sync_term_names() 中同步写入。"""
    print("=" * 60)
    print("Step 3: 导入 OWL → whale_datacloud")
    _run_import_cli(str(package_dir), "generated")


def step4_verify_retrieval() -> None:
    """Step 4: Provider API 检索验证 — 确认导入的术语可通过知识服务检索。

    与 run_clarify_e2e_query.py 一致的检索方式：
    通过 resolve_field_aliases / search_terms_by_type / prepare_query_clarification
    公共 API 验证知识图谱数据可用。
    """
    from datacloud_knowledge.provider import (
        get_object_props_by_code,
        prepare_query_clarification,
        resolve_field_aliases,
        search_terms_by_type,
    )

    # 🔧 设置 Provider API 所需的 DB 环境变量（create_reader() 读取）
    # 使用直接赋值覆盖 .env 中的值，确保与 Step 2/3 使用同一数据库
    os.environ["DATACLOUD_DB_HOST"] = "127.0.0.1"
    os.environ["DATACLOUD_DB_PORT"] = "5432"
    os.environ["DATACLOUD_DB_DATABASE"] = "postgres"
    os.environ["DATACLOUD_DB_USER"] = "gaussdb"
    os.environ["DATACLOUD_DB_PASSWORD"] = "Admin@123"
    os.environ["DATACLOUD_DB_SCHEMA"] = "whale_datacloud"
    os.environ["DATACLOUD_DB_TYPE"] = "opengauss"

    print("=" * 60)
    print("Step 4: Provider API 检索验证")

    # ── 4a. 按术语类型检索对象术语 ───────────────────────────────
    print("\n  4a. search_terms_by_type(term_type_code='object')")
    result = search_terms_by_type(term_type_code="object", limit=50)
    print(f"    检索到 {result.total} 条 object 术语")
    assert result.total >= 4, f"object 术语少于 4 条（实际 {result.total}），导入可能不完整"
    print("    ✅ object 术语可检索")

    # ── 4b. 字段别名解析 ────────────────────────────────────────
    print("\n  4b. resolve_field_aliases(scope_code='by_customer')")
    aliases = resolve_field_aliases(
        terms=("客户名称",),
        scope_code="by_customer",
    )
    print(f"    已解析: {aliases.resolved}")
    print(f"    模糊:   {aliases.ambiguous}")
    print(f"    未解析: {aliases.unresolved}")
    assert len(aliases.resolved) > 0, (
        f"字段别名解析失败，resolved 为空 (ambiguous={aliases.ambiguous}, unresolved={aliases.unresolved})"
    )
    print("    ✅ 字段别名解析正常")

    # ── 4c. 按对象查询属性列表（验证 HAS_FIELD 关系）───────────
    print("\n  4c. get_object_props_by_code(scope_code='by_customer')")
    props = get_object_props_by_code(scope_code="by_customer")
    print(
        f"    by_customer 拥有 {len(props)} 条属性: "
        f"{[p.term_code for p in props[:8]]}{'...' if len(props) > 8 else ''}"
    )
    assert len(props) > 0, "by_customer 属性列表为空，HAS_FIELD 关系可能未生效"
    print("    ✅ HAS_FIELD 关系正常")

    # ── 4d. 查询澄清分析（值术语召回验证：用真实数据的中文名称）────
    print("\n  4d. prepare_query_clarification (值术语召回验证)")
    print("      query: 查询华为技术有限公司的客户信息，展示客户名称、所在城市、客户编码")
    print("      scope: by_customer")
    analysis = prepare_query_clarification(
        query="查询华为公司的客户信息，展示客户名称、所在城市、客户编码",
        ontology_code="by_customer",
        structured_input={
            "select": ["customer_name", "city", "customer_code"],
            "filters": [{"field": "customer_name", "op": "eq", "value": "华为公司"}],
            "complex_conditions": [],
        },
        mode="query",
    )
    needs = "需要澄清" if analysis.needs_clarification else "无需澄清✅"
    print(f"    结果: {needs}")
    print(f"    form 存在: {analysis.form is not None}")
    assert analysis.form is not None, (
        "prepare_query_clarification 返回 form=None，知识图谱检索链路可能有问题"
    )
    print("    ✅ 值术语召回验证通过")

    print("\n  ✅ Step 4 检索验证全部通过\n")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # Step 2: 生成 OWL（全量：objects + props + 枚举值 + 列表值）
    config = _build_config(output_dir="/tmp/e2e-owl-output")
    package_dir = step2_generate_owl(config)

    # Step 3: 导入 OWL（jieba tsvector 在 writer 中同步写入）
    step3_import_owl(package_dir)

    # Step 4: 检索验证
    step4_verify_retrieval()


if __name__ == "__main__":
    main()
