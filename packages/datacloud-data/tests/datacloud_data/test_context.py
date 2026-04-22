import pytest
from datacloud_data_sdk.context import InvocationContext, get_current_context, get_tool_call_detail
from datacloud_data_sdk.exceptions import DatacloudError


def test_context_stores_values() -> None:
    with InvocationContext(tenant_id="t1", user_id="u1", token="tok", tool_call_detail=True):
        ctx = get_current_context()
        assert ctx.tenant_id == "t1"
        assert ctx.user_id == "u1"
        assert ctx.token == "tok"
        assert ctx.tool_call_detail is True


def test_context_resets_after_exit() -> None:
    with InvocationContext(tenant_id="t1"):
        pass
    with pytest.raises(DatacloudError, match="InvocationContext"):
        get_current_context()


def test_nested_contexts_isolated() -> None:
    with InvocationContext(tenant_id="outer"):
        with InvocationContext(tenant_id="inner"):
            assert get_current_context().tenant_id == "inner"
        assert get_current_context().tenant_id == "outer"


def test_get_tool_call_detail_defaults_to_false_without_context() -> None:
    assert get_tool_call_detail() is False
