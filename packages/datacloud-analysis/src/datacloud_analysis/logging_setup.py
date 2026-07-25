"""统一日志配置模块。

只配置 datacloud_analysis / byclaw_data 两个命名空间，不干扰
by_framework 或其他第三方库已安装的 root handler。

调用方式（在进程启动时调用一次）：

    from datacloud_analysis.logging_setup import setup_logging
    setup_logging()            # 使用环境变量 / 默认值
    setup_logging(             # 显式指定
        log_dir="/var/log/datacloud",
        level="DEBUG",
        app_backup_count=30,
        error_backup_count=90,
    )

日志格式符合 OTLP 标准：有活跃 OTel span 时自动注入 trace_id / span_id：

    2026-06-05 17:26:57 [INFO ] [tid=4b5205a0... sid=9ab1ee3c] byclaw_data.worker: ...
    2026-06-05 17:26:57 [INFO ] byclaw_data.worker: startup message ...

日志仅写入本地文件（app.log / error.log）和 console，不推送到远端。
排查时拿 Langfuse 的 trace_id 到本地 grep：
    grep "4b5205a019afa300" logs/app.log

request_log_context() 保留为兼容 shim，调用方无需修改：

    async with request_log_context(trace_id) as rid:
        ...

仅供测试使用的重置接口：

    from datacloud_analysis.logging_setup import reset_logging
    reset_logging()
"""

from __future__ import annotations

import contextlib
import gzip
import logging
import logging.handlers
import os
import shutil
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

_SETUP_DONE: bool = False
_CONFIGURED_NAMESPACES: list[str] = []

_FMT_CONSOLE = "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s"
_FMT_CONSOLE_OTEL = (
    "%(asctime)s [%(levelname)-5s] [tid=%(otelTraceID)s sid=%(otelSpanID)s] %(name)s: %(message)s"
)
_FMT_FILE = "%(asctime)s [%(levelname)-5s] %(process)d %(name)s: %(message)s"
_FMT_FILE_OTEL = "%(asctime)s [%(levelname)-5s] %(process)d [tid=%(otelTraceID)s sid=%(otelSpanID)s] %(name)s: %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

# 日志配置覆盖的命名空间（不触碰 root logger）
_MANAGED_NAMESPACES = (
    "datacloud_analysis",
    "datacloud_platform",
    "datacloud_knowledge",
    "datacloud_data",
    "datacloud_data_sdk",
    "unhandled_exception",
)

# 仅对噪音最大的子模块提升级别，保留 langchain_core 整体的 INFO 诊断
_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "urllib3",
    "langchain_core.tracers",
    "langchain_core.callbacks",
    "openai._base_client",
)


