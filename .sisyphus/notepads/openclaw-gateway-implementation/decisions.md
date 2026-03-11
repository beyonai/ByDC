# OpenClaw Gateway Implementation - Decisions

## Test Strategy Decisions

### 2025-03-09: Integration Test Approach
- **Decision**: Rely on mocked integration tests for SDK and Service components, with separate unit tests for each layer.
- **Rationale**: Faster test execution, easier isolation of failures, and sufficient coverage for component correctness.
- **Alternatives Considered**: Full end-to-end tests with real service instances; deemed too heavy for CI pipeline.
- **Impact**: Lightweight CI runs, but missing real network integration validation.

### 2025-03-09: Pydantic Version Compatibility
- **Decision**: Keep using Pydantic v2 with deprecated `json()` method for now, as tests pass.
- **Rationale**: Low priority; will address when upgrading Pydantic version.
- **Alternatives**: Immediate fix to `model_dump_json()`.
- **Impact**: Warning during tests but no functional breakage.