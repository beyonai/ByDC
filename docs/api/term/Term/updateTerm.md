# 更新术语

```
PUT /api/v1/knowledge/terms/{termId}
```

更新术语。仅更新传入的非空字段，支持字段级部分更新。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `termId` | string | 术语 ID。可通过 `searchTerms` 接口获取。 |

---

## Request Body

```json
{
  "termCode": "employee_name",     // string，可选。新编码
  "termName": "员工标准姓名",        // string，可选。新标准名称
  "descSummary": "员工身份证法定姓名",// string，可选。新描述摘要
  "parentTermId": "term_new_parent",// string，可选。新父术语 ID
  "domainIds": ["domain_hr", "domain_crm"],  // string[]，可选。新领域列表
  "termTypeCode": "prop",          // string，可选。新类型编码
  "termTags": {"dataType": "string", "maxLength": "50"},  // object，可选。新标签
  "extAttrs": {"source": "hr_v2"}   // object，可选。新扩展属性
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `termCode` | string | No | 新术语编码。不传=不修改。 |
| `termName` | string | No | 新标准名称。不传=不修改。 |
| `descSummary` | string | No | 新描述摘要。不传=不修改。 |
| `parentTermId` | string | No | 新父术语 ID。传 `""` 移至根节点。不传=不修改。 |
| `domainIds` | string[] | No | 新领域 ID 列表。不传=不修改。 |
| `termTypeCode` | string | No | 新术语类型编码。不传=不修改。 |
| `termTags` | object | No | 新标签属性。传入时**完全替换**原有标签。不传=不修改。 |
| `extAttrs` | object | No | 新扩展属性。传入时**完全替换**原有属性。不传=不修改。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "更新成功",
  "data": {
    "termId": "term_user_name",
    "termCode": "employee_name",
    "termName": "员工标准姓名",
    "descSummary": "员工身份证法定姓名",
    "parentTermId": null,
    "domainIds": ["domain_hr"],
    "termTypeCode": "prop",
    "termTags": {"dataType": "string"},
    "extAttrs": {"source": "hr_v2"},
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 11:00:00"
  }
}
```

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：{具体原因}` | 新 `termTypeCode` 不存在、新 `parentTermId` 不存在 |
| `404` | 404 | `未查询到术语「{termId}」` | 术语不存在 |
| `409` | 409 | `术语编码「{termCode}」冲突` | 新 `termCode` 在同级中已存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库更新失败 |

---

## Example

```bash
curl -X PUT \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/terms/term_user_name" \
  -d '{
    "termCode": "employee_name",
    "termName": "员工标准姓名",
    "extAttrs": {"source": "hr_v2"}
  }'
```
