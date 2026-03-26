import threading
import time
import os

_SNOWFLAKE_EPOCH_MS = 1288834974657
_snowflake_lock = threading.Lock()
_snowflake_last_ts = 0
_snowflake_sequence = 0


def _snowflake_datacenter_worker_ids() -> tuple[int, int]:
    d_raw = os.getenv("DATACLOUD_KNOWLEDGE_SNOWFLAKE_DATACENTER_ID", "1").strip() or "1"
    w_raw = os.getenv("DATACLOUD_KNOWLEDGE_SNOWFLAKE_WORKER_ID", "1").strip() or "1"
    try:
        d = int(d_raw)
    except ValueError:
        d = 1
    try:
        w = int(w_raw)
    except ValueError:
        w = 1
    return d & 0x1F, w & 0x1F


def _next_snowflake_id() -> str:
    """雪花算法 64bit 整数，字符串形式写入 term.term_id、term_name.name_id 等（VARCHAR）。"""
    global _snowflake_last_ts, _snowflake_sequence
    datacenter_id, worker_id = _snowflake_datacenter_worker_ids()
    with _snowflake_lock:
        ts = int(time.time() * 1000)
        if ts < _snowflake_last_ts:
            raise ValueError("系统时钟回拨，无法生成雪花ID")
        if ts == _snowflake_last_ts:
            _snowflake_sequence = (_snowflake_sequence + 1) & 0xFFF
            if _snowflake_sequence == 0:
                while ts <= _snowflake_last_ts:
                    ts = int(time.time() * 1000)
        else:
            _snowflake_sequence = 0
        _snowflake_last_ts = ts
        nid = (
            ((ts - _SNOWFLAKE_EPOCH_MS) << 22)
            | (datacenter_id << 17)
            | (worker_id << 12)
            | _snowflake_sequence
        )
        return str(nid)


def _next_snowflake_ids(count: int) -> list[str]:
    """批量生成雪花 ID，减少锁竞争。"""
    if count <= 0:
        return []
    global _snowflake_last_ts, _snowflake_sequence
    datacenter_id, worker_id = _snowflake_datacenter_worker_ids()
    ids: list[str] = []
    with _snowflake_lock:
        for _ in range(count):
            ts = int(time.time() * 1000)
            if ts < _snowflake_last_ts:
                raise ValueError("系统时钟回拨，无法生成雪花ID")
            if ts == _snowflake_last_ts:
                _snowflake_sequence = (_snowflake_sequence + 1) & 0xFFF
                if _snowflake_sequence == 0:
                    while ts <= _snowflake_last_ts:
                        ts = int(time.time() * 1000)
            else:
                _snowflake_sequence = 0
            _snowflake_last_ts = ts
            nid = (
                ((ts - _SNOWFLAKE_EPOCH_MS) << 22)
                | (datacenter_id << 17)
                | (worker_id << 12)
                | _snowflake_sequence
            )
            ids.append(str(nid))
    return ids