"""SQL-native graph query engine using PostgreSQL recursive CTEs.

Replaces NetworkX in-memory graph with native SQL graph traversal.
Uses recursive CTEs for BFS/DFS and tree reconstruction.

Requires: psycopg[binary,pool]>=3.1
"""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional, Set, Tuple

try:
    import psycopg
    from psycopg import Connection as PgConnection
    from psycopg.rows import dict_row

    PSYCOPG_VERSION = 3
except ImportError:
    # Fallback to psycopg2 for backward compatibility
    import psycopg2  # type: ignore
    from psycopg2.extensions import connection as PgConnection  # type: ignore

    PSYCOPG_VERSION = 2


# ============================================================================
# Data Classes (copied from engine.py for self-containment)
# ============================================================================


@dataclass
class QueryEntity:
    """查询识别的实体"""

    name: str  # 实体名称
    node_id: Optional[str] = None  # 图中节点ID
    node_type: Optional[str] = None  # 节点类型
    match_score: float = 0.0  # 匹配分数
    match_type: str = ""  # 匹配类型: exact, alias, pinyin, index_match
    matched_text: str = ""  # 在查询中匹配到的文本


@dataclass
class TreeNode:
    """树形节点"""

    id: str
    name: str
    node_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    children: List["TreeNode"] = field(default_factory=list)
    relation: str = ""  # 与父节点的关系
    level: int = 0


@dataclass
class SubgraphResult:
    """子图查询结果"""

    center_entity: QueryEntity
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    hops: int = 0
    tree: Optional[TreeNode] = None


# ============================================================================
# SQL Graph Query Engine
# ============================================================================


