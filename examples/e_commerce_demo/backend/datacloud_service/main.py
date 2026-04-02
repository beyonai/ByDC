"""DataCloud Service entry point.

运行方式（从仓库根目录）：
    uv run python examples/e_commerce_demo/backend/datacloud_service/main.py

或使用启动脚本：
    bash examples/e_commerce_demo/backend/start.sh        # Linux/macOS
    examples\\e_commerce_demo\\backend\\start.bat          # Windows
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from by_framework import run_worker
from dotenv import load_dotenv

from datacloud_service.plugins.recommended_question_plugins import (
    RecommendedQuestionsPlugin,
)
from datacloud_service.plugins.worker_plugins.init_agent_conf import (
    InitDataCloudDigitalEmployeePlugin,
)
from datacloud_service.worker import DataCloudWorker


@dataclass(frozen=True)
class WorkerConfig:
    """Gateway worker settings read from os.environ (after backend/.env is loaded)."""

    api_key: str | None
    base_url: str | None
    model_name: str
    worker_id: str
    redis_host: str
    redis_port: int
    redis_db: int
    redis_password: str | None
    redis_username: str | None
    consumer_group: str
    workspace_dir: str

    @classmethod
    def from_environ(cls) -> WorkerConfig:
        """Build config from the current environment."""

        def opt(key: str) -> str | None:
            raw = os.environ.get(key)
            return raw.strip() if raw and raw.strip() else None

        def as_int(key: str, default: int) -> int:
            raw = os.environ.get(key)
            return int(raw.strip(), 10) if raw and raw.strip() else default

        return cls(
            api_key=opt("OPENAI_API_KEY"),
            base_url=opt("OPENAI_BASE_URL"),
            model_name=os.environ.get("DATACLOUD_LLM_REASONING_MODEL", "Qwen/Qwen3-235B-A22B"),
            worker_id=os.environ.get("DATACLOUD_GATEWAY_WORKER_ID", "datacloud"),
            redis_host=os.environ.get("DATACLOUD_GATEWAY_REDIS_HOST", "localhost"),
            redis_port=as_int("DATACLOUD_GATEWAY_REDIS_PORT", 6379),
            redis_db=as_int("DATACLOUD_GATEWAY_REDIS_DB", 0),
            redis_password=opt("DATACLOUD_GATEWAY_REDIS_PASSWORD"),
            redis_username=opt("DATACLOUD_GATEWAY_REDIS_USERNAME"),
            consumer_group=os.environ.get("DATACLOUD_GATEWAY_CONSUMER_GROUP", "datacloud"),
            workspace_dir=os.environ.get("DATACLOUD_GATEWAY_WORKSPACE_DIR", "/tmp/datacloud"),
        )

    def run_worker_kwargs(self) -> dict[str, Any]:
        """Arguments for ``run_worker`` from ``by_framework`` (excluding ``worker_class``)."""
        return {
            "worker_id": self.worker_id,
            "redis_host": self.redis_host,
            "redis_port": self.redis_port,
            "redis_db": self.redis_db,
            "redis_password": self.redis_password,
            "redis_username": self.redis_username,
            "consumer_group": self.consumer_group,
            "workspace_dir": self.workspace_dir,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "model_name": self.model_name,
        }


def main() -> None:
    """Load environment variables and start the DataCloud gateway worker."""
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
    cfg = WorkerConfig.from_environ()

    if not cfg.api_key:
        pass


    run_worker(
        worker_class=DataCloudWorker,
        plugin_list=[
            InitDataCloudDigitalEmployeePlugin(),
            RecommendedQuestionsPlugin(),
        ],
        **cfg.run_worker_kwargs(),
    )


if __name__ == "__main__":
    main()
