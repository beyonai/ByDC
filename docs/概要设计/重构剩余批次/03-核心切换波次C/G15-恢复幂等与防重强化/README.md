# G15 恢复幂等与防重强化

## 1. 目标
完善invocation_id去重与重复resume幂等返回。

## 2. 范围
execution/sandbox_executor/worker恢复链路。

## 3. 依赖
G12,G14

## 4. 并行性
可并行

## 5. 验收标准
1) 重复resume无重复副作用；2) invocation_dedup稳定；3) 有并发恢复测试。

## 6. 实施备注
1. 变更必须包含对应单元测试或回归测试。
2. 若涉及中断/恢复，必须带 checkpoint 相关字段验证。
3. 提交信息建议：refactor(g15): ...。


