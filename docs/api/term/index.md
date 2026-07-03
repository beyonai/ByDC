# API 文档

## Domain（领域）

| API | Method | Path | Description |
|---|---|---|---|
| [listDomains](Domain/listDomains.md) | GET | `/api/v1/knowledge/domains` | 列出领域列表。可按 parentId 过滤子领域，无限层级树形遍历。 |
| [getDomain](Domain/getDomain.md) | GET | `/api/v1/knowledge/domains/{domainId}` | 查询单个领域完整详情，含关联术语库、术语类型及各类型术语数。 |
| [createDomain](Domain/createDomain.md) | POST | `/api/v1/knowledge/domains` | 创建领域，可同时关联归属术语库和术语类型。 |
| [updateDomain](Domain/updateDomain.md) | PUT | `/api/v1/knowledge/domains/{domainId}` | 更新领域元信息及关联库/类型。libraryIds / termTypeCodes 全量替换。 |
| [deleteDomain](Domain/deleteDomain.md) | DELETE | `/api/v1/knowledge/domains/{domainId}` | 删除领域。 |
| [listDomainTermTypes](Domain/listDomainTermTypes.md) | GET | `/api/v1/knowledge/domains/{domainId}/termTypes` | 查询领域下关联的术语类型列表，含各类型术语数。 |

## TermLibrary（术语库）

| API | Method | Path | Description |
|---|---|---|---|
| [listTermLibraries](TermLibrary/listTermLibraries.md) | GET | `/api/v1/knowledge/termLibraries` | 列出术语库列表。可按 libraryCode / libraryName 过滤。 |
| [getTermLibrary](TermLibrary/getTermLibrary.md) | GET | `/api/v1/knowledge/termLibraries/{libraryId}` | 查询单个术语库详情，含术语总数。 |
| [createTermLibrary](TermLibrary/createTermLibrary.md) | POST | `/api/v1/knowledge/termLibraries` | 创建术语库。libraryCode 全局唯一。 |
| [updateTermLibrary](TermLibrary/updateTermLibrary.md) | PUT | `/api/v1/knowledge/termLibraries/{libraryId}` | 更新术语库元信息。 |
| [deleteTermLibrary](TermLibrary/deleteTermLibrary.md) | DELETE | `/api/v1/knowledge/termLibraries/{libraryId}` | 删除术语库。 |
| [listLibraryDomains](TermLibrary/listLibraryDomains.md) | GET | `/api/v1/knowledge/termLibraries/{libraryId}/domains` | 查询术语库覆盖的领域列表。 |

## TermType（术语类型）

| API | Method | Path | Description |
|---|---|---|---|
| [listTermTypes](TermType/listTermTypes.md) | GET | `/api/v1/knowledge/termTypes` | 列出术语类型列表。可按 typeCategory 过滤。 |
| [getTermType](TermType/getTermType.md) | GET | `/api/v1/knowledge/termTypes/{typeCode}` | 查询单个术语类型详情，含术语总数。 |
| [createTermType](TermType/createTermType.md) | POST | `/api/v1/knowledge/termTypes` | 创建术语类型。typeCode 全局唯一。 |
| [updateTermType](TermType/updateTermType.md) | PUT | `/api/v1/knowledge/termTypes/{typeCode}` | 更新术语类型元信息。 |
| [deleteTermType](TermType/deleteTermType.md) | DELETE | `/api/v1/knowledge/termTypes/{typeCode}` | 删除术语类型。isBuiltin=true 内置类型禁止删除。 |

## Term（术语）

