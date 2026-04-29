"""Command line interface for datacloud-knowledge."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from datacloud_knowledge.db.schema import ensure_schema, verify_schema
from datacloud_knowledge.db.tsvector import backfill_tsvector_with_url


def _print_result(result: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE pairs into os.environ without overriding existing values."""

    if not path.exists():
        raise ValueError(f"Env file does not exist: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def _add_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--schema",
        default=None,
        help=(
            "Knowledge schema. Required unless present in --db-url query "
            "(currentSchema/schema/search_path) or DATACLOUD_DB_SCHEMA."
        ),
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help=(
            "Database URL, e.g. postgresql://user:pass@host:5432/db "
            "or jdbc:opengauss://host:5432/db?currentSchema=tenant."
        ),
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Load DATACLOUD_* and embedding variables from this .env file.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datacloud-knowledge",
        description="Initialize, import, and maintain DataCloud knowledge schemas.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable INFO logging")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ensure_parser = subparsers.add_parser("ensure-schema", help="Create/update knowledge tables")
    _add_connection_args(ensure_parser)
    ensure_parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate knowledge tables before applying DDL. Destructive; off by default.",
    )
    ensure_parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Do not insert built-in term types and system seed records after DDL.",
    )
    ensure_parser.add_argument(
        "--create-vector-extension",
        action="store_true",
        help="Try CREATE EXTENSION IF NOT EXISTS vector before DDL for PostgreSQL/pgvector.",
    )

    verify_parser = subparsers.add_parser("verify-schema", help="Verify core tables exist")
    _add_connection_args(verify_parser)

    import_parser = subparsers.add_parser("import-terms", help="Import OWL knowledge package")
    _add_connection_args(import_parser)
    import_parser.add_argument("package", type=Path, help="Knowledge import package directory")

    tsvector_parser = subparsers.add_parser("backfill-tsvector", help="Backfill term_name tsvector")
    _add_connection_args(tsvector_parser)
    tsvector_parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute all name_keywords values instead of only rows where the column is NULL.",
    )

    embedding_parser = subparsers.add_parser(
        "backfill-embeddings", help="Backfill term_name vector embeddings"
    )
    _add_connection_args(embedding_parser)
    embedding_parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of term names to embed per API batch. Default: 50.",
    )
    embedding_parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate embeddings for all term names instead of only NULL embeddings.",
    )
    embedding_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of term names to process in this run. Default: no limit.",
    )

    bootstrap_parser = subparsers.add_parser(
        "bootstrap", help="Ensure schema, import, and backfill"
    )
    _add_connection_args(bootstrap_parser)
    bootstrap_parser.add_argument("package", type=Path, help="Knowledge import package directory")
    bootstrap_parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate knowledge tables before importing. Destructive; off by default.",
    )
    bootstrap_parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Skip built-in seed records during schema initialization.",
    )
    bootstrap_parser.add_argument(
        "--with-embeddings",
        action="store_true",
        help="After import and tsvector backfill, also generate name_embedding vectors.",
    )
    bootstrap_parser.add_argument(
        "--embed-batch-size",
        type=int,
        default=50,
        help="Embedding API batch size used with --with-embeddings. Default: 50.",
    )
    bootstrap_parser.add_argument(
        "--create-vector-extension",
        action="store_true",
        help="Try CREATE EXTENSION IF NOT EXISTS vector before DDL for PostgreSQL/pgvector.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0911
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.env_file is not None:
        _load_env_file(args.env_file)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    try:
        if args.command == "ensure-schema":
            _print_result(
                ensure_schema(
                    schema=args.schema,
                    db_url=args.db_url,
                    reset=args.reset,
                    seed=not args.no_seed,
                    create_vector_extension=args.create_vector_extension,
                )
            )
            return 0
        if args.command == "verify-schema":
            _print_result(verify_schema(schema=args.schema, db_url=args.db_url))
            return 0
        if args.command == "import-terms":
            from datacloud_knowledge.knowledge_build.importer.executor import run as import_package

            result = import_package(str(args.package), schema=args.schema, db_url=args.db_url)
            _print_result(result)
            return 0 if result.get("status") != "failed" else 1
        if args.command == "backfill-tsvector":
            _print_result(
                backfill_tsvector_with_url(schema=args.schema, db_url=args.db_url, force=args.force)
            )
            return 0
        if args.command == "backfill-embeddings":
            from datacloud_knowledge.db.embeddings import backfill_name_embeddings

            _print_result(
                backfill_name_embeddings(
                    schema=args.schema,
                    db_url=args.db_url,
                    batch_size=args.batch_size,
                    force=args.force,
                    limit=args.limit,
                )
            )
            return 0
        if args.command == "bootstrap":
            from datacloud_knowledge.knowledge_build.importer.executor import run as import_package

            results: dict[str, Any] = {}
            results["ensure_schema"] = ensure_schema(
                schema=args.schema,
                db_url=args.db_url,
                reset=args.reset,
                seed=not args.no_seed,
                create_vector_extension=args.create_vector_extension,
            )
            import_result = import_package(
                str(args.package), schema=args.schema, db_url=args.db_url
            )
            results["import_terms"] = import_result
            if import_result.get("status") == "failed":
                _print_result(results)
                return 1
            results["backfill_tsvector"] = backfill_tsvector_with_url(
                schema=args.schema,
                db_url=args.db_url,
            )
            if args.with_embeddings:
                from datacloud_knowledge.db.embeddings import backfill_name_embeddings

                results["backfill_embeddings"] = backfill_name_embeddings(
                    schema=args.schema,
                    db_url=args.db_url,
                    batch_size=args.embed_batch_size,
                )
            _print_result(results)
            return 0
    except (RuntimeError, ValueError) as exc:
        parser.exit(2, f"datacloud-knowledge: error: {exc}\n")

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
