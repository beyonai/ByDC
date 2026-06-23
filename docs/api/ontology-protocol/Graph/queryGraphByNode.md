# 查询图节点及关系

```
POST /DtStudio/daiservice/graph/queryGraph
```

按节点编码或名称查询指定跳数范围内的图节点及关系，支持按场景过滤。图节点可为任意本体元素（对象、视图、动作、关系等），通过 `entityType` 区分。无需鉴权。

---

## Path Parameters

无

---

## Query Parameters

无

---

## Request Body

```
QueryGraphRequest
```

### Schema

```json
{
  "sceneId": "2064947287571644418",                    // string，必填。场景 ID
  "objectCode": ["ontoDimRegion"],                     // string[]，必填。起始节点所属对象编码
  "matchBy": "name",                                   // string，可选。匹配方式
  "values": ["北京市石景山区"],                          // string[]，必填。匹配值列表
  "step": 1                                            // integer，可选。跳数
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `sceneId` | string | Yes | 场景 ID。`"-1"` 表示整个命名空间。场景列表可通过 [queryScenes](../Scene/queryScenes.md) 获取。 |
| `objectCode` | string[] | Yes | 起始节点的对象编码列表。对象列表可通过 [getSceneDetails](../Scene/getSceneDetails.md) 获取。 |
| `matchBy` | string | No | 匹配方式：`code` 按节点编码匹配，`name` 按节点名称匹配。默认 `code`。 |
| `values` | string[] | Yes | 匹配值列表，可传多个节点。值类型取决于 `matchBy`。 |
| `step` | integer | No | 查询跳数（N 跳范围）。默认 `1`。 |

---

## Response Body

```
QueryGraphResponse
```

### Schema

```json
{
  "code": 200,                                        // integer
  "success": true,                                    // boolean
  "message": "查询成功",                               // string
  "data": {                                           // object，失败时为 null
    "entities": [                                     // array。图节点，可为任意本体元素
      {
        "entityType": "object",                       // string。实体类型
        "objectCode": "ontoFactRevenue",              // string。entityType=object 时
        "objectName": "收入",                          // string
        "objectId": "2059910671387910220",            // string
        "step": 1                                     // integer。距起始节点的跳数
      },
      {
        "entityType": "view",
        "viewCode": "revenue_analysis",
        "viewName": "收入分析视图",
        "step": 2
      },
      {
        "entityType": "action",
        "actionCode": "get_by_customer",
        "actionName": "获取客户详情",
        "belongObjectCode": "by_customer",
        "step": 1
      },
      {
        "entityType": "relation",
        "relationCode": "produce",
        "relationName": "产生",
        "step": 1
      }
    ],
    "relations": [                                    // array。图边
      {
        "relationCode": "produce",                    // string
        "relationName": "产生",                        // string
        "sourceEntityCode": "ontoDimUser",            // string。源节点编码
        "sourceEntityType": "object",                 // string。源节点类型
        "targetEntityCode": "ontoFactCdr",            // string。目标节点编码
        "targetEntityType": "object",                 // string。目标节点类型
        "attribute": {                                // object，可选
          "sourceColumnCode": "user_id",
          "targetColumnCode": "user_id"
        }
      }
    ],
    "queryMatches": [                                 // array。匹配到的起始节点
      {
        "value": "北京市石景山区",                      // string。原始查询值
        "entityType": "object",                       // string
        "objectCode": "ontoDimRegion",                // string
        "objectName": "行政区划",                      // string
        "objectId": "2059910671387910156"             // string
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
| `data` | object | Yes | 图数据。失败时为 `null`。 |
| `data.entities` | array | Yes | 图节点列表，节点可为任意本体元素。 |
| `data.entities[].entityType` | string | Yes | 实体类型：`object` / `view` / `action` / `relation`。 |
| `data.entities[].step` | integer | Yes | 距起始节点的跳数。 |

> `entityType` 对应的字段跟随已有实体命名体系：

| entityType | 字段（从已有接口同名） |
|---|---|
| `object` | `objectCode` / `objectName` / `objectId`（见 [models/Object.md](../models/Object.md)） |
| `view` | `viewCode` / `viewName`（见 [models/View.md](../models/View.md)） |
| `action` | `actionCode` / `actionName` / `belongObjectCode`（见 [models/Action.md](../models/Action.md)） |
| `relation` | `relationCode` / `relationName`（见 [models/Relation.md](../models/Relation.md)） |

| `data.relations` | array | Yes | 图边列表。 |
| `data.relations[].relationCode` | string | Yes | 关系编码。 |
| `data.relations[].relationName` | string | Yes | 关系名称。 |
| `data.relations[].sourceEntityCode` | string | Yes | 源节点编码。 |
| `data.relations[].sourceEntityType` | string | Yes | 源节点类型。 |
| `data.relations[].targetEntityCode` | string | Yes | 目标节点编码。 |
| `data.relations[].targetEntityType` | string | Yes | 目标节点类型。 |
| `data.queryMatches` | array | Yes | 匹配到的起始节点列表。 |
| `data.queryMatches[].value` | string | Yes | 原始查询值。 |
| `data.queryMatches[].entityType` | string | Yes | 匹配到的实体类型。 |
| `data.queryMatches[].objectCode` | string | No | entityType=object 时的编码。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：{具体原因}` | 必填参数缺失 |
| `500` | 500 | `系统错误：{原因}` | 服务端异常 |

### Error Example

```json
{
  "code": 400,
  "success": false,
  "message": "参数错误：sceneId不能为空",
  "data": null
}
```

---

## Example

### 按名称查询节点 1 跳图

在场景中查询名称为"北京市石景山区"的节点 1 跳关联图。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/DtStudio/daiservice/graph/queryGraph" \
  -d '{
    "sceneId": "2064947287571644418",
    "objectCode": ["ontoDimRegion"],
    "matchBy": "name",
    "values": ["北京市石景山区"],
    "step": 1
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "entities": [
      {
        "entityType": "object",
        "objectCode": "ontoFactRevenue",
        "objectName": "收入",
        "objectId": "2059910671387910220",
        "step": 1
      }
    ],
    "relations": [
      {
        "relationCode": "produce",
        "relationName": "产生",
        "sourceEntityCode": "ontoDimUser",
        "sourceEntityType": "object",
        "targetEntityCode": "ontoFactCdr",
        "targetEntityType": "object",
        "attribute": {
          "sourceColumnCode": "user_id",
          "targetColumnCode": "user_id"
        }
      }
    ],
    "queryMatches": [
      {
        "value": "北京市石景山区",
        "entityType": "object",
        "objectCode": "ontoDimRegion",
        "objectName": "行政区划",
        "objectId": "2059910671387910156"
      }
    ]
  }
}
```
