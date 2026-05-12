"""为 term_name 表新增 name_keywords_jieba 列并填充存量数据。

一个脚本完成全部工作：
  1. 检测列是否存在，不存在则 ALTER TABLE 新增
  2. 创建 GIN 索引（IF NOT EXISTS，幂等）
  3. 批量填充存量行的 jieba 分词 tsvector

用法:
    python db/scripts/backfill_jieba_tsvector.py           # 仅填充 NULL 行
    python db/scripts/backfill_jieba_tsvector.py --force   # 全量重新填充

环境变量:
    DATACLOUD_DB_HOST/PORT/DATABASE/SCHEMA/USER/PASS/TYPE — 数据库连接
    DATACLOUD_KNOWLEDGE_BACKFILL_BATCH_SIZE — 每批处理行数，默认 1000

索引侧使用 jieba.lcut_for_search（搜索引擎模式，宽分词提高召回率）；
查询侧使用 jieba.lcut（精确分词提高精确率）。

幂等：可反复执行。列已存在则跳过建列。
  - 默认模式：仅填充 name_keywords_jieba IS NULL 的行
  - --force 模式：全量重新填充（切换分词策略后使用）
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import jieba  # type: ignore[import-untyped]
import psycopg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BATCH_SIZE = int(os.getenv("DATACLOUD_KNOWLEDGE_BACKFILL_BATCH_SIZE", "1000"))
REPO_ROOT = Path(__file__).resolve().parents[4]
ENV_FILES = [
    REPO_ROOT / ".vscode" / ".env",
    REPO_ROOT / ".env",
]
KB_SRC = REPO_ROOT / "packages" / "datacloud-knowledge" / "src"

if str(KB_SRC) not in sys.path:
    sys.path.insert(0, str(KB_SRC))

_DB_CONFIG_TRIGGER_ENV_VARS = (
    "DATACLOUD_DB_HOST",
    "DATACLOUD_DB_DATABASE",
    "DATACLOUD_DB_USER",
    "DATACLOUD_DB_PASSWORD",
)


def load_env() -> None:
    """从 .env 文件加载环境变量（如果尚未提供显式数据库配置）。"""
    if any(os.getenv(name, "").strip() for name in _DB_CONFIG_TRIGGER_ENV_VARS):
        return

    for env_file in ENV_FILES:
        if not env_file.exists():
            continue
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value
        break


def _jieba_tokenize(text: str) -> str:
    """jieba 搜索引擎模式分词后用空格拼接，供 to_tsvector('simple', ...) 使用。

    使用 lcut_for_search：在精确模式基础上对长词再次切分，提高召回率。
    例: "中国科学院" → "中国 科学 学院 科学院 中国科学院"
    """
    tokens = [t for t in jieba.lcut_for_search(text) if t.strip()]
    return " ".join(tokens)


def _connect() -> psycopg.Connection:  # type: ignore[type-arg]
    from datacloud_knowledge.db.url import build_postgres_connection_uri

    return psycopg.connect(build_postgres_connection_uri(), autocommit=True)


def _column_exists(conn: psycopg.Connection) -> bool:  # type: ignore[type-arg]
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'whale_datacloud'
              AND table_name = 'term_name'
              AND column_name = 'name_keywords_jieba'
        """)
        return cur.fetchone() is not None


def _ensure_column(conn: psycopg.Connection) -> None:  # type: ignore[type-arg]
    """创建列 + GIN 索引（幂等）。"""
    if _column_exists(conn):
        log.info("列 name_keywords_jieba 已存在，跳过建列")
        return

    log.info("新增列 name_keywords_jieba ...")
    with conn.cursor() as cur:
        cur.execute("""
            ALTER TABLE whale_datacloud.term_name
            ADD COLUMN name_keywords_jieba tsvector
        """)
        cur.execute("""
            COMMENT ON COLUMN whale_datacloud.term_name.name_keywords_jieba
            IS 'BM25 全文搜索向量，基于 jieba 中文分词（词级粒度，由应用层填充）'
        """)
    log.info("列创建完成")

    log.info("创建 GIN 索引 ...")
    with conn.cursor() as cur:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_tn_name_keywords_jieba
            ON whale_datacloud.term_name USING GIN (name_keywords_jieba)
        """)
    log.info("索引创建完成")


def _backfill(conn: psycopg.Connection, *, force: bool = False) -> None:  # type: ignore[type-arg]
    """批量填充存量数据。force=True 时全量重新填充。"""
    mode = "全量重填" if force else "仅 NULL 行"
    log.info("开始填充（%s）...", mode)
    log.info("预热 jieba 词典 ...")
    jieba.lcut("预热")

    if force:
        log.info("--force: 先清空全部 name_keywords_jieba ...")
        with conn.cursor() as cur:
            cur.execute("UPDATE whale_datacloud.term_name SET name_keywords_jieba = NULL")
            log.info("  已清空 %d 行", cur.rowcount)

    total_updated = 0
    while True:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT name_id, name_text
                FROM whale_datacloud.term_name
                WHERE name_keywords_jieba IS NULL AND name_text IS NOT NULL
                LIMIT %s
                """,
                (BATCH_SIZE,),
            )
            rows = cur.fetchall()

        if not rows:
            break

        updates: list[tuple[str, str]] = []
        for name_id, name_text in rows:
            jieba_text = _jieba_tokenize(str(name_text))
            updates.append((jieba_text, str(name_id)))

        with conn.cursor() as cur:
            cur.executemany(
                """
                UPDATE whale_datacloud.term_name
                SET name_keywords_jieba = to_tsvector('simple', %s)
                WHERE name_id = %s
                """,
                updates,
            )

        total_updated += len(rows)
        log.info("已更新 %d 行 (累计 %d)", len(rows), total_updated)

    log.info("填充完成，共更新 %d 行", total_updated)


def main() -> None:
    parser = argparse.ArgumentParser(description="填充 name_keywords_jieba 列")
    parser.add_argument("--force", action="store_true", help="全量重新填充（忽略已有值）")
    args = parser.parse_args()

    load_env()
    if not any(os.getenv(name, "").strip() for name in _DB_CONFIG_TRIGGER_ENV_VARS):
        log.error(
            "缺少数据库环境变量，请设置 DATACLOUD_DB_HOST / DATACLOUD_DB_PORT / "
            "DATACLOUD_DB_DATABASE / DATACLOUD_DB_SCHEMA / DATACLOUD_DB_USER / "
            "DATACLOUD_DB_PASSWORD / DATACLOUD_DB_TYPE"
        )
        sys.exit(1)

    conn = _connect()
    try:
        _ensure_column(conn)
        _backfill(conn, force=args.force)
    finally:
        conn.close()

    log.info("全部完成")


if __name__ == "__main__":
    main()
