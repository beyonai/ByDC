import networkx as nx
from networkx.algorithms import isomorphism
import matplotlib.pyplot as plt
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Literal, Tuple
from enum import Enum

# ==================== 枚举定义 ====================

class BindType(Enum):
    OBJECT = "object"
    FIELD = "field"

class RelationType(Enum):
    ONE_TO_ONE = "1:1"
    ONE_TO_MANY = "1:N"
    MANY_TO_MANY = "N:M"

class NodeLabel(Enum):
    OBJECT = "Object"
    FIELD = "Field"
    ACTION = "Action"
    PARAMETER = "Parameter"
    FUNCTION = "Function"
    VIEW = "View"
    OBJECT_RELATION = "ObjectRelation"
    # NEW: Term system
    DOMAIN = "Domain"
    TERM_LIBRARY = "TermLibrary"
    TERM_TYPE = "TermType"
    TERM = "Term"

class EdgeLabel(Enum):
    HAS_FIELD = "HAS_FIELD"
    HAS_ACTION = "HAS_ACTION"
    HAS_PARAMETER = "HAS_PARAMETER"
    USES_FUNCTION = "USES_FUNCTION"
    BINDS_TO_OBJECT = "BINDS_TO_OBJECT"
    BINDS_TO_FIELD = "BINDS_TO_FIELD"
    CONTAINS = "CONTAINS"
    DEFINES_RELATION = "DEFINES_RELATION"
    SOURCE_FIELD = "SOURCE_FIELD"
    TARGET_FIELD = "TARGET_FIELD"
    INTERSECTS = "INTERSECTS"
    # NEW: Term-Type relationships
    IS_INSTANCE_OF = "IS_INSTANCE_OF"
    HAS_INSTANCE = "HAS_INSTANCE"
    IS_MEMBER_OF = "IS_MEMBER_OF"
    HAS_MEMBER = "HAS_MEMBER"
    IS_ENTRY_OF = "IS_ENTRY_OF"
    HAS_ENTRY = "HAS_ENTRY"
    IS_DOCUMENT_OF = "IS_DOCUMENT_OF"
    HAS_DOCUMENT = "HAS_DOCUMENT"
    # NEW: Term-to-Term relationships
    MANAGES = "MANAGES"
    BELONGS_TO = "BELONGS_TO"
    PART_OF = "PART_OF"
    DEPENDS_ON = "DEPENDS_ON"
    RELATES_TO = "RELATES_TO"
    # NEW: Tag relationships
    HAS_PROPERTY = "HAS_PROPERTY"
    HAS_NOTE = "HAS_NOTE"
    # NEW: Domain and Library
    BELONGS_TO_DOMAIN = "BELONGS_TO_DOMAIN"
    SOURCED_FROM_LIBRARY = "SOURCED_FROM_LIBRARY"
    HAS_CHILD_DOMAIN = "HAS_CHILD_DOMAIN"
    HAS_SUBTYPE = "HAS_SUBTYPE"
    # NEW: Field connection
    DEFINED_BY_TERM_TYPE = "DEFINED_BY_TERM_TYPE"
    DEFINES_FIELD = "DEFINES_FIELD"

# ==================== 数据类定义 ====================

@dataclass
class Properties:
    """属性基类"""
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return self.data

@dataclass
class ObjectNode:
    """对象节点"""
    id: str
    name: str
    label: str
    properties: Properties = field(default_factory=Properties)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "label": self.label,
            "properties": self.properties.to_dict(),
            "node_type": NodeLabel.OBJECT.value
        }

@dataclass
class FieldNode:
    """字段节点"""
    id: str
    object_id: str
    name: str
    field_type: str
    required: bool = False
    term_type_id: Optional[str] = None  # NEW: 关联TermType
    properties: Properties = field(default_factory=Properties)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "object_id": self.object_id,
            "name": self.name,
            "field_type": self.field_type,
            "required": self.required,
            "properties": self.properties.to_dict(),
            "node_type": NodeLabel.FIELD.value
        }
        if self.term_type_id:
            result["term_type_id"] = self.term_type_id
        return result

@dataclass
class FunctionNode:
    """函数节点"""
    id: str
    name: str
    properties: Properties = field(default_factory=Properties)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "properties": self.properties.to_dict(),
            "node_type": NodeLabel.FUNCTION.value
        }

@dataclass
class ParameterNode:
    """参数节点"""
    id: str
    action_id: str
    name: str
    bind_type: BindType
    bind_target_id: Optional[str] = None
    properties: Properties = field(default_factory=Properties)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action_id": self.action_id,
            "name": self.name,
            "bind_type": self.bind_type.value,
            "bind_target_id": self.bind_target_id,
            "properties": self.properties.to_dict(),
            "node_type": NodeLabel.PARAMETER.value
        }

