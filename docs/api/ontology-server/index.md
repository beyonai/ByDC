# API 文档

## OntologyBase（本体库）

| API | Method | Path | Description |
|---|---|---|---|
| [listOntologyBases](OntologyBase/listOntologyBases.md) | GET | `/api/v1/ontologyBases` | 列出所有本体库。 |
| [createOntologyBase](OntologyBase/createOntologyBase.md) | POST | `/api/v1/ontologyBases` | 创建本体库。baseId 可选，不传时雪花算法自动生成。 |
| [updateOntologyBase](OntologyBase/updateOntologyBase.md) | PUT | `/api/v1/ontologyBases/{ownerType}/{baseId}` | 更新本体库元信息。所有字段可选。 |
| [deleteOntologyBase](OntologyBase/deleteOntologyBase.md) | DELETE | `/api/v1/ontologyBases/{ownerType}/{baseId}` | 删除本体库。 |

## Scene

| API | Method | Path | Description |
|---|---|---|---|
| [createScene](Scene/createScene.md) | POST | `/api/v1/ontologyBases/{ownerType}/{baseId}/scenes` | 创建场景（分组）。sceneCode 可选，不传时雪花生成。 |
| [queryScenes](Scene/queryScenes.md) | GET | `/api/v1/ontologyBases/{ownerType}/{baseId}/scenes` | 按关键词模糊查询场景列表。 |
| [getSceneDetails](Scene/getSceneDetails.md) | GET | `/api/v1/ontologyBases/{ownerType}/{baseId}/scenes/{sceneId}` | 查询场景完整详情，含对象、视图、动作、关系、数据源。 |
| [updateScene](Scene/updateScene.md) | PUT | `/api/v1/ontologyBases/{ownerType}/{baseId}/scenes/{sceneId}` | 更新场景元信息。 |
| [deleteScene](Scene/deleteScene.md) | DELETE | `/api/v1/ontologyBases/{ownerType}/{baseId}/scenes/{sceneId}` | 删除场景。只删分组，不删资源。 |
| [addSceneMembers](Scene/addMembers.md) | POST | `/api/v1/ontologyBases/{ownerType}/{baseId}/scenes/{sceneId}/members` | 向场景添加对象/视图引用。幂等。 |
| [removeSceneMembers](Scene/removeMembers.md) | DELETE | `/api/v1/ontologyBases/{ownerType}/{baseId}/scenes/{sceneId}/members` | 从场景移除对象/视图引用。只删引用，不删资源。 |
| [queryOntologiesByScene](Scene/queryOntologiesByScene.md) | GET | `/api/v1/ontologyBases/{ownerType}/{baseId}/scenes/{sceneId}/ontologies` | 按场景分页查询本体列表。 |

## Object

| API | Method | Path | Description |
|---|---|---|---|
| [listObjects](Object/listObjects.md) | GET | `/api/v1/ontologyBases/{ownerType}/{baseId}/objects` | 列出对象类型列表。 |
| [getObject](Object/getObject.md) | GET | `/api/v1/ontologyBases/{ownerType}/{baseId}/objects/{objectCode}` | 获取对象类型详情，含属性列表和动作列表。 |
| [createObject](Object/createObject.md) | POST | `/api/v1/ontologyBases/{ownerType}/{baseId}/objects` | 创建对象类型。仅 LOCAL。 |
| [updateObject](Object/updateObject.md) | PUT | `/api/v1/ontologyBases/{ownerType}/{baseId}/objects/{objectCode}` | 更新对象类型。仅 LOCAL。 |
| [deleteObject](Object/deleteObject.md) | DELETE | `/api/v1/ontologyBases/{ownerType}/{baseId}/objects/{objectCode}` | 删除对象类型。仅 LOCAL。 |

## Relation

