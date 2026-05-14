"""Locate SQL resources from an installed wheel or a source checkout."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

_SQL_PACKAGE = "datacloud_knowledge.adapters.opengauss._db.sql_assets.sql"


def _repo_sql_dir(kind: str) -> Path:
    package_root = Path(__file__).resolve().parents[5]
    if kind == "ddl":
        return package_root / "db" / "ddl" / "knowledge"
    if kind == "seed":
        return package_root / "db" / "seed" / "knowledge"
    if kind == "migrations":
        return package_root / "db" / "migrations"
    raise ValueError(f"Unknown SQL resource kind: {kind}")


def sql_texts(kind: str) -> list[tuple[str, str]]:
    """Return ordered ``(name, SQL text)`` resources for ``kind``.

    Wheels contain these files under ``sql_assets.sql``.
    Source checkouts use the repository ``db/`` directory as a fallback."""

    traversable = resources.files(f"{_SQL_PACKAGE}.{kind}")
    packaged_files = sorted(
        (path for path in traversable.iterdir() if path.name.endswith(".sql")),
        key=lambda path: path.name,
    )
    materialized = [(path.name, path.read_text(encoding="utf-8")) for path in packaged_files]
    if materialized:
        return materialized

    fallback_dir = _repo_sql_dir(kind)
    if not fallback_dir.exists():
        return []
    return [
        (path.name, path.read_text(encoding="utf-8")) for path in sorted(fallback_dir.glob("*.sql"))
    ]
