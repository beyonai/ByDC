# 本体统一检索

```
POST /DtStudio/daiservice/search/ontology
```

统一的本体元数据 + 实例数据检索接口。支持向量检索、关键词检索和混合检索三种模式，可按场景、视图、对象类型限定搜索范围，按搜索域控制返回内容。无需鉴权。

---

## Path Parameters

无

---

## Query Parameters

无

---

## Request Body

```
SearchOntologyRequest
```

### Schema

```json
{
  "sceneId": "2064947287571644418",                    // string，必填。场景 ID
  "keyword": "客户",                                    // string，必填。检索关键词
  "queryType": "vector",                               // string，可选。检索模式
  "searchScope": "all",                                // string，可选。搜索域
  "objectCode": ["by_customer"],                       // string[]，可选。按对象编码限定范围
  "viewCode": [],                                      // string[]，可选。按视图编码限定范围
  "propertyCode": [],                                  // string[]，可选。按属性编码限定范围
  "resultPerType": 5,                                  // integer，可选。每种结果类型的返回上限
  "pageSize": 20,                                      // integer，可选。每页条数
  "pageToken": ""                                      // string，可选。分页游标
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `sceneId` | string | Yes | 场景 ID。`"-1"` 表示整个命名空间检索。具体场景可通过 [queryScenes](../Scene/queryScenes.md) 获取。 |
| `keyword` | string | Yes | 检索关键词。向量检索时用于生成 query embedding，关键词检索时用于全文匹配。 |
| `queryType` | string | No | 检索模式。默认 `vector`。 |
| `searchScope` | string | No | 搜索域。默认 `all`。 |
| `objectCode` | string[] | No | 按对象编码限定搜索范围。空数组表示不限定。对象列表可通过 [getSceneDetails](../Scene/getSceneDetails.md) 获取。 |
| `viewCode` | string[] | No | 按视图编码限定搜索范围。空数组表示不限定。 |
| `propertyCode` | string[] | No | 按属性编码限定实例搜索范围。仅 `searchScope` 含 `instance` 时生效。 |
| `resultPerType` | integer | No | 每种结果类型的返回上限。默认 `5`，上限 `20`。 |
| `pageSize` | integer | No | 每页总条数。默认 `20`，上限 `100`。 |
| `pageToken` | string | No | 分页游标。首次留空，后续取响应 `nextPageToken` 填入。 |

### 字段说明

> `queryType` 枚举值：

| 值 | 说明 |
|---|---|
| `vector` | 向量语义检索。默认值。 |
| `keyword` | 关键词全文检索。 |
| `hybrid` | 混合检索。向量 + 关键词结果融合排序。 |

> `searchScope` 枚举值：

| 值 | 说明 | 适用场景 |
|---|---|---|
| `metadata` | 仅搜索元数据（对象类型名/描述、视图名/描述、动作名/描述）。 | 找"客户信息表"这个对象类型是否存在。 |
| `instance` | 仅搜索实例数据（各对象类型的属性值）。 | 找"张三"这个客户、找"签约失败"这个枚举值。 |
| `all` | 同时搜索元数据和实例。默认值。 | 全局搜索，不确定目标在哪个域。 |

---

## 枚举型对象类型的搜索链路

当枚举值被建模为独立的 Object Type（例如 `sign_status` "签约状态"，其实例为"签约失败"、"签约成功"等），搜索"签约失败"是一个 `instance` 域的检索——因为这个标签存在`sign_status` 对象的**实例**中，不在元数据中。

但命中枚举实例后，调用方真正需要的往往**不是**这个枚举实例本身，**而是**知道"哪些业务对象的哪个属性引用了这个枚举"。此信息由实例结果附带的 `referencedByProperties` 提供。

**完整链路：**

```
搜索 "签约失败"
  → searchScope: "instance"（枚举值标签在实例数据中，不在元数据中）
  → 命中 sign_status 实例 { name: "签约失败", code: "SIGN_FAILED" }
  → 该对象类型为枚举型（isEnumType: true）
  → 附带 referencedByProperties: [contract.sign_status, agreement.status]
  → 调用方得知：合同和协议两个对象的属性使用了此枚举
  → 后续可调 searchInstances 查 contract 中 sign_status = "签约失败" 的实例（可能 0 条）
