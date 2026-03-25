"""
异常定义模块

本模块定义了 datacloud-data-sdk 的结构化异常层次结构。
所有异常都继承自 DatacloudError 基类，便于统一捕获和处理。

异常层次：
- DatacloudError: 所有异常的基类
  - OntologyError: 本体层错误
    - ObjectNotFoundError: 对象不存在
    - ActionNotFoundError: 动作不存在
    - InvalidOntologyFormatError: 本体格式无效
    - TermResolutionError: 术语解析错误
      - TermNotFoundError: 术语不存在
      - TermAmbiguousError: 术语匹配到多个结果
  - PlanError: 计划层错误
    - PlanGenerationError: 计划生成失败
    - PlanValidationError: 计划验证失败
    - CannotAnswerError: 无法回答问题
  - ExecutionError: 执行层错误
    - ApiExecutionError: API 执行失败
    - SqlExecutionError: SQL 执行失败
    - KbExecutionError: 知识库执行失败
    - ScriptExecutionError: 脚本执行失败
    - ActionNotConfiguredError: 动作未配置
    - DataSourceUnavailableError: 数据源不可用
    - StepDependencyError: 步骤依赖错误
  - AggregationError: 聚合层错误

使用示例：
    try:
        result = await action.execute(params)
    except ActionNotConfiguredError as e:
        print(f"动作 {e.action_code} 未配置")
    except ApiExecutionError as e:
        print(f"API 调用失败: {e.status_code}")
    except TermNotFoundError as e:
        print(f"术语不存在: {e.value}, 可用值: {e.available_values}")
    except TermAmbiguousError as e:
        print(f"术语歧义，请选择: {e.matches}")
"""

from __future__ import annotations


class DatacloudError(Exception):
    """
    SDK 所有异常的基类
    
    所有 datacloud-data-sdk 抛出的异常都继承此类，
    可以通过捕获 DatacloudError 来统一处理所有 SDK 异常。
    """


class OntologyError(DatacloudError):
    """
    本体解析与查询相关错误的基类
    
    当本体加载、验证或查询过程中发生错误时抛出。
    """


class TermResolutionError(OntologyError):
    """
    术语解析错误基类
    
    当术语解析过程中发生错误时抛出。
    
    Attributes:
        term_set: 术语集
        value: 待解析的值
        param_name: 参数名称（可选）
    """
    
    def __init__(self, term_set: str, value: str, message: str, param_name: str | None = None) -> None:
        super().__init__(message)
        self.term_set = term_set
        self.value = value
        self.param_name = param_name


class TermNotFoundError(TermResolutionError):
    """
    术语未找到异常
    
    当指定的术语值在术语集中不存在时抛出。
    
    Attributes:
        term_set: 术语集
        value: 未找到的值
        available_values: 可用的术语值列表
        available_entries: 可用的术语条目列表，每项包含 code 和 label
        param_name: 参数名称
    """
    
    def __init__(
        self,
        term_set: str,
        value: str,
        available_values: list[str] | None = None,
        param_name: str | None = None,
        available_entries: list[dict[str, str]] | None = None,
    ) -> None:
        self.available_values = available_values
        self.available_entries = available_entries
        lines = [f"值「{value}」不存在。"]
        if available_entries:
            if len(available_entries) <= 10:
                entries_str = ", ".join(f"[{e['code']}] {e['label']}" for e in available_entries)
                lines.append(f"可选值: {entries_str}")
            else:
                entries_str = ", ".join(f"[{e['code']}] {e['label']}" for e in available_entries[:10])
                lines.append(f"可选值: {entries_str}... 等共 {len(available_entries)} 个")
        elif available_values:
            if len(available_values) <= 10:
                lines.append(f"可选值: {', '.join(available_values)}")
            else:
                lines.append(f"可选值: {', '.join(available_values[:10])}... 等共 {len(available_values)} 个")
        else:
            lines.append(f"术语集: {term_set}")
        message = "\n".join(lines)
        super().__init__(term_set, value, message, param_name)


class TermAmbiguousError(TermResolutionError):
    """
    术语歧义异常
    
    当术语值匹配到多个结果时抛出，需要用户选择。
    
    Attributes:
        term_set: 术语集
        value: 有歧义的值
        matches: 匹配到的术语列表，每项包含 code, label, aliases
        param_name: 参数名称
    """
    
    def __init__(
        self,
        term_set: str,
        value: str,
        matches: list[dict[str, str]],
        param_name: str | None = None,
    ) -> None:
        self.matches = matches
        lines = [f"值「{value}」匹配到多个结果，请选择其中一个:"]
        for i, m in enumerate(matches, 1):
            aliases_str = f" (别名: {', '.join(m.get('aliases', []))})" if m.get('aliases') else ""
            lines.append(f"  {i}. [{m['code']}] {m['label']}{aliases_str}")
        message = "\n".join(lines)
        super().__init__(term_set, value, message, param_name)


class ObjectNotFoundError(OntologyError):
    """
    对象不存在异常
    
    当请求的对象代码在本体中不存在时抛出。
    
    Attributes:
        object_code: 未找到的对象代码
    """
    
    def __init__(self, object_code: str) -> None:
        super().__init__(f"Object not found: {object_code!r}")
        self.object_code = object_code


class ActionNotFoundError(OntologyError):
    """
    动作不存在异常
    
    当请求的动作代码在指定对象上不存在时抛出。
    
    Attributes:
        object_code: 对象代码
        action_code: 未找到的动作代码
    """
    
    def __init__(self, object_code: str, action_code: str) -> None:
        super().__init__(f"Action {action_code!r} not found on {object_code!r}")
        self.object_code = object_code
        self.action_code = action_code


