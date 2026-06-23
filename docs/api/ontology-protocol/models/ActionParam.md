# ActionParam

动作参数定义。

## Properties

| Name | Type | Required | Description |
|---|---|---|---|
| `paramCode` | string | Yes | 参数编码。 |
| `paramName` | string | No | 参数名称。 |
| `paramType` | string | No | 参数类型：`STRING` / `INTEGER` / `ARRAY`。 |
| `isRequired` | integer | No | 是否必填：`1` 必填，`0` 非必填。 |
| `direction` | string | No | 参数方向：`IN` 输入，`OUT` 输出。 |
| `mappingPath` | string | No | JSONPath 映射路径，如 `$.requestBody.xxx` 或 `$.data.xxx`。 |
