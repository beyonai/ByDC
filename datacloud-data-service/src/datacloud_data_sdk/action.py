"""Action 实体：封装 OntologyAction，提供 schema 与执行能力。"""

from __future__ import annotations

from typing import Any

from datacloud_data_sdk.ontology.models import OntologyAction, OntologyActionParam

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
        """生成 {input: JSON Schema, output: JSON Schema}。"""
        in_params = [p for p in self._action.params if p.direction in ("IN", "INOUT")]
        out_params = [p for p in self._action.params if p.direction in ("OUT", "INOUT")]
        return {
            "input": self._build_schema(in_params),
            "output": self._build_schema(out_params),
        }

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

    async def execute(self, params: dict[str, object]) -> dict[str, object]:
        """执行动作：script 优先 → API → ActionNotConfiguredError。"""
        from datacloud_data_sdk.exceptions import ActionNotConfiguredError

        if self._action.script:
            return await self._execute_script(dict(params))

        if self._action.function_refs:
            return await self._execute_api(dict(params))

        raise ActionNotConfiguredError(self._action.action_code)

    async def _execute_script(self, params: dict[str, Any]) -> dict[str, Any]:
        from datacloud_data_sdk.executor.script_executor import ScriptExecutor

        executor = ScriptExecutor(ontology_loader=self._loader)
        return await executor.execute(
            self._action.script,  # type: ignore[arg-type]
            params,
            action_code=self._action.action_code,
        )

    async def _execute_api(self, params: dict[str, Any]) -> dict[str, Any]:
        """通过 HTTP API 执行动作。"""
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

        return resp.json()

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
        except Exception:
            pass
        return headers
