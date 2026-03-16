# 术语-图模型整合分析

## 项目背景

用户希望将术语系统与现有的元数据图模型建立联系。具体需求：术语"王小明"应该作为"人员姓名"字段的实例，与"人员对象"的"人员姓名"字段建立联系。

## 现有架构分析

### 1. 术语ER设计 (@术语设计/er-关系.md)

**核心实体：**
- **Domain** - 领域分类（支持层级）
- **TermType** - 术语类型（列表/字典/本体/文档）
- **TermLibrary** - 术语库（来源管理）
- **Term** - 术语主表（核心实体）
- **TermRelation** - 术语间关系（有向）
- **TermName** - 术语名称（支持别名、缩写）
- **TermVocabulary** - 分词词典（jieba支持）

**关键关系：**
- TermLibrary → Term (来源)
- Domain → Term (包含)
- Domain → Domain (父级)
- TermType → Term (分类)
- Term → TermRelation (源术语/目标术语)
- Term → TermName (名称)
- TermName → TermVocabulary (去重派生)

### 2. 图模型 (@my_graph.py)

**现有节点类型：**
- `ObjectNode` - 对象节点 (绿色)
- `FieldNode` - 字段节点 (蓝色) - **已包含 term_meta 属性**
- `ActionNode` - 动作节点 (橙色)
- `ParameterNode` - 参数节点 (紫色) - **已包含 term_meta 属性**
- `FunctionNode` - 函数节点 (红色)
- `ViewNode` - 视图节点 (棕色)
- `ObjectRelationNode` - 对象关系节点 (灰色)

**现有边类型：**
- `HAS_FIELD` - 对象包含字段
- `HAS_ACTION` - 对象包含动作
- `HAS_PARAMETER` - 动作包含参数
- `USES_FUNCTION` - 动作使用函数
- `BINDS_TO_OBJECT` - 参数绑定到对象
- `BINDS_TO_FIELD` - 参数绑定到字段
- `CONTAINS` - 视图包含对象
- `DEFINES_RELATION` - 视图定义关系
- `SOURCE_FIELD`/`TARGET_FIELD` - 关系的源/目标字段
- `INTERSECTS` - 基于字段交集

### 3. 当前数据关联方式

**场景JSON中的 termMeta 结构：**
```json
"termMeta": {
  "datasetId": 760436323052421,
  "termMasterType": "list",
  "termTypeCode": "staffName",
  "termField": "code"
}
```

**当前实现：**
- 字段和参数通过 `termMeta` 属性与术语关联
- `termTypeCode` 引用 TermType（术语类型）
- 术语元数据以 JSON 形式存储在节点属性中
- 但术语本身（Term）还不是图中的节点

---

## 统一Term节点设计方案

### 核心设计原则

**只创建一个 "王小明" Term节点，用不同的边连接不同的TermType**

```
                    ┌─────────────────┐
                    │   Term(王小明)   │
                    │    ID: T001     │
                    │  Name: 王小明   │
                    └────────┬────────┘
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
           ▼                 ▼                 ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ TermType(员工)   │  │TermType(员工名称) │  │ 其他类型...      │
│   type=3(本体)   │  │   type=1(列表)   │  │                  │
└──────────────────┘  └──────────────────┘  └──────────────────┘
        │                      │
        │ IS_A                 │ IS_MEMBER_OF
        │ (是一个)              │ (是成员)
        ▼                      ▼
   "王小明是员工"          "王小明是员工名称
                          列表中的一个值"
```

---

## 边的语义设计

### 关系型命名方案

```python
class EdgeLabel(Enum):
    # ... 现有边 ...

    # 本体论关系 (type=3)
    IS_INSTANCE_OF = "IS_INSTANCE_OF"      # Term -> TermType(本体)
    HAS_INSTANCE = "HAS_INSTANCE"          # TermType(本体) -> Term

    # 列表关系 (type=1)
    IS_MEMBER_OF = "IS_MEMBER_OF"          # Term -> TermType(列表)
    HAS_MEMBER = "HAS_MEMBER"              # TermType(列表) -> Term

    # 字典关系 (type=2)
    IS_ENTRY_OF = "IS_ENTRY_OF"            # Term -> TermType(字典)
    HAS_ENTRY = "HAS_ENTRY"                # TermType(字典) -> Term

    # 文档关系 (type=4)
    IS_DOCUMENT_OF = "IS_DOCUMENT_OF"      # Term -> TermType(文档)
    HAS_DOCUMENT = "HAS_DOCUMENT"          # TermType(文档) -> Term

    # 字段-术语类型关系
    DEFINED_BY_TERM_TYPE = "DEFINED_BY_TERM_TYPE"  # Field -> TermType
```

---

## 完整图模型架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        统一Term节点设计                          │
└─────────────────────────────────────────────────────────────────┘

                    ┌──────────────────────┐
                    │    Term(王小明)       │
                    │  ID: term_wangxiaoming│
                    │  StandardName: 王小明 │
                    └──────────┬───────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│ TermType(员工) │      │TermType(员工名称)│     │TermType(部门经理)│
