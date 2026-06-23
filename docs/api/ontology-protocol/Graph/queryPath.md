# 查询路径

```
POST /DtStudio/daiservice/graph/queryPath
```

根据起点和终点查询两个节点之间的路径，返回路径节点序列、关系序列及路径描述。路径节点可为任意本体元素（对象、视图、动作、关系等），通过 `entityType` 区分。无需鉴权。

---

## Path Parameters

无

---

## Query Parameters

无

---

## Request Body

```
QueryPathRequest
```

### Schema

```json
{
  "sceneId": "2064947287571644418",                    // string，必填。场景 ID
  "matchBy": "name",                                   // string，可选。匹配方式
  "startNode": "北京市石景山区",                         // string，必填。起点节点值
  "endNode": "",                                      // string，可选。终点节点值
  "direction": "forward"                               // string，可选。方向
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `sceneId` | string | Yes | 场景 ID。`"-1"` 表示整个命名空间。场景列表可通过 [queryScenes](../Scene/queryScenes.md) 获取。 |
| `matchBy` | string | No | 匹配方式：`code` 按节点编码匹配，`name` 按节点名称匹配。默认 `code`。 |
| `startNode` | string | Yes | 起点节点值（编码或名称，取决于 `matchBy`）。 |
| `endNode` | string | No | 终点节点值。留空查询起点可达的所有路径。 |
| `direction` | string | No | 路径方向：`forward` 从起点到终点，`reverse` 从终点到起点。默认 `forward`。 |

---

## Response Body

```
QueryPathResponse
```

### Schema

```json
{
  "code": 200,                                        // integer
  "success": true,                                    // boolean
  "message": "查询成功",                               // string
  "data": {                                           // object，失败时为 null
    "totalCount": 2,                                  // integer。路径总数
    "paths": [                                        // array
      {
        "code": "BJ-SJSQ->",                          // string。路径编码
        "length": 3,                                  // integer。路径长度（节点数）
        "description": "北京市石景山区 -> 北京 -> 华北地区", // string。路径中文描述
        "entities": [                                 // array。路径上的节点序列
          {
            "entityType": "object",                   // string。实体类型
            "objectId": "2059910671387910156",        // string
            "objectCode": "BJ-SJSQ",                  // string
            "objectName": "北京市石景山区",             // string
            "objectType": "行政区"                     // string
          },
          {
            "entityType": "object",
            "objectId": "2059910671387910157",
            "objectCode": "BJ",
            "objectName": "北京",
            "objectType": "直辖市"
          },
          {
            "entityType": "object",
            "objectId": "2059910671387910158",
            "objectCode": "HB-DQ",
            "objectName": "华北地区",
            "objectType": "地理分区"
          }
        ],
        "relations": [                                // array。路径上的关系序列
          {
            "relationId": "2060306718048219138",      // string
            "relationCode": "belongs_to",             // string
            "relationName": "隶属于",                  // string
            "sourceEntityCode": "BJ-SJSQ",            // string。源节点编码
            "sourceEntityType": "object",             // string。源节点类型
            "targetEntityCode": "BJ",                 // string。目标节点编码
            "targetEntityType": "object",             // string。目标节点类型
            "attribute": {                            // object，可选
              "createTime": "2024-01-01"
            }
          },
          {
            "relationId": "2060306718048219139",
            "relationCode": "belongs_to",
            "relationName": "隶属于",
            "sourceEntityCode": "BJ",
            "sourceEntityType": "object",
            "targetEntityCode": "HB-DQ",
            "targetEntityType": "object"
          }
        ]
      }
    ]
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | object | Yes | 路径数据。失败时为 `null`。 |
| `data.totalCount` | integer | Yes | 路径总数。 |
| `data.paths` | array | Yes | 路径列表。 |
| `data.paths[].code` | string | Yes | 路径编码。 |
| `data.paths[].length` | integer | Yes | 路径长度（节点数）。 |
| `data.paths[].description` | string | Yes | 路径中文描述，`"A -> B -> C"` 格式。 |
| `data.paths[].entities` | array | Yes | 路径节点序列，按路径顺序排列。 |
| `data.paths[].entities[].entityType` | string | Yes | 实体类型：`object` / `view` / `action` / `relation`。 |

> `entityType` 对应的字段跟随已有实体命名体系：

| entityType | 字段 |
|---|---|
| `object` | `objectId` / `objectCode` / `objectName` / `objectType` |
| `view` | `viewCode` / `viewName` |
| `action` | `actionCode` / `actionName` / `belongObjectCode` |
| `relation` | `relationId` / `relationCode` / `relationName` |

| `data.paths[].relations` | array | Yes | 路径关系序列，长度为 `paths[].length - 1`。 |
| `data.paths[].relations[].relationId` | string | Yes | 关系 ID。 |
| `data.paths[].relations[].relationCode` | string | Yes | 关系编码。 |
| `data.paths[].relations[].relationName` | string | Yes | 关系名称。 |
| `data.paths[].relations[].sourceEntityCode` | string | Yes | 源节点编码。 |
| `data.paths[].relations[].sourceEntityType` | string | Yes | 源节点类型。 |
| `data.paths[].relations[].targetEntityCode` | string | Yes | 目标节点编码。 |
| `data.paths[].relations[].targetEntityType` | string | Yes | 目标节点类型。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：{具体原因}` | 必填参数缺失 |
| `404` | 404 | `未查询到起点到终点的路径` | 两节点间无可达路径 |
| `500` | 500 | `系统错误：{原因}` | 服务端异常 |

### Error Example

```json
{
  "code": 404,
  "success": false,
  "message": "未查询到起点到终点的路径",
  "data": null
}
```

---

## Example

### 按名称查询两点间路径

从"北京市石景山区"出发（空终点查所有可达路径），方向为 forward。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/DtStudio/daiservice/graph/queryPath" \
  -d '{
    "sceneId": "2064947287571644418",
    "matchBy": "name",
    "startNode": "北京市石景山区",
    "endNode": "",
    "direction": "forward"
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "totalCount": 2,
    "paths": [
      {
        "code": "BJ-SJSQ->",
        "length": 3,
        "description": "北京市石景山区 -> 北京 -> 华北地区",
        "entities": [
          { "entityType": "object", "objectId": "2059910671387910156", "objectCode": "BJ-SJSQ", "objectName": "北京市石景山区", "objectType": "行政区" },
          { "entityType": "object", "objectId": "2059910671387910157", "objectCode": "BJ", "objectName": "北京", "objectType": "直辖市" },
          { "entityType": "object", "objectId": "2059910671387910158", "objectCode": "HB-DQ", "objectName": "华北地区", "objectType": "地理分区" }
        ],
        "relations": [
          {
            "relationId": "2060306718048219138", "relationCode": "belongs_to", "relationName": "隶属于",
            "sourceEntityCode": "BJ-SJSQ", "sourceEntityType": "object",
            "targetEntityCode": "BJ", "targetEntityType": "object",
            "attribute": { "createTime": "2024-01-01" }
          },
          {
            "relationId": "2060306718048219139", "relationCode": "belongs_to", "relationName": "隶属于",
            "sourceEntityCode": "BJ", "sourceEntityType": "object",
            "targetEntityCode": "HB-DQ", "targetEntityType": "object"
          }
        ]
      }
    ]
  }
}
```
