"""Type2: initialize CSV data into crm_demo tables."""

from __future__ import annotations

import csv
from pathlib import Path

import psycopg2
import pytest
from dotenv import dotenv_values
from psycopg2.extras import execute_values
from psycopg2 import sql


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_po_organization_to_crm_demo(mock_env_root) -> None:
    csv_path = Path(mock_env_root) / "resource" / "data" / "org" / "po_organization.csv"
    _load_csv_into_table(csv_path, "crm_demo", "po_organization")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_po_users_organization_to_crm_demo(mock_env_root) -> None:
    csv_path = (
        Path(mock_env_root) / "resource" / "data" / "org" / "po_users_organization.csv"
    )
    _load_csv_into_table(csv_path, "crm_demo", "po_users_organization")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_po_users_to_crm_demo(mock_env_root) -> None:
    csv_path = Path(mock_env_root) / "resource" / "data" / "org" / "po_users.csv"
    _load_csv_into_table(csv_path, "crm_demo", "po_users")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_todo_items_to_crm_demo(mock_env_root) -> None:
    csv_path = Path(mock_env_root) / "resource" / "data" / "todo" / "todo_items.csv"
    _load_csv_into_table(csv_path, "crm_demo", "todo_items")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_todo_item_handlers_to_crm_demo(mock_env_root) -> None:
    csv_path = Path(mock_env_root) / "resource" / "data" / "todo" / "todo_item_handlers.csv"
    _load_csv_into_table(csv_path, "crm_demo", "todo_item_handlers")


def _load_csv_into_table(csv_path: Path, schema: str, table: str) -> None:
    assert csv_path.exists(), f"csv not found: {csv_path}"
    db_cfg = _read_db_config_from_env_example(csv_path.parents[3] / ".env.example")
    row_count = _count_csv_rows(csv_path)

    conn = psycopg2.connect(
        host=db_cfg["host"],
        port=db_cfg["port"],
        user=db_cfg["user"],
        password=db_cfg["password"],
        dbname=db_cfg["database"],
    )
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema))
            )
            cur.execute(
                sql.SQL("TRUNCATE TABLE {}.{} CASCADE").format(
                    sql.Identifier(schema), sql.Identifier(table)
                )
            )
            columns = _read_csv_header(csv_path)
            rows = _read_normalized_csv_rows(csv_path, len(columns))
            insert_sql = sql.SQL("INSERT INTO {}.{} ({}) VALUES %s").format(
                sql.Identifier(schema),
                sql.Identifier(table),
                sql.SQL(", ").join(sql.Identifier(col) for col in columns),
            )
            if rows:
                execute_values(cur, insert_sql.as_string(conn), rows, page_size=500)

            cur.execute(
                sql.SQL("SELECT count(*) FROM {}.{}").format(
                    sql.Identifier(schema), sql.Identifier(table)
                )
            )
            db_count = int(cur.fetchone()[0])
            assert db_count == row_count, (
                f"row count mismatch for {schema}.{table}: csv={row_count}, db={db_count}"
            )
        conn.commit()
    finally:
        conn.close()


def _read_db_config_from_env_example(env_path: Path) -> dict[str, str | int]:
    cfg = dotenv_values(env_path)
    host = cfg.get("DB_HOST")
    port = cfg.get("DB_PORT")
    user = cfg.get("DB_USER")
    password = cfg.get("DB_PASSWORD")
    database = cfg.get("DB_NAME")
    assert all([host, port, user, password, database]), f"missing DB_* in {env_path}"
    return {
        "host": str(host),
        "port": int(str(port)),
        "user": str(user),
        "password": str(password),
        "database": str(database),
    }


def _count_csv_rows(csv_path: Path) -> int:
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        return sum(1 for _ in reader)


def _read_csv_header(csv_path: Path) -> list[str]:
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, [])
    assert header, f"csv header is empty: {csv_path}"
    return header


def _read_normalized_csv_rows(csv_path: Path, expected_columns: int) -> list[list[str | None]]:
    rows: list[list[str | None]] = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for raw_row in reader:
            if len(raw_row) < expected_columns:
                raw_row = raw_row + [""] * (expected_columns - len(raw_row))
            elif len(raw_row) > expected_columns:
                raw_row = raw_row[:expected_columns]
            rows.append([None if value == "" else value for value in raw_row])
    return rows
