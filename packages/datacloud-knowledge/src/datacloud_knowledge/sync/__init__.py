"""虚拟表数据变更同步术语库。

公共入口：
    TermSyncConfig   — 对象级同步配置（来自 definition.json term_sync 块）
    TermSyncEvent    — 单次写入事件
    enqueue_sync     — 非阻塞投递事件到内存队列
    term_sync_worker — 后台常驻 asyncio Task，消费队列写入术语库
"""

from datacloud_knowledge.sync.config import TermSyncConfig
from datacloud_knowledge.sync.queue import TermSyncEvent, enqueue_sync, term_sync_worker

__all__ = [
    "TermSyncConfig",
    "TermSyncEvent",
    "enqueue_sync",
    "term_sync_worker",
]
