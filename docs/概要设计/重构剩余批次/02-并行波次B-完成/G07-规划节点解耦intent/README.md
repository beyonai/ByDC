# G07 规划节点解耦intent

## 1. 目标
planning不再直接调用intent_node，改为消费B节点产物与独立规划器。

## 2. 范围
planning.py拆分为planner facade；新增契约类型。

## 3. 依赖
G02,G03

## 4. 并行性
可并行（与G08低耦合）

## 5. 验收标准
1) planning.py无intent import；2) 输出todos契约不变；3) 旧路径有兼容开关。

## 6. 实施备注
1. 变更必须包含对应单元测试或回归测试。
2. 若涉及中断/恢复，必须带 checkpoint 相关字段验证。
3. 提交信息建议：refactor(g07): ...。


