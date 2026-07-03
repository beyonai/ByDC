# 批量导入术语

```
POST /api/v1/knowledge/terms/import
```

批量新增术语（含同义词、标签、扩展属性）。每条术语独立事务，部分失败不影响其他条目。需要 knowledge 服务鉴权。

---

## Path Parameters

无。

---

## Request Body

```json
{
  "libraryId": "lib_hr",           // string，必填。目标术语库 ID
  "terms": [                        // object[]，必填。待导入术语列表
    {
      "termCode": "user_name",      // string，必填。术语编码
      "termName": "员工姓名",        // string，必填。术语标准名称
      "termType": "prop",           // string，必填。术语类型编码
      "parentTermCode": "by_user",  // string，可选。父术语编码
      "desc": "员工身份证姓名",      // string，可选。术语描述
      "labels": {                   // object，可选。标签映射
        "dataType": "string"
      },
      "extAttrs": {                 // object，可选。扩展属性
        "source": "hr_system"
      },
      "synonyms": ["姓名", "员工名"] // string[]，可选。同义词列表
    }
  ]
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `libraryId` | string | Yes | 目标术语库 ID。 |
| `terms` | object[] | Yes | 待导入术语列表，上限 1000 条。 |
| `terms[].termCode` | string | Yes | 术语编码。同父级下唯一。 |
| `terms[].termName` | string | Yes | 术语标准名称。 |
| `terms[].termType` | string | Yes | 术语类型编码。传 `"-1"` 表示创建术语类型本身。 |
| `terms[].parentTermCode` | string | No | 父术语编码。 |
| `terms[].desc` | string | No | 术语描述。写入 `ext_attrs["desc"]`。 |
| `terms[].labels` | object | No | 标签映射 `{labelTypeCode: labelCode}`。 |
| `terms[].extAttrs` | object | No | 扩展属性。 |
| `terms[].synonyms` | string[] | No | 同义词列表。导入时自动创建 `term_name` 别名记录。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "批量导入完成",
  "data": {
    "created": 8,
    "termIds": [
      "term_user_name_001",
      "term_user_name_002"
    ],
    "errors": [
      "terms[2]: termCode 'user_name' 在该父术语下已存在"
    ]
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data.created` | integer | Yes | 成功创建数。 |
| `data.termIds` | string[] | Yes | 新创建的 `termId` 列表。 |
| `data.errors` | string[] | Yes | 错误信息列表。每次最多返回前 20 条。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：{具体原因}` | `libraryId` 或 `terms` 缺失、`terms` 超过 1000 条上限 |
| `500` | 500 | `系统错误：{原因}` | 数据库写入失败 |

---

## Example

```bash
curl -X POST \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/terms/import" \
  -d '{
    "libraryId": "lib_hr",
    "terms": [
      {
        "termCode": "user_name",
        "termName": "员工姓名",
        "termType": "prop",
        "parentTermCode": "by_user",
        "labels": {"dataType": "string"},
        "synonyms": ["姓名", "员工名"]
      },
      {
        "termCode": "user_age",
        "termName": "员工年龄",
        "termType": "prop",
        "parentTermCode": "by_user",
        "labels": {"dataType": "integer"},
        "synonyms": ["年龄"]
      }
    ]
  }'
```

### 为用户属性设置专属别名

用户 user456 将"销售负责人"映射到标准属性"商机跟进人员名称"。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/terms/import" \
  -d '{
    "libraryId": "1512990233355132928",
    "terms": [
      {
        "termCode": "user456_opportunity_follow_person",
        "termName": "销售负责人",
        "termType": "synonym",
        "parentTermCode": "opportunity_follow_person",
        "labels": {"userId": "user456"},
        "synonyms": ["负责人", "跟进销售"]
      }
    ]
  }'
```

### 为用户值设置专属别名

用户 user456 将"王总"映射到标准值"王为进"。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/terms/import" \
  -d '{
    "libraryId": "1512990233355132928",
    "terms": [
      {
        "termCode": "user456_wang_weijin",
        "termName": "王总",
        "termType": "synonym",
        "parentTermCode": "wang_weijin",
        "labels": {"userId": "user456"},
        "synonyms": ["老王", "王老板"]
      }
    ]
  }'
```

### 字段说明

| 字段 | 含义 |
|------|------|
| `termName` | 用户使用的自定义名称（"销售负责人"、"王总"） |
| `termCode` | 唯一标识，建议 `"{userId}_{标准编码}"` 保证不冲突 |
| `termType` | `"synonym"`，区别于标准术语 |
| `parentTermCode` | 映射到的标准术语编码 |
| `labels.userId` | 归属用户，保证隔离 |
| `synonyms` | 用户为该别名设置的附加同义词列表 |

创建后可通过 `searchTerms` 的 `labelFilters: userId=user456` + `keyword` 查询 → `getTermDetail` 获取详情。示例见 `searchTerms` 接口的「按用户过滤 + 模糊检索」章节。
