# Data Service SDK Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构建可开源的 `datacloud_data_sdk` 与薄接入的 `datacloud_data_service`，完成本体解析、查询计划、执行聚合与 MCP/REST 工具链路，并用 CRM Demo 场景验证。

**Architecture:** 双子包结构，SDK 包含所有核心逻辑（本体层 → 计划层 → 执行层 → 聚合层 → 事件层），服务层只做请求解析、上下文注入与结果包装。全程 TDD：先写失败测试，再最小实现，逐层叠加。

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, LangGraph, langchain-openai, httpx, SQLAlchemy AsyncIO, aiomysql, pytest, pytest-asyncio, pytest-mock

**设计文档：** `docs/plans/2026-03-06-data-service-sdk-design.md`

---

## P1.1 本体层

### Task 1: 调整 pyproject.toml 支持双子包与 extras

**Files:**
- Modify: `datacloud-data-service/pyproject.toml`

**Step 1: 修改 pyproject.toml**

将 `[tool.hatch.build.targets.wheel]` 的 packages 改为同时包含两个子包：

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/datacloud_data_sdk", "src/datacloud_data_service"]

[project.optional-dependencies]
langchain = ["langgraph>=0.2", "langchain-openai>=0.1"]
sql       = ["sqlalchemy[asyncio]>=2.0", "aiomysql>=0.2", "aiosqlite>=0.19"]
all       = ["datacloud-data-service[langchain,sql]"]
dev       = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-mock>=3.12",
    "httpx>=0.27",
]
```

**Step 2: 安装依赖（在 datacloud-data-service 目录下）**

Run: `cd datacloud-data-service && uv pip install -e ".[langchain,sql,dev]"`

Expected: 安装成功，无依赖冲突。

---

### Task 2: 建立 SDK 包结构与异常层次

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/__init__.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/exceptions.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/__init__.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/test_exceptions.py`

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
    DataSourceUnavailableError,
    AggregationError,
)


def test_error_hierarchy() -> None:
    assert issubclass(ObjectNotFoundError, DatacloudError)
    assert issubclass(CannotAnswerError, DatacloudError)
    assert issubclass(SqlExecutionError, DatacloudError)


def test_object_not_found_carries_code() -> None:
    err = ObjectNotFoundError("sales_bo")
    assert "sales_bo" in str(err)


def test_plan_validation_error_carries_errors_list() -> None:
    err = PlanValidationError(["step_1: invalid sourceId", "aggregation: missing finalStepId"])
    assert len(err.errors) == 2
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_exceptions.py -v`

Expected: FAIL，ImportError

**Step 3: 实现异常层次**

```python
# src/datacloud_data_sdk/exceptions.py
class DatacloudError(Exception):
    pass

class OntologyError(DatacloudError):
    pass

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

class PlanError(DatacloudError):
    pass

class PlanGenerationError(PlanError):
    pass

class PlanValidationError(PlanError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__(f"Plan validation failed: {errors}")
        self.errors = errors

class CannotAnswerError(PlanError):
    def __init__(self, clarification: str) -> None:
        super().__init__(clarification)
        self.clarification = clarification

class ExecutionError(DatacloudError):
    pass

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

class DataSourceUnavailableError(ExecutionError):
    def __init__(self, alias: str) -> None:
        super().__init__(f"Datasource unavailable: {alias!r}")

class AggregationError(DatacloudError):
    def __init__(self, strategy: str, sql: str, cause: str) -> None:
        super().__init__(f"Aggregation [{strategy}] failed: {cause}\nSQL: {sql}")
```

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_exceptions.py -v`

Expected: PASS

---

### Task 3: 实现 InvocationContext

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/context.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/test_context.py`

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

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_context.py -v`

Expected: FAIL

**Step 3: 实现 InvocationContext**

```python
# src/datacloud_data_sdk/context.py
from __future__ import annotations
import contextvars
from dataclasses import dataclass, field
from types import TracebackType
from datacloud_data_sdk.exceptions import DatacloudError

@dataclass
class RequestContext:
    tenant_id: str = ""
    user_id: str = ""
    session_id: str = ""
    token: str = ""
    system_code: str = ""

_ctx_var: contextvars.ContextVar[RequestContext | None] = contextvars.ContextVar(
    "invocation_context", default=None
)

class InvocationContext:
    def __init__(self, **kwargs: str) -> None:
        self._ctx = RequestContext(**{k: v for k, v in kwargs.items() if v})
        self._token: contextvars.Token[RequestContext | None] | None = None

    def __enter__(self) -> "InvocationContext":
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
    ctx = _ctx_var.get()
    if ctx is None:
        raise DatacloudError("InvocationContext not set. Call within `with InvocationContext(...):`")
    return ctx
```

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_context.py -v`

Expected: PASS

---

### Task 4: 定义本体内部模型

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/ontology/__init__.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/ontology/models.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/test_ontology_models.py`

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


def test_field_has_term_set_and_physical_mappings() -> None:
    f = OntologyField(
        field_code="stage_code",
        field_name="商机阶段",
        field_type="STRING",
        term_set="bo_stage",
        physical_mappings=[
            FieldPhysicalMapping(source_type="DB", source_ref="stage_code", datasource_alias="crm_db")
        ],
    )
    assert f.term_set == "bo_stage"
    assert f.physical_mappings[0].source_ref == "stage_code"


def test_ontology_class_has_no_embedded_datasource_config() -> None:
    cls = OntologyClass(
        object_code="sales_bo",
        object_name="销售商机",
        description="商机对象",
        source_type="DB",
        datasource_alias="crm_db",
        table_name="sales_business_opportunity",
    )
    assert cls.datasource_alias == "crm_db"
    assert not hasattr(cls, "jdbc_url")


def test_ontology_action_has_function_refs() -> None:
    action = OntologyAction(
        action_code="query_bo_by_owner",
        action_name="按负责人查商机",
        description="",
        belong_class="sales_bo",
        params=[],
        function_refs=["fn_crm_bo_query_by_owner"],
    )
    assert "fn_crm_bo_query_by_owner" in action.function_refs
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_ontology_models.py -v`

Expected: FAIL

**Step 3: 实现本体模型**

```python
# src/datacloud_data_sdk/ontology/models.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FieldPhysicalMapping:
    source_type: str       # DB / API
    source_ref: str        # DB 列名 或 $.response.xxx
    datasource_alias: str


@dataclass
class OntologyField:
    field_code: str
    field_name: str
    field_type: str        # STRING / NUMBER / DATE / BOOLEAN / INTEGER
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    required: bool = False
    term_set: str | None = None
    physical_mappings: list[FieldPhysicalMapping] = field(default_factory=list)


@dataclass
class OntologyActionParam:
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
    action_code: str
    action_name: str
    description: str
    belong_class: str
    params: list[OntologyActionParam]
    function_refs: list[str]


@dataclass
class OntologyRelation:
    relation_code: str
    source_class: str
    target_class: str
    relation_type: str     # hasMany / belongsTo / oneToMany / manyToMany
    join_keys: list[dict]
    description: str = ""


@dataclass
class OntologyClass:
    object_code: str
    object_name: str
    description: str
    source_type: str       # DB / API
    datasource_alias: str | None = None
    table_name: str | None = None
    fields: list[OntologyField] = field(default_factory=list)
    actions: list[OntologyAction] = field(default_factory=list)
```

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_ontology_models.py -v`

Expected: PASS

---

### Task 5: 实现术语加载器

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/ontology/term_loader.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/test_term_loader.py`

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

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_term_loader.py -v`

Expected: FAIL

**Step 3: 实现 TermLoader**

```python
# src/datacloud_data_sdk/ontology/term_loader.py
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class TermEntry:
    code: str
    label: str
    aliases: list[str] = field(default_factory=list)


class TermLoader:
    def __init__(self) -> None:
        self._sets: dict[str, list[TermEntry]] = {}

    @classmethod
    def from_mapping(cls, mapping: dict[str, list[dict]]) -> "TermLoader":
        loader = cls()
        for term_set, entries in mapping.items():
            loader._sets[term_set] = [
                TermEntry(code=e["code"], label=e["label"], aliases=e.get("aliases", []))
                for e in entries
            ]
        return loader

    def resolve_code(self, term_set: str, value: str) -> str:
        for entry in self._sets.get(term_set, []):
            if value in (entry.code, entry.label, *entry.aliases):
                return entry.code
        available = self.get_available_values(term_set)
        raise ValueError(f"Unknown term {value!r} in {term_set!r}. available: {available}")

    def get_available_values(self, term_set: str) -> list[str]:
        return [
            e.label for e in self._sets.get(term_set, [])
        ]
```

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_term_loader.py -v`

Expected: PASS

---

### Task 6: 实现 OntologyLoader（解析 objects_registry.json）

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/ontology/loader.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/test_ontology_loader.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/integration/test_ontology_loader_integration.py`

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
            "api_schema": {"servers": [{"url": "http://mock:8080"}], "paths": {"/api/v1/emp": {"post": {}}}},
        }
    ],
    "objects": [
        {
            "object_code": "sales_emp",
            "object_name": "员工",
            "description": "销售员工",
            "source_type": "API",
            "datasource_alias": None,
            "fields": [
                {"field_code": "emp_id", "field_name": "员工ID", "field_type": "STRING"}
            ],
            "actions": [
                {
                    "action_code": "query_emp_by_name",
                    "action_name": "按姓名查员工",
                    "description": "",
                    "params": [],
                    "function_refs": ["fn_get_emp"],
                }
            ],
            "relations": [],
        }
    ],
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
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_ontology_loader.py -v`

Expected: FAIL

**Step 3: 实现 OntologyLoader**

```python
# src/datacloud_data_sdk/ontology/loader.py
from __future__ import annotations
import json
from pathlib import Path
from datacloud_data_sdk.ontology.models import (
    OntologyClass, OntologyField, OntologyAction, OntologyActionParam,
    OntologyRelation, FieldPhysicalMapping,
)
from datacloud_data_sdk.exceptions import ObjectNotFoundError, ActionNotFoundError


