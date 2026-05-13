"""后端适配器层 — 不同数据源的读写实现。

adapters/opengauss/  — OpenGauss 实现（默认）
adapters/mysql/       — MySQL 实现（规划中）
adapters/http/        — HTTP API 实现（规划中）

新增后端：复制 opengauss/ 目录，实现 contracts/ 中的三个协议即可。
"""

__all__: list[str] = []
