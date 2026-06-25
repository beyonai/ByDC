# 列出视图

```
GET /api/v1/ontologyBases/{ownerType}/{baseId}/views
```

列出本体库下的视图摘要列表。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ownerType` | string | personal / enterprise |
| `baseId` | string | 本体库 API 名称。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": [
    {
      "viewCode": "scene_new_sales_analysis",
      "viewName": "复合肥销售分析视图",
      "description": "以复合肥销量宽表为主对象。",
      "objectCodes": ["dwd_..._demo", "order_details"]
    }
  ],
  "totalCount": 2
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | array | Yes | 视图列表。失败时为 `null`。 |
| `data[].viewCode` | string | Yes | 视图编码。 |
| `data[].viewName` | string | Yes | 视图名称。 |
| `data[].description` | string | No | 视图描述。 |
| `data[].objectCodes` | array | No | 包含的对象编码列表。 |
| `totalCount` | integer | Yes | 全量总数。 |

---

## Example

#### Request

```bash
curl -X GET \
  "https://$HOSTNAME/api/v1/ontologyBases/personal/crm_demo/views"
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": [
    {
      "viewCode": "customer_analysis",
      "viewName": "客户分析视图",
      "description": "以客户信息表为主对象。",
      "objectCodes": ["by_customer", "order_details"]
    }
  ],
  "totalCount": 1
}
```
