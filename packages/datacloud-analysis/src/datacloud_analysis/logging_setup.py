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

Per-request 隔离日志（解决并发时日志混淆问题）：

    from datacloud_analysis.logging_setup import attach_request_log, detach_request_log

    request_id = attach_request_log(request_id="abc123")   # 返回实际使用的 request_id
    try:
        ...
    finally:
        detach_request_log(request_id)

    # 或使用上下文管理器：
    async with request_log_context("abc123"):
        ...

每次调用生成独立日志文件：logs/requests/20260526_143022_abc123.log
并发 N 个请求 → N 个独立文件，互不干扰。

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
import uuid
from collections.abc import AsyncGenerator
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path

_SETUP_DONE: bool = False
_CONFIGURED_NAMESPACES: list[str] = []

_FMT_CONSOLE = "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s"
_FMT_FILE = "%(asctime)s [%(levelname)-5s] %(process)d %(name)s: %(message)s"
_FMT_REQUEST = "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

# 日志配置覆盖的命名空间（不触碰 root logger）
_MANAGED_NAMESPACES = ("datacloud_analysis",)

# 仅对噪音最大的子模块提升级别，保留 langchain_core 整体的 INFO 诊断
_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "urllib3",
    "langchain_core.tracers",
    "langchain_core.callbacks",
    "openai._base_client",
)


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
    handler.setFormatter(logging.Formatter(_FMT_FILE, datefmt=_DATE_FMT))
    return handler