@dataclass
class ActionNode:
    """动作节点"""
    id: str
    object_id: str
    name: str
    function_id: str
    properties: Properties = field(default_factory=Properties)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "object_id": self.object_id,
            "name": self.name,
            "function_id": self.function_id,
            "properties": self.properties.to_dict(),
            "node_type": NodeLabel.ACTION.value
        }

@dataclass
class ViewNode:
    """视图节点"""
    id: str
    name: str
    properties: Properties = field(default_factory=Properties)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "properties": self.properties.to_dict(),
            "node_type": NodeLabel.VIEW.value
        }

@dataclass
class ObjectRelationNode:
    """对象关系节点"""
    id: str
    view_id: str
    source_object_id: str
    target_object_id: str
    source_field_id: str
    target_field_id: str
    relation_type: RelationType
    properties: Properties = field(default_factory=Properties)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "view_id": self.view_id,
            "source_object_id": self.source_object_id,
            "target_object_id": self.target_object_id,
            "source_field_id": self.source_field_id,
            "target_field_id": self.target_field_id,
            "relation_type": self.relation_type.value,
            "properties": self.properties.to_dict(),
            "node_type": NodeLabel.OBJECT_RELATION.value
        }

@dataclass
class DomainNode:
    """领域节点"""
    id: str
    name: str
    parent_id: Optional[str] = None
    properties: Properties = field(default_factory=Properties)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "properties": self.properties.to_dict(),
            "node_type": NodeLabel.DOMAIN.value
        }

@dataclass
class TermLibraryNode:
    """术语库节点"""
    id: str
    name: str
    properties: Properties = field(default_factory=Properties)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "properties": self.properties.to_dict(),
            "node_type": NodeLabel.TERM_LIBRARY.value
        }

@dataclass
class TermTypeNode:
    """术语类型节点"""
    id: str
    code: str
    name: str
    type: int  # 1=list, 2=dict, 3=ontology, 4=document
    parent_type_id: Optional[str] = None
    properties: Properties = field(default_factory=Properties)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "type": self.type,
            "parent_type_id": self.parent_type_id,
            "properties": self.properties.to_dict(),
            "node_type": NodeLabel.TERM_TYPE.value
        }

@dataclass
class TermNode:
    """术语节点 - 统一术语，不存储type（通过边表达）"""
    id: str
    standard_name: str
    domain_id: Optional[str] = None
    library_id: Optional[str] = None
    properties: Properties = field(default_factory=Properties)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "standard_name": self.standard_name,
            "domain_id": self.domain_id,
            "library_id": self.library_id,
            "properties": self.properties.to_dict(),
            "node_type": NodeLabel.TERM.value
        }

# ==================== 图模型管理器 ====================