class OntologyLoader:
    def __init__(self) -> None:
        self._classes: dict[str, OntologyClass] = {}
        self._relations: list[OntologyRelation] = []
        self._functions: dict[str, dict] = {}

    def load_from_path(self, path: str | Path) -> None:
        content = json.loads(Path(path).read_text(encoding="utf-8"))
        self.load_from_content(content)

    def load_from_content(self, content: dict, format: str = "json") -> None:
        for fn in content.get("functions", []):
            self._functions[fn["function_code"]] = fn.get("api_schema", {})

        for obj in content.get("objects", []):
            fields = [
                OntologyField(
                    field_code=f["field_code"],
                    field_name=f.get("field_name", f["field_code"]),
                    field_type=f.get("field_type", "STRING"),
                    description=f.get("description", ""),
                    aliases=f.get("aliases", []),
                    required=f.get("required", False),
                    term_set=f.get("term_set") or f.get("ext_attrs", {}).get("term_type_code"),
                    physical_mappings=[
                        FieldPhysicalMapping(**m)
                        for m in f.get("physical_mappings", [])
                    ],
                )
                for f in obj.get("fields", [])
            ]
            actions = [
                OntologyAction(
                    action_code=a["action_code"],
                    action_name=a.get("action_name", a["action_code"]),
                    description=a.get("description", ""),
                    belong_class=obj["object_code"],
                    params=[
                        OntologyActionParam(
                            param_code=p["param_code"],
                            param_name=p.get("param_name", p["param_code"]),
                            direction=p.get("direction", "IN"),
                            param_type=p.get("param_type", "STRING"),
                            required=p.get("required", False),
                            default_value=p.get("default_value"),
                            mapping_path=p.get("mapping_path", ""),
                            term_set=p.get("term_set") or p.get("ext_attrs", {}).get("term_type_code"),
                        )
                        for p in a.get("params", [])
                    ],
                    function_refs=a.get("function_refs", []),
                )
                for a in obj.get("actions", [])
            ]
            ontology_class = OntologyClass(
                object_code=obj["object_code"],
                object_name=obj.get("object_name", obj["object_code"]),
                description=obj.get("description", ""),
                source_type=obj.get("source_type", "DB"),
                datasource_alias=obj.get("datasource_alias"),
                table_name=obj.get("table_name"),
                fields=fields,
                actions=actions,
            )
            self._classes[obj["object_code"]] = ontology_class

        for rel in content.get("relations", []):
            self._relations.append(
                OntologyRelation(
                    relation_code=rel.get("relation_code", ""),
                    source_class=rel["source_class"],
                    target_class=rel["target_class"],
                    relation_type=rel.get("relation_type", "oneToMany"),
                    join_keys=rel.get("join_keys", []),
                    description=rel.get("description", ""),
                )
            )

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

    def get_function_config(self, function_code: str) -> dict:
        return self._functions.get(function_code, {})
```

**Step 4: 运行单元测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_ontology_loader.py -v`

Expected: PASS

**Step 5: 写集成测试（使用真实 objects_registry.json）**

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
def test_crm_relations_loaded() -> None:
    loader = OntologyLoader()
    loader.load_from_path(REGISTRY_PATH)
    relations = loader.get_ontology_relations()
    assert isinstance(relations, list)
```

**Step 6: 复制 CRM 本体资源**

Run:
```bash
mkdir -p datacloud-data-service/resources/ontology/crm_demo
cp datacloud-mock/mock-resource/ontology/crm_demo/modules/objects_registry.json \
   datacloud-data-service/resources/ontology/crm_demo/
cp datacloud-mock/mock-resource/ontology/crm_demo/modules/scene_01_data_analysis.json \
   datacloud-data-service/resources/ontology/crm_demo/
```

**Step 7: 运行集成测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/integration/test_ontology_loader_integration.py -v`

Expected: PASS

---

### Task 7: 实现 Action / Object / View / Relation 核心实体

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/relation.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/action.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/object.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/view.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/test_sdk_entities.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_sdk/test_sdk_entities.py
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.exceptions import ActionNotFoundError
import pytest

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
                }
            ],
            "relations": [],
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


def test_list_action_codes() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    obj = loader.get_object("sales_bo")
    assert "query_bo_by_owner" in obj.list_action_codes()


def test_unknown_action_raises() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    obj = loader.get_object("sales_bo")
    with pytest.raises(ActionNotFoundError):
        obj.get_action_schema("nonexistent_action")
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_sdk_entities.py -v`

Expected: FAIL，`loader.get_object` 不存在

**Step 3: 实现 Relation、Action、Object、View**

`relation.py`：

```python
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Relation:
    from_object: str
    to_object: str
    cardinality: str
    join_keys: list[dict]
    description: str = ""
```

`action.py`（仅定义 schema 和 stub execute，execute 留到 Task 14 实现）：

```python
from __future__ import annotations
from dataclasses import dataclass
from datacloud_data_sdk.ontology.models import OntologyAction, OntologyActionParam

PARAM_TYPE_MAP = {
    "STRING": "string", "NUMBER": "number", "DECIMAL": "number",
    "INTEGER": "integer", "BOOLEAN": "boolean", "DATE": "string",
    "DATETIME": "string", "ARRAY": "array", "LIST": "array", "OBJECT": "object",
}


@dataclass
class Action:
    _action: OntologyAction

    def get_schema(self) -> dict:
        in_params = [p for p in self._action.params if p.direction in ("IN", "INOUT")]
        out_params = [p for p in self._action.params if p.direction in ("OUT", "INOUT")]

        def _build_schema(params: list[OntologyActionParam]) -> dict:
            properties = {}
            required = []
            for p in params:
                prop: dict = {
                    "type": PARAM_TYPE_MAP.get(p.param_type.upper(), "string"),
                    "description": p.param_name,
                }
                if p.default_value is not None:
                    prop["default"] = p.default_value
                properties[p.param_code] = prop
                if p.required:
                    required.append(p.param_code)
            schema: dict = {"type": "object", "properties": properties}
            if required:
                schema["required"] = required
            return schema

        return {"input": _build_schema(in_params), "output": _build_schema(out_params)}

    async def execute(self, params: dict) -> dict:
        raise NotImplementedError("Action.execute implemented in Task 14")