class SQLGraphQuery:
    """PostgreSQL-native graph query engine using recursive CTEs.

    Replaces NetworkX with SQL-based graph traversal:
    - BFS: Recursive CTE with level tracking
    - N-hop neighbors: Recursive CTE with depth limit
    - Tree building: parent-child tracking in CTE
    - Cycle detection: path array check
    """

    def __init__(self, db_config: Optional[Dict[str, Any]] = None, schema: str = "whale_datacloud"):
        """Initialize with DB config or auto-read from env vars.

        Args:
            db_config: Dict with host, port, user, password, database
                      If None, reads from DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME
            schema: Database schema name (default: whale_datacloud)
        """
        self.schema = schema
        self.db_config = db_config or self._load_db_config_from_env()
        self._name_index: Optional[Dict[str, List[Tuple[str, str, str]]]] = None

    def _load_db_config_from_env(self) -> Dict[str, Any]:
        """Load DB config from environment variables."""
        required = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"]
        missing = [v for v in required if not os.getenv(v)]
        if missing:
            raise ValueError(f"Missing DB env vars: {', '.join(missing)}")

        return {
            "host": os.environ["DB_HOST"],
            "port": int(os.environ["DB_PORT"]),
            "user": os.environ["DB_USER"],
            "password": os.environ["DB_PASSWORD"],
            "database": os.environ["DB_NAME"],
        }

    @contextmanager
    def _connect(self) -> Generator[PgConnection, None, None]:
        """Create database connection (psycopg3/psycopg2 compatible)."""
        conn = None
        try:
            if PSYCOPG_VERSION == 3:
                # psycopg3: use dbname instead of database
                config = self.db_config.copy()
                if "database" in config:
                    config["dbname"] = config.pop("database")
                conn = psycopg.connect(**config)
            else:
                # psycopg2
                conn = psycopg2.connect(**self.db_config)
            yield conn
        finally:
            if conn is not None:
                conn.close()

    def _build_name_index(self) -> Dict[str, List[Tuple[str, str, str]]]:
        """Build name -> term_id index from DB (cached).

        Returns:
            Dict mapping name -> [(term_id, node_type, match_type), ...]
        """
        if self._name_index is not None:
            return self._name_index

        index: Dict[str, List[Tuple[str, str, str]]] = {}

        with self._connect() as conn:
            with conn.cursor() as cur:
                # Index standard names from term table
                cur.execute(f"""
                    SELECT term_id, term_name, term_type_code
                    FROM {self.schema}.term
                """)
                for term_id, term_name, term_type in cur.fetchall():
                    if term_name not in index:
                        index[term_name] = []
                    index[term_name].append((term_id, term_type, "standard_name"))

                # Index aliases from term_tags JSONB
                cur.execute(f"""
                    SELECT term_id, term_name, term_type_code, term_tags
                    FROM {self.schema}.term
                    WHERE term_tags ? 'aliases'
                """)
                for term_id, term_name, term_type, tags in cur.fetchall():
                    aliases = tags.get("aliases", []) if isinstance(tags, dict) else []
                    for alias in aliases:
                        if alias and alias != term_name:
                            if alias not in index:
                                index[alias] = []
                            index[alias].append((term_id, term_type, "alias"))

        self._name_index = index
        return index

    def extract_entities(self, query: str) -> List[QueryEntity]:
        """Extract matching entities from natural language query.

        Strategy:
        1. Find all matches (exact, alias)
        2. Sort by: exact match > alias match, then by name length desc
        """
        name_index = self._build_name_index()
        entities: List[QueryEntity] = []
        matched_positions: Set[int] = set()

        # Sort by length desc for greedy matching
        sorted_names = sorted(name_index.keys(), key=len, reverse=True)

        for name in sorted_names:
            pattern = re.escape(name)
            for match in re.finditer(pattern, query):
                start, end = match.span()

                # Skip if overlaps with existing match
                if any(pos in matched_positions for pos in range(start, end)):
                    continue

                # Mark positions as matched
                for pos in range(start, end):
                    matched_positions.add(pos)

                # Add all matching entities for this name
                for term_id, node_type, match_type in name_index[name]:
                    score = 1.0 if match_type == "standard_name" else 0.9
                    entity = QueryEntity(
                        name=name,
                        node_id=term_id,
                        node_type=node_type,
                        match_score=score,
                        match_type=match_type,
                        matched_text=name,
                    )
                    entities.append(entity)

        # Deduplicate by term_id (keep highest score)
        seen_ids: Dict[str, QueryEntity] = {}
        unique_entities: List[QueryEntity] = []

        for entity in entities:
            if entity.node_id not in seen_ids:
                seen_ids[entity.node_id] = entity
                unique_entities.append(entity)
            elif entity.match_score > seen_ids[entity.node_id].match_score:
                old = seen_ids[entity.node_id]
                unique_entities.remove(old)
                seen_ids[entity.node_id] = entity
                unique_entities.append(entity)

        # Sort by score desc, then name length desc
        unique_entities.sort(key=lambda e: (-e.match_score, -len(e.matched_text)))

        return unique_entities

    def query_n_hop_subgraph(
        self,
        entity: QueryEntity,
        n_hops: int = 4,
        include_incoming: bool = True,
        include_outgoing: bool = True,
    ) -> SubgraphResult:
        """Query N-hop subgraph using SQL recursive CTE.

        Uses PostgreSQL recursive CTE for BFS traversal:
        - Tracks depth, path (for cycle detection)
        - Builds parent-child relationships for tree reconstruction
        - Returns both flat nodes/edges and hierarchical tree
        """
        if not entity.node_id:
            return SubgraphResult(center_entity=entity, hops=n_hops)

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    self._bfs_cte_sql(include_incoming, include_outgoing), (entity.node_id, n_hops)
                )

                rows = cur.fetchall()

                if not rows:
                    return SubgraphResult(center_entity=entity, hops=n_hops)

                # Build nodes, edges, and parent map from results
                nodes: Dict[str, Dict[str, Any]] = {}
                edges: List[Dict[str, Any]] = []
                parent_map: Dict[str, Tuple[str, str]] = {}

                for row in rows:
                    term_id, term_name, term_type, depth, path, parent_id, relation = row

                    # Store node
                    if term_id not in nodes:
                        nodes[term_id] = {
                            "_id": term_id,
                            "id": term_id,
                            "name": term_name,
                            "node_type": term_type,
                            "depth": depth,
                        }

                    # Store edge (if has parent)
                    if parent_id and relation:
                        parent_map[term_id] = (parent_id, relation)
                        edges.append(
                            {
                                "source": parent_id,
                                "target": term_id,
                                "relation": relation,
                                "data": {"relation": relation},
                            }
                        )

                # Build tree structure
                tree = self._build_tree_from_parent_map(entity.node_id, nodes, parent_map, n_hops)

                result = SubgraphResult(
                    center_entity=entity,
                    hops=n_hops,
                    nodes=list(nodes.values()),
                    edges=edges,
                    tree=tree,
                )

                return result

    def _bfs_cte_sql(self, include_incoming: bool, include_outgoing: bool) -> str:
        """Generate BFS recursive CTE SQL."""
        outgoing_sql = f"""
            SELECT 
                tr.source_term_id,
                tr.target_term_id,
                tr.relation_name,
                'out' AS direction
            FROM {self.schema}.term_relation tr
        """

        incoming_sql = f"""
            SELECT 
                tr.target_term_id AS source_term_id,
                tr.source_term_id AS target_term_id,
                tr.relation_name || '_REVERSE' AS relation_name,
                'in' AS direction
            FROM {self.schema}.term_relation tr
        """

        if include_outgoing and include_incoming:
            edge_sql = f"({outgoing_sql} UNION ALL {incoming_sql})"
        elif include_outgoing:
            edge_sql = f"({outgoing_sql})"
        elif include_incoming:
            edge_sql = f"({incoming_sql})"
        else:
            edge_sql = (
                "SELECT NULL::varchar, NULL::varchar, NULL::varchar, NULL::varchar WHERE false"
            )

        return f"""
            WITH RECURSIVE traversal AS (
                -- Anchor: starting node
                SELECT 
                    t.term_id,
                    t.term_name,
                    t.term_type_code,
                    0 AS depth,
                    ARRAY[t.term_id]::varchar(64)[] AS path,
                    NULL::varchar AS parent_id,
                    NULL::varchar AS relation
                FROM {self.schema}.term t
                WHERE t.term_id = %s
                
                UNION ALL
                
                -- Recursive: expand neighbors
                SELECT 
                    e.target_term_id,
                    t2.term_name,
                    t2.term_type_code,
                    tr.depth + 1,
                    (tr.path || e.target_term_id)::varchar(64)[],
                    tr.term_id,
                    e.relation_name
                FROM traversal tr
                JOIN {edge_sql} e ON tr.term_id = e.source_term_id
                JOIN {self.schema}.term t2 ON t2.term_id = e.target_term_id
                WHERE tr.depth < %s
                  AND NOT e.target_term_id = ANY(tr.path)
            )
            
            SELECT 
                term_id,
                term_name,
                term_type_code,
                depth,
                path,
                parent_id,
                relation
            FROM traversal
            
        """

    def _build_tree_from_parent_map(
        self,
        root_id: str,
        nodes: Dict[str, Dict[str, Any]],
        parent_map: Dict[str, Tuple[str, str]],
        max_depth: int,
    ) -> TreeNode:
        """Build TreeNode hierarchy from parent-child relationships."""
        root_data = nodes.get(root_id, {})

        root = TreeNode(
            id=root_id,
            name=root_data.get("name", root_id),
            node_type=root_data.get("node_type", "Unknown"),
            properties={},
            level=0,
        )

        visited: Set[str] = {root_id}
        queue: List[Tuple[str, TreeNode, int]] = [(root_id, root, 0)]

        while queue:
            current_id, current_node, current_level = queue.pop(0)

            if current_level >= max_depth:
                continue

            # Find all children
            for child_id, (parent_id, relation) in parent_map.items():
                if parent_id == current_id and child_id not in visited:
                    visited.add(child_id)
                    child_data = nodes.get(child_id, {})

                    display_relation = relation
                    if relation.endswith("_REVERSE"):
                        display_relation = f"<-{relation[:-8]}"

                    child = TreeNode(
                        id=child_id,
                        name=child_data.get("name", child_id),
                        node_type=child_data.get("node_type", "Unknown"),
                        properties={},
                        relation=display_relation,
                        level=current_level + 1,
                    )

                    current_node.children.append(child)
                    queue.append((child_id, child, current_level + 1))

        return root

    def query(
        self,
        natural_language: str,
        n_hops: int = 4,
        include_incoming: bool = True,
        include_outgoing: bool = True,
    ) -> Dict[str, Any]:
        """Main query interface."""
        entities = self.extract_entities(natural_language)

        if not entities:
            return {
                "query": natural_language,
                "entities_found": [],
                "results": [],
                "message": "未找到匹配的实体",
            }

        results = []
        for entity in entities:
            subgraph = self.query_n_hop_subgraph(
                entity,
                n_hops=n_hops,
                include_incoming=include_incoming,
                include_outgoing=include_outgoing,
            )
            results.append(self._format_subgraph_result(subgraph))

        return {
            "query": natural_language,
            "entities_found": [
                {
                    "name": e.name,
                    "node_id": e.node_id,
                    "node_type": e.node_type,
                    "match_type": e.match_type,
                    "match_score": e.match_score,
                }
                for e in entities
            ],
            "n_hops": n_hops,
            "results": results,
        }

    def _format_subgraph_result(self, subgraph: SubgraphResult) -> Dict[str, Any]:
        """Format subgraph to JSON-serializable dict."""
        return {
            "center_entity": {
                "name": subgraph.center_entity.name,
                "node_id": subgraph.center_entity.node_id,
                "node_type": subgraph.center_entity.node_type,
                "match_type": subgraph.center_entity.match_type,
            },
            "hops": subgraph.hops,
            "node_count": len(subgraph.nodes),
            "edge_count": len(subgraph.edges),
            "tree": self._tree_to_dict(subgraph.tree) if subgraph.tree else None,
        }

    def _tree_to_dict(self, tree: TreeNode) -> Dict[str, Any]:
        """Convert TreeNode to dict."""
        return {
            "id": tree.id,
            "name": tree.name,
            "node_type": tree.node_type,
            "properties": tree.properties,
            "relation": tree.relation,
            "level": tree.level,
            "children": [self._tree_to_dict(child) for child in tree.children],
        }


