# mock_env 目录硬切重构设计

**目标**

将 `mock_env` 中分散的资源目录重构为统一、可运行、可扩展的结构，并完成代码路径同步，确保应用启动时可按顺序完成库表、数据、知识初始化并正常提供 API。

## 背景与现状

- 当前资源主要分布在 `mock-resource/` 与 `data/term_example/` 两处，入口不统一。
- 脚本与部分文档硬编码了 `mock-resource` 路径。
- `src/sales_analysis_demo/` 已具备 API 启动能力，但资源层未形成单一规范目录。

## 方案选择

采用 **方案2（硬切）**：

1. 直接迁移目录，不保留旧路径兼容代码。
2. 全量同步脚本、文档、引用路径。
3. 一次性完成并验证可运行性。

## 目标目录结构

```text
mock_env/
├── docs/
│   ├── crm_demo/
│   └── plans/
├── db/
│   └── crm_demo/sql/DDL.sql
├── resource/
│   ├── data/
│   │   └── crm_demo/
│   │       ├── common/
│   │       ├── modules/
│   │       └── unstructured/   # 可选
│   ├── knowledge/
│   │   └── crm_demo/
│   │       ├── ontology/
│   │       └── terminology/
│   └── files/
├── src/
├── scripts/
└── tests/
```

## 迁移映射

- `mock-resource/data/crm_demo/**` -> `resource/data/crm_demo/**`
- `mock-resource/ontology/crm_demo/**` -> `resource/knowledge/crm_demo/ontology/**`
- `data/term_example/**` -> `resource/knowledge/crm_demo/terminology/**`
- `mock-resource/files/**` -> `resource/files/**`

## 代码改造范围

- 脚本目录 `scripts/*.py` 中所有资源路径更新到 `resource/**`
- 文档中出现的 `mock-resource` 路径替换为 `resource`
- 若服务代码有资源硬编码路径，同步替换为 `resource/**`

## 验证标准

1. 仓库不存在对旧目录 `mock-resource`、`data/term_example` 的有效运行时引用。
2. 资源文件在新目录可完整找到（文件数一致）。
3. Python 代码可通过基本语法与导入检查（至少 `python -m compileall src scripts`）。
4. 关键文档中的示例路径与新目录一致。

## 风险与回避

- 风险：路径硬编码遗漏导致脚本失败。
  - 回避：迁移后全局搜索旧路径并逐个修复。
- 风险：遗漏非 Python 文档引用。
  - 回避：对 `md/json` 也做路径扫描替换。
