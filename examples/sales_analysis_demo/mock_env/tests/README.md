# mock_env tests 目录说明

本目录按测试类型分层，和初始化流程保持一致。

## 目录结构

- `fixtures/`: 公共夹具与工具函数
- `type1_db_schema/`: DDL 建表相关测试
- `type2_data_load/`: 结构化数据加载前后校验
- `type3_api_service/`: `src/sales_analysis_demo` API 可用性测试
- `type4_knowledge_ingest/`: 知识资源与知识入库流程测试
- `e2e/`: 端到端冒烟（DDL -> data -> knowledge -> api）

## 运行建议

- 仅静态校验（默认）:
  - `pytest tests/type1_db_schema tests/type2_data_load tests/type4_knowledge_ingest -q`
- 启用集成测试（需要测试数据库）:
  - PowerShell:
    - `$env:DATACLOUD_ENABLE_INTEGRATION_TESTS="1"`
    - `$env:DATACLOUD_TEST_DATABASE_DSN="postgresql+psycopg://user:pass@host:5432/dbname"`
    - `pytest tests -q`
