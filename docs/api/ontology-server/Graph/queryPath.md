# 查询路径

```
POST /api/v1/ontologyBases/{baseId}/scenes/{sceneId}/graph/path
```

根据起点和终点查询两个节点之间的路径，返回路径节点序列及关系序列。REMOTE 时转发到外部服务。

---

## 与外部协议的关系

同 [ontology-protocol/queryPath](../../ontology-protocol/Graph/queryPath.md)，
仅 URL 和参数传递方式不同。

### 参数差异

| 外部 (POST body) | server |
|---|---|
| `sceneId` | Path: `{sceneId}`（proxy 注入 body） |

### 请求/响应

完全一致（body 中除 `sceneId` 外的字段和 response 原样透传），见 [ontology-protocol/queryPath](../../ontology-protocol/Graph/queryPath.md)。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `baseId` | string | 本体库 API 名称。 |
| `sceneId` | string | 场景 ID。转发时注入 body。 |

## Example

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/api/v1/ontologyBases/bio_platform/scenes/2064947287571644418/graph/path" \
  -d '{
    "matchBy": "name",
    "startNode": "北京市石景山区",
    "endNode": "",
    "direction": "forward"
  }'
```
