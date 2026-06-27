"""dataCloud Query Tool — 封装 (resource_code, resource_type, question) 接口。"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_loader: Any = None


def _get_loader() -> Any:
    """通过 LoaderRuntimeManager 获取 OntologyLoader 快照。"""
    global _loader  # noqa: PLW0603
    if _loader is None:
        from datacloud_platform import get_platform  # noqa: PLC0415
        from datacloud_platform.config import get_settings  # noqa: PLC0415
        from datacloud_platform.loader_runtime import LoaderRuntimeManager  # noqa: PLC0415

        runtime = LoaderRuntimeManager(platform=get_platform(), settings=get_settings())
        snapshot = runtime.get_loader("default")
        _loader = snapshot.loader
    return _loader


def build_datacloud_tool(_resource_dir: Path) -> Any:
    """构建 dataCloud 查询 Tool。

    Args:
        _resource_dir: OWL resource 根目录 (含 object/ 和 view/ 子目录).
    """
    loader = _get_loader()

    @tool
    async def datacloud_query(
        resource_code: str,
        resource_type: Literal["object", "view"],
        question: str,
    ) -> str:
        """对指定本体对象或视图执行自然语言数据查询。

        先调用 ontology_search 找到 resource_code 和 resource_type, 再调用本工具。

        Args:
            resource_code: 本体对象或视图的编码, 如 "by_customer"
            resource_type: 资源类型, "object" 或 "view"
            question: 自然语言查询问题, 如"查询前10条客户数据"
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
        except Exception as exc:
            logger.exception("datacloud_query 失败 (%s/%s)", resource_type, resource_code)
            return f"查询失败: {exc}"

    return datacloud_query
