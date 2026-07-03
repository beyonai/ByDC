# 创建术语名称

```
POST /api/v1/knowledge/termNames
```

为术语创建别名或标准名称记录。`(termId, nameText, searchScope)` 三者组合唯一。需要 knowledge 服务鉴权。

---

## Path Parameters

无。

---

## Request Body

```json
{
  "nameId": "nm_customer_en",      // string，可选。名称 ID，不传则自动生成
  "termId": "term_customer",       // string，必填。归属术语 ID
  "nameText": "Customer",          // string，必填。名称文本
  "searchScope": {                 // object，可选。搜索作用域
    "scope": "global"
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `nameId` | string | No | 名称 ID。不传时服务端雪花算法自动生成。 |
| `termId` | string | Yes | 归属术语 ID。若 `nameText = term.term_name` 则为标准名称，否则为别名。 |
| `nameText` | string | Yes | 名称文本。最长 255 字符。 |
| `searchScope` | object | No | 搜索作用域（JSONB）。`{"scope":"global"}` 全局可见；`{"scope":"view","code":"v_xxx"}` 限定视图；`{"scope":"object","code":"obj_xxx"}` 限定对象。默认 `{}`。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "创建成功",
  "data": {
    "nameId": "nm_customer_en",
    "termId": "term_customer",
    "nameText": "Customer",
    "searchScope": {"scope": "global"},
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 10:00:00"
  }
}
```

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：{具体原因}` | `termId` 或 `nameText` 缺失；`termId` 不存在 |
| `409` | 409 | `术语名称「{nameText}」在该作用域下已存在` | 同 termId + nameText + searchScope 已存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库写入失败 |

---

## Example

### 创建全局别名

```bash
curl -X POST \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termNames" \
  -d '{
    "termId": "term_customer",
    "nameText": "Customer",
    "searchScope": {"scope": "global"}
  }'
```

### 创建视图作用域别名

```bash
curl -X POST \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termNames" \
  -d '{
    "termId": "prop_revenue",
    "nameText": "销售额",
    "searchScope": {"scope": "view", "code": "v_sales_report"}
  }'
```
