# View

视图，共享 ObjectSet 概念，由多个对象组合而成的分析视角。

## Properties

| Name | Type | Required | Description |
|---|---|---|---|
| `viewCode` | string | Yes | 视图编码。 |
| `viewName` | string | Yes | 视图名称。 |
| `description` | string | No | 视图描述。 |
| `objectCodes` | string[] | No | 关联的对象编码列表。 |
| `properties` | [ViewProperty](ViewProperty.md)[] | No | 视图属性列表，每个属性含来源对象映射。 |
