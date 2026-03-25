"""DataCloud Service entry point.

运行方式（从仓库根目录）：
    uv run python examples/e_commerce_demo/backend/datacloud_service/main.py

或使用启动脚本：
    bash examples/e_commerce_demo/backend/start.sh        # Linux/macOS
    examples\\e_commerce_demo\\backend\\start.bat          # Windows
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from gateway_sdk import run_worker

from datacloud_service.worker import DataCloudWorker


def main() -> None:
    """Load environment variables and start the DataCloud gateway worker."""
    # 优先加载 backend/.env（与本文件同级的父目录）
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(dotenv_path=env_path)

    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")
    model_name = os.environ.get("DATACLOUD_LLM_REASONING_MODEL", "Qwen/Qwen3-235B-A22B")

    if not api_key:
        print("⚠️  警告: OPENAI_API_KEY 未设置，LLM 调用将失败，请检查 .env 文件。")

    print("▶  正在启动 DataCloudWorker ...")
    print(f"   model   : {model_name}")
    print(f"   base_url: {base_url or '(OpenAI 默认)'}")

    run_worker(
        worker_class=DataCloudWorker,
        worker_id="datacloud",
        redis_host="10.10.168.204",
        redis_port=6379,
        redis_db=0,
        redis_password="admin123",
        redis_username="default",
        consumer_group="datacloud",
        workspace_dir="/tmp/datacloud",
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
    )


if __name__ == "__main__":
    main()
