"""Built-in hook plugin for operation action confirmation forms."""

from __future__ import annotations

import hashlib
import json
import logging
from copy import deepcopy
from typing import Any

from datacloud_data_sdk.exceptions import TermAmbiguousError, TermNotFoundError

from datacloud_analysis.i18n.prompts import get_ui_text
from datacloud_analysis.tool_hook_plugins.types import (
    ClarificationNeededError,
    HookContext,
    HookDecision,
)
from datacloud_analysis.tools.file_io import read_file_via_storage as _read_file_via_storage

PLUGIN_ID = "builtin.operation_confirmation"
PRIORITY = 150
ENABLED = True

_INTERRUPT_TYPE = "operation_form"
_CONFIRM_PARAM = "userConfirmed"
_OPERATION_CONFIRM_PARAM = "_operationConfirm"
_OPERATION_FAMILIES = frozenset({"insert", "update", "delete", "write", "update_kb", "operation"})
_INPUT_DIRECTIONS = frozenset({"IN", "INOUT", ""})
_IGNORED_SCHEMA_FIELDS = frozenset({_CONFIRM_PARAM, _OPERATION_CONFIRM_PARAM})
_DISPLAY_WRAPPER_FIELDS = frozenset({"requestBody", "body", "parameters"})
_MAPPING_LOCATION_ALIASES: dict[str, str] = {
    "requestBody": "body",
    "body": "body",
    "parameters": "body",
    "query": "query",
    "queryParams": "query",
    "path": "path",
    "pathParams": "path",
    "headers": "headers",
    "header": "headers",
}
_LOCATION_SCHEMA_KEYS: dict[str, str] = {
    "body": "requestBody",
    "query": "query",
    "path": "path",
    "headers": "headers",
}
_FIELD_NAME_OVERRIDES: dict[str, str] = {
    "labels": "知识库属性标签",
    "records": "批量记录",
    "values": "修改字段",
    "filters": "过滤条件",
    "filter_relation": "过滤条件连接方式",
    "field": "字段",
    "op": "操作符",
    "value": "过滤值",
    "source_path": "文件路径",
    "file_path": "文件路径",
    "content": "正文内容",
    "source_text": "正文内容",
    "file_description": "文件描述",
    "original_source_path": "原文件路径",
    "original_content": "原文件正文内容",
    "current_source_path": "现整理文件路径",
    "current_content": "现整理文件正文内容",
}
_LABEL_DESCRIPTION_MAX_LEN = 30
_SENTENCE_PUNCTUATION = frozenset("，。；：、,.;:!?！？\n\r")
_NULL_FILTER_OPERATORS = frozenset({"is_null", "is_not_null"})

# 知识库 write 动作的文件路径字段（按优先级排列，与 kb_search_executor 保持一致）
_KB_WRITE_PATH_FIELDS: tuple[str, ...] = ("source_path", "file_path")
# 知识库 write 动作的内容字段（与 kb_search_executor 保持一致，统一写入 content）
_KB_WRITE_CONTENT_FIELD = "content"
# 知识库 update_kb 动作：从存储读取并注入表单展示的路径-内容字段对（不覆盖模型传入的 content）
_KB_UPDATE_KB_DISPLAY_PAIRS: tuple[tuple[str, str], ...] = (
    ("original_source_path", "original_content"),
    ("current_source_path", "current_content"),
    ("source_path", "content"),
)

logger = logging.getLogger(__name__)


