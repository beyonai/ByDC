# 更新视图

```
PUT /api/v1/ontologyBases/{baseId}/views/{viewCode}
```

全量替换视图定义。仅 LOCAL 可用。请求体同 [createView](createView.md)。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `baseId` | string | 本体库 API 名称。 |
| `viewCode` | string | 视图编码。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "更新成功",
  "data": {
    "viewCode": "customer_analysis"
  }
}
```
