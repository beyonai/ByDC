"""TermSyncEvent、内存队列、后台 Worker 及 TermRecordSyncer。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from typing import Any

from datacloud_knowledge.sync.config import TermSyncConfig

logger = logging.getLogger(__name__)

_LIBRARY_CODE = "PERSONAL_LIB"
_DOMAIN_CODE = "PERSONAL_DOMAIN"
_QUEUE_MAX = 10_000

# 全局队列（进程内单例）
_TERM_SYNC_QUEUE: asyncio.Queue[TermSyncEvent] = asyncio.Queue(maxsize=_QUEUE_MAX)


@dataclass
class TermSyncEvent:
    """单次写入事件。

    Attributes:
        op: "insert" | "update" | "delete"
        object_code: 对象编码（用于推导 term_type_code）
        records: 涉及的记录列表；delete 时为删除前快照
        config: 同步配置
    """

    op: str
    object_code: str
    records: list[dict[str, Any]]
    config: TermSyncConfig
    schema: str | None = field(default=None)
    db_url: str | None = field(default=None)


async def enqueue_sync(event: TermSyncEvent) -> None:
    """非阻塞投递事件，队列满时丢弃并打 warning。"""
    try:
        _TERM_SYNC_QUEUE.put_nowait(event)
    except asyncio.QueueFull:
        logger.warning("术语同步队列已满，丢弃事件: object=%s op=%s", event.object_code, event.op)


async def term_sync_worker(
    schema: str | None = None,
    db_url: str | None = None,
) -> None:
    """后台常驻 asyncio Task，消费同步队列，每批最多 100 条。

    在服务启动时注册为后台 Task：
        asyncio.create_task(term_sync_worker(schema=..., db_url=...))
    """
    while True:
        event = await _TERM_SYNC_QUEUE.get()
        # 事件自带 schema/db_url 优先，否则用 worker 启动时的全局配置
        ev_schema = event.schema or schema
        ev_db_url = event.db_url or db_url

        batch = [event]
        while not _TERM_SYNC_QUEUE.empty() and len(batch) < 100:
            try:
                batch.append(_TERM_SYNC_QUEUE.get_nowait())
            except asyncio.QueueEmpty:
                break

        for ev in batch:
            try:
                _apply_sync_event(ev, schema=ev_schema, db_url=ev_db_url)
            except Exception:
                logger.warning(
                    "术语同步失败: object=%s op=%s",
                    ev.object_code,
                    ev.op,
                    exc_info=True,
                )
            finally:
                _TERM_SYNC_QUEUE.task_done()


# ── TermRecordSyncer ──────────────────────────────────────────────────────────


def _apply_sync_event(
    event: TermSyncEvent,
    *,
    schema: str | None,
    db_url: str | None,
) -> None:
    """将单个同步事件应用到术语库（同步调用，在 worker 协程内串行执行）。

    写入复用 BulkImportAdapter.batch_process_term，自动处理：
    - term / term_name upsert（含 jieba 分词同步）
    - term_name 增量删除/插入（跳过 DELETE 优化）
    - term_vocabulary 同步
    写入后调用 backfill_tsvector 和 _backfill_embeddings_optional 补全索引。
    """
    cfg = event.config
    if not cfg.enabled:
        return
    if not event.records:
        return

    from datacloud_knowledge.adapters import backfill_tsvector, create_bulk_importer
    from datacloud_knowledge.ingestion.ontology_terms import _backfill_embeddings_optional

    term_type_code = cfg.term_type_code(event.object_code)
    upserted_term_ids: list[str] = []
    term_dicts: list[dict[str, Any]] = []

    for record in event.records:
        term_code = str(record.get(cfg.term_code_field, "")).strip()
        term_name = str(record.get(cfg.term_name_field, "")).strip()
        term_desc = str(record.get(cfg.term_desc_field, "")).strip() if cfg.term_desc_field else ""
        if not term_code or not term_name:
            continue

        # term_id 格式与 build_terms 一致：{library_code}#{term_type_code}#{term_code}
        term_id = f"{_LIBRARY_CODE}#{term_type_code}#{term_code}"

        if event.op == "delete":
            term_dicts.append(
                {
                    "op": "delete",
                    "term_id": term_id,
                    "term_code": term_code,
                    "term_name": term_name,
                    "term_type_code": term_type_code,
                    "library_code": _LIBRARY_CODE,
                    "domain_code": _DOMAIN_CODE,
                }
            )
        else:
            upserted_term_ids.append(term_id)
            term_dicts.append(
                {
                    "term_id": term_id,
                    "term_code": term_code,
                    "term_name": term_name,
                    "term_desc": term_desc,
                    "desc_summary": term_desc,
                    "term_type_code": term_type_code,
                    "library_code": _LIBRARY_CODE,
                    "domain_code": _DOMAIN_CODE,
                    "parent_term_id": None,
                    "aliases": [],
                    "owl_doc_file": None,
                    "ext_field": "{}",
                }
            )

    if not term_dicts:
        return

    try:
        adapter = create_bulk_importer(schema=schema, db_url=db_url)
    except Exception:
        logger.exception("创建 BulkImportAdapter 失败，跳过术语同步")
        return

    stats: dict[str, Any] = {"terms": {"inserted": 0, "updated": 0, "deleted": 0}}
    try:
        # 不调用 begin_import（会整体删除 scope），直接写入
        _ensure_term_type(adapter, term_type_code)
        adapter.batch_process_term(term_dicts, stats)
        adapter.commit()
        logger.debug(
            "术语同步完成: object=%s op=%s stats=%s",
            event.object_code,
            event.op,
            stats["terms"],
        )
    except Exception:
        logger.exception("术语同步写入失败: object=%s op=%s", event.object_code, event.op)
        with contextlib.suppress(Exception):
            adapter.rollback()
        return
    finally:
        with contextlib.suppress(Exception):
            adapter.close()

    # ── 回填分词和向量（仅 upsert，delete 无需回填）────────────────────────
    if upserted_term_ids:
        try:
            backfill_tsvector(schema=schema, db_url=db_url)
        except Exception:
            logger.warning(
                "name_keywords 回填失败，可手动运行: datacloud-knowledge backfill-tsvector"
            )

        _backfill_embeddings_optional(
            term_ids=upserted_term_ids,
            schema=schema,
            db_url=db_url,
            entity_code=event.object_code,
        )


def _ensure_term_type(adapter: Any, term_type_code: str) -> None:
    """若 term_type 不存在则自动创建（type_category=1，枚举型）。"""
    stats: dict[str, Any] = {"term_types": {"inserted": 0, "updated": 0, "deleted": 0}}
    term_type_dicts = [
        {
            "type_code": term_type_code,
            "type_name": term_type_code,
            "type_desc": "",
            "type_category": 1,
        }
    ]
    adapter.batch_process_term_type(term_type_dicts, stats)