| API | Method | Path | Description |
|---|---|---|---|
| [listRelations](Relation/listRelations.md) | GET | `/api/v1/ontologyBases/{ownerType}/{baseId}/relations` | 列出关系列表。 |
| [createRelation](Relation/createRelation.md) | POST | `/api/v1/ontologyBases/{ownerType}/{baseId}/relations` | 创建关系。仅 LOCAL。 |
| [updateRelation](Relation/updateRelation.md) | PUT | `/api/v1/ontologyBases/{ownerType}/{baseId}/relations/{relationCode}` | 更新关系。仅 LOCAL。 |
| [deleteRelation](Relation/deleteRelation.md) | DELETE | `/api/v1/ontologyBases/{ownerType}/{baseId}/relations/{relationCode}` | 删除关系。仅 LOCAL。 |

## View

| API | Method | Path | Description |
|---|---|---|---|
| [listViews](View/listViews.md) | GET | `/api/v1/ontologyBases/{ownerType}/{baseId}/views` | 列出视图列表。 |
| [getView](View/getView.md) | GET | `/api/v1/ontologyBases/{ownerType}/{baseId}/views/{viewCode}` | 获取视图详情。 |
| [createView](View/createView.md) | POST | `/api/v1/ontologyBases/{ownerType}/{baseId}/views` | 创建视图。仅 LOCAL。 |
| [updateView](View/updateView.md) | PUT | `/api/v1/ontologyBases/{ownerType}/{baseId}/views/{viewCode}` | 更新视图。仅 LOCAL。 |
| [deleteView](View/deleteView.md) | DELETE | `/api/v1/ontologyBases/{ownerType}/{baseId}/views/{viewCode}` | 删除视图。仅 LOCAL。 |

## Datasource

| API | Method | Path | Description |
|---|---|---|---|
| [listDatasources](Datasource/listDatasources.md) | GET | `/api/v1/ontologyBases/{ownerType}/{baseId}/datasources` | 列出数据源列表。 |
| [createDatasource](Datasource/createDatasource.md) | POST | `/api/v1/ontologyBases/{ownerType}/{baseId}/datasources` | 创建/更新数据源。仅 LOCAL。 |
| [deleteDatasource](Datasource/deleteDatasource.md) | DELETE | `/api/v1/ontologyBases/{ownerType}/{baseId}/datasources/{dbId}` | 删除数据源。仅 LOCAL。 |

## Action

| API | Method | Path | Description |
|---|---|---|---|
| [createAction](Action/createAction.md) | POST | `/api/v1/ontologyBases/{ownerType}/{baseId}/objects/{objectCode}/actions` | 创建动作。仅 LOCAL。 |
| [updateAction](Action/updateAction.md) | PUT | `/api/v1/ontologyBases/{ownerType}/{baseId}/objects/{objectCode}/actions/{actionCode}` | 更新动作。仅 LOCAL。 |
| [deleteAction](Action/deleteAction.md) | DELETE | `/api/v1/ontologyBases/{ownerType}/{baseId}/objects/{objectCode}/actions/{actionCode}` | 删除动作。仅 LOCAL。 |

## Instance

| API | Method | Path | Description |
|---|---|---|---|
| [searchInstances](Instance/searchInstances.md) | POST | `/api/v1/ontologyBases/{ownerType}/{baseId}/instances/search` | 带条件查询实例数据，支持 in / eq / and / or 等操作符。 |

## Graph

| API | Method | Path | Description |
|---|---|---|---|
| [queryGraph](Graph/queryGraph.md) | POST | `/api/v1/ontologyBases/{ownerType}/{baseId}/scenes/{sceneId}/graph/query` | 按节点编码或名称查询 N 跳范围内的图节点及关系。 |
| [queryPath](Graph/queryPath.md) | POST | `/api/v1/ontologyBases/{ownerType}/{baseId}/scenes/{sceneId}/graph/path` | 根据起点和终点查询路径节点序列及关系。 |

## Search

| API | Method | Path | Description |
|---|---|---|---|
| [searchScene](Search/searchScene.md) | POST | `/api/v1/ontologyBases/{ownerType}/{baseId}/scenes/{sceneId}/search` | 场景内全文/语义/混合检索。 |
| [searchOntologyBase](Search/searchOntologyBase.md) | POST | `/api/v1/ontologyBases/{ownerType}/{baseId}/search` | 跨场景全文/语义/混合检索。 |
