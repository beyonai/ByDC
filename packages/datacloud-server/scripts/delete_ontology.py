#!/usr/bin/env python3
"""删除本体示例。"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()

from datacloud_server.adapters.local_adapter import LocalOntologyAdapter
from datacloud_server.registry.registry import OntologyBaseEntry, OntologyBaseRegistry
from datacloud_server.services.adapter_router import AdapterRouter
from datacloud_server.services.ontology_base_service import OntologyBaseService
from datacloud_server.services.ontology_resource_service import OntologyResourceService
from datacloud_server.storage.json_writer import JSONWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


BASE_ID = "example_script"
DATA_DIR = os.environ.get("DATACLOUD_ONTOLOGY_PATH", "./")
SCENE_ID = "object"


def main() -> None:
    # --- 依赖装配 ---
    registry = OntologyBaseRegistry()
    registry.register(
        OntologyBaseEntry(
            base_id=BASE_ID,
            display_name="脚本示例本体库",
            description="由 create_ontology.py 创建",
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
    base_svc = OntologyBaseService(router)
    resource_svc = OntologyResourceService(router)

    # Delete child resources first, parent last -- avoid broken references
    # =================================================================
    # 1. 删除 Action
    # =================================================================
    print("\n--- 1. 删除 Action ---")
    try:
        resource_svc.delete_action(BASE_ID, SCENE_ID, "by_customer_script", "export_customer")
        logger.info("Action deleted: export_customer")
    except Exception:
        logger.exception("删除 Action 失败")

    # =================================================================
    # 2. 删除 Relation
    # =================================================================
    print("\n--- 2. 删除 Relation ---")
    try:
        resource_svc.delete_relation(BASE_ID, SCENE_ID, "customer_has_order")
        logger.info("Relation deleted: customer_has_order")
    except Exception:
        logger.exception("删除 Relation 失败")

    # =================================================================
    # 3. 删除 View
    # =================================================================
    print("\n--- 3. 删除 View ---")
    try:
        resource_svc.delete_view(BASE_ID, SCENE_ID, "customer_orders_v")
        logger.info("View deleted: customer_orders_v")
    except Exception:
        logger.exception("删除 View 失败")

    # =================================================================
    # 4. 删除 Objects
    # =================================================================
    print("\n--- 4. 删除 Objects ---")
    for code in ("by_customer_script", "by_order_script"):
        try:
            resource_svc.delete_object(BASE_ID, SCENE_ID, code)
            logger.info("Object deleted: %s", code)
        except Exception:
            logger.exception("删除 Object 失败: %s", code)

    # =================================================================
    # 5. 删除 Datasource
    # =================================================================
    print("\n--- 5. 删除 Datasource ---")
    try:
        resource_svc.delete_datasource(BASE_ID, SCENE_ID, "script_demo_db")
        logger.info("Datasource deleted: script_demo_db")
    except Exception:
        logger.exception("删除 Datasource 失败")

    # =================================================================
    # 6. 删除 OntologyBase
    # =================================================================
    print("\n--- 6. 删除 OntologyBase ---")
    try:
        base_svc.delete_base(BASE_ID)
        logger.info("OntologyBase deleted: %s", BASE_ID)
    except Exception:
        logger.exception("删除 OntologyBase 失败")

    print("\n" + "=" * 60)
    print("  完成。")
    print("=" * 60)


if __name__ == "__main__":
    main()
