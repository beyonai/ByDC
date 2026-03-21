# 自然语言查知识测试 (type5_nl_knowledge_query)

本目录包含电商产业大脑场景的自然语言查询测试，基于场景测试结果文档中的4大类测试用例。

## 测试分类

### 1. 经济活力类 (TestEconomicVitality)
- `test_query_lowest_output_per_mu_enterprises`: 查询亩产效益最低的10家企业
- `test_query_enterprise_industry_info`: 查询企业所属行业
- `test_query_enterprise_tax_ranking`: 查询企业纳税额及排名

### 2. 偷税漏税类 (TestTaxRisk)
- `test_query_risk_enterprise_count`: 查询整个区域有风险的企业数量
- `test_query_high_risk_enterprises`: 查询高风险等级企业
- `test_query_enterprise_risk_evidence`: 查询企业风险证据

### 3. 产业链对比类 (TestIndustryChainComparison)
- `test_query_region_industry_comparison`: 对比亦庄和闵行的产业链发展能力
- `test_query_minhang_advantage_industries`: 查询闵行优势产业
- `test_query_yizhuang_weakness`: 查询亦庄短板

### 4. 闲置资产交易类 (TestIdleAssetTransaction)
- `test_query_vacant_assets`: 查询空置工业用地和办公楼宇
- `test_query_asset_transaction_value`: 查询特定地块交易价值
- `test_query_asset_transaction_policy`: 查询推动闲置资产交易的政策建议

## 运行测试

### 运行所有测试
```bash
cd examples/e_commerce_demo/mock_env
pytest tests/type5_nl_knowledge_query -v
```

### 运行特定类别测试
```bash
# 经济活力类
pytest tests/type5_nl_knowledge_query/test_nl_query.py::TestEconomicVitality -v

# 偷税漏税类
pytest tests/type5_nl_knowledge_query/test_nl_query.py::TestTaxRisk -v

# 产业链对比类
pytest tests/type5_nl_knowledge_query/test_nl_query.py::TestIndustryChainComparison -v

# 闲置资产交易类
pytest tests/type5_nl_knowledge_query/test_nl_query.py::TestIdleAssetTransaction -v
```

### 直接运行（不通过 pytest）
```bash
# 运行所有测试
cd examples/e_commerce_demo/mock_env/tests/type5_nl_knowledge_query
python test_nl_query.py all

# 运行特定类别
python test_nl_query.py economic  # 经济活力类
python test_nl_query.py tax       # 偷税漏税类
python test_nl_query.py industry  # 产业链对比类
python test_nl_query.py asset     # 闲置资产交易类
```

## 环境配置

测试需要配置数据库连接环境变量：

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=username
export DB_PASSWORD=password
export DB_NAME=datacloud

# 启用集成测试
export DATACLOUD_ENABLE_INTEGRATION_TESTS=1
```

或在 `.env.example` 文件中配置。

## 前置条件

运行本测试前需要确保：

1. **数据已加载**: 三张DWS宽表已有数据
   - `e_commerce_demo.dws_enterprise_wide`
   - `e_commerce_demo.dws_grid_wide`
   - `e_commerce_demo.dws_industry_wide`

2. **知识已导入**: 术语库已导入到知识图谱
   - 运行 `type4_knowledge_ingest` 测试完成知识构建

3. **数据库可连接**: PostgreSQL/OpenGauss 数据库可访问

## 参考文档

- 场景测试结果: `mock_env/docs/场景测试结果0320.txt`
- 本体定义: `mock_env/resource/knowledge/import_package/ontology/`
- 术语定义: `mock_env/resource/knowledge/import_package/terms/ontology_terms.jsonl`