├───────────────┤      ├───────────────┤      ├───────────────┤
│Code: employee │      │Code: emp_name │      │Code: manager  │
│Name: 员工      │      │Name: 员工名称  │      │Name: 部门经理  │
│Type: 本体(3)   │      │Type: 列表(1)   │      │Type: 本体(3)   │
└───────┬───────┘      └───────┬───────┘      └───────┬───────┘
        │                      │                      │
        │ IS_INSTANCE_OF       │ IS_MEMBER_OF         │ IS_INSTANCE_OF
        │ (王小明是一个员工)    │ (王小明是员工名称    │ (王小明是一个部门经理)
        │                      │  列表中的一个值)      │
        ▼                      ▼                      ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│  Object(员工对象)│      │ Field(人员姓名) │      │ 其他对象...    │
└───────────────┘      └───────────────┘      └───────────────┘
                               │
                               │ DEFINED_BY_TERM_TYPE
                               ▼
                        TermType(员工名称)
                               │
                               │ CONTAINS_VALUE
                               ▼
                            "王小明" (字符串值)
```

**边的属性示例：**

| 边 | 属性 | 值 |
|---|---|---|
| Term(王小明) -> TermType(员工) | relation_type | "instance" |
| | semantic | "王小明是员工这个概念的一个实例" |
| | source_context | "本体定义" |
| Term(王小明) -> TermType(员工名称) | relation_type | "member" |
| | semantic | "王小明是员工名称列表中的一个有效值" |
| | source_context | "字段取值范围" |

---

## 新增节点类型

### TermNode（术语节点）

```python
@dataclass
class TermNode:
    id: str                    # 唯一标识（如 "term_wangxiaoming"）
    name: str                  # 标准名称（如 "王小明"）
    properties: Properties     # 属性：拼音、别名、标签等
    # 注意：不存储 primary_type_id，类型关系完全通过边来表达
```

**示例：**
```python
wang_xiaoming = TermNode(
    id="term_wangxiaoming",
    name="王小明",
    properties=Properties({
        "pinyin": "wangxiaoming",
        "aliases": ["小明", "王工"],
        "tags": {"department": "技术部", "level": "P6"}
    })
)
```

---

## 新增边类型

```python
class EdgeLabel(Enum):
    # ... 现有边类型 ...

    # === 术语-术语类型关系 ===
    # 本体论关系 (type=3)
    IS_INSTANCE_OF = "IS_INSTANCE_OF"      # Term -> TermType(本体)
    HAS_INSTANCE = "HAS_INSTANCE"          # TermType(本体) -> Term

    # 列表关系 (type=1)
    IS_MEMBER_OF = "IS_MEMBER_OF"          # Term -> TermType(列表)
    HAS_MEMBER = "HAS_MEMBER"              # TermType(列表) -> Term

    # 字典关系 (type=2)
    IS_ENTRY_OF = "IS_ENTRY_OF"            # Term -> TermType(字典)
    HAS_ENTRY = "HAS_ENTRY"                # TermType(字典) -> Term

    # 文档关系 (type=4)
    IS_DOCUMENT_OF = "IS_DOCUMENT_OF"      # Term -> TermType(文档)
    HAS_DOCUMENT = "HAS_DOCUMENT"          # TermType(文档) -> Term

    # === 字段-术语类型关系 ===
    DEFINED_BY_TERM_TYPE = "DEFINED_BY_TERM_TYPE"    # Field -> TermType
    USES_TERM_TYPE = "USES_TERM_TYPE"                # Parameter -> TermType
```

---

## 方案优势

### 1. 数据一致性

```python
# 只有一个王小明节点
wang_xiaoming = Term(
    id="term_wangxiaoming",
    name="王小明",
    # 标准名称、拼音、标签等只存一份
    properties={
        "pinyin": "wangxiaoming",
        "aliases": ["小明", "王工"],
        "tags": {"department": "技术部", "level": "P6"}
    }
)
```

### 2. 灵活的多重身份

```python
# 王小明可以同时是：
- 员工（本体实例）
- 员工名称（列表成员）
- 部门经理（本体实例）
- 项目成员（列表成员）
- 等等...

# 通过不同的边连接，不需要重复创建节点
```

### 3. 查询便捷

```cypher
// 查询王小明所有的身份
MATCH (t:Term {name: "王小明"})-[r]->(tt:TermType)
RETURN tt.name, type(r), r.semantic

// 结果：
// tt.name     | type(r)         | r.semantic
// ------------|-----------------|--------------------------
// 员工         | IS_INSTANCE_OF  | 王小明是员工这个概念...
// 员工名称     | IS_MEMBER_OF    | 王小明是员工名称列表...
// 部门经理     | IS_INSTANCE_OF  | 王小明是部门经理...
```

---

## 需要注意的问题

### 问题1：同名Term怎么处理？

**问题**：如果有两个不同的"王小明"（不同部门），怎么办？

**解决方案：**
```python
# 唯一ID包含上下文
Term(id="emp_tech_wangxiaoming", name="王小明")  # 技术部王小明
Term(id="emp_hr_wangxiaoming", name="王小明")    # HR部王小明

