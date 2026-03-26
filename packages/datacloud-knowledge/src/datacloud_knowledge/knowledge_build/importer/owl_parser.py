"""将 OWL RDF/XML 解析为简单实体字典。

该模块把 rdflib 的三元组结构收敛为导入流程更容易消费的 Python dict，
仅提取 NamedIndividual 上的 DatatypeProperty 字段，不处理对象引用和 OWL 推理。
"""

from __future__ import annotations

from pathlib import Path
from typing import Final
from urllib.parse import urlparse

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF
from rdflib.term import Node


class OWLParseError(Exception):
    """OWL 文件格式不合法或实体类型不受支持时抛出。"""


_ENTITY_TYPE_MAPPING: Final[dict[str, str]] = {
    "DomainDefinition": "domain",
    "LibraryDefinition": "library",
    "TermTypeDefinition": "term_type",
    "TermDefinition": "term",
    "TermRelation": "relation",
}

# 样例 OWL 中存在已知拼写问题，这里统一折叠为调用方更容易消费的字段名。
_PROPERTY_ALIASES: Final[dict[str, str]] = {
    "trem_type_code_path": "term_type_code_path",
    "trem_type_code": "term_type_code",
    "trem_type_name": "term_type_name",
    "trem_type_desc": "term_type_desc",
    "trem_data_type": "term_data_type",
    "source_libeary": "source_library",
    "target_libeary": "target_library",
}


def parse_owl_file(file_path: Path) -> list[dict]:
    """解析 OWL 文件中的 NamedIndividual 实体。

    Args:
        file_path: 待解析的 OWL 文件路径。

    Returns:
        由实体字典组成的列表；空文件返回空列表。

    Raises:
        OWLParseError: RDF/XML 格式错误，或 NamedIndividual 类型不受支持。
    """

    raw_content = file_path.read_text(encoding="utf-8")
    if not raw_content.strip():
        return []

    graph = Graph()
    try:
        # 样例文件存在未声明 owl 前缀的历史问题，解析前做最小兼容修复。
        graph.parse(
            data=_prepare_rdfxml_content(raw_content),
            format="xml",
            publicID=file_path.resolve().as_uri(),
        )
    except Exception as exc:  # noqa: BLE001 - rdflib 底层会抛出多种解析异常类型
        raise OWLParseError(f"OWL 文件解析失败: {file_path}: {exc}") from exc

    datatype_properties = _collect_datatype_properties(graph)
    datatype_property_names = {_extract_local_name(uri) for uri in datatype_properties}
    entities: list[dict] = []
    for individual in graph.subjects(RDF.type, OWL.NamedIndividual):
        if not isinstance(individual, URIRef):
            continue
        entity: dict[str, str | list[str]] = {
            "entity_type": _resolve_entity_type(graph, individual),
        }
        for predicate, value in graph.predicate_objects(individual):
            if not isinstance(predicate, URIRef):
                continue
            if predicate == RDF.type:
                continue
            property_name = _normalize_property_name(_extract_local_name(predicate))
            raw_property_name = _extract_local_name(predicate)
            if (
                predicate not in datatype_properties
                and raw_property_name not in datatype_property_names
            ):
                continue
            if not isinstance(value, Literal):
                continue

            _append_property_value(entity, property_name, str(value))
        entities.append(entity)

    return entities


def _prepare_rdfxml_content(raw_content: str) -> str:
    """兼容历史 RDF/XML 中缺失的 owl 命名空间前缀声明。"""

    if "xmlns:owl=" in raw_content:
        return raw_content
    if "owl:" not in raw_content:
        return raw_content

    # 历史样例把 OWL 命名空间声明成默认 xmlns，却又在元素名里使用 owl: 前缀。
    # 这里仅补齐前缀声明，不改动其他结构，尽量保持输入语义不变。
    return raw_content.replace(
        "<rdf:RDF",
        '<rdf:RDF xmlns:owl="http://www.w3.org/2002/07/owl#"',
        1,
    )


def _collect_datatype_properties(graph: Graph) -> set[URIRef]:
    """收集图中声明过的 DatatypeProperty，避免误取对象属性。"""

    return {
        subject
        for subject in graph.subjects(RDF.type, OWL.DatatypeProperty)
        if isinstance(subject, URIRef)
    }


def _resolve_entity_type(graph: Graph, individual: URIRef) -> str:
    """读取 NamedIndividual 的业务实体类型。"""

    for type_uri in graph.objects(individual, RDF.type):
        if type_uri == OWL.NamedIndividual:
            continue
        if not isinstance(type_uri, URIRef):
            continue

        class_name = _extract_local_name(type_uri)
        entity_type = _ENTITY_TYPE_MAPPING.get(class_name)
        if entity_type is not None:
            return entity_type

    raise OWLParseError(f"NamedIndividual 缺少受支持的实体类型: {individual}")


def _normalize_property_name(property_name: str) -> str:
    """兼容样例中的历史拼写问题。"""

    return _PROPERTY_ALIASES.get(property_name, property_name)


def _extract_local_name(uri: Node) -> str:
    """提取 URI 的本地名称，兼容 #fragment 与 /path 两种形式。"""

    parsed = urlparse(str(uri))
    if parsed.fragment:
        return parsed.fragment

    path = parsed.path.rstrip("/")
    if "/" in path:
        return path.rsplit("/", maxsplit=1)[-1]
    return path or str(uri)


def _append_property_value(entity: dict[str, str | list[str]], key: str, value: str) -> None:
    """同一属性出现多次时保留全部值，而不是静默覆盖。"""

    current_value = entity.get(key)
    if current_value is None:
        entity[key] = value
        return

    if isinstance(current_value, list):
        current_value.append(value)
        return

    entity[key] = [current_value, value]


__all__ = ["OWLParseError", "parse_owl_file"]
