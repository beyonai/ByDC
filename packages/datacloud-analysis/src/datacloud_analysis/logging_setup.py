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

仅供测试使用的重置接口：

    from datacloud_analysis.logging_setup import reset_logging
    reset_logging()
"""

from __future__ import annotations

import gzip
import logging
import logging.handlers
import os
import shutil
from pathlib import Path

_SETUP_DONE: bool = False
_CONFIGURED_NAMESPACES: list[str] = []

_FMT_CONSOLE = "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s"
_FMT_FILE = "%(asctime)s [%(levelname)-5s] %(process)d %(name)s: %(message)s"
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
    enable_console: bool = True,
    extra_namespaces: tuple[str, ...] = (),
) -> None:
    """初始化日志配置，进程生命周期内只执行一次。

    参数优先级：显式传参 > 环境变量 > 默认值。

    环境变量：
        DATACLOUD_LOG_DIR           日志目录，默认 ./logs
        DATACLOUD_LOG_LEVEL         日志级别，默认 INFO
        DATACLOUD_LOG_APP_KEEP      app.log 保留天数，默认 30
        DATACLOUD_LOG_ERROR_KEEP    error.log 保留天数，默认 90

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
