"""Type2: initialize CSV data into e_commerce_demo tables."""

from __future__ import annotations

import csv
import traceback
from pathlib import Path

import psycopg2
import pytest
from dotenv import dotenv_values
from psycopg2 import errors
from psycopg2.extras import execute_values
from psycopg2 import sql

SCHEMA = "e_commerce_demo"


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_dws_enterprise_wide(mock_env_root: Path) -> None:
    _init_table_from_csv(mock_env_root, "dws_enterprise_wide")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_dws_grid_wide(mock_env_root: Path) -> None:
    _init_table_from_csv(mock_env_root, "dws_grid_wide")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_dws_industry_wide(mock_env_root: Path) -> None:
    _init_table_from_csv(mock_env_root, "dws_industry_wide")


# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────

def _init_table_from_csv(mock_env_root: Path, table: str) -> None:
    mock_env_root = Path(mock_env_root)
    csv_path = _find_csv_for_table(mock_env_root, table)
    assert csv_path is not None, (
        f"csv not found for table '{table}' under resource/data. "
        "Expected a file matching <table>*.csv"
    )
    _load_csv_into_table(csv_path, SCHEMA, table)


def _load_csv_into_table(csv_path: Path, schema: str, table: str) -> None:
    assert csv_path.exists(), f"csv not found: {csv_path}"
    db_cfg = _read_db_config_from_env_example(csv_path.parents[2] / ".env.example")
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
            try:
                cur.execute(
                    sql.SQL("TRUNCATE TABLE {}.{} CASCADE").format(
                        sql.Identifier(schema), sql.Identifier(table)
                    )
                )
            except errors.UndefinedTable as exc:
                raise AssertionError(
                    f"target table {schema}.{table} does not exist. "
                    "Run type1_db_schema DDL initialization before type2 data load."
                ) from exc

            columns = _read_csv_header(csv_path)
            rows = _read_normalized_csv_rows(csv_path, len(columns))
            insert_sql = sql.SQL("INSERT INTO {}.{} ({}) VALUES %s").format(
                sql.Identifier(schema),
                sql.Identifier(table),
                sql.SQL(", ").join(sql.Identifier(col) for col in columns),
            )
            try:
                if rows:
                    execute_values(cur, insert_sql.as_string(conn), rows, page_size=500)

                cur.execute(
                    sql.SQL("SELECT count(*) FROM {}.{}").format(
                        sql.Identifier(schema), sql.Identifier(table)
                    )
                )
                db_count = int(cur.fetchone()[0])
            except Exception as exa:
                print("\n[load_csv_into_table] exception while loading csv into db")
                print(f"  csv_path={csv_path}")
                print(f"  target={schema}.{table}")
                print(f"  columns({len(columns)})={columns}")
                print(f"  row_count(csv)={row_count}, rows_to_insert={len(rows)}")
                try:
                    sql_text = insert_sql.as_string(conn)
                except Exception as exc:
                    sql_text = f"<failed to render insert_sql: {exc!r}>"
                print(f"  insert_sql={sql_text}")
                if rows:
                    print(f"  first_row={rows[0]}")
                    print(f"  last_row={rows[-1]}")
                traceback.print_exc()
                raise
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


def _find_csv_for_table(mock_env_root: Path, table: str) -> Path | None:
    """Find CSV whose stem starts with <table> under resource/data (handles date suffixes)."""
    data_dir = mock_env_root / "resource" / "data"
    matches = sorted(data_dir.rglob(f"{table}*.csv"))
    if not matches:
        return None
    return matches[0]
