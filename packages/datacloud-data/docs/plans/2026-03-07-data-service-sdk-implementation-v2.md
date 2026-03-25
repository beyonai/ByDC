# Data Service SDK Implementation Plan v2

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构建可开源的 `datacloud_data` 与薄接入的 `datacloud_data_service`，完成本体解析（含脚本动作）、查询计划、执行聚合与 MCP/REST 工具链路，并用 CRM Demo 场景验证。

**Architecture:** 双子包结构，SDK 包含所有核心逻辑（本体层 → 计划层 → 执行层 → 聚合层 → 事件层），服务层只做请求解析、上下文注入与结果包装。全程 TDD：先写失败测试，再最小实现，逐层叠加。

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, LangGraph, langchain-openai, httpx, SQLAlchemy AsyncIO, aiomysql, aiosqlite, pytest, pytest-asyncio, pytest-mock

**设计文档：** `docs/plans/2026-03-06-data-service-sdk-design.md` + `docs/plans/2026-03-07-design-revision.md`

---

## P1.0 工程基础

### Task 1: 目录结构迁移 + pyproject.toml 双子包

**Files:**
- Modify: `datacloud-data/pyproject.toml`
- Delete: `datacloud-data/src/datacloud_data_service/ontology/`（空目录）
- Delete: `datacloud-data/src/datacloud_data_service/plan/`（空目录）
- Delete: `datacloud-data/src/datacloud_data_service/executor/`（空目录）
- Delete: `datacloud-data/src/datacloud_data_service/aggregator/`（空目录）
- Delete: `datacloud-data/src/datacloud_data_service/events/`（空目录）
- Delete: `datacloud-data/src/datacloud_data_service/csv_storage/`（空目录）
- Delete: `datacloud-data/src/datacloud_data_service/sql_executor/`（空目录）
- Create: `datacloud-data/src/datacloud_data/__init__.py`

**Step 1: 删除 datacloud_data_service 下不应存在的 SDK 子目录**

Run:
```bash
cd datacloud-data
rm -rf src/datacloud_data_service/ontology
rm -rf src/datacloud_data_service/plan
rm -rf src/datacloud_data_service/executor
rm -rf src/datacloud_data_service/aggregator
rm -rf src/datacloud_data_service/events
rm -rf src/datacloud_data_service/csv_storage
rm -rf src/datacloud_data_service/sql_executor
```

**Step 2: 创建 datacloud_data 包骨架**

Run:
```bash
mkdir -p src/datacloud_data_sdk
touch src/datacloud_data_sdk/__init__.py
```

**Step 3: 修改 pyproject.toml**

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/datacloud_data", "src/datacloud_data_service"]

[project]
name = "datacloud-data"
version = "0.1.0"
description = "DataCloud Data Service & SDK - 本体驱动的数据查询与执行框架"
readme = "README.md"
requires-python = ">=3.12"
license = { text = "Apache-2.0" }
authors = [
    { name = "Whale DataCloud Team" }
]
keywords = ["data", "sql", "nl2data", "query", "ontology", "mcp"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3.12",
    "License :: OSI Approved :: Apache Software License",
]

dependencies = [
    "pydantic>=2.0",
]

[project.optional-dependencies]
langchain = ["langgraph>=0.2", "langchain-openai>=0.1"]
sql = ["sqlalchemy[asyncio]>=2.0", "aiomysql>=0.2", "aiosqlite>=0.19"]
service = ["fastapi>=0.115.0", "uvicorn>=0.32.0", "pydantic-settings>=2.0"]
all = ["datacloud-data[langchain,sql,service]"]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-mock>=3.12",
    "httpx>=0.27",
    "ruff>=0.8",
    "mypy>=1.13",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
