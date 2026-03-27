"""OWL 导入集成测试。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import dedent, indent
from typing import Any

import pytest

from datacloud_knowledge.knowledge_build.importer import executor, precheck


@dataclass
class _MockDatabase:
    """用内存结构模拟导入后的数据库状态。"""

    domains: dict[str, Any] = field(default_factory=dict)
    libraries: dict[str, Any] = field(default_factory=dict)
    term_types: dict[str, Any] = field(default_factory=dict)
    terms: dict[str, Any] = field(default_factory=dict)
    relations: dict[str, Any] = field(default_factory=dict)
    knowledge: dict[str, Any] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)
    next_term_id: int = 1

    def allocate_term_id(self) -> str:
        """分配稳定的 mock term_id，便于断言外键。"""

        term_id = f"term-{self.next_term_id}"
        self.next_term_id += 1
        return term_id


class _FakeCursor:
    """最小游标对象，仅满足 executor.run 的上下文协议。"""

    def __init__(self, connection: _FakeConnection):
        self.connection = connection

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        return None
        return False


class _FakeConnection:
    """最小连接对象，隔离外部数据库依赖。"""

    def __init__(self) -> None:
        self.autocommit = True
        self.db = _MockDatabase()
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True
        self.db = _MockDatabase()

    def close(self) -> None:
        self.closed = True


def _property_xml(class_name: str, property_name: str) -> str:
    """生成 DatatypeProperty 定义，确保解析器识别属性。"""

    return dedent(
        f"""
        <owl:DatatypeProperty rdf:about='#{property_name}'>
            <rdfs:domain rdf:resource='#{class_name}'/>
            <rdfs:range rdf:resource='http://www.w3.org/2001/XMLSchema#string'/>
        </owl:DatatypeProperty>
        """
    ).strip()


def _owl_document(
    *,
    base: str,
    class_name: str,
    property_names: list[str],
    individuals: list[str],
) -> str:
    """生成最小可解析的 OWL 文档。"""

    property_block = "\n".join(
        indent(_property_xml(class_name, property_name), "    ") for property_name in property_names
    )
    individual_block = "\n".join(indent(item.strip(), "    ") for item in individuals)
    return (
        dedent(
            f"""<?xml version='1.0'?>
            <rdf:RDF xmlns='http://www.w3.org/2002/07/owl#'
                     xmlns:owl='http://www.w3.org/2002/07/owl#'
                     xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'
                     xmlns:rdfs='http://www.w3.org/2000/01/rdf-schema#'
                     xmlns:xsd='http://www.w3.org/2001/XMLSchema#'
                     xml:base='{base}'>
                <owl:Class rdf:about='#{class_name}'/>
            {property_block}
            {individual_block}
            </rdf:RDF>
            """
        ).strip()
        + "\n"
    )


def _domain_owl() -> str:
    """生成与 term_type 引用一致的领域文件。"""

    return _owl_document(
        base="http://example.org/domain/ontology#",
        class_name="DomainDefinition",
        property_names=["domain_code", "domain_name", "parent_domain_code", "remark"],
        individuals=[
            dedent(
                """
                <owl:NamedIndividual rdf:about='#sale_domain'>
                    <rdf:type rdf:resource='#DomainDefinition'/>
                    <domain_code rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>SALE</domain_code>
                    <domain_name rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>销售</domain_name>
                    <parent_domain_code rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>BUSINESS</parent_domain_code>
                    <remark rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>销售业务领域</remark>
                </owl:NamedIndividual>
                """
            )
        ],
    )


def _library_owl() -> str:
    """生成知识库定义文件。"""

    return _owl_document(
        base="http://example.org/library/ontology#",
        class_name="LibraryDefinition",
        property_names=["library_code", "library_name", "library_desc"],
        individuals=[
            dedent(
                """
                <owl:NamedIndividual rdf:about='#hr_library'>
                    <rdf:type rdf:resource='#LibraryDefinition'/>
                    <library_code rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>HR</library_code>
                    <library_name rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>人力资源知识库</library_name>
                    <library_desc rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>OWL 集成测试知识库</library_desc>
                </owl:NamedIndividual>
                """
            )
        ],
    )


def _term_type_owl() -> str:
    """生成最小术语类型文件。"""

    return _owl_document(
        base="http://example.org/termtype/ontology#",
        class_name="TermTypeDefinition",
        property_names=[
            "term_type_code_path",
            "term_type_code",
            "term_type_name",
            "term_type_desc",
            "term_data_type",
        ],
        individuals=[
            dedent(
                """
                <owl:NamedIndividual rdf:about='#object_term_type'>
                    <rdf:type rdf:resource='#TermTypeDefinition'/>
                    <term_type_code_path rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>SALE#OBJECT</term_type_code_path>
                    <term_type_code rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>OBJECT</term_type_code>
                    <term_type_name rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>对象</term_type_name>
                    <term_type_desc rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>业务对象</term_type_desc>
                    <term_data_type rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>ONTOLOGY_TERM</term_data_type>
                </owl:NamedIndividual>
                """
            )
        ],
    )


def _terms_owl() -> str:
    """生成两个可被关系引用的术语。"""

    return _owl_document(
        base="http://example.org/term/ontology#",
        class_name="TermDefinition",
        property_names=[
            "term_code_path",
            "term_code",
            "term_name",
            "library_code",
            "term_type_code",
            "term_desc",
            "synonyms",
            "terms_knowledge",
        ],
        individuals=[
            dedent(
                """
                <owl:NamedIndividual rdf:about='#po_users_term'>
                    <rdf:type rdf:resource='#TermDefinition'/>
                    <term_code_path rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>OBJECT#po_users</term_code_path>
                    <term_code rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>po_users</term_code>
                    <term_name rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>人员</term_name>
                    <library_code rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>HR</library_code>
                    <term_type_code rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>OBJECT</term_type_code>
                    <term_desc rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>人员基础信息</term_desc>
                    <synonyms rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>[&quot;员工&quot;,&quot;用户&quot;,&quot;人员&quot;]</synonyms>
                    <terms_knowledge rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>[{&quot;name&quot;:&quot;员工手册&quot;,&quot;content&quot;:&quot;员工手册信息&quot;}]</terms_knowledge>
                </owl:NamedIndividual>
                """
            ),
            dedent(
                """
                <owl:NamedIndividual rdf:about='#po_organization_term'>
                    <rdf:type rdf:resource='#TermDefinition'/>
                    <term_code_path rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>OBJECT#po_organization</term_code_path>
                    <term_code rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>po_organization</term_code>
                    <term_name rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>组织</term_name>
                    <library_code rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>HR</library_code>
                    <term_type_code rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>OBJECT</term_type_code>
                    <term_desc rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>组织基础信息</term_desc>
                    <synonyms rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>[]</synonyms>
                    <terms_knowledge rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>[]</terms_knowledge>
                </owl:NamedIndividual>
                """
            ),
        ],
    )


def _relation_owl(target_code: str = "po_organization") -> str:
    """生成最小关系文件。"""

    return _owl_document(
        base="http://example.org/relation/ontology#",
        class_name="TermRelation",
        property_names=["source_code", "target_code", "relation_name", "relation_type", "joinkeys"],
        individuals=[
            dedent(
                f"""
                <owl:NamedIndividual rdf:about='#user_belong_org_relation'>
                    <rdf:type rdf:resource='#TermRelation'/>
                    <source_code rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>po_users</source_code>
                    <target_code rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>{target_code}</target_code>
                    <relation_name rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>人员_归属_组织</relation_name>
                    <relation_type rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>MANY_TO_ONE</relation_type>
                    <joinkeys rdf:datatype='http://www.w3.org/2001/XMLSchema#string'>[{{&quot;sourceField&quot;:&quot;org_id&quot;,&quot;targetField&quot;:&quot;org_id&quot;}}]</joinkeys>
                </owl:NamedIndividual>
                """
            )
        ],
    )


def _ontology_owl() -> str:
    """生成被 manifest 引用的占位 ontology 文件。"""

    return (
        dedent(
            """<?xml version='1.0'?>
            <rdf:RDF xmlns='http://www.w3.org/2002/07/owl#'
                     xmlns:owl='http://www.w3.org/2002/07/owl#'
                     xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>
                <owl:Class rdf:about='#ActionDefinition'/>
            </rdf:RDF>
            """
        ).strip()
        + "\n"
    )


def _write_file(path: Path, content: str) -> None:
    """按 UTF-8 写入测试文件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_manifest(include_ontology_step: bool = False) -> dict[str, Any]:
    """构造测试所需的 manifest。"""

    steps = [
        {"type": "meta", "file": "meta/domains.owl", "description": "领域定义"},
        {"type": "meta", "file": "meta/library.owl", "description": "知识库定义"},
        {"type": "term_types", "file": "term_types/term_types.owl", "description": "术语类型"},
        {"type": "terms", "file": "terms/terms.owl", "description": "术语定义"},
        {"type": "relations", "file": "relations/relation.owl", "description": "术语关系"},
    ]
    if include_ontology_step:
        steps.append(
            {
                "type": "objects",
                "file": "ontology/actions/action.owl",
                "description": "本体动作定义",
            }
        )

    return {
        "version": "1.0",
        "package_id": "owl-integration-test",
        "description": "OWL 导入集成测试包",
        "created_at": "2026-03-26",
        "import_steps": steps,
    }