```

`object.py`：

```python
from __future__ import annotations
from datacloud_data_sdk.ontology.models import OntologyClass
from datacloud_data_sdk.action import Action
from datacloud_data_sdk.relation import Relation
from datacloud_data_sdk.exceptions import ActionNotFoundError


class Object:
    def __init__(self, ontology_class: OntologyClass, relations: list[Relation]) -> None:
        self._cls = ontology_class
        self._relations = relations

    def get_description(self) -> str:
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
            lines.append(f"- {f.field_code}（{aliases}, {f.field_type}）"
                         + (f" —— {f.description}" if f.description else ""))
        if self._cls.actions:
            lines += ["", "**动作**："]
            for a in self._cls.actions:
                in_params = ", ".join(
                    f"{p.param_code}({'必填' if p.required else '可选'})"
                    for p in a.params if p.direction in ("IN", "INOUT")
                )
                lines.append(f"- `{a.action_code}`：{a.action_name}，入参：{in_params}")
        if self._relations:
            lines += ["", "**关联**："]
            for r in self._relations:
                other = r.to_object if r.from_object == self._cls.object_code else r.from_object
                lines.append(f"- 关联 {other}，{r.cardinality}"
                             + (f" —— {r.description}" if r.description else ""))
        return "\n".join(lines)

    def get_action_schema(self, action_code: str) -> dict:
        action = self._find_action(action_code)
        return Action(action).get_schema()

    def list_action_codes(self) -> list[str]:
        return [a.action_code for a in self._cls.actions]

    def get_relations(self) -> list[Relation]:
        return self._relations

    def _find_action(self, action_code: str):
        for a in self._cls.actions:
            if a.action_code == action_code:
                return a
        raise ActionNotFoundError(self._cls.object_code, action_code)

    async def query(self, question: str) -> dict:
        raise NotImplementedError("Object.query implemented in Task 10")

    async def invoke_action(self, action_code: str, params: dict) -> dict:
        action = self._find_action(action_code)
        return await Action(action).execute(params)
```

**在 `OntologyLoader` 中新增 `get_object` 方法：**

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

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_sdk_entities.py -v`

Expected: PASS

---

## P1.2 计划层

### Task 8: 定义计划层模型与 ObjectViewBuilder

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/plan/__init__.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/plan/models.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/plan/object_view_builder.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/test_object_view_builder.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_sdk/test_object_view_builder.py
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.plan.object_view_builder import ObjectViewBuilder

REGISTRY = {
    "functions": [],
    "objects": [
        {
            "object_code": "sales_bo",
            "object_name": "销售商机",
            "description": "商机对象",
            "source_type": "DB",
            "datasource_alias": "crm_db",
            "table_name": "sales_business_opportunity",
            "fields": [{"field_code": "bo_id", "field_name": "商机ID", "field_type": "STRING"}],
            "actions": [],
            "relations": [],
        },
        {
            "object_code": "sales_contract",
            "object_name": "销售合同",
            "description": "合同对象",
            "source_type": "DB",
            "datasource_alias": "crm_db",
            "table_name": "sales_contract",
            "fields": [{"field_code": "contract_id", "field_name": "合同ID", "field_type": "STRING"}],
            "actions": [],
            "relations": [],
        },
    ],
    "relations": [
        {
            "relation_code": "bo_to_contract",
            "source_class": "sales_bo",
            "target_class": "sales_contract",
            "relation_type": "ONE_TO_MANY",
            "join_keys": [{"from_field": "bo_id", "to_field": "bo_id"}],
            "description": "一个商机可以签署多份合同",
        }
    ],
}


def test_build_object_view_has_sources_and_objects() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    builder = ObjectViewBuilder(loader)
    payload = builder.build(object_ids=["sales_bo", "sales_contract"], view_id="test_view")
    assert len(payload.objects) == 2
    assert len(payload.sources) >= 1


def test_build_object_view_has_relations_with_description() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    builder = ObjectViewBuilder(loader)
    payload = builder.build(object_ids=["sales_bo", "sales_contract"], view_id="test_view")
    assert len(payload.relations) == 1
    assert "合同" in payload.relations[0].description


def test_object_view_object_has_name_and_description() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    builder = ObjectViewBuilder(loader)
    payload = builder.build(object_ids=["sales_bo"], view_id="test_view")
    assert payload.objects[0].object_name == "销售商机"
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_object_view_builder.py -v`

Expected: FAIL

**Step 3: 实现计划层模型与 ObjectViewBuilder**

在 `plan/models.py` 中定义 `ObjectViewSource`、`ObjectViewField`、`ObjectViewObject`、`ObjectViewRelation`、`ObjectViewPayload`、`PlanStep`、`PlanAggregation`、`QueryExecutionPlan`。

在 `plan/object_view_builder.py` 中实现 `ObjectViewBuilder.build(object_ids, view_id)` → `ObjectViewPayload`，从 `OntologyLoader` 拉取对应对象、去重来源、填充 relations。

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_object_view_builder.py -v`

Expected: PASS

---

### Task 9: 实现 PlanValidator

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/plan/plan_validator.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/test_plan_validator.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_sdk/test_plan_validator.py
from datacloud_data_sdk.plan.models import (
    ObjectViewPayload, ObjectViewSource, ObjectViewObject, ObjectViewField,
    ObjectViewRelation, QueryExecutionPlan, PlanStep, PlanAggregation,
)
from datacloud_data_sdk.plan.plan_validator import PlanValidator

PAYLOAD = ObjectViewPayload(
    view_id="v1",
    sources=[ObjectViewSource(source_id="SRC_CRM", source_type="DB", datasource_alias="crm_db")],
    objects=[
        ObjectViewObject(
            object_id="OBJ_BO",
            object_name="商机",
            source_id="SRC_CRM",
            table="sales_bo",
            fields=[ObjectViewField(name="bo_id", type="string"),
                    ObjectViewField(name="bo_name", type="string")],
            functions=[],
        )
    ],
    relations=[],
)

VALID_PLAN = QueryExecutionPlan(
    question="查商机",
    can_answer=True,
    steps=[PlanStep(
        step_id="step_1",
        type="SQL",
        source_id="SRC_CRM",
        datasource_alias="crm_db",
        sql_template="SELECT bo_id, bo_name FROM sales_bo",
        output_ref="bo_list",
    )],
    aggregation=PlanAggregation(
        strategy="DIRECT",
        final_step_id="step_1",
        columns=[{"name": "bo_id", "label": "商机ID", "type": "string"}],
    ),
)


def test_valid_direct_plan() -> None:
    result = PlanValidator().validate(VALID_PLAN, PAYLOAD)
    assert result.valid is True
    assert result.errors == []


def test_invalid_source_id_fails() -> None:
    bad_plan = QueryExecutionPlan(
        question="查商机",
        can_answer=True,
        steps=[PlanStep(step_id="s1", type="SQL", source_id="NONEXISTENT", output_ref="x")],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1", columns=[]),
    )
    result = PlanValidator().validate(bad_plan, PAYLOAD)
    assert result.valid is False
    assert any("NONEXISTENT" in e for e in result.errors)


def test_direct_plan_missing_final_step_id_fails() -> None:
    bad_plan = QueryExecutionPlan(
        question="查商机",
        can_answer=True,
        steps=[PlanStep(step_id="s1", type="SQL", source_id="SRC_CRM", output_ref="x")],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id=None, columns=[]),
    )
    result = PlanValidator().validate(bad_plan, PAYLOAD)
    assert result.valid is False
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_plan_validator.py -v`

Expected: FAIL

**Step 3: 实现 PlanValidator**

在 `plan/plan_validator.py` 中实现 `PlanValidator.validate(plan, payload)` → `ValidationResult(valid, errors)`，执行 Task 9 设计文档中列出的四类校验。

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_plan_validator.py -v`

Expected: PASS

---

