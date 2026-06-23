# OntologySummary

本体列表查询中的摘要条目。

## Properties

| Name | Type | Required | Description |
|---|---|---|---|
| `ontologyId` | string | Yes | 本体唯一标识。 |
| `sceneId` | string | Yes | 所属场景 ID。 |
| `ontologyName` | string | Yes | 本体名称。 |
| `ontologyCode` | string | Yes | 本体编码。 |
| `ontologySource` | string | No | 数据来源类型：`db` / `doc` / `api`，可多选以 `/` 分隔。 |
| `ontologyDesc` | string | No | 本体描述。 |
| `conceptType` | string | No | 概念类型：`1` 业务实体/对象实体，`2` 活动实体。 |
| `ontologyType` | string | No | 本体类型。 |
| `domainType` | string | No | 领域类型。 |
