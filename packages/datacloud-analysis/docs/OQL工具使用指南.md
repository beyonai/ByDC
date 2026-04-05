# OQL 工具使用指南

## 概述

OQL (Ontology Query Language) 工具提供了两个核心工具，用于 LLM 与本体数据进行交互：

1. **QueryObjects**: 查询本体对象或视图的实例列表、详情、聚合统计
2. **ExecuteAction**: 执行有副作用的业务动作（创建、更新、删除等）

## 安装与配置

### 1. 依赖初始化

在应用启动时，需要初始化全局依赖：

```python
from datacloud_analysis.dependencies import init_dependencies
from datacloud_data_sdk.oql import OqlRouter

# 创建必要的实例
oql_router = OqlRouter(registry=your_registry)
action_service = YourActionService()
term_resolver = YourTermResolver()
executor = YourExecutor()
datasource_registry = YourDatasourceRegistry()

# 初始化依赖
init_dependencies(
    oql_router=oql_router,
    action_service=action_service,
    term_resolver=term_resolver,
    executor=executor,
    datasource_registry=datasource_registry,
)
```

### 2. 工具注册

将 OQL 工具注册到 LangChain Agent：

```python
from datacloud_analysis.tools.oql import query_objects, execute_action

tools = [
    query_objects,
    execute_action,
    # ... 其他工具
]

agent = create_agent(tools=tools)
```

## QueryObjects 工具

### 功能说明

查询本体对象或视图的实例数据，支持：
- 列表查询
- 详情查询
- 聚合统计
- 关系漫游（JOIN）
- 条件过滤
- 排序和分页

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| object_type | str | 是 | 对象类型名或视图名 |
| select | list[str] | 否 | 返回属性列表，省略则返回全部 |
| where | list[dict] | 否 | 行级过滤条件 |
| include_links | list[dict] | 否 | 关系漫游配置 |
| metrics | list[dict] | 否 | 聚合指标 |
| group_by | list[dict] | 否 | 分组字段 |
| having | list[dict] | 否 | 聚合后过滤 |
| order_by | list[dict] | 否 | 排序规则 |
| limit | int | 否 | 返回记录数上限（默认100） |
| offset | int | 否 | 分页偏移量（默认0） |

### 使用示例

#### 1. 基本列表查询

```python
result = query_objects(
    object_type="员工",
    select=["姓名", "部门", "薪资"],
    where=[
        {"field": "部门", "op": "eq", "value": "技术部"}
    ],
    order_by=[
        {"field": "薪资", "direction": "desc"}
    ],
    limit=20
)
```

**响应格式**:
```json
{
    "status": "success",
    "tool": "QueryObjects",
    "result": {
        "columns": ["姓名", "部门", "薪资"],
        "rows": [
            ["张三", "技术部", 15000],
            ["李四", "技术部", 12000]
        ],
        "total": 2,
        "returned": 2,
        "pagination": {
            "limit": 20,
            "offset": 0,
            "has_next": false
        }
    }
}
```

#### 2. 聚合统计查询

```python
result = query_objects(
    object_type="订单",
    metrics=[
        {"field": "订单金额", "aggregation": "sum", "alias": "总金额"},
        {"field": "订单ID", "aggregation": "count", "alias": "订单数"}
    ],
    group_by=[
        {"field": "客户ID"}
    ],
    having=[
        {"field": "总金额", "op": "gt", "value": 10000}
    ]
)
```

#### 3. 关系漫游查询

```python
result = query_objects(
    object_type="订单",
    select=["订单号", "金额"],
    include_links=[
        {
            "relation": "订单_客户",
            "fields": ["客户名称", "联系电话"]
        },
        {
            "relation": "订单_产品",
            "fields": ["产品名称", "单价"]
        }
    ]
)
```

#### 4. 复杂条件查询

```python
result = query_objects(
    object_type="航班",
    select=["航班号", "起飞时间", "状态"],
    where=[
        {
            "logic": "and",
            "conditions": [
                {"field": "状态", "op": "in", "value": ["延误", "取消"]},
                {"field": "起飞时间", "op": "relativeDate", "value": "today"}
            ]
        }
    ]
)
```

### WHERE 条件操作符

| 操作符 | 说明 | 示例 |
|--------|------|------|
| eq | 等于 | `{"field": "状态", "op": "eq", "value": "正常"}` |
| ne | 不等于 | `{"field": "状态", "op": "ne", "value": "取消"}` |
| gt | 大于 | `{"field": "薪资", "op": "gt", "value": 10000}` |
| gte | 大于等于 | `{"field": "薪资", "op": "gte", "value": 10000}` |
| lt | 小于 | `{"field": "年龄", "op": "lt", "value": 30}` |
| lte | 小于等于 | `{"field": "年龄", "op": "lte", "value": 30}` |
| in | 在列表中 | `{"field": "部门", "op": "in", "value": ["技术部", "产品部"]}` |
| nin | 不在列表中 | `{"field": "状态", "op": "nin", "value": ["删除", "禁用"]}` |
| like | 模糊匹配 | `{"field": "姓名", "op": "like", "value": "%张%"}` |
| between | 区间 | `{"field": "薪资", "op": "between", "value": [5000, 15000]}` |
| isNull | 为空 | `{"field": "离职日期", "op": "isNull"}` |
| relativeDate | 相对日期 | `{"field": "创建时间", "op": "relativeDate", "value": "last_7_days"}` |

