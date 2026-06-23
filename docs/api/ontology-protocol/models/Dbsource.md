# Dbsource

数据源，包含数据库、文档、API 三类数据源的连接配置。

## Properties

| Name | Type | Required | Description |
|---|---|---|---|
| `db` | object[] | No | 数据库连接列表。 |
| `db[].dbId` | string | Yes | 数据库标识。 |
| `db[].dbCode` | string | Yes | 数据库编码。 |
| `db[].dbType` | string | Yes | 数据库类型：`mysql` / `opengauss` / `sqlite`。 |
| `db[].dbParams` | object | No | 连接参数（url/jdbc_url, user, password, pool_min, pool_max 等）。 |
| `doc` | object[] | No | 文档源列表。 |
| `doc[].docId` | string | Yes | 文档标识。 |
| `doc[].docPath` | string | Yes | 文档路径。 |
| `api` | object[] | No | API 源列表。 |
| `api[].apiId` | string | Yes | API 标识。 |
| `api[].url` | string | Yes | API 地址。 |
| `api[].method` | string | No | 请求方法。 |
| `api[].header` | object | No | 请求头。 |
| `api[].body` | string | No | 请求体模板。 |
