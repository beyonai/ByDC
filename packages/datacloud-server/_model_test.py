"""Quick model dump validation."""
import json

from datacloud_server.models import (
    Action,
    Datasource,
    InstanceHit,
    MetadataHit,
    ObjectType,
    ObjectTypeSummary,
    Relation,
    Scene,
    SearchResult,
    SearchTotalCount,
    View,
)

# ObjectType
obj = ObjectType.model_validate({
    'objectCode': 'cust', 'objectName': 'Customer',
    'properties': [{'propertyCode': 'name', 'propertyName': 'Name', 'dataType': 'STRING'}],
    'actions': [{'actionCode': 'search', 'actionName': 'Search', 'belongObjectCode': 'cust'}],
})
print('ObjectType:', json.dumps(obj.model_dump(by_alias=True, mode='json'), indent=2))
assert obj.model_dump(by_alias=True)['objectCode'] == 'cust'
assert obj.model_dump(by_alias=True)['properties'][0]['propertyCode'] == 'name'

# Relation
rel = Relation.model_validate({
    'relationCode': 'has_order', 'sourceObjectCode': 'cust', 'targetObjectCode': 'order'
})
print('Relation:', json.dumps(rel.model_dump(by_alias=True, mode='json'), indent=2))
assert rel.model_dump(by_alias=True)['sourceObjectCode'] == 'cust'

# Datasource (nested!)
ds = Datasource.model_validate({
    'db': [{'dbId': 'pg1', 'dbCode': 'main', 'dbType': 'opengauss'}],
    'doc': [], 'api': [],
})
d = ds.model_dump(by_alias=True)
assert d['db'][0]['dbId'] == 'pg1'
print('Datasource:', json.dumps(d, indent=2))

# SearchResult
sr = SearchResult(
    metadata=[MetadataHit(sceneId='s1', resultType='object', matchedField='cust', score=0.95)],
    instances=[],
    totalCount=SearchTotalCount(metadata=1, instances=0),
)
assert sr.model_dump(by_alias=True)['totalCount']['metadata'] == 1
print('SearchResult OK')

# ObjectTypeSummary
os_ = ObjectTypeSummary.model_validate({
    'objectCode': 'cust', 'objectName': 'Customer', 'fieldCount': 3, 'actionCount': 2,
})
assert os_.model_dump(by_alias=True)['fieldCount'] == 3

print("\nALL ASSERTIONS PASSED")
