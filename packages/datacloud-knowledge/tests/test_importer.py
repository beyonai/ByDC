#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""清空 whale_datacloud schema 下的术语相关表。

按依赖顺序清空以下表：
- term_knowledge（依赖 term）
- term_name（依赖 term）
- term_relation（依赖 term）
- term（依赖 term_type、domain、term_library）
- term_type
- term_library
- term_vocabulary
- domain

使用 TRUNCATE CASCADE 确保外键约束不阻塞。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import psycopg2

logger = logging.getLogger(__name__)

# 从 .env.test 或环境变量加载数据库配置
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILES = [
    _REPO_ROOT / ".vscode" / ".env.test",
    _REPO_ROOT / ".env.test",
]


def _load_env_if_needed() -> None:
    """若 DB_HOST 未设置，尝试从 .env.test 加载。"""
    if os.getenv("DB_HOST"):
        return
    for candidate in _ENV_FILES:
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
        break


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"missing required env var: {name}")
    return value


def _connect() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=_required_env("DB_HOST"),
        port=int(_required_env("DB_PORT")),
        user=_required_env("DB_USER"),
        password=_required_env("DB_PASSWORD"),
        dbname=_required_env("DB_NAME"),
    )


# 按外键依赖顺序排列，先清空的表不能被后清空的表引用
_TABLES_IN_ORDER = [
    "whale_datacloud.term_knowledge",
    "whale_datacloud.term_name",
    "whale_datacloud.term_relation",
    "whale_datacloud.term",
    "whale_datacloud.term_vocabulary",
    "whale_datacloud.term_type",
    "whale_datacloud.term_library",
    "whale_datacloud.domain",
]


def clear_term_tables() -> None:
    """清空所有术语相关表。"""
    conn = _connect()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            for table in _TABLES_IN_ORDER:
                logger.info(f"清空表: {table}")
                cur.execute(f"TRUNCATE TABLE {table} CASCADE")
        logger.info("术语表清空完成")
    except Exception as e:
        logger.error(f"清空表失败: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    from datacloud_knowledge.knowledge_build.importer.executor import run

    _load_env_if_needed()
    clear_term_tables()


    result = run('/home/luoyanzhuo/project/whale_datacloud/packages/datacloud-knowledge/docs/模块设计/导入包样例')
    print(result)