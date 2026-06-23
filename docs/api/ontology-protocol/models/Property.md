# Property

本体对象的属性/字段定义。

## Properties

| Name | Type | Required | Description |
|---|---|---|---|
| `propertyName` | string | Yes | 属性名称（中文）。 |
| `propertyCode` | string | Yes | 属性编码（字段名）。 |
| `propertyDesc` | string | No | 属性描述。 |
| `dataType` | string | No | 数据类型：`STRING` / `BIGINT` / `INTEGER` / `DOUBLE` / `BOOLEAN` / `DATE`。 |
| `dataFormat` | string | No | 数据格式，日期类为 `yyyy-MM-dd HH:mm:ss` 或 `yyyy-MM-dd`。 |
| `isRequired` | integer | No | 是否必填：`1` 必填，`0` 非必填。 |
| `isInstantiation` | integer | No | 是否为实例化属性：`1` 是，`0` 否。 |
| `isName` | integer | No | 是否为名称属性：`1` 是，`0` 否。 |
| `businessDefinition` | string | No | 业务定义。 |
| `technicalDefinition` | string | No | 技术定义。 |
| `terminology` | [TermMeta](#TermMeta) | No | 术语绑定。仅保留 `termMasterType` / `termTypeCode` / `termField` 三个字段。 |
| `synonyms` | string | No | 同义词。 |
| `propertyType` | string | No | 属性类型。 |
| `propertyTypeCode` | string | No | 属性类型编码。 |
| `propertySubType` | string | No | 属性子类型。 |
| `propertySubTypeCode` | string | No | 属性子类型编码。 |
| `businessKey` | integer | No | 是否为业务主键：`1` 是，`0` 否。 |
| `sortNo` | integer | No | 排序号。 |
| `status` | integer | No | 状态：`1` 启用，`0` 停用。 |
| `dbId` | string | No | 数据源 DB ID，关联 [Dbsource](Dbsource.md)。 |
| `columnId` | string | No | 列 ID。 |
| `sourceColumn` | string | No | 源数据列名。 |
| `apiId` | string | No | API 源 ID。 |
| `apiSource` | string | No | API 数据路径。 |
| `docId` | string | No | 文档源 ID。 |

## TermMeta

| Name | Type | Required | Description |
|---|---|---|---|
| `termMasterType` | string | Yes | 术语主类型：`dict`（字典）、`list`（列表）。 |
| `termTypeCode` | string | Yes | 术语类型编码。 |
| `termField` | string | Yes | 术语取值字段：`code` 或 `name`。 |
