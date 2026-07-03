# 创建术语

```
POST /api/v1/knowledge/terms
```

创建单条术语。根术语 (libraryId, termTypeCode, termCode) 唯一，子术语 (parentTermId, termCode) 唯一。需要 knowledge 服务鉴权。

---

## Path Parameters

无。

---

## Request Body

```
CreateTermRequest
```

### Schema

```json
{
  "termId": "term_user_name",      // string，可选。术语 ID，不传则自动生成
  "termCode": "user_name",         // string，必填。术语编码
  "termName": "员工姓名",           // string，必填。术语标准名称
  "descSummary": "员工身份证姓名",   // string，可选。描述摘要（约 100 字）
  "parentTermId": "term_user",     // string，可选。父术语 ID
  "domainIds": ["domain_hr"],      // string[]，可选。所属领域 ID 列表
  "termTypeCode": "prop",          // string，必填。术语类型编码
  "libraryId": "lib_hr",           // string，可选。所属术语库 ID
  "termTags": {                    // object，可选。标签属性
    "dataType": "string"
  },
  "extAttrs": {                    // object，可选。自定义扩展属性
    "source": "hr_system"
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `termId` | string | No | 术语 ID。不传时服务端雪花算法自动生成。 |
| `termCode` | string | Yes | 术语编码。根术语：同 libraryId + termTypeCode 下唯一；子术语：同 parentTermId 下唯一。 |
| `termName` | string | Yes | 术语标准名称，全局唯一规范名。最长 255 字符。 |
| `descSummary` | string | No | 描述摘要（约 100 字）。完整知识通过 `createTermKnowledge` 接口补充。 |
| `parentTermId` | string | No | 父术语 ID。不传=根术语。 |
| `domainIds` | string[] | No | 所属领域 ID 数组，支持多领域归属。默认 `[]`。 |
| `termTypeCode` | string | Yes | 术语类型编码，外键关联 `term_type` 表。 |
| `libraryId` | string | No | 所属术语库 ID。 |
| `termTags` | object | No | 标签属性（JSONB）。key=标签维度编码，value=标签值。默认 `{}`。 |
| `extAttrs` | object | No | 自定义扩展属性（JSONB）。默认 `{}`。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "创建成功",
  "data": {
    "termId": "term_user_name",
    "termCode": "user_name",
    "termName": "员工姓名",
    "descSummary": "员工身份证姓名",
    "parentTermId": "term_user",
    "domainIds": ["domain_hr"],
    "termTypeCode": "prop",
    "libraryId": "lib_hr",
    "termTags": {"dataType": "string"},
    "extAttrs": {"source": "hr_system"},
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 10:00:00"
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data.termId` | string | Yes | 术语 ID，主键。 |
| `data.termCode` | string | Yes | 术语编码。 |
| `data.termName` | string | Yes | 术语标准名称。 |
| `data.descSummary` | string | No | 描述摘要。 |
| `data.parentTermId` | string | No | 父术语 ID。 |
| `data.domainIds` | string[] | Yes | 所属领域 ID 列表。 |
| `data.termTypeCode` | string | Yes | 术语类型编码。 |
| `data.libraryId` | string | No | 所属术语库 ID。 |
| `data.termTags` | object | Yes | 标签属性。 |
| `data.extAttrs` | object | Yes | 扩展属性。 |
| `data.createdTime` | string | Yes | 创建时间。 |
| `data.updatedTime` | string | Yes | 更新时间。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：{具体原因}` | `termCode` 或 `termName` 或 `termTypeCode` 缺失、`termTypeCode` 不存在 |
| `409` | 409 | `术语编码「{termCode}」在该父术语下已存在` | 同父级下 `termCode` 重复 |
| `409` | 409 | `术语名称「{termName}」已存在` | `termName` 全局唯一冲突 |
| `500` | 500 | `系统错误：{原因}` | 数据库写入失败 |

---

## Example

### 创建根术语

```bash
curl -X POST \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/terms" \
  -d '{
    "termCode": "by_user",
    "termName": "用户",
    "termTypeCode": "object",
    "libraryId": "lib_hr",
    "domainIds": ["domain_hr"],
    "descSummary": "系统用户对象"
  }'
```

### 创建子术语（属性）

```bash
curl -X POST \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/terms" \
  -d '{
    "termCode": "user_name",
    "termName": "员工姓名",
    "termTypeCode": "prop",
    "parentTermId": "term_by_user",
    "descSummary": "员工身份证姓名"
  }'
```
