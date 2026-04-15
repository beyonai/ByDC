"""Type2: initialize CSV data into crm_demo tables."""

from __future__ import annotations

import csv
import traceback
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import pytest
from dotenv import dotenv_values
from psycopg2 import errors
from psycopg2.extras import execute_values
from psycopg2 import sql


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_po_organization_to_crm_demo(mock_env_root) -> None:
    _init_table_from_csv(mock_env_root, "po_organization")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_po_users_organization_to_crm_demo(mock_env_root) -> None:
    _init_table_from_csv(mock_env_root, "po_users_organization")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_po_users_to_crm_demo(mock_env_root) -> None:
    _init_table_from_csv(mock_env_root, "po_users")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_todo_items_to_crm_demo(mock_env_root) -> None:
    _init_table_from_csv(mock_env_root, "todo_items")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_todo_item_handlers_to_crm_demo(mock_env_root) -> None:
    _init_table_from_csv(mock_env_root, "todo_item_handlers")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_po_users_kpi_completion_to_crm_demo(mock_env_root) -> None:
    _init_table_from_csv(mock_env_root, "po_users_kpi_completion")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_po_users_kpi_summary_to_crm_demo(mock_env_root) -> None:
    _init_table_from_csv(mock_env_root, "po_users_kpi_summary")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_sales_bo_status_change_to_crm_demo(mock_env_root) -> None:
    _init_table_from_csv(mock_env_root, "sales_bo_status_change")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_sales_business_opportunity_to_crm_demo(mock_env_root) -> None:
    _init_table_from_csv(mock_env_root, "sales_business_opportunity")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_sales_customer_to_crm_demo(mock_env_root) -> None:
    _init_table_from_csv(mock_env_root, "sales_customer")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_sales_daily_report_to_crm_demo(mock_env_root) -> None:
    _init_table_from_csv(mock_env_root, "sales_daily_report")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_sales_emp_attendance_to_crm_demo(mock_env_root) -> None:
    _init_table_from_csv(mock_env_root, "sales_emp_attendance")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_sales_expense_report_to_crm_demo(mock_env_root) -> None:
    _init_table_from_csv(mock_env_root, "sales_expense_report")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_sales_meeting_note_to_crm_demo(mock_env_root) -> None:
    _init_table_from_csv(mock_env_root, "sales_meeting_note")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_sales_org_kpi_completion_to_crm_demo(mock_env_root) -> None:
    _init_table_from_csv(mock_env_root, "sales_org_kpi_completion")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_sales_org_kpi_summary_to_crm_demo(mock_env_root) -> None:
    _init_table_from_csv(mock_env_root, "sales_org_kpi_summary")


@pytest.mark.type2_data
@pytest.mark.integration
def test_init_sales_person_kpi_summary_to_crm_demo(mock_env_root) -> None:
    _init_table_from_csv(mock_env_root, "sales_person_kpi_summary")


def _init_table_from_csv(mock_env_root: Path, table: str) -> None:
    mock_env_root = Path(mock_env_root)
    csv_path = _find_csv_for_table(mock_env_root, table)
    assert csv_path is not None, f"csv not found for table {table} under resource/data"
    _load_csv_into_table(csv_path, "crm_demo", table)


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
    database_url = cfg.get("DATACLOUD_DB_URL")
    user = cfg.get("DATACLOUD_DB_USER")
    password = cfg.get("DATACLOUD_DB_PASSWORD")
    assert all([database_url, user, password]), f"missing DATACLOUD_DB_* in {env_path}"
    parsed = urlparse(str(database_url).removeprefix("jdbc:"))
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "user": str(user),
        "password": str(password),
        "database": parsed.path.lstrip("/") or "postgres",
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
    matches = sorted((mock_env_root / "resource" / "data").rglob(f"{table}.csv"))
    if not matches:
        return None
    return matches[0]
