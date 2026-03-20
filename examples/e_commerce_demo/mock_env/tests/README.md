# mock_env tests 目录说明

本目录按测试类型分层，和初始化流程保持一致。

## 目录结构

- `fixtures/`：公共夹具与工具函数
- `type1_db_schema/`：DDL 建表相关测试（e_commerce_demo schema，3 张宽表）
- `type2_data_load/`：结构化数据加载前后校验（3 张 CSV → DB）
- `type4_knowledge_ingest/`：知识资源与知识入库流程测试（亦庄术语库 import_package）

## 运行建议

仅静态校验（默认，无需数据库）：

```powershell
pytest tests/type1_db_schema tests/type2_data_load tests/type4_knowledge_ingest -q
```

启用集成测试（需要真实数据库）：

```powershell
$env:DATACLOUD_ENABLE_INTEGRATION_TESTS="1"
$env:DATACLOUD_TEST_DATABASE_DSN="postgresql+psycopg2://user:pass@host:5432/dbname"
pytest tests -q
```

## 初始化顺序

1. `type1_db_schema` — 建表（CREATE TABLE e_commerce_demo.*）
2. `type2_data_load` — 加载 CSV 数据
3. `type4_knowledge_ingest` — 导入亦庄术语库 import_package
