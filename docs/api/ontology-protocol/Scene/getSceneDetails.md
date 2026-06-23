# 查询本体详情

```
POST /DtStudio/daiservice/OntologyEntityController/sceneDetails
```

查询场景的本体详情。支持按视图编码或对象编码筛选，**响应中各列表自动裁剪为筛选结果的关联子图**，不返回无关数据。无需鉴权。

---

## Path Parameters

无

---

## Query Parameters

无

---

## Request Body

```
GetSceneDetailsRequest
```

### Schema

```json
{
  "sceneId": "2060279899043520523",                     // string，必填
  "viewCode": [],                                     // string[]，可选。按视图编码筛选
  "objectCode": []                                    // string[]，可选。按对象编码筛选
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `sceneId` | string | Yes | 场景 ID。场景列表可通过 [queryScenes](../Scene/queryScenes.md) 获取。 |
| `viewCode` | string[] | No | 按视图编码（`viewCode`）筛选。空数组表示返回全部视图。 |
| `objectCode` | string[] | No | 按对象编码（`objectCode`）筛选。空数组表示返回全部对象。 |

### 筛选规则

**两个筛选参数可同时传入，效果取并集。** 以下以单独传入为例说明关联裁剪逻辑。

**仅传入 `viewCode`：**

| 返回列表 | 裁剪规则 |
|---|---|
| `views` | 仅返回 `viewCode` 匹配的视图。 |
| `objects` | 返回这些视图的 `objectCodes` 引用的全部对象。 |
| `actions` | 返回上述对象的 `belongObjectCode` 关联的全部动作。 |
| `relations` | 返回 `sourceObjectCode` 和 `targetObjectCode` **均**在上述对象集合内的关系。 |
| `dbsources` | 返回上述对象的 `properties[].dbId` 引用的全部数据源。 |

**仅传入 `objectCode`：**

| 返回列表 | 裁剪规则 |
|---|---|
| `objects` | 仅返回 `objectCode` 匹配的对象。 |
| `views` | 空数组。 |
| `actions` | 返回上述对象的 `belongObjectCode` 关联的全部动作。 |
| `relations` | 返回 `sourceObjectCode` 和 `targetObjectCode` **均**在上述对象集合内的关系。 |
| `dbsources` | 返回上述对象的 `properties[].dbId` 引用的全部数据源。 |

**不传筛选参数（空数组）：** 返回场景下全部数据。

---

## Response Body

```
GetSceneDetailsResponse
```

### Schema

```json
{
  "code": 200,                                        // integer
  "success": true,                                    // boolean
  "message": "查询成功",                               // string
  "data": {                                           // object，失败时为 null
    "scene": {                                       // object。场景信息始终返回
      "sceneId": "2064947287571644418",              // string
      "sceneName": "默认场景",                        // string
      "sceneCode": "DefaultDemo",                    // string
      "sceneDesc": "初始化场景，包含所有对象"           // string，可选
    },
    "views": [                                        // array。按筛选规则裁剪
      {
        "viewCode": "scene_new_sales_analysis",       // string
        "viewName": "复合肥销售分析视图",               // string
        "description": "...",                         // string
        "objectCodes": ["dwd_..._demo", "order_details"], // string[]
        "properties": [                               // array
          {
            "propertyName": "销售日期",                 // string
            "propertyCode": "day",                    // string
            "sourceObject": "dwd_..._demo",           // string
            "sourceObjectProperty": "day"             // string
          }
        ]
      }
    ],
    "objects": [                                      // array。按筛选规则裁剪
      {
        "objectId": null,                             // string，可选
        "objectCode": "by_customer",                  // string
        "objectName": "客户信息表",                    // string
        "objectSource": "DB",                         // string，可选
        "objectDesc": "...",                          // string，可选
        "conceptType": "1",                           // string，可选
        "objectType": null,                           // string，可选
        "domainType": null,                           // string，可选
        "sceneId": null,                             // string，可选
        "properties": [                               // array
          {
            "propertyName": "主键",                   // string
            "propertyCode": "id",                     // string
            "dataType": "BIGINT",                     // string，可选
            "dataFormat": null,                       // string，可选
            "isRequired": 1,                          // integer
            "businessKey": 1,                         // integer
            "sourceColumn": "id",                     // string
            "dbId": "wukong_crm_demo",                // string
            "terminology": {                          // object，可选
              "termMasterType": "dict",
              "termTypeCode": "industry",
              "termField": "code"
            }
          }
        ]
      }
    ],
    "actions": [                                      // array。仅返回裁剪后对象集合的动作
      {
        "actionCode": "create_by_customer",           // string
        "actionName": "新增客户",                      // string
        "actionType": "operation",                    // string
        "belongObjectCode": "by_customer",            // string
        "actionDesc": "...",                          // string，可选
        "params": [                                   // array
          {
            "paramCode": "customerName",              // string
            "paramName": "客户名称",                   // string
            "paramType": "STRING",                    // string
            "isRequired": 0,                          // integer
            "direction": "IN",                        // string
            "mappingPath": "$.requestBody.customerName" // string
          }
        ],
        "requestUrl": "/api/by/customer/add",         // string
        "requestMethod": "POST",                      // string
        "script": null                                // string，可选
      }
    ],
    "relations": [                                    // array。两端对象均在裁剪集合内才返回
      {
        "objectRelationId": null,                     // string，可选
        "relationCode": "rel_...",                    // string
        "relationName": "复合肥销量关联订单明细",        // string
        "relationSceneType": "entity",                // string，可选
        "relationCardinality": "N:1",                 // string
        "relationDesc": "",                           // string，可选
        "sourceObjectCode": "dwd_..._demo",           // string
        "sourceObjectName": "复合肥销量演示宽表",        // string，可选
        "targetObjectCode": "order_details",          // string
        "targetObjectName": "订单明细表",              // string，可选
        "srcMetaId": null,                            // string，可选
        "srcColumnId": "",                            // string，可选
        "targetMetaId": null,                         // string，可选
        "targetColumnId": "",                         // string，可选
        "attribute": null,                            // object，可选
        "sortNo": 1,                                  // integer
        "status": 1                                   // integer
      }
    ],
    "dbsources": {                                    // object。仅返回裁剪后对象引用的数据源
      "db": [                                       // array
        {
          "dbId": "wukong_crm_demo",                // string
          "dbCode": "wukong_crm_demo",              // string
          "dbType": "opengauss",                    // string
          "dbParams": {                             // object
            "jdbc_url": "jdbc:opengauss://...",     // string
            "user": "gaussdb",                      // string
            "password": "***",                      // string
            "pool_min": 5,                          // integer
            "pool_max": 20                          // integer
          }
        }
      ],
      "doc": [                                      // array
        {
          "docId": "19",                            // string
          "docPath": "/会议纪要"                     // string
        }
      ],
      "api": []                                     // array
    },
    "version": "v0.0.1"                               // string，可选
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | object | Yes | 场景本体详情，各列表按筛选规则裁剪。失败时为 `null`。 |

> `data.scene` 字段定义见 [models/Scene.md](../models/Scene.md)
> `data.views` 元素定义见 [models/View.md](../models/View.md)
> `data.objects` 元素定义见 [models/Object.md](../models/Object.md)，嵌套 `properties` 见 [models/Property.md](../models/Property.md)
> `data.actions` 元素定义见 [models/Action.md](../models/Action.md)，嵌套 `params` 见 [models/ActionParam.md](../models/ActionParam.md)
> `data.relations` 元素定义见 [models/Relation.md](../models/Relation.md)
> `data.dbsources` 字段定义见 [models/Dbsource.md](../models/Dbsource.md)

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：场景ID不能为空` | `sceneId` 未传或为空字符串 |
| `404` | 404 | `未查询到场景「{sceneId}」` | 指定场景不存在 |
| `500` | 500 | `系统错误：{原因}` | 服务端异常 |

### Error Example

```json
{
  "code": 404,
  "success": false,
  "message": "未查询到场景「999」",
  "data": null
}
```

---

## Example

### 查询全部

不传筛选，返回场景全量元数据。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/DtStudio/daiservice/OntologyEntityController/sceneDetails" \
  -d '{
    "sceneId": "2060279899043520523",
    "viewCode": [],
    "objectCode": []
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "scene": {
      "sceneId": "2064947287571644418",
      "sceneName": "默认场景",
      "sceneCode": "DefaultDemo",
      "sceneDesc": "初始化场景，包含所有对象"
    },
    "views": [
      {
        "viewCode": "scene_new_sales_analysis",
        "viewName": "复合肥销售分析视图",
        "objectCodes": ["dwd_ai_yx_compound_fertilizer_sales_df_demo", "order_details"],
        "properties": [
          { "propertyName": "销售日期", "propertyCode": "day", "sourceObject": "dwd_ai_yx_compound_fertilizer_sales_df_demo", "sourceObjectProperty": "day" }
        ]
      }
      // ... 其他视图省略
    ],
    "objects": [
      {
        "objectCode": "by_customer",
        "objectName": "客户信息表",
        "objectSource": "DB",
        "objectDesc": "CRM 客户主数据对象。",
        "properties": [
          { "propertyName": "主键", "propertyCode": "id", "dataType": "BIGINT", "businessKey": 1, "sourceColumn": "id", "dbId": "wukong_crm_demo" }
        ]
      },
      {
        "objectCode": "dwd_ai_yx_compound_fertilizer_sales_df_demo",
        "objectName": "复合肥销量演示宽表",
        "objectSource": "DYNAMIC_TABLE",
        "properties": [
          { "propertyName": "日期", "propertyCode": "day", "dataType": "STRING", "sourceColumn": "day", "dbId": "86046" }
        ]
      },
      {
        "objectCode": "order_details",
        "objectName": "订单明细表",
        "objectSource": "DYNAMIC_TABLE",
        "properties": [
          { "propertyName": "订单编号", "propertyCode": "order_no", "dataType": "STRING", "sourceColumn": "order_no", "dbId": "86046" }
        ]
      }
      // ... 其他对象省略
    ],
    "actions": [
      {
        "actionCode": "create_by_customer",
        "actionName": "新增客户",
        "actionType": "operation",
        "belongObjectCode": "by_customer",
        "params": [
          { "paramCode": "customerName", "paramName": "客户名称", "paramType": "STRING", "direction": "IN" }
        ],
        "requestUrl": "/api/by/customer/add",
        "requestMethod": "POST"
      }
      // ... 其他动作省略
    ],
    "relations": [
      {
        "relationCode": "rel_LIB_NEW_SALES_object_dwd_ai_yx_compound_fertilizer_sales_df_demo_to_LIB_NEW_SALES_object_order_details",
        "relationName": "复合肥销量关联订单明细",
        "relationCardinality": "N:1",
        "sourceObjectCode": "dwd_ai_yx_compound_fertilizer_sales_df_demo",
        "targetObjectCode": "order_details"
      }
      // ... 其他关系省略
    ],
    "dbsources": {
      "db": [
        { "dbId": "wukong_crm_demo", "dbCode": "wukong_crm_demo", "dbType": "opengauss", "dbParams": {} },
        { "dbId": "86046", "dbCode": "86046", "dbType": "sqlite", "dbParams": {} }
      ],
      "doc": [
        { "docId": "19", "docPath": "/会议纪要" }
      ],
      "api": []
    },
    "version": "v0.0.1"
  }
}
```

### 按视图编码筛选

查询视图 `scene_new_sales_analysis`，自动带出其关联的对象、动作和数据源。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/DtStudio/daiservice/OntologyEntityController/sceneDetails" \
  -d '{
    "sceneId": "2060279899043520523",
    "viewCode": ["scene_new_sales_analysis"],
    "objectCode": []
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "scene": {
      "sceneId": "2064947287571644418",
      "sceneName": "默认场景",
      "sceneCode": "DefaultDemo",
      "sceneDesc": "初始化场景，包含所有对象"
    },
    "views": [
      {
        "viewCode": "scene_new_sales_analysis",
        "viewName": "复合肥销售分析视图",
        "description": "以复合肥销量宽表为主对象，关联订单明细。",
        "objectCodes": ["dwd_ai_yx_compound_fertilizer_sales_df_demo", "order_details"],
        "properties": [
          { "propertyName": "销售日期", "propertyCode": "day", "sourceObject": "dwd_ai_yx_compound_fertilizer_sales_df_demo", "sourceObjectProperty": "day" },
          { "propertyName": "订单编号", "propertyCode": "order_no", "sourceObject": "order_details", "sourceObjectProperty": "order_no" }
        ]
      }
    ],
    "objects": [
      {
        "objectCode": "dwd_ai_yx_compound_fertilizer_sales_df_demo",
        "objectName": "复合肥销量演示宽表",
        "objectSource": "DYNAMIC_TABLE",
        "objectDesc": "复合肥销量分析演示对象。",
        "properties": [
          { "propertyName": "日期", "propertyCode": "day", "dataType": "STRING", "sourceColumn": "day", "dbId": "86046" }
        ]
      },
      {
        "objectCode": "order_details",
        "objectName": "订单明细表",
        "objectSource": "DYNAMIC_TABLE",
        "objectDesc": "订单明细对象。",
        "properties": [
          { "propertyName": "订单编号", "propertyCode": "order_no", "dataType": "STRING", "sourceColumn": "order_no", "dbId": "86046" }
        ]
      }
    ],
    "actions": [],
    "relations": [
      {
        "relationCode": "rel_...",
        "relationName": "复合肥销量关联订单明细",
        "relationCardinality": "N:1",
        "sourceObjectCode": "dwd_ai_yx_compound_fertilizer_sales_df_demo",
        "sourceObjectName": "复合肥销量演示宽表",
        "targetObjectCode": "order_details",
        "targetObjectName": "订单明细表"
      }
    ],
    "dbsources": {
      "db": [{ "dbId": "86046", "dbCode": "86046", "dbType": "sqlite", "dbParams": {} }],
      "doc": [],
      "api": []
    },
    "version": "v0.0.1"
  }
}
```

### 按对象编码筛选

查询对象 `by_customer`，自动带出其动作和所用数据源。`views` 为空。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/DtStudio/daiservice/OntologyEntityController/sceneDetails" \
  -d '{
    "sceneId": "2060279899043520523",
    "viewCode": [],
    "objectCode": ["by_customer"]
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "scene": { "sceneId": "2064947287571644418", "sceneName": "默认场景", "sceneCode": "DefaultDemo" },
    "views": [],
    "objects": [
      {
        "objectCode": "by_customer",
        "objectName": "客户信息表",
        "objectSource": "DB",
        "objectDesc": "CRM 客户主数据对象。",
        "properties": [
          { "propertyName": "主键", "propertyCode": "id", "dataType": "BIGINT", "businessKey": 1, "sourceColumn": "id", "dbId": "wukong_crm_demo" },
          { "propertyName": "客户名称", "propertyCode": "customer_name", "dataType": "STRING", "sourceColumn": "customer_name", "dbId": "wukong_crm_demo" }
        ]
      }
    ],
    "actions": [
      {
        "actionCode": "create_by_customer",
        "actionName": "新增客户",
        "actionType": "operation",
        "belongObjectCode": "by_customer",
        "actionDesc": "新增一条客户记录。",
        "params": [
          { "paramCode": "customerName", "paramName": "客户名称", "paramType": "STRING", "isRequired": 0, "direction": "IN", "mappingPath": "$.requestBody.customerName" }
        ],
        "requestUrl": "/api/by/customer/add",
        "requestMethod": "POST"
      },
      {
        "actionCode": "get_by_customer",
        "actionName": "获取客户详情",
        "actionType": "query",
        "belongObjectCode": "by_customer",
        "params": [
          { "paramCode": "id", "paramName": "主键ID", "paramType": "INTEGER", "isRequired": 0, "direction": "IN", "mappingPath": "$.requestBody.id" }
        ],
        "requestUrl": "/api/by/customer/get",
        "requestMethod": "POST"
      }
    ],
    "relations": [],
    "dbsources": {
      "db": [{ "dbId": "wukong_crm_demo", "dbCode": "wukong_crm_demo", "dbType": "opengauss", "dbParams": {} }],
      "doc": [],
      "api": []
    },
    "version": "v0.0.1"
  }
}
```
