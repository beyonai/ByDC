# 列出数据源

```
GET /api/v1/ontologyBases/{baseId}/datasources
```

列出本体库下的数据源列表。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `baseId` | string | 本体库 API 名称。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "db": [
      {
        "dbId": "wukong_crm_demo",
        "dbCode": "wukong_crm_demo",
        "dbType": "opengauss",
        "dbParams": {
          "jdbc_url": "jdbc:opengauss://...",
          "user": "gaussdb",
          "password": "***",
          "pool_min": 5,
          "pool_max": 20
        }
      }
    ],
    "doc": [
      {
        "docId": "19",
        "docPath": "/会议纪要"
      }
    ],
    "api": []
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | object | Yes | 数据源分类列表。失败时为 `null`。 |
| `data.db` | array | No | 数据库数据源。 |
| `data.doc` | array | No | 文档数据源。 |
| `data.api` | array | No | API 数据源。 |

> `data` 字段定义见 [Dbsource](../../ontology-protocol/models/Dbsource.md)

---

## Example

#### Request

```bash
curl -X GET \
  "https://$HOSTNAME/api/v1/ontologyBases/crm_demo/datasources"
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "db": [
      {
        "dbId": "wukong_crm_demo",
        "dbCode": "wukong_crm_demo",
        "dbType": "opengauss",
        "dbParams": {
          "jdbc_url": "jdbc:opengauss://...",
          "user": "gaussdb",
          "password": "***",
          "pool_min": 5,
          "pool_max": 20
        }
      }
    ],
    "doc": [],
    "api": []
  }
}
```
