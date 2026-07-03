# 查询术语详情

```
GET /api/v1/knowledge/terms/{termId}
```

根据术语 ID 返回该术语的完整信息：基础属性、所有名称/别名、父术语信息、关联知识。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `termId` | string | 术语 ID，即 `term.term_id`。可通过 `searchTerms` 接口获取。 |

---

## Query Parameters

无。

---

## Request Body

无。

---

## Response Body

```
GetTermDetailResponse
```

### Schema

```json
{
  "code": 200,                       // integer
  "success": true,                   // boolean
  "message": "查询成功",              // string
  "data": {                          // object，失败时为 null
    "termId": "term_customer",       // string。术语 ID
    "termCode": "by_customer",       // string。术语编码
    "termName": "客户",               // string。术语标准名称
    "termTypeCode": "object",        // string。术语类型编码
    "termTypeName": "业务对象",        // string。术语类型翻译名称
    "domainIds": ["domain_crm"],     // string[]。所属领域 ID 列表
    "libraryId": "lib_001",          // string，可选。所属术语库 ID
    "descSummary": "企业客户基本信息对象",  // string，可选。描述摘要（约 100 字）
    "termTags": {                    // object。标签属性
      "source": "crm"
    },
    "extAttrs": {                    // object。自定义扩展属性
      "owner": "team_data"
    },
    "parentTermId": "term_biz_root", // string，可选。父术语 ID
    "parentTermName": "业务对象",      // string，可选。父术语标准名称
    "createdTime": "2026-01-15 10:00:00",  // string。创建时间
    "updatedTime": "2026-06-20 14:30:00",  // string。更新时间
    "names": [                       // object[]。所有名称列表（标准名 + 别名）
      {
        "nameId": "nm_001",          // string。名称 ID
        "nameText": "客户",           // string。名称文本
        "isPrimary": true,           // boolean。是否为标准名称（true=标准名，false=别名）
        "searchScope": {             // object。搜索作用域
          "scope": "global"
        }
      },
      {
        "nameId": "nm_002",
        "nameText": "Customer",
        "isPrimary": false,
        "searchScope": {"scope": "global"}
      }
    ],
    "knowledge": [                   // object[]。关联知识列表
      {
        "knowledgeId": "kb_001",     // string。知识 ID
        "descSummary": "客户主数据管理规范",    // string，可选。知识摘要
        "desc": "完整的客户主数据模型定义...",  // string，可选。知识原文
        "extSystem": null,           // string，可选。外部系统编码（RAGFLOW / DIFY 等）
        "extKbId": null,             // string，可选。外部知识库 ID
        "extDocId": null,            // string，可选。外部文档 ID
        "sortOrder": 0               // integer。展示排序
      }
    ]
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | object | Yes | 业务数据。失败时为 `null`。 |
| `data.termId` | string | Yes | 术语 ID，主键。 |
| `data.termCode` | string | Yes | 术语编码。 |
| `data.termName` | string | Yes | 术语标准名称。 |
| `data.termTypeCode` | string | Yes | 术语类型编码，关联 `term_type` 表。 |
| `data.termTypeName` | string | Yes | 术语类型翻译名称。如 `termTypeCode = "object"` 对应 `termTypeName = "业务对象"`。 |
| `data.domainIds` | string[] | Yes | 所属领域 ID 列表，支持术语多领域归属。 |
| `data.libraryId` | string | No | 所属术语库 ID。 |
| `data.descSummary` | string | No | 术语描述摘要（约 100 字）。完整知识见 `knowledge` 列表。 |
| `data.termTags` | object | Yes | 术语标签属性（JSONB）。 |
| `data.extAttrs` | object | Yes | 自定义扩展属性（JSONB），供业务/产品扩展。 |
| `data.parentTermId` | string | No | 父术语 ID。根术语为空。 |
| `data.parentTermName` | string | No | 父术语标准名称。根术语为空。 |
| `data.createdTime` | string | Yes | 创建时间。格式 `YYYY-MM-DD HH:mm:ss`。 |
| `data.updatedTime` | string | Yes | 更新时间。格式 `YYYY-MM-DD HH:mm:ss`。 |
| `data.names` | object[] | Yes | 术语的所有名称列表，首项为标准名称（`isPrimary = true`），其余为别名。 |
| `data.names[].nameId` | string | Yes | 名称记录 ID。 |
| `data.names[].nameText` | string | Yes | 名称文本。 |
| `data.names[].isPrimary` | boolean | Yes | 是否为标准名称。 |
| `data.names[].searchScope` | object | Yes | 搜索作用域（JSONB）。含 `scope`（`view` / `object` / `global`）和 `code` 等字段。 |
| `data.knowledge` | object[] | Yes | 术语关联知识列表。支持内部落地和外挂知识库两种模式。 |
| `data.knowledge[].knowledgeId` | string | Yes | 知识记录 ID。 |
| `data.knowledge[].descSummary` | string | No | 知识摘要。内部落地模式填写。 |
| `data.knowledge[].desc` | string | No | 知识原文，完整内容。内部落地模式填写。 |
| `data.knowledge[].extSystem` | string | No | 外部系统编码。外挂模式填写。 |
| `data.knowledge[].extKbId` | string | No | 外部知识库 ID。外挂模式填写。 |
| `data.knowledge[].extDocId` | string | No | 外部文档 ID。外挂模式填写。 |
| `data.knowledge[].sortOrder` | integer | Yes | 同术语下多条知识的展示排序，默认 0。 |

### 字段说明

> `names` 列表中，`isPrimary = true` 的记录（有且仅有一条）对应 `term.term_name`，同时也在 `term_name` 表中以 `name_text = term.term_name` 形式存在。其余 `isPrimary = false` 的记录为别名，可通过别名搜索召回。
>
> `knowledge` 支持两种模式：**内部落地**（`descSummary` / `desc` 有值，`extSystem` 为空）— 知识内容存储在库内，支持本地全文检索；**外挂知识库**（`extSystem` + `extKbId` + `extDocId` 有值）— 知识内容由外部系统负责存储和向量检索。

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：{具体原因}` | `termId` 缺失或格式不正确 |
| `404` | 404 | `未查询到术语「{termId}」` | 指定术语不存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库连接失败 |

