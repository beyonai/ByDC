"""HTTP 适配器模块。

提供 ``HttpTermAdapter`` 类，同时实现 TermReader 和 TermWriter 协议。
通过 ``DATACLOUD_HTTP_API_URL`` 和 ``DATACLOUD_HTTP_PID`` 环境变量配置。
"""

from __future__ import annotations

from datacloud_knowledge.adapters.http.adapter import HttpTermAdapter

__all__ = [
    "HttpTermAdapter",
]
