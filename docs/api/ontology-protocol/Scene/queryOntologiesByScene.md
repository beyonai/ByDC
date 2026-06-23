# 根据场景查询本体列表

```
POST /DtStudio/daiservice/OntologyScenceController/queryOntologies
```

按场景 ID 分页查询该场景下的本体列表。`sceneId` 传 `-1` 表示查询所有场景的本体。无需鉴权。

---

## Path Parameters

无

---

## Query Parameters

无

---

## Request Body

```
QueryOntologiesBySceneRequest
```

### Schema

```json
{
  "sceneId": "-1",                                   // string，必填。"-1" 表示所有场景
  "queryKeyword": "",                                 // string，可选。本体名称/编码关键词
  "pageSize": 10,                                     // integer，可选。每页条数
  "pageIndex": 1                                      // integer，可选。页码，从 1 开始
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `sceneId` | string | Yes | 场景 ID。`-1` 查询所有场景下的本体。场景列表可通过 [queryScenes](../Scene/queryScenes.md) 获取。 |
| `queryKeyword` | string | No | 模糊查询关键词，匹配本体名称和编码。留空返回全部。 |
| `pageSize` | integer | No | 每页条数。默认 `10`。 |
| `pageIndex` | integer | No | 页码，从 `1` 开始。默认 `1`。 |

---

## Response Body

```
QueryOntologiesBySceneResponse
```

### Schema

```json
{
  "code": 200,                                        // integer
  "success": true,                                    // boolean
  "message": "查询成功",                               // string
  "data": [                                           // array，失败时为 null
    {
      "ontologyId": "2064914044688310343",            // string
      "sceneId": "2064947287571644418",              // string
      "ontologyName": "套餐信息",                      // string
      "ontologyCode": "ontoDimPackageDemo",           // string
      "ontologySource": "db/doc/api",                 // string，可选
      "ontologyDesc": null,                           // string，可选
      "conceptType": "1",                             // string，可选
      "ontologyType": null,                           // string，可选
      "domainType": null                              // string，可选
    }
  ],
  "nextPageToken": "...",                             // string，可选
  "totalCount": 100                                   // integer
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | array | Yes | 本体摘要列表。失败时为 `null`。 |
| `nextPageToken` | string | No | 下一页游标。最后一页无此字段。 |
| `totalCount` | integer | Yes | 全量总数。 |

> 本体摘要字段定义见 [models/OntologySummary.md](../models/OntologySummary.md)

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：场景ID不能为空` | `sceneId` 未传或为空 |
| `500` | 500 | `系统错误：{原因}` | 服务端异常 |

### Error Example

```json
{
  "code": 400,
  "success": false,
  "message": "参数错误：场景ID不能为空",
  "data": null
}
```

---

## Example

### 查询所有场景下的本体

不传关键词，查第 1 页，每页 10 条。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/DtStudio/daiservice/OntologyScenceController/queryOntologies" \
  -d '{
    "sceneId": "-1",
    "queryKeyword": "",
    "pageSize": 10,
    "pageIndex": 1
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": [
    {
      "ontologyId": "2064914044688310343",
      "sceneId": "2064947287571644418",
      "ontologyName": "套餐信息",
      "ontologyCode": "ontoDimPackageDemo",
      "ontologySource": "db/doc/api",
      "ontologyDesc": null,
      "conceptType": "1",
      "ontologyType": null,
      "domainType": null
    }
  ],
  "totalCount": 1
}
```
