import sys

sys.path.insert(0, "src")

import asyncio
import logging
from pathlib import Path

from datacloud_data_sdk import InvocationContext, OntologyLoader
from datacloud_data_sdk.ontology.term_loader import TermLoader
from datacloud_data_sdk.plan.query_plan_generator import LangGraphPlanGenerator
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
    force=True,
)

load_dotenv(
    Path(
        "xx"
    )
)


async def main1() -> None:
    loader = OntologyLoader()
    loader.load_from_path("xxx")
    loader.load_scene_from_path("xxx")
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model="Qwen/Qwen3-Coder-30B-Instruct",
            base_url="xx",
            api_key="xxx",
            temperature=0.0,
            max_retries=2,
        ),
        term_loader=TermLoader.from_config({}),
        csv_base_dir=str(Path("./tmp").resolve()),
        sql_execution_mode="internal",
    )

    obj = loader.get_object("dws_enterprise_wide")
    with InvocationContext(tenant_id="t1", user_id="u1"):
        result = await obj.query(
            "2026年北京亦庄经济技术开发区区域内单位亩产效益最低的10家企业", include_plan=True
        )

    print(result)


async def main2() -> None:
    loader = OntologyLoader()

    loader.load_from_path("xxx")
    loader.load_scene_from_path("xxx")
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model="Qwen/Qwen3-Coder-30B-Instruct",
            base_url="xxx",
            api_key="xxx",
            temperature=0.0,
            max_retries=2,
        ),
        term_loader=TermLoader.from_config({}),
        csv_base_dir=str(Path("./tmp").resolve()),
        sql_execution_mode="internal",
    )

    view = loader.get_view("scene_01_data_analysis")
    with InvocationContext(tenant_id="t1", user_id="u1"):
        result = await view.query(
            "026年北京亦庄经济技术开发区区域内单位亩产效益最低的10家企业", include_plan=True
        )

    print(result)


async def main3() -> None:
    loader = OntologyLoader()
    loader.load_scene_from_path("xxx")
    loader.load_from_path("xxx")
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model="Qwen/Qwen3-Coder-30B-Instruct",
            base_url="xxx",
            api_key="xxx",
            temperature=0.0,
            max_retries=2,
        ),
        term_loader=TermLoader.from_config({}),
        csv_base_dir=str(Path("./tmp").resolve()),
        sql_execution_mode="internal",
    )
    obj = loader.get_object("analysis_report")

    print("actions:", obj.list_action_codes())
    print("schema:", obj.get_action_schema("query_reports_by_scope"))

    with InvocationContext(tenant_id="t1", user_id="u1"):
        result = await obj.invoke_action(
            "query_reports_by_scope",
            {
                "gridNames": ["博兴街道"],
                "regionNames": [],
                "category": "税务风险识别报告",
            },
        )
    print(result)


async def main4() -> None:
    loader = OntologyLoader()
    loader.load_scene_from_path("xxx")
    loader.load_from_path("xxx")
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model="Qwen/Qwen3-Coder-30B-Instruct",
            base_url="xxx",
            api_key="xxx",
            temperature=0.0,
            max_retries=2,
        ),
        term_loader=TermLoader.from_config({}),
        csv_base_dir=str(Path("./tmp").resolve()),
        sql_execution_mode="internal",
    )
    view = loader.get_view("scene_01_data_analysis")
    with InvocationContext(tenant_id="t1", user_id="u1"):
        result = await view.invoke_object_action(
            "analysis_report",
            "query_reports_by_scope",
            {
                "gridNames": ["博兴街道"],
                "regionNames": [],
                "category": "税务风险识别报告",
            },
        )
    print(result)


async def main5() -> None:
    loader = OntologyLoader()
    loader.load_from_owl_directory("xxx")
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model="Qwen/Qwen3-Coder-30B-Instruct",
            base_url="xxx",
            api_key="xxx",
            temperature=0.0,
            max_retries=2,
        ),
        term_loader=TermLoader.from_config({}),
        csv_base_dir=str(Path("./tmp").resolve()),
        sql_execution_mode="internal",
    )

    obj = loader.get_object("dws_enterprise_wide")
    with InvocationContext(tenant_id="t1", user_id="u1"):
        result = await obj.query(
            "2026年北京亦庄经济技术开发区区域内单位亩产效益最低的10家企业", include_plan=True
        )

    print(result)