class MetadataGraph:
    """
    元数据图形数据库模型
    使用 NetworkX 实现多标签属性图
    """
    
    def __init__(self):
        self.graph = nx.MultiDiGraph()  # 使用多重有向图支持多关系
    
    # ========== 节点操作 ==========
    
    def add_object(self, obj: ObjectNode) -> str:
        """添加对象节点"""
        node_id = f"Object:{obj.id}"
        self.graph.add_node(node_id, **obj.to_dict())
        return node_id
    
    def add_field(self, field: FieldNode) -> str:
        """添加字段节点"""
        node_id = f"Field:{field.id}"
        self.graph.add_node(node_id, **field.to_dict())
        
        # 自动创建与对象的 HAS_FIELD 关系
        object_node = f"Object:{field.object_id}"
        if object_node in self.graph:
            self.graph.add_edge(
                object_node, node_id,
                relation=EdgeLabel.HAS_FIELD.value,
                key=f"has_field_{field.id}"
            )
        
        # NEW: 添加TermType关联
        if field.term_type_id:
            term_type_node = f"TermType:{field.term_type_id}"
            if term_type_node in self.graph:
                self.graph.add_edge(
                    node_id, term_type_node,
                    relation=EdgeLabel.DEFINED_BY_TERM_TYPE.value
                )
        
        return node_id
    
    def add_function(self, func: FunctionNode) -> str:
        """添加函数节点"""
        node_id = f"Function:{func.id}"
        self.graph.add_node(node_id, **func.to_dict())
        return node_id
    
    def add_action(self, action: ActionNode) -> str:
        """添加动作节点"""
        node_id = f"Action:{action.id}"
        self.graph.add_node(node_id, **action.to_dict())
        
        # 自动创建与对象的 HAS_ACTION 关系
        object_node = f"Object:{action.object_id}"
        if object_node in self.graph:
            self.graph.add_edge(
                object_node, node_id,
                relation=EdgeLabel.HAS_ACTION.value,
                key=f"has_action_{action.id}"
            )
        
        # 自动创建与函数的 USES_FUNCTION 关系
        func_node = f"Function:{action.function_id}"
        if func_node in self.graph:
            self.graph.add_edge(
                node_id, func_node,
                relation=EdgeLabel.USES_FUNCTION.value,
                key=f"uses_func_{action.function_id}"
            )
        return node_id
    
    def add_parameter(self, param: ParameterNode) -> str:
        """添加参数节点"""
        node_id = f"Parameter:{param.id}"
        self.graph.add_node(node_id, **param.to_dict())
        
        # 自动创建与动作的 HAS_PARAMETER 关系
        action_node = f"Action:{param.action_id}"
        if action_node in self.graph:
            self.graph.add_edge(
                action_node, node_id,
                relation=EdgeLabel.HAS_PARAMETER.value,
                key=f"has_param_{param.id}"
            )
        
        # 根据 bind_type 创建绑定关系
        if param.bind_target_id:
            if param.bind_type == BindType.OBJECT:
                target_node = f"Object:{param.bind_target_id}"
                if target_node in self.graph:
                    self.graph.add_edge(
                        node_id, target_node,
                        relation=EdgeLabel.BINDS_TO_OBJECT.value,
                        key=f"binds_to_object_{param.bind_target_id}"
                    )
            elif param.bind_type == BindType.FIELD:
                target_node = f"Field:{param.bind_target_id}"
                if target_node in self.graph:
                    self.graph.add_edge(
                        node_id, target_node,
                        relation=EdgeLabel.BINDS_TO_FIELD.value,
                        key=f"binds_to_field_{param.bind_target_id}"
                    )
        return node_id
    
    def add_view(self, view: ViewNode) -> str:
        """添加视图节点"""
        node_id = f"View:{view.id}"
        self.graph.add_node(node_id, **view.to_dict())
        return node_id
    
    def add_object_relation(self, relation: ObjectRelationNode) -> str:
        """添加对象关系节点"""
        node_id = f"Relation:{relation.id}"
        self.graph.add_node(node_id, **relation.to_dict())
        
        # 创建与视图的 DEFINES_RELATION 关系
        view_node = f"View:{relation.view_id}"
        if view_node in self.graph:
            self.graph.add_edge(
                view_node, node_id,
                relation=EdgeLabel.DEFINES_RELATION.value,
                key=f"defines_rel_{relation.id}"
            )
        
        # 创建 SOURCE_FIELD 关系
        source_field = f"Field:{relation.source_field_id}"
        if source_field in self.graph:
            self.graph.add_edge(
                node_id, source_field,
                relation=EdgeLabel.SOURCE_FIELD.value,
                key=f"source_field_{relation.source_field_id}"
            )
        
        # 创建 TARGET_FIELD 关系
        target_field = f"Field:{relation.target_field_id}"
        if target_field in self.graph:
            self.graph.add_edge(
                node_id, target_field,
                relation=EdgeLabel.TARGET_FIELD.value,
                key=f"target_field_{relation.target_field_id}"
            )
        
        # 创建 INTERSECTS 关系（基于字段交集）
        source_obj = f"Object:{relation.source_object_id}"
        target_obj = f"Object:{relation.target_object_id}"
        if source_obj in self.graph and target_obj in self.graph:
            self.graph.add_edge(
                node_id, source_obj,
                relation=EdgeLabel.INTERSECTS.value,
                key=f"intersects_source_{relation.source_object_id}",
                intersect_field=relation.source_field_id
            )
            self.graph.add_edge(
                node_id, target_obj,
                relation=EdgeLabel.INTERSECTS.value,
                key=f"intersects_target_{relation.target_object_id}",
                intersect_field=relation.target_field_id
            )
        return node_id
    
    def add_domain(self, domain: DomainNode) -> str:
        """添加领域节点"""
        node_id = f"Domain:{domain.id}"
        self.graph.add_node(node_id, **domain.to_dict())
        
        # 自动创建层级关系
        if domain.parent_id:
            parent_node = f"Domain:{domain.parent_id}"
            if parent_node in self.graph:
                self.graph.add_edge(
                    parent_node, node_id,
                    relation=EdgeLabel.HAS_CHILD_DOMAIN.value
                )
        return node_id
    
    def add_term_library(self, library: TermLibraryNode) -> str:
        """添加术语库节点"""
        node_id = f"TermLibrary:{library.id}"
        self.graph.add_node(node_id, **library.to_dict())
        return node_id
    
    def add_term_type(self, term_type: TermTypeNode) -> str:
        """添加术语类型节点"""
        node_id = f"TermType:{term_type.id}"
        self.graph.add_node(node_id, **term_type.to_dict())
        
        # 自动创建层级关系
        if term_type.parent_type_id:
            parent_node = f"TermType:{term_type.parent_type_id}"
            if parent_node in self.graph:
                self.graph.add_edge(
                    parent_node, node_id,
                    relation=EdgeLabel.HAS_SUBTYPE.value
                )
        return node_id
    
    def add_term(self, term: TermNode, 
                 type_relations: Optional[List[Tuple[str, str]]] = None) -> str:
        """
        添加术语节点
        
        Args:
            term: TermNode实例
            type_relations: List of (term_type_id, relation_type)
                relation_type: "instance" | "member" | "entry" | "document"
        
        Returns:
            节点ID字符串
        """
        node_id = f"Term:{term.id}"
        self.graph.add_node(node_id, **term.to_dict())
        
        # 自动创建Domain边
        if term.domain_id:
            domain_node = f"Domain:{term.domain_id}"
            if domain_node in self.graph:
                self.graph.add_edge(
                    node_id, domain_node,
                    relation=EdgeLabel.BELONGS_TO_DOMAIN.value
                )
        
        # 自动创建Library边
        if term.library_id:
            library_node = f"TermLibrary:{term.library_id}"
            if library_node in self.graph:
                self.graph.add_edge(
                    node_id, library_node,
                    relation=EdgeLabel.SOURCED_FROM_LIBRARY.value
                )
        
        # 处理type_relations
        if type_relations:
            for term_type_id, relation_type in type_relations:
                self._add_term_type_relation(node_id, term_type_id, relation_type)
        
        return node_id
    
    def _validate_term_type_relation(self, term_type_id: str, relation_type: str):
        """验证relation_type与TermType.type的匹配性"""
        term_type_node = f"TermType:{term_type_id}"
        if term_type_node not in self.graph:
            raise ValueError(f"TermType {term_type_id} not found")
        
        term_type_data = self.graph.nodes[term_type_node]
        term_type_type = term_type_data.get("type")
        
        # type_to_relation映射
        type_to_relation = {
            1: ["member"],      # 列表
            2: ["entry"],       # 字典
            3: ["instance"],    # 本体
            4: ["document"]     # 文档
        }
        
        valid_relations = type_to_relation.get(term_type_type, [])
        if relation_type not in valid_relations:
            raise ValueError(
                f"Invalid relation '{relation_type}' for TermType "
                f"'{term_type_id}' with type={term_type_type}. "
                f"Valid relations: {valid_relations}"
            )

    def _add_term_type_relation(self, term_node_id: str, term_type_id: str, 
                                 relation_type: str):
        """根据relation_type创建对应的边"""
        # 先验证
        self._validate_term_type_relation(term_type_id, relation_type)
        
        term_type_node = f"TermType:{term_type_id}"
        
        edge_map = {
            "instance": (EdgeLabel.IS_INSTANCE_OF, EdgeLabel.HAS_INSTANCE),
            "member": (EdgeLabel.IS_MEMBER_OF, EdgeLabel.HAS_MEMBER),
            "entry": (EdgeLabel.IS_ENTRY_OF, EdgeLabel.HAS_ENTRY),
            "document": (EdgeLabel.IS_DOCUMENT_OF, EdgeLabel.HAS_DOCUMENT)
        }
        
        if relation_type not in edge_map:
            raise ValueError(f"Unknown relation_type: {relation_type}")
        
        term_to_type_edge, type_to_term_edge = edge_map[relation_type]
        
        # Term -> TermType
        self.graph.add_edge(
            term_node_id, term_type_node,
            relation=term_to_type_edge.value,
            relation_type=relation_type
        )
        
        # TermType -> Term
        self.graph.add_edge(
            term_type_node, term_node_id,
            relation=type_to_term_edge.value,
            relation_type=relation_type
        )
    
    def add_term_relation(self, source_term_id: str, target_term_id: str,
                          relation_label: EdgeLabel, 
                          properties: Optional[Dict] = None) -> None:
        """创建Term之间的关系
        
        Args:
            source_term_id: 源术语ID
            target_term_id: 目标术语ID
            relation_label: 关系标签 (MANAGES, BELONGS_TO, PART_OF, DEPENDS_ON, RELATES_TO)
            properties: 关系的额外属性
        """
        source_node = f"Term:{source_term_id}"
        target_node = f"Term:{target_term_id}"
        
        if source_node not in self.graph:
            raise ValueError(f"Source term {source_term_id} not found")
        if target_node not in self.graph:
            raise ValueError(f"Target term {target_term_id} not found")
        
        edge_props = properties or {}
        edge_props["relation"] = relation_label.value
        
        self.graph.add_edge(
            source_node, target_node,
            **edge_props
        )
    
    def add_view_object(self, view_id: str, object_id: str):
        """添加视图包含对象的关系"""
        view_node = f"View:{view_id}"
        object_node = f"Object:{object_id}"
        if view_node in self.graph and object_node in self.graph:
            self.graph.add_edge(
                view_node, object_node,
                relation=EdgeLabel.CONTAINS.value,
                key=f"contains_{object_id}"
            )
    
    # ========== 查询操作 ==========
    
    def get_object_fields(self, object_id: str) -> List[Dict]:
        """获取对象的所有字段"""
        node_id = f"Object:{object_id}"
        if node_id not in self.graph:
            return []
        
        fields = []
        for _, target, data in self.graph.out_edges(node_id, data=True):
            if data.get('relation') == EdgeLabel.HAS_FIELD.value:
                fields.append(dict(self.graph.nodes[target]))
        return fields
    
    def get_object_actions(self, object_id: str) -> List[Dict]:
        """获取对象的所有动作"""
        node_id = f"Object:{object_id}"
        if node_id not in self.graph:
            return []
        
        actions = []
        for _, target, data in self.graph.out_edges(node_id, data=True):
            if data.get('relation') == EdgeLabel.HAS_ACTION.value:
                actions.append(dict(self.graph.nodes[target]))
        return actions
    
    def get_action_parameters(self, action_id: str) -> List[Dict]:
        """获取动作的所有参数"""
        node_id = f"Action:{action_id}"
        if node_id not in self.graph:
            return []
        
        params = []
        for _, target, data in self.graph.out_edges(node_id, data=True):
            if data.get('relation') == EdgeLabel.HAS_PARAMETER.value:
                param_data = dict(self.graph.nodes[target])
                # 获取绑定信息
                for _, bind_target, bind_data in self.graph.out_edges(target, data=True):
                    if bind_data.get('relation') in [
                        EdgeLabel.BINDS_TO_OBJECT.value,
                        EdgeLabel.BINDS_TO_FIELD.value
                    ]:
                        param_data['binds_to'] = bind_target
                params.append(param_data)
        return params
    
    def get_view_objects(self, view_id: str) -> List[Dict]:
        """获取视图包含的所有对象"""
        node_id = f"View:{view_id}"
        if node_id not in self.graph:
            return []
        
        objects = []
        for _, target, data in self.graph.out_edges(node_id, data=True):
            if data.get('relation') == EdgeLabel.CONTAINS.value:
                objects.append(dict(self.graph.nodes[target]))
        return objects
    
    def get_view_relations(self, view_id: str) -> List[Dict]:
        """获取视图定义的所有对象关系"""
        node_id = f"View:{view_id}"
        if node_id not in self.graph:
            return []
        
        relations = []
        for _, target, data in self.graph.out_edges(node_id, data=True):
            if data.get('relation') == EdgeLabel.DEFINES_RELATION.value:
                relations.append(dict(self.graph.nodes[target]))
        return relations
    
    def get_related_objects_by_intersection(self, relation_id: str) -> Dict:
        """根据字段交集获取关联的对象"""
        node_id = f"Relation:{relation_id}"
        if node_id not in self.graph:
            return {}
        
        result = {
            "source": None,
            "target": None,
            "source_field": None,
            "target_field": None
        }
        
        for _, target, data in self.graph.out_edges(node_id, data=True):
            if data.get('relation') == EdgeLabel.SOURCE_FIELD.value:
                result["source_field"] = dict(self.graph.nodes[target])
            elif data.get('relation') == EdgeLabel.TARGET_FIELD.value:
                result["target_field"] = dict(self.graph.nodes[target])
            elif data.get('relation') == EdgeLabel.INTERSECTS.value:
                obj_data = dict(self.graph.nodes[target])
                if f"Object:{result['source_field']['object_id'] if result['source_field'] else ''}" == target:
                    result["source"] = obj_data
                else:
                    result["target"] = obj_data
        
        return result
    
    def find_objects_with_common_field_values(self, field_name: str) -> List[List[str]]:
        """查找具有相同字段值的对象对"""
        # 这是一个高级查询示例
        objects_with_field = []
        for node_id, data in self.graph.nodes(data=True):
            if data.get('node_type') == NodeLabel.FIELD.value:
                if data.get('name') == field_name:
                    objects_with_field.append(data.get('object_id'))
        
        return [[obj1, obj2] for i, obj1 in enumerate(objects_with_field) 
                for obj2 in objects_with_field[i+1:]]
    
    # ========== Term查询操作 ==========
    
    def get_term_by_name(self, name: str) -> Optional[Dict]:
        """根据名称查找Term
        
        Args:
            name: 术语标准名称
        
        Returns:
            Term数据字典或None
        """
        for node_id, data in self.graph.nodes(data=True):
            if data.get("node_type") == NodeLabel.TERM.value:
                if data.get("standard_name") == name:
                    return dict(data)
        return None
    
    def get_term_identities(self, term_id: str) -> List[Dict]:
        """获取Term的所有身份（关联的所有TermType）
        
        Args:
            term_id: 术语ID（不含"Term:"前缀）
        
        Returns:
            身份列表，每项包含type, relation, type_code
        """
        term_node = f"Term:{term_id}"
        if term_node not in self.graph:
            return []
        
        identities = []
        for _, target, data in self.graph.out_edges(term_node, data=True):
            if data.get("relation") in [
                EdgeLabel.IS_INSTANCE_OF.value,
                EdgeLabel.IS_MEMBER_OF.value,
                EdgeLabel.IS_ENTRY_OF.value,
                EdgeLabel.IS_DOCUMENT_OF.value
            ]:
                type_data = dict(self.graph.nodes[target])
                identities.append({
                    "type": type_data.get("name"),
                    "relation": data.get("relation"),
                    "type_code": type_data.get("code")
                })
        return identities
    
    def get_terms_by_ids(self, term_ids: List[str]) -> Dict[str, Dict]:
        """批量获取多个Term的信息
        
        Args:
            term_ids: 术语ID列表（不含"Term:"前缀）
        
        Returns:
            字典，key为term_id，value包含：
            - standard_name: 标准名称
            - properties: 属性字典
            - relations: 关系字典（按关系类型分组）
            不存在的ID会被跳过
        """
        result = {}
        
        for term_id in term_ids:
            term_node = f"Term:{term_id}"
            
            # 跳过不存在的Term
            if term_node not in self.graph:
                continue
            
            term_data = dict(self.graph.nodes[term_node])
            
            # 收集所有出边关系
            relations: Dict[str, List[Dict]] = {}
            for _, target, edge_data in self.graph.out_edges(term_node, data=True):
                relation_label = edge_data.get("relation")
                if not relation_label:
                    continue
                
                # 获取目标节点信息
                target_node_data = dict(self.graph.nodes[target])
                relation_info = {
                    "target_id": target.split(":")[-1] if ":" in target else target,
                    "target_type": target_node_data.get("node_type"),
                    "target_name": target_node_data.get("name") or target_node_data.get("standard_name"),
                }
                
                # 添加边的额外属性（如department, since等）
                for key, value in edge_data.items():
                    if key not in ["relation", "relation_type", "key", "source", "target"]:
                        relation_info[key] = value
                
                # 按关系类型分组
                if relation_label not in relations:
                    relations[relation_label] = []
                relations[relation_label].append(relation_info)
            
            result[term_id] = {
                "standard_name": term_data.get("standard_name"),
                "properties": term_data.get("properties", {}),
                "relations": relations
            }
        
        return result
    
    def get_terms_by_type(self, term_type_id: str, 
                         relation_type: Optional[str] = None) -> List[Dict]:
        """获取某TermType下的所有Term
        
        Args:
            term_type_id: TermType ID（不含"TermType:"前缀）
            relation_type: 可选过滤，"instance" | "member" | "entry" | "document"
        
        Returns:
            Term数据字典列表
        """
        term_type_node = f"TermType:{term_type_id}"
        if term_type_node not in self.graph:
            return []
        
        terms = []
        edge_filters = {
            "instance": EdgeLabel.HAS_INSTANCE.value,
            "member": EdgeLabel.HAS_MEMBER.value,
            "entry": EdgeLabel.HAS_ENTRY.value,
            "document": EdgeLabel.HAS_DOCUMENT.value
        }
        
        for _, target, data in self.graph.out_edges(term_type_node, data=True):
            edge_relation = data.get("relation")
            if relation_type and edge_relation != edge_filters.get(relation_type):
                continue
            
            target_data = dict(self.graph.nodes[target])
            if target_data.get("node_type") == NodeLabel.TERM.value:
                terms.append(target_data)
        
        return terms
    
    # ========== 图算法 ==========
    
    def get_object_dependency_graph(self, object_id: str) -> nx.DiGraph:
        """获取对象的依赖图（通过关系）"""
        # 使用子图提取
        related_nodes = set()
        node_id = f"Object:{object_id}"
        
        # BFS遍历找到所有相关节点
        visited = set()
        queue = [node_id]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            related_nodes.add(current)
            
            for neighbor in self.graph.neighbors(current):
                if neighbor not in visited:
                    queue.append(neighbor)
        
        return self.graph.subgraph(related_nodes).copy()
    
    def find_circular_dependencies(self) -> List[List[str]]:
        """查找循环依赖"""
        try:
            cycles = list(nx.simple_cycles(self.graph))
            return cycles
        except:
            return []
    
    def calculate_centrality(self) -> Dict[str, float]:
        """计算节点中心性（找出核心对象）"""
        try:
            return nx.degree_centrality(self.graph)
        except:
            return {}
    
    # ========== 序列化 ==========
    
    def to_cypher(self) -> List[str]:
        """导出为 Cypher 查询语句"""
        queries = []
        
        # 导出节点
        for node_id, data in self.graph.nodes(data=True):
            node_type = data.get('node_type', 'Unknown')
            props = {k: v for k, v in data.items() if k != 'node_type'}
            props_str = ', '.join([f"{k}: {repr(v)}" for k, v in props.items()])
            queries.append(f"CREATE ({node_id}:{node_type} {{{props_str}}})")
        
        # 导出边
        for source, target, key, data in self.graph.edges(data=True, keys=True):
            rel_type = data.get('relation', 'RELATED_TO')
            props = {k: v for k, v in data.items() if k != 'relation'}
            props_str = ', '.join([f"{k}: {repr(v)}" for k, v in props.items()]) if props else ""
            if props_str:
                queries.append(f"CREATE ({source})-[:{rel_type} {{{props_str}}}]->({target})")
            else:
                queries.append(f"CREATE ({source})-[:{rel_type}]->({target})")
        
        return queries
    
    def export_to_graphml(self, filepath: str):
        """导出为 GraphML 格式"""
        nx.write_graphml(self.graph, filepath)
    
    def export_to_json(self) -> Dict:
        """导出为 JSON 格式"""
        return nx.node_link_data(self.graph)
    
    # ========== 可视化 ==========
    
    def visualize(self, figsize=(16, 12)):
        """可视化图形"""
        plt.figure(figsize=figsize)
        
        # 使用分层布局
        pos = nx.spring_layout(self.graph, k=2, iterations=50)
        
        # 定义节点颜色
        color_map = {
            NodeLabel.OBJECT.value: '#4CAF50',      # 绿色
            NodeLabel.FIELD.value: '#2196F3',        # 蓝色
            NodeLabel.ACTION.value: '#FF9800',       # 橙色
            NodeLabel.PARAMETER.value: '#9C27B0',    # 紫色
            NodeLabel.FUNCTION.value: '#F44336',     # 红色
            NodeLabel.VIEW.value: '#795548',         # 棕色
            NodeLabel.OBJECT_RELATION.value: '#607D8B'  # 灰色
        }
        
        # 为每个节点设置颜色
        node_colors = []
        for node_id in self.graph.nodes():
            node_type = self.graph.nodes[node_id].get('node_type', 'Unknown')
            node_colors.append(color_map.get(node_type, '#999999'))
        
        # 绘制边
        edge_colors = []
        for u, v, data in self.graph.edges(data=True):
            relation = data.get('relation', '')
            if 'BINDS' in relation:
                edge_colors.append('#E91E63')  # 绑定关系 - 粉色
            elif 'INTERSECTS' in relation:
                edge_colors.append('#FF5722')  # 交集关系 - 深橙
            elif 'HAS' in relation:
                edge_colors.append('#666666')  # 包含关系 - 灰色
            else:
                edge_colors.append('#999999')  # 其他 - 浅灰
        
        # 绘制节点
        nx.draw_networkx_nodes(
            self.graph, pos,
            node_color=node_colors,
            node_size=3000,
            alpha=0.8,
            edgecolors='black',
            linewidths=2
        )
        
        # 绘制边
        nx.draw_networkx_edges(
            self.graph, pos,
            edge_color=edge_colors,
            arrows=True,
            arrowsize=20,
            arrowstyle='->',
            width=1.5,
            alpha=0.6,
            connectionstyle='arc3,rad=0.1'
        )
        
        # 绘制标签
        labels = {}
        for node_id in self.graph.nodes():
            data = self.graph.nodes[node_id]
            name = data.get('name', node_id)
            node_type = data.get('node_type', 'Unknown')
            labels[node_id] = f"{name}\n({node_type})"
        
        nx.draw_networkx_labels(
            self.graph, pos,
            labels,
            font_size=8,
            font_weight='bold',
            font_color='white'
        )
        
        # 添加图例
        legend_elements = [
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=color, 
                      markersize=10, label=label)
            for label, color in color_map.items()
        ]
        plt.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1, 1))
        
        plt.title('Metadata Graph Visualization', fontsize=16, fontweight='bold')
        plt.axis('off')
        plt.tight_layout()
        plt.show()

