# ruff: noqa: S101, RUF001
from __future__ import annotations

import uuid
from importlib import import_module
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _get_disambiguation_module() -> Any:
    return import_module("datacloud_knowledge.intent.disambiguation")


def _get_types_module() -> Any:
    return import_module("datacloud_knowledge.intent.types")


@pytest.mark.intent
def test_render_shortest_path_tree_text_matches_expected_string() -> None:
    disambiguation_module = _get_disambiguation_module()
    types_module = _get_types_module()
    tree_node_type = types_module.ShortestPathTreeNode

    root = tree_node_type(
        term_id="TERM_OBJECT",
        term_name="企业综合分析表",
        term_type_code="OBJECT",
        description="企业综合分析宽表，整合经营、税务与风险相关指标。",
        children=(
            tree_node_type(
                term_id="TERM_VIEW",
                term_name="企业税收风险判别",
                term_type_code="VIEW",
                description="面向企业税务风险识别的分析视图。",
                relation_from_parent="based_on",
                children=(
                    tree_node_type(
                        term_id="TERM_PROP",
                        term_name="税收指标",
                        term_type_code="PROP",
                        description="与企业纳税、税负、税收效率相关的指标集合。",
                        relation_from_parent="defined_in",
                        children=(
                            tree_node_type(
                                term_id="TERM_METRIC",
                                term_name="亩均税收",
                                term_type_code="METRIC",
                                description="单位面积对应的税收产出指标，常用于衡量园区产出效率。",
                                relation_from_parent="belongs_to",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )

    rendered = disambiguation_module._render_shortest_path_tree_text((root,))

    expected = (
        "企业综合分析表 [OBJECT] - 企业综合分析宽表，整合经营、税务与风险相关指标。\n"
        "    └── [based_on] 企业税收风险判别 [VIEW] - 面向企业税务风险识别的分析视图。\n"
        "        └── [defined_in] 税收指标 [PROP] - 与企业纳税、税负、税收效率相关的指标集合。\n"
        "            └── [belongs_to] 亩均税收 [METRIC] - 单位面积对应的税收产出指标，常用于衡量园区产出效率。"
    )

    assert rendered == expected


@pytest.mark.intent
def test_build_shortest_path_tree_requires_source_type_codes() -> None:
    disambiguation_module = _get_disambiguation_module()

    with pytest.raises(ValueError, match="source_term_type_codes must not be empty"):
        disambiguation_module.build_shortest_path_tree(
            target_term_id="TERM_METRIC",
            source_term_type_codes=(),
            session=None,
        )


@pytest.mark.intent
def test_build_shortest_path_tree_returns_empty_result_when_no_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disambiguation_module = _get_disambiguation_module()

    monkeypatch.setattr(disambiguation_module, "_query_shortest_path_rows", lambda **_kwargs: [])

    result = disambiguation_module.build_shortest_path_tree(
        target_term_id="TERM_METRIC",
        source_term_type_codes=("OBJECT",),
        session=object(),
    )

    assert result.target_term_id == "TERM_METRIC"
    assert result.source_term_type_codes == ("OBJECT",)
    assert result.root_term_ids == ()
    assert result.tree_text == ""


@pytest.mark.intent
def test_render_shortest_path_tree_text_matches_expected_string_for_multiple_paths() -> None:
    disambiguation_module = _get_disambiguation_module()
    types_module = _get_types_module()
    tree_node_type = types_module.ShortestPathTreeNode

    roots = (
        tree_node_type(
            term_id="TERM_OBJECT_A",
            term_name="企业综合分析表",
            term_type_code="OBJECT",
            description="企业综合分析宽表，整合经营、税务与风险相关指标。",
            children=(
                tree_node_type(
                    term_id="TERM_VIEW_A",
                    term_name="企业税收风险判别",
                    term_type_code="VIEW",
                    description="面向企业税务风险识别的分析视图。",
                    relation_from_parent="based_on",
                    children=(
                        tree_node_type(
                            term_id="TERM_PROP_A",
                            term_name="税收指标",
                            term_type_code="PROP",
                            description="与企业纳税、税负、税收效率相关的指标集合。",
                            relation_from_parent="defined_in",
                            children=(
                                tree_node_type(
                                    term_id="TERM_METRIC",
                                    term_name="亩均税收",
                                    term_type_code="METRIC",
                                    description="单位面积对应的税收产出指标，常用于衡量园区产出效率。",
                                    relation_from_parent="belongs_to",
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        tree_node_type(
            term_id="TERM_OBJECT_B",
            term_name="园区经营分析表",
            term_type_code="OBJECT",
            description="园区经营主题宽表，覆盖企业产值、税收与空间利用情况。",
            children=(
                tree_node_type(
                    term_id="TERM_VIEW_B",
                    term_name="园区税收统计视图",
                    term_type_code="VIEW",
                    description="按园区维度聚合税收相关统计口径。",
                    relation_from_parent="based_on",
                    children=(
                        tree_node_type(
                            term_id="TERM_PROP_B",
                            term_name="税收指标",
                            term_type_code="PROP",
                            description="与企业纳税、税负、税收效率相关的指标集合。",
                            relation_from_parent="defined_in",
                            children=(
                                tree_node_type(
                                    term_id="TERM_METRIC",
                                    term_name="亩均税收",
                                    term_type_code="METRIC",
                                    description="单位面积对应的税收产出指标，常用于衡量园区产出效率。",
                                    relation_from_parent="belongs_to",
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )

    rendered = disambiguation_module._render_shortest_path_tree_text(roots)

    expected = (
        "企业综合分析表 [OBJECT] - 企业综合分析宽表，整合经营、税务与风险相关指标。\n"
        "├── [based_on] 企业税收风险判别 [VIEW] - 面向企业税务风险识别的分析视图。\n"
        "│   └── [defined_in] 税收指标 [PROP] - 与企业纳税、税负、税收效率相关的指标集合。\n"
        "│       └── [belongs_to] 亩均税收 [METRIC] - 单位面积对应的税收产出指标，常用于衡量园区产出效率。\n"
        "园区经营分析表 [OBJECT] - 园区经营主题宽表，覆盖企业产值、税收与空间利用情况。\n"
        "└── [based_on] 园区税收统计视图 [VIEW] - 按园区维度聚合税收相关统计口径。\n"
        "    └── [defined_in] 税收指标 [PROP] - 与企业纳税、税负、税收效率相关的指标集合。\n"
        "        └── [belongs_to] 亩均税收 [METRIC] - 单位面积对应的税收产出指标，常用于衡量园区产出效率。"
    )

    assert rendered == expected


def _insert_term(
    db_session: Session,
    *,
    term_id: str,
    term_code: str,
    term_name: str,
    term_type_code: str,
    domain_id: str,
    desc_summary: str,
) -> None:
    db_session.execute(
        text(
            """
            INSERT INTO whale_datacloud.term (
                term_id, term_code, term_name, desc_summary, domain_id, term_type_code
            ) VALUES (
                :term_id, :term_code, :term_name, :desc_summary, :domain_id, :term_type_code
            )
            """
        ),
        {
            "term_id": term_id,
            "term_code": term_code,
            "term_name": term_name,
            "desc_summary": desc_summary,
            "domain_id": domain_id,
            "term_type_code": term_type_code,
        },
    )


def _insert_relation(
    db_session: Session,
    *,
    relation_id: str,
    source_term_id: str,
    target_term_id: str,
    relation_name: str,
) -> None:
    db_session.execute(
        text(
            """
            INSERT INTO whale_datacloud.term_relation (
                relation_id, source_term_id, target_term_id, relation_name
            ) VALUES (
                :relation_id, :source_term_id, :target_term_id, :relation_name
            )
            """
        ),
        {
            "relation_id": relation_id,
            "source_term_id": source_term_id,
            "target_term_id": target_term_id,
            "relation_name": relation_name,
        },
    )


def _insert_knowledge(
    db_session: Session,
    *,
    knowledge_id: str,
    term_id: str,
    desc_summary: str,
    desc: str,
) -> None:
    db_session.execute(
        text(
            """
            INSERT INTO whale_datacloud.term_knowledge (
                knowledge_id, term_id, desc_summary, "desc"
            ) VALUES (
                :knowledge_id, :term_id, :desc_summary, :desc
            )
            """
        ),
        {
            "knowledge_id": knowledge_id,
            "term_id": term_id,
            "desc_summary": desc_summary,
            "desc": desc,
        },
    )


@pytest.mark.intent
@pytest.mark.db_integration
def test_build_shortest_path_tree_with_session_matches_expected_string(db_session: Session) -> None:
    disambiguation_module = _get_disambiguation_module()
    prefix = f"intent_shortest_path_{uuid.uuid4().hex[:8]}"
    domain_row = db_session.execute(
        text("SELECT domain_id FROM whale_datacloud.domain LIMIT 1")
    ).fetchone()
    if domain_row is None:
        pytest.skip("No domain seed data in database")
    domain_id = str(domain_row[0])

    object_a_id = f"{prefix}_object_a"
    object_b_id = f"{prefix}_object_b"
    view_a_id = f"{prefix}_view_a"
    view_b_id = f"{prefix}_view_b"
    prop_id = f"{prefix}_prop"
    metric_id = f"{prefix}_metric"

    _insert_term(
        db_session,
        term_id=object_a_id,
        term_code=f"{prefix}_object_a",
        term_name="企业综合分析表",
        term_type_code="OBJECT",
        domain_id=domain_id,
        desc_summary="企业综合分析宽表，整合经营、税务与风险相关指标。",
    )
    _insert_term(
        db_session,
        term_id=object_b_id,
        term_code=f"{prefix}_object_b",
        term_name="园区经营分析表",
        term_type_code="OBJECT",
        domain_id=domain_id,
        desc_summary="园区经营主题宽表，覆盖企业产值、税收与空间利用情况。",
    )
    _insert_term(
        db_session,
        term_id=view_a_id,
        term_code=f"{prefix}_view_a",
        term_name="企业税收风险判别",
        term_type_code="VIEW",
        domain_id=domain_id,
        desc_summary="面向企业税务风险识别的分析视图。",
    )
    _insert_term(
        db_session,
        term_id=view_b_id,
        term_code=f"{prefix}_view_b",
        term_name="园区税收统计视图",
        term_type_code="VIEW",
        domain_id=domain_id,
        desc_summary="按园区维度聚合税收相关统计口径。",
    )
    _insert_term(
        db_session,
        term_id=prop_id,
        term_code=f"{prefix}_prop",
        term_name="税收指标",
        term_type_code="PROP",
        domain_id=domain_id,
        desc_summary="与企业纳税、税负、税收效率相关的指标集合。",
    )
    _insert_term(
        db_session,
        term_id=metric_id,
        term_code=f"{prefix}_metric",
        term_name="亩均税收",
        term_type_code="METRIC",
        domain_id=domain_id,
        desc_summary="单位面积对应的税收产出指标，常用于衡量园区产出效率。",
    )

    _insert_knowledge(
        db_session,
        knowledge_id=f"{prefix}_knowledge_object_a",
        term_id=object_a_id,
        desc_summary="企业综合分析宽表，整合经营、税务与风险相关指标。",
        desc="企业综合分析宽表，整合经营、税务与风险相关指标。",
    )
    _insert_knowledge(
        db_session,
        knowledge_id=f"{prefix}_knowledge_object_b",
        term_id=object_b_id,
        desc_summary="园区经营主题宽表，覆盖企业产值、税收与空间利用情况。",
        desc="园区经营主题宽表，覆盖企业产值、税收与空间利用情况。",
    )
    _insert_knowledge(
        db_session,
        knowledge_id=f"{prefix}_knowledge_view_a",
        term_id=view_a_id,
        desc_summary="面向企业税务风险识别的分析视图。",
        desc="面向企业税务风险识别的分析视图。",
    )
    _insert_knowledge(
        db_session,
        knowledge_id=f"{prefix}_knowledge_view_b",
        term_id=view_b_id,
        desc_summary="按园区维度聚合税收相关统计口径。",
        desc="按园区维度聚合税收相关统计口径。",
    )
    _insert_knowledge(
        db_session,
        knowledge_id=f"{prefix}_knowledge_prop",
        term_id=prop_id,
        desc_summary="与企业纳税、税负、税收效率相关的指标集合。",
        desc="与企业纳税、税负、税收效率相关的指标集合。",
    )
    _insert_knowledge(
        db_session,
        knowledge_id=f"{prefix}_knowledge_metric",
        term_id=metric_id,
        desc_summary="单位面积对应的税收产出指标，常用于衡量园区产出效率。",
        desc="单位面积对应的税收产出指标，常用于衡量园区产出效率。",
    )

    _insert_relation(
        db_session,
        relation_id=f"{prefix}_rel_1",
        source_term_id=object_a_id,
        target_term_id=view_a_id,
        relation_name="based_on",
    )
    _insert_relation(
        db_session,
        relation_id=f"{prefix}_rel_2",
        source_term_id=view_a_id,
        target_term_id=prop_id,
        relation_name="defined_in",
    )
    _insert_relation(
        db_session,
        relation_id=f"{prefix}_rel_3",
        source_term_id=prop_id,
        target_term_id=metric_id,
        relation_name="belongs_to",
    )
    _insert_relation(
        db_session,
        relation_id=f"{prefix}_rel_4",
        source_term_id=object_b_id,
        target_term_id=view_b_id,
        relation_name="based_on",
    )
    _insert_relation(
        db_session,
        relation_id=f"{prefix}_rel_5",
        source_term_id=view_b_id,
        target_term_id=prop_id,
        relation_name="defined_in",
    )

    result = disambiguation_module.build_shortest_path_tree(
        target_term_id=metric_id,
        source_term_type_codes=["OBJECT"],
        session=db_session,
        max_depth=4,
    )

    expected = (
        "企业综合分析表 [OBJECT] - 企业综合分析宽表，整合经营、税务与风险相关指标。\n"
        "├── [based_on] 企业税收风险判别 [VIEW] - 面向企业税务风险识别的分析视图。\n"
        "│   └── [defined_in] 税收指标 [PROP] - 与企业纳税、税负、税收效率相关的指标集合。\n"
        "│       └── [belongs_to] 亩均税收 [METRIC] - 单位面积对应的税收产出指标，常用于衡量园区产出效率。\n"
        "园区经营分析表 [OBJECT] - 园区经营主题宽表，覆盖企业产值、税收与空间利用情况。\n"
        "└── [based_on] 园区税收统计视图 [VIEW] - 按园区维度聚合税收相关统计口径。\n"
        "    └── [defined_in] 税收指标 [PROP] - 与企业纳税、税负、税收效率相关的指标集合。\n"
        "        └── [belongs_to] 亩均税收 [METRIC] - 单位面积对应的税收产出指标，常用于衡量园区产出效率。"
    )

    assert result.tree_text == expected
    assert result.root_term_ids == (object_a_id, object_b_id)


@pytest.mark.intent
@pytest.mark.db_integration
def test_build_shortest_path_tree_merges_term_and_knowledge_descriptions(
    db_session: Session,
) -> None:
    disambiguation_module = _get_disambiguation_module()
    prefix = f"intent_shortest_path_merge_{uuid.uuid4().hex[:8]}"
    domain_row = db_session.execute(
        text("SELECT domain_id FROM whale_datacloud.domain LIMIT 1")
    ).fetchone()
    if domain_row is None:
        pytest.skip("No domain seed data in database")
    domain_id = str(domain_row[0])

    object_id = f"{prefix}_object"
    metric_id = f"{prefix}_metric"

    _insert_term(
        db_session,
        term_id=object_id,
        term_code=f"{prefix}_object",
        term_name="企业综合分析表",
        term_type_code="OBJECT",
        domain_id=domain_id,
        desc_summary="企业综合分析宽表。",
    )
    _insert_term(
        db_session,
        term_id=metric_id,
        term_code=f"{prefix}_metric",
        term_name="亩均税收",
        term_type_code="METRIC",
        domain_id=domain_id,
        desc_summary="单位面积税收产出指标。",
    )

    _insert_knowledge(
        db_session,
        knowledge_id=f"{prefix}_knowledge_object",
        term_id=object_id,
        desc_summary="覆盖企业规模、营收变化、税务等分析主题。",
        desc="覆盖企业规模、营收变化、税务等分析主题。",
    )
    _insert_knowledge(
        db_session,
        knowledge_id=f"{prefix}_knowledge_metric",
        term_id=metric_id,
        desc_summary="常用于衡量园区产出效率。",
        desc="常用于衡量园区产出效率。",
    )

    _insert_relation(
        db_session,
        relation_id=f"{prefix}_rel_1",
        source_term_id=object_id,
        target_term_id=metric_id,
        relation_name="belongs_to",
    )

    result = disambiguation_module.build_shortest_path_tree(
        target_term_id=metric_id,
        source_term_type_codes=["OBJECT"],
        session=db_session,
        max_depth=2,
    )

    expected = (
        "企业综合分析表 [OBJECT] - 企业综合分析宽表。；覆盖企业规模、营收变化、税务等分析主题。\n"
        "    └── [belongs_to] 亩均税收 [METRIC] - 单位面积税收产出指标。；常用于衡量园区产出效率。"
    )

    assert result.tree_text == expected