| API | Method | Path | Description |
|---|---|---|---|
| [searchTerms](Term/searchTerms.md) | POST | `/api/v1/knowledge/terms/search` | 多策略术语检索：精确 + BM25 + 向量语义召回（RRF 融合），多维度过滤。 |
| [getTermDetail](Term/getTermDetail.md) | GET | `/api/v1/knowledge/terms/{termId}` | 查询单条术语完整详情：基础属性、所有名称/别名、父链、关联知识。 |
| [queryTermRelations](Term/queryTermRelations.md) | GET | `/api/v1/knowledge/terms/{termId}/relations` | 查询术语的关联关系：N 跳进出关系，可按类别/基数过滤。 |
| [createTerm](Term/createTerm.md) | POST | `/api/v1/knowledge/terms` | 创建单条术语。根术语 (libraryId, termTypeCode, termCode) 唯一。 |
| [importTerms](Term/importTerms.md) | POST | `/api/v1/knowledge/terms/import` | 批量导入术语，支持同义词、标签、扩展属性。 |
| [updateTerm](Term/updateTerm.md) | PUT | `/api/v1/knowledge/terms/{termId}` | 更新术语。仅更新非空字段，支持字段级部分更新。 |
| [deleteTerm](Term/deleteTerm.md) | DELETE | `/api/v1/knowledge/terms/{termId}` | 删除术语。 |

## TermRelation（术语关系）

| API | Method | Path | Description |
|---|---|---|---|
| [listTermRelations](TermRelation/listTermRelations.md) | GET | `/api/v1/knowledge/termRelations` | 列出术语关系列表。可按 sourceTermId / targetTermId / relationCategory 过滤。 |
| [getTermRelation](TermRelation/getTermRelation.md) | GET | `/api/v1/knowledge/termRelations/{relationId}` | 查询单个术语关系详情。 |
| [createTermRelation](TermRelation/createTermRelation.md) | POST | `/api/v1/knowledge/termRelations` | 创建术语关系。(sourceTermId, targetTermId, relationName) 唯一。 |
| [updateTermRelation](TermRelation/updateTermRelation.md) | PUT | `/api/v1/knowledge/termRelations/{relationId}` | 更新术语关系。 |
| [deleteTermRelation](TermRelation/deleteTermRelation.md) | DELETE | `/api/v1/knowledge/termRelations/{relationId}` | 删除术语关系。 |

## TermName（术语名称）

| API | Method | Path | Description |
|---|---|---|---|
| [listTermNames](TermName/listTermNames.md) | GET | `/api/v1/knowledge/termNames` | 列出术语名称列表。可按 termId / nameText 过滤。 |
| [getTermName](TermName/getTermName.md) | GET | `/api/v1/knowledge/termNames/{nameId}` | 查询单个名称记录详情。 |
| [createTermName](TermName/createTermName.md) | POST | `/api/v1/knowledge/termNames` | 创建术语别名。(termId, nameText, searchScope) 唯一。 |
| [updateTermName](TermName/updateTermName.md) | PUT | `/api/v1/knowledge/termNames/{nameId}` | 更新术语名称。 |
| [deleteTermName](TermName/deleteTermName.md) | DELETE | `/api/v1/knowledge/termNames/{nameId}` | 删除术语名称。 |

## TermKnowledge（术语知识）

| API | Method | Path | Description |
|---|---|---|---|
| [listTermKnowledges](TermKnowledge/listTermKnowledges.md) | GET | `/api/v1/knowledge/termKnowledges` | 列出术语关联知识列表。可按 termId / extSystem 过滤。 |
| [getTermKnowledge](TermKnowledge/getTermKnowledge.md) | GET | `/api/v1/knowledge/termKnowledges/{knowledgeId}` | 查询单条知识记录详情。 |
| [createTermKnowledge](TermKnowledge/createTermKnowledge.md) | POST | `/api/v1/knowledge/termKnowledges` | 创建术语关联知识。内部落地或外挂知识库两种模式。 |
| [updateTermKnowledge](TermKnowledge/updateTermKnowledge.md) | PUT | `/api/v1/knowledge/termKnowledges/{knowledgeId}` | 更新术语关联知识。 |
| [deleteTermKnowledge](TermKnowledge/deleteTermKnowledge.md) | DELETE | `/api/v1/knowledge/termKnowledges/{knowledgeId}` | 删除术语关联知识。 |
