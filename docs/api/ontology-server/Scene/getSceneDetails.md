# 查询场景详情

```
GET /api/v1/ontologyBases/{baseId}/scenes/{sceneId}
```

查询场景完整本体详情，返回该场景下对象、视图、动作、关系、数据源。支持按视图编码或对象编码筛选。

---

## 与外部协议的关系

同 [ontology-protocol/getSceneDetails](../../ontology-protocol/Scene/getSceneDetails.md)，
仅 URL 和参数传递方式不同。

### 参数差异

| 外部 (POST body) | server (GET) |
|---|---|
| `sceneId` | Path: `{sceneId}` |
| `viewCode[]` | Query: `viewCode`（逗号分隔多个） |
| `objectCode[]` | Query: `objectCode`（逗号分隔多个） |

### 请求/响应

完全一致，见 [ontology-protocol/getSceneDetails](../../ontology-protocol/Scene/getSceneDetails.md)。

> 数据模型引用：[Scene](../../ontology-protocol/models/Scene.md) · [View](../../ontology-protocol/models/View.md) · [Object](../../ontology-protocol/models/Object.md) · [Property](../../ontology-protocol/models/Property.md) · [Action](../../ontology-protocol/models/Action.md) · [Relation](../../ontology-protocol/models/Relation.md) · [Dbsource](../../ontology-protocol/models/Dbsource.md)

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `baseId` | string | 本体库 API 名称。获取方式见 [listOntologyBases](../OntologyBase/listOntologyBases.md)。 |
| `sceneId` | string | 场景 ID。获取方式见 [queryScenes](queryScenes.md)。 |

## Example

```bash
curl -X GET \
  "https://$HOSTNAME/api/v1/ontologyBases/bio_platform/scenes/2064947287571644418"
```
