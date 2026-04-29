"""T1：OntologyLoader.load_view_with_deps / load_object_with_deps 单元测试（红阶段）。

验收目标：
- TC-T1-1: load_view_with_deps - view_dir 不存在时不抛异常、不加载任何内容
- TC-T1-2: load_view_with_deps - view_dir 存在时解析 view 并加载依赖 object
- TC-T1-3: load_view_with_deps - 追加语义：load_from_content 仅被调用，现有类不被清空
- TC-T1-4: load_object_with_deps - object_dir 不存在时不抛异常
- TC-T1-5: load_object_with_deps - object_dir 存在时解析 object 并写入 loader
- TC-T1-6: load_object_with_deps - 追加语义：现有类不被清空
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from datacloud_data_sdk.ontology.loader import OntologyLoader

# ── 模块级 patch 路径 ──────────────────────────────────────────────────────────
# OwlParser 在方法内部延迟导入（from datacloud_data_sdk.ontology.owl_parser import OwlParser），
# 需 patch 其定义模块，使延迟导入时拿到 mock。
_PARSER_PATH = "datacloud_data_sdk.ontology.owl_parser.OwlParser"

# ── 辅助：最简 stub content（load_from_content 接受的格式）────────────────────
_STUB_CONTENT: dict = {
    "objects": [
        {
            "object_code": "stub_obj",
            "object_name": "Stub",
            "fields": [],
            "actions": [],
        }
    ],
    "relations": [],
    "functions": {},
    "views": [],
    "datasource_configs": {},
}


# ── TC-T1-1: view_dir 不存在时静默跳过 ───────────────────────────────────────


def test_load_view_with_deps_missing_dir_does_not_raise(tmp_path: Path) -> None:
    """view_dir 不存在时不抛异常，也不调用 parser。"""
    loader = OntologyLoader()
    nonexistent = tmp_path / "view" / "no_such_view"
    # 确认目录不存在
    assert not nonexistent.is_dir()
    # 应静默完成，不抛异常
    loader.load_view_with_deps(tmp_path, "no_such_view")


def test_load_view_with_deps_missing_dir_does_not_load(tmp_path: Path) -> None:
    """view_dir 不存在时 load_from_content 不被调用。"""
    loader = OntologyLoader()
    with patch.object(loader, "load_from_content") as mock_load:
        loader.load_view_with_deps(tmp_path, "no_such_view")
        mock_load.assert_not_called()


# ── TC-T1-2: view_dir 存在时调用 parser 并加载依赖 object ────────────────────


def test_load_view_with_deps_calls_parser_when_dir_exists(tmp_path: Path) -> None:
    """view_dir 存在时调用 _parse_new_layout_view_directory。"""
    view_id = "scene_sales"
    view_dir = tmp_path / "view" / view_id
    view_dir.mkdir(parents=True)

    mock_parser = MagicMock()
    parsed_view = MagicMock()
    parsed_view.object_codes = []
    mock_parser._views.get.return_value = parsed_view
    mock_parser._build_content.return_value = _STUB_CONTENT

    with patch(_PARSER_PATH, return_value=mock_parser):
        loader = OntologyLoader()
        loader.load_view_with_deps(tmp_path, view_id)

    mock_parser._parse_new_layout_view_directory.assert_called_once_with(view_dir)


def test_load_view_with_deps_loads_dependent_objects(tmp_path: Path) -> None:
    """view_dir 存在时，依赖的每个 object 目录都会被解析。"""
    view_id = "scene_crm"
    view_dir = tmp_path / "view" / view_id
    view_dir.mkdir(parents=True)

    dep_obj = "by_customer"
    obj_dir = tmp_path / "object" / dep_obj
    obj_dir.mkdir(parents=True)

    mock_parser = MagicMock()
    parsed_view = MagicMock()
    parsed_view.object_codes = [dep_obj]
    mock_parser._views.get.return_value = parsed_view
    mock_parser._build_content.return_value = _STUB_CONTENT

    with patch(_PARSER_PATH, return_value=mock_parser):
        loader = OntologyLoader()
        loader.load_view_with_deps(tmp_path, view_id)

    mock_parser._parse_new_layout_object_directory.assert_called_once_with(obj_dir)


def test_load_view_with_deps_skips_missing_object_dir(tmp_path: Path) -> None:
    """依赖的 object 目录不存在时跳过，不抛异常。"""
    view_id = "scene_sales"
    view_dir = tmp_path / "view" / view_id
    view_dir.mkdir(parents=True)

    mock_parser = MagicMock()
    parsed_view = MagicMock()
    parsed_view.object_codes = ["missing_obj"]
    mock_parser._views.get.return_value = parsed_view
    mock_parser._build_content.return_value = _STUB_CONTENT

    with patch(_PARSER_PATH, return_value=mock_parser):
        loader = OntologyLoader()
        loader.load_view_with_deps(tmp_path, view_id)

    mock_parser._parse_new_layout_object_directory.assert_not_called()


# ── TC-T1-3: 追加语义，不清空现有 _classes ───────────────────────────────────


def test_load_view_with_deps_is_additive(tmp_path: Path) -> None:
    """load_view_with_deps 使用 load_from_content（追加），不清空已有类。"""
    view_dir = tmp_path / "view" / "v1"
    view_dir.mkdir(parents=True)

    mock_parser = MagicMock()
    mock_parser._views.get.return_value = MagicMock(object_codes=[])
    mock_parser._build_content.return_value = _STUB_CONTENT

    loader = OntologyLoader()
    # 预先向 loader 写入一个类
    loader.load_from_content(
        {
            "objects": [
                {
                    "object_code": "existing_obj",
                    "object_name": "Existing",
                    "fields": [],
                    "actions": [],
                }
            ],
            "relations": [],
            "functions": {},
        }
    )
    assert "existing_obj" in loader._classes

    with patch(_PARSER_PATH, return_value=mock_parser):
        loader.load_view_with_deps(tmp_path, "v1")

    # 已有类不应被清空
    assert "existing_obj" in loader._classes


# ── TC-T1-4: load_object_with_deps - object_dir 不存在时静默跳过 ─────────────


def test_load_object_with_deps_missing_dir_does_not_raise(tmp_path: Path) -> None:
    loader = OntologyLoader()
    loader.load_object_with_deps(tmp_path, "no_such_object")


def test_load_object_with_deps_missing_dir_no_load(tmp_path: Path) -> None:
    loader = OntologyLoader()
    with patch.object(loader, "load_from_content") as mock_load:
        loader.load_object_with_deps(tmp_path, "no_such_object")
        mock_load.assert_not_called()


# ── TC-T1-5: load_object_with_deps - object_dir 存在时调用 parser ────────────


def test_load_object_with_deps_calls_parser_when_dir_exists(tmp_path: Path) -> None:
    obj_code = "by_order"
    obj_dir = tmp_path / "object" / obj_code
    obj_dir.mkdir(parents=True)

    mock_parser = MagicMock()
    mock_parser._build_content.return_value = _STUB_CONTENT

    with patch(_PARSER_PATH, return_value=mock_parser):
        loader = OntologyLoader()
        loader.load_object_with_deps(tmp_path, obj_code)

    mock_parser._parse_new_layout_object_directory.assert_called_once_with(obj_dir)
    mock_parser._apply_mappings_to_objects.assert_called_once()


# ── TC-T1-6: load_object_with_deps 是追加语义 ────────────────────────────────


def test_load_object_with_deps_is_additive(tmp_path: Path) -> None:
    obj_code = "by_order"
    obj_dir = tmp_path / "object" / obj_code
    obj_dir.mkdir(parents=True)

    mock_parser = MagicMock()
    mock_parser._build_content.return_value = _STUB_CONTENT

    loader = OntologyLoader()
    loader.load_from_content(
        {
            "objects": [
                {
                    "object_code": "pre_existing",
                    "object_name": "PreExisting",
                    "fields": [],
                    "actions": [],
                }
            ],
            "relations": [],
            "functions": {},
        }
    )
    assert "pre_existing" in loader._classes

    with patch(_PARSER_PATH, return_value=mock_parser):
        loader.load_object_with_deps(tmp_path, obj_code)

    assert "pre_existing" in loader._classes