async def _try_fill_file_content(
    tool_params: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """读取 tool_params 中的文件路径字段，用文件内容替换对应的内容字段。

    仅处理知识库 write 动作的字段：source_path / file_path → content。
    支持 records 数组模式（每条记录独立读取）和单条模式。
    读取失败、内容为空或发生异常时静默忽略，保留原参数。

    Args:
        tool_params: 工具调用参数字典。
        metadata: HookContext.metadata，用于构建 InvocationContext。

    Returns:
        有内容被替换时返回新的参数字典副本，否则返回原字典。
    """
    storage = _resolve_storage_from_metadata(metadata)
    if storage is None:
        return tool_params

    inv_ctx = _build_invocation_context(metadata, storage)

    records = tool_params.get("records")
    if isinstance(records, list):
        new_records = [
            await _fill_record_file_content(record, storage, inv_ctx) for record in records
        ]
        if any(new is not orig for new, orig in zip(new_records, records, strict=True)):
            return {**tool_params, "records": new_records}
        return tool_params

    # 单条模式
    return await _fill_record_file_content(tool_params, storage, inv_ctx)


async def _try_fill_update_kb_file_content(
    tool_params: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """根据 update_kb 动作的原/现路径字段，从存储读取文件内容注入 tool_params 供表单展示。

    处理两对路径-内容字段（来源引用，只读展示）：
    - original_source_path → original_content
    - current_source_path  → current_content

    注意：不处理 source_path→content，该字段由模型提供，属于实际写入内容。
    读取失败或内容为空时静默忽略。

    Args:
        tool_params: 工具调用参数字典。
        metadata: HookContext.metadata，用于构建 InvocationContext。

    Returns:
        有内容被注入时返回新的参数字典副本，否则返回原字典。
    """
    storage = _resolve_storage_from_metadata(metadata)
    if storage is None:
        return tool_params

    inv_ctx = _build_invocation_context(metadata, storage)
    patched = dict(tool_params)
    changed = False

    for path_field, content_field in _KB_UPDATE_KB_DISPLAY_PAIRS:
        path_value = str(patched.get(path_field) or "").strip()
        # if not path_value:
        #     continue
        try:
            with inv_ctx:
                file_content: str = await _read_file_via_storage(path_value, storage)
        except Exception:
            logger.warning(
                "[operation_confirmation] update_kb read_file raised exception path=%r field=%s",
                path_value,
                path_field,
                exc_info=True,
            )
            continue
        if not file_content or file_content.startswith("错误："):
            logger.info(
                "[operation_confirmation] update_kb read_file skipped: path=%r field=%s result=%r",
                path_value,
                path_field,
                file_content[:80] if file_content else "",
            )
            continue
        patched[content_field] = file_content
        changed = True
        logger.info(
            "[operation_confirmation] update_kb file content filled: path=%r field=%s len=%d",
            path_value,
            content_field,
            len(file_content),
        )

    return patched if changed else tool_params


def _inject_update_kb_display_fields(
    schema: dict[str, Any],
    tool_params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """将 tool_params 中的 original_content / current_content 注入 schema properties。

    这两个字段不在 update_kb 的 inputSchema 里（不暴露给模型），但在表单中需要展示。
    由 _try_fill_update_kb_file_content 从存储填充后，通过此函数临时注入 schema 供渲染。
    注入的字段标记为 readOnly，用户不可编辑。
    """
    display_pairs: list[tuple[str, str, str]] = [
        ("original_source_path", "original_content", "原文件正文内容"),
        ("current_source_path", "current_content", "现整理文件正文内容"),
    ]
    extra_props: dict[str, Any] = {}
    for path_field, content_field, label in display_pairs:
        if content_field in tool_params:
            extra_props[content_field] = {
                "type": "string",
                "title": label,
                "description": f"由系统根据 {path_field} 自动读取，仅供确认查阅，不可修改。",
                "readOnly": True,
                "x-dc-form-type": "textarea",
            }
    if not extra_props:
        return schema, tool_params

    # 深拷贝 schema，在对应路径字段之后插入内容展示字段
    from copy import deepcopy

    patched_schema = deepcopy(schema)
    props = patched_schema.get("properties")
    if not isinstance(props, dict):
        return schema, tool_params

    new_props: dict[str, Any] = {}
    for key, val in props.items():
        new_props[key] = val
        for path_field, content_field, _ in display_pairs:
            if key == path_field and content_field in extra_props:
                new_props[content_field] = extra_props[content_field]
    patched_schema["properties"] = new_props
    return patched_schema, tool_params


async def _fill_record_file_content(
    record: Any,
    storage: Any,
    inv_ctx: Any,
) -> Any:
    """对单条记录尝试读取文件内容并替换内容字段，失败则返回原记录。"""
    if not isinstance(record, dict):
        return record
    path_value = ""
    for path_field in _KB_WRITE_PATH_FIELDS:
        candidate = str(record.get(path_field) or "").strip()
        if candidate:
            path_value = candidate
            break
    if not path_value:
        return record
    try:
        with inv_ctx:
            file_content: str = await _read_file_via_storage(path_value, storage)
    except Exception:
        logger.warning(
            "[operation_confirmation] read_file raised exception path=%r",
            path_value,
            exc_info=True,
        )
        return record
    if not file_content or file_content.startswith("错误："):
        logger.info(
            "[operation_confirmation] read_file skipped: path=%r result=%r",
            path_value,
            file_content[:80] if file_content else "",
        )
        return record
    patched = dict(record)
    patched[_KB_WRITE_CONTENT_FIELD] = file_content
    logger.info(
        "[operation_confirmation] file content filled: path=%r content_field=%s len=%d",
        path_value,
        _KB_WRITE_CONTENT_FIELD,
        len(file_content),
    )
    return patched


def _resolve_storage_from_metadata(metadata: dict[str, Any]) -> Any | None:
    """从 metadata 取 loader.result_file_storage；不存在则返回 None。"""
    loader = metadata.get("loader")
    return getattr(loader, "result_file_storage", None)


def _build_invocation_context(metadata: dict[str, Any], storage: Any) -> Any:
    """构建 InvocationContext，对齐 hook_aware_tool_node 的参数来源。

    设置完整字段，确保 with 块内调用的所有代码都能通过 get_current_context()
    拿到正确的 user_id / session_id / workspace_dir / token 等信息。
    """
    from datacloud_data_sdk.context import InvocationContext  # type: ignore[import]

    try:
        from datacloud_analysis.orchestration.execution.tool_wrapper import (  # noqa: PLC0415
            _resolve_gateway_user_id,
        )
        from datacloud_analysis.workspace.runtime import (  # noqa: PLC0415
            resolve_shared_workspace_dir,
        )
    except ImportError:
        return InvocationContext(result_file_storage=storage)

    gw_ctx = metadata.get("gateway_context")
    configurable = dict(metadata.get("configurable") or {})

    user_id = _resolve_gateway_user_id(gw_ctx) if gw_ctx is not None else ""
    session_id = str(getattr(gw_ctx, "session_id", "") or "")
    token = str(getattr(gw_ctx, "beyond_token", "") or configurable.get("beyond_token") or "")
    locale = str(configurable.get("locale") or "zh_CN")
    workspace_dir = str(configurable.get("workspace_dir") or "")
    workspace_root = resolve_shared_workspace_dir(workspace_dir) if workspace_dir else None
    config_extras: dict[str, Any] | None = configurable.get("extras")
    extras = config_extras if config_extras is not None else getattr(gw_ctx, "extras", None)

    return InvocationContext(
        user_id=user_id,
        session_id=session_id,
        token=token,
        gateway_context=gw_ctx,
        workspace_dir=str(workspace_root) if workspace_root is not None else workspace_dir,
        result_file_storage=storage,
        extras=extras,
        language=locale,
    )


def _is_kb_write_action(action: Any) -> bool:
    """判断 action 是否为知识库 write 动作。"""
    action_family = str(getattr(action, "action_family", "") or "").lower()
    if action_family != "write":
        return False
    scope = getattr(action, "_datacloud_scope", None)
    source_type = str(getattr(scope, "source_type", "") or "").upper()
    return source_type == "KNOWLEDGE_BASE"


def _is_kb_update_kb_action(action: Any) -> bool:
    """判断 action 是否为知识库 update_kb 动作。"""
    action_family = str(getattr(action, "action_family", "") or "").lower()
    if action_family != "update_kb":
        return False
    scope = getattr(action, "_datacloud_scope", None)
    source_type = str(getattr(scope, "source_type", "") or "").upper()
    return source_type == "KNOWLEDGE_BASE"


async def before_call_back(ctx: HookContext) -> HookDecision | None:
    """Interrupt operation tool calls before execution and resume with confirmed params."""
    tool_name = str(ctx.get("tool_name") or "")
    tool_call_id = str(ctx.get("tool_call_id") or "")
    tool_params = dict(ctx.get("tool_params") or {})
    metadata = dict(ctx.get("metadata") or {})
    state = metadata.get("state")
    state_dict = state if isinstance(state, dict) else {}
    loader = metadata.get("loader")
    locale = _locale_from_metadata(metadata)
    action = find_operation_action(loader, tool_name)
    if action is None:
        return None
    term_loader = _term_loader_from_loader(loader)

    # 读取文件内容替换模型参数（仅知识库 write / update_kb 动作，读取失败则静默忽略）
    if _is_kb_write_action(action):
        tool_params = await _try_fill_file_content(tool_params, metadata)
    elif _is_kb_update_kb_action(action):
        tool_params = await _try_fill_update_kb_file_content(tool_params, metadata)

    formatted_params = _get_operation_formatted_params(state_dict, tool_name, tool_call_id)
    if formatted_params is not None:
        if not bool(formatted_params.get("confirmed")):
            return {
                "action": "fail",
                "result": {
                    "tool_error": {
                        "error_type": "OperationCancelled",
                        "message": str(
                            formatted_params.get("reason")
                            or get_ui_text("operation_cancelled_reason", locale)
                        ),
                        "retryable": False,
                        "hint": get_ui_text("operation_cancelled_hint", locale),
                        "context": {"tool_name": tool_name, "tool_call_id": tool_call_id},
                    }
                },
            }
        patched = dict(formatted_params.get("params") or {})
        if not patched:
            patched = restore_action_params(
                list(formatted_params.get("rule") or []),
                action=action,
                original_params=tool_params,
            )
        patched[_CONFIRM_PARAM] = True
        patched[_OPERATION_CONFIRM_PARAM] = {
            "formId": str(formatted_params.get("formId") or ""),
            "toolCallId": tool_call_id,
            "confirmed": True,
        }
        logger.info("[operation_confirmation] resume patch tool=%s", tool_name)
        return {"action": "patch", "patch": {"tool_params": patched}}

    operation_form = build_operation_form(
        action,
        tool_params,
        term_loader=term_loader,
        locale=locale,
    )
    operation_form_action = build_operation_action_form(
        action,
        tool_params,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        term_loader=term_loader,
        locale=locale,
    )
    form_id = str(operation_form_action.get("formId") or operation_form.get("formId") or "")
    logger.info("[operation_confirmation] interrupt tool=%s form_id=%s", tool_name, form_id)
    raise ClarificationNeededError(
        {
            "interrupt_type": _INTERRUPT_TYPE,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "structured_input": deepcopy(tool_params),
            "operation_form": operation_form,
            "operation_form_action": operation_form_action,
            "operation_confirm_context": {
                "formId": form_id,
                "actionCode": str(getattr(action, "action_code", tool_name) or tool_name),
                "actionFamily": str(getattr(action, "action_family", "") or ""),
                "originalParamsHash": _stable_hash(tool_params),
            },
        }
    )


def find_operation_action(loader: Any, tool_name: str) -> Any | None:
    """Find a confirmable ontology action by tool name."""
    if loader is None or not tool_name:
        return None
    for scope, action in _iter_loader_actions(loader):
        action_code = str(getattr(action, "action_code", "") or "")
        aliases = [str(item) for item in (getattr(action, "legacy_aliases", None) or [])]
        if tool_name not in {action_code, *aliases}:
            continue
        if _is_confirmable_action(action):
            try:
                action._datacloud_scope = scope
            except Exception:
                logger.debug("failed to attach action scope metadata", exc_info=True)
            return action
    return None


def build_operation_form(
    action: Any,
    tool_params: dict[str, Any],
    *,
    term_loader: Any | None = None,
    locale: str | None = None,
) -> dict[str, Any]:
    """Build frontend operation confirmation form from action metadata and params."""
    form_id = _build_form_id(action, tool_params)
    action_code = str(getattr(action, "action_code", "") or "")
    action_name = str(getattr(action, "action_name", "") or action_code)
    rule = _build_top_level_rule(
        action,
        tool_params,
        form_id=form_id,
        term_loader=term_loader,
        locale=locale,
    )
    display_action_name = action_name or action_code
    return {
        "schemaVersion": "1.0",
        "formId": form_id,
        "actionCode": action_code,
        "actionName": action_name,
        "title": get_ui_text("operation_form_title", locale, action_name=display_action_name),
        "description": get_ui_text("operation_form_description", locale),
        "rule": rule,
    }


def build_operation_action_form(
    action: Any,
    tool_params: dict[str, Any],
    *,
    tool_call_id: str,
    tool_name: str,
    term_loader: Any | None = None,
    locale: str | None = None,
) -> dict[str, Any]:
    """Build one action item for a batch operation confirmation form."""
    form = build_operation_form(action, tool_params, term_loader=term_loader, locale=locale)
    return {
        "formId": str(form.get("formId") or ""),
        "toolCallId": tool_call_id,
        "toolName": tool_name,
        "actionCode": str(form.get("actionCode") or tool_name),
        "actionName": str(form.get("actionName") or form.get("actionCode") or tool_name),
        "title": str(form.get("title") or ""),
        "description": str(form.get("description") or ""),
        "rule": list(form.get("rule") or []),
    }


def build_batch_operation_form(
    operation_contexts: list[dict[str, Any]],
    *,
    locale: str | None = None,
) -> dict[str, Any]:
    """Build a batch operation form from collected operation interruption contexts."""
    actions: list[dict[str, Any]] = []
    for context in operation_contexts:
        action_form = context.get("operation_form_action")
        if isinstance(action_form, dict):
            action = dict(action_form)
        else:
            legacy_form = dict(context.get("operation_form") or {})
            action = {
                "formId": str(legacy_form.get("formId") or ""),
                "toolCallId": str(context.get("tool_call_id") or ""),
                "toolName": str(context.get("tool_name") or ""),
                "actionCode": str(legacy_form.get("actionCode") or context.get("tool_name") or ""),
                "actionName": str(
                    legacy_form.get("actionName")
                    or legacy_form.get("actionCode")
                    or context.get("tool_name")
                    or ""
                ),
                "title": str(legacy_form.get("title") or ""),
                "description": str(legacy_form.get("description") or ""),
                "rule": list(legacy_form.get("rule") or []),
            }
        action = _normalize_frontend_action_keys(action)
        actions.append(action)

    form_id = _build_batch_form_id(actions)
    for action in actions:
        action.pop("formId", None)
    return {
        "schemaVersion": "1.0",
        "formId": form_id,
        "title": get_ui_text("operation_batch_title", locale, count=len(actions))
        if len(actions) > 1
        else get_ui_text("operation_batch_single_title", locale),
        "description": get_ui_text("operation_form_description", locale),
        "actions": actions,
    }


def _build_batch_form_id(actions: list[dict[str, Any]]) -> str:
    source = json.dumps(
        [
            {
                "toolCallId": action.get("toolCallId") or action.get("tool_call_id"),
                "actionCode": action.get("actionCode"),
                "rule": action.get("rule"),
            }
            for action in actions
        ],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return f"op_form_batch_{hashlib.sha256(source.encode()).hexdigest()[:16]}"


def _normalize_frontend_action_keys(action: dict[str, Any]) -> dict[str, Any]:
    """Expose operation action identity fields with frontend camelCase keys."""
    normalized = dict(action)
    normalized["toolCallId"] = str(
        normalized.get("toolCallId") or normalized.get("tool_call_id") or ""
    )
    normalized["toolName"] = str(normalized.get("toolName") or normalized.get("tool_name") or "")
    normalized.pop("tool_call_id", None)
    normalized.pop("tool_name", None)
    return normalized


def restore_action_params(
    rule: list[Any],
    *,
    action: Any | None = None,
    original_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Restore action params from confirmed 2D rule payload."""
    rule_rows = _normalize_rule_rows(rule)
    if not rule_rows:
        return dict(original_params or {})

    action_family = str(getattr(action, "action_family", "") or "").lower() if action else ""
    if action_family == "insert" or (
        action_family == "write" and isinstance((original_params or {}).get("records"), list)
    ):
        return {"records": [_fields_to_object(row) for row in rule_rows]}

    params: dict[str, Any] = dict(original_params or {})
    if len(rule_rows) == 1:
        for key, value in _fields_to_object(rule_rows[0], use_field_path=True).items():
            _set_path_value(params, key, value)
        return _filter_restored_params(params, action)

    params["records"] = [_fields_to_object(row, use_field_path=True) for row in rule_rows]
    return _filter_restored_params(params, action)


def _get_operation_formatted_params(
    state: dict[str, Any],
    tool_name: str,
    tool_call_id: str = "",
) -> dict[str, Any] | None:
    formatted = state.get("clarification_formatted_params")
    if not isinstance(formatted, dict):
        return None
    if str(formatted.get("interrupt_type") or "") != _INTERRUPT_TYPE:
        return None

    by_tool_call_id = formatted.get("params_by_tool_call_id")
    if tool_call_id and isinstance(by_tool_call_id, dict):
        matched = by_tool_call_id.get(tool_call_id)
        if isinstance(matched, dict):
            result = dict(matched)
            result.setdefault("formId", formatted.get("formId"))
            return result

    actions = formatted.get("actions")
    if tool_call_id and isinstance(actions, list):
        for item in actions:
            if (
                isinstance(item, dict)
                and str(item.get("tool_call_id") or item.get("toolCallId") or "") == tool_call_id
            ):
                result = dict(item)
                result.setdefault("formId", formatted.get("formId"))
                return result
    if tool_call_id and (isinstance(by_tool_call_id, dict) or isinstance(actions, list)):
        return None

    if str(formatted.get("tool_name") or "") != tool_name:
        return None
    return formatted


def _iter_loader_actions(loader: Any) -> list[tuple[Any, Any]]:
    actions: list[tuple[Any, Any]] = []
    get_classes = getattr(loader, "get_ontology_classes", None)
    if callable(get_classes):
        try:
            for cls in get_classes():
                actions.extend((cls, action) for action in list(getattr(cls, "actions", []) or []))
        except Exception:
            logger.debug("operation action lookup failed for ontology classes", exc_info=True)
    get_views = getattr(loader, "get_views", None)
    if callable(get_views):
        try:
            for view in get_views():
                actions.extend(
                    (view, action) for action in list(getattr(view, "actions", []) or [])
                )
        except Exception:
            logger.debug("operation action lookup failed for views", exc_info=True)
    return actions


def _term_loader_from_loader(loader: Any) -> Any | None:
    config = getattr(loader, "_config", None)
    term_loader = getattr(config, "term_loader", None)
    if term_loader is not None:
        return term_loader
    return getattr(loader, "term_loader", None)


def _locale_from_metadata(metadata: dict[str, Any]) -> str | None:
    configurable = metadata.get("configurable")
    if isinstance(configurable, dict):
        locale = str(configurable.get("locale") or "").strip()
        if locale:
            return locale
    gateway_context = metadata.get("gateway_context")
    locale = str(getattr(gateway_context, "locale", "") or "").strip()
    return locale or None


def _is_confirmable_action(action: Any) -> bool:
    action_type = str(getattr(action, "action_type", "") or "").lower()
    action_family = str(getattr(action, "action_family", "") or "").lower()
    return action_type == "operation" or action_family in _OPERATION_FAMILIES


def _build_top_level_rule(
    action: Any,
    tool_params: dict[str, Any],
    *,
    form_id: str,
    term_loader: Any | None = None,
    locale: str | None = None,
) -> list[list[dict[str, Any]]]:
    action_family = str(getattr(action, "action_family", "") or "").lower()
    field_meta = _action_field_meta(action)
    param_meta = _action_param_meta(action)
    if action_family == "insert" and isinstance(tool_params.get("records"), list):
        return _build_records_rule(
            action,
            tool_params,
            form_id=form_id,
            field_meta=field_meta,
            param_meta=param_meta,
            term_loader=term_loader,
            locale=locale,
        )

    if action_family == "write" and isinstance(tool_params.get("records"), list):
        return _build_records_rule(
            action,
            tool_params,
            form_id=form_id,
            field_meta=field_meta,
            param_meta=param_meta,
            term_loader=term_loader,
            locale=locale,
        )

    input_schema = _schema_for_single_action_display(_get_action_input_schema(action), tool_params)
    # update_kb 动作：把从存储读取到的原/现文件内容注入 schema 和 values，供表单展示（只读）
    if _is_kb_update_kb_action(action):
        input_schema, tool_params = _inject_update_kb_display_fields(input_schema, tool_params)
    schema, values, parent_path = _display_schema_and_values(input_schema, tool_params)
    row = _build_fields_from_schema(
        schema,
        values,
        item_id=_build_item_id(form_id, 1),
        parent_path=parent_path,
        field_meta=field_meta,
        param_meta=param_meta,
        term_loader=term_loader,
        locale=locale,
        action=action,
    )
    if row:
        return [row]

    params = [
        param
        for param in list(getattr(action, "params", []) or [])
        if str(getattr(param, "direction", "") or "").upper() in _INPUT_DIRECTIONS
    ]
    return [
        [
            _build_field_from_param(
                param,
                tool_params,
                first=index == 1,
                form_id=form_id,
                term_loader=term_loader,
                locale=locale,
                action=action,
            )
            for index, param in enumerate(params, start=1)
        ]
    ]


def _build_records_rule(
    action: Any,
    tool_params: dict[str, Any],
    *,
    form_id: str,
    field_meta: dict[str, Any],
    param_meta: dict[str, Any],
    term_loader: Any | None = None,
    locale: str | None = None,
) -> list[list[dict[str, Any]]]:
    records = tool_params.get("records")
    if not isinstance(records, list):
        return []
    return [
        _build_fields_from_schema(
            _get_records_item_schema(action),
            record if isinstance(record, dict) else {},
            item_id=_build_item_id(form_id, index),
            field_meta=field_meta,
            param_meta=param_meta,
            term_loader=term_loader,
            locale=locale,
            action=action,
        )
        for index, record in enumerate(records, start=1)
    ]


def _get_action_input_schema(action: Any) -> dict[str, Any]:
    schema = getattr(action, "input_schema", None)
    if isinstance(schema, dict):
        return schema
    params = [
        param
        for param in list(getattr(action, "params", []) or [])
        if str(getattr(param, "direction", "") or "").upper() in _INPUT_DIRECTIONS
    ]
    if any(str(getattr(param, "mapping_path", "") or "").startswith("$.") for param in params):
        return _build_input_schema_from_mapping_paths(params)
    return _build_flat_input_schema(params)


def _build_flat_input_schema(params: list[Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param in params:
        code = str(getattr(param, "param_code", "") or "")
        if not code:
            continue
        properties[code] = {
            "type": _normalize_field_type(getattr(param, "param_type", "string")),
            "description": str(getattr(param, "param_name", "") or code),
        }
        term = _term_from_param(param)
        if term is not None:
            properties[code]["term"] = term
        data_format = str(getattr(param, "data_format", "") or "").strip()
        if data_format:
            properties[code]["x-data-format"] = data_format
        if bool(getattr(param, "required", False)):
            required.append(code)
    result: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    return result


def _build_input_schema_from_mapping_paths(params: list[Any]) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": {}}
    required_wrappers: set[str] = set()
    properties = schema["properties"]
    for param in params:
        code = str(getattr(param, "param_code", "") or "")
        if not code:
            continue
        leaf_schema = _build_param_schema(param)
        location, path_parts = _parse_mapping_path(
            str(getattr(param, "mapping_path", "") or ""),
            default_location="body",
        )
        location_key = _schema_location_key(location)
        if not path_parts:
            path_parts = [code]

        node = properties.setdefault(location_key, {"type": "object", "properties": {}})
        if not isinstance(node, dict):
            node = {"type": "object", "properties": {}}
            properties[location_key] = node
        _assign_schema_path(
            node,
            path_parts,
            leaf_schema,
            required=bool(getattr(param, "required", False)),
        )
        if bool(getattr(param, "required", False)):
            required_wrappers.add(location_key)
    if required_wrappers:
        schema["required"] = sorted(required_wrappers)
    return schema


def _build_param_schema(param: Any) -> dict[str, Any]:
    code = str(getattr(param, "param_code", "") or "")
    schema: dict[str, Any] = {
        "type": _normalize_field_type(getattr(param, "param_type", "string")),
        "description": str(getattr(param, "param_name", "") or code),
    }
    term = _term_from_param(param)
    if term is not None:
        schema["term"] = term
    default_value = getattr(param, "default_value", None)
    if default_value is not None:
        schema["default"] = default_value
    data_format = str(getattr(param, "data_format", "") or "").strip()
    if data_format:
        schema["x-data-format"] = data_format
    return schema


def _get_records_item_schema(action: Any) -> dict[str, Any]:
    schema = _get_action_input_schema(action)
    records_schema = dict((schema.get("properties") or {}).get("records") or {})
    item_schema = records_schema.get("items")
    return item_schema if isinstance(item_schema, dict) else {"type": "object", "properties": {}}


def _schema_for_single_action_display(
    schema: dict[str, Any],
    values: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(values.get("records"), list):
        return schema

    properties = schema.get("properties")
    if not isinstance(properties, dict) or "records" not in properties:
        return schema

    display_schema = deepcopy(schema)
    display_properties = display_schema.get("properties")
    if isinstance(display_properties, dict):
        display_properties.pop("records", None)
    return display_schema


def _display_schema_and_values(
    schema: dict[str, Any],
    values: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    properties = schema.get("properties")
    if not isinstance(properties, dict) or len(properties) != 1:
        return schema, values, ""
    wrapper_key = next(iter(properties))
    wrapper_schema = properties.get(wrapper_key)
    if wrapper_key not in _DISPLAY_WRAPPER_FIELDS or not isinstance(wrapper_schema, dict):
        return schema, values, ""
    if str(wrapper_schema.get("type") or "").lower() != "object":
        return schema, values, ""
    wrapper_values = values.get(wrapper_key)
    return (
        wrapper_schema,
        wrapper_values if isinstance(wrapper_values, dict) else values,
        wrapper_key,
    )


def _build_fields_from_schema(
    schema: dict[str, Any],
    values: dict[str, Any],
    *,
    item_id: str,
    parent_path: str = "",
    field_meta: dict[str, Any] | None = None,
    param_meta: dict[str, Any] | None = None,
    term_loader: Any | None = None,
    locale: str | None = None,
    action: Any,
) -> list[dict[str, Any]]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    required = set(schema.get("required") or [])
    is_filter_condition = _is_filter_condition_schema(schema)
    fields: list[dict[str, Any]] = []
    provided_keys = set(values) if isinstance(values, dict) else set()
    sorted_properties = sorted(
        properties.items(), key=lambda item: 0 if item[0] in provided_keys else 1
    )
    for code, property_schema_raw in sorted_properties:
        if code in _IGNORED_SCHEMA_FIELDS or not isinstance(property_schema_raw, dict):
            continue
        property_schema = dict(property_schema_raw)
        if is_filter_condition and str(code) == "value" and _is_null_filter_operator(values):
            continue
        field_path = f"{parent_path}.{code}" if parent_path else str(code)
        field_type = (
            _filter_value_field_type(values)
            if is_filter_condition and str(code) == "value"
            else _schema_field_type(property_schema)
        )
        normalized_field_type = _field_type_family(field_type)
        field_value = values.get(code)
        if field_value is None and "default" in property_schema:
            field_value = property_schema.get("default")
        children: list[list[dict[str, Any]]] | None = None
        if normalized_field_type == "object":
            child_values = field_value if isinstance(field_value, dict) else {}
            child_schema = property_schema
            if property_schema.get("x-dc-provided-only") and child_values:
                orig_props = property_schema.get("properties") or {}
                filtered_props = {k: v for k, v in orig_props.items() if k in child_values}
                child_schema = {**property_schema, "properties": filtered_props}
            children = [
                _build_fields_from_schema(
                    child_schema,
                    child_values,
                    item_id=f"{item_id}_{code}_001",
                    parent_path=field_path,
                    field_meta=field_meta,
                    param_meta=param_meta,
                    term_loader=term_loader,
                    locale=locale,
                    action=action,
                )
            ]
        elif normalized_field_type == "array":
            items_schema = _array_object_item_schema(property_schema)
            item_values = field_value if isinstance(field_value, list) else []
            if items_schema is not None and not item_values:
                item_values = [{}]
            if items_schema is not None:
                children = [
                    _build_fields_from_schema(
                        _schema_for_array_item_value(items_schema, item),
                        item if isinstance(item, dict) else {},
                        item_id=f"{item_id}_{code}_{index:03d}",
                        parent_path=field_path,
                        field_meta=field_meta,
                        param_meta=param_meta,
                        term_loader=term_loader,
                        locale=locale,
                        action=action,
                    )
                    for index, item in enumerate(item_values, start=1)
                ]
        meta = _match_field_meta(field_meta or {}, str(code), field_path)
        param = _match_field_meta(param_meta or {}, str(code), field_path)
        field_name, description = _field_display_text(
            field_code=str(code),
            schema=property_schema,
            field_meta=meta,
            param=param,
        )
        field = _build_field(
            field_code=str(code),
            field_name=field_name,
            description=description,
            field_type=field_type,
            field_value=field_value,
            children=children,
            field_path=field_path,
            required=str(code) in required,
            term=(
                _term_from_schema(property_schema)
                or _term_from_param(param)
                or _term_from_field_meta(meta)
            ),
            optional=_schema_options(property_schema),
            data_format=str(property_schema.get("x-data-format") or "").strip() or None,
            term_loader=term_loader,
            locale=locale,
            action=action,
        )
        filter_options = _filter_condition_options(property_schema)
        if filter_options:
            field["filterOptions"] = filter_options
        forced_form_type = str(property_schema.get("x-dc-form-type") or "").strip()
        if forced_form_type:
            field["formType"] = forced_form_type
        if not fields:
            field["itemId"] = item_id
        fields.append(field)
    return fields


def _build_field_from_param(
    param: Any,
    tool_params: dict[str, Any],
    *,
    first: bool,
    form_id: str,
    term_loader: Any | None = None,
    locale: str | None = None,
    action: Any,
) -> dict[str, Any]:
    code = str(getattr(param, "param_code", "") or "")
    field = _build_field(
        field_code=code,
        field_name=str(getattr(param, "param_name", "") or code),
        description=str(getattr(param, "description", "") or ""),
        field_type=_normalize_field_type(getattr(param, "param_type", "string")),
        field_value=tool_params.get(code, getattr(param, "default_value", None)),
        children=None,
        field_path=code,
        required=bool(getattr(param, "required", False)),
        term=_term_from_param(param),
        optional=[],
        data_format=str(getattr(param, "data_format", "") or "").strip() or None,
        term_loader=term_loader,
        locale=locale,
        action=action,
    )
    if first:
        field["itemId"] = _build_item_id(form_id, 1)
    return field


def _build_field(
    *,
    field_code: str,
    field_name: str,
    description: str,
    field_type: str,
    field_value: Any,
    children: list[list[dict[str, Any]]] | None,
    field_path: str,
    required: bool,
    term: dict[str, Any] | None,
    optional: list[str],
    data_format: str | None = None,
    term_loader: Any | None = None,
    locale: str | None = None,
    action: Any,
) -> dict[str, Any]:
    field: dict[str, Any] = {
        "formType": _field_form_type(
            field_type=field_type,
            action=action,
            filed_name=field_name,
            term=term,
            optional=optional,
            data_format=data_format,
        ),
        "fieldCode": field_code,
        "fieldPath": field_path,
        "fieldName": field_name,
        "fieldType": field_type,
        "description": description,
        "required": required,
        "readonly": _field_readonly(field_code, optional),
        "disabled": False,
        "isHidden": False,
        "defaultFiles": [],
    }
    if data_format:
        field["format"] = data_format
    if children is not None:
        field["children"] = children
    else:
        resolved_value, notice = _resolve_term_field_value(
            field_value,
            term=term,
            term_loader=term_loader,
            field_name=field_name,
            locale=locale,
        )
        field["fieldValue"] = resolved_value
        if notice:
            field["termResolveNotice"] = notice
    if term:
        field["term"] = term
    if optional:
        field["optional"] = optional
    return field


def _field_form_type(
    field_type: str,
    action: Any,
    filed_name: str,
    term: dict[str, Any] | None,
    optional: list[str],
    data_format: str | None = None,
) -> str:
    if _is_kb_write_action(action) and filed_name == "正文内容":
        return "textarea"
    if _is_kb_update_kb_action(action) and filed_name == "正文内容":
        return "textarea"
    if field_type == "object":
        return "object"
    if field_type == "array<object>":
        return "array"
    if term:
        return "term_select"
    if optional:
        return "select"
    if data_format and field_type == "string":
        return "date_time"
    return {
        "number": "number",
        "integer": "number",
        "boolean": "checkbox",
        "object": "object",
        "array": "array",
    }.get(field_type, "input")


def _resolve_term_field_value(
    value: Any,
    *,
    term: dict[str, Any] | None,
    term_loader: Any | None,
    field_name: str,
    locale: str | None = None,
) -> tuple[Any, dict[str, Any] | None]:
    if term_loader is None or not term or _is_empty_term_value(value):
        return value, None
    if isinstance(value, (list, tuple)):
        resolved_items: list[Any] = []
        notices: list[dict[str, Any]] = []
        changed = False
        for item in value:
            resolved_item, notice = _resolve_single_term_value(
                item,
                term=term,
                term_loader=term_loader,
                field_name=field_name,
                locale=locale,
            )
            resolved_items.append(resolved_item)
            changed = changed or resolved_item != item
            if notice:
                notices.append(notice)
        if not notices:
            return resolved_items if changed else value, None
        return resolved_items, {"status": "list_resolved", "items": notices}
    return _resolve_single_term_value(
        value, term=term, term_loader=term_loader, field_name=field_name, locale=locale
    )


def _resolve_single_term_value(
    value: Any,
    *,
    term: dict[str, Any],
    term_loader: Any,
    field_name: str,
    locale: str | None = None,
) -> tuple[Any, dict[str, Any] | None]:
    raw_value = str(value).strip()
    if not raw_value:
        return value, None
    try:
        term_loader.resolve_value(
            str(term.get("termSet") or ""),
            raw_value,
            term_field="code",
            dataset_id=_term_dataset_id(term),
            term_type_code=str(term.get("termTypeCode") or "") or None,
            keyword=raw_value,
            param_name=field_name,
        )
    except TermAmbiguousError as exc:
        recommendation = _first_term_entry(exc.matches)
        if recommendation is None:
            return None, _build_term_resolve_notice(
                status="ambiguous",
                original_value=raw_value,
                recommended_value="",
                recommended_label="",
                locale=locale,
            )
        return _recommended_term_value(
            raw_value,
            recommendation,
            status="ambiguous_recommended",
            candidates=_term_notice_candidates(exc.matches),
            locale=locale,
        )
    except TermNotFoundError as exc:
        recommendation = _recommend_term_entry(term_loader, term, raw_value, exc.available_entries)
        if recommendation is None:
            return None, _build_term_resolve_notice(
                status="not_found",
                original_value=raw_value,
                recommended_value="",
                recommended_label="",
                locale=locale,
            )
        return _recommended_term_value(
            raw_value, recommendation, status="recommended", locale=locale
        )
    except (AttributeError, ImportError, RuntimeError, ValueError):
        recommendation = _recommend_term_entry(term_loader, term, raw_value, None)
        if recommendation is not None:
            return _recommended_term_value(
                raw_value, recommendation, status="recommended", locale=locale
            )
        logger.debug(
            "failed to resolve operation form term value: term=%s value=%s",
            term.get("termSet"),
            raw_value,
            exc_info=True,
        )
        return value, None

    return value, None


def _recommended_term_value(
    original_value: str,
    recommendation: dict[str, str],
    *,
    status: str,
    candidates: list[dict[str, str]] | None = None,
    locale: str | None = None,
) -> tuple[str, dict[str, Any]]:
    recommended_value = str(recommendation.get("code") or recommendation.get("value") or "")
    recommended_label = str(recommendation.get("label") or recommendation.get("name") or "")
    notice = _build_term_resolve_notice(
        status=status,
        original_value=original_value,
        recommended_value=recommended_value,
        recommended_label=recommended_label,
        candidates=candidates,
        locale=locale,
    )
    return recommended_value, notice


def _recommend_term_entry(
    term_loader: Any,
    term: dict[str, Any],
    raw_value: str,
    available_entries: list[dict[str, str]] | None,
) -> dict[str, str] | None:
    recommendation = _first_term_entry(available_entries)
    if recommendation is not None:
        return recommendation
    try:
        entries, _total = term_loader.get_entries_page(
            str(term.get("termSet") or ""),
            dataset_id=_term_dataset_id(term),
            term_type_code=str(term.get("termTypeCode") or "") or None,
            keyword=raw_value,
            limit=1,
            offset=0,
        )
    except AttributeError:
        entries = term_loader.get_entries(
            str(term.get("termSet") or ""),
            dataset_id=_term_dataset_id(term),
            term_type_code=str(term.get("termTypeCode") or "") or None,
            keyword=raw_value,
        )
    except (ImportError, RuntimeError, ValueError):
        logger.debug(
            "failed to recommend operation form term value: term=%s value=%s",
            term.get("termSet"),
            raw_value,
            exc_info=True,
        )
        return None
    return _first_term_entry(list(entries or []))


def _first_term_entry(entries: list[dict[str, str]] | None) -> dict[str, str] | None:
    if not entries:
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("code") or entry.get("value") or "").strip()
        if code:
            return {
                "code": code,
                "label": str(entry.get("label") or entry.get("name") or "").strip(),
            }
    return None


def _term_notice_candidates(entries: list[dict[str, str]] | None) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    if not entries:
        return candidates
    for entry in entries:
        normalized = _first_term_entry([entry])
        if normalized is not None:
            candidates.append(
                {
                    "value": normalized["code"],
                    "label": normalized["label"],
                }
            )
    return candidates


def _build_term_resolve_notice(
    *,
    status: str,
    original_value: str,
    recommended_value: str,
    recommended_label: str,
    candidates: list[dict[str, str]] | None = None,
    locale: str | None = None,
) -> dict[str, Any]:
    display = recommended_label or recommended_value
    if status == "ambiguous_recommended" and recommended_value:
        message = get_ui_text(
            "operation_term_ambiguous_recommended",
            locale,
            original=original_value,
            display=display,
            code=recommended_value,
        )
    elif status == "recommended" and recommended_value:
        message = get_ui_text(
            "operation_term_recommended",
            locale,
            original=original_value,
            display=display,
            code=recommended_value,
        )
    else:
        message = get_ui_text("operation_term_not_found", locale, original=original_value)
    notice: dict[str, Any] = {
        "status": status,
        "originalValue": original_value,
        "recommendedValue": recommended_value,
        "recommendedLabel": recommended_label,
        "message": message,
    }
    if candidates:
        notice["candidates"] = candidates
    return notice


def _term_dataset_id(term: dict[str, Any]) -> int | None:
    dataset_id = term.get("datasetId")
    if dataset_id is None:
        return None
    try:
        return int(dataset_id)
    except (TypeError, ValueError):
        return None


def _is_empty_term_value(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _field_readonly(field_code: str, optional: list[str]) -> bool:
    return field_code in {"field", "op"} and bool(optional)


def _field_display_text(
    *,
    field_code: str,
    schema: dict[str, Any],
    field_meta: Any | None,
    param: Any | None,
) -> tuple[str, str]:
    """Resolve concise form label and keep schema description as helper text."""
    description = str(schema.get("description") or "").strip()
    explicit_name = str(
        getattr(param, "param_name", "")
        or getattr(field_meta, "field_name", "")
        or getattr(field_meta, "property_name", "")
        or ""
    ).strip()
    if explicit_name:
        return explicit_name, description

    title = str(
        schema.get("title")
        or schema.get("fieldName")
        or schema.get("field_name")
        or schema.get("x-form-label")
        or ""
    ).strip()
    if title:
        return title, description

    override = _FIELD_NAME_OVERRIDES.get(field_code)
    if override:
        return override, description

    if _is_concise_label(description):
        return description, description

    return field_code, description


def _is_concise_label(text: str) -> bool:
    if not text:
        return False
    if len(text) > _LABEL_DESCRIPTION_MAX_LEN:
        return False
    return not any(char in _SENTENCE_PUNCTUATION for char in text)


def _is_filter_condition_schema(schema: dict[str, Any]) -> bool:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return False
    return {"field", "op", "value"}.issubset(set(properties))


def _filter_value_field_type(values: dict[str, Any]) -> str:
    return "array<string>" if str(values.get("op") or "").lower() == "in" else "string"


def _is_null_filter_operator(values: dict[str, Any]) -> bool:
    return str(values.get("op") or "").lower() in _NULL_FILTER_OPERATORS


def _schema_field_type(schema: dict[str, Any]) -> str:
    normalized = _normalize_field_type(schema.get("type") or "string")
    if normalized != "array":
        return normalized
    if _array_object_item_schema(schema) is not None:
        return "array<object>"
    items = schema.get("items")
    if not isinstance(items, dict):
        return "array"
    item_type = _normalize_field_type(items.get("type") or "")
    if item_type in {"string", "integer", "number", "boolean"}:
        return f"array<{item_type}>"
    return "array"


def _schema_options(schema: dict[str, Any]) -> list[str]:
    options = _string_list(schema.get("enum"))
    if options:
        return options
    const_value = schema.get("const")
    if const_value is not None:
        return [str(const_value)]
    return []


def _normalize_field_type(raw_type: Any) -> str:
    normalized = str(raw_type or "string").lower()
    type_map = {
        "str": "string",
        "string": "string",
        "integer": "integer",
        "int": "integer",
        "long": "integer",
        "number": "number",
        "decimal": "number",
        "double": "number",
        "float": "number",
        "boolean": "boolean",
        "bool": "boolean",
        "array": "array",
        "list": "array",
        "object": "object",
    }
    return type_map.get(normalized, "string")


def _field_type_family(field_type: str) -> str:
    normalized = str(field_type or "").lower()
    if normalized.startswith("array<"):
        return "array"
    return _normalize_field_type(normalized)


def _term_from_param(param: Any) -> dict[str, Any] | None:
    term_set = str(getattr(param, "term_set", "") or "").strip()
    if not term_set:
        return None
    return _build_term(
        term_set=term_set,
        term_type_code="",
        term_field=str(getattr(param, "term_field", "") or "").strip(),
        dataset_id=getattr(param, "dataset_id", None),
    )


def _term_from_field_meta(field: Any | None) -> dict[str, Any] | None:
    if field is None:
        return None
    term_set = str(getattr(field, "term_set", "") or "").strip()
    if not term_set:
        return None
    return _build_term(
        term_set=term_set,
        term_type_code="",
        term_field=str(getattr(field, "term_field", "") or "").strip(),
        dataset_id=getattr(field, "dataset_id", None),
    )


def _term_from_schema(schema: dict[str, Any]) -> dict[str, Any] | None:
    term_raw = schema.get("term")
    if isinstance(term_raw, dict):
        term_set = str(term_raw.get("termSet") or term_raw.get("term_set") or "").strip()
        if term_set:
            return _build_term(
                term_set=term_set,
                term_type_code=str(
                    term_raw.get("termTypeCode") or term_raw.get("term_type_code") or ""
                ),
                term_field=str(term_raw.get("termField") or term_raw.get("term_field") or ""),
                dataset_id=term_raw.get("datasetId") or term_raw.get("dataset_id"),
            )
    term_set = str(schema.get("termSet") or schema.get("term_set") or "").strip()
    if not term_set:
        return None
    return _build_term(
        term_set=term_set,
        term_type_code=str(schema.get("termTypeCode") or schema.get("term_type_code") or ""),
        term_field=str(schema.get("termField") or schema.get("term_field") or ""),
        dataset_id=schema.get("datasetId") or schema.get("dataset_id"),
    )


def _build_term(
    *,
    term_set: str,
    term_type_code: str,
    term_field: str,
    dataset_id: Any,
) -> dict[str, Any]:
    term: dict[str, Any] = {
        "termSet": term_set,
        "termTypeCode": term_type_code or term_set.split(".", 1)[0],
    }
    if term_field:
        term["termField"] = term_field
    if dataset_id is not None:
        term["datasetId"] = dataset_id
    return term


def _action_field_meta(action: Any) -> dict[str, Any]:
    scope = getattr(action, "_datacloud_scope", None)
    fields = getattr(scope, "fields", None)
    if not isinstance(fields, list):
        return {}
    result: dict[str, Any] = {}
    for field in fields:
        code = str(getattr(field, "field_code", "") or getattr(field, "property_code", "") or "")
        if code:
            result[code] = field
    return result


def _action_param_meta(action: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for param in list(getattr(action, "params", []) or []):
        code = str(getattr(param, "param_code", "") or "")
        if code:
            result[code] = param
        mapping_path = str(getattr(param, "mapping_path", "") or "")
        for key in _mapping_path_keys(mapping_path):
            result.setdefault(key, param)
    return result


def _mapping_path_keys(mapping_path: str) -> list[str]:
    if not mapping_path.startswith("$."):
        return []
    ignored_roots = {"requestBody", "body", "parameters", "query", "path", "headers", "header"}
    parts = [part[:-2] if part.endswith("[]") else part for part in mapping_path[2:].split(".")]
    return [part for part in parts if part and part != "[]" and part not in ignored_roots]


def _match_field_meta(field_meta: dict[str, Any], field_code: str, field_path: str) -> Any | None:
    if field_code in field_meta:
        return field_meta[field_code]
    leaf = field_path.split(".")[-1]
    return field_meta.get(leaf)


def _looks_like_2d_field_array(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(row, list) for row in value)
        and all(isinstance(item, dict) for row in value for item in row)
    )


def _parse_mapping_path(
    mapping_path: str,
    *,
    default_location: str,
) -> tuple[str, list[str]]:
    normalized_default = _normalize_mapping_location(default_location)
    if not mapping_path.startswith("$."):
        return normalized_default, []
    parts = [part for part in mapping_path[2:].split(".") if part]
    if not parts:
        return normalized_default, []
    first_part = parts[0]
    if first_part in _MAPPING_LOCATION_ALIASES:
        return _normalize_mapping_location(first_part), parts[1:]
    return normalized_default, parts


def _normalize_mapping_location(location: str) -> str:
    return _MAPPING_LOCATION_ALIASES.get(location, location)


def _schema_location_key(location: str) -> str:
    return _LOCATION_SCHEMA_KEYS.get(_normalize_mapping_location(location), location)


def _ensure_object_schema(schema: dict[str, Any]) -> None:
    schema.setdefault("type", "object")
    properties = schema.setdefault("properties", {})
    if not isinstance(properties, dict):
        schema["properties"] = {}


def _ensure_array_object_schema(schema: dict[str, Any]) -> dict[str, Any]:
    schema.setdefault("type", "array")
    items = schema.setdefault("items", {"type": "object", "properties": {}})
    if not isinstance(items, dict):
        items = {"type": "object", "properties": {}}
        schema["items"] = items
    _ensure_object_schema(items)
    return items


def _append_required(schema: dict[str, Any], field_name: str) -> None:
    required = schema.setdefault("required", [])
    if isinstance(required, list) and field_name not in required:
        required.append(field_name)


def _assign_schema_path(
    root: dict[str, Any],
    path_parts: list[str],
    leaf_schema: dict[str, Any],
    *,
    required: bool,
) -> None:
    if not path_parts:
        _ensure_object_schema(root)
        properties = root.setdefault("properties", {})
        if isinstance(properties, dict):
            properties.update(leaf_schema)
        return

    current = root
    for index, raw_part in enumerate(path_parts):
        is_last = index == len(path_parts) - 1
        is_array = raw_part.endswith("[]")
        part = raw_part[:-2] if is_array else raw_part
        if not part:
            continue
        _ensure_object_schema(current)
        properties = current.setdefault("properties", {})
        if not isinstance(properties, dict):
            properties = {}
            current["properties"] = properties

        if is_last:
            properties[part] = {"type": "array", "items": leaf_schema} if is_array else leaf_schema
            if required:
                _append_required(current, part)
            return

        if required:
            _append_required(current, part)
        if is_array:
            node = properties.setdefault(
                part, {"type": "array", "items": {"type": "object", "properties": {}}}
            )
            if not isinstance(node, dict):
                node = {"type": "array", "items": {"type": "object", "properties": {}}}
                properties[part] = node
            current = _ensure_array_object_schema(node)
        else:
            node = properties.setdefault(part, {"type": "object", "properties": {}})
            if not isinstance(node, dict):
                node = {"type": "object", "properties": {}}
                properties[part] = node
            _ensure_object_schema(node)
            current = node


def _is_array_object_schema(schema: dict[str, Any]) -> bool:
    return _array_object_item_schema(schema) is not None


def _array_object_item_variants(schema: dict[str, Any]) -> list[dict[str, Any]]:
    items = schema.get("items")
    if not isinstance(items, dict):
        return []
    if str(items.get("type") or "").lower() == "object":
        return [dict(items)]
    variants = items.get("oneOf") or items.get("anyOf")
    if not isinstance(variants, list):
        return []
    return [
        dict(variant)
        for variant in variants
        if isinstance(variant, dict) and str(variant.get("type") or "").lower() == "object"
    ]


def _array_object_item_schema(schema: dict[str, Any]) -> dict[str, Any] | None:
    object_variants = _array_object_item_variants(schema)
    if not object_variants:
        return None
    if len(object_variants) == 1:
        return object_variants[0]
    merged = _merge_object_schema_variants(object_variants)
    merged["oneOf"] = object_variants
    return merged


def _filter_condition_options(schema: dict[str, Any]) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for variant in _array_object_item_variants(schema):
        properties = variant.get("properties")
        if not isinstance(properties, dict):
            continue
        field_schema = properties.get("field")
        op_schema = properties.get("op")
        if not isinstance(field_schema, dict) or not isinstance(op_schema, dict):
            continue
        field_codes = _schema_options(field_schema)
        operators = _schema_options(op_schema)
        if not field_codes or not operators:
            continue
        for field_code in field_codes:
            options.append(
                {
                    "fieldCode": field_code,
                    "fieldName": _filter_field_name(variant, field_schema, field_code),
                    "operators": operators,
                }
            )
    return options


def _filter_field_name(
    variant: dict[str, Any],
    field_schema: dict[str, Any],
    field_code: str,
) -> str:
    for text in (
        str(variant.get("description") or ""),
        str(field_schema.get("description") or ""),
    ):
        parsed = _extract_text_between(text, "（", "）") or _extract_text_between(text, "(", ")")
        if parsed and parsed != field_code:
            return parsed
        if "（" in text:
            prefix = text.split("（", 1)[0].strip()
            if prefix:
                return prefix
        if "(" in text:
            prefix = text.split("(", 1)[0].strip()
            if prefix:
                return prefix
    return field_code


def _extract_text_between(text: str, start: str, end: str) -> str:
    if start not in text:
        return ""
    tail = text.split(start, 1)[1]
    if end not in tail:
        return ""
    return tail.split(end, 1)[0].strip()


def _schema_for_array_item_value(item_schema: dict[str, Any], item_value: Any) -> dict[str, Any]:
    variants = item_schema.get("oneOf") or item_schema.get("anyOf")
    if isinstance(item_value, dict) and isinstance(variants, list):
        matched = _match_object_schema_variant(variants, item_value)
        if matched is not None:
            return matched
    return item_schema


def _match_object_schema_variant(
    variants: list[Any],
    item_value: dict[str, Any],
) -> dict[str, Any] | None:
    field_value = item_value.get("field")
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        properties = variant.get("properties")
        if not isinstance(properties, dict):
            continue
        field_schema = properties.get("field")
        if not isinstance(field_schema, dict):
            continue
        enum_values = field_schema.get("enum")
        if isinstance(enum_values, list) and field_value in enum_values:
            return dict(variant)
    return None


def _merge_object_schema_variants(variants: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "object",
        "properties": {},
    }
    required: list[str] = []
    for variant in variants:
        for field_name in list(variant.get("required") or []):
            if isinstance(field_name, str) and field_name not in required:
                required.append(field_name)
        properties = variant.get("properties")
        if not isinstance(properties, dict):
            continue
        for key, schema_raw in properties.items():
            if not isinstance(schema_raw, dict):
                continue
            existing = result["properties"].get(key)
            result["properties"][key] = (
                _merge_property_schema(existing, schema_raw)
                if isinstance(existing, dict)
                else dict(schema_raw)
            )
    if required:
        result["required"] = required
    return result


def _merge_property_schema(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    if not merged.get("type") and right.get("type"):
        merged["type"] = right.get("type")
    if not merged.get("description") and right.get("description"):
        merged["description"] = right.get("description")
    merged["enum"] = _merge_list_values(merged.get("enum"), right.get("enum"))
    return {key: value for key, value in merged.items() if value not in (None, [])}


def _merge_list_values(left: Any, right: Any) -> list[Any]:
    values: list[Any] = []
    for source in (left, right):
        if not isinstance(source, list):
            continue
        for item in source:
            if item not in values:
                values.append(item)
    return values


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _normalize_rule_rows(rule: list[Any]) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = []
    for row in rule:
        if isinstance(row, list):
            fields = [dict(item) for item in row if isinstance(item, dict)]
            if fields:
                rows.append(fields)
    return rows


def _fields_to_object(
    fields: list[dict[str, Any]],
    *,
    use_field_path: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in fields:
        field_code = str(field.get("fieldCode") or "").strip()
        if not field_code:
            continue
        field_path = str(field.get("fieldPath") or "").strip()
        result_key = field_path if use_field_path and field_path else field_code
        field_type = _field_type_family(str(field.get("fieldType") or ""))
        value = field.get("fieldValue")
        children = field.get("children")
        if field_type == "object":
            nested_value = children if isinstance(children, list) else value
            rows = _normalize_rule_rows(nested_value if isinstance(nested_value, list) else [])
            value = _fields_to_object(rows[0]) if rows else {}
        elif field_type == "array" and (
            _looks_like_2d_field_array(children) or _looks_like_2d_field_array(value)
        ):
            nested_value = children if _looks_like_2d_field_array(children) else value
            rows = _normalize_rule_rows(nested_value if isinstance(nested_value, list) else [])
            value = [_fields_to_object(row) for row in rows]
        result[result_key] = value
    return result


def _set_path_value(target: dict[str, Any], field_path: str, value: Any) -> None:
    parts = [part for part in field_path.split(".") if part]
    if not parts:
        return
    cursor = target
    for part in parts[:-1]:
        next_value = cursor.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            cursor[part] = next_value
        cursor = next_value
    cursor[parts[-1]] = value


def _filter_restored_params(params: dict[str, Any], action: Any | None) -> dict[str, Any]:
    if action is None:
        return params
    schema = _get_action_input_schema(action)
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return params
    allowed = set(properties) | {_CONFIRM_PARAM, _OPERATION_CONFIRM_PARAM}
    return {key: value for key, value in params.items() if key in allowed}


def _build_form_id(action: Any, params: dict[str, Any]) -> str:
    action_code = str(getattr(action, "action_code", "") or "operation")
    digest = _stable_hash({"actionCode": action_code, "params": params})[:16]
    return f"op_form_{digest}"


def _build_item_id(form_id: str, index: int) -> str:
    return f"{form_id}_item_{index:03d}"


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
