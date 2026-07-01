# 根据场景查询本体列表

```
GET /api/v1/ontologyBases/{baseId}/scenes/{sceneId}/ontologies
```

按场景 ID 分页查询该场景下的本体列表。`sceneId` 传 `-1` 表示查询所有场景的本体。REMOTE 时转发到外部服务。

---

## 与外部协议的关系

同 [ontology-protocol/queryOntologiesByScene](../../ontology-protocol/Scene/queryOntologiesByScene.md)，
仅 URL 和参数传递方式不同。

### 参数差异

| 外部 (POST body) | server (GET) |
|---|---|
| `sceneId` | Path: `{sceneId}` |
| `queryKeyword` | Query: `queryKeyword` |
| `pageSize` | Query: `pageSize`，默认 `10` |
| `pageIndex` | Query: `pageIndex`，默认 `1` |

### 请求/响应

完全一致，见 [ontology-protocol/queryOntologiesByScene](../../ontology-protocol/Scene/queryOntologiesByScene.md)。

> `data[]` 元素定义见 [OntologySummary](../../ontology-protocol/models/OntologySummary.md)

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `baseId` | string | 本体库 API 名称。获取方式见 [listOntologyBases](../OntologyBase/listOntologyBases.md)。 |
| `sceneId` | string | 场景 ID。`-1` 表示所有场景。获取方式见 [queryScenes](queryScenes.md)。 |

## Example

```bash
curl -X GET \
  "https://$HOSTNAME/api/v1/ontologyBases/bio_platform/scenes/-1/ontologies?pageSize=10"
```
