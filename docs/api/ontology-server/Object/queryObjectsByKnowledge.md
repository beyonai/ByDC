# 按知识库查询对象列表

```text
POST /api/v1/ontologyBases/objects/queryByKnowledge
```

根据知识库资源 ID 分页查询对象基本信息，可选按知识库目录列表和对象名称进一步过滤。返回结果不包含对象的 `properties` 和 `actions`。

接口固定查询 `constants.py` 中 `DEFAULT_BASE_ID` 对应的本体库，不接收 `baseId` 查询条件。每条结果通过 `baseId` 返回实际使用的默认本体库 ID。

---

## Request Body

```json
{
  "kbResourceId": "10000765",
  "kbDirectories": ["/Product", "/Ability"],
  "objectName": "产品",
  "pageIndex": 1,
  "pageSize": 20
}
```

### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `kbResourceId` | string | Yes | — | 知识库资源 ID，去除首尾空白后精确匹配。 |
| `kbDirectories` | array[string] | No | `[]` | 知识库目录路径列表。非空时匹配任一目录；未传、空数组或仅含空白项时不限制目录。重复项会被去除。 |
| `objectName` | string | No | — | 对象名称，不区分大小写的包含匹配；空白值不参与过滤。 |
| `pageIndex` | integer | No | `1` | 页码，从 1 开始。 |
| `pageSize` | integer | No | `20` | 每页数量，范围 1–1000。 |

`kbResourceId`、`kbDirectories` 和 `objectName` 之间使用 AND 语义；`kbDirectories` 内部使用 OR 语义。目录采用完整路径精确匹配，不执行前缀或递归匹配。

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "ok",
  "data": {
    "items": [
      {
        "objectCode": "product",
        "objectName": "产品",
        "objectDesc": "产品对象",
        "objectSource": "KNOWLEDGE_BASE",
        "fieldCount": 6,
        "actionCount": 0,
        "ownerType": "enterprise",
        "userCode": null,
        "baseId": "BYCLAW_DATACLOUD",
        "kbResourceId": "10000765",
        "kbDirectory": "/Product"
      }
    ],
    "total": 1,
    "pageIndex": 1,
    "pageSize": 20,
    "totalPages": 1
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data.items` | array | Yes | 当前页对象基本信息，不包含 `properties` 和 `actions`。 |
| `data.items[].baseId` | string | Yes | 本次查询使用的本体库 ID。 |
| `data.items[].kbResourceId` | string | Yes | 对象关联的知识库资源 ID。 |
| `data.items[].kbDirectory` | string | Yes | 对象关联的知识库目录。 |
| `data.total` | integer | Yes | 应用全部过滤条件后、分页前的对象总数。 |
| `data.pageIndex` | integer | Yes | 当前页码。 |
| `data.pageSize` | integer | Yes | 当前每页数量。 |
| `data.totalPages` | integer | Yes | 总页数，按 `ceil(total / pageSize)` 计算；无数据时为 0。 |

---

## Errors

| HTTP Status | Condition |
|---|---|
| `422` | 缺少 `kbResourceId`、资源 ID 为空白、`pageIndex < 1`，或 `pageSize` 不在 1–1000。 |
| `404` | 指定的 `baseId` 未注册。 |

---

## Example

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  "https://$HOSTNAME/api/v1/ontologyBases/objects/queryByKnowledge" \
  -d '{
    "kbResourceId": "10000765",
    "kbDirectories": [],
    "objectName": "产品",
    "pageIndex": 1,
    "pageSize": 20
  }'
```
