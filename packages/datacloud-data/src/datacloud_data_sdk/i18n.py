"""Lightweight i18n helpers for DataCloud SDK runtime messages."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

DEFAULT_LANGUAGE: Final[str] = "zh_CN"
SUPPORTED_LANGUAGES: Final[frozenset[str]] = frozenset({"zh_CN", "en_US"})

_LANGUAGE_ALIASES: Final[dict[str, str]] = {
    "zh": "zh_CN",
    "zh_cn": "zh_CN",
    "zh-cn": "zh_CN",
    "cn": "zh_CN",
    "chinese": "zh_CN",
    "en": "en_US",
    "en_us": "en_US",
    "en-us": "en_US",
    "english": "en_US",
}


def normalize_language(language: str | None) -> str:
    """Normalize language aliases to supported DataCloud language codes."""
    raw = str(language or "").strip()
    if not raw:
        return DEFAULT_LANGUAGE
    first_token = raw.split(",", 1)[0].split(";", 1)[0].strip()
    if not first_token:
        return DEFAULT_LANGUAGE
    raw = first_token
    if raw in SUPPORTED_LANGUAGES:
        return raw
    return _LANGUAGE_ALIASES.get(raw.lower(), DEFAULT_LANGUAGE)


def is_english(language: str | None) -> bool:
    """Return whether the normalized language is English."""
    return normalize_language(language) == "en_US"


def localized_text(language: str | None, *, zh_cn: str, en_us: str) -> str:
    """Select localized text by language."""
    return en_us if is_english(language) else zh_cn


def format_invocation_context_not_set(language: str | None = None) -> str:
    return localized_text(
        language,
        zh_cn="未设置 InvocationContext。请使用 `with InvocationContext(...):`",
        en_us="InvocationContext is not set. Use `with InvocationContext(...):`",
    )


def format_tenant_id_required(language: str | None = None) -> str:
    return localized_text(
        language,
        zh_cn="X-Tenant-Id 必填",
        en_us="X-Tenant-Id is required",
    )


def format_loader_not_initialized(language: str | None = None) -> str:
    return localized_text(
        language,
        zh_cn="OntologyLoader 未初始化 (OntologyLoader not initialized)",
        en_us="OntologyLoader not initialized",
    )


def format_file_not_found(language: str | None = None) -> str:
    return localized_text(
        language,
        zh_cn="文件未找到或 file_id 无效",
        en_us="File not found or invalid file_id",
    )


def format_use_post_for_jsonrpc(language: str | None = None) -> str:
    return localized_text(
        language,
        zh_cn="请使用 POST 发送 JSON-RPC 消息",
        en_us="Use POST for JSON-RPC messages",
    )


def format_method_not_found(language: str | None, method: str) -> str:
    return localized_text(
        language,
        zh_cn=f"未找到方法：{method}",
        en_us=f"Method not found: {method}",
    )


def format_unknown_tool(language: str | None, tool_name: str) -> str:
    return localized_text(
        language,
        zh_cn=f"未找到工具：{tool_name} (Unknown tool: {tool_name})",
        en_us=f"Unknown tool: {tool_name}",
    )


def format_input_validation_error(language: str | None, detail: str) -> str:
    return localized_text(
        language,
        zh_cn=f"输入校验失败：{detail}",
        en_us=f"Input validation error: {detail}",
    )


def format_auto_view_name(language: str | None = None) -> str:
    return localized_text(
        language,
        zh_cn="自动视图",
        en_us="Auto view",
    )


def format_plan_prompt_current_time(language: str | None, now: str) -> str:
    return localized_text(
        language,
        zh_cn=f"## 当前时间：\n{now}\n",
        en_us=f"## Current time:\n{now}\n",
    )


def format_plan_prompt_object_view(language: str | None, object_view_json: str) -> str:
    return localized_text(
        language,
        zh_cn=f"## 输入内容\n\n**对象视图：**\n{object_view_json}",
        en_us=f"## Input\n\n**Object view:**\n{object_view_json}",
    )


def format_plan_prompt_question(language: str | None, question: str) -> str:
    return localized_text(
        language,
        zh_cn=f"\n**用户问题：**\n{question}",
        en_us=f"\n**User question:**\n{question}",
    )


def format_plan_prompt_knowledge_context(language: str | None, knowledge_context: str) -> str:
    return localized_text(
        language,
        zh_cn=f"\n**知识增强上下文（可选）：**\n{knowledge_context.strip()}",
        en_us=f"\n**Knowledge context (optional):**\n{knowledge_context.strip()}",
    )


def format_plan_prompt_instruction(language: str | None = None) -> str:
    return localized_text(
        language,
        zh_cn="\n请直接输出 QueryExecutionPlan 的 JSON，不要输出其他内容。",
        en_us=(
            "\nOutput only the QueryExecutionPlan JSON. "
            "If canAnswer is false, write clarification in English."
        ),
    )


def _format_available_entries(
    entries: Sequence[dict[str, Any]],
    *,
    show_aliases: bool,
    language: str | None,
) -> list[str]:
    lines: list[str] = []
    for index, entry in enumerate(entries, 1):
        aliases = entry.get("aliases") or []
        aliases_text = ""
        if show_aliases and aliases:
            alias_label = "aliases" if is_english(language) else "别名"
            aliases_text = f" ({alias_label}: {', '.join(str(alias) for alias in aliases)})"
        lines.append(f"  {index}. [{entry['code']}] {entry['label']}{aliases_text}")
    return lines


def format_term_not_found(
    language: str | None,
    term_set: str,
    value: str,
    available_values: list[str] | None = None,
    available_entries: list[dict[str, Any]] | None = None,
) -> str:
    lines = [
        localized_text(
            language,
            zh_cn=f"值「{value}」不存在。",
            en_us=f"Value {value!r} was not found.",
        )
    ]
    if available_entries:
        entries = available_entries[:10]
        header = localized_text(language, zh_cn="可选值: ", en_us="Available values: ")
        formatted_entries = _format_available_entries(entries, show_aliases=True, language=language)
        if formatted_entries:
            lines.append(header + formatted_entries[0])
            lines.extend(formatted_entries[1:])
        if len(available_entries) > 10:
            lines[-1] += localized_text(
                language,
                zh_cn=f"... 等共 {len(available_entries)} 个",
                en_us=f"... and {len(available_entries)} total",
            )
    elif available_values:
        values = available_values[:10]
        prefix = localized_text(language, zh_cn="可选值: ", en_us="Available values: ")
        lines.append(prefix + ", ".join(values))
        if len(available_values) > 10:
            lines[-1] += localized_text(
                language,
                zh_cn=f"... 等共 {len(available_values)} 个",
                en_us=f"... and {len(available_values)} total",
            )
    else:
        lines.append(
            localized_text(
                language,
                zh_cn=f"术语集: {term_set}",
                en_us=f"Term set: {term_set}",
            )
        )
    return "\n".join(lines)


def format_term_ambiguous(
    language: str | None,
    term_set: str,
    value: str,
    matches: list[dict[str, Any]],
) -> str:
    lines = [
        localized_text(
            language,
            zh_cn=f"值「{value}」匹配到多个结果，请选择其中一个:",
            en_us=f"Value {value!r} matched multiple results. Please choose one:",
        )
    ]
    lines.extend(_format_available_entries(matches, show_aliases=True, language=language))
    return "\n".join(lines)


def format_object_not_found(language: str | None, object_code: str) -> str:
    return localized_text(
        language,
        zh_cn=f"未找到对象：{object_code}",
        en_us=f"Object not found: {object_code!r}",
    )


def format_action_not_found(language: str | None, object_code: str, action_code: str) -> str:
    return localized_text(
        language,
        zh_cn=f"对象 {object_code!r} 上未找到动作 {action_code!r}",
        en_us=f"Action {action_code!r} not found on {object_code!r}",
    )


def format_invalid_ontology(language: str | None, path: str, reason: str) -> str:
    return localized_text(
        language,
        zh_cn=f"无效的本体文件 {path!r}: {reason}",
        en_us=f"Invalid ontology at {path!r}: {reason}",
    )


def format_plan_generation(language: str | None, question: str, cause: str) -> str:
    return localized_text(
        language,
        zh_cn=f"计划生成失败：{question!r}，原因：{cause}",
        en_us=f"Plan generation failed for {question!r}: {cause}",
    )


def format_plan_validation(language: str | None, errors: list[str]) -> str:
    return localized_text(
        language,
        zh_cn=f"计划验证失败：{errors}",
        en_us=f"Plan validation failed: {errors}",
    )


def format_cannot_answer(language: str | None, clarification: str) -> str:
    return localized_text(language, zh_cn=clarification, en_us=clarification)


def format_api_execution(
    language: str | None,
    function_code: str,
    status_code: int,
    body: str,
) -> str:
    return localized_text(
        language,
        zh_cn=f"API {function_code!r} 调用失败 [{status_code}]: {body}",
        en_us=f"API {function_code!r} failed [{status_code}]: {body}",
    )


def format_sql_execution(
    language: str | None,
    datasource_alias: str,
    sql: str,
    cause: str,
) -> str:
    return localized_text(
        language,
        zh_cn=f"SQL 在 {datasource_alias!r} 上执行失败：{cause}\nSQL: {sql}",
        en_us=f"SQL failed on {datasource_alias!r}: {cause}\nSQL: {sql}",
    )


def format_kb_execution(language: str | None, datasource_alias: str, cause: str) -> str:
    return localized_text(
        language,
        zh_cn=f"知识库在 {datasource_alias!r} 上执行失败：{cause}",
        en_us=f"KB execution failed on {datasource_alias!r}: {cause}",
    )


def format_script_execution(
    language: str | None,
    action_code: str,
    cause: str,
    line_no: int | None = None,
) -> str:
    loc = ""
    if line_no:
        loc = localized_text(
            language,
            zh_cn=f"（行 {line_no}）",
            en_us=f" (line {line_no})",
        )
    return localized_text(
        language,
        zh_cn=f"脚本 {action_code!r} 执行失败{loc}：{cause}",
        en_us=f"Script {action_code!r} failed{loc}: {cause}",
    )


def format_action_not_configured(language: str | None, action_code: str) -> str:
    return localized_text(
        language,
        zh_cn=f"动作 {action_code!r} 未配置脚本或 function_refs",
        en_us=f"Action {action_code!r} has neither script nor function_refs",
    )


def format_permission_not_configured(language: str | None = None) -> str:
    return localized_text(
        language,
        zh_cn="未配置权限提供器",
        en_us="Permission provider is not configured",
    )


def format_permission_denied(
    language: str | None,
    resource: str,
    detail: str,
) -> str:
    return localized_text(
        language,
        zh_cn=f"资源 {resource!r} 权限被拒绝：{detail}",
        en_us=f"Permission denied for {resource!r}: {detail}",
    )


def format_datasource_unavailable(language: str | None, alias: str) -> str:
    return localized_text(
        language,
        zh_cn=f"数据源不可用：{alias!r}",
        en_us=f"Datasource unavailable: {alias!r}",
    )


def format_step_dependency(language: str | None, step_id: str, depends_on: str) -> str:
    return localized_text(
        language,
        zh_cn=f"步骤 {step_id!r} 依赖缺失的步骤 {depends_on!r}",
        en_us=f"Step {step_id!r} depends on {depends_on!r} which is missing",
    )


def format_aggregation(language: str | None, strategy: str, sql: str, cause: str) -> str:
    return localized_text(
        language,
        zh_cn=f"聚合 [{strategy}] 失败：{cause}\nSQL: {sql}",
        en_us=f"Aggregation [{strategy}] failed: {cause}\nSQL: {sql}",
    )


def format_overflow_notice(
    *,
    language: str | None,
    total: int,
    preview_count: int,
    file_path: str | None = None,
    download_url: str | None = None,
) -> str:
    """Build a localized large-result notice."""
    if download_url:
        return localized_text(
            language,
            zh_cn=(
                f"【重要】数据量较大（共 {total} 条），此处仅返回前 {preview_count} 条预览。"
                f"完整数据请通过以下地址下载 CSV：{download_url}"
            ),
            en_us=(
                f"Important: the result is large ({total} rows). "
                f"Only the first {preview_count} rows are returned here. "
                f"Download the full CSV here: {download_url}"
            ),
        )

    resolved_path = file_path or ""
    return localized_text(
        language,
        zh_cn=(
            f"【重要】数据量较大（共 {total} 条），此处仅返回前 {preview_count} 条预览。"
            f"完整数据请通过以下文件路径获取：{resolved_path}"
        ),
        en_us=(
            f"Important: the result is large ({total} rows). "
            f"Only the first {preview_count} rows are returned here. "
            f"Read the full data from this file path: {resolved_path}"
        ),
    )


def translate_exception(exception: Exception, language: str | None = None) -> str:
    """Render a localized message for a datacloud exception."""
    from datacloud_data_sdk.exceptions import (
        ActionNotConfiguredError,
        ActionNotFoundError,
        AggregationError,
        ApiExecutionError,
        CannotAnswerError,
        DataSourceUnavailableError,
        InvalidOntologyFormatError,
        KbExecutionError,
        ObjectNotFoundError,
        PermissionDeniedError,
        PermissionNotConfiguredError,
        PlanGenerationError,
        PlanValidationError,
        ScriptExecutionError,
        SqlExecutionError,
        StepDependencyError,
        TermAmbiguousError,
        TermNotFoundError,
    )

    if isinstance(exception, ObjectNotFoundError):
        return format_object_not_found(language, exception.object_code)
    if isinstance(exception, ActionNotFoundError):
        return format_action_not_found(language, exception.object_code, exception.action_code)
    if isinstance(exception, InvalidOntologyFormatError):
        return format_invalid_ontology(language, exception.path, exception.reason)
    if isinstance(exception, TermNotFoundError):
        return format_term_not_found(
            language,
            exception.term_set,
            exception.value,
            exception.available_values,
            exception.available_entries,
        )
    if isinstance(exception, TermAmbiguousError):
        return format_term_ambiguous(
            language, exception.term_set, exception.value, exception.matches
        )
    if isinstance(exception, PlanGenerationError):
        return format_plan_generation(language, exception.question, exception.cause)
    if isinstance(exception, PlanValidationError):
        return format_plan_validation(language, exception.errors)
    if isinstance(exception, CannotAnswerError):
        return format_cannot_answer(language, exception.clarification)
    if isinstance(exception, ApiExecutionError):
        return format_api_execution(
            language,
            exception.function_code,
            exception.status_code,
            exception.body,
        )
    if isinstance(exception, SqlExecutionError):
        return format_sql_execution(
            language,
            exception.datasource_alias,
            exception.sql,
            exception.cause,
        )
    if isinstance(exception, KbExecutionError):
        return format_kb_execution(language, exception.datasource_alias, exception.cause)
    if isinstance(exception, ScriptExecutionError):
        return format_script_execution(
            language,
            exception.action_code,
            exception.cause,
            exception.line_no,
        )
    if isinstance(exception, ActionNotConfiguredError):
        return format_action_not_configured(language, exception.action_code)
    if isinstance(exception, PermissionNotConfiguredError):
        return format_permission_not_configured(language)
    if isinstance(exception, PermissionDeniedError):
        detail = exception.message or exception.reason_code
        return format_permission_denied(language, exception.resource, detail)
    if isinstance(exception, DataSourceUnavailableError):
        return format_datasource_unavailable(language, exception.alias)
    if isinstance(exception, StepDependencyError):
        return format_step_dependency(language, exception.step_id, exception.depends_on)
    if isinstance(exception, AggregationError):
        return format_aggregation(language, exception.strategy, exception.sql, exception.cause)
    return str(exception)
