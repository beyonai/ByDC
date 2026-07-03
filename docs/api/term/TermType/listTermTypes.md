# 列出术语类型

```
GET /api/v1/knowledge/termTypes
```

分页列出术语类型列表。支持按 typeCategory 大分类过滤。需要 knowledge 服务鉴权。

---

## Path Parameters

无。

---

## Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `typeCategory` | integer | No | — | 大分类编号过滤。 |
| `pageSize` | integer | No | 20 | 每页条数。上限 100。 |
| `pageToken` | string | No | — | 分页游标。首次请求留空，后续取响应中 `nextPageToken`。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "termTypes": [
      {
        "typeId": 1,
        "typeCode": "view",
        "typeName": "视图",
        "typeDesc": "数据视图类型",
        "typeCategory": 1,
        "isBuiltin": true,
        "createdTime": "2026-07-02 10:00:00",
        "updatedTime": "2026-07-02 10:00:00"
      }
    ],
    "nextPageToken": "...",
    "totalCount": 8
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data.termTypes[].typeId` | integer | Yes | 自增主键。 |
| `data.termTypes[].typeCode` | string | Yes | 类型编码。 |
| `data.termTypes[].typeName` | string | Yes | 类型名称。 |
| `data.termTypes[].typeDesc` | string | No | 类型描述。 |
| `data.termTypes[].typeCategory` | integer | Yes | 大分类编号。 |
| `data.termTypes[].isBuiltin` | boolean | Yes | 是否内置。 |
| `data.termTypes[].createdTime` | string | Yes | 创建时间。 |
| `data.termTypes[].updatedTime` | string | Yes | 更新时间。 |
| `data.nextPageToken` | string | No | 下一页游标。 |
| `data.totalCount` | integer | Yes | 全量总数。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `500` | 500 | `系统错误：{原因}` | 数据库查询失败 |

---

## Example

```bash
curl -X GET \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termTypes?typeCategory=1&pageSize=10"
```
