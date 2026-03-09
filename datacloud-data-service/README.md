# datacloud-data-service

数据服务（Data Service）是 dataCloud 2.0 的核心服务之一，负责执行数据查询、返回数据结果，并提供行列权限控制。

## 核心定位

**安全执行**：受控取数与脱敏，确保数据访问的安全性。

## 核心功能

### 1. NL2Data 查询执行

- **自然语言转SQL**：将自然语言查询转换为SQL语句
- **DSL查询**：支持自定义DSL（Domain Specific Language）查询
- **多数据源支持**：支持MySQL、ClickHouse、Doris等异构数据库

### 2. 数据返回

- **小数据直接返回**：查询结果较小时直接返回JSON
- **大数据文件返回**：查询结果较大时返回文件下载链接
- **数据格式转换**：支持多种数据格式（JSON、CSV、Excel等）

### 3. 权限控制

- **行级权限**：基于用户角色和业务规则过滤数据行
- **列级权限**：基于用户权限隐藏敏感列
- **数据脱敏**：对敏感数据进行脱敏处理

### 4. 查询优化

- **查询缓存**：缓存常用查询结果
- **查询限流**：防止恶意查询和资源滥用
- **查询监控**：监控查询性能和资源使用

## 技术架构

### 核心技术

- **查询引擎**：UniQuery（虚拟计算网关）
- **数据连接**：异构数据库适配器
- **权限引擎**：基于规则的权限控制

### 技术栈

```python
# 查询引擎
- UniQuery: 虚拟计算网关
- DuckDB: 内存分析数据库
- Trino: 分布式查询引擎

# 数据连接
- SQLAlchemy: 关系型数据库ORM
- 自定义连接器: 异构数据源适配

# 权限控制
- 自定义权限引擎: 基于规则的权限控制
```

## 快速开始

```bash
# 安装依赖
pip install -e ".[all]"

# 配置环境变量（可选）
cp .env.example .env
# 编辑 .env 文件，配置 LLM、本体路径等；数据源来自本体对象上的 source_config

# 启动服务
uvicorn datacloud_data_service.api.routes:create_app --factory --host 0.0.0.0 --port 8080
```

## API 接口

### 执行查询

```http
POST /api/v1/query/execute
Content-Type: application/json

{
  "query_plan": {
    "steps": [
      {
        "type": "sql",
        "sql": "SELECT * FROM sales_person WHERE name = '王小明'"
      }
    ]
  },
  "context": {
    "user_id": "user-001",
    "session_id": "session-001"
  }
}
```

### 获取数据

```http
GET /api/v1/data/{query_id}
Authorization: Bearer {token}
```

## 项目结构

```
datacloud-data-service/
├── README.md              # 本文件
├── requirements.txt       # Python依赖
├── .env.example          # 环境变量示例
├── src/
│   ├── query/            # 查询执行逻辑
│   ├── connector/        # 数据连接器
│   ├── permission/       # 权限控制
│   └── api/              # API接口
├── tests/                # 测试文件
└── docs/                 # 文档
```

## 开发脚本

### 导出场景完整 JSON

根据场景定义和 objects_registry 生成自包含的完整 JSON：

```bash
python scripts/export_scene_json.py \
  --scene resources/ontology/crm_demo/scene_01_data_analysis.json \
  --registry resources/ontology/crm_demo/objects_registry.json \
  --output resources/ontology/crm_demo/scene_01_data_analysis_full.json
```

## 相关文档

- [数据服务详细设计](../../story/V202602/feature_datacloud2.0设计/本体服务_模块设计/数据服务详细设计.md)
- [dataCloud 2.0 概要设计](../../story/V202602/feature_datacloud2.0设计/dataCloud2.0概要设计.md)

## 许可证

MIT License

