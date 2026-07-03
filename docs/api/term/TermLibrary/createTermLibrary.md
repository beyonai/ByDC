# 创建术语库

```
POST /api/v1/knowledge/termLibraries
```

创建术语库，管理术语来源渠道。libraryCode 全局唯一。需要 knowledge 服务鉴权。

---

## Path Parameters

无。

---

## Query Parameters

无。

---

## Request Body

```
CreateTermLibraryRequest
```

### Schema

```json
{
  "libraryId": "lib_hr",           // string，可选。术语库 ID，不传则自动生成
  "libraryCode": "HR_SYSTEM",       // string，必填。术语库编码，全局唯一
  "libraryName": "HR系统术语库"      // string，必填。术语库名称
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `libraryId` | string | No | 术语库 ID。不传时服务端雪花算法自动生成。 |
| `libraryCode` | string | Yes | 术语库编码，全局唯一。最长 32 字符。 |
| `libraryName` | string | Yes | 术语库名称，如 "HR系统术语库"。最长 255 字符。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "创建成功",
  "data": {
    "libraryId": "lib_hr",
    "libraryCode": "HR_SYSTEM",
    "libraryName": "HR系统术语库",
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 10:00:00"
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data.libraryId` | string | Yes | 术语库 ID，主键。 |
| `data.libraryCode` | string | Yes | 术语库编码，全局唯一。 |
| `data.libraryName` | string | Yes | 术语库名称。 |
| `data.createdTime` | string | Yes | 创建时间。 |
| `data.updatedTime` | string | Yes | 更新时间。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：{具体原因}` | `libraryCode` 或 `libraryName` 缺失 |
| `409` | 409 | `术语库编码「{libraryCode}」已存在` | `libraryCode` 冲突 |
| `500` | 500 | `系统错误：{原因}` | 数据库写入失败 |

---

## Example

```bash
curl -X POST \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termLibraries" \
  -d '{
    "libraryCode": "HR_SYSTEM",
    "libraryName": "HR系统术语库"
  }'
```
