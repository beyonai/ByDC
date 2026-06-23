# 删除数据源

```
DELETE /api/v1/ontologyBases/{ownerType}/{baseId}/scenes/{sceneId}/datasources/{dbId}
```

仅 LOCAL 可用。删除前检查是否有对象引用此数据源。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ownerType` | string | personal / enterprise |
| `baseId` | string | 本体库 API 名称。 |
| `sceneId` | string | 场景 ID。 |
| `dbId` | string | 数据源 ID。获取方式见 [listDatasources](listDatasources.md)。 |

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
| `409` | 409 | `数据源被{count}个对象引用，无法删除` | 有对象引用。 |
