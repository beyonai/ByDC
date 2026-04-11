#!/usr/bin/env python
"""重新初始化 whale_datacloud schema 并导入知识包。

流程：
    1. 执行 DDL（DROP + CREATE 表，含新的 BM25/向量字段）
    2. 执行 Seed（内置术语类型）
    3. 导入知识包（OWL/JSONL）
    4. 生成向量嵌入（可选）

用法：
    python test_importer.py                     # 完整重建 + 导入默认包
    python test_importer.py --ddl-only          # 仅重建表结构
    python test_importer.py --truncate-only     # 仅清空数据
    python test_importer.py /path/to/package    # 导入指定包
    python test_importer.py --embed             # 完整重建 + 导入 + 向量化
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

logger = logging.getLogger(__name__)

# === 常量 ===

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILES = [
    REPO_ROOT / ".vscode" / ".env",
    REPO_ROOT / ".env",
]

DEFAULT_IMPORT_PACKAGE = (
    REPO_ROOT / "examples/e_commerce_demo/mock_env/resource/knowledge/import_package_owl_latest"
)

# 表清空顺序（按外键依赖）
TRUNCATE_ORDER = [
    "whale_datacloud.term_knowledge",
    "whale_datacloud.term_name",
    "whale_datacloud.term_relation",
    "whale_datacloud.term",
    "whale_datacloud.term_vocabulary",
    "whale_datacloud.term_type",
    "whale_datacloud.term_library",
    "whale_datacloud.domain",
]


# === 数据库连接 ===


def load_env() -> None:
    """从 .env 文件加载环境变量（如果 DB_HOST 未设置）。"""
    if os.getenv("DB_HOST"):
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


def get_db_connection() -> psycopg2.extensions.connection:
    """创建数据库连接。"""
    required = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise ValueError(f"缺少环境变量: {missing}")

    return psycopg2.connect(
        host=os.getenv("DB_HOST", ""),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", ""),
        password=os.getenv("DB_PASSWORD", ""),
        dbname=os.getenv("DB_NAME", ""),
    )


# === 操作函数 ===


def truncate_tables() -> None:
    """清空所有术语表（TRUNCATE CASCADE）。"""
    conn = get_db_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            for table in TRUNCATE_ORDER:
                logger.info("TRUNCATE %s", table)
                cur.execute(f"TRUNCATE TABLE {table} CASCADE")
        logger.info("表清空完成")
    except Exception:
        logger.exception("清空表失败")
        raise
    finally:
        conn.close()


def apply_ddl_and_seed() -> None:
    """执行 DDL + Seed（重建表结构并写入内置数据）。"""
    # 添加 db 目录到 sys.path 以导入 scripts
    db_dir = Path(__file__).resolve().parents[1] / "db"
    sys.path.insert(0, str(db_dir))

    from scripts.apply_whale_datacloud import apply_ddl, apply_seed

    logger.info("执行 DDL...")
    apply_ddl()
    logger.info("DDL 完成")

    logger.info("执行 Seed...")
    apply_seed()
    logger.info("Seed 完成")


def import_package(folder_path: str) -> dict:
    """导入知识包。"""
    from datacloud_knowledge.knowledge_build.importer.executor import run

    logger.info("导入知识包: %s", folder_path)
    result = run(folder_path)
    status = result.get("status", "unknown")
    logger.info("导入完成: %s", status)
    return result


def generate_embeddings(batch_size: int = 50) -> dict:
    """为 term_name 表生成向量嵌入。

    流程：
        1. 查询 name_embedding 为 NULL 的记录
        2. 批量调用 embedding 服务生成向量
        3. 写入 name_embedding 字段

    Args:
        batch_size: 批量处理大小

    Returns:
        统计信息 {"total": N, "updated": M}
    """
    try:
        from datacloud_knowledge.query.embedding import get_embedding_service
    except ImportError:
        logger.error("Embedding service not available. Install llama-index-embeddings-openai.")
        return {"total": 0, "updated": 0, "error": "ImportError"}

    embedding_service = get_embedding_service()
    conn = get_db_connection()
    conn.autocommit = False

    try:
        # 统计总数
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM whale_datacloud.term_name WHERE name_embedding IS NULL"
            )
            total_row = cur.fetchone()

        if total_row is None:
            raise RuntimeError("COUNT(*) query returned no rows")

        total = total_row[0]

        if total == 0:
            logger.info("所有术语名称已有向量，无需更新")
            return {"total": 0, "updated": 0}

        logger.info("开始向量化 %d 条术语名称...", total)

        updated = 0

        while True:
            # 获取一批数据
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT name_id, name_text
                    FROM whale_datacloud.term_name
                    WHERE name_embedding IS NULL
                    ORDER BY name_id
                    LIMIT %s
                    """,
                    (batch_size,),
                )
                rows = cur.fetchall()

            if not rows:
                break

            # 提取文本
            name_ids = [r[0] for r in rows]
            texts = [r[1] for r in rows]

            # 批量生成向量
            try:
                vectors = embedding_service.get_text_embedding_batch(texts)
            except Exception as e:
                logger.error("向量生成失败，跳过当前批次: %s", e)
                continue

            payloads = [
                (name_id, "[" + ",".join(map(str, vector)) + "]")
                for name_id, vector in zip(name_ids, vectors, strict=True)
            ]

            # 批量更新
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """
                    UPDATE whale_datacloud.term_name AS tn
                    SET name_embedding = src.embedding::vector
                    FROM (VALUES %s) AS src(name_id, embedding)
                    WHERE tn.name_id = src.name_id
                    """,
                    payloads,
                    template="(%s, %s)",
                    page_size=batch_size,
                )

            conn.commit()

            updated += len(rows)
            logger.info("已处理 %d/%d 条记录", updated, total)

        logger.info("向量化完成: %d 条记录已更新", updated)
        return {"total": total, "updated": updated}

    except Exception:
        conn.rollback()
        logger.exception("向量化失败")
        raise
    finally:
        conn.close()


