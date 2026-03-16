"""curl 命令打印工具，用于本地调试 HTTP 请求。"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def log_curl(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: Any = None,
) -> None:
    """将 HTTP 请求格式化为 curl 命令并打印，便于本地调试。

    Args:
        method: HTTP 方法，如 POST、GET
        url: 请求 URL
        headers: 请求头，可为 None
        body: 请求体，dict 会序列化为 JSON
    """
    parts = [f"curl -X {method.upper()} '{url}'"]
    hdrs = headers or {}
    for k, v in hdrs.items():
        parts.append(f'-H "{k}: {v}"')
    if body is not None:
        if isinstance(body, dict):
            body_str = json.dumps(body, ensure_ascii=False)
        else:
            body_str = str(body)
        parts.append(f"-d '{body_str}'")
    cmd = " ".join(parts)
    logger.info("[curl] %s", cmd)
