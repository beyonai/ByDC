# 获取对象详情

```
GET /api/v1/ontologyBases/{ownerType}/{baseId}/objects/{objectCode}
```

获取对象类型完整定义，含属性列表和动作列表。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ownerType` | string | personal / enterprise |
| `baseId` | string | 本体库 API 名称。获取方式见 [listOntologyBases](../OntologyBase/listOntologyBases.md)。 |
| `objectCode` | string | 对象编码。获取方式见 [listObjects](listObjects.md)。 |

---

## Query Parameters

无

---

## Request Body

无

---

## Response Body

```
GetObjectResponse
```

### Schema

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "objectCode": "by_customer",
    "objectName": "客户信息表",
    "objectSource": "DB",
    "objectDesc": "CRM 客户主数据对象。",
    "conceptType": "1",
    "properties": [
      {
        "propertyCode": "id",
        "propertyName": "主键",
        "dataType": "BIGINT",
        "isRequired": 1,
        "businessKey": 1,
        "sourceColumn": "id",
        "dbId": "wukong_crm_demo"
      },
      {
        "propertyCode": "customer_name",
        "propertyName": "客户名称",
        "dataType": "STRING",
        "isRequired": 1,
        "sourceColumn": "customer_name",
        "dbId": "wukong_crm_demo",
        "terminology": {
          "termMasterType": "dict",
          "termTypeCode": "customer_name",
          "termField": "name"
        }
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
          {
            "paramCode": "customerName",
            "paramName": "客户名称",
            "paramType": "STRING",
            "isRequired": 0,
            "direction": "IN",
            "mappingPath": "$.requestBody.customerName"
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
| `data` | object | Yes | 对象完整定义。失败时为 `null`。 |
| `data.objectCode` | string | Yes | 对象编码。 |
| `data.objectName` | string | Yes | 对象名称。 |
| `data.objectSource` | string | No | 数据来源。 |
| `data.objectDesc` | string | No | 对象描述。 |
| `data.conceptType` | string | No | 概念类型。 |
| `data.properties` | array | No | 属性列表。 |
| `data.actions` | array | No | 动作列表。 |

> `data.properties` 元素定义见 [Property](../../ontology-protocol/models/Property.md)
> `data.actions` 元素定义见 [Action](../../ontology-protocol/models/Action.md)

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `404` | 404 | `本体库「{baseId}」不存在` | 指定本体库未注册。 |
| `404` | 404 | `未查询到对象类型「{objectCode}」` | 指定对象不存在。 |
| `500` | 500 | `系统错误：{原因}` | 服务端异常。 |

### Error Example

```json
{
  "code": 404,
  "success": false,
  "message": "未查询到对象类型「unknown」",
  "data": null
}
```

---

## Example

### 获取对象详情

#### Request

```bash
curl -X GET \
  "https://$HOSTNAME/api/v1/ontologyBases/personal/crm_demo/objects/by_customer"
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "objectCode": "by_customer",
    "objectName": "客户信息表",
    "objectSource": "DB",
    "objectDesc": "CRM 客户主数据对象。",
    "conceptType": "1",
    "properties": [
      {
        "propertyCode": "id",
        "propertyName": "主键",
        "dataType": "BIGINT",
        "businessKey": 1,
        "sourceColumn": "id",
        "dbId": "wukong_crm_demo"
      }
    ],
    "actions": [
      {
        "actionCode": "get_by_customer",
        "actionName": "获取客户详情",
        "actionType": "query",
        "belongObjectCode": "by_customer",
        "params": [
          {
            "paramCode": "customerCode",
            "paramName": "客户编码",
            "paramType": "STRING",
            "direction": "IN"
          }
        ]
      }
    ]
  }
}
```
