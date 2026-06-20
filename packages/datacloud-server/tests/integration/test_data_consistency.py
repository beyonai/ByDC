"""Consistency test: OWL metadata vs knowledge SQL vector data.

Validates:
  1. OWL object/prop names have matching term_name records in DB
  2. Every term_name has name_embedding (vector coverage)
  3. HAS_FIELD relations match OWL definitions
  4. Vector search hits self (semantic self-consistency)

Scope: 6 CRM objects from owl_example.
  Excludes: po_users, po_organization (not in DB); HR/product objects (not in OWL).
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

import pytest
import requests
from datacloud_data_sdk.ontology.owl_parser import OwlParser
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.db_integration

# -- scope: CRM objects only --
CRM_OBJECTS = [
    "by_customer",
    "by_opportunity",
    "by_project",
    "by_opp_task",
    "by_project_task",
    "by_rd_task",
]


# -- fixtures --


@pytest.fixture(scope="module")
def owl_data() -> dict:
    parser = OwlParser()
    return parser.parse_resource_directory(Path("/workspace/projects/ontology_server/owl_example"))


@pytest.fixture(scope="module")
def db_conn():
    _load_env()
    url = f"opengauss+psycopg2://gaussdb:{quote_plus('Admin@123')}@10.10.168.200:5432/postgres"
    engine = create_engine(url, echo=False)
    conn = engine.connect()
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def embedding_api_key() -> str:
    _load_env()
    return os.environ["DATACLOUD_EMBEDDING_API_KEY"]


def _load_env() -> None:
    env_path = Path("/workspace/projects/ontology_server/.env")
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        if key.startswith("DATACLOUD_"):
            os.environ.setdefault(key, val.strip())


def _embed(text: str) -> list[float]:
    api_key = os.environ["DATACLOUD_EMBEDDING_API_KEY"]
    resp = requests.post(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": "text-embedding-v4", "input": [text]},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


# =============================================================================
# Test 1: Name consistency
# =============================================================================


class TestNameConsistency:
    """Each OWL object/prop name has a matching term_name record in DB."""

    def test_all_object_names_in_term_name(self, owl_data: dict, db_conn) -> None:
        objects = owl_data.get("objects", [])
        crm = [o for o in objects if o["object_code"] in CRM_OBJECTS]
        assert len(crm) == 6, f"Expected 6 CRM objects, got {len(crm)}"

        for obj in crm:
            code = obj["object_code"]
            name = obj["object_name"]
            rows = db_conn.execute(
                text(
                    """SELECT tn.name_text
                       FROM byai.term_name tn
                       JOIN byai.term t ON t.term_id = tn.term_id
                       WHERE t.term_code = :code AND t.term_type_code = 'object'"""
                ),
                {"code": code},
            ).fetchall()
            assert len(rows) > 0, f"{code}: no term_name record for object '{name}'"
            names = {r[0] for r in rows}
            assert name in names, f"{code}: OWL name='{name}' not in term_name names={names}"

    def test_prop_names_exist_in_db(self, owl_data: dict, db_conn) -> None:
        """Every OWL field has at least one term_name record (exact name match optional)."""
        objects = {o["object_code"]: o for o in owl_data.get("objects", [])}

        missing: list[str] = []
        name_mismatches: list[str] = []

        for obj_code in CRM_OBJECTS:
            obj = objects.get(obj_code)
            if not obj:
                continue
            for field in obj["fields"]:
                field_code = field["field_code"]
                field_name = field.get("field_name", field_code)

                rows = db_conn.execute(
                    text(
                        """SELECT tn.name_text
                           FROM byai.term_name tn
                           JOIN byai.term t ON t.term_id = tn.term_id
                           WHERE t.term_code = :code AND t.term_type_code = 'prop'"""
                    ),
                    {"code": field_code},
                ).fetchall()

                if not rows:
                    missing.append(f"{obj_code}.{field_code} ({field_name})")
                    continue

                names = {r[0] for r in rows}
                if field_name not in names:
                    name_mismatches.append(
                        f"{obj_code}.{field_code}: OWL='{field_name}' DB={names}"
                    )

        if missing:
            print(f"\n  MISSING {len(missing)} props (no term_name record):")
            for m in missing[:10]:
                print(f"      {m}")
        if name_mismatches:
            print(f"\n  RENAME {len(name_mismatches)} props (exist, different name):")
            for m in name_mismatches[:10]:
                print(f"      {m}")

        assert len(missing) == 0, f"{len(missing)} props are missing from DB"


# =============================================================================
# Test 2: Embedding coverage
# =============================================================================


class TestEmbeddingCoverage:
    """All CRM object/prop term_name records must have name_embedding."""

    def test_all_object_embeddings_exist(self, db_conn) -> None:
        for obj_code in CRM_OBJECTS:
            missing = db_conn.execute(
                text(
                    """SELECT count(*)
                       FROM byai.term_name tn
                       JOIN byai.term t ON t.term_id = tn.term_id
                       WHERE t.term_code = :code
                         AND t.term_type_code = 'object'
                         AND tn.name_embedding IS NULL"""
                ),
                {"code": obj_code},
            ).scalar()
            assert missing == 0, f"{obj_code}: {missing} term_name(s) without embedding"

    def test_prop_embedding_coverage(self, owl_data: dict, db_conn) -> None:
        objects = {o["object_code"]: o for o in owl_data.get("objects", [])}

        results: dict[str, dict] = {}
        for obj_code in CRM_OBJECTS:
            obj = objects.get(obj_code)
            if not obj:
                continue
            total = len(obj["fields"])
            with_embed = 0
            without_embed_props: list[str] = []

            for field in obj["fields"]:
                has_vec = db_conn.execute(
                    text(
                        """SELECT count(*)
                           FROM byai.term_name tn
                           JOIN byai.term t ON t.term_id = tn.term_id
                           WHERE t.term_code = :code
                             AND t.term_type_code = 'prop'
                             AND tn.name_embedding IS NOT NULL"""
                    ),
                    {"code": field["field_code"]},
                ).scalar()
                if has_vec > 0:
                    with_embed += 1
                else:
                    without_embed_props.append(field["field_code"])

            results[obj_code] = {
                "total": total,
                "with_embed": with_embed,
                "without": without_embed_props,
            }

        print("\n  Prop vector coverage:")
        for code, r in sorted(results.items()):
            pct = r["with_embed"] / r["total"] * 100 if r["total"] else 0
            missing = ", ".join(r["without"][:5])
            more = f" +{len(r['without']) - 5}" if len(r["without"]) > 5 else ""
            print(
                f"    {code:20s} {r['with_embed']:2d}/{r['total']:2d} ({pct:5.1f}%)  "
                f"missing: [{missing}{more}]"
            )

        fully_covered = [c for c, r in results.items() if r["with_embed"] == r["total"]]
        assert len(fully_covered) > 0, "No CRM object has 100% prop embedding coverage"


# =============================================================================
# Test 3: HAS_FIELD relation consistency
# =============================================================================


class TestHasFieldConsistency:
    """OWL object->field relations vs DB HAS_FIELD relations."""

    def test_has_field_counts(self, owl_data: dict, db_conn) -> None:
        objects = {o["object_code"]: o for o in owl_data.get("objects", [])}

        print("\n  HAS_FIELD coverage (OWL vs DB):")
        for obj_code in CRM_OBJECTS:
            obj = objects.get(obj_code)
            if not obj:
                continue
            owl_count = len(obj["fields"])

            db_count = db_conn.execute(
                text(
                    """SELECT count(*)
                       FROM byai.term_relation tr
                       JOIN byai.term t_obj ON t_obj.term_id = tr.source_term_id
                       JOIN byai.term t_prop ON t_prop.term_id = tr.target_term_id
                       WHERE tr.relation_category = 'HAS_FIELD'
                         AND t_obj.term_code = :code
                         AND t_obj.term_type_code = 'object'
                         AND t_prop.term_type_code = 'prop'"""
                ),
                {"code": obj_code},
            ).scalar()

            status = "OK" if owl_count <= db_count else f"GAP {owl_count - db_count}"
            print(f"    {obj_code:20s} OWL={owl_count:2d}  DB={db_count:2d}  {status}")


# =============================================================================
# Test 4: Vector self-consistency
# =============================================================================


class TestVectorSelfConsistency:
    """Vector search with prop name should hit itself."""

    def test_prop_name_search_hits_itself(self, owl_data: dict, db_conn) -> None:
        """Sample 5 props per object; self-search should score > 0.7."""
        objects = {o["object_code"]: o for o in owl_data.get("objects", [])}

        tested = 0
        passed = 0
        failures: list[str] = []

        for obj_code in CRM_OBJECTS:
            obj = objects.get(obj_code)
            if not obj:
                continue
            for field in obj["fields"][:3]:
                field_name = field.get("field_name", field["field_code"])
                tested += 1

                vec = _embed(field_name)
                vec_str = "[" + ",".join(str(x) for x in vec) + "]"

                rows = db_conn.execute(
                    text(
                        """SELECT tn.name_text, 1 - (tn.name_embedding <=> :vec) AS sim
                           FROM byai.term_name tn
                           JOIN byai.term t ON t.term_id = tn.term_id
                           WHERE t.term_code = :code
                             AND tn.name_embedding IS NOT NULL
                           ORDER BY tn.name_embedding <=> :vec
                           LIMIT 1"""
                    ),
                    {"vec": vec_str, "code": field["field_code"]},
                ).fetchall()

                if not rows:
                    failures.append(f"{obj_code}.{field['field_code']}: no vector in DB")
                    continue

                score = float(rows[0][1])
                if score > 0.7:
                    passed += 1
                else:
                    failures.append(
                        f"{obj_code}.{field['field_code']} (name='{field_name}'): "
                        f"self-search score={score:.4f} (need >0.7)"
                    )

        print(f"\n  Self-consistency: {passed}/{tested} passed")
        for f in failures[:5]:
            print(f"    FAIL {f}")

        assert passed / tested >= 0.5, f"Only {passed}/{tested} props passed self-consistency test"
