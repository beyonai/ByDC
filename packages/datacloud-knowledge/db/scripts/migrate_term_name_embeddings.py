"""向量迁移
- 用法是先配两套环境变量：目标库走现有 DATACLOUD_DB_*，源库走新增 DATACLOUD_SOURCE_DB_*，然后先跑：
- python packages/datacloud-knowledge/db/scripts/migrate_term_name_embeddings.py
- 确认 dry-run 统计没问题后，再跑：
- python packages/datacloud-knowledge/db/scripts/migrate_term_name_embeddings.py --apply

"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlunparse

from psycopg import Connection, sql

LOGGER = logging.getLogger(__name__)

_TARGET_DB_PREFIX = "DATACLOUD_DB_"
_SOURCE_DB_PREFIX = "DATACLOUD_SOURCE_DB_"
_TARGET_DB_TRIGGER_ENV_VARS = (
    f"{_TARGET_DB_PREFIX}HOST",
    f"{_TARGET_DB_PREFIX}DATABASE",
    f"{_TARGET_DB_PREFIX}USER",
    f"{_TARGET_DB_PREFIX}PASSWORD",
)
_SOURCE_DB_TRIGGER_ENV_VARS = (
    f"{_SOURCE_DB_PREFIX}HOST",
    f"{_SOURCE_DB_PREFIX}DATABASE",
    f"{_SOURCE_DB_PREFIX}USER",
    f"{_SOURCE_DB_PREFIX}PASSWORD",
)
_REQUIRED_TERM_NAME_COLUMNS = ("name_text", "name_embedding")
REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILES = (
    REPO_ROOT / ".vscode" / ".env",
    REPO_ROOT / ".env",
)


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """Database connection settings for one knowledge DB target."""

    db_type: str
    host: str
    port: int
    database: str
    user: str
    password: str
    schema: str

    def identity(self) -> tuple[str, str, int, str, str]:
        """Return a stable tuple used to compare DB targets."""

        return (self.db_type.lower(), self.host, self.port, self.database, self.schema)

    def as_log_text(self) -> str:
        """Return a concise connection target string without secrets."""

        return (
            f"db_type={self.db_type}, host={self.host}, port={self.port}, "
            f"database={self.database}, schema={self.schema}"
        )


@dataclass(slots=True)
class MigrationStats:
    """Aggregated migration stats for dry-run/apply output."""

    apply: bool
    force_overwrite: bool
    batch_size: int
    limit: int | None
    target_candidate_rows: int = 0
    target_candidate_texts: int = 0
    source_vector_rows: int = 0
    processed_texts: int = 0
    matched_texts: int = 0
    unmatched_texts: int = 0
    conflicting_texts: int = 0
    updated_rows: int = 0
    unmatched_samples: list[str] = field(default_factory=list)
    conflict_samples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Convert stats to a JSON-friendly dict."""

        return {
            "apply": self.apply,
            "force_overwrite": self.force_overwrite,
            "batch_size": self.batch_size,
            "limit": self.limit,
            "source_vector_rows": self.source_vector_rows,
            "target_candidate_rows": self.target_candidate_rows,
            "target_candidate_texts": self.target_candidate_texts,
            "processed_texts": self.processed_texts,
            "matched_texts": self.matched_texts,
            "unmatched_texts": self.unmatched_texts,
            "conflicting_texts": self.conflicting_texts,
            "updated_rows": self.updated_rows,
            "unmatched_samples": self.unmatched_samples,
            "conflict_samples": self.conflict_samples,
        }


def load_env() -> None:
    """Load repo-level .env only when DB envs were not provided explicitly."""

    has_target_env = any(os.getenv(name, "").strip() for name in _TARGET_DB_TRIGGER_ENV_VARS)
    has_source_env = any(os.getenv(name, "").strip() for name in _SOURCE_DB_TRIGGER_ENV_VARS)
    if has_target_env and has_source_env:
        return

    for env_file in _ENV_FILES:
        if not env_file.exists():
            continue
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            env_key = key.strip()
            env_value = value.strip().strip("'\"")
            if env_key and env_key not in os.environ:
                os.environ[env_key] = env_value
        break


