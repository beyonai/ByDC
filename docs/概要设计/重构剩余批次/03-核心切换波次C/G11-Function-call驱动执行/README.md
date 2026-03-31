# G11 Function-call驱动执行

## 1. 目标
单todo执行由LLM function-call选择capability，不再仅dispatcher直调。

## 2. 范围
新增react_runtime模块；tool/skill统一选择。

## 3. 依赖
G10

## 4. 并行性
核心主干

## 5. 验收标准
1) 可回放tool_calls轨迹；2) 无可用capability时明确blocked；3) 有单测覆盖。

## 6. 实施备注
1. 变更必须包含对应单元测试或回归测试。
2. 若涉及中断/恢复，必须带 checkpoint 相关字段验证。
3. 提交信息建议：refactor(g11): ...。


