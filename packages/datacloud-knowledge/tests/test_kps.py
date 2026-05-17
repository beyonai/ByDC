"""KPS 数据模型单元测试 — DomainDef / TermDef / RelationDef / KnowledgePackage 等。

测试 frozen dataclass 的构造、默认值、不可变性和 compute_term_id 规则。
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from datacloud_knowledge.contracts.kps import (
    ActionDef,
    ActionParamDef,
    DomainDef,
    KnowledgePackage,
    LibraryDef,
    RelationDef,
    TermDef,
    TermTypeDef,
)

# ═══════════════════════════════════════════════════════════════════════════════
# DomainDef 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestDomainDef:
    """DomainDef 构造与默认值测试。"""

    def test_construction_minimal(self) -> None:
        """最少必填字段创建 DomainDef。"""
        d = DomainDef(domain_code="D1", domain_name="销售域")
        assert d.domain_code == "D1"
        assert d.domain_name == "销售域"
        assert d.parent_code is None
        assert d.domain_desc == ""

    def test_construction_full(self) -> None:
        """全部字段创建 DomainDef。"""
        d = DomainDef(
            domain_code="SALE",
            domain_name="销售域",
            parent_code="ROOT",
            domain_desc="销售业务领域",
        )
        assert d.parent_code == "ROOT"
        assert d.domain_desc == "销售业务领域"

    def test_frozen(self) -> None:
        """DomainDef 不可修改（frozen=True）。"""
        d = DomainDef(domain_code="D1", domain_name="测试")
        with pytest.raises(FrozenInstanceError):
            d.domain_code = "D2"


# ═══════════════════════════════════════════════════════════════════════════════
# LibraryDef 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestLibraryDef:
    """LibraryDef 构造与默认值测试。"""

    def test_construction_minimal(self) -> None:
        """最少必填字段创建 LibraryDef。"""
        lib = LibraryDef(library_code="L1", library_name="标准术语库")
        assert lib.library_code == "L1"
        assert lib.library_name == "标准术语库"
        assert lib.library_desc == ""

    def test_construction_full(self) -> None:
        """全部字段创建 LibraryDef。"""
        lib = LibraryDef(
            library_code="standard",
            library_name="标准术语库",
            library_desc="平台内置标准术语集合",
        )
        assert lib.library_desc == "平台内置标准术语集合"


# ═══════════════════════════════════════════════════════════════════════════════
# TermTypeDef 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestTermTypeDef:
    """TermTypeDef 构造与 type_category 值测试。"""

    def test_construction_ontology(self) -> None:
        """本体术语类型（type_category=3）。"""
        tt = TermTypeDef(type_code="object", type_name="对象", type_category=3)
        assert tt.type_code == "object"
        assert tt.type_category == 3
        assert tt.type_desc == ""

    def test_construction_list_term(self) -> None:
        """列表术语类型（type_category=1）。"""
        tt = TermTypeDef(
            type_code="LIST_TERM", type_name="列表术语", type_category=1, type_desc="枚举值"
        )
        assert tt.type_category == 1

    def test_frozen(self) -> None:
        """TermTypeDef 不可修改。"""
        tt = TermTypeDef(type_code="prop", type_name="属性", type_category=3)
        with pytest.raises(FrozenInstanceError):
            tt.type_code = "view"


# ═══════════════════════════════════════════════════════════════════════════════
# TermDef 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestTermDef:
    """TermDef 构造、compute_term_id、不可变性测试。"""

    def test_construction_minimal(self) -> None:
        """最少必填字段创建 TermDef。"""
        term = TermDef(
            term_code="by_customer",
            term_name="客户",
            term_type_code="object",
            library_code="L1",
            domain_code="D1",
        )
        assert term.term_code == "by_customer"
        assert term.term_name == "客户"
        assert term.parent_term_code is None
        assert term.synonyms == ()
        assert term.term_desc == ""

    def test_construction_with_synonyms(self) -> None:
        """带同义词的 TermDef 构造。"""
        term = TermDef(
            term_code="customer",
            term_name="客户",
            term_type_code="object",
            library_code="L1",
            domain_code="D1",
            synonyms=("顾客", "Client"),
        )
        assert term.synonyms == ("顾客", "Client")

    def test_construction_with_parent(self) -> None:
        """带 parent_term_code 的子术语构造。"""
        term = TermDef(
            term_code="SIGNED",
            term_name="签约成功",
            term_type_code="opp_status",
            library_code="L1",
            domain_code="D1",
            parent_term_code="status",
        )
        assert term.parent_term_code == "status"

    def test_frozen(self) -> None:
        """TermDef 不可修改。"""
        term = TermDef(
            term_code="test",
            term_name="测试",
            term_type_code="object",
            library_code="L1",
            domain_code="D1",
        )
        with pytest.raises(FrozenInstanceError):
            term.term_code = "changed"

    # ── compute_term_id ──────────────────────────────────────────────────────

    def test_compute_term_id_root(self) -> None:
        """根术语：{library_code}#{term_type_code}#{term_code}。"""
        term = TermDef(
            term_code="by_customer",
            term_name="客户",
            term_type_code="object",
            library_code="L1",
            domain_code="D1",
        )
        assert term.compute_term_id() == "L1#object#by_customer"

    def test_compute_term_id_child(self) -> None:
        """子术语：{parent_term_id}#{term_type_code}#{term_code}。"""
        term = TermDef(
            term_code="customer_name",
            term_name="客户名称",
            term_type_code="prop",
            library_code="L1",
            domain_code="D1",
            parent_term_code="by_customer",
        )
        tid = term.compute_term_id(parent_term_id="L1#object#by_customer")
        assert tid == "L1#object#by_customer#prop#customer_name"

    def test_compute_term_id_deep_child(self) -> None:
        """深度嵌套子术语。"""
        term = TermDef(
            term_code="SIGNED",
            term_name="签约成功",
            term_type_code="opp_status",
            library_code="L1",
            domain_code="D1",
            parent_term_code="status",
        )
        tid = term.compute_term_id(parent_term_id="L1#prop#status")
        assert tid == "L1#prop#status#opp_status#SIGNED"

    def test_compute_term_id_no_parent_term_id(self) -> None:
        """不传 parent_term_id → 使用 library_code 作为前缀。"""
        term_with_parent = TermDef(
            term_code="child_x",
            term_name="子X",
            term_type_code="value",
            library_code="L2",
            domain_code="D1",
            parent_term_code="prop_x",
        )
        assert term_with_parent.compute_term_id() == "L2#value#child_x"


