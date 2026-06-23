# 查询图节点及关系

```
POST /api/v1/ontologyBases/{ownerType}/{baseId}/scenes/{sceneId}/graph/query
```

按节点编码或名称查询指定跳数范围内的图节点及关系。REMOTE 时转发到外部服务。

---

## 与外部协议的关系

同 [ontology-protocol/queryGraphByNode](../../ontology-protocol/Graph/queryGraphByNode.md)，
仅 URL 和参数传递方式不同。

### 参数差异

| 外部 (POST body) | server |
|---|---|
| `sceneId` | Path: `{sceneId}`（proxy 注入 body） |

### 请求/响应

完全一致（body 中除 `sceneId` 外的字段和 response 原样透传），见 [ontology-protocol/queryGraphByNode](../../ontology-protocol/Graph/queryGraphByNode.md)。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ownerType` | string | personal / enterprise |
| `baseId` | string | 本体库 API 名称。 |
| `sceneId` | string | 场景 ID。转发时注入 body。 |

## Example

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/api/v1/ontologyBases/personal/bio_platform/scenes/2064947287571644418/graph/query" \
  -d '{
    "objectCode": ["ontoDimRegion"],
    "matchBy": "name",
    "values": ["北京市石景山区"],
    "step": 1
  }'
```
