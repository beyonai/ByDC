# API 文档

## Scene

| API | Method | Path | Description |
|---|---|---|---|
| [queryScenes](Scene/queryScenes.md) | POST | `/DtStudio/daiservice/OntologyScenceController/query` | 按关键词模糊查询场景列表。 |
| [queryOntologiesByScene](Scene/queryOntologiesByScene.md) | POST | `/DtStudio/daiservice/OntologyScenceController/queryOntologies` | 根据场景 ID 分页查询本体列表。 |
| [getSceneDetails](Scene/getSceneDetails.md) | POST | `/DtStudio/daiservice/OntologyEntityController/sceneDetails` | 查询场景完整本体详情，含对象、视图、动作、关系、数据源。 |

## Instance

| API | Method | Path | Description |
|---|---|---|---|
| [searchInstances](Instance/searchInstances.md) | POST | `/DtStudio/daiservice/InstanceController/search` | 带条件查询实例数据，支持 `in` / `eq` / `and` / `or` 等操作符。 |

## Graph

| API | Method | Path | Description |
|---|---|---|---|
| [queryGraphByNode](Graph/queryGraphByNode.md) | POST | `/DtStudio/daiservice/graph/queryGraph` | 按节点编码或名称查询 N 跳范围内的图节点及关系。 |
| [queryPath](Graph/queryPath.md) | POST | `/DtStudio/daiservice/graph/queryPath` | 根据起点和终点查询路径节点序列及关系。 |

## OntologySearch

| API | Method | Path | Description |
|---|---|---|---|
| [searchOntology](OntologySearch/searchOntology.md) | POST | `/DtStudio/daiservice/search/ontology` | 统一本体元数据与实例向量检索。支持 vector / keyword / hybrid 模式，按 searchScope 控制返回域。 |
