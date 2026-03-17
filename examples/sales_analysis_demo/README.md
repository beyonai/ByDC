# Sales Analysis Demo

销售分析 Demo 由三层组成：

1. `mock_env`：源系统模拟层（库表、业务数据、知识、本体、源 API）。
2. `backend` + `frontend`：Agent 应用层（后端与前端），运行时依赖 `packages` SDK。
3. `eval_test`：评测层（准确性、性能、回归对比）。

## 目录说明

```text
sales_analysis_demo/
├── mock_env/           # 源系统模拟
├── backend/            # Agent 后端
├── frontend/           # Agent 前端
├── eval_test/          # 评测（cases/configs/reports/baselines）
├── contracts/          # 共享契约（API/Eval 约束）
├── docker-compose.yml
└── start_demo.sh
```

## 各层职责

- `mock_env`
  - 对外提供演示数据与模拟 API。
  - 负责数据库 DDL、数据初始化、知识资源准备。
- `backend`
  - 负责 Agent 编排、工具调用、数据服务接口。
  - 引用仓库 `packages` 下 SDK 作为能力底座。
- `frontend`
  - 提供对话与配置界面，调用 `backend` 能力。
- `eval_test`
  - 维护评测用例、运行配置、评测报告与基线结果。
- `contracts`
  - 维护跨层共享的 API/评测约束，降低前后端和评测脚本的耦合风险。
