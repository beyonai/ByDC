# 创建术语类型

```
POST /api/v1/knowledge/termTypes
```

创建术语分类类型。typeCode 全局唯一，isBuiltin 决定是否内置保护。需要 knowledge 服务鉴权。

---

## Path Parameters

无。

---

## Request Body

```json
{
  "typeCode": "view",              // string，必填。类型编码，全局唯一
  "typeName": "视图",               // string，必填。类型名称
  "typeDesc": "数据视图类型",        // string，可选。类型描述
  "typeCategory": 1,               // integer，必填。大分类编号
  "isBuiltin": false               // boolean，可选。是否内置，默认 false
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `typeCode` | string | Yes | 术语类型编码，全局唯一。最长 32 字符。 |
| `typeName` | string | Yes | 术语类型名称。最长 255 字符。 |
| `typeDesc` | string | No | 类型描述。 |
| `typeCategory` | integer | Yes | 大分类编号，用于分类展示。 |
| `isBuiltin` | boolean | No | 是否内置。`true`=系统预置不可删除，`false`=用户自定义。默认 `false`。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "创建成功",
  "data": {
    "typeId": 1,
    "typeCode": "view",
    "typeName": "视图",
    "typeDesc": "数据视图类型",
    "typeCategory": 1,
    "isBuiltin": false,
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 10:00:00"
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data.typeId` | integer | Yes | 自增主键。 |
| `data.typeCode` | string | Yes | 术语类型编码，全局唯一。 |
| `data.typeName` | string | Yes | 术语类型名称。 |
| `data.typeDesc` | string | No | 类型描述。 |
| `data.typeCategory` | integer | Yes | 大分类编号。 |
| `data.isBuiltin` | boolean | Yes | 是否内置。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：{具体原因}` | `typeCode` 或 `typeName` 缺失 |
| `409` | 409 | `术语类型编码「{typeCode}」已存在` | `typeCode` 冲突 |
| `500` | 500 | `系统错误：{原因}` | 数据库写入失败 |

---

## Example

```bash
curl -X POST \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termTypes" \
  -d '{
    "typeCode": "view",
    "typeName": "视图",
    "typeDesc": "数据视图类型",
    "typeCategory": 1,
    "isBuiltin": false
  }'
```
