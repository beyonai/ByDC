# 跨场景检索

```
POST /api/v1/ontologyBases/{ownerType}/{baseId}/search
```

跨场景统一检索。调用方在 body 中指定 `sceneId`，`"-1"` 跨所有场景。

- **LOCAL** 时本地执行，与场景内检索逻辑相同，区别仅在于 `sceneId="-1"` 时不对 term 做场景限定。
- **REMOTE** 时 body 原样转发到外部服务。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ownerType` | string | personal / enterprise |
| `baseId` | string | 本体库 API 名称。 |

---

## Request Body

```
SearchNamespaceRequest
```

### Schema

```json
{
  "sceneId": "-1",
  "keyword": "客户",
  "queryType": "hybrid",
  "searchScope": "all",
  "objectCode": [],
  "viewCode": [],
  "propertyCode": [],
  "resultPerType": 5,
  "pageSize": 20,
  "pageToken": ""
}
```

### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `sceneId` | string | Yes | — | 场景 ID。`"-1"` 跨所有场景。 |
| `keyword` | string | Yes | — | 检索关键词。 |
| `queryType` | string | No | `vector` | 检索模式。 |
| `searchScope` | string | No | `all` | 搜索域。 |
| `objectCode` | string[] | No | — | 按对象编码限定范围。 |
| `viewCode` | string[] | No | — | 按视图编码限定范围。 |
| `propertyCode` | string[] | No | — | 按属性编码限定实例搜索范围。 |
| `resultPerType` | integer | No | `5` | 每种类型上限。 |
| `pageSize` | integer | No | `20` | 每页条数。 |
| `pageToken` | string | No | — | 分页游标。 |

> `queryType` 枚举值：`vector` / `keyword` / `hybrid`
> `searchScope` 枚举值：`metadata` / `instance` / `all`

---

## LOCAL 行为说明

同 [searchScene](searchScene.md) 的 LOCAL 行为，区别在于 `sceneId="-1"` 时不限定场景范围。

---

## Response Body

同 [searchScene](searchScene.md)，响应的 `metadata[]` 和 `instances[]` 中每个元素会携带各自所属的 `sceneId`。

---

## Example

### 跨场景检索

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/api/v1/ontologyBases/personal/bio_platform/search" \
  -d '{
    "sceneId": "-1",
    "keyword": "客户",
    "searchScope": "all",
    "resultPerType": 2
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "metadata": [
      {
        "sceneId": "2064947287571644418",
        "resultType": "object",
        "objectCode": "by_customer",
        "objectName": "客户信息表",
        "matchedField": "objectName",
        "score": 0.95
      },
      {
        "sceneId": "2089012345678901234",
        "resultType": "object",
        "objectCode": "crm_customer",
        "objectName": "CRM客户",
        "matchedField": "objectName",
        "score": 0.88
      }
    ],
    "instances": [
      {
        "sceneId": "2064947287571644418",
        "objectCode": "by_customer",
        "objectName": "客户信息表",
        "primaryKey": 1,
        "matchedProperty": "customer_name",
        "matchedValue": "张三",
        "isEnumType": false,
        "referencedByProperties": [],
        "score": 0.93,
        "properties": {
          "id": 1,
          "customer_code": "C001",
          "customer_name": "张三"
        }
      }
    ],
    "totalCount": {
      "metadata": 5,
      "instances": 18
    }
  }
}
```