class _OtelContextFilter(logging.Filter):
    """向每条 LogRecord 注入当前 OTel span 的 trace_id / span_id。

    有活跃 span 时 record.otelTraceID / record.otelSpanID 为 32/16 位 hex 字符串；
    无 span 时为空字符串，Formatter 据此选择不含 tid/sid 的格式。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from opentelemetry import trace as _otel_trace  # noqa: PLC0415

            ctx = _otel_trace.get_current_span().get_span_context()
            if ctx.is_valid:
                record.otelTraceID = format(ctx.trace_id, "032x")  # type: ignore[attr-defined]
                record.otelSpanID = format(ctx.span_id, "016x")  # type: ignore[attr-defined]
            else:
                record.otelTraceID = ""  # type: ignore[attr-defined]
                record.otelSpanID = ""  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            record.otelTraceID = ""  # type: ignore[attr-defined]
            record.otelSpanID = ""  # type: ignore[attr-defined]
        return True


class _OptionalOtelFormatter(logging.Formatter):
    """有活跃 OTel span 时插入 [tid=xxx sid=xxx]，无 span 时格式保持干净。"""

    def __init__(self, fmt_with_otel: str, fmt_without_otel: str, **kwargs: object) -> None:
        super().__init__(fmt_with_otel, **kwargs)
        self._fmt_with = fmt_with_otel
        self._fmt_without = fmt_without_otel

    def format(self, record: logging.LogRecord) -> str:
        self._style._fmt = (  # type: ignore[attr-defined]
            self._fmt_with if getattr(record, "otelTraceID", "") else self._fmt_without
        )
        return super().format(record)


def _gz_namer(name: str) -> str:
    """轮转文件名追加 .gz 后缀。

    TimedRotatingFileHandler.getFilesToDelete() 用此函数生成预期文件名，
    再去磁盘匹配删除。namer 必须返回磁盘上的真实文件名（含 .gz），
    cleanup 才能正确触发，保证 backupCount 生效。
    """
    return name + ".gz"


def _gzip_rotator(source: str, dest: str) -> None:
    """轮转回调：gzip 压缩旧日志文件。

    dest 已由 _gz_namer 追加了 .gz，此处直接写入即可。
    """
    with open(source, "rb") as f_in, gzip.open(dest, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    os.remove(source)


def _make_timed_handler(
    log_path: Path,
    level: int,
    backup_count: int,
) -> logging.handlers.TimedRotatingFileHandler:
    """创建按天轮转 + gzip 压缩的 FileHandler。"""
    handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(log_path),
        when="midnight",
        interval=1,
        backupCount=backup_count,
        encoding="utf-8",
        utc=False,
    )
    handler.suffix = "%Y-%m-%d"
    handler.namer = _gz_namer
    handler.rotator = _gzip_rotator
    handler.setLevel(level)
    handler.setFormatter(_OptionalOtelFormatter(_FMT_FILE_OTEL, _FMT_FILE, datefmt=_DATE_FMT))
    return handler


def setup_logging(
    *,
    log_dir: str | None = None,
    level: str | None = None,
    app_backup_count: int | None = None,
    error_backup_count: int | None = None,
    enable_console: bool = True,
    extra_namespaces: tuple[str, ...] = (),
) -> None:
    """初始化日志配置，进程生命周期内只执行一次。

    参数优先级：显式传参 > 环境变量 > 默认值。

    环境变量：
        DATACLOUD_LOG_DIR              日志目录，默认 ./logs
        DATACLOUD_LOG_LEVEL            日志级别，默认 INFO
        DATACLOUD_LOG_APP_KEEP         app.log 保留天数，默认 30
        DATACLOUD_LOG_ERROR_KEEP       error.log 保留天数，默认 90

    日志格式：遵循 OTLP 标准，有活跃 OTel span 时自动注入 trace_id/span_id。
    日志仅写入本地文件和 console，不推送到远端。

    Args:
        extra_namespaces: 调用方追加的额外命名空间（如落地项目的包名）。
    """
    global _SETUP_DONE, _CONFIGURED_NAMESPACES
    if _SETUP_DONE:
        return
    _SETUP_DONE = True
    _CONFIGURED_NAMESPACES = [*_MANAGED_NAMESPACES, *extra_namespaces]

    # ── 参数解析（用 is not None 避免 0 被 or 短路）────────────────────────
    _log_dir = Path(log_dir if log_dir is not None else os.environ.get("DATACLOUD_LOG_DIR", "logs"))
    _level_str = (
        level if level is not None else os.environ.get("DATACLOUD_LOG_LEVEL", "INFO")
    ).upper()
    _level = getattr(logging, _level_str, logging.INFO)
    _app_keep = int(
        app_backup_count
        if app_backup_count is not None
        else os.environ.get("DATACLOUD_LOG_APP_KEEP", "30")
    )
    _error_keep = int(
        error_backup_count
        if error_backup_count is not None
        else os.environ.get("DATACLOUD_LOG_ERROR_KEEP", "90")
    )

    _log_dir.mkdir(parents=True, exist_ok=True)

    otel_filter = _OtelContextFilter()

    # ── 共享 Handler（两个命名空间复用同一对文件）──────────────────────────
    app_handler = _make_timed_handler(_log_dir / "app.log", _level, _app_keep)
    err_handler = _make_timed_handler(_log_dir / "error.log", logging.ERROR, _error_keep)
    app_handler.addFilter(otel_filter)
    err_handler.addFilter(otel_filter)

    console_handler: logging.StreamHandler | None = None  # type: ignore[type-arg]
    if enable_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(_level)
        console_handler.setFormatter(
            _OptionalOtelFormatter(_FMT_CONSOLE_OTEL, _FMT_CONSOLE, datefmt=_DATE_FMT)
        )
        console_handler.addFilter(otel_filter)

    # ── 按命名空间配置，不触碰 root logger ──────────────────────────────────
    for ns in _CONFIGURED_NAMESPACES:
        ns_logger = logging.getLogger(ns)
        ns_logger.setLevel(_level)
        ns_logger.handlers.clear()
        if console_handler is not None:
            ns_logger.addHandler(console_handler)
        ns_logger.addHandler(app_handler)
        ns_logger.addHandler(err_handler)
        ns_logger.propagate = False  # 不向 root 传播，避免与 by_framework 重复打印

    # ── 降噪：仅针对真正高噪音的子模块 ─────────────────────────────────────
    for noisy in _NOISY_LOGGERS:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # ── 未捕获异常兜底：确保写入 error.log ───────────────────────────────────
    _install_excepthook()

    logging.getLogger(__name__).info(
        "Logging initialized: level=%s log_dir=%s app_keep=%dd error_keep=%dd",
        _level_str,
        _log_dir.resolve(),
        _app_keep,
        _error_keep,
    )


def _install_excepthook() -> None:
    """将未捕获异常路由到 logging.error，确保写入 error.log。

    - sys.excepthook：同步主线程未捕获异常
    - asyncio loop policy：新建 event loop 时自动注入异常处理器
    """
    import asyncio  # noqa: PLC0415

    _unhandled_logger = logging.getLogger("unhandled_exception")

    def _sync_excepthook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: object,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)  # type: ignore[arg-type]
            return
        _unhandled_logger.error(
            "Unhandled exception", exc_info=(exc_type, exc_value, exc_tb)  # type: ignore[arg-type]
        )

    sys.excepthook = _sync_excepthook

    def _async_exception_handler(loop: object, context: dict[str, object]) -> None:
        exc = context.get("exception")
        msg = context.get("message", "Unhandled exception in asyncio")
        if isinstance(exc, BaseException):
            _unhandled_logger.error(msg, exc_info=exc)
        else:
            _unhandled_logger.error("%s: %s", msg, context)

    # 包装 loop policy，使每个新建的 event loop 自动装载 exception handler
    _orig_policy = asyncio.get_event_loop_policy()

    class _LoggingPolicy(type(_orig_policy)):  # type: ignore[misc]
        def new_event_loop(self) -> asyncio.AbstractEventLoop:
            loop = super().new_event_loop()
            loop.set_exception_handler(_async_exception_handler)
            return loop

    asyncio.set_event_loop_policy(_LoggingPolicy())


def reset_logging() -> None:
    """重置初始化标志，仅供测试使用。

    允许在不同测试用例中以不同参数重新调用 setup_logging()，
    防止全局状态污染测试隔离。生产代码不应调用此函数。
    """
    global _SETUP_DONE, _CONFIGURED_NAMESPACES
    _SETUP_DONE = False
    for ns in _CONFIGURED_NAMESPACES:
        ns_logger = logging.getLogger(ns)
        ns_logger.handlers.clear()
        ns_logger.propagate = True
    _CONFIGURED_NAMESPACES = []


# ---------------------------------------------------------------------------
# request_log_context — 兼容 shim
# ---------------------------------------------------------------------------
# per-request 隔离文件机制已移除（日志通过 app.log + OTLP 统一输出，
# trace_id 由 OTel span context 自动注入）。
# 此 shim 保持接口兼容，调用方（worker.py）无需修改。
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def request_log_context(
    request_id: str | None = None,
    **_kwargs: object,
) -> AsyncGenerator[str, None]:
    """兼容 shim：原 per-request 隔离日志已由 OTLP trace_id 注入替代。

    调用方行为不变，request_id 直接透传返回供外部标识使用。
    """
    yield request_id or ""


# 保留供可能存在的直接调用方使用，均为无操作
def attach_request_log(request_id: str | None = None, **_kwargs: object) -> str:
    """兼容 shim，无操作。"""
    return request_id or ""


def detach_request_log(request_id: str, **_kwargs: object) -> None:  # noqa: ARG001
    """兼容 shim，无操作。"""
