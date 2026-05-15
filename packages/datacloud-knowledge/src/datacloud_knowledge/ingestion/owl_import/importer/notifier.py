"""回调通知：导入完成后（不论成功/失败）通知源系统。

支持 GET / POST 两种方式，POST 时发送 JSON body。
网络故障只记录日志，不影响主流程返回。
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10


def notify(
    url: str,
    method: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> bool:
    """向源系统发送回调通知。

    Args:
        url:     回调地址。
        method:  HTTP 方法，GET 或 POST。
        headers: 附加请求头（如 Authorization）。
        payload: 通知内容，POST 时作为 JSON body，GET 时忽略。

    Returns:
        True 表示收到 2xx 响应；False 表示请求失败（已记录日志）。
    """
    method = method.upper()
    all_headers = {"Content-Type": "application/json", **headers}

    try:
        if method == "GET":
            req = urllib.request.Request(url, headers=all_headers, method="GET")  # noqa: S310
        else:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers=all_headers, method="POST")  # noqa: S310

        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:  # noqa: S310
            status_code = int(resp.status)
            logger.info("callback notified: url=%s status=%d", url, status_code)
            return 200 <= status_code < 300

    except urllib.error.HTTPError as exc:
        logger.warning("callback HTTP error: url=%s status=%d", url, exc.code)
        return False
    except Exception as exc:
        logger.warning("callback failed: url=%s error=%s", url, exc)
        return False