### Task 10: 实现 LangGraph QueryPlanGenerator

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/plan/query_plan_generator.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/test_query_plan_generator.py`

**Step 1: 写失败测试（使用 MockPlanGenerator）**

```python
# tests/datacloud_data_sdk/test_query_plan_generator.py
import pytest
import json
from datacloud_data_sdk.plan.query_plan_generator import BasePlanGenerator, MockPlanGenerator
from datacloud_data_sdk.plan.models import ObjectViewPayload, QueryExecutionPlan

PAYLOAD = ObjectViewPayload(view_id="v1", sources=[], objects=[], relations=[])

MOCK_PLAN = {
    "question": "查商机",
    "can_answer": True,
    "steps": [{"step_id": "s1", "type": "SQL", "source_id": "SRC_CRM",
               "datasource_alias": "crm_db", "sql_template": "SELECT 1",
               "output_ref": "result"}],
    "aggregation": {"strategy": "DIRECT", "final_step_id": "s1", "columns": []},
}


@pytest.mark.asyncio
async def test_mock_plan_generator_returns_plan() -> None:
    gen = MockPlanGenerator(fixed_plan=MOCK_PLAN)
    plan = await gen.generate(PAYLOAD, "查商机")
    assert isinstance(plan, QueryExecutionPlan)
    assert plan.can_answer is True


@pytest.mark.asyncio
async def test_mock_plan_generator_cannot_answer() -> None:
    gen = MockPlanGenerator(fixed_plan={"question": "？", "can_answer": False,
                                         "clarification": "无法回答"})
    plan = await gen.generate(PAYLOAD, "？")
    assert plan.can_answer is False
    assert plan.clarification == "无法回答"
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_query_plan_generator.py -v`

Expected: FAIL

**Step 3: 实现 BasePlanGenerator、MockPlanGenerator、LangGraphPlanGenerator**

在 `plan/query_plan_generator.py` 中：
- 定义 `BasePlanGenerator(ABC)` 抽象类（`async def generate(payload, question) -> QueryExecutionPlan`）
- 实现 `MockPlanGenerator(fixed_plan: dict)` 直接返回固定计划，用于测试
- 实现 `LangGraphPlanGenerator`：用 LangGraph 构建单节点图，`call_llm` 节点：
  - 从 `InvocationContext` 或 `Settings` 读取 `llm_base_url`、`llm_api_key`、`llm_model`
  - 用设计文档 §6.6 中的 Prompt 模板，填充 `{{objectView}}` 和 `{{question}}`
  - 调用 LLM，解析 JSON 响应 → `QueryExecutionPlan`

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_query_plan_generator.py -v`

Expected: PASS

---

### Task 11: 实现 ExecutionObjectConverter 与 DataPermissionRewriter

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/plan/execution_object_converter.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/plan/data_permission_rewriter.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/test_execution_object_converter.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_sdk/test_execution_object_converter.py
from datacloud_data_sdk.plan.models import QueryExecutionPlan, PlanStep, PlanAggregation
from datacloud_data_sdk.plan.execution_object_converter import ExecutionObjectConverter
from datacloud_data_sdk.executor.models import SqlExecTask, ApiExecTask


PLAN_WITH_SQL = QueryExecutionPlan(
    question="查商机",
    can_answer=True,
    steps=[PlanStep(
        step_id="s1", type="SQL", source_id="SRC_CRM",
        datasource_alias="crm_db",
        sql_template="SELECT bo_id FROM sales_bo",
        output_ref="bo_list",
    )],
    aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1", columns=[]),
)

PLAN_WITH_API = QueryExecutionPlan(
    question="查员工",
    can_answer=True,
    steps=[PlanStep(
        step_id="s1", type="API", source_id="SRC_EMP",
        function_id="fn_get_emp",
        params={"names": ["邹海天"]},
        output_ref="emp_list",
        csv_table_name="api_emp",
    )],
    aggregation=PlanAggregation(strategy="SQLITE_MEM", sqlite_sql="SELECT * FROM api_emp", columns=[]),
)


def test_sql_step_converts_to_sql_exec_task() -> None:
    tasks = ExecutionObjectConverter().convert(PLAN_WITH_SQL)
    assert len(tasks) == 1
    assert isinstance(tasks[0], SqlExecTask)
    assert tasks[0].datasource_alias == "crm_db"


def test_api_step_converts_to_api_exec_task() -> None:
    tasks = ExecutionObjectConverter().convert(PLAN_WITH_API)
    assert len(tasks) == 1
    assert isinstance(tasks[0], ApiExecTask)
    assert tasks[0].function_code == "fn_get_emp"
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_execution_object_converter.py -v`

Expected: FAIL

**Step 3: 实现**

- 在 `executor/models.py` 中定义 `ApiExecTask` 和 `SqlExecTask`
- 在 `plan/execution_object_converter.py` 实现 `ExecutionObjectConverter.convert(plan)` → `list[ApiExecTask | SqlExecTask]`
- 在 `plan/data_permission_rewriter.py` 实现 `DataPermissionRewriter.rewrite(plan, context)`，从 `InvocationContext` 注入 `tenant_id` WHERE 条件到 SQL

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_execution_object_converter.py -v`

Expected: PASS

---

## P1.3 执行层与聚合层

### Task 12: 实现可扩展数据源连接器

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/sql_executor/__init__.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/sql_executor/models.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/sql_executor/base_connector.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/sql_executor/connector_registry.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/sql_executor/connectors/__init__.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/sql_executor/connectors/sqlite_connector.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/sql_executor/jdbc_parser.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/test_connector_registry.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_sdk/test_connector_registry.py
from datacloud_data_sdk.sql_executor.connector_registry import ConnectorRegistry
from datacloud_data_sdk.sql_executor.connectors.sqlite_connector import SQLiteConnector


def test_sqlite_connector_registered_by_default() -> None:
    cls = ConnectorRegistry.get("SQLITE")
    assert cls is SQLiteConnector


def test_register_custom_connector() -> None:
    class MyConnector(SQLiteConnector):
        @classmethod
        def supported_type(cls) -> str:
            return "CUSTOM_DB"

    ConnectorRegistry.register("CUSTOM_DB", MyConnector)
    assert ConnectorRegistry.get("CUSTOM_DB") is MyConnector


def test_unknown_type_raises() -> None:
    from datacloud_data_sdk.exceptions import DataSourceUnavailableError
    import pytest
    with pytest.raises(DataSourceUnavailableError):
        ConnectorRegistry.get("NONEXISTENT_DB")
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_connector_registry.py -v`

Expected: FAIL

**Step 3: 实现**

在 `sql_executor/models.py` 中定义 `DataSourceConfig`（alias, type, jdbc_url, user, password, pool 配置）。

在 `sql_executor/base_connector.py` 中定义 `BaseSourceConnector(ABC)`，含抽象方法 `execute(sql, params) -> list[dict]`、`test_connection() -> bool`、`supported_type() -> str`。

在 `sql_executor/connectors/sqlite_connector.py` 实现 `SQLiteConnector`（用 `aiosqlite`，`supported_type="SQLITE"`）。

在 `sql_executor/connector_registry.py` 实现 `ConnectorRegistry`，模块加载时注册 SQLITE；MYSQL/POSTGRESQL/CLICKHOUSE 可在安装对应 extras 后懒加载注册。

在 `sql_executor/jdbc_parser.py` 实现 `parse_jdbc_url(jdbc_url, db_type) -> str`（JDBC URL → SQLAlchemy URL）。

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_connector_registry.py -v`

Expected: PASS

---

### Task 13: 实现 SqlExecutor + CSV 存储

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/sql_executor/data_source_manager.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/sql_executor/sql_executor.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/sql_executor/result_converter.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/csv_storage/__init__.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/csv_storage/manager.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/test_sql_executor.py`

**Step 1: 写失败测试（使用 SQLite 内存 DB 替代真实 DB）**

```python
# tests/datacloud_data_sdk/test_sql_executor.py
import pytest
from pathlib import Path
from datacloud_data_sdk.sql_executor.models import DataSourceConfig, SqlExecTask
from datacloud_data_sdk.sql_executor.sql_executor import SqlExecutor
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager

SQLITE_CONFIG = DataSourceConfig(
    alias="test_db",
    db_type="SQLITE",
    jdbc_url="jdbc:sqlite::memory:",
    user="",
    password="",
)


@pytest.mark.asyncio
async def test_sql_executor_returns_csv(tmp_path: Path) -> None:
    manager = DataSourceManager({"test_db": SQLITE_CONFIG})
    executor = SqlExecutor(manager, csv_base_dir=str(tmp_path))
    task = SqlExecTask(
        datasource_alias="test_db",
        sql_template="SELECT 1 AS id, 'hello' AS name",
        output_ref="result",
    )
    result = await executor.execute(task, request_id="req1", step_results={})
    csv_path = Path(result.csv_path)
    assert csv_path.exists()
    content = csv_path.read_text()
    assert "id" in content
    assert "hello" in content


@pytest.mark.asyncio
async def test_sql_executor_bind_from_step(tmp_path: Path) -> None:
    import csv, io

    csv_content = "emp_id\nU001\nU002\n"
    step_csv = tmp_path / "req1" / "step_1_api.csv"
    step_csv.parent.mkdir(parents=True)
    step_csv.write_text(csv_content)

    manager = DataSourceManager({"test_db": SQLITE_CONFIG})
    executor = SqlExecutor(manager, csv_base_dir=str(tmp_path))
    task = SqlExecTask(
        datasource_alias="test_db",
        sql_template="SELECT '{bind_values}' AS ids",
        bind_from_step="step_1_api",
        bind_key="emp_id",
        output_ref="result",
    )
    result = await executor.execute(
        task, request_id="req1", step_results={"step_1_api": str(step_csv)}
    )
    content = Path(result.csv_path).read_text()
    assert "U001" in content
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_sql_executor.py -v`

Expected: FAIL

**Step 3: 实现**

- `csv_storage/manager.py`：`CsvStorageManager.get_path(request_id, output_ref) -> Path`，确保目录存在
- `sql_executor/data_source_manager.py`：`DataSourceManager(configs: dict[str, DataSourceConfig])`，`get_connector(alias) -> BaseSourceConnector`
- `sql_executor/sql_executor.py`：`SqlExecutor.execute(task, request_id, step_results)` → 从 bind_from_step CSV 读取绑定值 → 填充占位符 → 通过 `DataSourceManager` 执行 SQL → 写 CSV → 返回 `SqlExecResult(csv_path, row_count)`
- `sql_executor/result_converter.py`：`ResultConverter.to_csv(records: list[dict], path: str) -> None`

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_sql_executor.py -v`

Expected: PASS

---

### Task 14: 实现 ApiExecutor

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/executor/__init__.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/executor/models.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/executor/api_executor.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/test_api_executor.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_sdk/test_api_executor.py
import pytest
from unittest.mock import AsyncMock, patch
from pathlib import Path
from datacloud_data_sdk.executor.models import ApiExecTask
from datacloud_data_sdk.executor.api_executor import ApiExecutor
from datacloud_data_sdk.context import InvocationContext

API_SCHEMA = {
    "servers": [{"url": "http://mock-service:8080"}],
    "paths": {
        "/api/v1/emp/query": {
            "post": {
                "requestBody": {"content": {"application/json": {}}},
                "responses": {},
            }
        }
    },
}

MOCK_RESPONSE = {"users": [{"userId": "U001", "userName": "邹海天"}]}


@pytest.mark.asyncio
async def test_api_executor_writes_csv(tmp_path: Path) -> None:
    task = ApiExecTask(
        function_code="fn_get_emp",
        params={"names": ["邹海天"]},
        output_ref="emp_list",
        csv_table_name="api_emp",
    )
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json = lambda: MOCK_RESPONSE
        with InvocationContext(tenant_id="t1", token="tok"):
            executor = ApiExecutor(
                function_configs={"fn_get_emp": API_SCHEMA},
                csv_base_dir=str(tmp_path),
            )
            result = await executor.execute(task, request_id="req1")
    assert Path(result.csv_path).exists()


@pytest.mark.asyncio
async def test_api_executor_raises_on_http_error(tmp_path: Path) -> None:
    from datacloud_data_sdk.exceptions import ApiExecutionError
    task = ApiExecTask(function_code="fn_get_emp", params={}, output_ref="x")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 500
        mock_post.return_value.text = "Internal Error"
        mock_post.return_value.json = lambda: {}
        with InvocationContext(tenant_id="t1", token="tok"):
            executor = ApiExecutor(
                function_configs={"fn_get_emp": API_SCHEMA},
                csv_base_dir=str(tmp_path),
            )
            with pytest.raises(ApiExecutionError):
                await executor.execute(task, request_id="req1")
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_api_executor.py -v`

Expected: FAIL

**Step 3: 实现 ApiExecutor**

- 从 `api_schema.servers[0].url + paths` 组合请求 URL
- 从 `InvocationContext` 注入 `Authorization`、`X-Tenant-Id` 等 Header
- 用 `httpx.AsyncClient` POST，超时 30s
- `status_code >= 400` 时抛 `ApiExecutionError`
- 响应数据写入 CSV（通过 `CsvStorageManager`）
- 响应路径按 OUT params `mapping_path` 提取（`$.response.users` → 取 `response.users` 字段）

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_api_executor.py -v`

Expected: PASS

---

### Task 15: 实现聚合层（Direct + SQLite）

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/aggregator/__init__.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/aggregator/base.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/aggregator/direct_aggregator.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/aggregator/sqlite_aggregator.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/test_aggregator.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_sdk/test_aggregator.py
import csv, pytest
from pathlib import Path
from datacloud_data_sdk.plan.models import PlanAggregation
from datacloud_data_sdk.aggregator.direct_aggregator import DirectAggregator
from datacloud_data_sdk.aggregator.sqlite_aggregator import SqliteAggregator


def make_csv(tmp_path: Path, filename: str, rows: list[dict]) -> str:
    p = tmp_path / filename
    with p.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return str(p)


@pytest.mark.asyncio
async def test_direct_aggregator_returns_records(tmp_path: Path) -> None:
    csv_path = make_csv(tmp_path, "result.csv", [{"bo_id": "B001", "bo_name": "5G项目"}])
    agg = PlanAggregation(
        strategy="DIRECT",
        final_step_id="step_1",
        columns=[{"name": "bo_id", "label": "商机ID", "type": "string"},
                 {"name": "bo_name", "label": "商机名称", "type": "string"}],
    )
    records = await DirectAggregator().aggregate(agg, {"step_1": csv_path})
    assert records == [{"bo_id": "B001", "bo_name": "5G项目"}]


@pytest.mark.asyncio
async def test_sqlite_aggregator_joins_csvs(tmp_path: Path) -> None:
    emp_csv = make_csv(tmp_path, "api_emp.csv", [{"emp_id": "U001", "emp_name": "邹海天"}])
    bo_csv  = make_csv(tmp_path, "db_bo.csv",  [{"emp_id": "U001", "bo_name": "5G项目"}])
    agg = PlanAggregation(
        strategy="SQLITE_MEM",
        sqlite_sql="SELECT e.emp_name, b.bo_name FROM api_emp e JOIN db_bo b ON e.emp_id = b.emp_id",
        columns=[{"name": "emp_name", "label": "员工姓名", "type": "string"},
                 {"name": "bo_name", "label": "商机名称", "type": "string"}],
    )
    records = await SqliteAggregator().aggregate(
        agg,
        {"step_api_emp": emp_csv, "step_db_bo": bo_csv},
        csv_table_names={"step_api_emp": "api_emp", "step_db_bo": "db_bo"},
    )
    assert records[0]["emp_name"] == "邹海天"
    assert records[0]["bo_name"] == "5G项目"
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_aggregator.py -v`

Expected: FAIL

**Step 3: 实现**

- `aggregator/base.py`：`BaseAggregator(ABC)` 定义 `aggregate(agg, step_results)` 抽象方法
- `aggregator/direct_aggregator.py`：读取 `finalStepId` 的 CSV，按 columns 过滤重命名，返回 `list[dict]`
- `aggregator/sqlite_aggregator.py`：创建 `sqlite3.connect(":memory:")`，各 step CSV 按 `csvTableName` 用 `pandas` 或纯 csv 导入，执行 `sqliteSql`，返回结果

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_aggregator.py -v`