# ============================================================================
# Backward Compatibility Wrapper
# ============================================================================


class SQLKnowledgeGraphQuery:
    """Backward-compatible wrapper - delegates to SQLGraphQuery."""

    def __init__(self, db_config: Optional[Dict[str, Any]] = None, default_hops: int = 4):
        """Initialize SQL-native graph query.

        Args:
            db_config: Database config dict (or auto-read from env)
            default_hops: Default number of hops for queries
        """
        self.sql_engine = SQLGraphQuery(db_config=db_config)
        self.default_hops = default_hops

    def query(
        self,
        question: str,
        n_hops: Optional[int] = None,
        include_incoming: bool = True,
        include_outgoing: bool = True,
    ) -> Dict[str, Any]:
        """Execute natural language query."""
        hops = n_hops or self.default_hops
        return self.sql_engine.query(
            question,
            n_hops=hops,
            include_incoming=include_incoming,
            include_outgoing=include_outgoing,
        )

    def query_entities(self, question: str, n_hops: Optional[int] = None) -> List[QueryEntity]:
        """Query and return matching entity list."""
        return self.sql_engine.extract_entities(question)


# ============================================================================
# Convenience Functions
# ============================================================================


def create_sql_graph_query(
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    database: Optional[str] = None,
    schema: str = "whale_datacloud",
) -> SQLGraphQuery:
    """Factory function to create SQLGraphQuery with explicit config."""
    config = {
        "host": host or os.getenv("DB_HOST", "localhost"),
        "port": port or int(os.getenv("DB_PORT", "5432")),
        "user": user or os.getenv("DB_USER", "postgres"),
        "password": password or os.getenv("DB_PASSWORD", ""),
        "database": database or os.getenv("DB_NAME", "postgres"),
    }
    return SQLGraphQuery(db_config=config, schema=schema)


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "SQLGraphQuery",
    "SQLKnowledgeGraphQuery",
    "QueryEntity",
    "TreeNode",
    "SubgraphResult",
    "create_sql_graph_query",
]