default-groups = ["dev"]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM", "ASYNC"]
ignore = ["E501"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

**Step 4: 创建测试目录**

Run:
```bash
mkdir -p tests/datacloud_data_sdk/integration
mkdir -p tests/datacloud_data_service
mkdir -p tests/e2e
touch tests/__init__.py
touch tests/datacloud_data_sdk/__init__.py
touch tests/datacloud_data_sdk/integration/__init__.py
touch tests/datacloud_data_service/__init__.py
touch tests/e2e/__init__.py
```

**Step 5: 安装依赖**

Run: `cd datacloud-data && uv pip install -e ".[all,dev]"`

Expected: 安装成功，无依赖冲突。

**Step 6: 验证双子包可导入**

Run: `cd datacloud-data && python -c "import datacloud_data; import datacloud_data_service; print('OK')"`

Expected: 输出 `OK`

---

## P1.1 本体层

### Task 2: 异常层次

**Files:**
- Create: `datacloud-data/src/datacloud_data/exceptions.py`
- Create: `datacloud-data/tests/datacloud_data/test_exceptions.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_sdk/test_exceptions.py
from datacloud_data_sdk.exceptions import (
    DatacloudError,
    ObjectNotFoundError,
    ActionNotFoundError,
    InvalidOntologyFormatError,
    PlanGenerationError,
    PlanValidationError,
    CannotAnswerError,
    ApiExecutionError,
    SqlExecutionError,
    ScriptExecutionError,
    ActionNotConfiguredError,
    DataSourceUnavailableError,
    AggregationError,
)


def test_error_hierarchy() -> None:
    assert issubclass(ObjectNotFoundError, DatacloudError)
    assert issubclass(CannotAnswerError, DatacloudError)
    assert issubclass(SqlExecutionError, DatacloudError)
    assert issubclass(ScriptExecutionError, DatacloudError)
    assert issubclass(ActionNotConfiguredError, DatacloudError)


def test_object_not_found_carries_code() -> None:
    err = ObjectNotFoundError("sales_bo")
    assert "sales_bo" in str(err)
    assert err.object_code == "sales_bo"


def test_plan_validation_error_carries_errors_list() -> None:
    err = PlanValidationError(["step_1: invalid sourceId", "aggregation: missing finalStepId"])
    assert len(err.errors) == 2


def test_script_execution_error_carries_details() -> None:
    err = ScriptExecutionError("calc_score", "NameError: x not defined", line_no=3)
    assert err.action_code == "calc_score"
    assert err.line_no == 3
    assert "NameError" in str(err)


def test_action_not_configured_error() -> None:
    err = ActionNotConfiguredError("empty_action")
    assert "empty_action" in str(err)
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data && pytest tests/datacloud_data/test_exceptions.py -v`

Expected: FAIL，ImportError

**Step 3: 实现异常层次**

```python
# src/datacloud_data_sdk/exceptions.py
"""datacloud-data-sdk 结构化异常层次。"""

from __future__ import annotations

from typing import Any


class DatacloudError(Exception):
    """SDK 所有异常的基类。"""


# --- 本体层 ---

class OntologyError(DatacloudError):
    """本体解析与查询相关错误。"""


class ObjectNotFoundError(OntologyError):
    def __init__(self, object_code: str) -> None:
        super().__init__(f"Object not found: {object_code!r}")
        self.object_code = object_code


class ActionNotFoundError(OntologyError):
    def __init__(self, object_code: str, action_code: str) -> None:
        super().__init__(f"Action {action_code!r} not found on {object_code!r}")
        self.object_code = object_code
        self.action_code = action_code


class InvalidOntologyFormatError(OntologyError):
    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"Invalid ontology at {path!r}: {reason}")
        self.path = path
        self.reason = reason


# --- 计划层 ---

class PlanError(DatacloudError):
    """查询计划相关错误。"""


class PlanGenerationError(PlanError):
    def __init__(self, question: str, cause: str) -> None:
        super().__init__(f"Plan generation failed for {question!r}: {cause}")
        self.question = question
        self.cause = cause


class PlanValidationError(PlanError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__(f"Plan validation failed: {errors}")
        self.errors = errors


class CannotAnswerError(PlanError):
    def __init__(self, clarification: str) -> None:
        super().__init__(clarification)
        self.clarification = clarification


# --- 执行层 ---

class ExecutionError(DatacloudError):
    """执行层错误基类。"""


class ApiExecutionError(ExecutionError):
    def __init__(self, function_code: str, status_code: int, body: str) -> None:
        super().__init__(f"API {function_code!r} failed [{status_code}]: {body}")
        self.function_code = function_code
        self.status_code = status_code
        self.body = body


class SqlExecutionError(ExecutionError):
    def __init__(self, datasource_alias: str, sql: str, cause: str) -> None:
        super().__init__(f"SQL failed on {datasource_alias!r}: {cause}\nSQL: {sql}")
        self.datasource_alias = datasource_alias
        self.sql = sql
        self.cause = cause


class ScriptExecutionError(ExecutionError):
    def __init__(self, action_code: str, cause: str, line_no: int | None = None) -> None:
        loc = f" (line {line_no})" if line_no else ""
        super().__init__(f"Script {action_code!r} failed{loc}: {cause}")
        self.action_code = action_code
        self.cause = cause
        self.line_no = line_no


class ActionNotConfiguredError(ExecutionError):
    def __init__(self, action_code: str) -> None:
        super().__init__(f"Action {action_code!r} has neither script nor function_refs")
        self.action_code = action_code


class DataSourceUnavailableError(ExecutionError):
    def __init__(self, alias: str) -> None:
        super().__init__(f"Datasource unavailable: {alias!r}")
        self.alias = alias


# --- 聚合层 ---

class AggregationError(DatacloudError):
    def __init__(self, strategy: str, sql: str, cause: str) -> None:
        super().__init__(f"Aggregation [{strategy}] failed: {cause}\nSQL: {sql}")
        self.strategy = strategy
        self.sql = sql
        self.cause = cause
```

**Step 4: 更新 `__init__.py` 公开 API**

```python
# src/datacloud_data_sdk/__init__.py
"""datacloud-data-sdk: 本体驱动的数据查询与执行 SDK。"""

from datacloud_data_sdk.exceptions import (
    DatacloudError,
    ObjectNotFoundError,
    ActionNotFoundError,
    ScriptExecutionError,
    ActionNotConfiguredError,
)

__all__ = [
    "DatacloudError",
    "ObjectNotFoundError",
    "ActionNotFoundError",
    "ScriptExecutionError",
    "ActionNotConfiguredError",
]
```

**Step 5: 运行测试**

Run: `cd datacloud-data && pytest tests/datacloud_data/test_exceptions.py -v`

Expected: PASS

---

### Task 3: InvocationContext

**Files:**
- Create: `datacloud-data/src/datacloud_data/context.py`
- Create: `datacloud-data/tests/datacloud_data/test_context.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_sdk/test_context.py
import pytest
from datacloud_data_sdk.context import InvocationContext, get_current_context
from datacloud_data_sdk.exceptions import DatacloudError


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
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data && pytest tests/datacloud_data/test_context.py -v`

Expected: FAIL

**Step 3: 实现 InvocationContext**

```python
# src/datacloud_data_sdk/context.py
"""请求级上下文，基于 contextvars 实现线程/协程安全。"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from types import TracebackType

from datacloud_data_sdk.exceptions import DatacloudError


@dataclass
class RequestContext:
    """请求上下文数据。"""

    tenant_id: str = ""
    user_id: str = ""
    session_id: str = ""
    token: str = ""
    system_code: str = ""


_ctx_var: contextvars.ContextVar[RequestContext | None] = contextvars.ContextVar(
    "invocation_context", default=None
)


class InvocationContext:
    """上下文管理器，在 with 块内设置请求上下文。

    Example::

        with InvocationContext(tenant_id="t1", token="xxx"):
            ctx = get_current_context()
            print(ctx.tenant_id)  # "t1"
    """

    def __init__(self, **kwargs: str) -> None:
        self._ctx = RequestContext(**{k: v for k, v in kwargs.items() if v})
        self._token: contextvars.Token[RequestContext | None] | None = None

    def __enter__(self) -> InvocationContext:
        self._token = _ctx_var.set(self._ctx)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._token is not None:
            _ctx_var.reset(self._token)


def get_current_context() -> RequestContext:
    """获取当前请求上下文，未设置时抛出异常。"""
    ctx = _ctx_var.get()
    if ctx is None:
        raise DatacloudError(
            "InvocationContext not set. Use `with InvocationContext(...):`"
        )
    return ctx
```

**Step 4: 运行测试**

Run: `cd datacloud-data && pytest tests/datacloud_data/test_context.py -v`

Expected: PASS

---

### Task 4: 本体内部模型（含 script 字段）

**Files:**
- Create: `datacloud-data/src/datacloud_data/ontology/__init__.py`
- Create: `datacloud-data/src/datacloud_data/ontology/models.py`
- Create: `datacloud-data/tests/datacloud_data/test_ontology_models.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_sdk/test_ontology_models.py
from datacloud_data_sdk.ontology.models import (
    FieldPhysicalMapping,
    OntologyField,
    OntologyActionParam,
    OntologyAction,
    OntologyRelation,
    OntologyClass,
)


def test_field_has_term_set_and_source_column() -> None:
    f = OntologyField(
        field_code="stage_code",
        field_name="商机阶段",
        field_type="STRING",
        term_set="bo_stage",
        source_column="stage_code",
    )
    assert f.term_set == "bo_stage"
    assert f.source_column == "stage_code"


def test_ontology_class_has_datasource_alias() -> None:
    cls = OntologyClass(
        object_code="sales_bo",
        object_name="销售商机",
        description="商机对象",
        source_type="DB",
        datasource_alias="crm_db",
        table_name="sales_business_opportunity",
    )
    assert cls.datasource_alias == "crm_db"
    assert cls.source_type == "DB"


def test_ontology_action_has_script_field() -> None:
    action = OntologyAction(
        action_code="calc_score",
        action_name="计算评分",
        description="",
        belong_class="sales_bo",
        params=[],
        function_refs=[],
        script="def execute(params):\n    return {'score': 100}",
    )
    assert action.script is not None
    assert "def execute" in action.script


def test_ontology_action_script_defaults_to_none() -> None:
    action = OntologyAction(
        action_code="query_bo",
        action_name="查商机",
        description="",
        belong_class="sales_bo",
        params=[],
        function_refs=["fn_get_bo"],
    )
    assert action.script is None


def test_ontology_relation_has_join_keys() -> None:
    rel = OntologyRelation(
        relation_code="bo_to_contract",
        relation_name="商机关联合同",
        source_class="sales_bo",
        target_class="sales_contract",
        relation_type="ONE_TO_MANY",
        join_keys=[{"from_field": "bo_id", "to_field": "bo_id"}],
        description="一个商机可签署多份合同",
    )
    assert rel.join_keys[0]["from_field"] == "bo_id"
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data && pytest tests/datacloud_data/test_ontology_models.py -v`

Expected: FAIL

**Step 3: 实现本体模型**

```python
# src/datacloud_data_sdk/ontology/__init__.py
```

```python
# src/datacloud_data_sdk/ontology/models.py
"""本体内部模型：OntologyClass / Field / Action / Relation。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FieldPhysicalMapping:
    """字段到物理存储的映射。"""

    source_type: str       # DB / API
    source_ref: str        # DB 列名 或 $.response.xxx
    datasource_alias: str


@dataclass
class OntologyField:
    """对象字段定义。"""

    field_code: str
    field_name: str
    field_type: str        # STRING / NUMBER / DATE / BOOLEAN / INTEGER / ARRAY / OBJECT
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    required: bool = False
    is_primary_key: bool = False
    source_column: str | None = None
    term_set: str | None = None
    physical_mappings: list[FieldPhysicalMapping] = field(default_factory=list)


@dataclass
class OntologyActionParam:
    """动作参数定义。"""

    param_code: str
    param_name: str
    direction: str         # IN / OUT / INOUT
    param_type: str
    required: bool = False
    default_value: Any = None
    mapping_path: str = ""
    term_set: str | None = None


@dataclass
class OntologyAction:
    """对象动作定义，支持 API 调用或 Python 脚本执行。

    执行优先级：script（非空）> function_refs > 抛 ActionNotConfiguredError
    """

    action_code: str
    action_name: str
    description: str
    belong_class: str
    params: list[OntologyActionParam]
    function_refs: list[str]
    script: str | None = None


@dataclass
class OntologyRelation:
    """对象间关联关系。"""

    relation_code: str
    relation_name: str = ""
    source_class: str = ""
    target_class: str = ""
    relation_type: str = ""     # ONE_TO_MANY / MANY_TO_ONE / ONE_TO_ONE / MANY_TO_MANY
    join_keys: list[dict[str, str]] = field(default_factory=list)
    description: str = ""


@dataclass
class OntologyClass:
    """本体对象/类定义。"""

    object_code: str
    object_name: str
    description: str
    source_type: str       # DB / API / KNOWLEDGE_BASE
    datasource_alias: str | None = None
    table_name: str | None = None
    tags: list[str] = field(default_factory=list)
    fields: list[OntologyField] = field(default_factory=list)
    actions: list[OntologyAction] = field(default_factory=list)
```

**Step 4: 运行测试**

Run: `cd datacloud-data && pytest tests/datacloud_data/test_ontology_models.py -v`

Expected: PASS

---

### Task 5: 术语加载器

**Files:**
- Create: `datacloud-data/src/datacloud_data/ontology/term_loader.py`
- Create: `datacloud-data/tests/datacloud_data/test_term_loader.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_sdk/test_term_loader.py
import pytest
from datacloud_data_sdk.ontology.term_loader import TermLoader


def test_resolve_by_label() -> None:
    loader = TermLoader.from_mapping(
        {"bo_stage": [{"code": "SIGNED", "label": "已签约", "aliases": ["签了合同"]}]}
    )
    assert loader.resolve_code("bo_stage", "已签约") == "SIGNED"


def test_resolve_by_alias() -> None:
    loader = TermLoader.from_mapping(
        {"bo_stage": [{"code": "SIGNED", "label": "已签约", "aliases": ["签了合同"]}]}
    )
    assert loader.resolve_code("bo_stage", "签了合同") == "SIGNED"


def test_resolve_by_exact_code() -> None:
    loader = TermLoader.from_mapping(
        {"bo_stage": [{"code": "SIGNED", "label": "已签约", "aliases": []}]}
    )
    assert loader.resolve_code("bo_stage", "SIGNED") == "SIGNED"


def test_resolve_unknown_raises() -> None:
    loader = TermLoader.from_mapping({"bo_stage": []})
    with pytest.raises(ValueError, match="available"):
        loader.resolve_code("bo_stage", "不存在的值")


def test_get_available_values() -> None:
    loader = TermLoader.from_mapping(
        {"bo_stage": [{"code": "SIGNED", "label": "已签约", "aliases": []}]}
    )
    available = loader.get_available_values("bo_stage")
    assert "已签约" in available
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data && pytest tests/datacloud_data/test_term_loader.py -v`

Expected: FAIL

**Step 3: 实现 TermLoader**

```python
# src/datacloud_data_sdk/ontology/term_loader.py
"""术语集加载与解析：code / label / aliases 多维匹配。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TermEntry:
    code: str
    label: str
    aliases: list[str] = field(default_factory=list)


class TermLoader:
    """术语集加载器，支持 code、label、alias 三种匹配方式。"""

    def __init__(self) -> None:
        self._sets: dict[str, list[TermEntry]] = {}

    @classmethod
    def from_mapping(cls, mapping: dict[str, list[dict[str, object]]]) -> TermLoader:
        loader = cls()
        for term_set, entries in mapping.items():
            loader._sets[term_set] = [
                TermEntry(
                    code=str(e["code"]),
                    label=str(e["label"]),
                    aliases=[str(a) for a in e.get("aliases", [])],  # type: ignore[union-attr]
                )
                for e in entries
            ]
        return loader

    def resolve_code(self, term_set: str, value: str) -> str:
        """将标签/别名/code 解析为标准 code。"""
        for entry in self._sets.get(term_set, []):
            if value in (entry.code, entry.label, *entry.aliases):
                return entry.code
        available = self.get_available_values(term_set)
        raise ValueError(
            f"Unknown term {value!r} in {term_set!r}. available: {available}"
        )

    def get_available_values(self, term_set: str) -> list[str]:
        """返回术语集的所有标签值。"""
        return [e.label for e in self._sets.get(term_set, [])]
```

**Step 4: 运行测试**

Run: `cd datacloud-data && pytest tests/datacloud_data/test_term_loader.py -v`

Expected: PASS

---

### Task 6: OntologyLoader（解析标准格式 + configure）

**Files:**
- Create: `datacloud-data/src/datacloud_data/ontology/loader.py`
- Create: `datacloud-data/tests/datacloud_data/test_ontology_loader.py`

**Step 1: 写失败单元测试**

```python
# tests/datacloud_data_sdk/test_ontology_loader.py
import pytest
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.exceptions import ObjectNotFoundError

MINIMAL_REGISTRY = {
    "functions": [
        {
            "function_code": "fn_get_emp",
            "function_type": "API",
            "api_schema": {
                "servers": [{"url": "http://mock:8080"}],
                "paths": {"/api/v1/emp": {"post": {}}},
            },
        }
    ],
    "objects": [
        {
            "object_code": "sales_emp",
            "object_name": "员工",
            "description": "销售员工",
            "source_type": "API",
            "fields": [
                {"field_code": "emp_id", "field_name": "员工ID", "field_type": "STRING"}
            ],
            "actions": [
                {
                    "action_code": "query_emp",
                    "action_name": "查员工",
                    "description": "",
                    "params": [],
                    "function_refs": ["fn_get_emp"],
                }
            ],
        }
    ],
    "relations": [],
}

REGISTRY_WITH_SCRIPT = {
    "functions": [],
    "objects": [
        {
            "object_code": "sales_bo",
            "object_name": "商机",
            "description": "商机对象",
            "source_type": "DB",
            "datasource_alias": "crm_db",
            "table_name": "sales_bo",
            "fields": [
                {"field_code": "bo_id", "field_name": "商机ID", "field_type": "STRING"}
            ],
            "actions": [
                {
                    "action_code": "calc_score",
                    "action_name": "计算评分",
                    "description": "计算商机评分",
                    "script": "def execute(params):\n    return {'score': 100}",
                    "function_refs": [],
                    "params": [
                        {"param_code": "bo_id", "param_name": "商机ID",
                         "direction": "IN", "param_type": "STRING", "required": True},
                        {"param_code": "score", "param_name": "评分",
                         "direction": "OUT", "param_type": "NUMBER"},
                    ],
                }
            ],
        }
    ],
    "relations": [],
}


def test_load_from_content_parses_objects() -> None:
    loader = OntologyLoader()
    loader.load_from_content(MINIMAL_REGISTRY)
    cls = loader.get_ontology_class("sales_emp")
    assert cls.object_code == "sales_emp"
    assert len(cls.fields) == 1


def test_get_unknown_object_raises() -> None:
    loader = OntologyLoader()
    loader.load_from_content(MINIMAL_REGISTRY)
    with pytest.raises(ObjectNotFoundError):
        loader.get_ontology_class("nonexistent")


def test_get_function_config_returns_api_schema() -> None:
    loader = OntologyLoader()
    loader.load_from_content(MINIMAL_REGISTRY)
    cfg = loader.get_function_config("fn_get_emp")
    assert "servers" in cfg


def test_action_script_parsed_correctly() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY_WITH_SCRIPT)
    cls = loader.get_ontology_class("sales_bo")
    action = cls.actions[0]
    assert action.script is not None
    assert "def execute" in action.script
    assert action.action_code == "calc_score"


def test_action_without_script_has_none() -> None:
    loader = OntologyLoader()
    loader.load_from_content(MINIMAL_REGISTRY)
    cls = loader.get_ontology_class("sales_emp")
    assert cls.actions[0].script is None


def test_configure_sets_plan_generator() -> None:
    loader = OntologyLoader()
    loader.load_from_content(MINIMAL_REGISTRY)
    loader.configure(csv_base_dir="/tmp/test")
    assert loader._config.csv_base_dir == "/tmp/test"
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data && pytest tests/datacloud_data/test_ontology_loader.py -v`

Expected: FAIL

**Step 3: 实现 OntologyLoader**

```python
# src/datacloud_data_sdk/ontology/loader.py
"""OntologyLoader: 解析 JSON/YAML 本体 → 内部模型 + 核心实体。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from datacloud_data_sdk.exceptions import ObjectNotFoundError, ActionNotFoundError
from datacloud_data_sdk.ontology.models import (
    OntologyClass,
    OntologyField,
    OntologyAction,
    OntologyActionParam,
    OntologyRelation,
    FieldPhysicalMapping,
)


@dataclass
class LoaderConfig:
    """OntologyLoader 运行时配置。"""

    plan_generator: Any = None
    datasource_configs: dict[str, Any] = field(default_factory=dict)
    csv_base_dir: str = "/tmp/datacloud_csv"


class OntologyLoader:
    """本体加载器：解析标准格式 JSON，产出 Ontology* 模型与核心实体。

    Example::

        loader = OntologyLoader()
        loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
        loader.configure(csv_base_dir="/tmp/csv")
        obj = loader.get_object("sales_bo")
    """

    def __init__(self) -> None:
        self._classes: dict[str, OntologyClass] = {}
        self._relations: list[OntologyRelation] = []
        self._functions: dict[str, dict[str, Any]] = {}
        self._config = LoaderConfig()

    def load_from_path(self, path: str | Path) -> None:
        """从本地文件加载本体定义。"""
        content = json.loads(Path(path).read_text(encoding="utf-8"))
        self.load_from_content(content)

    def load_from_content(self, content: dict[str, Any], format: str = "json") -> None:
        """从内存 dict 加载本体定义。"""
        for fn in content.get("functions", []):
            self._functions[fn["function_code"]] = fn.get("api_schema", {})

        for obj in content.get("objects", []):
            fields = self._parse_fields(obj.get("fields", []))
            actions = self._parse_actions(obj.get("actions", []), obj["object_code"])
            ontology_class = OntologyClass(
                object_code=obj["object_code"],
                object_name=obj.get("object_name", obj["object_code"]),
                description=obj.get("description", ""),
                source_type=obj.get("source_type", "DB"),
                datasource_alias=obj.get("datasource_alias"),
                table_name=obj.get("table_name"),
                tags=obj.get("tags", []),
                fields=fields,
                actions=actions,
            )
            self._classes[obj["object_code"]] = ontology_class

        for rel in content.get("relations", []):
            self._relations.append(
                OntologyRelation(
                    relation_code=rel.get("relation_code", ""),
                    relation_name=rel.get("relation_name", ""),
                    source_class=rel.get("source_class", ""),
                    target_class=rel.get("target_class", ""),
                    relation_type=rel.get("relation_type", "ONE_TO_MANY"),
                    join_keys=rel.get("join_keys", []),
                    description=rel.get("description", ""),
                )
            )

    def configure(self, **kwargs: Any) -> None:
        """设置运行时配置（plan_generator、datasource_configs、csv_base_dir）。"""
        for k, v in kwargs.items():
            if hasattr(self._config, k):
                setattr(self._config, k, v)

    # --- 本体层 API ---

    def get_ontology_class(self, object_code: str) -> OntologyClass:
        if object_code not in self._classes:
            raise ObjectNotFoundError(object_code)
        return self._classes[object_code]

    def get_ontology_classes(self, object_ids: list[str] | None = None) -> list[OntologyClass]:
        if object_ids is None:
            return list(self._classes.values())
        return [self.get_ontology_class(oid) for oid in object_ids]

    def get_ontology_relations(self) -> list[OntologyRelation]:
        return list(self._relations)

    def get_function_config(self, function_code: str) -> dict[str, Any]:
        return self._functions.get(function_code, {})

    # --- 核心层 API（后续 Task 实现完整版本）---

    def get_object(self, object_code: str) -> Any:
        """获取 Object 实体（Task 7 实现）。"""
        raise NotImplementedError("Implemented in Task 7")

    def get_view(self, view_id: str) -> Any:
        """获取 View 实体（Task 8 实现）。"""
        raise NotImplementedError("Implemented in Task 8")

    # --- 内部解析 ---

    def _parse_fields(self, raw_fields: list[dict[str, Any]]) -> list[OntologyField]:
        return [
            OntologyField(
                field_code=f["field_code"],
                field_name=f.get("field_name", f["field_code"]),
                field_type=f.get("field_type", "STRING"),
                description=f.get("description", ""),
                aliases=f.get("aliases", []),
                required=f.get("required", False),
                is_primary_key=f.get("is_primary_key", False),
                source_column=f.get("source_column"),
                term_set=f.get("term_set"),
                physical_mappings=[
                    FieldPhysicalMapping(**m) for m in f.get("physical_mappings", [])
                ],
            )
            for f in raw_fields
        ]

    def _parse_actions(
        self, raw_actions: list[dict[str, Any]], belong_class: str
    ) -> list[OntologyAction]:
        return [
            OntologyAction(
                action_code=a["action_code"],
                action_name=a.get("action_name", a["action_code"]),
                description=a.get("description", ""),
                belong_class=belong_class,
                params=[
                    OntologyActionParam(
                        param_code=p["param_code"],
                        param_name=p.get("param_name", p["param_code"]),
                        direction=p.get("direction", "IN"),
                        param_type=p.get("param_type", "STRING"),
                        required=p.get("required", False),
                        default_value=p.get("default_value"),
                        mapping_path=p.get("mapping_path", ""),
                        term_set=p.get("term_set"),
                    )
                    for p in a.get("params", [])
                ],
                function_refs=a.get("function_refs", []),
                script=a.get("script"),
            )
            for a in raw_actions
        ]
```

**Step 4: 运行测试**

Run: `cd datacloud-data && pytest tests/datacloud_data/test_ontology_loader.py -v`

Expected: PASS

---

### Task 7: Relation + Action + Object + OntologyLoader.get_object()

**Files:**
- Create: `datacloud-data/src/datacloud_data/relation.py`
- Create: `datacloud-data/src/datacloud_data/action.py`
- Create: `datacloud-data/src/datacloud_data/object.py`
- Modify: `datacloud-data/src/datacloud_data/ontology/loader.py`
- Create: `datacloud-data/tests/datacloud_data/test_sdk_entities.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_sdk/test_sdk_entities.py
import pytest
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.exceptions import ActionNotFoundError

REGISTRY = {
    "functions": [
        {
            "function_code": "fn_get_bo",
            "function_type": "API",
            "api_schema": {
                "servers": [{"url": "http://mock:8080"}],
                "paths": {"/api/bo": {"post": {}}},
            },
        }
    ],
    "objects": [
        {
            "object_code": "sales_bo",
            "object_name": "销售商机",
            "description": "商机对象",
            "source_type": "DB",
            "datasource_alias": "crm_db",
            "table_name": "sales_business_opportunity",
            "fields": [
                {"field_code": "bo_id", "field_name": "商机ID", "field_type": "STRING"},
                {"field_code": "bo_name", "field_name": "商机名称", "field_type": "STRING",
                 "aliases": ["项目名称"]},
            ],
            "actions": [
                {
                    "action_code": "query_bo_by_owner",
                    "action_name": "按负责人查商机",
                    "description": "通过负责人ID查询商机列表",
                    "params": [
                        {"param_code": "owner_id", "param_name": "负责人ID",
                         "direction": "IN", "param_type": "STRING", "required": True,
                         "mapping_path": "$.requestBody.ownerId"},
                        {"param_code": "bo_list", "param_name": "商机列表",
                         "direction": "OUT", "param_type": "ARRAY",
                         "mapping_path": "$.response.data"},
                    ],
                    "function_refs": ["fn_get_bo"],
                },
                {
                    "action_code": "calc_score",
                    "action_name": "计算评分",
                    "description": "计算商机评分",
                    "script": "def execute(params):\n    return {'score': 100}",
                    "function_refs": [],
                    "params": [
                        {"param_code": "score", "param_name": "评分",
                         "direction": "OUT", "param_type": "NUMBER"},
                    ],
                },
            ],
        }
    ],
    "relations": [],
}


def test_object_get_description_contains_fields_and_actions() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    obj = loader.get_object("sales_bo")
    desc = obj.get_description()
    assert "销售商机" in desc
    assert "bo_name" in desc
    assert "项目名称" in desc
    assert "query_bo_by_owner" in desc


def test_action_get_schema_returns_input_output() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    obj = loader.get_object("sales_bo")
    schema = obj.get_action_schema("query_bo_by_owner")
    assert "input" in schema
    assert "output" in schema
    assert "owner_id" in schema["input"]["properties"]
    assert schema["input"]["required"] == ["owner_id"]


def test_list_action_codes_includes_script_action() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    obj = loader.get_object("sales_bo")
    codes = obj.list_action_codes()
    assert "query_bo_by_owner" in codes
    assert "calc_score" in codes


def test_unknown_action_raises() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    obj = loader.get_object("sales_bo")
    with pytest.raises(ActionNotFoundError):
        obj.get_action_schema("nonexistent_action")


def test_get_description_shows_script_action() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    obj = loader.get_object("sales_bo")
    desc = obj.get_description()
    assert "calc_score" in desc
    assert "脚本" in desc or "Script" in desc
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data && pytest tests/datacloud_data/test_sdk_entities.py -v`

Expected: FAIL

**Step 3: 实现 Relation**

```python
# src/datacloud_data_sdk/relation.py
"""对象间关联关系模型。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Relation:
    """对象间关联关系。"""

    from_object: str
    to_object: str
    cardinality: str
    join_keys: list[dict[str, str]]
    description: str = ""
```

**Step 4: 实现 Action**

```python
# src/datacloud_data_sdk/action.py
"""Action 实体：封装 OntologyAction，提供 schema 与执行能力。"""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass
class Action:
    """动作实体，提供 schema 生成与执行（execute 在执行层实现后补全）。"""

    _action: OntologyAction

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
        """执行动作（ScriptExecutor / ApiExecutor 在后续 Task 中集成）。"""
        raise NotImplementedError("Action.execute implemented in execution layer tasks")
```

**Step 5: 实现 Object**

```python
# src/datacloud_data_sdk/object.py
"""Object 实体：本体对象的运行时表示。"""

from __future__ import annotations

from datacloud_data_sdk.action import Action
from datacloud_data_sdk.exceptions import ActionNotFoundError
from datacloud_data_sdk.ontology.models import OntologyAction, OntologyClass
from datacloud_data_sdk.relation import Relation


class Object:
    """本体对象实体，提供自生说明、动作调用与查询能力。

    通过 OntologyLoader.get_object() 获取实例。
    """

    def __init__(self, ontology_class: OntologyClass, relations: list[Relation]) -> None:
        self._cls = ontology_class
        self._relations = relations

    @property
    def object_code(self) -> str:
        return self._cls.object_code

    def get_description(self) -> str:
        """生成 Markdown 格式的对象自生说明。"""
        lines = [
            f"## 对象：{self._cls.object_name}（{self._cls.object_code}）",
            "",
            f"**数据来源**：{self._cls.source_type}"
            + (f"（{self._cls.datasource_alias}）" if self._cls.datasource_alias else "")
            + (f"，表 `{self._cls.table_name}`" if self._cls.table_name else ""),
            "",
            "**字段**：",
        ]
        for f in self._cls.fields:
            aliases = "，".join([f.field_name] + f.aliases)
            line = f"- {f.field_code}（{aliases}, {f.field_type}）"
            if f.description:
                line += f" —— {f.description}"
            lines.append(line)

        if self._cls.actions:
            lines += ["", "**动作**："]
            for a in self._cls.actions:
                exec_type = "脚本" if a.script else "API"
                in_params = ", ".join(
                    f"{p.param_code}({'必填' if p.required else '可选'})"
                    for p in a.params
                    if p.direction in ("IN", "INOUT")
                )
                lines.append(
                    f"- `{a.action_code}`（{exec_type}）：{a.action_name}，入参：{in_params}"
                )

        if self._relations:
            lines += ["", "**关联**："]
            for r in self._relations:
                other = r.to_object if r.from_object == self._cls.object_code else r.from_object
                line = f"- 关联 {other}，{r.cardinality}"
                if r.description:
                    line += f" —— {r.description}"
                lines.append(line)

        return "\n".join(lines)

    def get_action_schema(self, action_code: str) -> dict[str, object]:
        """获取动作的 input/output JSON Schema。"""
        action = self._find_action(action_code)
        return Action(action).get_schema()

    def list_action_codes(self) -> list[str]:
        return [a.action_code for a in self._cls.actions]

    def get_relations(self) -> list[Relation]:
        return self._relations

    def _find_action(self, action_code: str) -> OntologyAction:
        for a in self._cls.actions:
            if a.action_code == action_code:
                return a
        raise ActionNotFoundError(self._cls.object_code, action_code)

    async def query(self, question: str) -> dict[str, object]:
        """自然语言查询（计划层实现后补全）。"""
        raise NotImplementedError("Object.query implemented in plan/execution tasks")

    async def invoke_action(self, action_code: str, params: dict[str, object]) -> dict[str, object]:
        """执行动作（执行层实现后补全）。"""
        action = self._find_action(action_code)
        return await Action(action).execute(params)
```

**Step 6: 在 OntologyLoader 中实现 get_object()**

在 `loader.py` 的 `get_object` 方法替换 `NotImplementedError`：

```python
def get_object(self, object_code: str) -> "Object":
    from datacloud_data_sdk.object import Object
    from datacloud_data_sdk.relation import Relation

    cls = self.get_ontology_class(object_code)
    rels = [
        Relation(
            from_object=r.source_class,
            to_object=r.target_class,
            cardinality=r.relation_type,
            join_keys=r.join_keys,
            description=r.description,
        )
        for r in self._relations
        if r.source_class == object_code or r.target_class == object_code
    ]
    return Object(cls, rels)
```

**Step 7: 运行测试**

Run: `cd datacloud-data && pytest tests/datacloud_data/test_sdk_entities.py -v`

Expected: PASS

---

### Task 8: View 实体 + OntologyLoader.get_view()

**Files:**
- Create: `datacloud-data/src/datacloud_data/view.py`
- Modify: `datacloud-data/src/datacloud_data/ontology/loader.py`
- Create: `datacloud-data/tests/datacloud_data/test_view.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_sdk/test_view.py
from datacloud_data_sdk.ontology.loader import OntologyLoader

REGISTRY = {
    "functions": [],
    "objects": [
        {
            "object_code": "sales_bo",
            "object_name": "销售商机",
            "description": "商机对象",
            "source_type": "DB",
            "datasource_alias": "crm_db",
            "table_name": "sales_bo",
            "fields": [
                {"field_code": "bo_id", "field_name": "商机ID", "field_type": "STRING"},
            ],
            "actions": [],
        },
        {
            "object_code": "sales_contract",
            "object_name": "销售合同",
            "description": "合同对象",
            "source_type": "DB",
            "datasource_alias": "crm_db",
            "table_name": "sales_contract",
            "fields": [
                {"field_code": "contract_id", "field_name": "合同ID", "field_type": "STRING"},
            ],
            "actions": [],
        },
    ],
    "relations": [
        {
            "relation_code": "bo_to_contract",
            "relation_name": "商机关联合同",
            "source_class": "sales_bo",
            "target_class": "sales_contract",
            "relation_type": "ONE_TO_MANY",
            "join_keys": [{"from_field": "bo_id", "to_field": "bo_id"}],
            "description": "一个商机可签署多份合同",
        }
    ],
}

SCENE = {
    "view_id": "scene_01",
    "view_name": "CRM销售分析视图",
    "description": "包含商机与合同",
    "object_ids": ["sales_bo", "sales_contract"],
}


def test_view_get_description_contains_objects() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    loader.load_scene(SCENE)
    view = loader.get_view("scene_01")
    desc = view.get_description()
    assert "销售商机" in desc
    assert "销售合同" in desc
    assert "商机关联合同" in desc or "bo_to_contract" in desc


def test_view_list_objects() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    loader.load_scene(SCENE)
    view = loader.get_view("scene_01")
    assert len(view.objects) == 2
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data && pytest tests/datacloud_data/test_view.py -v`

Expected: FAIL

**Step 3: 实现 View**

```python
# src/datacloud_data_sdk/view.py
"""View 实体：跨对象的视图聚合，提供自然语言查询与自生说明。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from datacloud_data_sdk.relation import Relation

if TYPE_CHECKING:
    from datacloud_data_sdk.object import Object


class View:
    """视图实体，聚合多个对象，提供跨对象查询能力。

    通过 OntologyLoader.get_view() 获取实例。
    """

    def __init__(
        self,
        view_id: str,
        view_name: str,
        description: str,
        objects: list[Object],
        relations: list[Relation],
    ) -> None:
        self.view_id = view_id
        self.view_name = view_name
        self.description = description
        self.objects = objects
        self.relations = relations

    def get_description(self) -> str:
        """生成 Markdown 格式的视图自生说明。"""
        lines = [
            f"## 视图：{self.view_name}（{self.view_id}）",
            "",
            f"{self.description}" if self.description else "",
            "",
            "**包含对象**：",
        ]
        for obj in self.objects:
            actions = ", ".join(f"`{c}`" for c in obj.list_action_codes())
            action_info = f"（动作：{actions}）" if actions else ""
            lines.append(f"- {obj._cls.object_name}（{obj.object_code}）{action_info}")

        if self.relations:
            lines += ["", "**对象关联**："]
            for r in self.relations:
                lines.append(
                    f"- {r.from_object} → {r.to_object}，{r.cardinality}"
                    + (f" —— {r.description}" if r.description else "")
                )

        return "\n".join(lines)

    async def query(self, question: str) -> dict[str, object]:
        """跨对象自然语言查询（计划层实现后补全）。"""
        raise NotImplementedError("View.query implemented in plan/execution tasks")

    async def invoke_object_action(
        self, object_code: str, action_code: str, params: dict[str, object]
    ) -> dict[str, object]:
        """通过视图调用对象动作。"""
        for obj in self.objects:
            if obj.object_code == object_code:
                return await obj.invoke_action(action_code, params)
        raise ValueError(f"Object {object_code!r} not in view {self.view_id!r}")
```

**Step 4: 在 OntologyLoader 中实现 load_scene() 和 get_view()**

在 `loader.py` 的 `__init__` 中新增 `self._scenes: dict[str, dict] = {}`，然后实现：

```python
def load_scene(self, scene: dict[str, Any]) -> None:
    """加载场景/视图定义。"""
    self._scenes[scene["view_id"]] = scene

def load_scene_from_path(self, path: str | Path) -> None:
    """从文件加载场景定义。"""
    content = json.loads(Path(path).read_text(encoding="utf-8"))
    self.load_scene(content)

def get_view(self, view_id: str) -> "View":
    from datacloud_data_sdk.view import View
    from datacloud_data_sdk.relation import Relation

    scene = self._scenes.get(view_id)
    if scene is None:
        raise ObjectNotFoundError(view_id)

    object_ids = scene.get("object_ids", [])
    objects = [self.get_object(oid) for oid in object_ids]

    object_set = set(object_ids)
    rels = [
        Relation(
            from_object=r.source_class,
            to_object=r.target_class,
            cardinality=r.relation_type,
            join_keys=r.join_keys,
            description=r.description,
        )
        for r in self._relations
        if r.source_class in object_set and r.target_class in object_set
    ]

    return View(
        view_id=view_id,
        view_name=scene.get("view_name", view_id),
        description=scene.get("description", ""),
        objects=objects,
        relations=rels,
    )
```

**Step 5: 运行测试**

Run: `cd datacloud-data && pytest tests/datacloud_data/test_view.py -v`

Expected: PASS

---

### Task 9: 迁移 objects_registry.json 为标准格式 + 集成测试

**Files:**
- Create: `datacloud-data/resources/ontology/crm_demo/objects_registry.json`
- Create: `datacloud-data/resources/ontology/crm_demo/scene_01_data_analysis.json`
- Create: `datacloud-data/tests/datacloud_data/integration/test_ontology_loader_integration.py`

**Step 1: 从 datacloud-mock 复制并转换 objects_registry.json 为标准格式**

编写一个一次性迁移脚本，将 `datacloud-mock/mock-resource/ontology/crm_demo/modules/objects_registry.json` 转换为标准格式（`properties` → `fields`，`property_code` → `field_code`，`object_type` → `source_type` 等），输出到 `datacloud-data/resources/ontology/crm_demo/objects_registry.json`。

关键映射：
- `object_type: "API"` → `source_type: "API"`
- `object_type: "ANALYTICS_DB"` → `source_type: "DB"`
- `object_type: "KNOWLEDGE_BASE"` → `source_type: "KNOWLEDGE_BASE"`
- `properties[].property_code` → `fields[].field_code`
- `properties[].property_name` → `fields[].field_name`
- `properties[].property_type` → `fields[].field_type`
- `source_object_ref` → `source_class`
- `target_object_ref` → `target_class`
- `source_property_ref` / `target_property_ref` → `join_keys[{from_field, to_field}]`
- `source_config.table` → `table_name`
- 有 `source_config.base_url` 的 → `datasource_alias` 留空（API 类型）
- DB 类型按 `source_system` 推导 `datasource_alias`

Run: 编写并运行迁移脚本

**Step 2: 复制 scene 文件**

Run:
```bash
cp datacloud-mock/mock-resource/ontology/crm_demo/modules/scene_01_data_analysis.json \
   datacloud-data/resources/ontology/crm_demo/
```

如果 scene 文件格式不兼容，需要做类似适配。

**Step 3: 写集成测试**

```python
# tests/datacloud_data_sdk/integration/test_ontology_loader_integration.py
import pytest
from pathlib import Path
from datacloud_data_sdk.ontology.loader import OntologyLoader

REGISTRY_PATH = Path(__file__).parents[3] / "resources/ontology/crm_demo/objects_registry.json"


@pytest.mark.skipif(not REGISTRY_PATH.exists(), reason="CRM registry not found")
def test_load_crm_registry_has_objects() -> None:
    loader = OntologyLoader()
    loader.load_from_path(REGISTRY_PATH)
    classes = loader.get_ontology_classes()
    assert len(classes) > 0


@pytest.mark.skipif(not REGISTRY_PATH.exists(), reason="CRM registry not found")
def test_crm_objects_have_fields() -> None:
    loader = OntologyLoader()
    loader.load_from_path(REGISTRY_PATH)
    bo = loader.get_ontology_class("sales_business_opportunity")
    assert len(bo.fields) > 0
    assert bo.source_type == "DB"


@pytest.mark.skipif(not REGISTRY_PATH.exists(), reason="CRM registry not found")
def test_crm_relations_loaded() -> None:
    loader = OntologyLoader()
    loader.load_from_path(REGISTRY_PATH)
    relations = loader.get_ontology_relations()
    assert len(relations) > 0


@pytest.mark.skipif(not REGISTRY_PATH.exists(), reason="CRM registry not found")
def test_get_object_returns_description() -> None:
    loader = OntologyLoader()
    loader.load_from_path(REGISTRY_PATH)
    obj = loader.get_object("sales_business_opportunity")
    desc = obj.get_description()
    assert "商机" in desc
```

**Step 4: 运行集成测试**

Run: `cd datacloud-data && pytest tests/datacloud_data/integration/ -v`

Expected: PASS

---

## P1.2 计划层

> Task 10-13 与原计划 Task 8-11 基本相同，关键修订点：
> - Task 10: ObjectViewBuilder 无变化
> - Task 11: PlanValidator 无变化
> - Task 12: QueryPlanGenerator 新增 `camel_to_snake_keys()` 转换
> - Task 13: ExecutionObjectConverter 新增 `ScriptExecTask` 分支

### Task 10: 计划层模型 + ObjectViewBuilder

与原计划 Task 8 相同，无需修改。

---

### Task 11: PlanValidator

与原计划 Task 9 相同，无需修改。

---

### Task 12: QueryPlanGenerator（含 camelCase 转换）

与原计划 Task 10 基本相同，新增 `camel_to_snake_keys` 工具函数：

**在 `plan/query_plan_generator.py` 中增加**：

```python
import re

def camel_to_snake(name: str) -> str:
    """canAnswer → can_answer, sqlTemplate → sql_template"""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

def camel_to_snake_keys(d: dict | list | object) -> dict | list | object:
    """递归转换 dict 的 key 从 camelCase 到 snake_case。"""
    if isinstance(d, dict):
        return {camel_to_snake(k): camel_to_snake_keys(v) for k, v in d.items()}
    if isinstance(d, list):
        return [camel_to_snake_keys(i) for i in d]
    return d
```

在 `LangGraphPlanGenerator` 解析 LLM JSON 时调用 `camel_to_snake_keys()` 再构造 `QueryExecutionPlan`。

---

### Task 13: ExecutionObjectConverter（含 ScriptExecTask）

与原计划 Task 11 基本相同，新增 Script 步骤转换。

**在 `executor/models.py` 中定义**（Task 14 创建此文件时一并定义）：

```python
@dataclass
class ScriptExecTask:
    action_code: str
    script: str
    params: dict
    output_ref: str = ""
```

---

## P1.3 执行层与聚合层

### Task 14: 执行层模型 + 可扩展数据源连接器

与原计划 Task 12 相同，`executor/models.py` 新增 `ScriptExecTask`，`sql_executor/models.py` 定义 `DataSourceConfig` + `SqlExecTask` + `SqlExecResult`。

---

### Task 15: SqlExecutor + CSV 存储

与原计划 Task 13 相同。

---

### Task 16: ScriptExecutor（新增）

**Files:**
- Create: `datacloud-data/src/datacloud_data/executor/script_executor.py`
- Create: `datacloud-data/tests/datacloud_data/test_script_executor.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_sdk/test_script_executor.py
import pytest
from datacloud_data_sdk.executor.script_executor import ScriptExecutor
from datacloud_data_sdk.context import InvocationContext, get_current_context
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
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data && pytest tests/datacloud_data/test_script_executor.py -v`

Expected: FAIL

**Step 3: 实现 ScriptExecutor**

```python
# src/datacloud_data_sdk/executor/script_executor.py
"""ScriptExecutor: 执行与动作绑定的 Python 脚本。

脚本约定：必须定义 def execute(params: dict) -> dict
注入环境：context（RequestContext）、loader（OntologyLoader，可选）、httpx 模块
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Any

from datacloud_data_sdk.context import get_current_context
from datacloud_data_sdk.exceptions import ScriptExecutionError


class ScriptExecutor:
    """执行预定义 Python 脚本的执行器。"""

    def __init__(self, ontology_loader: Any = None) -> None:
        self._loader = ontology_loader

    async def execute(
        self,
        script: str,
        params: dict[str, Any],
        action_code: str = "<inline>",
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """编译并执行脚本，返回结果 dict。"""
        try:
            ctx = get_current_context()
        except Exception:
            ctx = None

        namespace: dict[str, Any] = {
            "context": ctx,
            "loader": self._loader,
        }

        try:
            import httpx  # noqa: F811

            namespace["httpx"] = httpx
        except ImportError:
            pass

        try:
            exec(compile(script, f"<action:{action_code}>", "exec"), namespace)
        except SyntaxError as e:
            raise ScriptExecutionError(action_code, f"SyntaxError: {e}", line_no=e.lineno)

        execute_fn = namespace.get("execute")
        if execute_fn is None or not callable(execute_fn):
            raise ScriptExecutionError(
                action_code,
                "Script must define `def execute(params: dict) -> dict`",
            )

        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, execute_fn, params),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise ScriptExecutionError(action_code, f"Script timed out after {timeout}s")
        except ScriptExecutionError:
            raise
        except Exception as e:
            tb = traceback.extract_tb(e.__traceback__)
            line_no = tb[-1].lineno if tb else None
            raise ScriptExecutionError(action_code, str(e), line_no=line_no)

        if not isinstance(result, dict):
            raise ScriptExecutionError(
                action_code,
                f"execute() must return dict, got {type(result).__name__}",
            )
        return result
```

**Step 4: 运行测试**

Run: `cd datacloud-data && pytest tests/datacloud_data/test_script_executor.py -v`

Expected: PASS

---

### Task 17: ApiExecutor

与原计划 Task 14 相同。

---

### Task 18: 聚合层（签名统一版）

与原计划 Task 15 基本相同，关键修改：`csv_table_names` 从 `PlanAggregation` 中读取而非作为额外参数。

`SqliteAggregator.aggregate(agg, step_results)` 内部从 `agg.csv_table_names` 获取映射。

---

### Task 19: 集成 Object.query() + CSV 清理

与原计划 Task 16 基本相同，增加 CSV 清理逻辑：

```python
async def query(self, question: str) -> dict[str, object]:
    request_id = str(uuid.uuid4())
    try:
        # 计划 → 执行 → 聚合管线
        ...
        return {"records": records, "meta": meta}
    finally:
        csv_manager.cleanup(request_id)
```

---

## P1.3.5 事件驱动层

### Task 20-22: 事件总线 + 链路追踪 + 事件驱动查询

与原计划 Task 16.5-16.7 相同，无需修改。

---

## P1.4 服务层

### Task 23-27: FastAPI + MCP + REST

与原计划 Task 17-21 相同，无需修改。

---

## 完整测试验证

### Task 28: 运行全部测试

Run: `cd datacloud-data && pytest tests/ -v --tb=short`

Expected: 全部 PASS

### Task 29: CRM 端到端测试

与原计划 Task 22 相同，新增场景：

| 场景 | 验证点 |
|------|--------|
| 脚本动作：`calc_score` | `tools/call` 执行脚本，返回 score |
| 脚本优先：action 同时有 script 和 function_refs | 执行 script，不调 API |
