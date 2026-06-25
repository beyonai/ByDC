# 删除动作

```
DELETE /api/v1/ontologyBases/{ownerType}/{baseId}/objects/{objectCode}/actions/{actionCode}
```

仅 LOCAL 可用。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ownerType` | string | personal / enterprise |
| `baseId` | string | 本体库 API 名称。 |
| `objectCode` | string | 对象编码。 |
| `actionCode` | string | 动作编码。 |

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
