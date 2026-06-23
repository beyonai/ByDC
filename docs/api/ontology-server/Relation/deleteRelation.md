# 删除关系

```
DELETE /api/v1/ontologyBases/{ownerType}/{baseId}/scenes/{sceneId}/relations/{relationCode}
```

删除关系。仅 LOCAL 可用。如有字段引用此关系（`relation_ref`）则拒绝删除。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ownerType` | string | personal / enterprise |
| `baseId` | string | 本体库 API 名称。 |
| `sceneId` | string | 场景 ID。 |
| `relationCode` | string | 关系编码。 |

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
| `403` | 403 | `Remote ontology base is read-only` | REMOTE 写操作。 |
| `409` | 409 | `关系被{count}个字段引用，无法删除` | 有字段引用。 |