# ═══════════════════════════════════════════════════════════════════════════════
# ActionParamDef 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestActionParamDef:
    """ActionParamDef 构造测试。"""

    def test_construction_required(self) -> None:
        """必填参数。"""
        param = ActionParamDef(
            param_code="id",
            param_type="integer",
            description="主键ID",
            is_required=True,
        )
        assert param.param_code == "id"
        assert param.param_type == "integer"
        assert param.is_required is True

    def test_construction_optional(self) -> None:
        """可选参数（默认值）。"""
        param = ActionParamDef(
            param_code="name",
            param_type="string",
            description="名称",
        )
        assert param.is_required is False


# ═══════════════════════════════════════════════════════════════════════════════
# ActionDef 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestActionDef:
    """ActionDef 构造测试。"""

    def test_construction_minimal(self) -> None:
        """最少必填字段创建 ActionDef。"""
        action = ActionDef(
            action_code="get_customer",
            action_name="获取客户",
            action_type="QUERY",
            request_url="/api/customer",
            request_method="GET",
        )
        assert action.action_code == "get_customer"
        assert action.action_type == "QUERY"
        assert action.request_params == ()
        assert action.response_params == ()

    def test_construction_with_params(self) -> None:
        """带参数的 ActionDef 构造。"""
        action = ActionDef(
            action_code="update_customer",
            action_name="更新客户",
            action_type="MUTATION",
            request_url="/api/customer",
            request_method="POST",
            request_params=(
                ActionParamDef(
                    param_code="id", param_type="integer", description="ID", is_required=True
                ),
                ActionParamDef(param_code="name", param_type="string", description="名称"),
            ),
            response_params=(
                ActionParamDef(param_code="success", param_type="boolean", description="是否成功"),
            ),
        )
        assert len(action.request_params) == 2
        assert len(action.response_params) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# RelationDef 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestRelationDef:
    """RelationDef 构造、joinkeys、ext_field 测试。"""

    def test_construction_has_field(self) -> None:
        """HAS_FIELD 关系构造。"""
        rel = RelationDef(
            source_term_code="L1#object#by_customer",
            target_term_code="L1#prop#customer_name",
            relation_name="客户_拥有字段_客户名称",
            relation_category="HAS_FIELD",
            cardinality="1:N",
            ext_field={"field_alias": "客户名称"},
        )
        assert rel.relation_category == "HAS_FIELD"
        assert rel.cardinality == "1:N"
        assert rel.ext_field == {"field_alias": "客户名称"}
        assert rel.joinkeys == ()

    def test_construction_many_to_one(self) -> None:
        """MANY_TO_ONE 关系带 joinkeys。"""
        rel = RelationDef(
            source_term_code="L1#object#obj_a",
            target_term_code="L1#object#obj_b",
            relation_name="A关联B",
            relation_category="MANY_TO_ONE",
            cardinality="N:1",
            joinkeys=({"sourceField": "b_id", "targetField": "id"},),
        )
        assert len(rel.joinkeys) == 1
        assert rel.joinkeys[0]["sourceField"] == "b_id"

    def test_construction_defaults(self) -> None:
        """默认值测试：joinkeys 空元组，ext_field None。"""
        rel = RelationDef(
            source_term_code="L1#opp_status#opp_status",
            target_term_code="L1#opp_status#SIGNED",
            relation_name="状态含子项",
            relation_category="HAS_TERM",
            cardinality="",
        )
        assert rel.joinkeys == ()
        assert rel.ext_field is None

    def test_frozen(self) -> None:
        """RelationDef 不可修改。"""
        rel = RelationDef(
            source_term_code="L1#object#a",
            target_term_code="L1#object#b",
            relation_name="ab",
            relation_category="MANY_TO_ONE",
            cardinality="",
        )
        with pytest.raises(FrozenInstanceError):
            rel.relation_name = "changed"