### 聚合函数

| 函数 | 说明 |
|------|------|
| count | 计数 |
| count_distinct | 去重计数 |
| sum | 求和 |
| avg | 平均值 |
| max | 最大值 |
| min | 最小值 |

## ExecuteAction 工具

### 功能说明

执行有副作用的业务动作，支持：
- 标准 CRUD 操作（创建、更新、删除）
- 自定义业务动作

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| action_type | str | 是 | 动作类型名称 |
| target_objects | list[str] | 否 | 目标对象ID列表 |
| payload | dict | 否 | 动作参数字典 |

### 使用示例

#### 1. 创建对象

```python
result = execute_action(
    action_type="创建员工",
    payload={
        "姓名": "张三",
        "部门": "技术部",
        "职位": "工程师",
        "入职日期": "2024-01-01"
    }
)
```

**响应格式**:
```json
{
    "status": "success",
    "tool": "ExecuteAction",
    "result": {
        "action_type": "创建员工",
        "affected_count": 1,
        "affected_objects": ["EMP001"],
        "details": {
            "created_id": "EMP001"
        }
    }
}
```

#### 2. 更新对象

```python
result = execute_action(
    action_type="更新员工信息",
    target_objects=["EMP001", "EMP002"],
    payload={
        "部门": "产品部",
        "更新原因": "组织调整"
    }
)
```

#### 3. 删除对象

```python
result = execute_action(
    action_type="删除员工",
    target_objects=["EMP003"]
)
```

#### 4. 自定义业务动作

```python
result = execute_action(
    action_type="发送延误通知",
    target_objects=["FL001", "FL002"],
    payload={
        "通知类型": "短信",
        "模板": "延误致歉"
    }
)
```

## 错误处理

### 错误响应格式

```json
{
    "status": "error",
    "error_code": "OQL_ERR_UNKNOWN_OBJECT",
    "message": "对象 'Employee' 不存在",
    "detail": {
        "object_type": "Employee"
    }
}
```

### 常见错误代码

| 错误代码 | 说明 |
|---------|------|
| OQL_ERR_UNKNOWN_OBJECT | 对象不存在 |
| OQL_ERR_UNKNOWN_FIELD | 字段不存在 |
| OQL_ERR_UNKNOWN_RELATION | 关系不存在 |
| OQL_ERR_UNSUPPORTED_OPERATION | 不支持的操作 |
| OQL_ERR_INVALID_OPERATOR | 无效的操作符 |
| OQL_ERR_EXECUTION_FAILED | 执行失败 |
| OQL_ERR_TERM_RESOLUTION_FAILED | 术语解析失败 |
| INTERNAL_ERROR | 内部错误 |

## Pipeline 模式

对于需要多步骤执行的复杂查询，可以使用 Pipeline 模式（由 OqlRouter 自动处理）：

```python
# Pipeline 会自动识别并执行
pipeline = [
    {
        "step_id": "s1",
        "tool": "QueryObjects",
        "parameters": {
            "object_type": "航班",
            "select": ["航班号", "延误时长"],
            "where": [
                {"field": "状态", "op": "eq", "value": "延误"},
                {"field": "延误时长", "op": "gt", "value": 120}
            ]
        }
    },
    {
        "step_id": "s2",
        "tool": "ExecuteAction",
        "parameters": {
            "action_type": "发送延误通知",
            "target_objects": {"$ref": "s1.result[*].航班号"},
            "payload": {
                "通知类型": "短信"
            }
        }
    }
]
```

## 最佳实践

### 1. 分页查询大数据集

```python
# 避免一次性查询大量数据
result = query_objects(
    object_type="订单",
    limit=100,  # 使用合理的 limit
    offset=0
)

# 检查是否有更多数据
if result["result"]["pagination"]["has_next"]:
    # 继续查询下一页
    pass
```

### 2. 使用聚合减少数据传输

```python
# 优先使用聚合查询，而不是查询全部数据后在内存中计算
result = query_objects(
    object_type="订单",
    metrics=[
        {"field": "订单金额", "aggregation": "sum"}
    ],
    group_by=[{"field": "日期"}]
)
```

### 3. 合理使用 include_links

```python
# 只获取需要的关联字段
result = query_objects(
    object_type="订单",
    include_links=[
        {
            "relation": "订单_客户",
            "fields": ["客户名称"]  # 只获取需要的字段
        }
    ]
)
```

### 4. 错误处理

```python
result = query_objects(object_type="员工")

if result["status"] == "error":
    error_code = result["error_code"]
    if error_code == "OQL_ERR_UNKNOWN_OBJECT":
        # 处理对象不存在的情况
        pass
    else:
        # 处理其他错误
        pass
```

## 参考资料

- [OQL JSON Schema](./OQL.schema.json) - 完整的协议定义
- [本体推理引擎重构方案](./本体推理引擎重构方案.md) - 架构设计文档
- [OQL翻译规则方案设计](../../datacloud-data/docs/OQL翻译规则方案设计.md) - 实现细节
