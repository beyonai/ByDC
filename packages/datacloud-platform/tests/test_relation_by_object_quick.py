"""Quick verification for get_relations_by_object batch name resolution (方案A).

Covers: batch name_map path, fallback path (code missing from map),
compatibility of _raw_to_relation_dict without name_map, owner/user filters.
"""

from __future__ import annotations

from datacloud_platform.adapters.data_adapter._composite import DataCloudDataBackend
from datacloud_platform.adapters.json_entity_store import JsonEntityStore


def _make_backend(tmp_path):
    store = JsonEntityStore(tmp_path)
    backend = DataCloudDataBackend(entity_store=store)
    return store, backend


def _save_object(store, code: str, name: str) -> None:
    store.save("objects", code, {"object_code": code, "object_name": name})


def _save_relation(
    store,
    code: str,
    src: str,
    tgt: str,
    owner: str = "enterprise",
    user: str | None = None,
) -> None:
    rel = {
        "relation_code": code,
        "relation_name": code,
        "source_class": src,
        "target_class": tgt,
        "relation_type": "one_to_many",
        "owner_type": owner,
    }
    if user:
        rel["user_code"] = user
    store.save("relations", code, rel)


def test_batch_name_resolution(tmp_path):
    """Happy path: names resolved via batch search, filtering intact."""
    store, backend = _make_backend(tmp_path)
    _save_object(store, "obj_a", "对象A")
    _save_object(store, "obj_b", "对象B")
    _save_object(store, "obj_c", "对象C")
    _save_relation(store, "rel_ab", "obj_a", "obj_b")
    _save_relation(store, "rel_ac", "obj_a", "obj_c")

    result = backend.get_relations_by_object("obj_a")
    assert len(result) == 2
    codes = {r["relationCode"] for r in result}
    assert codes == {"rel_ab", "rel_ac"}
    for r in result:
        assert r["sourceObjectName"] == "对象A"
        assert r["targetObjectName"] in ("对象B", "对象C")

    # Bidirectional: querying the target side also matches
    result_b = backend.get_relations_by_object("obj_b")
    assert [r["relationCode"] for r in result_b] == ["rel_ab"]
    assert result_b[0]["sourceObjectName"] == "对象A"


def test_fallback_for_missing_object_codes(tmp_path):
    """Relation referencing a non-existent object: no crash, empty name (old behavior)."""
    store, backend = _make_backend(tmp_path)
    _save_object(store, "obj_a", "对象A")
    _save_relation(store, "rel_missing", "obj_a", "ghost_obj")

    result = backend.get_relations_by_object("obj_a")
    assert len(result) == 1
    r = result[0]
    assert r["sourceObjectName"] == "对象A"
    assert r["targetObjectCode"] == "ghost_obj"
    assert r["targetObjectName"] == ""


def test_owner_user_filters_unchanged(tmp_path):
    """owner_type / user_code filtering semantics preserved."""
    store, backend = _make_backend(tmp_path)
    _save_object(store, "obj_a", "对象A")
    _save_object(store, "obj_b", "对象B")
    _save_relation(store, "rel_ent", "obj_a", "obj_b", owner="enterprise")
    _save_relation(
        store, "rel_personal_me", "obj_a", "obj_b", owner="personal", user="u1"
    )
    _save_relation(
        store, "rel_personal_other", "obj_a", "obj_b", owner="personal", user="u2"
    )

    assert len(backend.get_relations_by_object("obj_a", owner_type="enterprise")) == 1
    personal = backend.get_relations_by_object("obj_a", owner_type="personal")
    assert {r["relationCode"] for r in personal} == {
        "rel_personal_me",
        "rel_personal_other",
    }
    mine = backend.get_relations_by_object(
        "obj_a", owner_type="personal", user_code="u1"
    )
    assert [r["relationCode"] for r in mine] == ["rel_personal_me"]


def test_raw_to_relation_dict_compat_without_name_map(tmp_path):
    """_raw_to_relation_dict without name_map keeps legacy per-get behavior."""
    store, backend = _make_backend(tmp_path)
    _save_object(store, "obj_a", "对象A")
    _save_object(store, "obj_b", "对象B")
    raw = {
        "relation_code": "rel_legacy",
        "source_class": "obj_a",
        "target_class": "obj_b",
    }
    store.save("relations", "rel_legacy", raw)
    sub_store = store.sub_store("")
    out = backend._raw_to_relation_dict(raw, sub_store)
    assert out["sourceObjectName"] == "对象A"
    assert out["targetObjectName"] == "对象B"
    assert out["relationCode"] == "rel_legacy"


