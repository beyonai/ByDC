# G13 term_context语义约束

## 1. 目标
按semantic_type(action/object/view/relation)约束工具选择与补参。

## 2. 范围
execution策略层+默认tool_hook插件。

## 3. 依赖
G11,G12

## 4. 并行性
可并行

## 5. 验收标准
1) 四类semantic_type均有策略分支；2) 错配工具显著下降；3) 回归样例通过。

## 6. 实施备注
1. 变更必须包含对应单元测试或回归测试。
2. 若涉及中断/恢复，必须带 checkpoint 相关字段验证。
3. 提交信息建议：refactor(g13): ...。