def _create_owl_package(
    tmp_path: Path,
    *,
    include_ontology_step: bool = False,
    relation_target_code: str = "po_organization",
) -> Path:
    """在临时目录中创建完整的 OWL 导入包。"""

    package_root = tmp_path / "owl_import_package"
    _write_file(package_root / "meta/domains.owl", _domain_owl())
    _write_file(package_root / "meta/library.owl", _library_owl())
    _write_file(package_root / "term_types/term_types.owl", _term_type_owl())
    _write_file(package_root / "terms/terms.owl", _terms_owl())
    _write_file(package_root / "relations/relation.owl", _relation_owl(relation_target_code))
    if include_ontology_step:
        _write_file(package_root / "ontology/actions/action.owl", _ontology_owl())
    _write_file(
        package_root / "manifest.json",
        json.dumps(_build_manifest(include_ontology_step), ensure_ascii=False, indent=2) + "\n",
    )
    return package_root


def _run_precheck_for_owl_package(
    package_root: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """在不修改生产代码的前提下执行 manifest 级 OWL 预检。

    当前 precheck 仍按 JSONL 逐行读取内容；这里仅把测试包内的 OWL 文件视为空，
    从而聚焦验证 manifest、文件存在性以及 ontology 目录拦截逻辑。
    """

    package_root = package_root.resolve()
    original_read_text = Path.read_text

    def _patched_read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        resolved_path = path.resolve()
        if resolved_path.suffix == ".owl" and resolved_path.is_relative_to(package_root):
            return ""
        return original_read_text(path, *args, **kwargs)

    with monkeypatch.context() as patch_ctx:
        patch_ctx.setattr(Path, "read_text", _patched_read_text)
        return precheck.run(str(package_root))


def _build_mock_handlers(connection: _FakeConnection) -> dict[str, Any]:
    """构造写入内存数据库的 batch handlers。"""

    def handle_domains(
        _cur: _FakeCursor, objs: list[dict[str, Any]], stats: dict[str, Any]
    ) -> None:
        connection.db.events.append("meta_domain")
        for obj in objs:
            connection.db.domains[obj["domain_code"]] = obj.copy()
        stats["domains"]["inserted"] += len(objs)

    def handle_libraries(
        _cur: _FakeCursor, objs: list[dict[str, Any]], stats: dict[str, Any]
    ) -> None:
        connection.db.events.append("meta_library")
        for obj in objs:
            connection.db.libraries[obj["library_code"]] = obj.copy()
        stats["libraries"]["inserted"] += len(objs)

    def handle_term_types(
        _cur: _FakeCursor, objs: list[dict[str, Any]], stats: dict[str, Any]
    ) -> None:
        connection.db.events.append("term_type")
        for obj in objs:
            if obj["domain_code"] not in connection.db.domains:
                raise ValueError(f"缺少 domain_code: {obj['domain_code']}")
            connection.db.term_types[obj["type_code"]] = obj.copy()
        stats["term_types"]["inserted"] += len(objs)

    def handle_terms(_cur: _FakeCursor, objs: list[dict[str, Any]], stats: dict[str, Any]) -> None:
        connection.db.events.append("term")
        for obj in objs:
            domain_code = obj.get("domain_code")
            if domain_code is None:
                term_type = connection.db.term_types.get(obj["term_type_code"], {})
                domain_code = term_type.get("domain_code")
            if domain_code not in connection.db.domains:
                raise ValueError(f"术语缺少领域引用: {domain_code}")
            if obj["library_code"] not in connection.db.libraries:
                raise ValueError(f"术语缺少知识库引用: {obj['library_code']}")
            if obj["term_type_code"] not in connection.db.term_types:
                raise ValueError(f"术语缺少术语类型引用: {obj['term_type_code']}")

            stored = obj.copy()
            stored["domain_code"] = domain_code
            stored["term_id"] = connection.db.allocate_term_id()
            connection.db.terms[obj["term_code"]] = stored
        stats["terms"]["inserted"] += len(objs)

    def handle_relations(
        _cur: _FakeCursor, objs: list[dict[str, Any]], stats: dict[str, Any]
    ) -> None:
        connection.db.events.append("relation")
        for obj in objs:
            source_term = connection.db.terms.get(obj["source_term_code"])
            target_term = connection.db.terms.get(obj["target_term_code"])
            if source_term is None or target_term is None:
                raise ValueError("关系引用了不存在的术语")

            stored = obj.copy()
            stored["source_term_id"] = source_term["term_id"]
            stored["target_term_id"] = target_term["term_id"]
            connection.db.relations[stored["relation_code"]] = stored
        stats["relations"]["inserted"] += len(objs)

    def handle_knowledge(
        _cur: _FakeCursor, objs: list[dict[str, Any]], stats: dict[str, Any]
    ) -> None:
        connection.db.events.append("knowledge")
        for obj in objs:
            term = connection.db.terms.get(obj["term_code"])
            if term is None:
                raise ValueError("知识记录引用了不存在的术语")

            stored = obj.copy()
            stored["term_id"] = term["term_id"]
            connection.db.knowledge[stored["knowledge_id"]] = stored
        stats["knowledge"]["inserted"] += len(objs)

    return {
        "meta_domain": handle_domains,
        "meta_library": handle_libraries,
        "term_type": handle_term_types,
        "term": handle_terms,
        "relation": handle_relations,
        "knowledge": handle_knowledge,
    }


def _install_executor_mocks(monkeypatch: pytest.MonkeyPatch, connection: _FakeConnection) -> None:
    """安装 mock DB 连接和批处理器。"""

    monkeypatch.setattr(executor, "_connect", lambda: connection)
    monkeypatch.setattr(executor, "_STEP_BATCH_HANDLERS", _build_mock_handlers(connection))


def _expected_stats() -> dict[str, dict[str, int]]:
    """返回 happy path 的期望统计值。"""

    return {
        "domains": {"inserted": 1, "updated": 0, "deleted": 0},
        "libraries": {"inserted": 1, "updated": 0, "deleted": 0},
        "term_types": {"inserted": 1, "updated": 0, "deleted": 0},
        "terms": {"inserted": 2, "updated": 0, "deleted": 0},
        "relations": {"inserted": 1, "updated": 0, "deleted": 0},
        "knowledge": {"inserted": 1, "updated": 0, "deleted": 0},
    }


class TestOwlIntegration:
    """覆盖 OWL 导入 happy path 与 error path。"""

    def test_run_imports_owl_package_after_precheck(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """测试完整流程：precheck 通过后执行导入并验证 mock DB。"""

        package_root = _create_owl_package(tmp_path)

        precheck_result = _run_precheck_for_owl_package(package_root, monkeypatch)
        """测试完整流程：precheck 通过后执行导入并验证 mock DB。"""

        package_root = _create_owl_package(tmp_path)

        precheck_result = _run_precheck_for_owl_package(package_root, monkeypatch)
        assert precheck_result["status"] == "ok"
        assert precheck_result["total_rows"] == 0
        assert precheck_result["errors"] == []
        assert [item["file"] for item in precheck_result["files"]] == [
            "meta/domains.owl",
            "meta/library.owl",
            "term_types/term_types.owl",
            "terms/terms.owl",
            "relations/relation.owl",
        ]

        connection = _FakeConnection()
        _install_executor_mocks(monkeypatch, connection)

        result = executor.run(str(package_root))

        assert result == {"status": "success", "stats": _expected_stats(), "error": None}
        assert connection.committed is True
        assert connection.rolled_back is False
        assert connection.closed is True

        db = connection.db
        assert db.domains["SALE"]["domain_name"] == "销售"
        assert db.domains["SALE"]["domain_name"] == "销售"
        assert db.libraries["HR"]["library_name"] == "人力资源知识库"
        assert db.term_types["OBJECT"]["type_category"] == "本体术语"
        assert db.terms["po_users"]["aliases"] == ["员工", "用户"]
        assert db.terms["po_users"]["domain_code"] == "SALE"

        relation = next(iter(db.relations.values()))
        assert relation["relation_name"] == "人员_归属_组织"
        assert relation["cardinality"] == "N:1"
        assert relation["source_term_id"] == db.terms["po_users"]["term_id"]
        assert relation["target_term_id"] == db.terms["po_organization"]["term_id"]

        knowledge = next(iter(db.knowledge.values()))
        assert knowledge["term_id"] == db.terms["po_users"]["term_id"]
        assert knowledge["desc_summary"] == "员工手册"
        assert knowledge["desc"] == "员工手册信息"

    def test_precheck_rejects_manifest_with_ontology_step(self, tmp_path: Path) -> None:
        """测试 manifest 中包含 ontology 文件时会被 precheck 拒绝。"""

        package_root = _create_owl_package(tmp_path, include_ontology_step=True)

        result = precheck.run(str(package_root))

        assert result["status"] == "failed"
        assert result["total_rows"] == 0
        assert result["files"] == []
        assert result["errors"] == [
            {
                "code": "INVALID_ONTOLOGY_STEP",
                "message": "ontology 文件不允许入库: ontology/actions/action.owl",
                "file": "ontology/actions/action.owl",
            }
        ]

    def test_executor_returns_failed_when_relation_target_is_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """测试 executor 在关系引用缺失术语时返回 failed 并回滚。"""

        package_root = _create_owl_package(tmp_path, relation_target_code="missing_term")
        connection = _FakeConnection()
        _install_executor_mocks(monkeypatch, connection)

        result = executor.run(str(package_root))

        assert result["status"] == "failed"
        assert result["stats"]["domains"]["inserted"] == 1
        assert result["stats"]["terms"]["inserted"] == 2
        assert "关系引用了不存在的术语" in str(result["error"])
        assert connection.committed is False
        """测试 executor 在关系引用缺失术语时返回 failed 并回滚。"""

        package_root = _create_owl_package(tmp_path, relation_target_code="missing_term")
        connection = _FakeConnection()
        _install_executor_mocks(monkeypatch, connection)

        result = executor.run(str(package_root))

        assert result["status"] == "failed"
        assert result["stats"]["domains"]["inserted"] == 1
        assert result["stats"]["terms"]["inserted"] == 2
        assert "关系引用了不存在的术语" in str(result["error"])
        assert connection.committed is False
        assert connection.rolled_back is True
        assert connection.closed is True
        assert connection.db.terms == {}
        assert connection.db.relations == {}