# ============================================================================
# SQL Graph Query Engine
# ============================================================================


class SQLGraphQuery:
    """PostgreSQL-native graph query engine using recursive CTEs.

    Replaces NetworkX with SQL-based graph traversal:
    - BFS: Recursive CTE with level tracking
    - N-hop neighbors: Recursive CTE with depth limit
    - Tree building: parent-child tracking in CTE
    - Cycle detection: path array check
    """

    def __init__(self, db_config: Optional[Dict[str, Any]] = None, schema: str = "whale_datacloud"):
        """Initialize with DB config or auto-read from env vars.

        Args:
            db_config: Dict with host, port, user, password, database
                      If None, reads from DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME
            schema: Database schema name (default: whale_datacloud)
        """
        self.schema = schema
        self.db_config = db_config or self._load_db_config_from_env()
        self._name_index: Optional[Dict[str, List[Tuple[str, str, str]]]] = None

    def _load_db_config_from_env(self) -> Dict[str, Any]:
        """Load DB config from environment variables."""
        required = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"]
        missing = [v for v in required if not os.getenv(v)]
        if missing:
            raise ValueError(f"Missing DB env vars: {', '.join(missing)}")

        return {
            "host": os.environ["DB_HOST"],
            "port": int(os.environ["DB_PORT"]),
            "user": os.environ["DB_USER"],
            "password": os.environ["DB_PASSWORD"],
            "database": os.environ["DB_NAME"],
        }

    @contextmanager
    def _connect(self) -> Generator[PgConnection, None, None]:
        """Create database connection (psycopg3/psycopg2 compatible)."""
        conn = None
        try:
            if PSYCOPG_VERSION == 3:
                # psycopg3: use dbname instead of database
                config = self.db_config.copy()
                if "database" in config:
                    config["dbname"] = config.pop("database")
                conn = psycopg.connect(**config)
            else:
                # psycopg2
                conn = psycopg2.connect(**self.db_config)
            yield conn
        finally:
            if conn is not None:
                conn.close()

    def _build_name_index(self) -> Dict[str, List[Tuple[str, str, str]]]:
        """Build name -> term_id index from DB (cached).

        Returns:
            Dict mapping name -> [(term_id, node_type, match_type), ...]
        """
        if self._name_index is not None:
            return self._name_index

        index: Dict[str, List[Tuple[str, str, str]]] = {}

        with self._connect() as conn:
            with conn.cursor() as cur:
                # Index standard names from term table
                cur.execute(f"""
                    SELECT term_id, term_name, term_type_code
                    FROM {self.schema}.term
                """)
                for term_id, term_name, term_type in cur.fetchall():
                    if term_name not in index:
                        index[term_name] = []
                    index[term_name].append((term_id, term_type, "standard_name"))

                # Index aliases from term_tags JSONB
                cur.execute(f"""
                    SELECT term_id, term_name, term_type_code, term_tags
                    FROM {self.schema}.term
                    WHERE term_tags ? 'aliases'
                """)
                for term_id, term_name, term_type, tags in cur.fetchall():
                    aliases = tags.get("aliases", []) if isinstance(tags, dict) else []
                    for alias in aliases:
                        if alias and alias != term_name:
                            if alias not in index:
                                index[alias] = []
                            index[alias].append((term_id, term_type, "alias"))

        self._name_index = index
        return index

    def extract_entities(self, query: str) -> List[QueryEntity]:
        """Extract matching entities from natural language query.

        Strategy:
        1. Find all matches (exact, alias)
        2. Sort by: exact match > alias match, then by name length desc
        """
        name_index = self._build_name_index()
        entities: List[QueryEntity] = []
        matched_positions: Set[int] = set()

        # Sort by length desc for greedy matching
        sorted_names = sorted(name_index.keys(), key=len, reverse=True)

        import re

        for name in sorted_names:
            pattern = re.escape(name)
            for match in re.finditer(pattern, query):
                start, end = match.span()

                # Skip if overlaps with existing match
                if any(pos in matched_positions for pos in range(start, end)):
                    continue

                # Mark positions as matched
                for pos in range(start, end):
                    matched_positions.add(pos)

                # Add all matching entities for this name
                for term_id, node_type, match_type in name_index[name]:
                    score = 1.0 if match_type == "standard_name" else 0.9
                    entity = QueryEntity(
                        name=name,
                        node_id=term_id,
                        node_type=node_type,
                        match_score=score,
                        match_type=match_type,
                        matched_text=name,
                    )
                    entities.append(entity)

        # Deduplicate by term_id (keep highest score)
        seen_ids: Dict[str, QueryEntity] = {}
        unique_entities: List[QueryEntity] = []

        for entity in entities:
            if entity.node_id not in seen_ids:
                seen_ids[entity.node_id] = entity
                unique_entities.append(entity)
            elif entity.match_score > seen_ids[entity.node_id].match_score:
                old = seen_ids[entity.node_id]
                unique_entities.remove(old)
                seen_ids[entity.node_id] = entity
                unique_entities.append(entity)

        # Sort by score desc, then name length desc
        unique_entities.sort(key=lambda e: (-e.match_score, -len(e.matched_text)))

        return unique_entities

    def query_n_hop_subgraph(
        self,
        entity: QueryEntity,
        n_hops: int = 4,
        include_incoming: bool = True,
        include_outgoing: bool = True,
    ) -> SubgraphResult:
        """Query N-hop subgraph using SQL recursive CTE.

        Uses PostgreSQL recursive CTE for BFS traversal:
        - Tracks depth, path (for cycle detection)
        - Builds parent-child relationships for tree reconstruction
        - Returns both flat nodes/edges and hierarchical tree
        """
        if not entity.node_id:
            return SubgraphResult(center_entity=entity, hops=n_hops)

        with self._connect() as conn:
            with conn.cursor() as cur:
                # Single SQL query for BFS N-hop traversal
                # Returns: term_id, term_name, term_type_code, depth, path, parent_id, relation
                cur.execute(
                    self._bfs_cte_sql(include_incoming, include_outgoing), (entity.node_id, n_hops)
                )

                rows = cur.fetchall()

                if not rows:
                    return SubgraphResult(center_entity=entity, hops=n_hops)

                # Build nodes, edges, and parent map from results
                nodes: Dict[str, Dict[str, Any]] = {}
                edges: List[Dict[str, Any]] = []
                parent_map: Dict[str, Tuple[str, str]] = {}  # child -> (parent, relation)

                for row in rows:
                    term_id, term_name, term_type, depth, path, parent_id, relation = row

                    # Store node
                    if term_id not in nodes:
                        nodes[term_id] = {
                            "_id": term_id,
                            "id": term_id,
                            "name": term_name,
                            "node_type": term_type,
                            "depth": depth,
                        }

                    # Store edge (if has parent)
                    if parent_id and relation:
                        parent_map[term_id] = (parent_id, relation)
                        edges.append(
                            {
                                "source": parent_id,
                                "target": term_id,
                                "relation": relation,
                                "data": {"relation": relation},
                            }
                        )

                # Build tree structure
                tree = self._build_tree_from_parent_map(entity.node_id, nodes, parent_map, n_hops)

                result = SubgraphResult(
                    center_entity=entity,
                    hops=n_hops,
                    nodes=list(nodes.values()),
                    edges=edges,
                    tree=tree,
                )

                return result

    def _bfs_cte_sql(self, include_incoming: bool, include_outgoing: bool) -> str:
        """Generate BFS recursive CTE SQL.

        The CTE traverses the graph from a starting node:
        - Anchor: starting term_id
        - Recursive: expand via term_relation (outgoing and/or incoming)
        - Cycle detection: path array tracking
        - Depth limit: n_hops parameter
        """
        # Base CTE structure
        outgoing_sql = f"""
            SELECT 
                tr.source_term_id,
                tr.target_term_id,
                tr.relation_name,
                'out' AS direction
            FROM {self.schema}.term_relation tr
        """

        incoming_sql = f"""
            SELECT 
                tr.target_term_id AS source_term_id,
                tr.source_term_id AS target_term_id,
                tr.relation_name || '_REVERSE' AS relation_name,
                'in' AS direction
            FROM {self.schema}.term_relation tr
        """

        # Combine edge directions based on parameters
        if include_outgoing and include_incoming:
            edge_sql = f"({outgoing_sql} UNION ALL {incoming_sql})"
        elif include_outgoing:
            edge_sql = f"({outgoing_sql})"
        elif include_incoming:
            edge_sql = f"({incoming_sql})"
        else:
            # No traversal - just return starting node
            edge_sql = (
                "SELECT NULL::varchar, NULL::varchar, NULL::varchar, NULL::varchar WHERE false"
            )

        return f"""
            WITH RECURSIVE traversal AS (
                -- Anchor: starting node (depth 0)
                SELECT 
                    t.term_id,
                    t.term_name,
                    t.term_type_code,
                    0 AS depth,
                    ARRAY[t.term_id]::varchar(64)[] AS path,
                    NULL::varchar AS parent_id,
                    NULL::varchar AS relation
                FROM {self.schema}.term t
                WHERE t.term_id = %s
                
                UNION ALL
                
                -- Recursive: expand neighbors
                SELECT 
                    e.target_term_id,
                    t2.term_name,
                    t2.term_type_code,
                    tr.depth + 1,
                    (tr.path || e.target_term_id)::varchar(64)[],
                    tr.term_id,  -- current becomes parent
                    e.relation_name
                FROM traversal tr
                JOIN {edge_sql} e ON tr.term_id = e.source_term_id
                JOIN {self.schema}.term t2 ON t2.term_id = e.target_term_id
                WHERE tr.depth < %s
                  AND NOT e.target_term_id = ANY(tr.path)  -- cycle detection
            )
            
            SELECT 
                term_id,
                term_name,
                term_type_code,
                depth,
                path,
                parent_id,
                relation
            FROM traversal
            
        """

    def _build_tree_from_parent_map(
        self,
        root_id: str,
        nodes: Dict[str, Dict[str, Any]],
        parent_map: Dict[str, Tuple[str, str]],
        max_depth: int,
    ) -> TreeNode:
        """Build TreeNode hierarchy from parent-child relationships.

        Uses BFS to construct tree from flat parent_map:
        - parent_map[child_id] = (parent_id, relation)
        """
        root_data = nodes.get(root_id, {})

        root = TreeNode(
            id=root_id,
            name=root_data.get("name", root_id),
            node_type=root_data.get("node_type", "Unknown"),
            properties={},
            level=0,
        )

        # BFS to attach children
        visited: Set[str] = {root_id}
        queue: List[Tuple[str, TreeNode, int]] = [(root_id, root, 0)]

        while queue:
            current_id, current_node, current_level = queue.pop(0)

            if current_level >= max_depth:
                continue

            # Find all children of current node
            for child_id, (parent_id, relation) in parent_map.items():
                if parent_id == current_id and child_id not in visited:
                    visited.add(child_id)
                    child_data = nodes.get(child_id, {})

                    # Format relation for display
                    display_relation = relation
                    if relation.endswith("_REVERSE"):
                        display_relation = f"<-{relation[:-8]}"

                    child = TreeNode(
                        id=child_id,
                        name=child_data.get("name", child_id),
                        node_type=child_data.get("node_type", "Unknown"),
                        properties={},
                        relation=display_relation,
                        level=current_level + 1,
                    )

                    current_node.children.append(child)
                    queue.append((child_id, child, current_level + 1))

        return root

    def query(
        self,
        natural_language: str,
        n_hops: int = 4,
        include_incoming: bool = True,
        include_outgoing: bool = True,
    ) -> Dict[str, Any]:
        """Main query interface - matches original API."""
        # 1. Extract entities
        entities = self.extract_entities(natural_language)

        if not entities:
            return {
                "query": natural_language,
                "entities_found": [],
                "results": [],
                "message": "未找到匹配的实体",
            }

        # 2. Query subgraph for each entity
        results = []
        for entity in entities:
            subgraph = self.query_n_hop_subgraph(
                entity,
                n_hops=n_hops,
                include_incoming=include_incoming,
                include_outgoing=include_outgoing,
            )
            results.append(self._format_subgraph_result(subgraph))

        return {
            "query": natural_language,
            "entities_found": [
                {
                    "name": e.name,
                    "node_id": e.node_id,
                    "node_type": e.node_type,
                    "match_type": e.match_type,
                    "match_score": e.match_score,
                }
                for e in entities
            ],
            "n_hops": n_hops,
            "results": results,
        }

    def _format_subgraph_result(self, subgraph: SubgraphResult) -> Dict[str, Any]:
        """Format subgraph to JSON-serializable dict."""
        return {
            "center_entity": {
                "name": subgraph.center_entity.name,
                "node_id": subgraph.center_entity.node_id,
                "node_type": subgraph.center_entity.node_type,
                "match_type": subgraph.center_entity.match_type,
            },
            "hops": subgraph.hops,
            "node_count": len(subgraph.nodes),
            "edge_count": len(subgraph.edges),
            "tree": self._tree_to_dict(subgraph.tree) if subgraph.tree else None,
        }

    def _tree_to_dict(self, tree: TreeNode) -> Dict[str, Any]:
        """Convert TreeNode to dict."""
        return {
            "id": tree.id,
            "name": tree.name,
            "node_type": tree.node_type,
            "properties": tree.properties,
            "relation": tree.relation,
            "level": tree.level,
            "children": [self._tree_to_dict(child) for child in tree.children],
        }


