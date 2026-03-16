import pytest
from datacloud_data.context import InvocationContext, get_current_context
from datacloud_data.exceptions import DatacloudError


def test_context_stores_values() -> None:
    with InvocationContext(tenant_id="t1", user_id="u1", token="tok"):
        ctx = get_current_context()
        assert ctx.tenant_id == "t1"
        assert ctx.user_id == "u1"
        assert ctx.token == "tok"


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
