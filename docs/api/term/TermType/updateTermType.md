# 更新术语类型

```
PUT /api/v1/knowledge/termTypes/{typeCode}
```

更新术语类型元信息。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `typeCode` | string | 类型编码。可通过 `listTermTypes` 接口获取。 |

---

## Request Body

```json
{
  "typeName": "数据视图",
  "typeDesc": "更新后的描述",
  "typeCategory": 2
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `typeName` | string | No | 类型名称。不传=不修改。 |
| `typeDesc` | string | No | 类型描述。不传=不修改。 |
| `typeCategory` | integer | No | 大分类编号。不传=不修改。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "更新成功",
  "data": {
    "typeId": 1,
    "typeCode": "view",
    "typeName": "数据视图",
    "typeDesc": "更新后的描述",
    "typeCategory": 2,
    "isBuiltin": true,
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 11:00:00"
  }
}
```

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `404` | 404 | `未查询到术语类型「{typeCode}」` | 类型不存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库更新失败 |

---

## Example

```bash
curl -X PUT \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termTypes/view" \
  -d '{"typeName": "数据视图", "typeDesc": "更新后的描述"}'
```
