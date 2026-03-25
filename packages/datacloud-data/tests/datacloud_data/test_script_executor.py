import pytest
from datacloud_data_sdk.executor.script_executor import ScriptExecutor
from datacloud_data_sdk.context import InvocationContext
from datacloud_data_sdk.exceptions import ScriptExecutionError


@pytest.mark.asyncio
async def test_script_executor_runs_simple_script() -> None:
    executor = ScriptExecutor()
    script = "def execute(params):\n    return {'sum': params['a'] + params['b']}"
    with InvocationContext(tenant_id="t1"):
        result = await executor.execute(script, {"a": 1, "b": 2})
    assert result == {"sum": 3}


@pytest.mark.asyncio
async def test_script_executor_injects_context() -> None:
    executor = ScriptExecutor()
    script = "def execute(params):\n    return {'tid': context.tenant_id}"
    with InvocationContext(tenant_id="test_tenant"):
        result = await executor.execute(script, {})
    assert result == {"tid": "test_tenant"}


@pytest.mark.asyncio
async def test_script_executor_raises_on_error() -> None:
    executor = ScriptExecutor()
    script = "def execute(params):\n    raise ValueError('bad input')"
    with InvocationContext(tenant_id="t1"):
        with pytest.raises(ScriptExecutionError, match="bad input"):
            await executor.execute(script, {})


@pytest.mark.asyncio
async def test_script_executor_raises_on_missing_execute() -> None:
    executor = ScriptExecutor()
    script = "def wrong_name(params):\n    return {}"
    with InvocationContext(tenant_id="t1"):
        with pytest.raises(ScriptExecutionError, match="execute"):
            await executor.execute(script, {})


@pytest.mark.asyncio
async def test_script_priority_over_api() -> None:
    """验证 script 存在时优先执行。"""
    executor = ScriptExecutor()
    script = "def execute(params):\n    return {'source': 'script'}"
    with InvocationContext(tenant_id="t1"):
        result = await executor.execute(script, {})
    assert result["source"] == "script"
