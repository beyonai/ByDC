"""知识包全流程执行器：预检 → 入库 → 回调通知。

流程：
  1. 调用 precheck.run() 做全量校验
  2. 预检失败 → 组装 precheck_failed 结果，触发回调后返回
  3. 预检通过 → 调用 executor.run() 单事务入库
  4. 入库完成（成功/失败）→ 触发回调通知（若配置了 callback）
  5. 返回 RunResult
"""

from __future__ import annotations

import logging
from typing import Any

from . import executor, notifier, precheck

logger = logging.getLogger(__name__)


def run(
    folder_path: str,
    callback_url: str | None = None,
    callback_method: str = "POST",
    callback_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """执行知识包导入全流程。

    Args:
        folder_path:      导入包根目录的本地绝对路径。
        callback_url:     回调通知地址，为 None 则不回调。
        callback_method:  回调 HTTP 方法（GET | POST），默认 POST。
        callback_headers: 回调附加请求头（如鉴权头）。

    Returns:
        dict，字段与 RunResult 对应：
          status / folder_path / precheck_errors / stats / error / callback_notified
    """
    cb_headers = callback_headers or {}

    # ── Step 1：预检 ─────────────────────────────────────────────────────────
    logger.info("runner: precheck start folder=%s", folder_path)
    pc = precheck.run(folder_path)

    if pc["status"] != "ok":
        logger.info("runner: precheck failed, %d errors", len(pc["errors"]))
        result: dict[str, Any] = {
            "status": "precheck_failed",
            "folder_path": folder_path,
            "precheck_errors": pc["errors"],
            "stats": {},
            "error": None,
            "callback_notified": False,
        }
        result["callback_notified"] = _maybe_notify(
            callback_url,
            callback_method,
            cb_headers,
            result,
        )
        return result

    # ── Step 2：入库 ─────────────────────────────────────────────────────────
    logger.info("runner: precheck ok, total_rows=%d, start import", pc["total_rows"])
    exec_result = executor.run(folder_path)

    if exec_result["status"] == "success":
        result = {
            "status": "success",
            "folder_path": folder_path,
            "precheck_errors": [],
            "stats": exec_result["stats"],
            "error": None,
            "callback_notified": False,
        }
    else:
        result = {
            "status": "import_failed",
            "folder_path": folder_path,
            "precheck_errors": [],
            "stats": exec_result.get("stats", {}),
            "error": exec_result.get("error"),
            "callback_notified": False,
        }

    # ── Step 3：回调通知 ──────────────────────────────────────────────────────
    result["callback_notified"] = _maybe_notify(
        callback_url,
        callback_method,
        cb_headers,
        result,
    )
    return result


def _maybe_notify(
    url: str | None,
    method: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> bool:
    """若配置了回调地址则发送通知，否则返回 False。"""
    if not url:
        return False
    return notifier.notify(url=url, method=method, headers=headers, payload=payload)
