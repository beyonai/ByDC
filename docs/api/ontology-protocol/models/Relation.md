# Relation

关系，两个本体对象之间的关联定义。

## Properties

| Name | Type | Required | Description |
|---|---|---|---|
| `objectRelationId` | string | No | 关系唯一标识。 |
| `relationCode` | string | Yes | 关系编码。 |
| `relationName` | string | No | 关系名称。 |
| `relationSceneType` | string | No | 关系场景类型：`entity` 实体关系。 |
| `relationCardinality` | string | No | 基数：`1:1` / `1:N` / `N:1` / `N:M`。 |
| `relationDesc` | string | No | 关系描述。 |
| `sourceObjectCode` | string | Yes | 源对象编码。 |
| `sourceObjectName` | string | No | 源对象名称。 |
| `targetObjectCode` | string | Yes | 目标对象编码。 |
| `targetObjectName` | string | No | 目标对象名称。 |
| `srcMetaId` | string | No | 源元数据 ID。 |
| `srcColumnId` | string | No | 源列 ID。 |
| `targetMetaId` | string | No | 目标元数据 ID。 |
| `targetColumnId` | string | No | 目标列 ID。 |
| `attribute` | object | No | 附加属性，含源端/目标端的列映射详情。 |
| `sortNo` | integer | No | 排序号。 |
| `status` | integer | No | 状态：`1` 启用，`0` 停用。 |
