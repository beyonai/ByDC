# 创建/更新数据源

```
POST /api/v1/ontologyBases/{baseId}/datasources
```

按 `dbId` 创建或全量替换数据源配置。仅 LOCAL 可用。

---

## Request Body

```json
{
  "dbId": "wukong_crm_demo",
  "dbCode": "wukong_crm_demo",
  "dbType": "opengauss",
  "dbParams": {
    "jdbc_url": "jdbc:opengauss://10.10.168.203:5432/postgres",
    "user": "gaussdb",
    "password": "Admin@123",
    "pool_min": 5,
    "pool_max": 20
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `dbId` | string | Yes | 数据源 ID。创建或更新的依据。 |
| `dbCode` | string | Yes | 数据源编码。 |
| `dbType` | string | Yes | 数据库类型：`opengauss` / `mysql` / `sqlite` 等。 |
| `dbParams` | object | Yes | 连接参数。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "创建成功",
  "data": {
    "dbId": "wukong_crm_demo"
  }
}
```

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `403` | 403 | `Remote ontology base is read-only` | REMOTE 写操作。 |