async def main6() -> None:
    loader = OntologyLoader()
    loader.load_from_owl_directory("xxx")
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model="Qwen/Qwen3-Coder-30B-Instruct",
            base_url="xxx",
            api_key="xxx",
            temperature=0.0,
            max_retries=2,
        ),
        term_loader=TermLoader.from_config({}),
        csv_base_dir=str(Path("./tmp").resolve()),
        sql_execution_mode="internal",
    )
    obj = loader.get_object("ads_enterprise_analysis")
    from datacloud_data_service.tools.virtual_action_injector import (
        inject_virtual_actions,
    )

    inject_virtual_actions(loader)

    print("actions:", obj.list_action_codes())
    print("schema:", obj.get_action_schema("query_ads_enterprise_analysis"))

    with InvocationContext(tenant_id="t1", user_id="u1"):
        result = await obj.invoke_action(
            "query_ads_enterprise_analysis",
            {
                "select": ["企业唯一ID", "企业全称"],
                "order_by": [{"field": "企业总营收（万元）", "direction": "desc"}],
                "limit": 100,
                "offset": 0,
            },
        )
    print(result)


async def main7() -> None:
    loader = OntologyLoader()
    loader.load_from_owl_directory("xxx")
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model="Qwen/Qwen3-Coder-30B-Instruct",
            base_url="xxx",
            api_key="xxx",
            temperature=0.0,
            max_retries=2,
        ),
        term_loader=TermLoader.from_config({}),
        csv_base_dir=str(Path("./tmp").resolve()),
        sql_execution_mode="internal",
    )
    obj = loader.get_view("scene_enterprise_analysis")
    from datacloud_data_service.tools.virtual_action_injector import (
        inject_virtual_actions,
    )

    inject_virtual_actions(loader)

    print("actions:", obj.list_action_codes())
    print("schema:", obj.get_action_schema("query_scene_enterprise_analysis"))

    with InvocationContext(tenant_id="t1", user_id="u1", language=""):
        result = await obj.invoke_action(
            "query_scene_enterprise_analysis",
            {"select": [], "order_by": [], "limit": 10, "offset": 0},
        )
    print(result)


async def main8() -> None:
    loader = OntologyLoader()
    loader.load_from_owl_directory(
        "xxx"
    )
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model="MiniMax-M2.7-highspeed",
            base_url="https://api.minimaxi.com/v1",
            api_key="xxx",
            temperature=0.0,
            max_retries=2,
        ),
        term_loader=TermLoader.from_config({}),
        csv_base_dir=str(Path("./tmp").resolve()),
        sql_execution_mode="internal",
    )
    obj = loader.get_object("by_opportunity")
    from datacloud_data_service.tools.virtual_action_injector import (
        inject_virtual_actions,
    )

    inject_virtual_actions(loader)

    # print("actions:", obj.list_action_codes())
    # print("schema:", obj.get_action_schema("query_ads_enterprise_analysis"))

    with InvocationContext(tenant_id="t1", user_id="u1"):
        result = await obj.query("查询销售用户黄牛逼的商机，显示商机名称和签约金额")
    print(result)