Expected: PASS

---

### Task 16: 集成 Object.query() 完整查询链路

**Files:**
- Modify: `datacloud-data-service/src/datacloud_data_sdk/object.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/executor/executor.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/integration/test_query_pipeline_integration.py`

**Step 1: 写失败集成测试**

```python
# tests/datacloud_data_sdk/integration/test_query_pipeline_integration.py
import pytest
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.plan.query_plan_generator import MockPlanGenerator
from datacloud_data_sdk.context import InvocationContext

REGISTRY = { ... }  # 使用 Task 7 的 REGISTRY，增加 DB source 和 table

MOCK_PLAN_DICT = {
    "question": "查商机",
    "can_answer": True,
    "steps": [{"step_id": "s1", "type": "SQL", "source_id": "SRC_CRM",
               "datasource_alias": "test_db",
               "sql_template": "SELECT '1' AS bo_id, '5G项目' AS bo_name",
               "output_ref": "bo_list"}],
    "aggregation": {"strategy": "DIRECT", "final_step_id": "s1",
                    "columns": [{"name": "bo_id", "label": "商机ID", "type": "string"},
                                {"name": "bo_name", "label": "商机名称", "type": "string"}]},
}


@pytest.mark.asyncio
async def test_object_query_returns_records(tmp_path) -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    obj = loader.get_object("sales_bo")
    obj.set_plan_generator(MockPlanGenerator(fixed_plan=MOCK_PLAN_DICT))
    obj.set_datasource_configs({"test_db": ...})  # SQLite 内存 DB
    obj.set_csv_base_dir(str(tmp_path))

    with InvocationContext(tenant_id="t1"):
        result = await obj.query("查商机")

    assert len(result["records"]) == 1
    assert result["records"][0]["bo_name"] == "5G项目"
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/integration/test_query_pipeline_integration.py -v`

Expected: FAIL

**Step 3: 实现 Executor 主调度器 + Object.query()**

在 `executor/executor.py` 实现 `Executor.run(tasks, request_id, step_results={})` → 按 task 类型分发到 `ApiExecutor` 或 `SqlExecutor` → 收集所有 step 的 `csv_path`。

在 `object.py` 中实现 `Object.query(question)` 完整链路：
1. `ObjectViewBuilder.build()` → ObjectViewPayload
2. `BasePlanGenerator.generate()` → QueryExecutionPlan
3. `PlanValidator.validate()` → 失败则抛 `PlanValidationError`
4. `DataPermissionRewriter.rewrite()`
5. `ExecutionObjectConverter.convert()` → tasks
6. `Executor.run()` → step_results
7. `BaseAggregator.aggregate()` → records

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/integration/test_query_pipeline_integration.py -v`

Expected: PASS

---

---

## P1.3.5 事件驱动层

> **设计参考：** 设计文档 §2（事件驱动架构）、§2.8（链路追踪）
>
> **策略：** Phase 1 使用**内存同步事件总线**；`Object.query()` 内部链路改为通过事件总线驱动，对外 API 不变。事件总线中间件自动记录 `EventSpan`，写入结构化日志。

### Task 16.5: 实现内存同步事件总线与事件类型

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/events/__init__.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/events/events.py`
- Create: `datacloud-data-service/src/datacloud_data_sdk/events/bus.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/test_event_bus.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_sdk/test_event_bus.py
import pytest
from datacloud_data_sdk.events.bus import EventBus
from datacloud_data_sdk.events.events import QueryRequestReceived, ObjectViewBuilt


@pytest.mark.asyncio
async def test_bus_delivers_event_to_subscriber() -> None:
    bus = EventBus()
    received = []

    async def handler(event: ObjectViewBuilt) -> None:
        received.append(event)

    bus.subscribe(ObjectViewBuilt, handler)
    await bus.publish(ObjectViewBuilt(
        request_id="req1",
        trace_id="tr1",
        object_view={"viewId": "v1"},
        question="查商机",
    ))
    assert len(received) == 1
    assert received[0].request_id == "req1"


@pytest.mark.asyncio
async def test_bus_no_subscriber_does_not_raise() -> None:
    bus = EventBus()
    await bus.publish(ObjectViewBuilt(
        request_id="req1", trace_id="tr1", object_view={}, question="?"
    ))
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_event_bus.py -v`

Expected: FAIL

**Step 3: 实现事件类型与事件总线**

在 `events/events.py` 中定义所有事件 dataclass（每个事件必须含 `request_id`、`trace_id`）：

```python
# events/events.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BaseEvent:
    request_id: str
    trace_id: str


@dataclass
class QueryRequestReceived(BaseEvent):
    question: str
    view_ids: list[str] = field(default_factory=list)
    object_ids: list[str] = field(default_factory=list)
    tenant_id: str = ""


@dataclass
class ObjectViewBuilt(BaseEvent):
    object_view: dict = field(default_factory=dict)   # ObjectViewPayload 序列化
    question: str = ""


@dataclass
class QueryPlanGenerated(BaseEvent):
    plan: dict = field(default_factory=dict)          # QueryExecutionPlan 序列化
    object_view: dict = field(default_factory=dict)
    question: str = ""


@dataclass
class PlanValidated(BaseEvent):
    valid: bool = False
    plan: dict = field(default_factory=dict)
    object_view: dict = field(default_factory=dict)
    question: str = ""
    errors: list[str] = field(default_factory=list)
    retry_count: int = 0


@dataclass
class PlanRetryRequested(BaseEvent):
    object_view: dict = field(default_factory=dict)
    question: str = ""
    validation_errors: list[str] = field(default_factory=list)
    retry_count: int = 0


@dataclass
class PlanValidationFailed(BaseEvent):
    errors: list[str] = field(default_factory=list)
    last_plan: dict = field(default_factory=dict)


@dataclass
class PlanRewritten(BaseEvent):
    rewritten_plan: dict = field(default_factory=dict)


@dataclass
class ExecutionTasksReady(BaseEvent):
    tasks: list[dict] = field(default_factory=list)
    aggregation: dict = field(default_factory=dict)


@dataclass
class StepsExecuted(BaseEvent):
    step_results: dict[str, str] = field(default_factory=dict)  # step_id → csv_path
    aggregation: dict = field(default_factory=dict)
    csv_table_names: dict[str, str] = field(default_factory=dict)


@dataclass
class AggregationCompleted(BaseEvent):
    records: list[dict] = field(default_factory=list)
    columns: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
```

在 `events/bus.py` 中实现内存同步事件总线：

```python
# events/bus.py
from __future__ import annotations
import asyncio
from collections import defaultdict
from typing import Any, Callable, Awaitable, Type
from datacloud_data_sdk.events.events import BaseEvent

HandlerType = Callable[[Any], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type, list[HandlerType]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: HandlerType) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: BaseEvent) -> None:
        for handler in self._handlers.get(type(event), []):
            await handler(event)
```

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_event_bus.py -v`

Expected: PASS

---

### Task 16.6: 实现 EventSpan 链路追踪中间件

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/events/tracing.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/test_tracing.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_sdk/test_tracing.py
import pytest
from datacloud_data_sdk.events.tracing import TracingMiddleware, EventSpan
from datacloud_data_sdk.events.bus import EventBus
from datacloud_data_sdk.events.events import ObjectViewBuilt, QueryPlanGenerated


@pytest.mark.asyncio
async def test_tracing_middleware_records_span() -> None:
    bus = EventBus()
    tracing = TracingMiddleware(bus)
    spans: list[EventSpan] = []
    tracing.on_span_complete(spans.append)

    async def handler(event: ObjectViewBuilt) -> None:
        await bus.publish(QueryPlanGenerated(
            request_id=event.request_id,
            trace_id=event.trace_id,
            plan={},
            object_view=event.object_view,
            question=event.question,
        ))

    tracing.subscribe(ObjectViewBuilt, handler, module_name="ObjectViewBuilder")

    await bus.publish(ObjectViewBuilt(
        request_id="req1", trace_id="tr1", object_view={}, question="查商机"
    ))

    assert len(spans) == 1
    span = spans[0]
    assert span.module == "ObjectViewBuilder"
    assert span.event_in == "ObjectViewBuilt"
    assert span.status == "ok"
    assert span.duration_ms >= 0
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_tracing.py -v`

