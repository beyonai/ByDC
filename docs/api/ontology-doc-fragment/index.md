# API 文档

## OntologyDocFragment（本体文档片段）

| API | Method | Path | Description |
|---|---|---|---|
| [batchCreateFragments](batchCreateFragments.md) | POST | `/api/v1/rpc/ontologyDocFragment/batchCreate` | 批量创建文档片段，自动从 term 表查询实例名称及原文件信息，任意 instanceId 不存在则整批拒绝。 |
| [listFragmentsByInstanceIds](listFragmentsByInstanceIds.md) | POST | `/api/v1/rpc/ontologyDocFragment/listByInstanceIds` | 按实例 ID 列表分页查询文档片段，支持按融合状态过滤。 |
| [updateFragmentStatus](updateFragmentStatus.md) | POST | `/api/v1/rpc/ontologyDocFragment/updateStatus` | 按主键 ID 列表批量更新融合状态（0=未融合，1=已融合）。 |
