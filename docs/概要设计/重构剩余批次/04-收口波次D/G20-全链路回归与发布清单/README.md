# G20 全链路回归与发布清单

## 1. 目标
完成重构收官验证与上线清单，形成可执行、可追溯的发布闭环。

## 2. 交付物
1. 回归脚本：
   - `scripts/g20/run_regression.ps1`
   - `python -m datacloud_analysis.release.g20_regression`
2. 回归结果输出：
   - `回归报告.md`
   - `回归结果.json`
3. 发布文档：
   - `风险清单.md`
   - `回滚预案.md`
   - `发布清单.md`
   - `验收报告模板.md`

## 3. 使用方式

### 3.1 快速执行（Windows）
```powershell
pwsh scripts/g20/run_regression.ps1
```

### 3.2 Dry-Run（只生成执行计划）
```powershell
pwsh scripts/g20/run_regression.ps1 -DryRun
```

### 3.3 直接 Python 执行
```bash
uv run python -m datacloud_analysis.release.g20_regression
```

## 4. 回归范围（默认矩阵）
1. C1：闲聊短路（不进图）。
2. C2：自动确权后可规划与执行。
3. C3：中断恢复链路（含 checkpoint 语义）。
4. C4：子 agent 委托路径（不被术语澄清阻断）。
5. P1：图主链结构稳定性。
6. P2：Tool Hook 回调链稳定性。
7. P3：执行层关键单测集合时延基线（可选项）。

## 5. 验收门禁
1. 必测项（C1~C4、P1、P2）全部通过。
2. 可选项（P3）若失败，需在发布记录中给出风险说明和后续修复计划。
3. 生成并归档本目录下 `回归报告.md` 与 `回归结果.json`。

## 6. 依赖与顺序
1. 依赖：G01..G19 已完成并入目标分支。
2. 执行顺序：回归脚本 -> 风险评审 -> 发布清单签核 -> 发布 -> 回滚预案演练记录。

## 7. 实施备注
1. 若涉及中断/恢复场景，必须验证 `checkpoint_id/checkpoint_ns/todo_active_id/react_step_id` 字段链路。
2. 提交信息建议：`refactor(g20): ...`