async def main9() -> None:
    loader = OntologyLoader()
    loader.load_from_owl_resource_directory(
        "xxx",
        object_codes=["sales_meeting_note"],
    )
    from datacloud_data_sdk.executor.kb_search_backend import HttpKnowledgeSearchBackend

    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model="MiniMax-M2.7-highspeed",
            base_url="https://api.minimaxi.com/v1",
            api_key="xxx",
            temperature=0.0,
            max_retries=2,
        ),
        term_loader=TermLoader.from_config({}),
        csv_base_dir=str(Path("./tmp").resolve()),
        sql_execution_mode="internal",
        kb_backends={
            "http_knowledge_import": HttpKnowledgeSearchBackend(
                kb_configs={"endpoint_url": "xxx"}
            ),
        },
        default_kb_backend="http_knowledge_import",
    )
    obj = loader.get_object("sales_meeting_note")
    from datacloud_data_service.tools.virtual_action_injector import (
        inject_virtual_actions,
    )

    inject_virtual_actions(loader)

    print("actions:", obj.list_action_codes())
    print("schema:", obj.get_action_schema("search_sales_meeting_note"))
    print("schema:", obj.get_action_schema("write_sales_meeting_note"))

    # with InvocationContext(tenant_id="t1", user_id="u1"):
    #     result = await obj.invoke_action(
    #         "write_sales_meeting_note",
    #         {
    #             "labels": {
    #                 "meetingId": "2",
    #                 "meetingTitle": "datacloud的会议纪要内容",
    #                 "meetingTime": "2026-05-18 20:52:25",
    #                 "relatedBoId": 23,
    #                 "relatedCustomerId": 100,
    #                 "participantEmpNos": ["黄升", "罗彦卓"],
    #             },
    #             "source_path": "/会议纪要/datacloud的会议纪要内容.docx",
    #             "content": 'datacloud的会议纪要内容会议时间：2026-05-18 20:52:25会议主持：王威参与人员：黄升,罗彦卓会议主题：datacloud的会议──────────────────────────────────────────────────一、会议概述本次技术联调会议围绕端到端流程验证中的接口认证、服务注册与数据传递问题展开，重点排查了401认证错误、Redis缓存未刷新、会话ID错传等关键故障点，并明确了参数补全与SDK调用规范的修复方案。二、故障排查与定位1.401认证异常问题描述：接口返回401状态码，初步判断为认证配置问题。调用路径中多出BYservice层级，导致请求未正确路由。原因分析：实际服务已免登录，但因服务名未正常解析为IP地址，引发认证拦截。该问题与中层网关的服务发现机制有关。2.Redis缓存未刷新问题描述：模型APIKey未更新，因系统从Redis读取旧key所致。陈晓锋指出"没刷redis"，需手动触发刷新操作。修复方式：在管理页面更新token并保存，强制刷新缓存数据。验证后模型切换成功。三、服务注册与实例管理1.过期实例未清理问题描述：中层服务注册了多个instance，部分为上周遗留实例，TTL机制未能自动清除。处理建议：增强心跳检测逻辑，确保get时仅返回有效实例，避免调用失效节点。2.服务注册路径错误问题描述：直接调用SDK返回401，而本地命令行可通，怀疑注册路径不一致。后续动作：需进一步查看真实发出的请求头和路径。四、数据流与会话一致性1.会话ID传递错误问题描述：家长侧调用"大师"接口写文件时，传入的CSID（会话ID）错误，导致文件写入非目标目录。根因分析：正确sessionID应为纯数字格式（如4545401），但实际传入为doc-10042908类结构化ID。根本原因为中层服务未正确传递前端会话上下文，拼接逻辑出错。2.缺失必要参数问题描述：当前消息体中漏传usercode、sessionID、parentmessageID等关键字段，导致下游无法串联完整数据链路。五、修复方案与后续动作1.参数传递规范统一使用下划线命名法传递参数：user_code、session_id。所有调用应通过标准SDK发起，避免手动构造请求体导致协议不一致。小红负责修改代码，确保消息体包含全部必要字段。2.工具与资源准备MCP工具、智能体、知识库等组件需提前导入测试环境，当前部分工具缺失或未激活。王威安排向2.0群同步最新工具包，包括空气分析智能体、MGP能力模块等。3.验证计划明日完成最后一次端到端全流程验证，确保所有环节就绪。六、AI洞察1.多次故障根源指向服务元数据管理薄弱，建议建立注册实例健康度监控看板。2.手动构造请求而非使用SDK是主要风险源，需推动标准化接入并废弃自定义调用路径。3.会话上下文丢失问题暴露了中台服务对前端状态依赖过重，宜设计更健壮的上下文透传机制。──────────────────────────────────────────────────文档生成时间：2026-05-1410:58:12',
    #         },
    #     )

    select_fields = [
        "meetingId",
        "meetingTitle",
        "meetingTime",
        "relatedBoId",
        "relatedCustomerId",
        "participantEmpNos",
    ]
    search_cases = [
        (
            "semantic_only",
            {
                "query": "会议",
                "select": select_fields,
                "limit": 5,
            },
        ),
        (
            "is_not_null",
            {
                "query": "会议",
                "select": select_fields,
                "filters": [{"field": "relatedCustomerId", "op": "is_not_null"}],
                "limit": 5,
            },
        ),
        (
            "is_null",
            {
                "query": "会议",
                "select": select_fields,
                "filters": [{"field": "relatedCustomerId", "op": "is_null"}],
                "limit": 5,
            },
        ),
        (
            "eq",
            {
                "query": "会议",
                "select": select_fields,
                "filters": [
                    {
                        "field": "meetingTitle",
                        "op": "eq",
                        "value": "端到端流程故障排查会议纪要",
                    }
                ],
                "limit": 5,
            },
        ),
        (
            "ne",
            {
                "query": "会议",
                "select": select_fields,
                "filters": [{"field": "relatedCustomerId", "op": "ne", "value": ""}],
                "limit": 5,
            },
        ),
        (
            "in_to_or_contains",
            {
                "query": "会议",
                "select": select_fields,
                "filters": [
                    {
                        "field": "participantEmpNos",
                        "op": "in",
                        "value": ["王威", "黎嘉朗"],
                    }
                ],
                "limit": 5,
            },
        ),
        (
            "contains",
            {
                "query": "会议",
                "select": select_fields,
                "filters": [{"field": "participantEmpNos", "op": "contains", "value": "王威"}],
                "limit": 5,
            },
        ),
        (
            "between",
            {
                "query": "会议",
                "select": select_fields,
                "filters": [
                    {
                        "field": "meetingTime",
                        "op": "between",
                        "value": ["2026-04-01 00:00:00", "2026-04-30 23:59:59"],
                    }
                ],
                "limit": 5,
            },
        ),
        (
            "range_gte_lte",
            {
                "query": "会议",
                "select": select_fields,
                "filters": [
                    {"field": "meetingTime", "op": "gte", "value": "2026-04-01 00:00:00"},
                    {"field": "meetingTime", "op": "lte", "value": "2026-04-30 23:59:59"},
                ],
                "limit": 5,
            },
        ),
        (
            "or_relation",
            {
                "query": "会议",
                "select": select_fields,
                "filter_relation": "OR",
                "filters": [
                    {"field": "relatedBoId", "op": "is_not_null"},
                    {"field": "relatedCustomerId", "op": "is_not_null"},
                ],
                "limit": 5,
            },
        ),
        (
            "system_file_name_prefix",
            {
                "query": "会议",
                "select": select_fields,
                "filters": [{"field": "fileName", "op": "prefix", "value": "端到端"}],
                "limit": 5,
            },
        ),
        (
            "system_file_name_wildcard",
            {
                "query": "会议",
                "select": select_fields,
                "filters": [{"field": "fileName", "op": "wildcard", "value": "*会议纪要*"}],
                "limit": 5,
            },
        ),
        (
            "system_file_type",
            {
                "query": "会议",
                "select": select_fields,
                "filters": [{"field": "fileType", "op": "eq", "value": "md"}],
                "limit": 5,
            },
        ),
    ]

    with InvocationContext(tenant_id="t1", user_id="u1"):
        for case_name, payload in search_cases:
            print(f"\n===== search case: {case_name} =====")
            print("payload:", payload)
            result = await obj.invoke_action("search_sales_meeting_note", payload)
            print("result:", result)