# ==================== 使用示例 ====================

def create_example():
    """创建示例元数据图"""
    g = MetadataGraph()
    
    # 创建对象
    user_obj = ObjectNode(
        id="user",
        name="User",
        label="用户",
        properties=Properties({"description": "系统用户"})
    )
    g.add_object(user_obj)
    
    order_obj = ObjectNode(
        id="order",
        name="Order",
        label="订单",
        properties=Properties({"description": "用户订单"})
    )
    g.add_object(order_obj)
    
    # 创建字段
    user_id_field = FieldNode(
        id="user_id",
        object_id="user",
        name="id",
        field_type="string",
        required=True,
        properties=Properties({"primary_key": True})
    )
    g.add_field(user_id_field)
    
    user_name_field = FieldNode(
        id="user_name",
        object_id="user",
        name="username",
        field_type="string",
        required=True
    )
    g.add_field(user_name_field)
    
    order_id_field = FieldNode(
        id="order_id",
        object_id="order",
        name="id",
        field_type="string",
        required=True,
        properties=Properties({"primary_key": True})
    )
    g.add_field(order_id_field)
    
    order_user_id_field = FieldNode(
        id="order_user_id",
        object_id="order",
        name="user_id",
        field_type="string",
        required=True,
        properties=Properties({"foreign_key": True, "references": "user.id"})
    )
    g.add_field(order_user_id_field)
    
    # 创建函数
    create_user_func = FunctionNode(
        id="create_user",
        name="createUser",
        properties=Properties({"async": True, "permissions": ["admin"]})
    )
    g.add_function(create_user_func)
    
    get_orders_func = FunctionNode(
        id="get_orders",
        name="getOrdersByUser",
        properties=Properties({"cache": True})
    )
    g.add_function(get_orders_func)
    
    # 创建动作
    create_action = ActionNode(
        id="create_user_action",
        object_id="user",
        name="create",
        function_id="create_user",
        properties=Properties({"http_method": "POST"})
    )
    g.add_action(create_action)
    
    # 创建参数
    name_param = ParameterNode(
        id="param_name",
        action_id="create_user_action",
        name="name",
        bind_type=BindType.FIELD,
        bind_target_id="user_name",
        properties=Properties({"validation": "required"})
    )
    g.add_parameter(name_param)
    
    self_param = ParameterNode(
        id="param_self",
        action_id="create_user_action",
        name="self",
        bind_type=BindType.OBJECT,
        bind_target_id="user",
        properties=Properties({"represents": "current_user"})
    )
    g.add_parameter(self_param)
    
    # 创建视图
    user_order_view = ViewNode(
        id="user_order_view",
        name="UserOrders",
        properties=Properties({"layout": "table"})
    )
    g.add_view(user_order_view)
    
    # 添加视图包含的对象
    g.add_view_object("user_order_view", "user")
    g.add_view_object("user_order_view", "order")
    
    # 创建对象关系（基于 user_id 字段交集）
    user_order_relation = ObjectRelationNode(
        id="rel_user_orders",
        view_id="user_order_view",
        source_object_id="user",
        target_object_id="order",
        source_field_id="user_id",
        target_field_id="order_user_id",
        relation_type=RelationType.ONE_TO_MANY,
        properties=Properties({"join_type": "inner"})
    )
    g.add_object_relation(user_order_relation)
    
    return g