Expected: FAIL

**Step 3: 实现 TracingMiddleware 和 EventSpan**

```python
# events/tracing.py
from __future__ import annotations
import uuid, time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Optional
from datacloud_data_sdk.events.bus import EventBus
from datacloud_data_sdk.events.events import BaseEvent


@dataclass
class EventSpan:
    trace_id: str
    request_id: str
    span_id: str
    parent_span_id: Optional[str]
    module: str
    event_in: str
    event_out: Optional[str]
    started_at: float
    finished_at: float
    duration_ms: float
    status: str                    # ok / error
    error_message: Optional[str] = None
    input_summary: Optional[dict] = None
    output_summary: Optional[dict] = None


SpanCallback = Callable[[EventSpan], None]


class TracingMiddleware:
    """将 EventBus 订阅包装为带 span 记录的追踪版本。"""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._callbacks: list[SpanCallback] = []

    def on_span_complete(self, callback: SpanCallback) -> None:
        self._callbacks.append(callback)

    def subscribe(
        self,
        event_type: type,
        handler: Callable[[Any], Awaitable[None]],
        module_name: str,
    ) -> None:
        async def traced_handler(event: BaseEvent) -> None:
            span_id = str(uuid.uuid4())[:8]
            started_at = time.monotonic()
            status = "ok"
            error_msg = None
            event_out = None
            try:
                await handler(event)
            except Exception as e:
                status = "error"
                error_msg = str(e)
                raise
            finally:
                finished_at = time.monotonic()
                span = EventSpan(
                    trace_id=getattr(event, "trace_id", ""),
                    request_id=getattr(event, "request_id", ""),
                    span_id=span_id,
                    parent_span_id=None,
                    module=module_name,
                    event_in=type(event).__name__,
                    event_out=event_out,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=(finished_at - started_at) * 1000,
                    status=status,
                    error_message=error_msg,
                )
                for cb in self._callbacks:
                    cb(span)

        self._bus.subscribe(event_type, traced_handler)
```

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_tracing.py -v`

Expected: PASS

---

### Task 16.7: 将 Object.query() 链路改为事件驱动 + 编排层重试

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/events/handlers.py`
- Modify: `datacloud-data-service/src/datacloud_data_sdk/object.py`
- Create: `datacloud-data-service/tests/datacloud_data_sdk/test_event_driven_query.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_sdk/test_event_driven_query.py
import pytest
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.plan.query_plan_generator import MockPlanGenerator
from datacloud_data_sdk.context import InvocationContext

REGISTRY = {
    "functions": [],
    "objects": [{
        "object_code": "sales_bo",
        "object_name": "销售商机",
        "description": "商机对象",
        "source_type": "DB",
        "datasource_alias": "test_db",
        "table_name": "sales_business_opportunity",
        "fields": [
            {"field_code": "bo_id", "field_name": "商机ID", "field_type": "STRING"},
            {"field_code": "bo_name", "field_name": "商机名称", "field_type": "STRING"},
        ],
        "actions": [],
        "relations": [],
    }],
    "relations": [],
}

MOCK_PLAN = {
    "question": "查商机",
    "can_answer": True,
    "steps": [{"step_id": "s1", "type": "SQL", "source_id": "SRC_DB",
               "datasource_alias": "test_db",
               "sql_template": "SELECT '1' AS bo_id, '5G项目' AS bo_name",
               "output_ref": "bo_list"}],
    "aggregation": {"strategy": "DIRECT", "final_step_id": "s1",
                    "columns": [{"name": "bo_id", "label": "商机ID", "type": "string"},
                                {"name": "bo_name", "label": "商机名称", "type": "string"}]},
}


@pytest.mark.asyncio
async def test_event_driven_query_returns_records(tmp_path) -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    obj = loader.get_object("sales_bo")
    obj.configure(
        plan_generator=MockPlanGenerator(fixed_plan=MOCK_PLAN),
        datasource_configs={"test_db": ...},   # SQLite 内存 DB config
        csv_base_dir=str(tmp_path),
        use_event_bus=True,                    # 新增：通过事件总线驱动
    )
    with InvocationContext(tenant_id="t1"):
        result = await obj.query("查商机")

    assert len(result["records"]) == 1
    assert result["meta"]["trace_id"] != ""        # 链路追踪 trace_id 透出


@pytest.mark.asyncio
async def test_event_driven_query_retries_on_validation_failure(tmp_path) -> None:
    """第一次计划校验失败，第二次返回正确计划，触发重试逻辑。"""
    from datacloud_data_sdk.plan.query_plan_generator import SequentialMockPlanGenerator

    bad_plan = {"question": "?", "can_answer": True,
                "steps": [{"step_id": "s1", "type": "SQL", "source_id": "NONEXISTENT",
                            "output_ref": "x"}],
                "aggregation": {"strategy": "DIRECT", "final_step_id": "s1", "columns": []}}

    gen = SequentialMockPlanGenerator([bad_plan, MOCK_PLAN])
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    obj = loader.get_object("sales_bo")
    obj.configure(
        plan_generator=gen,
        datasource_configs={"test_db": ...},
        csv_base_dir=str(tmp_path),
        use_event_bus=True,
        max_plan_retries=2,
    )
    with InvocationContext(tenant_id="t1"):
        result = await obj.query("查商机")

    assert len(result["records"]) == 1
    assert gen.call_count == 2                     # 验证触发了重试
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_event_driven_query.py -v`

Expected: FAIL

**Step 3: 实现事件处理器与编排层**

在 `events/handlers.py` 中为每个事件注册处理函数，将现有直调逻辑拆解为事件处理链：

- `on_query_request_received` → 调 `ObjectViewBuilder` → 发布 `ObjectViewBuilt`
- `on_object_view_built` → 调 `QueryPlanGenerator.generate()` → 发布 `QueryPlanGenerated`
- `on_query_plan_generated` → 调 `PlanValidator.validate()` → 发布 `PlanValidated`
- `on_plan_validated_valid` → 调 `DataPermissionRewriter.rewrite()` → 发布 `PlanRewritten`
- `on_plan_validated_invalid`（**编排层**）→ 若 `retry_count < max_retries` 发布 `PlanRetryRequested`；否则发布 `PlanValidationFailed`
- `on_plan_retry_requested` → 重新调 `QueryPlanGenerator.generate()`（含 `validationErrors`）→ 发布 `QueryPlanGenerated`
- `on_plan_rewritten` → 调 `ExecutionObjectConverter.convert()` → 发布 `ExecutionTasksReady`
- `on_execution_tasks_ready` → 调 `Executor.run()` → 发布 `StepsExecuted`
- `on_steps_executed` → 调 `Aggregator.aggregate()` → 发布 `AggregationCompleted`

在 `MockPlanGenerator` 旁增加 `SequentialMockPlanGenerator(plans_list)`，按调用顺序返回计划（支持重试测试）。

修改 `Object.query()` 增加 `use_event_bus: bool` 选项：
- `False`（默认）：原直调链路（向后兼容）
- `True`：通过 `EventBus` + `TracingMiddleware` 驱动，发布 `QueryRequestReceived`，等待 `AggregationCompleted`

**Step 4: 运行所有事件驱动相关测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_event_bus.py tests/datacloud_data_sdk/test_tracing.py tests/datacloud_data_sdk/test_event_driven_query.py -v`

Expected: 全部 PASS

---

## P1.4 服务层

### Task 17: 配置层与 FastAPI 应用骨架

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_service/config.py`
- Modify: `datacloud-data-service/src/datacloud_data_service/__init__.py`
- Create: `datacloud-data-service/src/datacloud_data_service/api/__init__.py`
- Create: `datacloud-data-service/src/datacloud_data_service/api/routes.py`
- Create: `datacloud-data-service/tests/datacloud_data_service/__init__.py`
- Create: `datacloud-data-service/tests/datacloud_data_service/test_health.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_service/test_health.py
from fastapi.testclient import TestClient


def test_health_check() -> None:
    from datacloud_data_service.api.routes import create_app
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_service/test_health.py -v`