def parse_database_config(
    prefix: str, *, default_schema: str = "whale_datacloud"
) -> DatabaseConfig:
    """Parse one prefixed DB config from environment variables."""

    normalized_prefix = prefix if prefix.endswith("_") else f"{prefix}_"

    def _read(name: str, default: str = "") -> str:
        return os.getenv(f"{normalized_prefix}{name}", default).strip()

    raw_port = _read("PORT", "5432")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError(f"无效端口: {normalized_prefix}PORT={raw_port!r}") from exc

    schema = _read("SCHEMA", default_schema)
    if not schema:
        raise ValueError(f"缺少 schema 配置: {normalized_prefix}SCHEMA")

    config = DatabaseConfig(
        db_type=_read("TYPE", "postgresql") or "postgresql",
        host=_read("HOST", "localhost") or "localhost",
        port=port,
        database=_read("DATABASE", "postgres") or "postgres",
        user=_read("USER", "postgres") or "postgres",
        password=os.getenv(f"{normalized_prefix}PASSWORD", ""),
        schema=schema,
    )

    missing_required = [
        suffix
        for suffix in ("HOST", "DATABASE", "USER", "PASSWORD")
        if not os.getenv(f"{normalized_prefix}{suffix}", "").strip()
    ]
    if missing_required:
        missing_names = ", ".join(f"{normalized_prefix}{suffix}" for suffix in missing_required)
        raise ValueError(f"缺少数据库环境变量: {missing_names}")

    return config


def build_connection_uri(config: DatabaseConfig) -> str:
    """Build a libpq-compatible connection URI."""

    safe_user = quote(config.user, safe="")
    safe_password = quote(config.password, safe="")
    auth = safe_user if not config.password else f"{safe_user}:{safe_password}"
    query = urlencode((("options", f"-csearch_path={config.schema}"),), doseq=True)
    return urlunparse(
        (
            "postgresql",
            f"{auth}@{config.host}:{config.port}",
            f"/{quote(config.database, safe='')}",
            "",
            query,
            "",
        )
    )


def ensure_distinct_databases(source: DatabaseConfig, target: DatabaseConfig) -> None:
    """Refuse to run when source and target point to the same schema target."""

    if source.identity() == target.identity():
        raise ValueError("源库与目标库完全相同，已拒绝执行迁移")


def connect_database(config: DatabaseConfig) -> Connection[Any]:
    """Open a psycopg connection for one DB target."""

    import psycopg

    return psycopg.connect(build_connection_uri(config))


