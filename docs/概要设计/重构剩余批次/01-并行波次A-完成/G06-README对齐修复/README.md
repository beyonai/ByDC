# G06 README对齐修复

## 1. 目标
对外README与当前5节点实现一致，移除loop主图叙述。

## 2. 范围
packages/datacloud-analysis/README.md、examples/e_commerce_demo/backend/README.md

## 3. 依赖
无

## 4. 并行性
可并行

## 5. 验收标准
1) 文档图谱为knowledge_enhance->planning->execution->end；2) 无旧节点主链描述；3) 启动/调试步骤可复现。

## 6. 实施备注
1. 变更必须包含对应单元测试或回归测试。
2. 若涉及中断/恢复，必须带 checkpoint 相关字段验证。
3. 提交信息建议：refactor(g06): ...。


