# 重构剩余批次最终版

## 概述

G01~G17 已完成。本目录为重构收口阶段的最终任务清单，共 3 个波次。

## 当前残留问题（截至 2026-03-31）

### 旧节点残留
| 问题 | 位置 | 说明 |
|------|------|------|
| `clarification_node` 仍被引用 | `execution.py:17,849` | 处理 `ambiguous_terms` 中断路径 |
| `intent_node` 仍被引用 | `planner_facade.py:65` | `intent_compat` 兼容层 |
| 6 个旧节点文件未删除 | `orchestration/` | `intent/dag/clarification/loop/agent_delegate/direct_tool` |
| `orchestration/` 目录平铺 | 17 个文件 | 应按节点分子目录 |

### 设计文档未落地项（§ 引用重构方案章节）
| 设计章节 | 未落地内容 | 对应任务 |
|---------|-----------|---------|
| §4.6 | `ToolRuntime.invoke_with_callbacks` 统一入口，当前是 `execute_next_task` + 分散 hook | G22 |
| §4.5 | `allowlist_tags / blocklist_tags / risk_level` 在 skill 能力模型中未实现 | G23 |
| §3.4.2 | ReAct 每轮读 `todo.md` 摘要作为上下文，当前只写不读 | G24 |
| §3.4.5 | `relation` 语义的多步编排（先定位主语/宾语再执行），当前只做工具优先级调整 | G25 |

## 波次顺序

| 波次 | 任务 | 可并行 | 说明 |
|------|------|--------|------|
| 01-收口前置波次 | G18、G19、G21 | G18 先行，G19/G21 可并行 | 清除旧节点、重组目录 |
| 02-能力补齐波次 | G22、G23、G24、G25 | 全部可并行 | 补齐设计文档未落地项 |
| 03-全链路回归波次 | G20 | 不可并行 | 依赖前两波次全部完成 |

## 执行原则

1. 每个波次完成后 CI 必须绿色，再进入下一波次。
2. 旧文件删除前必须确认无任何引用（静态检查 + grep）。
3. 目录重组必须同步更新所有 import 路径。
4. 能力补齐任务每项必须有对应单元测试。
