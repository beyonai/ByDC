# 创建对象类型

```
POST /api/v1/ontologyBases/{baseId}/objects
```

创建对象类型。仅 LOCAL 可用，REMOTE ontology base 返回 403。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `baseId` | string | 本体库 API 名称。获取方式见 [listOntologyBases](../OntologyBase/listOntologyBases.md)。 |

---

## Query Parameters

无

---

## Request Body

```
CreateObjectRequest
```

### Schema

```json
{
  "objectCode": "by_customer",
  "objectName": "客户信息表",
  "objectSource": "DB",
  "objectDesc": "CRM 客户主数据对象。",
  "conceptType": "1",
  "sourceConfig": {
    "alias": "wukong_crm_demo",
    "dbType": "OPENGAUSS",
    "jdbc_url": "jdbc:opengauss://...",
    "user": "gaussdb",
    "password": "***"
  },
  "tableName": "by_customer",
  "properties": [
    {
      "propertyCode": "id",
      "propertyName": "主键",
      "dataType": "BIGINT",
      "isRequired": 1,
      "businessKey": 1,
      "sourceColumn": "id",
      "dbId": "wukong_crm_demo"
    }
  ]
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `objectCode` | string | Yes | 对象编码，场景内不可重复。 |
| `objectName` | string | Yes | 对象名称。 |
| `objectSource` | string | Yes | `DB` / `DYNAMIC_TABLE` / `KNOWLEDGE_BASE`。 |
| `objectDesc` | string | No | 对象描述。 |
| `conceptType` | string | No | `1` 业务实体，`2` 活动实体。 |
| `sourceConfig` | object | No | 数据源连接配置。 |
| `tableName` | string | No | 表名。 |
| `properties` | array | No | 属性列表。 |

> `properties` 元素定义见 [Property](../../ontology-protocol/models/Property.md)

---

## Response Body

```
CreateObjectResponse
```

### Schema

```json
{
  "code": 200,
  "success": true,
  "message": "创建成功",
  "data": {
    "objectCode": "by_customer"
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | object | Yes | 创建结果。失败时为 `null`。 |
| `data.objectCode` | string | Yes | 创建的对象编码。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：objectCode 不能为空` | `objectCode` 未传或为空。 |
| `403` | 403 | `Remote ontology base is read-only` | REMOTE ontology base 写操作。 |
| `409` | 409 | `对象类型「{objectCode}」已存在` | `objectCode` 重复。 |
| `500` | 500 | `系统错误：{原因}` | 服务端异常。 |

### Error Example

```json
{
  "code": 403,
  "success": false,
  "message": "Remote ontology base is read-only",
  "data": null
}
```

---

## Example

### 创建数据库对象

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/api/v1/ontologyBases/crm_demo/objects" \
  -d '{
    "objectCode": "by_customer",
    "objectName": "客户信息表",
    "objectSource": "DB",
    "objectDesc": "CRM 客户主数据对象。",
    "conceptType": "1",
    "sourceConfig": {
      "alias": "wukong_crm_demo",
      "dbType": "OPENGAUSS",
      "jdbc_url": "jdbc:opengauss://...",
      "user": "gaussdb",
      "password": "***"
    },
    "tableName": "by_customer",
    "properties": [
      {
        "propertyCode": "id",
        "propertyName": "主键",
        "dataType": "BIGINT",
        "isRequired": 1,
        "businessKey": 1,
        "sourceColumn": "id",
        "dbId": "wukong_crm_demo"
      }
    ]
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "创建成功",
  "data": {
    "objectCode": "by_customer"
  }
}
```