def setup_logging(
    *,
    log_dir: str | None = None,
    level: str | None = None,
    app_backup_count: int | None = None,
    error_backup_count: int | None = None,
    request_keep_days: int | None = None,
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
        DATACLOUD_LOG_REQUEST_KEEP     requests/*.log 保留天数，默认 7

    Args:
        extra_namespaces: 调用方追加的额外命名空间（如落地项目的包名）。
    """
    global _SETUP_DONE, _CONFIGURED_NAMESPACES, _log_dir_for_requests, _request_keep_days
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
    _request_keep_days = int(
        request_keep_days
        if request_keep_days is not None
        else os.environ.get("DATACLOUD_LOG_REQUEST_KEEP", "7")
    )
    _log_dir_for_requests = _log_dir

    _log_dir.mkdir(parents=True, exist_ok=True)

    # ── 共享 Handler（两个命名空间复用同一对文件）──────────────────────────
    app_handler = _make_timed_handler(_log_dir / "app.log", _level, _app_keep)
    err_handler = _make_timed_handler(_log_dir / "error.log", logging.ERROR, _error_keep)

    console_handler: logging.StreamHandler | None = None  # type: ignore[type-arg]
    if enable_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(_level)
        console_handler.setFormatter(logging.Formatter(_FMT_CONSOLE, datefmt=_DATE_FMT))

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

    logging.getLogger(__name__).info(
        "Logging initialized: level=%s log_dir=%s app_keep=%dd error_keep=%dd",
        _level_str,
        _log_dir.resolve(),
        _app_keep,
        _error_keep,
    )


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
# Per-request 隔离日志
# ---------------------------------------------------------------------------
# 设计原则：
#   logging 的 Handler 挂在 logger 对象上，是进程级全局状态。
#   如果每个请求各自 addHandler/removeHandler，并发时多个 handler 同时在线，
#   每条日志会被所有在线 handler 写入，导致串台。
#
#   正确方案：
#   1. 进程启动时挂一个共享的 PerRequestRouter（单例），永不移除。
#   2. 每个请求通过 ContextVar 注册自己的 (request_id, file_path)。
#   3. PerRequestRouter.emit() 读取当前协程的 ContextVar，只写入当前请求的文件。
#   4. 并发 N 个请求 → N 个独立文件，互不串台。
# ---------------------------------------------------------------------------

# ContextVar：当前协程绑定的 (request_id, log_file_path)
# None 表示当前协程不在任何 request_log_context 内
_current_request: ContextVar[tuple[str, Path] | None] = ContextVar("_current_request", default=None)

_log_dir_for_requests: Path = Path("logs")

# 共享 router 单例（进程级，挂载一次）
_per_request_router: _PerRequestRouter | None = None
_router_namespaces: list[str] = []
_request_keep_days: int = 7  # requests/*.log 默认保留7天
_detach_counter: int = 0  # 每 _CLEANUP_INTERVAL 次 detach 触发一次清理
_CLEANUP_INTERVAL: int = 100


class _PerRequestRouter(logging.Handler):
    """进程级共享 handler，按 ContextVar 把日志路由到当前请求的独立文件。

    并发时每个协程各自读取 _current_request，只写入自己的文件，不会串台。
    文件 handle 按 request_id 缓存，detach 时关闭。
    """

    def __init__(self, level: int = logging.DEBUG) -> None:
        super().__init__(level)
        self._files: dict[str, tuple[Path, logging.FileHandler]] = {}
        self._lock = __import__("threading").Lock()

    def emit(self, record: logging.LogRecord) -> None:
        ctx = _current_request.get()
        if ctx is None:
            return
        rid, log_path = ctx
        fh = self._get_or_open(rid, log_path)
        fh.emit(record)

    def _get_or_open(self, rid: str, log_path: Path) -> logging.FileHandler:
        with self._lock:
            if rid not in self._files:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                fh = logging.FileHandler(str(log_path), encoding="utf-8")
                fh.setLevel(self.level)
                fh.setFormatter(self.formatter)
                self._files[rid] = (log_path, fh)
            return self._files[rid][1]

    def close_request(self, rid: str) -> None:
        with self._lock:
            entry = self._files.pop(rid, None)
        if entry:
            _, fh = entry
            fh.flush()
            fh.close()


def _ensure_router_installed(
    extra_namespaces: tuple[str, ...] = (),
    level: int = logging.DEBUG,
) -> _PerRequestRouter:
    """确保 PerRequestRouter 已挂载到所有目标命名空间（幂等）。"""
    global _per_request_router, _router_namespaces

    all_ns: list[str] = list(_CONFIGURED_NAMESPACES)
    for ns in extra_namespaces:
        if ns not in all_ns:
            all_ns.append(ns)

    if _per_request_router is None:
        router = _PerRequestRouter(level=level)
        router.setFormatter(logging.Formatter(_FMT_REQUEST, datefmt=_DATE_FMT))
        _per_request_router = router
    else:
        router = _per_request_router

    # 把 router 挂到尚未挂载的命名空间
    for ns in all_ns:
        lg = logging.getLogger(ns)
        if router not in lg.handlers:
            lg.addHandler(router)
            if ns not in _router_namespaces:
                _router_namespaces.append(ns)

    return router


def _get_request_log_dir() -> Path:
    return _log_dir_for_requests / "requests"


def _make_request_id(hint: str | None) -> str:
    """生成 request_id，格式：{日期}_{时间}_{trace_id 或 uuid8}。

    trace_id 内部的 _ 替换为 - 避免与外层分隔符混淆，不截断保留完整值。
    示例：20260526_100848_10012478-10012480
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")  # noqa: DTZ005
    raw = (hint or "").strip()
    short = raw.replace("_", "-") if raw else uuid.uuid4().hex[:8]
    return f"{ts}_{short}"


def _cleanup_old_request_logs(keep_days: int) -> None:
    """删除 requests/ 目录下超过 keep_days 天的 .log 文件。"""
    log_dir = _get_request_log_dir()
    if not log_dir.exists():
        return
    cutoff = datetime.now().timestamp() - keep_days * 86400  # noqa: DTZ005
    for f in log_dir.glob("*.log"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def attach_request_log(
    request_id: str | None = None,
    *,
    level: int | None = None,
    extra_namespaces: tuple[str, ...] = (),
) -> str:
    """为当前协程绑定一个独立日志文件，返回实际使用的 request_id。

    底层使用单个共享 PerRequestRouter + ContextVar 路由，并发请求互不串台。

    Args:
        request_id: 外部传入的请求标识（如 trace_id），None 时自动生成。
        level: 日志级别，默认 DEBUG。
        extra_namespaces: 除 _CONFIGURED_NAMESPACES 外，额外需要捕获的 logger 命名空间，
            例如 "by-framework"、"byclaw_data"。

    Returns:
        实际使用的 request_id（用于传给 detach_request_log）。
    """
    rid = _make_request_id(request_id)
    log_path = _get_request_log_dir() / f"{rid}.log"

    _ensure_router_installed(
        extra_namespaces=extra_namespaces,
        level=level or logging.DEBUG,
    )

    # 绑定到当前协程的 ContextVar
    _current_request.set((rid, log_path))

    logging.getLogger(__name__).debug("attach_request_log: rid=%s path=%s", rid, log_path)
    return rid


def detach_request_log(request_id: str) -> None:
    """解除当前协程的 request 绑定，关闭对应的日志文件。

    应在 finally 块中调用，确保文件句柄不泄漏。
    每 100 次调用触发一次过期文件清理（基于 _request_keep_days）。
    """
    global _detach_counter
    _current_request.set(None)

    if _per_request_router is not None:
        _per_request_router.close_request(request_id)

    _detach_counter += 1
    if _detach_counter % _CLEANUP_INTERVAL == 0:
        _cleanup_old_request_logs(_request_keep_days)

    logging.getLogger(__name__).debug("detach_request_log: rid=%s closed", request_id)


@contextlib.asynccontextmanager
async def request_log_context(
    request_id: str | None = None,
    *,
    level: int | None = None,
    extra_namespaces: tuple[str, ...] = (),
) -> AsyncGenerator[str, None]:
    """异步上下文管理器，自动 attach/detach per-request 日志文件。

    并发安全：每个协程通过 ContextVar 独立路由，不会互相串台。

    用法::

        async with request_log_context(
            trace_id,
            extra_namespaces=("by-framework", "byclaw_data"),
        ) as rid:
            logger.info("只写入当前请求的 requests/{rid}.log")

    Args:
        request_id: 外部传入的请求标识，None 时自动生成。
        level: 日志级别，默认 DEBUG。
        extra_namespaces: 额外需要捕获的 logger 命名空间。

    Yields:
        实际使用的 request_id。
    """
    rid = attach_request_log(request_id, level=level, extra_namespaces=extra_namespaces)
    try:
        yield rid
    finally:
        detach_request_log(rid)