# ── Store-level: top_level_or_filters + page_size=None ────────────────────


def test_store_top_level_or_filters(tmp_path):
    """search top_level_or_filters: OR semantics over top-level JSON keys."""
    store, _ = _make_backend(tmp_path)
    _save_object(store, "obj_a", "对象A")
    _save_object(store, "obj_b", "对象B")
    _save_object(store, "obj_c", "对象C")
    _save_relation(store, "rel_ab", "obj_a", "obj_b")
    _save_relation(store, "rel_ac", "obj_a", "obj_c")
    _save_relation(store, "rel_bc", "obj_b", "obj_c")

    sub = store.sub_store("")
    # matches source_class == obj_b OR target_class == obj_b
    items, total = sub.search(
        "relations",
        top_level_or_filters={"source_class": ["obj_b"], "target_class": ["obj_b"]},
    )
    assert total == 2
    assert {it["relation_code"] for it in items} == {"rel_ab", "rel_bc"}

    # combined with owner_type (AND semantics across filter kinds)
    _save_relation(store, "rel_bc_personal", "obj_b", "obj_c", owner="personal")
    items, total = sub.search(
        "relations",
        top_level_or_filters={"source_class": ["obj_b"], "target_class": ["obj_b"]},
        owner_type="personal",
    )
    assert total == 1
    assert items[0]["relation_code"] == "rel_bc_personal"


def test_store_search_page_size_none(tmp_path):
    """search page_size=None returns all matches without pagination."""
    store, _ = _make_backend(tmp_path)
    for i in range(30):
        _save_object(store, f"obj_{i}", f"对象{i}")
    for i in range(30):
        _save_relation(store, f"rel_{i}", "obj_0", f"obj_{i}")

    sub = store.sub_store("")
    items, total = sub.search(
        "relations",
        top_level_or_filters={"source_class": ["obj_0"], "target_class": ["obj_0"]},
        page_size=None,
    )
    # 30 relations all have source_class=obj_0; default page_size=20 would
    # truncate, page_size=None must return all.
    assert total == 30
    assert len(items) == 30


# ── OpenGauss: SQL pushdown construction (compile-level, no DB needed) ────


class _FakeRows:
    def all(self) -> list:
        return []

    def scalar(self) -> int:
        return 1


class _FakeSession:
    def __init__(self) -> None:
        self.stmts: list = []

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def execute(self, stmt: object) -> _FakeRows:
        self.stmts.append(stmt)
        return _FakeRows()


def test_opengauss_top_level_or_pushdown():
    """search top_level_or_filters compiles to OR'd JSONB conditions; page_size=None drops LIMIT."""
    from unittest import mock

    from sqlalchemy import Select
    from sqlalchemy.dialects import postgresql

    from datacloud_platform.adapters.opengauss_entity_store import OpenGaussEntityStore

    fake_session = _FakeSession()
    with (
        mock.patch(
            "datacloud_platform.adapters.opengauss_entity_store._get_or_create_engine",
            return_value=object(),
        ),
        mock.patch("sqlalchemy.orm.Session", return_value=fake_session),
    ):
        store = OpenGaussEntityStore("test-base")
        items, total = store.search(
            "relations",
            top_level_or_filters={
                "source_class": ["obj_x"],
                "target_class": ["obj_x"],
            },
            page_size=None,
        )

    assert items == [] and total == 1
    selects = [s for s in fake_session.stmts if isinstance(s, Select)]
    assert selects, "expected at least one SELECT statement"
    data_sql = str(selects[-1].compile(dialect=postgresql.dialect()))
    assert "ontology_relations" in data_sql
    # OR pushdown: JSONB ->> extraction combined with OR, two bound keys
    assert "data ->>" in data_sql
    assert " OR " in data_sql
    # page_size=None → no LIMIT / OFFSET
    assert "LIMIT" not in data_sql.upper()

    # Default page_size keeps pagination intact
    fake_session2 = _FakeSession()
    with (
        mock.patch(
            "datacloud_platform.adapters.opengauss_entity_store._get_or_create_engine",
            return_value=object(),
        ),
        mock.patch("sqlalchemy.orm.Session", return_value=fake_session2),
    ):
        store2 = OpenGaussEntityStore("test-base")
        store2.search(
            "relations",
            top_level_or_filters={
                "source_class": ["obj_x"],
                "target_class": ["obj_x"],
            },
        )
    selects2 = [s for s in fake_session2.stmts if isinstance(s, Select)]
    paged_sql = str(selects2[-1].compile(dialect=postgresql.dialect()))
    assert "LIMIT" in paged_sql.upper()
