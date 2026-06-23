# Object

本体对象，映射物理数据源（表/接口/文档）的逻辑实体。

## Properties

| Name | Type | Required | Description |
|---|---|---|---|
| `objectId` | string | No | 对象唯一标识。 |
| `objectCode` | string | Yes | 对象编码。 |
| `objectName` | string | Yes | 对象名称。 |
| `objectSource` | string | No | 数据来源类型：`DB` / `DYNAMIC_TABLE` / `KNOWLEDGE_BASE`。 |
| `objectDesc` | string | No | 对象描述。 |
| `conceptType` | string | No | 概念类型：`1` 业务实体/对象实体，`2` 活动实体。 |
| `objectType` | string | No | 对象类型。 |
| `domainType` | string | No | 领域类型。 |
| `sceneId` | string | No | 所属场景 ID。 |
| `properties` | [Property](Property.md)[] | No | 属性列表。 |
