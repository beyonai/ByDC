"""
OQL Pipeline 执行器（策略 C）

职责：
1. 多步顺序执行
2. $ref 表达式解析
3. 步骤间结果传递
"""

from __future__ import annotations
import logging
import re
from typing import Any
import sys

if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal

from datacloud_data_sdk.oql.models import OQLError, OQLErrorCode

logger = logging.getLogger(__name__)


class RefResolver:
    """$ref 表达式解析器"""

    @staticmethod
    def resolve(params: dict | list, context: dict[str, dict]) -> dict | list:
        """
        解析参数中的 $ref 表达式。

        $ref 语法：
        - {step_id}.result[*].{field} → 去重列表
        - {step_id}.result[N].{field} → 标量值
        - {step_id}.result[*] → 完整记录列表
        - {step_id}.result[N] → 单条记录

        Args:
            params: 参数（可能包含 $ref 表达式）
            context: 步骤执行上下文

        Returns:
            解析后的参数

        Raises:
            OQLError: $ref 表达式无效
        """
        if isinstance(params, dict):
            result = {}
            for k, v in params.items():
                result[k] = RefResolver.resolve(v, context)
            return result

        elif isinstance(params, list):
            return [RefResolver.resolve(item, context) for item in params]

        elif isinstance(params, str):
            # 检查是否为 $ref 表达式：{step_id}.result[*|N](.field)?
            if params.startswith("{") and ".result[" in params:
                return RefResolver._resolve_ref(params, context)
            return params

        else:
            return params

    @staticmethod
    def _resolve_ref(ref_expr: str, context: dict[str, dict]) -> Any:
        """
        解析单个 $ref 表达式。

        Args:
            ref_expr: $ref 表达式（如 "{step1}.result[*].field"）
            context: 步骤执行上下文

        Returns:
            解析结果

        Raises:
            OQLError: 表达式无效或步骤不存在
        """
        # 移除外层 {}（如果存在）
        expr = ref_expr
        if expr.startswith("{") and "}" in expr:
            end_brace = expr.index("}")
            expr = expr[1:end_brace] + expr[end_brace+1:]

        # 解析格式：step_id.result[index].field 或 step_id.result[index]
        match = re.match(r"(\w+)\.result\[([*\d]+)\](?:\.(\w+))?", expr)
        if not match:
            raise OQLError(
                OQLErrorCode.OQL_ERR_INVALID_REF,
                f"无效的 $ref 表达式：{ref_expr}"
            )

        step_id, index_str, field = match.groups()

        # 获取步骤结果
        if step_id not in context:
            raise OQLError(
                OQLErrorCode.OQL_ERR_INVALID_REF,
                f"步骤 '{step_id}' 不存在或未执行"
            )

        records = context[step_id].get("records", [])

        # 处理索引
        if index_str == "*":
            # 返回列表
            if field:
                # 提取字段，去重
                values = []
                seen = set()
                for record in records:
                    val = record.get(field)
                    if val is not None and val not in seen:
                        values.append(val)
                        seen.add(val)
                return values
            else:
                # 返回完整记录列表
                return records
        else:
            # 返回单条记录
            try:
                idx = int(index_str)
                if idx >= len(records):
                    raise OQLError(
                        OQLErrorCode.OQL_ERR_INVALID_REF,
                        f"索引 {idx} 超出范围（共 {len(records)} 条记录）"
                    )
                record = records[idx]
                if field:
                    return record.get(field)
                else:
                    return record
            except ValueError:
                raise OQLError(
                    OQLErrorCode.OQL_ERR_INVALID_REF,
                    f"无效的索引：{index_str}"
                )


class PipelineExecutor:
    """Pipeline 执行器"""

    MAX_STEPS = 10

    async def execute(
        self,
        steps: list[dict],
        registry,
        term_resolver,
        executor,
        datasource_registry,
        request_id: str
    ) -> dict[str, dict]:
        """
        顺序执行 Pipeline 步骤。

        Args:
            steps: 步骤列表
            registry: 本体注册表
            term_resolver: 术语解析器
            executor: 执行器
            datasource_registry: 数据源注册表
            request_id: 请求 ID

        Returns:
            步骤执行结果字典 {step_id: {records: [...]}}

        Raises:
            OQLError: 步骤执行失败
        """
        if len(steps) > self.MAX_STEPS:
            raise OQLError(
                OQLErrorCode.OQL_ERR_STEP_LIMIT_EXCEEDED,
                f"Pipeline 最多支持 {self.MAX_STEPS} 步，当前 {len(steps)} 步"
            )

        context: dict[str, dict] = {}

        # 延迟导入以避免循环依赖
        from datacloud_data_sdk.oql.router import OqlRouter
        router = OqlRouter(registry)

        for step in steps:
            step_id = step.get("step_id")
            parameters = step.get("parameters", {})

            logger.debug("Pipeline 执行步骤：%s", step_id)

            try:
                # 解析 $ref 表达式
                resolved_params = RefResolver.resolve(parameters, context)
            except OQLError as e:
                raise OQLError(
                    e.code,
                    f"步骤 '{step_id}' 的 $ref 解析失败：{e.message}",
                    details=e.details
                )

            try:
                # 执行步骤
                records = await router.execute_single_step(
                    resolved_params, term_resolver, executor, datasource_registry, request_id
                )
            except OQLError as e:
                raise OQLError(
                    e.code,
                    f"步骤 '{step_id}' 执行失败：{e.message}",
                    details=e.details
                )

            # 保存步骤结果
            context[step_id] = {"records": records}

        return context
