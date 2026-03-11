# POC 1 Results: deepagents 基础集成验证

**执行时间**: 2026-03-10 10:38 CST
**测试文件**: `/home/luoyanzhuo/project/whale_datacloud-worktrees/openclaw-gateway-implementation/poc_tests/test_poc1_basic_integration.py`

## 环境配置
- **模型**: 阿里云百炼 Qwen (qwen3.5-plus)
- **API端点**: `https://lab.iwhalecloud.com/gpt-proxy/v1`
- **Python环境**: 工作树 venv (`poc_tests/.venv/bin/python`)

## 测试结果

### 验证点 1: Agent 创建成功
```
✓ Agent created: <class 'langgraph.graph.state.CompiledStateGraph'>
```

### 验证点 2: 同步调用 (invoke) 成功
```
✓ Result: {'messages': [HumanMessage(content='Hello, what is 2+2?', additional_kwargs={}, response_metadata={}, id='9fe41259-c804-4d8a-a8b7-3226208925a9'), AIMessage(content='2+2 = 4', additional_kwargs={'refusal': None}, response_metadata={'token_usage': {'completion_tokens': 6, 'prompt_tokens': 5845, 'total_tokens': 5851, 'completion_tokens_details': {'accepted_prediction_tokens': None, 'audio_tokens': None, 'reasoning_tokens': None, 'rejected_prediction_tokens': None, 'text_tokens': 6}, 'prompt_tokens_details': {'audio_tokens': None, 'cached_tokens': None, 'text_tokens': 5845}}, 'model_provider': 'openai', 'model_name': 'qwen3.5-plus', 'system_fingerprint': None, 'id': 'chatcmpl-ebaee751-a387-9738-bb91-c9ac9e381ed9', 'finish_reason': 'stop', 'logprobs': None}, id='lc_run--019cd59b-77b0-7853-9d4e-00a1d225a1a1-0', tool_calls=[], invalid_tool_calls=[], usage_metadata={'input_tokens': 5845, 'output_tokens': 6, 'total_tokens': 5851, 'input_token_details': {}, 'output_token_details': {}})]}
```

### 验证点 3: 异步调用 (ainvoke) 成功
```
✓ Async result: {'messages': [HumanMessage(content='Hello async!', additional_kwargs={}, response_metadata={}, id='cd771408-69df-4d9d-ac12-382a50fe0c47'), AIMessage(content='Hello! How can I help you today?', additional_kwargs={'refusal': None}, response_metadata={'token_usage': {'completion_tokens': 9, 'prompt_tokens': 5839, 'total_tokens': 5848, 'completion_tokens_details': {'accepted_prediction_tokens': None, 'audio_tokens': None, 'reasoning_tokens': None, 'rejected_prediction_tokens': None, 'text_tokens': 9}, 'prompt_tokens_details': {'audio_tokens': None, 'cached_tokens': None, 'text_tokens': 5839}}, 'model_provider': 'openai', 'model_name': 'qwen3.5-plus', 'system_fingerprint': None, 'id': 'chatcmpl-a6c01404-abba-9e77-9d0a-eb7d906161f4', 'finish_reason': 'stop', 'logprobs': None}, id='lc_run--019cd59b-7f42-7d20-992f-41014dca4d2a-0', tool_calls=[], invalid_tool_calls=[], usage_metadata={'input_tokens': 5839, 'output_tokens': 9, 'total_tokens': 5848, 'input_token_details': {}, 'output_token_details': {}})]}
```

## 结论
✅ **POC 1 验证通过** - deepagents 基础集成验证成功

所有三个验证点均通过：
1. ✅ `create_deep_agent` 可以正常创建和运行
2. ✅ 同步调用 (invoke) 返回正确结果
3. ✅ 异步调用 (ainvoke) 返回正确结果

**注意**: 模型响应正常，token 使用量显示正常，API 连接成功。