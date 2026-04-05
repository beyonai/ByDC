"""
动作(Action)实体模块

本模块定义了 Action 类，用于封装本体动作(OntologyAction)，提供 schema 生成与执行能力。
Action 是数据服务中执行操作的核心抽象，支持多种执行方式：脚本执行、API调用、虚拟查询等。

核心功能：
- 动作 schema 生成：生成符合 JSON Schema 规范的输入输出定义
- 参数映射：支持参数名/别名的自动映射
- 多执行模式：script(脚本) -> function_refs(API) -> 虚拟查询
- 术语解析：自动解析业务术语到实际值

执行优先级：
1. is_virtual=True: 执行虚拟查询（动态构建 SQL）
2. script 存在: 执行脚本代码
3. function_refs 存在: 调用外部 API
4. 否则抛出 ActionNotConfiguredError

使用示例：
    action = Action(ontology_action, loader=ontology_loader)
    schema = action.get_schema()  # 获取 JSON Schema
    result = await action.execute({"param1": "value1"})  # 执行动作
"""

from __future__ import annotations

import logging
from typing import Any

from datacloud_data_sdk.ontology.models import OntologyAction, OntologyActionParam

logger = logging.getLogger(__name__)

def _default_query_output_schema() -> dict[str, object]:
    """
    生成虚拟动作的默认输出 schema

    虚拟动作通常返回记录列表和总数，此函数提供标准化的输出格式定义。

    Returns:
        dict: 包含 records 数组和 total 整数的 JSON Schema
    """
    return {
        "type": "object",
        "properties": {
            "records": {"type": "array", "items": {"type": "object"}, "description": "记录行"},
            "total": {"type": "integer", "description": "总条数"},
        },
    }


PARAM_TYPE_MAP: dict[str, str] = {
    "STRING": "string",
    "NUMBER": "number",
    "DECIMAL": "number",
    "INTEGER": "integer",
    "BIGINT": "integer",
    "BOOLEAN": "boolean",
    "DATE": "string",
    "DATETIME": "string",
    "ARRAY": "array",
    "LIST": "array",
    "OBJECT": "object",
}
"""本体参数类型到 JSON Schema 类型的映射表

将本体定义中的参数类型（如 STRING, INTEGER）映射到 JSON Schema 标准类型。
"""


