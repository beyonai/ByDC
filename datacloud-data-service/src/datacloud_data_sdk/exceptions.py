"""datacloud-data-sdk 结构化异常层次。"""

from __future__ import annotations


class DatacloudError(Exception):
    """SDK 所有异常的基类。"""


# --- 本体层 ---


class OntologyError(DatacloudError):
    """本体解析与查询相关错误。"""


class ObjectNotFoundError(OntologyError):
    def __init__(self, object_code: str) -> None:
        super().__init__(f"Object not found: {object_code!r}")
        self.object_code = object_code


class ActionNotFoundError(OntologyError):
    def __init__(self, object_code: str, action_code: str) -> None:
        super().__init__(f"Action {action_code!r} not found on {object_code!r}")
        self.object_code = object_code
        self.action_code = action_code


class InvalidOntologyFormatError(OntologyError):
    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"Invalid ontology at {path!r}: {reason}")
        self.path = path
        self.reason = reason


# --- 计划层 ---


class PlanError(DatacloudError):
    """查询计划相关错误。"""


class PlanGenerationError(PlanError):
    def __init__(self, question: str, cause: str) -> None:
        super().__init__(f"Plan generation failed for {question!r}: {cause}")
        self.question = question
        self.cause = cause


class PlanValidationError(PlanError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__(f"Plan validation failed: {errors}")
        self.errors = errors


class CannotAnswerError(PlanError):
    def __init__(self, clarification: str) -> None:
        super().__init__(clarification)
        self.clarification = clarification


# --- 执行层 ---


class ExecutionError(DatacloudError):
    """执行层错误基类。"""


class ApiExecutionError(ExecutionError):
    def __init__(self, function_code: str, status_code: int, body: str) -> None:
        super().__init__(f"API {function_code!r} failed [{status_code}]: {body}")
        self.function_code = function_code
        self.status_code = status_code
        self.body = body


class SqlExecutionError(ExecutionError):
    def __init__(self, datasource_alias: str, sql: str, cause: str) -> None:
        super().__init__(f"SQL failed on {datasource_alias!r}: {cause}\nSQL: {sql}")
        self.datasource_alias = datasource_alias
        self.sql = sql
        self.cause = cause


class KbExecutionError(ExecutionError):
    def __init__(self, datasource_alias: str, cause: str) -> None:
        super().__init__(f"KB execution failed on {datasource_alias!r}: {cause}")
        self.datasource_alias = datasource_alias
        self.cause = cause


class ScriptExecutionError(ExecutionError):
    def __init__(self, action_code: str, cause: str, line_no: int | None = None) -> None:
        loc = f" (line {line_no})" if line_no else ""
        super().__init__(f"Script {action_code!r} failed{loc}: {cause}")
        self.action_code = action_code
        self.cause = cause
        self.line_no = line_no


class ActionNotConfiguredError(ExecutionError):
    def __init__(self, action_code: str) -> None:
        super().__init__(f"Action {action_code!r} has neither script nor function_refs")
        self.action_code = action_code


class DataSourceUnavailableError(ExecutionError):
    def __init__(self, alias: str) -> None:
        super().__init__(f"Datasource unavailable: {alias!r}")
        self.alias = alias


class StepDependencyError(ExecutionError):
    def __init__(self, step_id: str, depends_on: str) -> None:
        super().__init__(f"Step {step_id!r} depends on {depends_on!r} which is missing")
        self.step_id = step_id
        self.depends_on = depends_on


# --- 聚合层 ---


class AggregationError(DatacloudError):
    def __init__(self, strategy: str, sql: str, cause: str) -> None:
        super().__init__(f"Aggregation [{strategy}] failed: {cause}\nSQL: {sql}")
        self.strategy = strategy
        self.sql = sql
        self.cause = cause
