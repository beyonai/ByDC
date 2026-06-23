# 获取视图详情

```
GET /api/v1/ontologyBases/{ownerType}/{baseId}/scenes/{sceneId}/views/{viewCode}
```

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ownerType` | string | personal / enterprise |
| `baseId` | string | 本体库 API 名称。 |
| `sceneId` | string | 场景 ID。 |
| `viewCode` | string | 视图编码。获取方式见 [listViews](listViews.md)。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "viewCode": "scene_new_sales_analysis",
    "viewName": "复合肥销售分析视图",
    "description": "以复合肥销量宽表为主对象。",
    "objectCodes": ["dwd_..._demo", "order_details"],
    "properties": [
      {
        "propertyName": "销售日期",
        "propertyCode": "day",
        "sourceObject": "dwd_..._demo",
        "sourceObjectProperty": "day"
      }
    ]
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data.viewCode` | string | Yes | 视图编码。 |
| `data.viewName` | string | Yes | 视图名称。 |
| `data.description` | string | No | 视图描述。 |
| `data.objectCodes` | array | No | 包含的对象编码列表。 |
| `data.properties` | array | No | 视图属性列表，含 `sourceObject` 和 `sourceObjectProperty` 映射。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `404` | 404 | `未查询到视图「{viewCode}」` | 指定视图不存在。 |
