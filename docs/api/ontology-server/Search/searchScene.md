# 场景内检索

```
POST /api/v1/ontologyBases/{ownerType}/{baseId}/scenes/{sceneId}/search
```

场景内统一检索，支持全文检索、向量语义检索和混合检索。

- **LOCAL** 时本地执行：元数据检索走知识库 `term_name` 向量索引，实例检索走向量命中 + `searchInstances` 回填。
- **REMOTE** 时等价转发到外部服务。

---

## 与外部协议的关系

同 [ontology-protocol/searchOntology](../../ontology-protocol/OntologySearch/searchOntology.md)，
仅 URL 和参数传递方式不同。

### 参数差异

| 外部 (POST body) | server |
|---|---|
| `sceneId`（body） | Path: `{sceneId}`（server 从路径提取后注入 body 或直接用于本地检索） |

### 请求/响应

完全一致（body 中除 `sceneId` 外的字段和 response 原样透传），见 [ontology-protocol/searchOntology](../../ontology-protocol/OntologySearch/searchOntology.md)。

> `queryType` 枚举值：`vector` / `keyword` / `hybrid`
> `searchScope` 枚举值：`metadata` / `instance` / `all`

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ownerType` | string | personal / enterprise |
| `baseId` | string | 本体库 API 名称。 |
| `sceneId` | string | 场景 ID。LOCAL 时直接用于限定检索范围；REMOTE 时注入 body。 |

## LOCAL 行为说明

LOCAL 场景下，请求由 `OntologySearchEngine` 本地处理，不转发外部服务：

- **元数据检索（`searchScope=metadata|all`）**：对 `term_name.name_embedding` 做向量检索，限定 `term.term_type_code` 为 `object/view/action/prop/func`。
- **实例检索（`searchScope=instance|all`）**：对 `term_name.name_embedding` 做向量检索，限定 `term.term_type_code` 为 cat=1,2 的值类型（如 `city`/`industry`/`customer_name`）。命中值术语后，通过 `term_relation.HAS_TERM` 反向链路找到所属的对象和属性，然后调用 `searchInstances` 回填实例的完整属性行。

> 详细设计见架构文档 [4.14 统一检索等价实现](../../../docs/architecture/ontology-service-mvp.md#414-统一检索searchontology等价实现)。

## Example

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/api/v1/ontologyBases/personal/bio_platform/scenes/2064947287571644418/search" \
  -d '{
    "keyword": "客户",
    "queryType": "hybrid",
    "searchScope": "all",
    "resultPerType": 3
  }'
```