```

**关键设计：**
- `referencedByProperties` 挂在 `instances[]` 结果上，而非 `metadata[]` 上——因为触发它的入口是实例命中。
- `searchScope` 的最小范围是 `"instance"`，不需要 `"metadata"` 或 `"all"`。
- `metadataTypes` 和 `propertyCode` 不相关——枚举命中和它们无关。
- 即使当前没有任何业务实例使用了此枚举值，`referencedByProperties` 仍会返回，让前端可展示"存在此状态，对应这些对象类型的这些属性"。

---

## Response Body

```
SearchOntologyResponse
```

### Schema

```json
{
  "code": 200,                                        // integer
  "success": true,                                    // boolean
  "message": "查询成功",                               // string
  "data": {                                           // object，失败时为 null
    "metadata": [                                     // array。元数据命中结果
      {
        "sceneId": "2064947287571644418",             // string。所属场景 ID
        "resultType": "object",                       // string。结果类型
        "objectCode": "by_customer",                  // string
        "objectName": "客户信息表",                    // string
        "objectDesc": "CRM 客户主数据对象",            // string，可选
        "objectSource": "DB",                         // string，可选
        "matchedField": "objectName",                 // string。命中的字段
        "score": 0.92                                 // number。相关度分数
      },
      {
        "resultType": "view",
        "viewCode": "customer_analysis",
        "viewName": "客户分析视图",
        "description": "以客户信息表为主对象的分析视图",
        "matchedField": "viewName",
        "score": 0.85
      },
      {
        "resultType": "action",
        "actionCode": "get_by_customer",
        "actionName": "获取客户详情",
        "actionDesc": "根据主键 id 查询单条客户记录",
        "belongObjectCode": "by_customer",
        "matchedField": "actionName",
        "score": 0.78
      }
    ],
    "instances": [                                    // array。实例命中结果
      {
        "sceneId": "2064947287571644418",             // string。所属场景 ID
        "objectCode": "by_customer",                  // string。所属对象编码
        "objectName": "客户信息表",                    // string。所属对象名称
        "primaryKey": 1,                              // integer。实例主键
        "matchedProperty": "customer_name",           // string。命中的属性编码
        "matchedValue": "张三",                        // string。命中的属性值
        "isEnumType": false,                          // boolean。是否为枚举型对象类型
        "referencedByProperties": [],                 // array。isEnumType=true 时列出引用方属性
        "score": 0.91,                                // number。相关度分数
        "properties": {                               // object。实例的核心属性
          "id": 1,
          "customer_code": "C001",
          "customer_name": "张三",
          "industry": "金融",
          "province": "北京"
        }
      },
      {
        "sceneId": "2064947287571644418",
        "objectCode": "sign_status",
        "objectName": "签约状态",
        "primaryKey": 3,
        "matchedProperty": "name",
        "matchedValue": "签约失败",
        "isEnumType": true,
        "referencedByProperties": [
          {
            "objectCode": "contract",                 // string。引用方对象编码
            "objectName": "合同",                      // string。引用方对象名称
            "propertyCode": "sign_status",            // string。引用方属性编码
            "propertyName": "签约状态"                  // string。引用方属性名称
          },
          {
            "objectCode": "agreement",
            "objectName": "协议",
            "propertyCode": "status",
            "propertyName": "签署状态"
          }
        ],
        "score": 0.93,
        "properties": {
          "id": 3,
          "code": "SIGN_FAILED",
          "name": "签约失败"
        }
      }
    ],
    "totalCount": {                                   // object。各域命中总数
      "metadata": 12,
      "instances": 45
    },
    "nextPageToken": "v1.xxx"                         // string，可选。下一页游标
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | object | Yes | 检索结果。失败时为 `null`。 |
| `data.metadata` | array | No | 元数据命中列表。`searchScope` 不含 `metadata` 时为空数组。 |
| `data.metadata[].sceneId` | string | Yes | 所属场景 ID。 |
| `data.metadata[].resultType` | string | Yes | 结果类型：`object` / `view` / `action`。 |
| `data.metadata[].score` | number | Yes | 相关度分数（0~1）。 |
| `data.instances` | array | No | 实例命中列表。`searchScope` 不含 `instance` 时为空数组。 |
| `data.instances[].sceneId` | string | Yes | 所属场景 ID。 |
| `data.instances[].objectCode` | string | Yes | 所属对象编码。 |
| `data.instances[].objectName` | string | Yes | 所属对象名称。 |
| `data.instances[].primaryKey` | integer | Yes | 实例主键。 |
| `data.instances[].matchedProperty` | string | Yes | 命中的属性编码。 |
| `data.instances[].matchedValue` | string | Yes | 命中的属性值。 |
| `data.instances[].isEnumType` | boolean | Yes | 是否为枚举型对象类型。 |
| `data.instances[].referencedByProperties` | array | Yes | 引用属性列表。`isEnumType = false` 时为空数组。 |
| `data.instances[].referencedByProperties[].objectCode` | string | Yes | 引用方对象编码。 |
| `data.instances[].referencedByProperties[].objectName` | string | Yes | 引用方对象名称。 |
| `data.instances[].referencedByProperties[].propertyCode` | string | Yes | 引用方属性编码。 |
| `data.instances[].referencedByProperties[].propertyName` | string | Yes | 引用方属性名称。 |
| `data.instances[].score` | number | Yes | 相关度分数（0~1）。 |
| `data.instances[].properties` | object | Yes | 实例的核心属性。完整属性可通过 [searchInstances](../Instance/searchInstances.md) 按 primaryKey 查询。 |
| `data.totalCount` | object | No | 各域命中总数。 |
| `data.totalCount.metadata` | integer | No | 元数据命中总数。 |
| `data.totalCount.instances` | integer | No | 实例命中总数。 |
| `data.nextPageToken` | string | No | 下一页游标。最后一页无此字段。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：sceneId不能为空` | `sceneId` 未传或为空 |
| `400` | 400 | `参数错误：keyword不能为空` | `keyword` 未传或为空 |
| `400` | 400 | `参数错误：searchScope必须为 metadata / instance / all 之一` | `searchScope` 不在枚举值内 |
| `404` | 404 | `未查询到场景「{sceneId}」` | 指定场景不存在 |
| `500` | 500 | `系统错误：{原因}` | 服务端异常 |

### Error Example

```json
{
  "code": 400,
  "success": false,
  "message": "参数错误：keyword不能为空",
  "data": null
}
```

---

## Example

### 全量混合检索

在场景中搜索"客户"，同时返回元数据和实例结果。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/DtStudio/daiservice/search/ontology" \
  -d '{
    "sceneId": "2064947287571644418",
    "keyword": "客户",
    "queryType": "hybrid",
    "searchScope": "all",
    "resultPerType": 3
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
        "objectDesc": "CRM 客户主数据对象",
        "objectSource": "DB",
        "matchedField": "objectName",
        "score": 0.95
      },
      {
        "sceneId": "2064947287571644418",
        "resultType": "view",
        "viewCode": "customer_analysis",
        "viewName": "客户分析视图",
        "description": "以客户信息表为主对象的分析视图",
        "matchedField": "viewName",
        "score": 0.87
      },
      {
        "sceneId": "2064947287571644418",
        "resultType": "action",
        "actionCode": "get_by_customer",
        "actionName": "获取客户详情",
        "actionDesc": "根据主键 id 查询单条客户记录",
        "belongObjectCode": "by_customer",
        "matchedField": "actionName",
        "score": 0.76
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
          "customer_name": "张三",
          "industry": "金融",
          "province": "北京"
        }
      }
    ],
    "totalCount": { "metadata": 8, "instances": 23 }
  }
}
```

### 仅搜元数据

搜索对象类型和视图中匹配"收入"的条目。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/DtStudio/daiservice/search/ontology" \
  -d '{
    "sceneId": "2064947287571644418",
    "keyword": "收入",
    "searchScope": "metadata"
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
        "objectCode": "ontoFactRevenue",
        "objectName": "收入",
        "objectDesc": null,
        "matchedField": "objectName",
        "score": 0.98
      },
      {
        "sceneId": "2064947287571644418",
        "resultType": "view",
        "viewCode": "revenue_analysis",
        "viewName": "收入分析视图",
        "description": "按月份、战区分析收入",
        "matchedField": "viewName",
        "score": 0.82
      }
    ],
    "instances": [],
    "totalCount": { "metadata": 2, "instances": 0 }
  }
}
```

### 跨场景检索

传入 `sceneId: "-1"` 在整个命名空间搜索，每个命中结果携带各自的场景 ID。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/DtStudio/daiservice/search/ontology" \
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
        "properties": { "id": 1, "customer_code": "C001", "customer_name": "张三" }
      },
      {
        "sceneId": "2089012345678901234",
        "objectCode": "crm_customer",
        "objectName": "CRM客户",
        "primaryKey": 42,
        "matchedProperty": "name",
        "matchedValue": "李四",
        "isEnumType": false,
        "referencedByProperties": [],
        "score": 0.85,
        "properties": { "id": 42, "code": "CRM042", "name": "李四" }
      }
    ],
    "totalCount": { "metadata": 5, "instances": 18 }
  }
}
```

### 枚举型对象实例检索

搜索"签约失败"，命中枚举对象 `sign_status` 的实例。响应中 `isEnumType: true` 且 `referencedByProperties` 列出引用方。仅需 `searchScope: "instance"`。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/DtStudio/daiservice/search/ontology" \
  -d '{
    "sceneId": "2064947287571644418",
    "keyword": "签约失败",
    "searchScope": "instance",
    "resultPerType": 3
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "metadata": [],
    "instances": [
      {
        "sceneId": "2064947287571644418",
        "objectCode": "sign_status",
        "objectName": "签约状态",
        "primaryKey": 3,
        "matchedProperty": "name",
        "matchedValue": "签约失败",
        "isEnumType": true,
        "referencedByProperties": [
          {
            "objectCode": "contract",
            "objectName": "合同",
            "propertyCode": "sign_status",
            "propertyName": "签约状态"
          },
          {
            "objectCode": "agreement",
            "objectName": "协议",
            "propertyCode": "status",
            "propertyName": "签署状态"
          }
        ],
        "score": 0.93,
        "properties": {
          "id": 3,
          "code": "SIGN_FAILED",
          "name": "签约失败"
        }
      }
    ],
    "totalCount": { "metadata": 0, "instances": 1 }
  }
}
```