# ═══════════════════════════════════════════════════════════════════════════════
# KnowledgePackage 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestKnowledgePackage:
    """KnowledgePackage 构造与字段完整性测试。"""

    def test_construction_minimal(self) -> None:
        """仅必要字段（terms + relations）构造。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="obj",
                    term_name="对象",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(),
        )
        assert len(pkg.terms) == 1
        assert len(pkg.relations) == 0
        assert pkg.domains == ()
        assert pkg.libraries == ()
        assert pkg.term_types == ()
        assert pkg.actions == ()

    def test_construction_full(self) -> None:
        """全字段 KnowledgePackage 构造。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="by_customer",
                    term_name="客户",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
                TermDef(
                    term_code="customer_name",
                    term_name="客户名称",
                    term_type_code="prop",
                    library_code="L1",
                    domain_code="D1",
                    parent_term_code="by_customer",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#object#by_customer",
                    target_term_code="L1#prop#customer_name",
                    relation_name="客户_拥有字段_客户名称",
                    relation_category="HAS_FIELD",
                    cardinality="1:N",
                    ext_field={"field_alias": "客户名称"},
                ),
            ),
            domains=(DomainDef(domain_code="D1", domain_name="测试域"),),
            libraries=(LibraryDef(library_code="L1", library_name="标准术语库"),),
            term_types=(
                TermTypeDef(type_code="object", type_name="对象", type_category=3),
                TermTypeDef(type_code="prop", type_name="属性", type_category=3),
            ),
            actions=(
                ActionDef(
                    action_code="get_customer",
                    action_name="获取客户",
                    action_type="QUERY",
                    request_url="/api/customer",
                    request_method="GET",
                ),
            ),
        )
        assert len(pkg.terms) == 2
        assert len(pkg.relations) == 1
        assert len(pkg.domains) == 1
        assert len(pkg.libraries) == 1
        assert len(pkg.term_types) == 2
        assert len(pkg.actions) == 1

    def test_frozen(self) -> None:
        """KnowledgePackage 不可修改。"""
        pkg = KnowledgePackage(terms=(), relations=())
        with pytest.raises(FrozenInstanceError):
            pkg.terms = ()
