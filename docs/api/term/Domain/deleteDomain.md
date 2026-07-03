# 删除领域

```
DELETE /api/v1/knowledge/domains/{domainId}
```

删除指定领域。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `domainId` | string | 领域 ID。可通过 `listDomains` 接口获取。 |

---

## Query Parameters

无。

---

## Request Body

无。

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "删除成功",
  "data": null
}
```

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `404` | 404 | `未查询到领域「{domainId}」` | 领域不存在 |
| `409` | 409 | `领域「{domainId}」存在子领域，无法删除` | 领域下有子领域时拒绝删除 |
| `500` | 500 | `系统错误：{原因}` | 数据库删除失败 |

---

## Example

```bash
curl -X DELETE \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/domains/domain_crm"
```
