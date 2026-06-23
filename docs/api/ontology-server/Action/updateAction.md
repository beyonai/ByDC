# 更新动作

```
PUT /api/v1/ontologyBases/{ownerType}/{baseId}/scenes/{sceneId}/objects/{objectCode}/actions/{actionCode}
```

全量替换动作定义。仅 LOCAL 可用。请求体同 [createAction](createAction.md)。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ownerType` | string | personal / enterprise |
| `baseId` | string | 本体库 API 名称。 |
| `sceneId` | string | 场景 ID。 |
| `objectCode` | string | 对象编码。 |
| `actionCode` | string | 动作编码。必须已存在。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "更新成功",
  "data": {
    "actionCode": "create_by_customer"
  }
}
```
