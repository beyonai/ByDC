"""TermSyncEvent、内存队列、后台 Worker 及 TermSyncHandler 协议。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from datacloud_knowledge.sync.config import TermSyncConfig

logger = logging.getLogger(__name__)

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
    base_id: str
    object_code: str
    records: list[dict[str, Any]]
    config: TermSyncConfig
    schema: str | None = field(default=None)
    db_url: str | None = field(default=None)


@runtime_checkable
class TermSyncHandler(Protocol):
    """术语同步写入接口，由调用方（如 datacloud-platform）提供实现。

    将同步逻辑与 datacloud-knowledge 内部实现解耦：
    knowledge 包负责队列/事件定义，写入逻辑由上层通过 TermBackend 实现并注入。
    """

    def ensure_term_type(self, *, base_id: str, type_code: str, type_name: str) -> None:
        """确保术语类型存在（幂等）。"""
        ...

    def upsert_terms(self, *, base_id: str, terms: list[dict[str, Any]]) -> list[str]:
        """批量 upsert 术语，返回数据库 term_id（UUID）列表。

        ``terms`` 为 dict 列表，每条字段：
            term_code, term_name, term_desc,
            term_type_code, library_code, domain_code
        """
        ...

    def delete_terms(
        self,
        *,
        base_id: str,
        term_ids: list[str] | None = None,
        terms: list[dict[str, Any]] | None = None,
    ) -> None:
        """批量删除术语，支持两种入参，均有值时全部执行。

        Args:
            base_id: 库id
            term_ids: 数据库 UUID 列表，直接按主键删除。
            terms:    业务三元组 dict 列表（term_code, term_type_code, library_code），
                      先反查 UUID 再删除。与 upsert_terms 参数结构对称。
        """
        ...


async def enqueue_sync(event: TermSyncEvent) -> None:
    """非阻塞投递事件，队列满时丢弃并打 warning。"""
    try:
        _TERM_SYNC_QUEUE.put_nowait(event)
    except asyncio.QueueFull:
        logger.warning("术语同步队列已满，丢弃事件: object=%s op=%s", event.object_code, event.op)


async def term_sync_worker(
    handler: TermSyncHandler | None = None,
) -> None:
    """后台常驻 asyncio Task，消费同步队列，每批最多 100 条。

    在服务启动时注册为后台 Task，并注入 TermSyncHandler 实现：
        asyncio.create_task(term_sync_worker(handler=my_backend))

    Args:
        handler: 实现 TermSyncHandler 协议的写入后端（由 datacloud-platform 提供）。
                 为 None 时事件仍会被消费但不写入，并打 warning。
    """
    if handler is None:
        logger.warning(
            "term_sync_worker 启动时未注入 handler，术语同步将被静默丢弃。"
            "请在 start_heartbeat() 中传入 TermSyncHandler 实现。"
        )
    while True:
        event = await _TERM_SYNC_QUEUE.get()

        batch = [event]
        while not _TERM_SYNC_QUEUE.empty() and len(batch) < 100:
            try:
                batch.append(_TERM_SYNC_QUEUE.get_nowait())
            except asyncio.QueueEmpty:
                break

        for ev in batch:
            try:
                if handler is not None:
                    _apply_sync_event(ev, handler=handler)
                else:
                    logger.debug(
                        "term_sync_worker: handler 未注入，跳过事件 object=%s op=%s",
                        ev.object_code,
                        ev.op,
                    )
            except Exception:
                logger.warning(
                    "术语同步失败: object=%s op=%s",
                    ev.object_code,
                    ev.op,
                    exc_info=True,
                )
            finally:
                _TERM_SYNC_QUEUE.task_done()


# ── 事件处理 ──────────────────────────────────────────────────────────────────

# 动态表业务术语统一写入 default_term 库，与 create_term/import_terms 的 fallback 一致。
_LIBRARY_CODE = "default_term"
_DOMAIN_CODE = "PERSONAL_DOMAIN"


def _apply_sync_event(event: TermSyncEvent, *, handler: TermSyncHandler) -> None:
    """将单个同步事件通过 handler 写入术语库。

    由 term_sync_worker 在 asyncio Task 内串行调用。
    """
    cfg = event.config
    if not cfg.enabled:
        return
    if not event.records:
        return

    term_type_code = cfg.term_type_code(event.object_code)
    upsert_list: list[dict[str, Any]] = []
    delete_list: list[dict[str, Any]] = []

    for record in event.records:
        term_code = str(record.get(cfg.term_code_field, "")).strip()
        term_name = str(record.get(cfg.term_name_field, "")).strip()
        term_desc = str(record.get(cfg.term_desc_field, "")).strip() if cfg.term_desc_field else ""
        if not term_code or not term_name:
            continue

        if event.op == "delete":
            delete_list.append(
                {
                    "term_code": term_code,
                    "term_type_code": term_type_code,
                    "library_code": _LIBRARY_CODE,
                }
            )
        else:
            upsert_list.append(
                {
                    "term_code": term_code,
                    "term_name": term_name,
                    "term_desc": term_desc,
                    "term_type_code": term_type_code,
                    "library_code": _LIBRARY_CODE,
                    "domain_code": _DOMAIN_CODE,
                }
            )

    if not upsert_list and not delete_list:
        return

    if upsert_list:
        handler.ensure_term_type(
            base_id=event.base_id, type_code=term_type_code, type_name=term_type_code
        )
        upserted_ids = handler.upsert_terms(base_id=event.base_id, terms=upsert_list)
        logger.debug(
            "术语同步完成: object=%s op=%s upserted=%d",
            event.object_code,
            event.op,
            len(upserted_ids),
        )

    if delete_list:
        handler.delete_terms(base_id=event.base_id, terms=delete_list)
        logger.debug(
            "术语同步删除: object=%s count=%d",
            event.object_code,
            len(delete_list),
        )
