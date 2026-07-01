# 查询场景列表

```
GET /api/v1/ontologyBases/{baseId}/scenes
```

按关键词模糊查询场景列表。REMOTE 时转发到外部服务。

---

## 与外部协议的关系

同 [ontology-protocol/queryScenes](../../ontology-protocol/Scene/queryScenes.md)，
仅 URL 和参数传递方式不同。

### 参数差异

| 外部 (POST body) | server (GET query) |
|---|---|
| `queryKeyword` | `queryKeyword`（query param） |

### 请求/响应

完全一致，见 [ontology-protocol/queryScenes](../../ontology-protocol/Scene/queryScenes.md)。

---
## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `baseId` | string | 本体库 API 名称。获取方式见 [listOntologyBases](../OntologyBase/listOntologyBases.md)。 |

## Example

```bash
curl -X GET \
  "https://$HOSTNAME/api/v1/ontologyBases/bio_platform/scenes?queryKeyword=收入"
```
