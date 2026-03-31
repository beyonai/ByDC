# G02 知识增强高置信裁剪

## 1. 目标
knowledge_enhance节点只输出高置信term_hints，契约前移到B节点。

## 2. 范围
knowledge_enhance.py与测试；阈值可配置并有默认值。

## 3. 依赖
无

## 4. 并行性
可并行

## 5. 验收标准
1) 低置信术语不进入term_hints；2) knowledge_snippets保留证据原文；3) 覆盖边界值测试。

## 6. 实施备注
1. 变更必须包含对应单元测试或回归测试。
2. 若涉及中断/恢复，必须带 checkpoint 相关字段验证。
3. 提交信息建议：refactor(g02): ...。


