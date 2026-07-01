# 更新动作

```
PUT /api/v1/ontologyBases/{baseId}/objects/{objectCode}/actions/{actionCode}
```

全量替换动作定义。仅 LOCAL 可用。请求体同 [createAction](createAction.md)。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `baseId` | string | 本体库 API 名称。 |
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
