import sys

sys.path.insert(0, "src")

import asyncio
from pathlib import Path

from datacloud_data_sdk import InvocationContext, OntologyLoader
from datacloud_data_sdk.ontology.term_loader import TermLoader
from datacloud_data_sdk.plan.query_plan_generator import LangGraphPlanGenerator

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(
    Path(
        "/Users/zouhaitian/Documents/workplace/project/Haojing/baiyin_ai/whale_datacloud/packages/datacloud-data/.env"
    )
)


async def main1() -> None:
    loader = OntologyLoader()
    loader.load_from_path(
        "/Users/zouhaitian/Documents/workplace/project/Haojing/baiyin_ai/whale_datacloud/examples/e_commerce_demo/mock_env/resource/knowledge/import_package/ontology/e_commerce_scene_01_data_analysis_full.json"
    )
    loader.load_scene_from_path(
        "/Users/zouhaitian/Documents/workplace/project/Haojing/baiyin_ai/whale_datacloud/examples/e_commerce_demo/mock_env/resource/knowledge/import_package/ontology/e_commerce_scene_01_data_analysis_full.json"
    )
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model="Qwen/Qwen3-Coder-30B-Instruct",
            base_url="https://lab.iwhalecloud.com/gpt-proxy/v1",
            api_key="sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf",
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

    loader.load_from_path(
        "/Users/zouhaitian/Documents/workplace/project/Haojing/baiyin_ai/whale_datacloud/examples/e_commerce_demo/mock_env/resource/knowledge/import_package/ontology/e_commerce_scene_01_data_analysis_full.json"
    )
    loader.load_scene_from_path(
        "/Users/zouhaitian/Documents/workplace/project/Haojing/baiyin_ai/whale_datacloud/examples/e_commerce_demo/mock_env/resource/knowledge/import_package/ontology/e_commerce_scene_01_data_analysis_full.json"
    )
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model="Qwen/Qwen3-Coder-30B-Instruct",
            base_url="https://lab.iwhalecloud.com/gpt-proxy/v1",
            api_key="sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf",
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
    loader.load_scene_from_path(
        "/Users/zouhaitian/Documents/workplace/project/Haojing/baiyin_ai/whale_datacloud/examples/e_commerce_demo/mock_env/resource/knowledge/import_package/ontology/e_commerce_scene_01_data_analysis_full.json"
    )
    loader.load_from_path(
        "/Users/zouhaitian/Documents/workplace/project/Haojing/baiyin_ai/whale_datacloud/examples/e_commerce_demo/mock_env/resource/knowledge/import_package/ontology/e_commerce_scene_01_data_analysis_full.json"
    )
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model="Qwen/Qwen3-Coder-30B-Instruct",
            base_url="https://lab.iwhalecloud.com/gpt-proxy/v1",
            api_key="sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf",
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
    loader.load_scene_from_path(
        "/Users/zouhaitian/Documents/workplace/project/Haojing/baiyin_ai/whale_datacloud/examples/e_commerce_demo/mock_env/resource/knowledge/import_package/ontology/e_commerce_scene_01_data_analysis_full.json"
    )
    loader.load_from_path(
        "/Users/zouhaitian/Documents/workplace/project/Haojing/baiyin_ai/whale_datacloud/examples/e_commerce_demo/mock_env/resource/knowledge/import_package/ontology/e_commerce_scene_01_data_analysis_full.json"
    )
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model="Qwen/Qwen3-Coder-30B-Instruct",
            base_url="https://lab.iwhalecloud.com/gpt-proxy/v1",
            api_key="sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf",
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
    loader.load_from_owl_directory(
        "/Users/zouhaitian/Documents/workplace/project/Haojing/baiyin_ai/whale_datacloud/examples/e_commerce_demo/mock_env/resource/knowledge/import_package_owl/"
    )
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model="Qwen/Qwen3-Coder-30B-Instruct",
            base_url="https://lab.iwhalecloud.com/gpt-proxy/v1",
            api_key="sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf",
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


if __name__ == "__main__":
    asyncio.run(main5())
