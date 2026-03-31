# G09 规划契约与回归测试

## 1. 目标
补齐规划节点契约测试（term_context/required_capabilities/blocked_capabilities）。

## 2. 范围
tests/dca/unit/test_planning_node.py及新增fixture。

## 3. 依赖
G07,G08

## 4. 并行性
可并行

## 5. 验收标准
1) 关键契约全覆盖；2) 历史回归case通过；3) 测试可稳定并行执行。

## 6. 实施备注
1. 变更必须包含对应单元测试或回归测试。
2. 若涉及中断/恢复，必须带 checkpoint 相关字段验证。
3. 提交信息建议：refactor(g09): ...。