class Action:
    """
    动作实体类，提供 schema 生成与执行能力

    Action 是数据服务中执行操作的核心抽象。每个动作对应一个本体中定义的操作，
    可以是数据库查询、API调用或脚本执行。

    执行优先级：
        1. is_virtual=True: 执行虚拟查询（动态构建 SQL）
        2. script 存在: 执行脚本代码
        3. function_refs 存在: 调用外部 API
        4. 否则抛出 ActionNotConfiguredError

    Attributes:
        _action: 本体动作定义对象
        _loader: 本体加载器，用于获取相关配置和资源

    Example:
        action = Action(ontology_action, loader=ontology_loader)
        schema = action.get_schema()
        result = await action.execute({"status": "active"})
    """

    def __init__(self, ontology_action: OntologyAction, loader: Any = None) -> None:
        """
        初始化动作实体

        Args:
            ontology_action: 本体动作定义
            loader: 本体加载器实例，用于获取数据源配置等
        """
        self._action = ontology_action
        self._loader = loader

    @property
    def action_code(self) -> str:
        """动作代码，唯一标识此动作"""
        return self._action.action_code

    @property
    def has_script(self) -> bool:
        """是否配置了执行脚本"""
        return bool(self._action.script)

    def get_schema(self) -> dict[str, object]:
        """
        生成动作的 JSON Schema

        生成包含 name, title, description, inputSchema, outputSchema 的完整 schema。
        结果会被缓存，避免重复计算。

        Returns:
            dict: 包含动作元数据和输入输出 schema 的字典
        """
        if self._action._schema_cache is not None:
            return self._action._schema_cache
        if self._action.input_schema is not None:
            inp = self._action.input_schema
            out = self._action.output_schema or _default_query_output_schema()
        else:
            in_params = [p for p in self._action.params if p.direction in ("IN", "INOUT")]
            out_params = [p for p in self._action.params if p.direction in ("OUT", "INOUT")]
            inp = self._build_schema(in_params)
            out = self._build_schema(out_params)
        result = {
            "name": self._action.action_code,
            "title": self._action.action_name or self._action.action_code,
            "description": self._action.description or self._action.action_name or "",
            "inputSchema": inp,
            "outputSchema": out,
        }
        self._action._schema_cache = result
        return result

    def _build_schema(self, params: list[OntologyActionParam]) -> dict[str, object]:
        """
        从参数列表构建 JSON Schema

        Args:
            params: 动作参数列表

        Returns:
            dict: JSON Schema 对象
        """
        properties: dict[str, dict[str, object]] = {}
        required: list[str] = []
        for p in params:
            prop: dict[str, object] = {
                "type": PARAM_TYPE_MAP.get(p.param_type.upper(), "string"),
                "description": p.param_name,
            }
            if p.default_value is not None:
                prop["default"] = p.default_value
            properties[p.param_code] = prop
            if p.required:
                required.append(p.param_code)
        schema: dict[str, object] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    def _map_names(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        将参数名/别名映射为标准的参数代码

        支持使用 param_name 或 alias 作为参数名，自动转换为 param_code。

        Args:
            arguments: 原始参数字典，可能使用别名作为键

        Returns:
            dict: 键为 param_code 的参数字典
        """
        alias_map: dict[str, str] = {}
        for p in self._action.params:
            alias_map[p.param_code] = p.param_code
            alias_map[p.param_name] = p.param_code
        mapped: dict[str, Any] = {}
        for key, value in arguments.items():
            param_code = alias_map.get(key, key)
            mapped[param_code] = value
        return mapped

    async def execute(self, params: dict[str, object]) -> dict[str, object]:
        """
        执行动作

        完整的执行流程：
        1. 参数映射：将参数名/别名转换为标准 param_code
        2. 术语解析：解析业务术语到实际值
        3. 执行操作：按优先级选择执行方式（虚拟查询/脚本/API）
        4. 结果标准化：统一返回格式

        Args:
            params: 执行参数字典

        Returns:
            dict: 标准化的执行结果，包含 records, total, meta 等字段

        Raises:
            ActionNotConfiguredError: 动作未配置执行方式
        """
        from datacloud_data_sdk.exceptions import ActionNotConfiguredError

        params = dict(params)
        term_loader = (
            getattr(self._loader._config, "term_loader", None)
            if self._loader
            else None
        )

        from datacloud_data_sdk.result_formatter import build_query_response
        from datacloud_data_sdk.csv_storage.manager import CsvStorageManager

        cfg = self._loader._config if self._loader else None
        threshold = cfg.query_result_csv_threshold if cfg else 0
        preview_rows = cfg.query_result_preview_rows if cfg else 5
        csv_manager = CsvStorageManager(cfg.csv_base_dir if cfg else "/tmp/datacloud_csv")

        if getattr(self._action, "is_virtual", False):
            if term_loader and "filters" in params and isinstance(params.get("filters"), dict):
                cls = self._loader.get_ontology_class(
                    getattr(self._action, "belong_class", "") or ""
                )
                if cls and cls.fields:
                    from datacloud_data_sdk.plan.term_resolver import TermResolver

                    tr = TermResolver(term_loader)
                    params["filters"] = tr.resolve_filter_values(
                        params["filters"], cls.fields
                    )
            result = await self._execute_virtual(params)
            normalized = self._normalize_to_unified_format(result)
            return build_query_response(
                normalized,
                csv_manager=csv_manager,
                threshold=threshold,
                preview_rows=preview_rows,
            )

        params = self._map_names(params)
        if term_loader:
            from datacloud_data_sdk.plan.term_resolver import TermResolver

            params = TermResolver(term_loader).resolve(self._action, params)

        if self._action.script:
            result = await self._execute_script(params)
            normalized = self._normalize_to_unified_format(result)
            return build_query_response(
                normalized,
                csv_manager=csv_manager,
                threshold=threshold,
                preview_rows=preview_rows,
            )
        if self._action.function_refs:
            from datacloud_data_sdk.plan.param_converter import (
                _to_function_param,
                map_to_physical,
            )

            in_params = [
                _to_function_param(p)
                for p in self._action.params
                if getattr(p, "direction", "IN") in ("IN", "INOUT")
            ]
            physical_params = map_to_physical(params, in_params)
            result = await self._execute_api(physical_params)
            normalized = self._normalize_to_unified_format(result)
            return build_query_response(
                normalized,
                csv_manager=csv_manager,
                threshold=threshold,
                preview_rows=preview_rows,
            )
        raise ActionNotConfiguredError(self._action.action_code)

    async def _execute_virtual(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        执行虚拟查询动作

        虚拟动作不预定义 SQL，而是根据参数动态构建查询。
        通常用于对象的基础查询操作。

        Args:
            params: 查询参数，包含 filters, page, page_size 等

        Returns:
            dict: 包含 records 和 total 的原始结果

        Raises:
            ActionNotConfiguredError: 未配置 loader 时抛出
        """
        from datacloud_data_sdk.executor.dynamic_query_executor import DynamicQueryExecutor

        if not self._loader:
            from datacloud_data_sdk.exceptions import ActionNotConfiguredError

            raise ActionNotConfiguredError(self._action.action_code)

        object_code = getattr(self._action, "belong_class", "") or ""
        executor = DynamicQueryExecutor(self._loader)
        return await executor.execute(object_code, params)

    async def _execute_script(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        执行脚本动作

        通过 ScriptExecutor 执行预定义的脚本代码，
        支持从返回结果中提取记录数据。

        Args:
            params: 脚本执行参数

        Returns:
            dict: 标准化的结果格式
        """
        from datacloud_data_sdk.executor.script_executor import ScriptExecutor

        executor = ScriptExecutor(ontology_loader=self._loader)
        result = await executor.execute(
            self._action.script,  # type: ignore[arg-type]
            params,
            action_code=self._action.action_code,
        )
        if not isinstance(result, dict):
            return {"records": [], "total": 0, "meta": {"viewId": "auto_view", "columns": [], "total": 0}}
        out_params = [
            (p.param_code, p.mapping_path)
            for p in self._action.params
            if getattr(p, "direction", "IN") in ("OUT", "INOUT") and getattr(p, "mapping_path", "")
        ]
        if out_params:
            from datacloud_data_sdk.executor.response_mapping import extract_by_mapping_path

            records = extract_by_mapping_path(result, out_params)
            columns = [p[0] for p in out_params]
        else:
            records = self._extract_records_fallback(result)
            columns = list(records[0].keys()) if records and isinstance(records[0], dict) else []
        return {
            "records": records,
            "total": len(records),
            "meta": {"viewId": "auto_view", "columns": columns, "total": len(records)},
        }

    async def _execute_api(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        通过 HTTP API 执行动作

        调用外部 API 服务执行动作，支持：
        - 自动构建请求 URL 和 headers
        - 请求日志记录（curl 格式）
        - 响应数据提取和标准化

        Args:
            params: API 请求参数

        Returns:
            dict: 标准化的结果格式

        Raises:
            ActionNotConfiguredError: 未配置 function 或 loader
            ApiExecutionError: API 调用失败时抛出
        """
        import httpx

        from datacloud_data_sdk.exceptions import ActionNotConfiguredError, ApiExecutionError
        from datacloud_data_sdk.utils.curl_logger import log_curl

        if not self._loader:
            raise ActionNotConfiguredError(self._action.action_code)

        function_code = self._action.function_refs[0]
        config = self._loader.get_function_config(function_code)
        if not config:
            raise ActionNotConfiguredError(self._action.action_code)

        url = self._build_url(config)
        headers = self._build_headers()

        log_curl("POST", url, headers=headers, body=params)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=params, headers=headers)

        if resp.status_code >= 400:
            raise ApiExecutionError(function_code, resp.status_code, resp.text)

        raw = resp.json()
        out_params = [
            (p.param_code, p.mapping_path)
            for p in self._action.params
            if getattr(p, "direction", "IN") in ("OUT", "INOUT") and getattr(p, "mapping_path", "")
        ]
        if out_params:
            from datacloud_data_sdk.executor.response_mapping import extract_by_mapping_path

            records = extract_by_mapping_path(raw, out_params)
            columns = [p[0] for p in out_params]
        else:
            records = self._extract_records_fallback(raw)
            columns = list(records[0].keys()) if records and isinstance(records[0], dict) else []
        return {
            "records": records,
            "total": len(records),
            "meta": {"viewId": "auto_view", "columns": columns, "total": len(records)},
        }

    def _build_url(self, config: dict[str, Any]) -> str:
        servers = config.get("servers", [])
        base_url = servers[0]["url"] if servers else "http://localhost:8080"
        paths = config.get("paths", {})
        path = next(iter(paths), "")
        return f"{base_url}{path}"

    def _build_headers(self) -> dict[str, str]:
        from datacloud_data_sdk.context import get_current_context

        headers: dict[str, str] = {"Content-Type": "application/json"}
        try:
            ctx = get_current_context()
            if ctx.token:
                headers["Authorization"] = f"Bearer {ctx.token}"
            if ctx.tenant_id:
                headers["X-Tenant-Id"] = ctx.tenant_id
        except Exception as exc:
            logger.debug("_build_headers: failed to inject auth context: %s", exc)
        return headers

    def _extract_records_fallback(self, data: Any) -> list[dict[str, Any]]:
        """从 API 原始响应按常见 key 兜底提取 records。"""
        if isinstance(data, list):
            return data if data and isinstance(data[0], dict) else [{"value": data}] if data else []
        if isinstance(data, dict):
            for key in ("data", "records", "items", "list", "users", "results", "opportunities"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            return [data]
        return [{"value": data}]

    def _normalize_to_unified_format(self, result: dict[str, Any]) -> dict[str, Any]:
        """将任意 dict 归一化为 {records, total, meta} 统一结构。"""
        if not isinstance(result, dict):
            return {
                "records": [],
                "total": 0,
                "meta": {"viewId": "auto_view", "columns": [], "total": 0},
            }
        if "records" in result and "meta" in result:
            meta = result.get("meta", {})
            meta.setdefault("viewId", "auto_view")
            meta.setdefault("total", result.get("total", len(result.get("records", []))))
            return result
        records = result.get("records")
        if records is None:
            records = [result] if result else []
        if not isinstance(records, list):
            records = [result]
        total = len(records)
        columns = list(records[0].keys()) if records and isinstance(records[0], dict) else []
        return {
            "records": records,
            "total": total,
            "meta": {"viewId": "auto_view", "columns": columns, "total": total},
        }
