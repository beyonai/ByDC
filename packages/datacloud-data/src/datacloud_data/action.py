"""Action 实体：封装 OntologyAction，提供 schema 与执行能力。"""

from __future__ import annotations

from typing import Any

from datacloud_data.ontology.models import OntologyAction, OntologyActionParam

def _default_query_output_schema() -> dict[str, object]:
    """虚拟动作默认 output schema。"""
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


class Action:
    """动作实体，提供 schema 生成与执行能力。

    执行优先级：script > function_refs(API) > ActionNotConfiguredError
    """

    def __init__(self, ontology_action: OntologyAction, loader: Any = None) -> None:
        self._action = ontology_action
        self._loader = loader

    @property
    def action_code(self) -> str:
        return self._action.action_code

    @property
    def has_script(self) -> bool:
        return bool(self._action.script)

    def get_schema(self) -> dict[str, object]:
        """生成 {name, title, description, inputSchema, outputSchema}，结果缓存。"""
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
        """将 param_name/alias 映射为标准 param_code。"""
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
        """执行动作：参数映射、术语解析、map_to_physical 自闭环，is_virtual 优先 → script → API。"""
        from datacloud_data.exceptions import ActionNotConfiguredError

        params = dict(params)
        term_loader = (
            getattr(self._loader._config, "term_loader", None)
            if self._loader
            else None
        )

        if getattr(self._action, "is_virtual", False):
            if term_loader and "filters" in params and isinstance(params.get("filters"), dict):
                cls = self._loader.get_ontology_class(
                    getattr(self._action, "belong_class", "") or ""
                )
                if cls and cls.fields:
                    from datacloud_data.plan.term_resolver import TermResolver

                    tr = TermResolver(term_loader)
                    params["filters"] = tr.resolve_filter_values(
                        params["filters"], cls.fields
                    )
            result = await self._execute_virtual(params)
            return self._normalize_to_unified_format(result)

        params = self._map_names(params)
        if term_loader:
            from datacloud_data.plan.term_resolver import TermResolver

            params = TermResolver(term_loader).resolve(self._action, params)

        if self._action.script:
            result = await self._execute_script(params)
            return self._normalize_to_unified_format(result)
        if self._action.function_refs:
            from datacloud_data.plan.param_converter import (
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
            return self._normalize_to_unified_format(result)
        raise ActionNotConfiguredError(self._action.action_code)

    async def _execute_virtual(self, params: dict[str, Any]) -> dict[str, Any]:
        """执行虚拟查询动作，返回原始数据 {"records": [], "total": 0}。"""
        from datacloud_data.executor.dynamic_query_executor import DynamicQueryExecutor

        if not self._loader:
            from datacloud_data.exceptions import ActionNotConfiguredError

            raise ActionNotConfiguredError(self._action.action_code)

        object_code = getattr(self._action, "belong_class", "") or ""
        executor = DynamicQueryExecutor(self._loader)
        return await executor.execute(object_code, params)

    async def _execute_script(self, params: dict[str, Any]) -> dict[str, Any]:
        from datacloud_data.executor.script_executor import ScriptExecutor

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
            from datacloud_data.executor.response_mapping import extract_by_mapping_path

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
        """通过 HTTP API 执行动作。"""
        import httpx

        from datacloud_data.exceptions import ActionNotConfiguredError, ApiExecutionError
        from datacloud_data.utils.curl_logger import log_curl

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
            from datacloud_data.executor.response_mapping import extract_by_mapping_path

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
        from datacloud_data.context import get_current_context

        headers: dict[str, str] = {"Content-Type": "application/json"}
        try:
            ctx = get_current_context()
            if ctx.token:
                headers["Authorization"] = f"Bearer {ctx.token}"
            if ctx.tenant_id:
                headers["X-Tenant-Id"] = ctx.tenant_id
        except Exception:
            pass
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
