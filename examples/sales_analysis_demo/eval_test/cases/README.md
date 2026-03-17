# Eval Cases

建议按业务场景拆分样例文件，例如：

- `accuracy_sales_query.jsonl`
- `accuracy_knowledge_grounding.jsonl`
- `performance_chat_turns.jsonl`

每条样例至少包含：

- 输入问题
- 期望关键信息或评分规则
- 场景标签（用于分桶统计）