def populate_tsvector() -> dict:
    """为 term_name 表填充 tsvector 字段（BM25 全文搜索）。

    使用单字分词方式更新 name_keywords 字段。

    Returns:
        统计信息 {"updated": N}
    """
    conn = get_db_connection()
    conn.autocommit = True

    try:
        with conn.cursor() as cur:
            # 更新 tsvector 字段（单字分词）
            cur.execute("""
                UPDATE whale_datacloud.term_name
                SET name_keywords = to_tsvector(
                    'simple',
                    array_to_string(string_to_array(COALESCE(name_text, ''), NULL), ' ')
                )
                WHERE name_text IS NOT NULL
            """)
            updated = cur.rowcount

        logger.info("已更新 %d 条记录的 tsvector 字段", updated)
        return {"updated": updated}

    except Exception:
        logger.exception("tsvector 更新失败")
        raise
    finally:
        conn.close()


# === CLI ===


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="重新初始化 whale_datacloud schema 并导入知识包",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "import_package",
        nargs="?",
        default=str(DEFAULT_IMPORT_PACKAGE),
        help="导入包路径",
    )
    parser.add_argument(
        "--ddl-only",
        action="store_true",
        help="仅执行 DDL + Seed，不导入知识包",
    )
    parser.add_argument(
        "--truncate-only",
        action="store_true",
        help="仅清空表数据（TRUNCATE），不重建表结构",
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        help="导入后生成向量嵌入（需要 embedding 服务）",
    )
    parser.add_argument(
        "--embed-batch-size",
        type=int,
        default=50,
        help="向量批量处理大小（默认 50）",
    )
    return parser.parse_args()


def main() -> None:
    """主流程。"""
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    args = parse_args()

    if args.ddl_only:
        apply_ddl_and_seed()
        return

    if args.truncate_only:
        truncate_tables()
        return

    if not args.embed:
        # 默认：完整重建 + 导入
        apply_ddl_and_seed()
        import_package(args.import_package)

        # 填充 tsvector（BM25）
        logger.info("填充 tsvector 字段...")
        populate_tsvector()

    # 可选：生成向量嵌入
    if args.embed:
        logger.info("生成向量嵌入...")
        generate_embeddings(batch_size=args.embed_batch_size)


if __name__ == "__main__":
    main()
