# 创建视图

```
POST /api/v1/ontologyBases/{baseId}/views
```

仅 LOCAL 可用。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `baseId` | string | 本体库 API 名称。 |

---

## Request Body

```json
{
  "viewCode": "customer_analysis",
  "viewName": "客户分析视图",
  "description": "以客户信息表为主对象的分析视图。",
  "objectCodes": ["by_customer", "order_details"],
  "properties": [
    {
      "propertyCode": "customer_name",
      "propertyName": "客户名称",
      "sourceObject": "by_customer",
      "sourceObjectProperty": "customer_name"
    }
  ]
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `viewCode` | string | Yes | 视图编码。不可重复。 |
| `viewName` | string | Yes | 视图名称。 |
| `description` | string | No | 视图描述。 |
| `objectCodes` | array | No | 包含的对象编码列表。 |
| `properties` | array | No | 视图属性，含 `sourceObject` 和 `sourceObjectProperty` 映射。 |

> `properties` 元素定义见 [ViewProperty](../../ontology-protocol/models/ViewProperty.md)

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "创建成功",
  "data": {
    "viewCode": "customer_analysis"
  }
}
```

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `403` | 403 | `Remote ontology base is read-only` | REMOTE 写操作。 |
| `409` | 409 | `视图「{viewCode}」已存在` | 编码重复。 |