# 或者通过属性区分
Term(id="wangxiaoming_001", name="王小明", properties={
    "department": "技术部",
    "employee_id": "EMP001"
})
```

### 问题2：如何保证边的语义一致性？

**问题**：如何防止错误地创建 "王小明 IS_INSTANCE_OF 员工名称"？

**解决方案**：在添加边时进行类型检查
```python
def add_term_to_type(self, term: TermNode, term_type: TermTypeNode,
                     relation_type: str):
    """
    relation_type: "instance" | "member" | "entry" | "document"
    """
    # 校验关系类型是否匹配TermType的type
    if relation_type == "instance" and term_type.type != 3:
        raise ValueError(f"TermType {term_type.name} 不是本体类型，不能使用instance关系")

    if relation_type == "member" and term_type.type != 1:
        raise ValueError(f"TermType {term_type.name} 不是列表类型，不能使用member关系")

    # 创建边
    edge_label = self._get_edge_label(relation_type)
    self.graph.add_edge(term.id, term_type.id,
                       relation=edge_label,
                       relation_type=relation_type)
```

---

## 实现代码框架

```python
# 1. 定义边类型
class TermEdgeLabel(Enum):
    # 本体关系 (type=3)
    IS_INSTANCE_OF = "IS_INSTANCE_OF"      # Term -> TermType(本体)
    HAS_INSTANCE = "HAS_INSTANCE"          # TermType(本体) -> Term

    # 列表关系 (type=1)
    IS_MEMBER_OF = "IS_MEMBER_OF"          # Term -> TermType(列表)
    HAS_MEMBER = "HAS_MEMBER"              # TermType(列表) -> Term

    # 字典关系 (type=2)
    IS_ENTRY_OF = "IS_ENTRY_OF"            # Term -> TermType(字典)
    HAS_ENTRY = "HAS_ENTRY"                # TermType(字典) -> Term

    # 文档关系 (type=4)
    IS_DOCUMENT_OF = "IS_DOCUMENT_OF"      # Term -> TermType(文档)
    HAS_DOCUMENT = "HAS_DOCUMENT"          # TermType(文档) -> Term

    # 字段-术语类型关系
    DEFINED_BY_TERM_TYPE = "DEFINED_BY_TERM_TYPE"  # Field -> TermType


# 2. 定义Term节点
@dataclass
class TermNode:
    id: str
    name: str
    properties: Properties


# 3. 添加Term并关联多个TermType
def add_term_with_types(self, term: TermNode, type_relations: List[Tuple[TermTypeNode, str]]):
    """
    type_relations: List of (TermType, relation_type)
        relation_type: "instance" | "member" | "entry" | "document"
    """
    # 添加Term节点
    term_node_id = self.add_term(term)

    # 添加与各个TermType的关系
    for term_type, rel_type in type_relations:
        self._add_term_type_relation(term_node_id, term_type, rel_type)

    return term_node_id


# 4. 示例：创建王小明并关联多个类型
wang_xiaoming = TermNode(
    id="term_wangxiaoming",
    name="王小明",
    properties=Properties({
        "pinyin": "wangxiaoming",
        "aliases": ["小明", "王工"]
    })
)

# 定义关系
relations = [
    (term_type_employee, "instance"),      # 王小明是员工（本体）
    (term_type_emp_name, "member"),        # 王小明是员工名称（列表）
    (term_type_manager, "instance"),       # 王小明是部门经理（本体）
]

# 添加到图
graph.add_term_with_types(wang_xiaoming, relations)
```

---

## 实现步骤建议

**Phase 1: 基础术语节点**
1. 在 my_graph.py 中添加 TermNode 节点类型
2. 添加语义化的边类型（IS_INSTANCE_OF、IS_MEMBER_OF 等）
3. 添加对应的 add_term()、add_term_with_types() 方法

**Phase 2: 术语-字段关联**
1. 支持 FieldNode 通过 DEFINED_BY_TERM_TYPE 边关联到 TermType
2. 支持从场景JSON中的 termMeta 自动创建术语关系
3. 添加查询方法：get_field_term_type()、get_term_type_fields()

**Phase 3: 数据导入工具**
1. 创建术语数据导入器（从JSON/数据库）
2. 扩展场景转换器支持术语关联
3. 支持增量更新

---

## 总结

| 方面 | 说明 |
|------|------|
| **核心设计** | 只创建一个Term节点，用不同边连接多个TermType |
| **优势** | 避免数据重复，语义清晰，查询灵活，支持多重身份 |
| **边类型** | 语义化命名（IS_INSTANCE_OF、IS_MEMBER_OF等）区分不同关系 |
| **注意事项** | 同名Term需唯一ID区分；边类型需与TermType.type匹配校验 |

---

*文档基于 [统一Term节点设计](./unified-term-design.md) 方案更新*
