# OpenClaw Gateway Phase 2 Implementation Notes

## Project Context
- **Plan**: openclaw-gateway-phase2-optimized
- **Worktree**: /home/luoyanzhuo/project/whale_datacloud-worktrees/openclaw-gateway-implementation
- **Goal**: Replace mock code with actual deepagents integration
- **Tech Stack**: Python 3.12+, deepagents 0.4.7, LangGraph 1.0.10, 阿里云百炼Qwen

## Key Design Decisions

### 1. Backend vs Sandbox (Critical Finding)
- `create_deep_agent()` has **NO `sandbox` parameter**
- Use `backend` parameter instead: `LocalShellBackend`, `FilesystemBackend`
- Production recommendation: backend + custom Docker sandbox

### 2. POC Validation Results
| POC | Feature | Status |
|-----|---------|--------|
| 1 | Basic integration | ✅ Verified |
| 2 | Token counting | ✅ Verified |
| 3 | STEER mode | ✅ Verified |
| 4 | Tool system | ✅ Verified |
| 5 | SubAgent | ✅ Verified |
| 6 | Streaming | ✅ Verified |
| 7 | Backend | ✅ Verified (2026-03-10) |

### 3. Multi-tenant Architecture (Already Implemented)
- Tenant resolution from X-Tenant-ID header
- Four-level organization: App → User → Session → Task
- TenantAwareFileBackend for path routing

## Environment Configuration
```bash
export OPENAI_API_KEY="sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
export OPENAI_BASE_URL="https://lab.iwhalecloud.com/gpt-proxy/v1"
export MODEL_NAME="openai:qwen3.5-plus"
```

## Task Progress Tracking

### Wave 0: Backend Verification (1 day)
- [x] Task 0.1: Verify deepagents backend functionality (COMPLETED 2026-03-10)
- [ ] Task 0.2: Adjust plan based on verification results

### Wave 1: Core Integration (3-4 days)
- [x] Task 1.1: Configure model and deepagents dependencies (COMPLETED - dependencies already in pyproject.toml)
- [x] Task 1.2: Create model configuration module (COMPLETED 2026-03-10)
- [x] Task 1.3: Create tool definitions module (COMPLETED 2026-03-10)
- [x] Task 1.4: Refactor AgentRunner with deepagents (COMPLETED 2026-03-10)
- [ ] Task 1.5: Implement subAgent configuration support
- [ ] Task 1.6: Update AgentRegistry with security validation

### Wave 2: Queue Strategy (2-3 days)
- [ ] Task 2.1: Implement SUMMARIZE drop policy
- [ ] Task 2.2: Implement all queue modes

### Wave 3: Integration Testing (1-2 days)
- [ ] Task 3.1: Create end-to-end integration tests
- [ ] Task 3.2: Create POC verification script

### Wave 4: Documentation (0.5 day)
- [ ] Task 4.1: Update architecture documentation
- [ ] Task 4.2: Run full test suite

## Conventions

### Code Style
- Use type hints
- Follow existing codebase patterns
- Write tests for all new modules

### Commit Messages
- Format: `type(scope): description`
- Types: feat, fix, test, docs, refactor, chore

### Testing
- Unit tests for each module
- Integration tests for end-to-end flows
- Incremental validation after each Wave 1 task

## Issues & Blockers

*Track any issues encountered during implementation*

## Decisions Log

### 2026-03-10: Backend Verification Results (Task 0.1)

**Test File**: `poc_tests/test_poc7_backend.py`

**Key Findings**:
1. **backend parameter IS supported** (not 'sandbox')
   - `LocalShellBackend`: Provides command execution, file operations
   - `FilesystemBackend`: File operations only, no command execution
   - Both support `virtual_mode` for path-based routing

2. **Built-in tools work correctly**:
   - `write_file`: Creates/updates files
   - `read_file`: Reads file contents with line numbers
   - `ls`: Lists directory contents

3. **Isolation level is LOW**:
   - LocalShellBackend: Commands execute on host system
   - No process isolation, no container support
   - NOT suitable for multi-tenant scenarios without additional sandboxing

**Additional Backend Options Discovered**:
- `CompositeBackend`: For routing multiple backends
- `StateBackend`: For state management
- `StoreBackend`: For store management

**BackendProtocol Operations**:
- File: `read`, `write`, `edit`, `ls_info`, `glob_info`, `grep_raw`
- Async variants: `aread`, `awrite`, `aedit`, etc.
- Upload/Download: `upload_files`, `download_files`, `aupload_files`, `adownload_files`

**Recommendations**:
1. Use `FilesystemBackend` for file operations in production
2. Implement custom Docker sandbox for command execution
3. Consider container-based isolation for multi-tenant scenarios

**Dependencies Added**:
- `deepagents>=0.4.7`
- `langchain-openai` (required for model initialization)

## Task 1.2: Model Configuration Module (COMPLETED 2026-03-10)

**Files Created**:
- `datacloud-agent/src/datacloud_agent/core/model_config.py`
- `datacloud-agent/tests/test_model_config.py`

**Implementation Details**:
- Uses `langchain_openai.ChatOpenAI` for model initialization
- Default model: `openai:qwen3.5-plus`
- Supports config dict or environment variables (OPENAI_API_KEY, OPENAI_BASE_URL)
- Raises ValueError when API key is missing

**Tests**: 14 unit tests, all passing

**Code Pattern**:
```python
from datacloud_agent.core.model_config import create_model, get_default_model_config

# Get default config
config = get_default_model_config()

# Create model with custom config
model = create_model({"model": "openai:qwen3.5-plus", "api_key": "..."})
```

## Task 1.3: Tool Definitions Module (COMPLETED 2026-03-10)

**Files Created**:
- `datacloud-agent/src/datacloud_agent/core/tools.py`
- `datacloud-agent/tests/test_tools.py`

**Implementation Details**:
- Uses `langchain_core.tools.tool` decorator for all 5 atomic tools
- Each tool has detailed docstrings with Chinese descriptions, Args, and Returns
- `get_business_tools()` returns list of all 5 tools
- `get_system_prompt()` returns system prompt forcing tool usage

**5 Atomic Tools**:
1. `know(query: str) -> str` - Knowledge retrieval
2. `query(data: str) -> str` - Data query (NL2Data)
3. `compute(expression: str) -> str` - Computation
4. `render(format_type: str, content: str) -> str` - Rendering
5. `store(key: str, value: str) -> str` - Storage

**Tests**: 26 unit tests, all passing

**Code Pattern**:
```python
from langchain_core.tools import tool
from datacloud_agent.core.tools import get_business_tools, get_system_prompt

# Get all tools
tools = get_business_tools()

# Get system prompt
prompt = get_system_prompt()
```

**Key Finding**:
- LangChain `@tool` decorator wraps functions in `StructuredTool` objects
- Tools have `.invoke()` method rather than being directly callable
- Tool descriptions are auto-generated from docstrings
