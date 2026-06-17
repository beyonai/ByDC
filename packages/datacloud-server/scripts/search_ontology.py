#!/usr/bin/env python3
"""快速开始：本体检索示例。
"""

from __future__ import annotations

import json
import logging
import os

from dotenv import load_dotenv

load_dotenv()

from datacloud_server.adapters.local_adapter import LocalOntologyAdapter
from datacloud_server.registry.registry import OntologyBaseEntry, OntologyBaseRegistry
from datacloud_server.services.adapter_router import AdapterRouter
from datacloud_server.services.search_engine import (
    RRFStrategy,
    SearchEngine,
)
from datacloud_server.storage.json_writer import JSONWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__file__)


BASE_ID = "owl_example"
DATA_DIR = os.environ.get('DATACLOUD_ONTOLOGY_PATH', "./")


def _print_engine_hits(hits: list[dict], limit: int = 3) -> None:
    """打印 SearchEngine 命中结果。"""
    if not hits:
        print("    (无结果)")
        return
    for h in hits[:limit]:
        rt = h.get("resultType", "?")
        score = h.get("score", 0)
        name = h.get("objectName") or h.get("matchedValue", "?")
        code = h.get("objectCode") or h.get("propertyCode") or "?"
        print(f"    → [{rt}] {name}  ({code})  score={score:.4f}")


def main() -> None:
    # --- 依赖装配 ---
    registry = OntologyBaseRegistry()
    registry.register(
        OntologyBaseEntry(
            base_id=BASE_ID,
            display_name="OWL 示例本体库",
            description="从 owl_example 目录加载的本体数据",
            owner_type="personal",
            source_type="LOCAL",
            ontology_path=DATA_DIR,
        )
    )
    adapter = LocalOntologyAdapter(DATA_DIR, JSONWriter())
    router = AdapterRouter(
        registry=registry,
        adapters={"LOCAL": adapter},  # type: ignore[arg-type]
    )

    # =================================================================
    # Agent 挂载场景模拟
    # =================================================================
    mount_config: list[dict[str, str]] = [
        {"type": "scene", "baseId": BASE_ID, "sceneId": "object"},
    ]
    scopes = [(m["baseId"], m["sceneId"]) for m in mount_config]
    agent_engine = SearchEngine(router=router, scopes=scopes, strategy=RRFStrategy())

    for query in ["帮我查客户相关的本体", "项目任务"]:
        print(f"\n  用户: 「{query}」")
        try:
            agent_hits = agent_engine.search(keyword=query, search_scope="metadata")
        except Exception:
            logger.exception("Agent 搜索失败: %s", query)
            agent_hits = []
        _print_engine_hits(agent_hits)

    print("\n" + "=" * 60)
    print("  完成。")


if __name__ == "__main__":
    main()
