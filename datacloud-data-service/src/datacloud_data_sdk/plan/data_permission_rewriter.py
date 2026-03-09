"""DataPermissionRewriter: 注入数据权限条件到 SQL。"""
from __future__ import annotations

import re

from datacloud_data_sdk.plan.models import PlanStep, QueryExecutionPlan
from datacloud_data_sdk.context import RequestContext


class DataPermissionRewriter:
    """将 tenant_id 等权限条件注入到 SQL 步骤的 WHERE 子句中。

    MVP 阶段仅注入 tenant_id，后续可扩展行级权限。
    """

    def rewrite(self, plan: QueryExecutionPlan, context: RequestContext) -> QueryExecutionPlan:
        if not context.tenant_id:
            return plan

        rewritten_steps = [
            self._rewrite_step(step, context) for step in plan.steps
        ]
        return QueryExecutionPlan(
            question=plan.question,
            can_answer=plan.can_answer,
            clarification=plan.clarification,
            steps=rewritten_steps,
            aggregation=plan.aggregation,
        )

    def _rewrite_step(self, step: PlanStep, context: RequestContext) -> PlanStep:
        if step.type != "SQL" or not step.sql_template:
            return step

        sql = self._inject_tenant_id(step.sql_template, context.tenant_id)
        return PlanStep(
            step_id=step.step_id,
            type=step.type,
            source_id=step.source_id,
            datasource_alias=step.datasource_alias,
            sql_template=sql,
            function_id=step.function_id,
            params=step.params,
            output_ref=step.output_ref,
            csv_table_name=step.csv_table_name,
            bind_from_step=step.bind_from_step,
            bind_key=step.bind_key,
            script=step.script,
            action_code=step.action_code,
        )

    def _inject_tenant_id(self, sql: str, tenant_id: str) -> str:
        """在 SQL 的 WHERE 子句中追加 tenant_id 条件。

        仅对含 FROM 子句的 SQL 注入。
        已有 WHERE → 追加 AND tenant_id = 'xxx'。
        无 WHERE → 在 GROUP BY/ORDER BY/LIMIT 前插入。
        """
        if not re.search(r'\bFROM\b', sql, re.IGNORECASE):
            return sql

        condition = f"tenant_id = '{tenant_id}'"

        if re.search(r'\bWHERE\b', sql, re.IGNORECASE):
            sql = re.sub(
                r'(\bWHERE\b\s+)',
                rf'\g<1>{condition} AND ',
                sql,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            match = re.search(
                r'\b(GROUP\s+BY|ORDER\s+BY|LIMIT|HAVING)\b',
                sql,
                re.IGNORECASE,
            )
            if match:
                pos = match.start()
                sql = sql[:pos] + f" WHERE {condition} " + sql[pos:]
            else:
                sql = sql.rstrip() + f" WHERE {condition}"

        return sql
