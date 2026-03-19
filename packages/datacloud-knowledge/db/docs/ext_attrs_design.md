# 术语与关系的扩展属性字段设计（ext_attrs）

## 目标

为 **术语（term）** 与 **术语关系（term_relation）** 增加统一的「自定义扩展属性」字段，用于业务或产品侧在不改表结构的前提下添加各类扩展键值，便于后续功能演进。

## 与现有字段的区分

| 表 / 字段 | 用途 | 约定 |
|-----------|------|------|
| **term.term_tags** | 标签、别名及「标签维度 → {type, value}」结构化属性 | key 多为术语ID/维度ID，value 为 `{type, value}`（TERM_REF/TEXT/NUMBER 等），用于检索与展示 |
| **term.ext_attrs**（新增） | 任意业务/产品扩展属性 | 无固定 schema，纯键值对，与 term_tags 语义分离 |
| **term_relation.ext_attrs**（新增） | 关系的任意扩展属性 | 同上 |

- **term_tags**：保留现有语义（别名、标签维度、类型化 value），不做变更。
- **ext_attrs**：与 term_tags 分离，专用于「未在模型中显式列出的扩展属性」，避免与标签体系混淆。

## 方案：新增 JSONB 列 `ext_attrs`

- **类型**：`JSONB NOT NULL DEFAULT '{}'::jsonb`
- **位置**：`whale_datacloud.term.ext_attrs`、`whale_datacloud.term_relation.ext_attrs`
- **索引**：两表均对 `ext_attrs` 建 GIN 索引，支持 `ext_attrs ? 'key'`、`ext_attrs @> '{"k": "v"}'` 等查询。

### 取值约定（建议）

- key：建议使用有命名空间的字符串（如 `product_xxx`、`biz_xxx`），避免与未来标准字段冲突。
- value：任意合法 JSON 类型（字符串、数值、布尔、数组、对象均可）。

### 本体层级冗余约定（ext_attrs.onto）

为提升「视图 → 对象 → 动作 → 函数」多跳查询性能，在 **term.ext_attrs** 中预留 **`onto`** 命名空间，用于冗余直接下级的术语 ID（数据由 term_relation 同步得到，不手写）。详见：[ext_attrs_ontology_hierarchy.md](./ext_attrs_ontology_hierarchy.md)。

### 已实施内容

- DDL：在 `04_term.sql`、`05_term_relation.sql` 的建表语句中增加 `ext_attrs` 列；存量库通过 `98_add_ext_attrs.sql` 迁移脚本追加列。
- ER：`db/er/whale_datacloud.mmd` 中 Term、TermRelation 增加 `ext_attrs`。
- 索引：`99_indexes_constraints.sql` 中为两表 `ext_attrs` 增加 GIN 索引。