# 运行示例
if __name__ == "__main__":
    # 创建示例图
    graph = create_example()
    
    # 打印统计信息
    print(f"节点数量: {graph.graph.number_of_nodes()}")
    print(f"边数量: {graph.graph.number_of_edges()}")
    print()
    
    # 查询示例
    print("=== 用户对象的字段 ===")
    fields = graph.get_object_fields("user")
    for f in fields:
        print(f"  - {f['name']} ({f['field_type']})")
    
    print("\n=== 用户对象的动作 ===")
    actions = graph.get_object_actions("user")
    for a in actions:
        print(f"  - {a['name']}")
    
    print("\n=== 动作的参数 ===")
    params = graph.get_action_parameters("create_user_action")
    for p in params:
        bind_info = f" -> {p.get('binds_to', 'N/A')}"
        print(f"  - {p['name']} ({p['bind_type']}){bind_info}")
    
    print("\n=== 视图的关联对象 ===")
    objects = graph.get_view_objects("user_order_view")
    for o in objects:
        print(f"  - {o['name']} ({o['label']})")
    
    print("\n=== 对象关系详情 ===")
    relation_details = graph.get_related_objects_by_intersection("rel_user_orders")
    print(f"  源对象: {relation_details['source']['name'] if relation_details['source'] else 'N/A'}")
    print(f"  目标对象: {relation_details['target']['name'] if relation_details['target'] else 'N/A'}")
    print(f"  源字段: {relation_details['source_field']['name'] if relation_details['source_field'] else 'N/A'}")
    print(f"  目标字段: {relation_details['target_field']['name'] if relation_details['target_field'] else 'N/A'}")
    
    print("\n=== 导出为 Cypher ===")
    cypher_queries = graph.to_cypher()
    for query in cypher_queries[:5]:  # 只打印前5条
        print(query)
    
    # 可视化（需要 matplotlib）
    try:
        graph.visualize()
    except Exception as e:
        print(f"\n可视化需要 matplotlib: {e}")