Expected: FAIL

**Step 3: 实现最小 FastAPI 应用**

在 `config.py` 实现 `Settings`（pydantic-settings），读取 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、`ONTOLOGY_PATH`、`SQL_EXECUTION_MODE` 等环境变量。

在 `api/routes.py` 实现 `create_app() -> FastAPI`，注册 `/health` 路由，后续挂载 `/api/v1/query` 和 `/api/v1/mcp`。

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_service/test_health.py -v`

Expected: PASS

---

### Task 18: 实现 MCP tools/list 与 tools/call 路由

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_service/tools/__init__.py`
- Create: `datacloud-data-service/src/datacloud_data_service/tools/registry.py`
- Create: `datacloud-data-service/src/datacloud_data_service/tools/action_tool_generator.py`
- Create: `datacloud-data-service/src/datacloud_data_service/api/mcp_handler.py`
- Create: `datacloud-data-service/tests/datacloud_data_service/test_mcp_tools_list.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_service/test_mcp_tools_list.py
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


def get_client():
    from datacloud_data_service.api.routes import create_app
    return TestClient(create_app())


def test_tools_list_returns_unified_query_tool() -> None:
    client = get_client()
    resp = client.post(
        "/api/v1/mcp",
        json={"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}},
        headers={"X-Tenant-Id": "t1", "X-User-Id": "u1",
                 "X-Session-Id": "s1", "Authorization": "Bearer tok",
                 "X-System-Code": "dc"},
    )
    assert resp.status_code == 200
    tools = resp.json()["result"]["tools"]
    names = [t["name"] for t in tools]
    assert "unified_data_query" in names


def test_tools_list_missing_tenant_id_returns_400() -> None:
    client = get_client()
    resp = client.post(
        "/api/v1/mcp",
        json={"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}},
    )
    assert resp.status_code == 400
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_service/test_mcp_tools_list.py -v`

Expected: FAIL

**Step 3: 实现 MCP tools/list**

在 `tools/registry.py` 实现 `ToolRegistry`，`list_tools(view_id, object_ids)` → 返回 `unified_data_query` + 从 `OntologyLoader` 加载的 action tools（通过 `ActionToolGenerator.build(obj, schema)`）。

在 `tools/action_tool_generator.py` 实现 `ActionToolGenerator.build()` → `MCPTool(name, description, inputSchema)`。

在 `api/mcp_handler.py` 实现 MCP JSON-RPC 2.0 handler：校验通用 Header → 设置 `InvocationContext` → `tools/list` 或 `tools/call` 分流。

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_service/test_mcp_tools_list.py -v`

Expected: PASS

---

### Task 19: 实现操作类工具执行（ActionExecutor）

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_service/tools/param_mapper.py`
- Create: `datacloud-data-service/src/datacloud_data_service/tools/term_resolver.py`
- Create: `datacloud-data-service/src/datacloud_data_service/tools/action_executor.py`
- Create: `datacloud-data-service/tests/datacloud_data_service/test_mcp_tools_call.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_service/test_mcp_tools_call.py
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

HEADERS = {"X-Tenant-Id": "t1", "X-User-Id": "u1",
           "X-Session-Id": "s1", "Authorization": "Bearer tok",
           "X-System-Code": "dc"}


def get_client():
    from datacloud_data_service.api.routes import create_app
    return TestClient(create_app())


def test_tools_call_action_returns_records() -> None:
    with patch(
        "datacloud_data_service.tools.action_executor.ActionExecutor.execute",
        new_callable=AsyncMock,
        return_value={"records": [{"bo_id": "B001"}], "meta": {}},
    ):
        client = get_client()
        resp = client.post(
            "/api/v1/mcp",
            json={"jsonrpc": "2.0", "id": "2", "method": "tools/call",
                  "params": {"name": "query_bo_by_owner", "arguments": {"owner_id": "U001"}}},
            headers=HEADERS,
        )
    assert resp.status_code == 200
    content = resp.json()["result"]["content"]
    assert len(content) > 0


def test_tools_call_unknown_tool_returns_error() -> None:
    client = get_client()
    resp = client.post(
        "/api/v1/mcp",
        json={"jsonrpc": "2.0", "id": "3", "method": "tools/call",
              "params": {"name": "nonexistent_tool", "arguments": {}}},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert "error" in resp.json() or resp.json()["result"].get("isError") is True
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_service/test_mcp_tools_call.py -v`

Expected: FAIL

**Step 3: 实现操作类工具执行流水线**

- `tools/param_mapper.py`：`ParamMapper.map_names(arguments, params)` → 标准化 key；`map_to_physical(resolved, params)` → 按 `mapping_path` 构造 API body/query
- `tools/term_resolver.py`：`TermResolver.resolve(args, params, term_loader)` → 术语标签转标准 code；失败返回 `TermResolutionError`
- `tools/action_executor.py`：`ActionExecutor.execute(action_code, arguments, loader)` → 执行完整参数流水线 → `Object.invoke_action()` → 返回格式化结果

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_service/test_mcp_tools_call.py -v`

Expected: PASS

---

### Task 20: 实现 REST POST /api/v1/query

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_service/api/query.py`
- Create: `datacloud-data-service/tests/datacloud_data_service/test_rest_query.py`

**Step 1: 写失败测试**

```python
# tests/datacloud_data_service/test_rest_query.py
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

HEADERS = {"X-Tenant-Id": "t1", "X-User-Id": "u1", "X-Session-Id": "s1",
           "Authorization": "Bearer tok", "X-System-Code": "dc",
           "X-View-Ids": "scene_01"}

MOCK_RESULT = {
    "records": [{"bo_id": "B001", "bo_name": "5G项目"}],
    "meta": {"total": 1, "columns": []},
}


def test_rest_query_returns_records() -> None:
    with patch(
        "datacloud_data_sdk.view.View.query",
        new_callable=AsyncMock,
        return_value=MOCK_RESULT,
    ):
        from datacloud_data_service.api.routes import create_app
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/query",
            json={"question": "查商机"},
            headers=HEADERS,
        )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["records"][0]["bo_id"] == "B001"
```

**Step 2: 运行失败测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_service/test_rest_query.py -v`

Expected: FAIL

**Step 3: 实现 /api/v1/query**

在 `api/query.py` 实现 `POST /api/v1/query`：校验 Header → 设置 `InvocationContext` → 加载 `OntologyLoader`（按 `X-View-Ids` 或 `X-Object-Ids`）→ 调用 `View.query(question)` 或 `Object.query(question)` → 返回统一响应格式。

**Step 4: 运行测试**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_service/test_rest_query.py -v`

Expected: PASS

---

## 完整测试验证

### Task 21: 运行所有单元与集成测试

Run: `cd datacloud-data-service && pytest tests/ -v --tb=short`

Expected: 全部 PASS，无跳过（除有外部依赖标注的集成测试）。

### Task 22: CRM 端到端测试（需要 datacloud-mock）

**前提：** 启动 `datacloud-mock` 服务，确保 CRM Demo API 可用，配置 `.env` 指向真实 MySQL 或 SQLite 测试数据库。

**运行：** `cd datacloud-data-service && pytest tests/e2e/ -v`

**五个核心场景验证：**

| 场景 | 预期 |
|------|------|
| 自然语言：「查询邹海天的商机」 | records 非空，含 bo_name |
| 跨数据源：「邹海天签了合同的商机」 | SQLITE_MEM 聚合，含 contract_id |
| 不可回答：「按合同金额统计」 | canAnswer=false，clarification 非空 |
| MCP `query_bo_by_owner` | tools/call 直接返回，不走 LLM |
| 术语值：传"已签约"→"SIGNED" | TermResolver 正确映射 |
