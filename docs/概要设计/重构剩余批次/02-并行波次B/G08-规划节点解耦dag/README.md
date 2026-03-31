# G08 规划节点解耦dag

## 1. 目标
planning不再依赖dag_node，任务分解逻辑内聚到新规划模块。

## 2. 范围
dag依赖迁移、任务分解prompt与后处理。

## 3. 依赖
G07

## 4. 并行性
可并行（与G09）

## 5. 验收标准
1) planning.py无dag import；2) analysis模式可稳定产出plan/todos；3) 规划失败有回退。

## 6. 实施备注
1. 变更必须包含对应单元测试或回归测试。
2. 若涉及中断/恢复，必须带 checkpoint 相关字段验证。
3. 提交信息建议：refactor(g08): ...。


