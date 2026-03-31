# G20 清理旧图节点及代码

## 1. 任务定义

### 1.1 背景

进入 G20 收口阶段后，主链路能力已基本切到 `knowledge_enhance -> planning -> execution -> end`，但代码与文档层面仍存在几类残留，导致《重构方案》与当前实现之间还有收口差距：

1. `G23 skill` 能力模型标签未完全收口，`allowlist_tags / blocklist_tags / risk_level` 尚未完整进入执行链路。
2. 旧节点语义仍有兼容残留，如 `clarification`、`intent_compat`、`dag_*`、`loop_node` 等命名或引用仍散落在代码中。
3. `G21 orchestration` 目录重组虽已启动，但仍需彻底收口，避免新旧目录结构混用。
4. 旧测试、README、流程描述与静态防回归检查仍需统一整理，保证旧节点不会被重新引回主链。

### 1.2 当前状态（截至 2026-03-31）

经检查，当前仍可见的典型残留包括：

| 类别 | 位置 | 残留表现 |
| ------ | ------ | ---------- |
| skill 标签模型 | `execution/node.py` | 仍有 `risk_level="medium"` 的硬编码 |
| clarification 残留 | `execution/node.py`、`orchestration/clarification.py` | 澄清中断相关兼容逻辑仍存在 |
| 旧命名残留 | `planning/decomposer.py`、`sandbox_executor.py`、`end/node.py` | 仍有 `dag_*`、`loop_node` 等旧流程命名 |
| delegate 兼容语义 | `planning/node.py`、`release/g20_regression.py` | `agent_delegate` 仍作为 query_mode/测试场景名存在 |
| 测试与静态检查 | `tests/dca/unit/` | 已有 `test_no_legacy_node_imports.py`，但仍需与 README/图结构/目录收口一起复核 |

### 1.3 目标

1. 完成 `G23 skill` 能力模型标签收口：补齐 `allowlist_tags`、`blocklist_tags`、`risk_level`，并接入执行过滤链路。
2. 清理所有旧节点兼容残留，确认主链不再依赖 `clarification`、`intent_compat`、`dag`、`loop` 等旧节点语义。
3. 完成 `G21 orchestration` 目录重组收口，统一到按节点分组的目录结构，并修正 import、注释、文档中的旧路径表述。
4. 补齐旧测试与文档清理，完善静态防回归检查，确保旧节点不会被重新引入。

---

## 2. 详细任务

### 2.1 收口 G23：skill 能力模型标签

对照 `docs/概要设计/重构剩余批次最终版/02-能力补齐波次/G23-skill能力模型标签/README.md` 收口以下内容：

- 在 skill 元数据模型中补齐 `allowlist_tags`、`blocklist_tags`、`risk_level`
- 在 skill 选择/执行路径中接入标签过滤
- 将 `risk_level` 从 skill 元数据传递到审计字段，移除执行层硬编码 `"medium"`

**当前问题：**

```python
detail={
    "plugin_id": "react_replanning",
    "risk_level": "medium",
    ...
}
```

**目标：**

- skill 定义自身携带 `risk_level`
- 执行链路按 `allowlist_tags / blocklist_tags` 过滤 skill
- 审计链路记录真实 skill 风险级别，而不是兜底硬编码

### 2.2 清理旧节点与兼容命名残留

基于 G18 的“删除旧节点文件”目标，在 G20 做最终残留清点与收口，重点包括：

| 残留项 | 当前位置 | 收口要求 |
| -------- | ---------- | ---------- |
| `clarification` 兼容逻辑 | `execution/node.py`、`orchestration/clarification.py` | 确认只保留执行节点内部所需运行时能力，不再保留旧节点入口语义 |
| `intent_compat` / `intent_node` 兼容思路 | planning 相关上下文解析逻辑 | 删除兼容分支和旧来源标记 |
| `dag_*` 命名 | `planning/decomposer.py` | 改为与 planning 节点一致的命名 |
| `loop_node` 注释/说明 | `sandbox_executor.py`、`end/node.py` | 改为 execution/ReAct 当前实现表述 |
| `agent_delegate` / `direct_tool` 旧图节点语义 | planning/execution 回归场景与注释 | 保留业务能力，移除“旧图节点”表述 |

