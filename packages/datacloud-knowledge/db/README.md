# 数据库资产（whale_datacloud）

本目录用于管理 `datacloud-knowledge-service` 的数据库资产：

- `er/`：ER 关系图（Mermaid 源文件）
- `ddl/whale_datacloud/`：按顺序执行的 DDL 脚本
- `scripts/`：DDL 应用与校验脚本

## 环境变量

执行脚本或测试前，请先设置以下环境变量：

- `DB_HOST`
- `DB_PORT`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`
- `DB_SCHEMA`（可选，默认 `whale_datacloud`）

## 应用 DDL

```bash
python db/scripts/apply_whale_datacloud.py
```

## 校验表结构

```bash
python db/scripts/verify_whale_datacloud.py
```

## 运行测试

```bash
pytest tests/db/test_schema_apply.py -q
```
