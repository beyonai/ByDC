# 带条件查询实例数据

```
POST /api/v1/ontologyBases/{ownerType}/{baseId}/instances/search
```

根据对象类型和查询条件检索实例数据，返回匹配的对象列表。REMOTE 时转发到外部服务。

---

## 与外部协议的关系

同 [ontology-protocol/searchInstances](../../ontology-protocol/Instance/searchInstances.md)，
仅多了 Path 层级。

### 参数差异

| 外部 | server |
|---|---|
| Path: 无 | Path: `{ownerType}`, `{baseId}` |

### 请求/响应

完全一致（body 和 response 原样透传），见 [ontology-protocol/searchInstances](../../ontology-protocol/Instance/searchInstances.md)。

> `where` 操作符定义见 [QueryOperators](../../ontology-protocol/models/QueryOperators.md)
> `data` 中各属性字段定义见 [Property](../../ontology-protocol/models/Property.md)

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ownerType` | string | personal / enterprise |
| `baseId` | string | 本体库 API 名称。 |

## Example

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/api/v1/ontologyBases/personal/bio_platform/instances/search" \
  -d '{
    "objectCode": "by_customer",
    "select": ["customer_code", "customer_name"],
    "where": {
      "type": "and",
      "value": [
        {"type": "eq", "field": "industry", "value": "金融"},
        {"type": "in", "field": "province", "value": ["北京", "上海"]}
      ]
    }
  }'
```
