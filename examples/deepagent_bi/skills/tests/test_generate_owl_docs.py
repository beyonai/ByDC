"""generate_owl_docs.py 单元测试（mock OntologyLoader，不依赖真实 OWL 文件）。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_field(code: str, name: str, role: str = "dimension", kind: str = "name") -> MagicMock:
    f = MagicMock()
    f.field_code = code
    f.field_name = name
    f.property_code = code
    f.property_name = name
    f.analytic_role = role
    f.analytic_kind = kind
    f.filter_ops = ["eq", "in"]
    f.group_ops = ["direct"]
    f.aggregate_ops = []
    f.required_filter_group = None
    f.property_kind = "physical"
    return f


def _make_action(code: str, name: str, desc: str, family: str = "operation") -> MagicMock:
    a = MagicMock()
    a.action_code = code
    a.action_name = name
    a.description = desc
    a.action_family = family
    a.is_virtual = False
    return a


def _make_cls(code: str, name: str, desc: str) -> MagicMock:
    cls = MagicMock()
    cls.object_code = code
    cls.object_name = name
    cls.description = desc
    cls.fields = [
        _make_field("customer_name", "客户名称"),
        _make_field("industry", "行业"),
    ]
    query_action = _make_action(f"query_{code}", f"查询{name}", f"查询{name}明细", "query")
    query_action.is_virtual = True
    compute_action = _make_action(f"compute_{code}", f"统计{name}", f"统计{name}", "compute")
    compute_action.is_virtual = True
    op_action = _make_action(f"create_{code}", f"新增{name}", f"新增一条{name}记录")
    cls.actions = [query_action, compute_action, op_action]
    return cls


class TestGenerateOwlDocs:
    def test_generates_md_for_object(self, tmp_path: Path) -> None:
        """每个对象应生成一个 MD 文件，包含三个区块标题。"""
        resource_dir = tmp_path / "resource"
        output_dir = tmp_path / "owl_docs"
        resource_dir.mkdir()

        mock_loader = MagicMock()
        mock_loader._classes = {"by_customer": _make_cls("by_customer", "客户", "CRM客户主数据")}
        mock_loader._scenes = {}
        mock_loader.get_ontology_class.return_value = _make_cls(
            "by_customer", "客户", "CRM客户主数据"
        )

        mock_schema = {
            "name": "create_by_customer",
            "title": "新增客户",
            "description": "新增一条客户记录",
            "inputSchema": {
                "type": "object",
                "properties": {"customerName": {"type": "string", "description": "客户名称"}},
                "required": ["customerName"],
            },
            "outputSchema": {
                "type": "object",
                "properties": {"id": {"type": "integer", "description": "客户ID"}},
            },
        }

        with (
            patch("scripts.generate_owl_docs.OntologyLoader", return_value=mock_loader),
            patch("scripts.generate_owl_docs.inject_virtual_actions"),
            patch("scripts.generate_owl_docs.Action") as mock_action_cls,
        ):
            mock_action_cls.return_value.get_schema.return_value = mock_schema
            from scripts.generate_owl_docs import generate_object_md

            md = generate_object_md("by_customer", mock_loader)

        assert "# 客户（by_customer）" in md
        assert "**类型**：object" in md
        assert "## 查询能力（query）" in md
        assert "## 统计能力（compute）" in md
        assert "## 操作动作（operations）" in md
        assert "create_by_customer" in md
        assert "customerName" in md

    def test_main_writes_files(self, tmp_path: Path) -> None:
        """main() 应为每个对象写出 MD 文件到 output_dir。"""
        resource_dir = tmp_path / "resource"
        output_dir = tmp_path / "owl_docs"
        resource_dir.mkdir()

        mock_loader = MagicMock()
        mock_loader._classes = {"by_customer": MagicMock()}
        mock_loader._scenes = {}
        mock_loader.get_ontology_class.return_value = _make_cls(
            "by_customer", "客户", "CRM客户主数据"
        )

        with (
            patch("scripts.generate_owl_docs.OntologyLoader", return_value=mock_loader),
            patch("scripts.generate_owl_docs.inject_virtual_actions"),
            patch("scripts.generate_owl_docs.Action") as mock_action_cls,
        ):
            mock_action_cls.return_value.get_schema.return_value = {
                "name": "create_by_customer",
                "title": "新增客户",
                "description": "新增客户",
                "inputSchema": {"type": "object", "properties": {}, "required": []},
                "outputSchema": {"type": "object", "properties": {}},
            }
            import sys

            sys.argv = [
                "generate_owl_docs.py",
                "--resource-dir",
                str(resource_dir),
                "--output-dir",
                str(output_dir),
            ]
            from scripts.generate_owl_docs import main

            main()

        assert (output_dir / "by_customer.md").exists()

    def test_dependency_isolation(self) -> None:
        """主项目 pyproject.toml 不应包含 deepagents 依赖。"""
        root_pyproject = Path(__file__).parents[3] / "pyproject.toml"
        content = root_pyproject.read_text(encoding="utf-8")
        assert "deepagents" not in content
