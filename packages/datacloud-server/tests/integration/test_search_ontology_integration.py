"""Integration tests for search_ontology with real OpenGauss + embedding model.

Requires:
  - OpenGauss at 10.10.168.200:5432 (DATACLOUD_DB_* env vars)
  - DashScope text-embedding-v4 (DATACLOUD_EMBEDDING_API_KEY)
  - psycopg2-binary installed in venv
  - Run with: pytest -m db_integration
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

import pytest
import requests
from datacloud_server.adapters.local_adapter import LocalOntologyAdapter
from datacloud_server.storage.json_writer import JSONWriter
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.db_integration


# ── helpers ──────────────────────────────────────────────────

ENV_PATH = Path("/workspace/projects/ontology_server/.env")


def _load_env() -> None:
    """Load DATACLOUD_* env vars from ontology_server .env."""
    if not ENV_PATH.exists():
        return
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        if key.startswith("DATACLOUD_"):
            os.environ.setdefault(key, val.strip())


def _embed(text: str) -> list[float]:
    """Get embedding from DashScope text-embedding-v4."""
    api_key = os.environ["DATACLOUD_EMBEDDING_API_KEY"]
    resp = requests.post(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": "text-embedding-v4", "input": [text]},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


def _vec_to_pgvector(vec: list[float]) -> str:
    """Convert embedding list to pgvector string format '[v1,v2,...]'."""
    return "[" + ",".join(str(x) for x in vec) + "]"


# ══════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════


class TestSearchOntologyMetadata:
    """search_ontology metadata branch - vector search on object/view/prop/action/func names."""

    def test_metadata_search_hits_object_names(self) -> None:
        """Searching '客户' should hit object/prop names in metadata."""
        _load_env()
        vec = _embed("客户信息")
        vec_str = _vec_to_pgvector(vec)

        url = f"opengauss+psycopg2://gaussdb:{quote_plus('Admin@123')}@10.10.168.200:5432/postgres"
        engine = create_engine(url, echo=False)

        with engine.connect() as c:
            rows = c.execute(
                text(
                    """SELECT tn.name_text, t.term_code, t.term_type_code,
                              1 - (tn.name_embedding <=> :vec) AS sim
                       FROM byai.term_name tn
                       JOIN byai.term t ON t.term_id = tn.term_id
                       WHERE t.term_type_code IN ('object', 'view', 'prop', 'action', 'func')
                         AND tn.name_embedding IS NOT NULL
                       ORDER BY tn.name_embedding <=> :vec
                       LIMIT 5"""
                ),
                {"vec": vec_str},
            ).fetchall()

        assert len(rows) > 0
        top_hit = rows[0][0]
        assert any(kw in top_hit for kw in ["客户", "customer"]), (
            f"Expected customer-related hit, got '{top_hit}'"
        )
        assert rows[0][3] > 0.5


class TestSearchOntologyInstance:
    """search_ontology instance branch - vector search on value term names."""

    def test_instance_search_hits_financial_customers(self) -> None:
        """Searching '金融行业客户' should return bank/financial customer names."""
        _load_env()
        vec = _embed("金融行业客户")
        vec_str = _vec_to_pgvector(vec)

        url = f"opengauss+psycopg2://gaussdb:{quote_plus('Admin@123')}@10.10.168.200:5432/postgres"
        engine = create_engine(url, echo=False)

        with engine.connect() as c:
            rows = c.execute(
                text(
                    """SELECT tn.name_text, t.term_code, t.term_type_code,
                              1 - (tn.name_embedding <=> :vec) AS sim
                       FROM byai.term_name tn
                       JOIN byai.term t ON t.term_id = tn.term_id
                       JOIN byai.term_type tt ON tt.type_code = t.term_type_code
                       WHERE tt.type_category IN (1, 2)
                         AND tn.name_embedding IS NOT NULL
                       ORDER BY tn.name_embedding <=> :vec
                       LIMIT 5"""
                ),
                {"vec": vec_str},
            ).fetchall()

        assert len(rows) > 0
        all_names = [r[0] for r in rows]
        financial_hits = [
            n for n in all_names if any(kw in n for kw in ["银行", "金融", "分行"])
        ]
        assert len(financial_hits) > 0, f"No financial hits in: {all_names[:5]}"
        assert rows[0][3] > 0.5


class TestSearchOntologyIntegration:
    """Test the LocalOntologyAdapter.search_ontology method end-to-end."""

    def test_search_ontology_returns_both_branches(self) -> None:
        """search_ontology('金融行业客户', scope='all') returns metadata + instances."""
        _load_env()

        writer = JSONWriter()
        adapter = LocalOntologyAdapter("/tmp", writer)

        result = adapter.search_ontology(
            "test_base",
            "test_scene",
            {"keyword": "金融行业客户", "searchScope": "all", "queryType": "vector"},
        )

        assert "metadata" in result
        assert "instances" in result
        assert "totalCount" in result

        assert len(result["metadata"]) > 0, "Expected metadata hits"
        meta = result["metadata"][0]
        assert "score" in meta

        assert len(result["instances"]) > 0, "Expected instance hits"
        inst = result["instances"][0]
        assert "objectCode" in inst
        assert "matchedProperty" in inst
        assert "matchedValue" in inst
        assert "score" in inst

        assert result["totalCount"]["metadata"] > 0
        assert result["totalCount"]["instances"] > 0
