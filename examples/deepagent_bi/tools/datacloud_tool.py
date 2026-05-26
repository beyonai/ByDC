"""dataCloud Query Tool — 封装 (resource_code, resource_type, question) 接口。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_loader: Any = None


def _get_loader(resource_dir: Path) -> Any:
    """懒加载 OntologyLoader 单例，首次调用时初始化。"""
    global _loader  # noqa: PLW0603
    if _loader is None:
        import os  # noqa: PLC0415

        from datacloud_analysis.tools.ontology_tool_loader import configure_loader  # noqa: PLC0415
        from datacloud_data_sdk.ontology.loader import OntologyLoader  # noqa: PLC0415
        from datacloud_data_service.tools.virtual_action_injector import (  # noqa: PLC0415
            inject_virtual_actions,
        )

        loader = OntologyLoader()
        loader.load_from_owl_resource_directory(str(resource_dir))
        inject_virtual_actions(loader)

        configure_loader(
            loader=loader,
            model=os.environ.get("DATACLOUD_LLM_MODEL") or os.environ.get("LLM_MODEL", ""),
            base_url=os.environ.get("DATACLOUD_LLM_URL") or os.environ.get("LLM_URL") or None,
            api_key=os.environ.get("DATACLOUD_LLM_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", ""),
            temperature=float(os.environ.get("DEMO_TEMPERATURE", "0")),
            sql_execution_mode="http_sql",
            sql_execute_url=os.environ.get("DEMO_SQL_EXECUTE_URL") or None,
        )
        _loader = loader
    return _loader


def build_datacloud_tool(resource_dir: Path):  # type: ignore[return]
    """构建 dataCloud 查询 Tool。

    Args:
        resource_dir: OWL resource 根目录（含 object/ 和 view/ 子目录）。
    """
    loader = _get_loader(resource_dir)

    @tool
    async def datacloud_query(
        resource_code: str,
        resource_type: Literal["object", "view"],
        question: str,
    ) -> str:
        """对指定本体对象或视图执行自然语言数据查询。

        先调用 ontology_search 找到 resource_code 和 resource_type，再调用本工具。

        Args:
            resource_code: 本体对象或视图的编码，如 "by_customer"
            resource_type: 资源类型，"object" 或 "view"
            question: 自然语言查询问题，如"查询前10条客户数据"
        """
        try:
            from datacloud_data_sdk.context import InvocationContext  # noqa: PLC0415

            user_code = os.environ.get("USER_CODE", "")
            token = os.environ.get("BEYOND_TOKEN", "")
            with InvocationContext(
                user_id=user_code,
                token=token,
                extras={"user_code": user_code},
            ):
                if resource_type == "view":
                    entity = loader.get_view(resource_code)
                else:
                    entity = loader.get_object(resource_code)
                result = await entity.query(question=question)
            return str(result)
        except Exception as exc:  # noqa: BLE001
            logger.error("datacloud_query 失败 (%s/%s): %s", resource_type, resource_code, exc)
            return f"查询失败：{exc}"

    return datacloud_query