def validate_term_name_columns(conn: Connection[Any], schema_name: str) -> None:
    """Verify required term_name columns exist in the selected schema."""

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'term_name'
            """,
            (schema_name,),
        )
        existing = {str(row[0]) for row in cur.fetchall()}

    missing = [column for column in _REQUIRED_TERM_NAME_COLUMNS if column not in existing]
    if missing:
        missing_text = ", ".join(missing)
        raise ValueError(f"{schema_name}.term_name 缺少必需列: {missing_text}")


def count_source_vector_rows(conn: Connection[Any], schema_name: str) -> int:
    """Count source term_name rows with reusable embeddings."""

    query = sql.SQL("SELECT COUNT(*) FROM {}.term_name WHERE name_embedding IS NOT NULL").format(
        sql.Identifier(schema_name)
    )
    with conn.cursor() as cur:
        cur.execute(query)
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("源库向量计数未返回结果")
    return int(row[0])


def count_target_candidate_rows(
    conn: Connection[Any],
    schema_name: str,
    *,
    force_overwrite: bool,
) -> int:
    """Count target rows eligible for migration."""

    predicate = sql.SQL("name_text IS NOT NULL")
    if not force_overwrite:
        predicate = sql.SQL("name_text IS NOT NULL AND name_embedding IS NULL")
    query = sql.SQL("SELECT COUNT(*) FROM {}.term_name WHERE {}").format(
        sql.Identifier(schema_name),
        predicate,
    )
    with conn.cursor() as cur:
        cur.execute(query)
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("目标库候选行计数未返回结果")
    return int(row[0])


def count_target_candidate_texts(
    conn: Connection[Any],
    schema_name: str,
    *,
    force_overwrite: bool,
) -> int:
    """Count distinct target texts eligible for migration."""

    predicate = sql.SQL("name_text IS NOT NULL")
    if not force_overwrite:
        predicate = sql.SQL("name_text IS NOT NULL AND name_embedding IS NULL")
    query = sql.SQL("SELECT COUNT(DISTINCT name_text) FROM {}.term_name WHERE {}").format(
        sql.Identifier(schema_name),
        predicate,
    )
    with conn.cursor() as cur:
        cur.execute(query)
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("目标库候选文本计数未返回结果")
    return int(row[0])


def fetch_target_candidate_texts(
    conn: Connection[Any],
    schema_name: str,
    *,
    batch_size: int,
    after_name_text: str | None,
    force_overwrite: bool,
    remaining_limit: int | None,
) -> list[str]:
    """Fetch one ordered batch of distinct target texts."""

    effective_batch_size = (
        batch_size if remaining_limit is None else min(batch_size, remaining_limit)
    )
    predicate = "name_text IS NOT NULL"
    if not force_overwrite:
        predicate += " AND name_embedding IS NULL"
    params: list[Any] = []
    if after_name_text is not None:
        predicate += " AND name_text > %s"
        params.append(after_name_text)
    params.append(effective_batch_size)

    query = sql.SQL(
        f"""
        SELECT DISTINCT name_text
        FROM {{}}.term_name
        WHERE {predicate}
        ORDER BY name_text
        LIMIT %s
        """
    ).format(sql.Identifier(schema_name))

    with conn.cursor() as cur:
        cur.execute(query, params)
        return [str(row[0]) for row in cur.fetchall()]


def split_source_embedding_rows(
    rows: list[tuple[str, str]],
) -> tuple[dict[str, str], set[str]]:
    """Build a text→embedding map and detect conflicting source vectors."""

    embeddings_by_text: dict[str, str] = {}
    conflicts: set[str] = set()
    for name_text, embedding_text in rows:
        existing = embeddings_by_text.get(name_text)
        if existing is None:
            embeddings_by_text[name_text] = embedding_text
            continue
        if existing != embedding_text:
            conflicts.add(name_text)

    for conflict_text in conflicts:
        embeddings_by_text.pop(conflict_text, None)
    return embeddings_by_text, conflicts


def fetch_source_embedding_map(
    conn: Connection[Any],
    schema_name: str,
    texts: list[str],
) -> tuple[dict[str, str], set[str]]:
    """Fetch exact source embeddings for a target-text batch."""

    if not texts:
        return {}, set()

    query = sql.SQL(
        """
        SELECT name_text, name_embedding::text AS embedding_text
        FROM {}.term_name
        WHERE name_embedding IS NOT NULL
          AND name_text = ANY(%s)
        """
    ).format(sql.Identifier(schema_name))

    with conn.cursor() as cur:
        cur.execute(query, (texts,))
        rows = [(str(row[0]), str(row[1])) for row in cur.fetchall()]
    return split_source_embedding_rows(rows)


def count_target_rows_for_texts(
    conn: Connection[Any],
    schema_name: str,
    texts: list[str],
    *,
    force_overwrite: bool,
) -> int:
    """Count target rows that would be updated for a matched text batch."""

    if not texts:
        return 0

    predicate = "name_text = ANY(%s)"
    if not force_overwrite:
        predicate += " AND name_embedding IS NULL"
    query = sql.SQL(f"SELECT COUNT(*) FROM {{}}.term_name WHERE {predicate}").format(
        sql.Identifier(schema_name)
    )

    with conn.cursor() as cur:
        cur.execute(query, (texts,))
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("目标库更新候选计数未返回结果")
    return int(row[0])


def apply_embedding_batch(
    conn: Connection[Any],
    schema_name: str,
    embeddings_by_text: dict[str, str],
    *,
    force_overwrite: bool,
) -> int:
    """Apply one matched embedding batch to the target DB."""

    if not embeddings_by_text:
        return 0

    with conn.cursor() as cur:
        cur.execute(
            "CREATE TEMP TABLE _tmp_term_name_embedding_migration ("
            "name_text VARCHAR(255), embedding_text TEXT"
            ") ON COMMIT PRESERVE ROWS"
        )
        cur.executemany(
            "INSERT INTO _tmp_term_name_embedding_migration (name_text, embedding_text) VALUES (%s, %s)",
            list(embeddings_by_text.items()),
        )
        overwrite_guard = (
            sql.SQL("") if force_overwrite else sql.SQL(" AND tgt.name_embedding IS NULL")
        )
        update_query = sql.SQL(
            """
            UPDATE {}.term_name AS tgt
            SET name_embedding = src.embedding_text::vector,
                updated_time = CURRENT_TIMESTAMP
            FROM _tmp_term_name_embedding_migration AS src
            WHERE tgt.name_text = src.name_text
            {}
            """
        ).format(sql.Identifier(schema_name), overwrite_guard)
        cur.execute(update_query)
        updated_rows = cur.rowcount
        cur.execute("DROP TABLE _tmp_term_name_embedding_migration")
    return updated_rows


def append_samples(target: list[str], values: set[str], *, max_samples: int = 20) -> None:
    """Append sorted samples until reaching the cap."""

    remaining = max_samples - len(target)
    if remaining <= 0:
        return
    target.extend(sorted(values)[:remaining])


def ensure_source_vectors_available(source_vector_rows: int) -> None:
    """Require the source DB to contain reusable embeddings."""

    if source_vector_rows <= 0:
        raise ValueError("源库 term_name.name_embedding 没有可复用数据")


def raise_source_conflict(conflicts: set[str]) -> None:
    """Abort when one source text maps to multiple vector payloads."""

    raise ValueError(
        f"源库存在相同 name_text 对应多个不同向量，已拒绝迁移: {', '.join(sorted(conflicts)[:5])}"
    )


def run_migration(
    *,
    source: DatabaseConfig,
    target: DatabaseConfig,
    batch_size: int,
    limit: int | None,
    apply: bool,
    force_overwrite: bool,
) -> MigrationStats:
    """Run the embedding reuse migration."""

    if batch_size <= 0:
        raise ValueError("batch_size 必须大于 0")
    if limit is not None and limit <= 0:
        raise ValueError("limit 必须大于 0")

    ensure_distinct_databases(source, target)
    stats = MigrationStats(
        apply=apply,
        force_overwrite=force_overwrite,
        batch_size=batch_size,
        limit=limit,
    )

    LOGGER.info("源库: %s", source.as_log_text())
    LOGGER.info("目标库: %s", target.as_log_text())

    source_conn = connect_database(source)
    target_conn = connect_database(target)
    try:
        source_conn.autocommit = True
        target_conn.autocommit = False

        validate_term_name_columns(source_conn, source.schema)
        validate_term_name_columns(target_conn, target.schema)

        stats.source_vector_rows = count_source_vector_rows(source_conn, source.schema)
        ensure_source_vectors_available(stats.source_vector_rows)

        stats.target_candidate_rows = count_target_candidate_rows(
            target_conn,
            target.schema,
            force_overwrite=force_overwrite,
        )
        stats.target_candidate_texts = count_target_candidate_texts(
            target_conn,
            target.schema,
            force_overwrite=force_overwrite,
        )
        if stats.target_candidate_rows <= 0 or stats.target_candidate_texts <= 0:
            LOGGER.info("目标库没有可迁移候选，直接结束")
            target_conn.rollback()
            return stats

        last_name_text: str | None = None
        while True:
            remaining_limit = None if limit is None else limit - stats.processed_texts
            if remaining_limit is not None and remaining_limit <= 0:
                break

            texts = fetch_target_candidate_texts(
                target_conn,
                target.schema,
                batch_size=batch_size,
                after_name_text=last_name_text,
                force_overwrite=force_overwrite,
                remaining_limit=remaining_limit,
            )
            if not texts:
                break

            last_name_text = texts[-1]
            stats.processed_texts += len(texts)
            embeddings_by_text, conflicts = fetch_source_embedding_map(
                source_conn, source.schema, texts
            )
            matched_texts = list(embeddings_by_text)
            unmatched = set(texts) - set(matched_texts) - conflicts
            stats.matched_texts += len(matched_texts)
            stats.unmatched_texts += len(unmatched)
            stats.conflicting_texts += len(conflicts)
            append_samples(stats.unmatched_samples, unmatched)
            append_samples(stats.conflict_samples, conflicts)

            if conflicts:
                raise_source_conflict(conflicts)

            updatable_rows = count_target_rows_for_texts(
                target_conn,
                target.schema,
                matched_texts,
                force_overwrite=force_overwrite,
            )
            if apply:
                updated_rows = apply_embedding_batch(
                    target_conn,
                    target.schema,
                    embeddings_by_text,
                    force_overwrite=force_overwrite,
                )
                stats.updated_rows += updated_rows
            else:
                stats.updated_rows += updatable_rows

            LOGGER.info(
                "批次完成: processed_texts=%s matched_texts=%s unmatched=%s updated_rows=%s",
                stats.processed_texts,
                len(matched_texts),
                len(unmatched),
                stats.updated_rows,
            )

        if apply:
            target_conn.commit()
        else:
            target_conn.rollback()
        return stats
    except Exception:
        target_conn.rollback()
        raise
    finally:
        source_conn.close()
        target_conn.close()


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for the migration tool."""

    parser = argparse.ArgumentParser(description="复用旧术语库的 term_name.name_embedding 到新库")
    parser.add_argument("--apply", action="store_true", help="执行写入；默认仅 dry-run")
    parser.add_argument(
        "--batch-size", type=int, default=1000, help="每批处理的 distinct name_text 数"
    )
    parser.add_argument("--limit", type=int, default=None, help="最多处理多少个 distinct name_text")
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="覆盖目标库已有向量；默认仅填充 name_embedding IS NULL",
    )
    parser.add_argument("--source-schema", default=None, help="覆盖 DATACLOUD_SOURCE_DB_SCHEMA")
    parser.add_argument("--target-schema", default=None, help="覆盖 DATACLOUD_DB_SCHEMA")
    return parser


