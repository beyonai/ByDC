# Action

动作，归属于某个对象的操作定义。

## Properties

| Name | Type | Required | Description |
|---|---|---|---|
| `actionCode` | string | Yes | 动作编码。 |
| `actionName` | string | Yes | 动作名称。 |
| `actionType` | string | No | 动作类型：`query` 查询，`operation` 操作。 |
| `belongObjectCode` | string | Yes | 所属对象编码。 |
| `actionDesc` | string | No | 动作描述。 |
| `params` | [ActionParam](ActionParam.md)[] | No | 参数列表。 |
| `requestUrl` | string | No | 实际请求 URL。 |
| `requestMethod` | string | No | 请求方法：`GET` / `POST`。 |
| `script` | string | No | 关联脚本内容。 |
