"""
OQL 路由层

职责：
1. JSON Schema 校验
2. 执行模式判断（Pipeline / 跨源 / 单源）
3. 策略分派
"""

from __future__ import annotations
import logging
from typing import Any
import sys

if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal

from datacloud_data_sdk.oql.adapter import OqlAdapter, resolve_object, route_by_source_type
from datacloud_data_sdk.oql.cross_source_executor import CrossSourceExecutor
from datacloud_data_sdk.oql.pipeline_executor import PipelineExecutor
from datacloud_data_sdk.oql.models import OQLError, OQLErrorCode

logger = logging.getLogger(__name__)


class OqlRouter:
    """OQL 路由器"""

    def __init__(self, registry):
        self.registry = registry
        self.adapter = OqlAdapter()
        self.cross_source_executor = CrossSourceExecutor()
        self.pipeline_executor = PipelineExecutor()

    def route(
        self,
        oql_params: dict | list,
        term_resolver,
        executor,
        datasource_registry
    ) -> list[dict]:
        """
        路由 OQL 请求到对应的执行策略。

        Args:
            oql_params: OQL 参数（dict 或 list）
            term_resolver: 术语解析器
            executor: 执行器
            datasource_registry: 数据源注册表

        Returns:
            查询结果列表

        Raises:
            OQLError: 执行失败
        """
        # 1. 类型判断：Pipeline vs 单步
        if isinstance(oql_params, list):
            # Pipeline 模式
            logger.debug("OQL 路由：Pipeline 模式，步骤数 %d", len(oql_params))
            context = self.pipeline_executor.execute(
                oql_params, self.registry, term_resolver, executor, datasource_registry
            )
            # 返回最后一步的结果
            if context:
                last_step_id = list(context.keys())[-1]
                return context[last_step_id].get("records", [])
            return []

        # 2. 单步模式：判断执行策略
        return self.execute_single_step(oql_params, term_resolver, executor, datasource_registry)

    def execute_single_step(
        self,
        oql_params: dict,
        term_resolver,
        executor,
        datasource_registry
    ) -> list[dict]:
        """
        执行单个 OQL 步骤。

        Args:
            oql_params: OQL 参数
            term_resolver: 术语解析器
            executor: 执行器
            datasource_registry: 数据源注册表

        Returns:
            查询结果列表
        """
        # 1. JSON Schema 校验
        self._validate_oql_params(oql_params)

        # 2. 对象解析 + 前置校验
        object_code = oql_params.get("object")
        cls = resolve_object(object_code, self.registry)

        # 前置校验
        if cls.source_type == "API":
            if oql_params.get("metrics"):
                raise OQLError(
                    OQLErrorCode.OQL_ERR_UNSUPPORTED_OPERATION,
                    f"API 对象 '{object_code}' 不支持 metrics 聚合"
                )
            if oql_params.get("include_links"):
                raise OQLError(
                    OQLErrorCode.OQL_ERR_UNSUPPORTED_OPERATION,
                    f"API 对象 '{object_code}' 不支持 include_links 关联"
                )

        # 3. 路由判断：跨源 vs 单源
        include_links = oql_params.get("include_links", [])
        if include_links and cls.source_type == "DB":
            from datacloud_data_sdk.oql.cross_source_executor import classify_include_links
            same_source, cross_source = classify_include_links(
                include_links, cls, self.registry
            )
            if cross_source:
                # 策略 B：跨源执行
                logger.debug("OQL 路由：策略 B（跨源执行）")
                return self.cross_source_executor.execute(
                    oql_params, cls, self.registry, term_resolver, executor, datasource_registry
                )

        # 策略 A：单源执行
        logger.debug("OQL 路由：策略 A（单源执行）")
        db_type = self._get_db_type(cls, datasource_registry)
        task = self.adapter.translate(oql_params, self.registry, term_resolver, db_type)

        # 执行任务
        result = executor.run(task)
        return result if isinstance(result, list) else [result]

    def _validate_oql_params(self, oql_params: dict) -> None:
        """
        校验 OQL 参数的合法性。

        Args:
            oql_params: OQL 参数字典

        Raises:
            OQLError: 参数不合法
        """
        # 必需字段
        if "object" not in oql_params:
            raise OQLError(
                OQLErrorCode.OQL_ERR_INVALID_OPERATOR,
                "缺少必需字段：object"
            )

        # fields 校验
        if "fields" in oql_params:
            fields = oql_params["fields"]
            if not isinstance(fields, list):
                raise OQLError(
                    OQLErrorCode.OQL_ERR_INVALID_OPERATOR,
                    "fields 必须是数组"
                )

        # where 校验
        if "where" in oql_params:
            where = oql_params["where"]
            if not isinstance(where, list):
                raise OQLError(
                    OQLErrorCode.OQL_ERR_INVALID_OPERATOR,
                    "where 必须是数组"
                )

        # include_links 校验
        if "include_links" in oql_params:
            include_links = oql_params["include_links"]
            if not isinstance(include_links, list):
                raise OQLError(
                    OQLErrorCode.OQL_ERR_INVALID_OPERATOR,
                    "include_links 必须是数组"
                )
            for link in include_links:
                if "path" not in link:
                    raise OQLError(
                        OQLErrorCode.OQL_ERR_INVALID_OPERATOR,
                        "include_links 中每个元素必须包含 path 字段"
                    )

        # metrics 校验
        if "metrics" in oql_params:
            metrics = oql_params["metrics"]
            if not isinstance(metrics, list):
                raise OQLError(
                    OQLErrorCode.OQL_ERR_INVALID_OPERATOR,
                    "metrics 必须是数组"
                )

        # group_by 校验
        if "group_by" in oql_params:
            group_by = oql_params["group_by"]
            if not isinstance(group_by, list):
                raise OQLError(
                    OQLErrorCode.OQL_ERR_INVALID_OPERATOR,
                    "group_by 必须是数组"
                )

        # limit 校验
        if "limit" in oql_params:
            limit = oql_params["limit"]
            if not isinstance(limit, int) or limit <= 0:
                raise OQLError(
                    OQLErrorCode.OQL_ERR_INVALID_OPERATOR,
                    "limit 必须是正整数"
                )

        # offset 校验
        if "offset" in oql_params:
            offset = oql_params["offset"]
            if not isinstance(offset, int) or offset < 0:
                raise OQLError(
                    OQLErrorCode.OQL_ERR_INVALID_OPERATOR,
                    "offset 必须是非负整数"
                )


    def _get_db_type(self, cls: Any, datasource_registry) -> str:
        """获取数据库类型。"""
        if cls.source_type == "API":
            return "API"

        datasource_alias = cls.datasource_alias
        if not datasource_alias:
            return "MYSQL"  # 默认

        try:
            ds = datasource_registry.get(datasource_alias)
            if ds and hasattr(ds, 'db_type'):
                return ds.db_type.upper()
        except Exception:
            pass

        return "MYSQL"  # 默认