async def main10() -> None:
    loader = OntologyLoader()
    loader.load_from_owl_resource_directory(
        "/Users/zouhaitian/Documents/workplace/project/Haojing/baiyin_ai_v2/ByClaw/byclaw-data/byclaw/resource",
        object_codes=["by_customer"],
    )
    from datacloud_data_sdk.executor.kb_search_backend import HttpKnowledgeSearchBackend

    # ByclawSqlExecuteConnector.configure_default_redis(
    #     RedisDiscoveryConfig(host="10.10.168.203", password="admin123", username="default")
    # )
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model="MiniMax-M2.7-highspeed",
            base_url="https://api.minimaxi.com/v1",
            api_key="xxx",
            temperature=0.0,
            max_retries=2,
        ),
        term_loader=TermLoader.from_config({}),
        csv_base_dir=str(Path("./tmp").resolve()),
        sql_execution_mode="internal",
        # kb_backends={
        #     "http_knowledge_import": HttpKnowledgeSearchBackend(
        #         kb_configs={"endpoint_url": "xxx"}
        #     ),
        # },
        # default_kb_backend="http_knowledge_import",
    )
    obj = loader.get_object("by_customer")
    from datacloud_data_service.tools.virtual_action_injector import (
        inject_virtual_actions,
    )

    inject_virtual_actions(loader)

    print("actions:", obj.list_action_codes())
    schemas = {
        "insert_by_customer": obj.get_action_schema("insert_by_customer"),
        "update_by_customer": obj.get_action_schema("update_by_customer"),
        "delete_by_customer": obj.get_action_schema("delete_by_customer"),
        "query_by_customer": obj.get_action_schema("query_by_customer"),
        "compute_by_customer": obj.get_action_schema("compute_by_customer"),
    }
    for action_code, schema in schemas.items():
        print(f"\n===== schema: {action_code} =====")
        print(schema)

    insert_schema = schemas["insert_by_customer"]["inputSchema"]
    record_schema = insert_schema["properties"]["records"]["items"]
    writable_fields = list(record_schema.get("properties", {}))
    sample_record = {
        field_code: _sample_value_for_schema(record_schema["properties"][field_code])
        for field_code in writable_fields[:8]
    }
    sample_record.update(
        {
            "customer_name": "北京国投中债资产管理有限公司",
            "salesEmpName": "洪七公",
            "industry": "金融",
            "province": "北京",
            "domain": "教育",
            "sales_person": "洪七公",
            "sales_user_id": "洪七公",
        }
    )
    sample_record = {
        field_code: value
        for field_code, value in sample_record.items()
        if field_code in record_schema.get("properties", {})
    }
    query_select = _schema_enum_values(
        schemas["query_by_customer"]["inputSchema"]["properties"]["select"]
    )[:8]
    if not query_select:
        query_select = writable_fields[:8]

    query_cases = [
        (
            "query_basic",
            {
                "select": query_select,
                "filters": [{"field": "id", "op": "eq", "value": 2}],
                "limit": 10,
                "offset": 0,
            },
        ),
        # (
        #     "query_in",
        #     {
        #         "select": query_select,
        #         "filters": [{"field": "salesEmpName", "op": "in", "value": ["罗彦卓"]}],
        #         "limit": 10,
        #         "offset": 0,
        #     },
        # ),
        # (
        #     "query_or_relation",
        #     {
        #         "select": query_select,
        #         "filter_relation": "OR",
        #         "filters": [
        #             {"field": "salesEmpName", "op": "eq", "value": "罗彦卓"},
        #             {"field": "customerName", "op": "like", "value": "测试客户"},
        #         ],
        #         "limit": 10,
        #         "offset": 0,
        #     },
        # ),
    ]
    operation_cases = [
        (
            "insert_by_customer",
            "insert_sample",
            {
                "records": [sample_record],
            },
        ),
        # (
        #     "update_by_customer",
        #     "update_by_filter",
        #     {
        #         "values": {"customerName": "测试客户_罗彦卓_已更新"},
        #         "filters": [{"field": "salesEmpName", "op": "eq", "value": "罗彦卓"}],
        #         "filter_relation": "AND",
        #     },
        # ),
        # (
        #     "delete_by_customer",
        #     "delete_by_filter_preview",
        #     {
        #         "filters": [
        #             {"field": "customerName", "op": "eq", "value": "测试客户_罗彦卓_已更新"}
        #         ],
        #         "filter_relation": "AND",
        #     },
        # ),
    ]
    compute_cases = [
        (
            "compute_count_all",
            {
                "dimensions": [],
                "metrics": [{"agg": "count_all", "as": "customer_count"}],
                "filters": [{"field": "salesEmpName", "op": "eq", "value": "罗彦卓"}],
                "limit": 10,
            },
        )
    ]

    with InvocationContext(tenant_id="t1", user_id="0027024630", language=""):
        for case_name, payload in query_cases:
            print(f"\n===== dynamic query case: {case_name} =====")
            print("payload:", payload)
            result = await obj.invoke_action("query_by_customer", payload)
            print("result:", result)

        # for case_name, payload in compute_cases:
        #     print(f"\n===== dynamic compute case: {case_name} =====")
        #     print("payload:", payload)
        #     result = await obj.invoke_action("compute_by_customer", payload)
        #     print("result:", result)

        # for action_code, case_name, payload in operation_cases:
        #     print(f"\n===== dynamic operation case: {case_name} =====")
        #     print("action:", action_code)
        #     print("payload:", payload)
        #     if action_code == "delete_by_customer":
        #         print("skip execute delete_by_customer by default; remove guard to run it.")
        #         continue
        #     result = await obj.invoke_action(action_code, payload)
        #     print("result:", result)


def _schema_enum_values(schema: object) -> list[str]:
    if not isinstance(schema, dict):
        return []
    items = schema.get("items")
    if not isinstance(items, dict):
        return []
    values = items.get("enum")
    if not isinstance(values, list):
        return []
    return [str(value) for value in values]


def _sample_value_for_schema(schema: object) -> object:
    if not isinstance(schema, dict):
        return "北京国投中债资产管理有限公司"
    schema_type = schema.get("type")
    if schema_type == "integer":
        return 1
    if schema_type == "number":
        return 1.0
    if schema_type == "boolean":
        return True
    if schema_type == "array":
        return ["北京国投中债资产管理有限公司"]
    if schema_type == "object":
        return {}
    return "北京国投中债资产管理有限公司"


if __name__ == "__main__":
    asyncio.run(main10())