def configure_logging() -> None:
    """Configure production-style INFO logging for script use."""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for embedding migration."""

    configure_logging()
    load_env()

    parser = build_arg_parser()
    args = parser.parse_args(argv)

    source = parse_database_config(_SOURCE_DB_PREFIX.rstrip("_"))
    target = parse_database_config(_TARGET_DB_PREFIX.rstrip("_"))

    if args.source_schema:
        source = replace(source, schema=str(args.source_schema).strip())
    if args.target_schema:
        target = replace(target, schema=str(args.target_schema).strip())

    stats = run_migration(
        source=source,
        target=target,
        batch_size=args.batch_size,
        limit=args.limit,
        apply=args.apply,
        force_overwrite=args.force_overwrite,
    )
    LOGGER.info("迁移完成: %s", stats.as_dict())
    return 0


__all__ = [
    "DatabaseConfig",
    "MigrationStats",
    "append_samples",
    "build_arg_parser",
    "build_connection_uri",
    "configure_logging",
    "connect_database",
    "count_source_vector_rows",
    "count_target_candidate_rows",
    "count_target_candidate_texts",
    "count_target_rows_for_texts",
    "ensure_distinct_databases",
    "ensure_source_vectors_available",
    "fetch_source_embedding_map",
    "fetch_target_candidate_texts",
    "load_env",
    "main",
    "parse_database_config",
    "raise_source_conflict",
    "run_migration",
    "split_source_embedding_rows",
    "validate_term_name_columns",
]


if __name__ == "__main__":
    raise SystemExit(main())
