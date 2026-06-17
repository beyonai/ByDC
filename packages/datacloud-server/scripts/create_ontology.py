#!/usr/bin/env python3
"""创建本体示例。"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()

from datacloud_server.adapters.local_adapter import LocalOntologyAdapter
from datacloud_server.models.action import Action, ActionParam
from datacloud_server.models.datasource import Datasource
from datacloud_server.models.object_type import ObjectType
from datacloud_server.models.property import Property
from datacloud_server.models.relation import Relation
from datacloud_server.models.view import View, ViewProperty
from datacloud_server.registry.registry import OntologyBaseEntry, OntologyBaseRegistry
from datacloud_server.services.adapter_router import AdapterRouter
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
    resource_svc = OntologyResourceService(router)

    # =================================================================
    # 1. Create Object (with Properties)
    # =================================================================
    print("\n--- 1. 创建 Object ---")
    customer = ObjectType(
        objectCode="by_customer_script",
        objectName="客户（脚本示例）",
        objectDesc="由脚本创建的客户对象",
        conceptType="business",
        properties=[
            Property(
                propertyCode="customer_name",
                propertyName="客户名称",
                dataType="string",
                isRequired=1,
                businessDefinition="客户的完整名称",
            ),
            Property(
                propertyCode="contact_phone",
                propertyName="联系电话",
                dataType="string",
                businessDefinition="客户联系电话号码",
            ),
        ],
    )
    created = resource_svc.create_object(BASE_ID, SCENE_ID, customer)
    logger.info("Object created: %s (%s)", created.object_code, created.object_name)

    # =================================================================
    # 2. 创建 View
    # =================================================================
    print("\n--- 2. 创建 View ---")
    v = View(
        viewCode="customer_orders_v",
        viewName="客户订单视图",
        description="关联客户与订单的查询视图",
        objectCodes=["by_customer_script"],
        properties=[
            ViewProperty(
                propertyName="客户名称",
                propertyCode="customer_name",
                sourceObject="by_customer_script",
                sourceObjectProperty="customer_name",
            ),
        ],
    )
    created_view = resource_svc.create_view(BASE_ID, SCENE_ID, v)
    logger.info("View created: %s (%s)", created_view.view_code, created_view.view_name)

    # =================================================================
    # 3. 创建 Relation
    # =================================================================
    print("\n--- 3. 创建 Relation ---")
    order = resource_svc.create_object(
        BASE_ID,
        SCENE_ID,
        ObjectType(
            objectCode="by_order_script",
            objectName="订单（脚本示例）",
            objectDesc="由脚本创建的订单对象",
            conceptType="business",
            properties=[
                Property(
                    propertyCode="order_amount",
                    propertyName="订单金额",
                    dataType="float",
                    businessDefinition="订单总金额",
                ),
            ],
        ),
    )
    logger.info("Object created: %s (%s)", order.object_code, order.object_name)

    rel = Relation(
        relationCode="customer_has_order",
        relationName="客户拥有订单",
        relationCardinality="1:N",
        relationDesc="一个客户可以拥有多个订单",
        sourceObjectCode="by_customer_script",
        sourceObjectName="客户（脚本示例）",
        targetObjectCode="by_order_script",
        targetObjectName="订单（脚本示例）",
    )
    created_rel = resource_svc.create_relation(BASE_ID, SCENE_ID, rel)
    logger.info(
        "Relation created: %s (%s -> %s)",
        created_rel.relation_code,
        created_rel.source_object_code,
        created_rel.target_object_code,
    )

    # =================================================================
    # 4. 创建 Action
    # =================================================================
    print("\n--- 4. 创建 Action ---")
    action = Action(
        actionCode="export_customer",
        actionName="导出客户数据",
        actionType="API",
        actionDesc="导出客户的完整信息",
        belongObjectCode="by_customer_script",
        requestMethod="POST",
        requestUrl="https://api.example.com/customers/export",
        params=[
            ActionParam(
                paramCode="format",
                paramName="导出格式",
                paramType="string",
                isRequired=0,
            ),
            ActionParam(
                paramCode="customer_id",
                paramName="客户ID",
                paramType="string",
                isRequired=1,
            ),
        ],
    )
    created_action = resource_svc.create_action(
        BASE_ID,
        SCENE_ID,
        "by_customer_script",
        action,
    )
    logger.info("Action created: %s (%s)", created_action.action_code, created_action.action_name)

    # =================================================================
    # 5. 创建 Datasource
    # =================================================================
    print("\n--- 5. 创建 Datasource ---")
    ds = Datasource(
        dbId="script_demo_db",
        dbName="示例数据库",
        dbType="opengauss",
        host="localhost",
        port=5432,
        database="demo",
        dbSchema="public",
        description="由脚本创建的示例数据源",
    )
    created_ds = resource_svc.create_datasource(BASE_ID, SCENE_ID, ds)
    logger.info("Datasource created: %s (%s)", created_ds.db_id, created_ds.db_name)

    # =================================================================
    # 6. 汇总
    # =================================================================
    print("\n--- 6. 汇总 ---")
    objects = resource_svc.get_objects(BASE_ID, SCENE_ID)
    views = resource_svc.get_views(BASE_ID, SCENE_ID)
    rels = resource_svc.get_relations(BASE_ID, SCENE_ID)
    actions = resource_svc.get_actions(BASE_ID, SCENE_ID, "by_customer_script")
    dss = resource_svc.get_datasources(BASE_ID, SCENE_ID)

    print(f"  Objects      : {len(objects)}")
    print(f"  Views        : {len(views)}")
    print(f"  Relations    : {len(rels)}")
    print(f"  Actions      : {len(actions)}")
    print(f"  Datasources  : {len(dss)}")

    print("\n" + "=" * 60)
    print("  完成。")
    print(f"  BASE_ID={BASE_ID}  SCENE_ID={SCENE_ID}")
    print("=" * 60)


if __name__ == "__main__":
    main()