# ============================================================================
# Backward Compatibility Wrapper
# ============================================================================


class KnowledgeGraphQuery:
    """Backward-compatible wrapper that replaces NetworkX with SQL.

    Maintains same interface as original KnowledgeGraphQuery but uses
    SQLGraphQuery internally for all graph operations.
    """

    def __init__(
        self,
        graph_files: Optional[List[str]] = None,  # Ignored - kept for compatibility
        db_config: Optional[Dict[str, Any]] = None,
        default_hops: int = 4,
    ):
        """Initialize SQL-native graph query.

        Args:
            graph_files: DEPRECATED - kept for API compatibility, ignored
            db_config: Database config dict (or auto-read from env)
            default_hops: Default number of hops for queries
        """
        self.sql_engine = SQLGraphQuery(db_config=db_config)
        self.default_hops = default_hops

        if graph_files:
            import warnings

            warnings.warn(
                "graph_files parameter is deprecated - data is loaded from PostgreSQL",
                DeprecationWarning,
                stacklevel=2,
            )

    def query(
        self,
        question: str,
        n_hops: Optional[int] = None,
        include_incoming: bool = True,
        include_outgoing: bool = True,
    ) -> Dict[str, Any]:
        """Execute natural language query."""
        hops = n_hops or self.default_hops
        return self.sql_engine.query(
            question,
            n_hops=hops,
            include_incoming=include_incoming,
            include_outgoing=include_outgoing,
        )

    def query_entities(self, question: str, n_hops: Optional[int] = None) -> List[QueryEntity]:
        """Query and return matching entity list."""
        return self.sql_engine.extract_entities(question)


# ============================================================================
# Convenience Functions
# ============================================================================


def create_sql_graph_query(
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    database: Optional[str] = None,
    schema: str = "whale_datacloud",
) -> SQLGraphQuery:
    """Factory function to create SQLGraphQuery with explicit config.

    Args override environment variables.
    """
    config = {
        "host": host or os.getenv("DB_HOST", "localhost"),
        "port": port or int(os.getenv("DB_PORT", "5432")),
        "user": user or os.getenv("DB_USER", "postgres"),
        "password": password or os.getenv("DB_PASSWORD", ""),
        "database": database or os.getenv("DB_NAME", "postgres"),
    }
    return SQLGraphQuery(db_config=config, schema=schema)


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "SQLGraphQuery",
    "KnowledgeGraphQuery",
    "QueryEntity",
    "TreeNode",
    "SubgraphResult",
    "create_sql_graph_query",
]