class InvalidOntologyFormatError(OntologyError):
    """
    本体格式无效异常
    
    当本体文件格式不符合规范时抛出。
    
    Attributes:
        path: 本体文件路径
        reason: 错误原因描述
    """
    
    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"Invalid ontology at {path!r}: {reason}")
        self.path = path
        self.reason = reason


class PlanError(DatacloudError):
    """
    查询计划相关错误的基类
    
    当计划生成、验证或执行过程中发生错误时抛出。
    """


class PlanGenerationError(PlanError):
    """
    计划生成失败异常
    
    当 LLM 无法生成有效的查询计划时抛出。
    
    Attributes:
        question: 原始问题
        cause: 失败原因
    """
    
    def __init__(self, question: str, cause: str) -> None:
        super().__init__(f"Plan generation failed for {question!r}: {cause}")
        self.question = question
        self.cause = cause


class PlanValidationError(PlanError):
    """
    计划验证失败异常
    
    当生成的查询计划未通过验证时抛出。
    
    Attributes:
        errors: 验证错误列表
        plan: 验证失败的计划对象
    """
    
    def __init__(self, errors: list[str], plan: object = None) -> None:
        super().__init__(f"Plan validation failed: {errors}")
        self.errors = errors
        self.plan = plan


class CannotAnswerError(PlanError):
    """
    无法回答问题异常
    
    当 LLM 判断无法基于现有数据回答问题时抛出，
    通常需要用户提供更多信息或澄清问题。
    
    Attributes:
        clarification: 澄清说明或建议
    """
    
    def __init__(self, clarification: str) -> None:
        super().__init__(clarification)
        self.clarification = clarification


class ExecutionError(DatacloudError):
    """
    执行层错误基类
    
    当查询执行过程中发生错误时抛出。
    """


class ApiExecutionError(ExecutionError):
    """
    API 执行失败异常
    
    当外部 API 调用返回错误时抛出。
    
    Attributes:
        function_code: 函数代码
        status_code: HTTP 状态码
        body: 响应体内容
    """
    
    def __init__(self, function_code: str, status_code: int, body: str) -> None:
        super().__init__(f"API {function_code!r} failed [{status_code}]: {body}")
        self.function_code = function_code
        self.status_code = status_code
        self.body = body


class SqlExecutionError(ExecutionError):
    """
    SQL 执行失败异常
    
    当数据库查询执行失败时抛出。
    
    Attributes:
        datasource_alias: 数据源别名
        sql: 执行的 SQL 语句
        cause: 错误原因
    """
    
    def __init__(self, datasource_alias: str, sql: str, cause: str) -> None:
        super().__init__(f"SQL failed on {datasource_alias!r}: {cause}\nSQL: {sql}")
        self.datasource_alias = datasource_alias
        self.sql = sql
        self.cause = cause


class KbExecutionError(ExecutionError):
    """
    知识库执行失败异常
    
    当知识库查询执行失败时抛出。
    
    Attributes:
        datasource_alias: 数据源别名
        cause: 错误原因
    """
    
    def __init__(self, datasource_alias: str, cause: str) -> None:
        super().__init__(f"KB execution failed on {datasource_alias!r}: {cause}")
        self.datasource_alias = datasource_alias
        self.cause = cause


class ScriptExecutionError(ExecutionError):
    """
    脚本执行失败异常
    
    当动作脚本执行过程中发生错误时抛出。
    
    Attributes:
        action_code: 动作代码
        cause: 错误原因
        line_no: 错误发生的行号（如果有）
    """
    
    def __init__(self, action_code: str, cause: str, line_no: int | None = None) -> None:
        loc = f" (line {line_no})" if line_no else ""
        super().__init__(f"Script {action_code!r} failed{loc}: {cause}")
        self.action_code = action_code
        self.cause = cause
        self.line_no = line_no


class ActionNotConfiguredError(ExecutionError):
    """
    动作未配置异常
    
    当动作既没有配置脚本也没有配置 API 引用时抛出。
    
    Attributes:
        action_code: 动作代码
    """
    
    def __init__(self, action_code: str) -> None:
        super().__init__(f"Action {action_code!r} has neither script nor function_refs")
        self.action_code = action_code


class DataSourceUnavailableError(ExecutionError):
    """
    数据源不可用异常
    
    当请求的数据源不存在或无法连接时抛出。
    
    Attributes:
        alias: 数据源别名
    """
    
    def __init__(self, alias: str) -> None:
        super().__init__(f"Datasource unavailable: {alias!r}")
        self.alias = alias


class StepDependencyError(ExecutionError):
    """
    步骤依赖错误异常
    
    当执行步骤依赖的其他步骤不存在或未完成时抛出。
    
    Attributes:
        step_id: 当前步骤 ID
        depends_on: 依赖的步骤 ID
    """
    
    def __init__(self, step_id: str, depends_on: str) -> None:
        super().__init__(f"Step {step_id!r} depends on {depends_on!r} which is missing")
        self.step_id = step_id
        self.depends_on = depends_on


class AggregationError(DatacloudError):
    """
    聚合层错误异常
    
    当结果聚合过程中发生错误时抛出。
    
    Attributes:
        strategy: 聚合策略名称
        sql: 执行的 SQL 语句
        cause: 错误原因
    """
    
    def __init__(self, strategy: str, sql: str, cause: str) -> None:
        super().__init__(f"Aggregation [{strategy}] failed: {cause}\nSQL: {sql}")
        self.strategy = strategy
        self.sql = sql
        self.cause = cause
