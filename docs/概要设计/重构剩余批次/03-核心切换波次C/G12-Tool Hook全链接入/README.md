# G12 Tool Hook全链接入

## 1. 目标
function-call命中工具时统一走before/after hook链。

## 2. 范围
sandbox_executor.py与tool_hook_plugins manager整合。

## 3. 依赖
G11

## 4. 并行性
可并行（与G13）

## 5. 验收标准
1) before patch/interrupt/fail生效；2) after recover/fail生效；3) strict模式行为可测。

## 6. 实施备注
1. 变更必须包含对应单元测试或回归测试。
2. 若涉及中断/恢复，必须带 checkpoint 相关字段验证。
3. 提交信息建议：refactor(g12): ...。


