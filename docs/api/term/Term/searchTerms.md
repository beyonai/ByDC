# 多策略术语检索

```
POST /api/v1/knowledge/terms/search
```

根据关键词、术语名称、类型、标签等多维度条件检索术语，支持精确匹配、BM25 全文检索、向量语义召回三种策略及 RRF 混合融合。需要 knowledge 服务鉴权。

---

## Path Parameters

无。

---

## Query Parameters

无。

---

## Request Body

```
SearchTermsRequest
```

### Schema

```json
{
  "datasetIds": ["ds_001"],          // string[]，可选。术语库 ID 列表，空=不限
  "keyword": "客户",                  // string，可选。模糊匹配 term_name / term_code
  "termName": "员工姓名",             // string，可选。精确匹配 term_name，与 keyword 互斥
  "termType": "view",                // string，可选。术语类型编码，不传=不限类型
  "queryType": "mixed",             // string，可选。检索策略，默认 "fulltext"
  "parentTermCode": "root_001",      // string，可选。父术语编码过滤
  "labelFilters": [                  // object[]，可选。标签过滤条件
    {
      "fieldCode": "status",         // string，必填。标签字段编码（labelTypeCode）
      "filterValue": "active",       // string，可选。等值过滤值
      "minFilterValue": 0,           // integer，可选。范围最小值
      "maxFilterValue": 100          // integer，可选。范围最大值
    }
  ],
  "labelCondition": "and",           // string，可选。多标签组合方式，默认 "and"
  "termIds": ["term_001"],           // string[]，可选。按 ID 精确查询，传入时忽略 keyword/queryType
  "pageSize": 20,                    // integer，可选。每页条数，上限 200，默认 20
  "pageToken": "..."                 // string，可选。分页游标，首次请求留空
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `datasetIds` | string[] | No | 术语库 ID 列表。`[]` 或 `null` = 不限。 |
| `keyword` | string | No | 检索关键词，模糊匹配 `term_name` / `term_code`。与 `termName` 互斥。 |
| `termName` | string | No | 术语名称精确匹配。与 `keyword` 互斥。 |
| `termType` | string | No | 术语类型编码（如 `"view"`、`"object"`、`"prop"`）。不传 = 不限类型。 |
| `queryType` | string | No | 检索策略：`"exact"` 精确匹配 \| `"fulltext"` BM25 全文检索 \| `"embedding"` 向量语义 \| `"mixed"` 混合召回（RRF 融合）。默认 `"fulltext"`。 |
| `parentTermCode` | string | No | 父术语编码（`term_code`），用于限定子术语范围。 |
| `labelFilters` | object[] | No | 标签过滤条件列表。每项含 `fieldCode`（必填）和 `filterValue` / `minFilterValue` / `maxFilterValue`（三选一及以上）。 |
| `labelFilters[].fieldCode` | string | Yes | 标签字段编码。 |
| `labelFilters[].filterValue` | string | No | 等值过滤值。与范围过滤可同时使用。 |
| `labelFilters[].minFilterValue` | integer | No | 范围最小值。 |
| `labelFilters[].maxFilterValue` | integer | No | 范围最大值。 |
| `labelCondition` | string | No | 多标签组合方式：`"and"` 取交集 \| `"or"` 取并集。默认 `"and"`。 |
| `termIds` | string[] | No | 按 ID 列表精确查询。传入时 `keyword` / `queryType` 忽略。 |
| `pageSize` | integer | No | 每页条数。上限 200，默认 20。 |
| `pageToken` | string | No | 分页游标。首次请求留空，后续取响应中 `nextPageToken`。 |

### 字段说明

> `queryType` 枚举值：`"exact"` — 精确匹配 `term_name` / `term_code`；`"fulltext"` — BM25 全文搜索（含单字和 jieba 分词两路）；`"embedding"` — 1024 维向量余弦相似度搜索；`"mixed"` — 全文 + 向量两路召回经 RRF 融合排序。

---

## Response Body

```
SearchTermsResponse
```

### Schema

```json
{
  "code": 200,                       // integer
  "success": true,                   // boolean
  "message": "查询成功",              // string
  "data": {                          // object，失败时为 null
    "terms": [                       // object[]
      {
        "termId": "term_001",        // string。术语 ID
        "termCode": "crm",           // string。术语编码
        "termName": "CRM系统",        // string。术语标准名称
        "termTypeCode": "view",      // string。术语类型编码
        "descSummary": "客户关系管理系统",  // string，可选。描述摘要（约 100 字）
        "termTags": {                // object。标签属性
          "status": "active"
        },
        "createdTime": "2026-01-15 10:00:00",  // string。创建时间
        "updatedTime": "2026-06-20 14:30:00",  // string。更新时间
        "score": 0.95                // float，可选。搜索相关性分数
      }
    ],
    "nextPageToken": "...",          // string，可选。下一页游标，最后一页无此字段
    "totalCount": 42                 // integer。全量总数
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
| `data.terms` | object[] | Yes | 当前页术语列表。 |
| `data.terms[].termId` | string | Yes | 术语 ID，主键。 |
| `data.terms[].termCode` | string | Yes | 术语编码。 |
| `data.terms[].termName` | string | Yes | 术语标准名称。 |
| `data.terms[].termTypeCode` | string | Yes | 术语类型编码，关联 `term_type` 表。 |
| `data.terms[].descSummary` | string | No | 术语描述摘要（约 100 字）。用于列表快速展示。 |
| `data.terms[].termTags` | object | Yes | 术语标签属性（JSONB）。key=标签维度编码，value 为标签值。 |
| `data.terms[].createdTime` | string | Yes | 创建时间。格式 `YYYY-MM-DD HH:mm:ss`。 |
| `data.terms[].updatedTime` | string | Yes | 更新时间。格式 `YYYY-MM-DD HH:mm:ss`。 |
| `data.terms[].score` | float | No | 搜索相关性分数。仅 `fulltext` / `embedding` / `mixed` 策略时有值，精确匹配为 `null`。 |
| `data.nextPageToken` | string | No | 下一页游标。最后一页无此字段。 |
| `data.totalCount` | integer | Yes | 全量命中总数（跨所有页）。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：{具体原因}` | 请求参数缺失、`queryType` 不在枚举范围内、`pageSize` 超出上限 |
| `500` | 500 | `系统错误：{原因}` | 数据库连接失败、索引不可用 |

### Error Example

```json
{
  "code": 400,
  "success": false,
  "message": "参数错误：queryType 仅支持 exact / fulltext / embedding / mixed",
  "data": null
}
```

---

## Example

### 关键词模糊检索

模糊匹配术语名称，返回相关性排序的前 20 条。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer ***" \
  "https://$HOSTNAME/api/v1/knowledge/terms/search" \
  -d '{
    "keyword": "客户",
    "termType": "object",
    "queryType": "fulltext",
    "pageSize": 10
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "terms": [
      {
        "termId": "term_customer",
        "termCode": "by_customer",
        "termName": "客户",
        "termTypeCode": "object",
        "descSummary": "企业客户基本信息对象",
        "termTags": {"source": "crm"},
        "createdTime": "2026-01-15 10:00:00",
        "updatedTime": "2026-06-20 14:30:00",
        "score": 0.98
      },
      {
        "termId": "term_customer_level",
        "termCode": "customer_level",
        "termName": "客户等级",
        "termTypeCode": "prop",
        "descSummary": "客户分级属性",
        "termTags": {"parent_object": "by_customer"},
        "createdTime": "2026-01-18 09:00:00",
        "updatedTime": "2026-03-15 11:00:00",
        "score": 0.72
      }
    ],
    "totalCount": 15
  }
}
```

### 按 ID 精确查询

传入已知 `termIds` 列表精确查询，忽略关键词和检索策略。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer ***" \
  "https://$HOSTNAME/api/v1/knowledge/terms/search" \
  -d '{
    "termIds": ["term_customer", "term_order"],
    "pageSize": 20
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "terms": [
      {
        "termId": "term_customer",
        "termCode": "by_customer",
        "termName": "客户",
        "termTypeCode": "object",
        "descSummary": "企业客户基本信息对象",
        "termTags": {"source": "crm"},
        "createdTime": "2026-01-15 10:00:00",
        "updatedTime": "2026-06-20 14:30:00"
      },
      {
        "termId": "term_order",
        "termCode": "by_order",
        "termName": "订单",
        "termTypeCode": "object",
        "descSummary": "客户订单对象",
        "termTags": {"source": "erp"},
        "createdTime": "2026-02-10 08:30:00",
        "updatedTime": "2026-05-18 16:00:00"
      }
    ],
    "totalCount": 2
  }
}
```

### 向量语义搜索

用自然语言查询语义相近的术语。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer ***" \
  "https://$HOSTNAME/api/v1/knowledge/terms/search" \
  -d '{
    "keyword": "销售收入和利润",
    "queryType": "embedding",
    "pageSize": 5
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "terms": [
      {
        "termId": "term_revenue",
        "termCode": "revenue",
        "termName": "营业收入",
        "termTypeCode": "prop",
        "descSummary": "企业主营业务收入金额",
        "termTags": {},
        "createdTime": "2026-03-01 09:00:00",
        "updatedTime": "2026-03-01 09:00:00",
        "score": 0.91
      },
      {
        "termId": "term_gross_profit",
        "termCode": "gross_profit",
        "termName": "毛利润",
        "termTypeCode": "prop",
        "descSummary": "营业收入减去营业成本",
        "termTags": {},
        "createdTime": "2026-03-01 09:00:00",
        "updatedTime": "2026-03-01 09:00:00",
        "score": 0.85
      }
    ],
    "totalCount": 8
  }
}
```

### 按用户过滤 + 模糊检索

通过 `labelFilters` 限定用户，`keyword` 模糊匹配名称，用于查询某用户专属的术语数据。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/terms/search" \
  -d '{
    "datasetIds": ["1512990233355132928"],
    "keyword": "张三",
    "queryType": "fulltext",
    "labelFilters": [
      {"fieldCode": "userId", "filterValue": "user456"}
    ],
    "labelCondition": "and",
    "pageSize": 20
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "terms": [
      {
        "termId": "1513355147245977600",
        "termCode": "staff001",
        "termName": "张三",
        "termTypeCode": "staffName",
        "descSummary": null,
        "termTags": {"userId": "user456"},
        "createdTime": "2026-06-01 08:00:00",
        "updatedTime": "2026-06-15 14:00:00",
        "score": 0.98
      }
    ],
    "totalCount": 1
  }
}
```