### Error Example

```json
{
  "code": 404,
  "success": false,
  "message": "未查询到术语「term_nonexist」",
  "data": null
}
```

---

## Example

### 查询单个术语完整详情

#### Request

```bash
curl -X GET \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/terms/term_customer"
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "termId": "term_customer",
    "termCode": "by_customer",
    "termName": "客户",
    "termTypeCode": "object",
    "termTypeName": "业务对象",
    "domainIds": ["domain_crm"],
    "libraryId": "lib_001",
    "descSummary": "企业客户基本信息对象",
    "termTags": {"source": "crm", "level": "core"},
    "extAttrs": {"owner": "team_data"},
    "parentTermId": "term_biz_root",
    "parentTermName": "业务对象",
    "createdTime": "2026-01-15 10:00:00",
    "updatedTime": "2026-06-20 14:30:00",
    "names": [
      {
        "nameId": "nm_001",
        "nameText": "客户",
        "isPrimary": true,
        "searchScope": {"scope": "global"}
      },
      {
        "nameId": "nm_002",
        "nameText": "Customer",
        "isPrimary": false,
        "searchScope": {"scope": "global"}
      },
      {
        "nameId": "nm_003",
        "nameText": "企业客户",
        "isPrimary": false,
        "searchScope": {"scope": "global"}
      }
    ],
    "knowledge": [
      {
        "knowledgeId": "kb_001",
        "descSummary": "客户主数据管理规范",
        "desc": "客户是企业的核心业务对象，包含基本信息（名称、编码、行业、区域）、联系信息、财务信息等。客户数据标准参照 GB/T 36073-2018。",
        "extSystem": null,
        "extKbId": null,
        "extDocId": null,
        "sortOrder": 0
      },
      {
        "knowledgeId": "kb_002",
        "descSummary": null,
        "desc": null,
        "extSystem": "RAGFLOW",
        "extKbId": "kb_crm_docs",
        "extDocId": "doc_2026_customer_guide",
        "sortOrder": 1
      }
    ]
  }
}
```

### 查用户专属术语详情（含 termTypeName）

通过 `searchTerms` 拿到 `termId` 后，逐条查询完整详情，获取类型翻译名称、同义词、标签等完整信息。

#### Request

```bash
curl -X GET \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/terms/1513355147245977600"
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "termId": "1513355147245977600",
    "termCode": "staff001",
    "termName": "张三",
    "termTypeCode": "staffName",
    "termTypeName": "员工姓名",
    "domainIds": [],
    "libraryId": "1512990233355132928",
    "descSummary": null,
    "termTags": {"userId": "user456", "term_binding": "user_name"},
    "extAttrs": {},
    "parentTermId": "staffName",
    "parentTermName": "员工姓名",
    "createdTime": "2026-06-01 08:00:00",
    "updatedTime": "2026-06-15 14:00:00",
    "names": [
      {
        "nameId": "nm_staff001",
        "nameText": "张三",
        "isPrimary": true,
        "searchScope": {"scope": "global"}
      },
      {
        "nameId": "nm_staff001_syn1",
        "nameText": "小张",
        "isPrimary": false,
        "searchScope": {"scope": "global"}
      },
      {
        "nameId": "nm_staff001_syn2",
        "nameText": "张工",
        "isPrimary": false,
        "searchScope": {"scope": "global"}
      }
    ],
    "knowledge": []
  }
}
```
