# 更新关系

```
PUT /api/v1/ontologyBases/{ownerType}/{baseId}/scenes/{sceneId}/relations/{relationCode}
```

全量替换关系定义。仅 LOCAL 可用。请求体同 [createRelation](createRelation.md)。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ownerType` | string | personal / enterprise |
| `baseId` | string | 本体库 API 名称。 |
| `sceneId` | string | 场景 ID。 |
| `relationCode` | string | 关系编码。必须已存在。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "更新成功",
  "data": {
    "relationCode": "rel_customer_orders"
  }
}
```