**实现要求：**

- 不再出现对旧节点模块的 import
- 不再保留“这是旧节点兼容层”的实现分支
- 允许保留必要的业务语义，但命名必须回归主链模型

### 2.3 完成 G21 目录重组收口

对照 `docs/概要设计/重构剩余批次最终版/01-收口前置波次/G21-orchestration目录重组/README.md`，确认以下事项彻底收口：

1. 平铺文件全部迁移到 `shared/`、`knowledge_enhance/`、`planning/`、`execution/`、`end/`
2. import 路径全部更新为新目录结构
3. 注释、docstring、README 中的旧路径描述同步修正
4. 顶层公共导出保持稳定，不再混用旧平铺路径

**重点复查项：**

- `graph_builder.py` 是否仅引用新节点子包导出
- `planning/*`、`execution/*`、`end/*` 内部是否仍有旧平铺路径 import
- `__init__.py` 导出是否与新目录结构一致

### 2.4 补齐旧测试与文档清理

在 G19 基础上做最终复核，覆盖以下四类内容：

1. 清理测试中对旧节点、旧路径、旧命名的依赖
2. 清理 README、设计文档、流程图中的旧图流程描述
3. 复核静态防回归测试，确认旧节点不会被重新引入
4. 将 G20 回归检查项与前置波次的验收测试对齐

**重点检查文件：**

- `tests/dca/unit/test_no_legacy_node_imports.py`
- `tests/dca/unit/test_graph_builder_pipeline.py`
- `tests/dca/unit/test_readme_pipeline_alignment.py`
- 与 planning/execution 相关的单测中是否仍引用旧节点语义

**文档目标表述统一为：**

```text
knowledge_enhance -> planning -> execution -> end
```

### 2.5 建议执行顺序

为降低冲突与返工，建议按以下顺序执行：

1. 先完成 `G23 skill` 标签模型收口
2. 再清理旧节点兼容语义与命名残留
3. 然后完成 `G21` 目录重组的最后收口
4. 最后统一清理测试、README、静态防回归检查

---

## 3. 验收标准

| # | 验收项 | 检查方式 |
| --- | -------- | --------- |
| 1 | skill 元数据含 `allowlist_tags / blocklist_tags / risk_level` | 代码审查或静态搜索 |
| 2 | 执行链路不再硬编码 `risk_level="medium"` | 搜索 `risk_level": "medium"` 并确认仅保留合理兜底场景 |
| 3 | 无旧节点模块 import | `test_no_legacy_node_imports.py` 绿色 |
| 4 | 无 `clarification`、`intent_compat`、`dag_*`、`loop_node` 等旧图兼容残留表述 | 代码审查 + 静态搜索 |
| 5 | `orchestration/` 目录结构符合 G21 目标 | 目录审查 |
| 6 | 测试与 README 无旧图流程描述 | `test_readme_pipeline_alignment.py` 绿色 |
| 7 | 图结构仅体现主链节点 | `test_graph_builder_pipeline.py` 绿色 |
| 8 | 全量单测通过 | `pytest packages/datacloud-analysis/tests/` 绿色 |

---

## 4. 依赖

**前置**：G20 回归执行前，应确保 G22、G24、G25 主能力已稳定；本任务与 G23/G21/G19 收口结果强相关。

## 5. 并行性

本任务属于 G20 收口项，建议串行推进，不再与新增功能并行。

## 6. 风险提示

- `clarification`、`agent_delegate` 等词可能同时承载业务语义与旧图节点语义，清理时需区分“删除旧节点表述”和“保留业务能力”。
- `risk_level="medium"` 可能既有真实默认值，也可能是历史硬编码，需区分审计兜底与业务元数据来源。
- 目录重组收口时，若顶层兼容导出尚有外部调用依赖，需先确认迁移策略再彻底删旧路径。
- 测试与 README 清理必须与代码收口同步，否则容易出现“代码已改、文档未改”或“文档已改、测试口径未改”的假收口。

## 7. 提交规范

```text
refactor(g20): clean up legacy graph nodes, naming residue, and orchestration structure
```
