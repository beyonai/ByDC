# OpenClaw Gateway Implementation - Issues

## Test Run Issues (2025-03-09)

### SDK Test Warnings
1. **RuntimeWarning**: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited
   - File: `datacloud-agent/src/datacloud_agent/core/runner.py:402`
   - Impact: Low - test passes, but indicates potential resource leak in mock cleanup
   - Recommendation: Ensure proper cleanup of async mocks in test fixtures

### Service Test Warnings
1. **PydanticDeprecatedSince20**: The `json` method is deprecated; use `model_dump_json` instead.
   - File: `service/datacloud-agent-service/routers/chat.py:154`
   - Impact: Medium - compatibility with future Pydantic versions
   - Recommendation: Update to `model_dump_json()` for Pydantic v2 compatibility

## Integration Issues
- No direct end-to-end integration tests between SDK and Service (both sides mock each other)
- Consider adding a lightweight integration test that uses real HTTP client with test server