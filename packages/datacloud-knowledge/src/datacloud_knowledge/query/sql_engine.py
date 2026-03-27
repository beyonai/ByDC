"""SQL-native graph query engine using PostgreSQL recursive CTEs.

Native SQL graph traversal.
Uses recursive CTEs for BFS/DFS and tree reconstruction.

Requires: psycopg[binary,pool]>=3.1
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import md5
from pathlib import Path
from typing import Any, Dict, FrozenSet, Generator, List, Mapping, Optional, Set, Tuple
from collections import defaultdict



from psycopg import Connection as PgConnection
from psycopg.sql import SQL, Identifier
from psycopg_pool import ConnectionPool

from .fuzzy import (
    FuzzySuggestion,
    FuzzyConfig,
    UnmatchedSpan,
    create_matcher,
    match_all_unmatched,
)
from .vocab_cache import VocabularyCache

# ============================================================================
# Data Classes
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


class SQLKnowledgeGraphQuery:
    """PostgreSQL-native graph query engine using recursive CTEs.

    SQL-based graph traversal:
    - BFS: Recursive CTE with level tracking
    - N-hop neighbors: Recursive CTE with depth limit
    - Tree building: parent-child tracking in CTE
    - Cycle detection: path array check
    """

    def __init__(
        self,
        db_config: Optional[Dict[str, Any]] = None,
        schema: str = "whale_datacloud",
        default_hops: int = 4,
        pool_min: int = 2,
        pool_max: int = 10,
        cache_dir: Optional[Path] = None,
        enable_query_cache: bool = True,
        query_cache_maxsize: int = 1000,
    ):
        """Initialize with DB config or auto-read from env vars.

        Args:
            db_config: Dict with host, port, user, password, database
                      If None, reads from DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME
            schema: Database schema name (default: whale_datacloud)
            default_hops: Default number of hops for queries
            pool_min: Minimum connection pool size
            pool_max: Maximum connection pool size
            cache_dir: Directory for mmap cache (default: ~/.cache/datacloud_knowledge
                      or DATACLOUD_KNOWLEDGE_CACHE_DIR env var)
            enable_query_cache: Enable LRU cache for query results (default: True)
            query_cache_maxsize: Max entries in LRU cache (default: 1000)
        """
        self.schema = schema
        self.default_hops = default_hops
        self.db_config = db_config or self._load_db_config_from_env()
        self._name_index: Optional[Dict[str, List[Tuple[str, str, str]]]] = None
        self._vocabulary_set: Optional[Set[str]] = None
        self._pool: Optional["ConnectionPool"] = None
        self._pool_min = pool_min
        self._pool_max = pool_max
        
        # mmap-based cache for vocabulary and name index
        self._cache = VocabularyCache(schema=schema, cache_dir=cache_dir)
        
        # Fuzzy matching config (using rapidfuzz, no pre-built index needed)
        self._fuzzy_config: FuzzyConfig = FuzzyConfig()
        self._fuzzy_stopwords: FrozenSet[str] = frozenset()
        self._fuzzy_term_metadata: Optional[Mapping[str, Tuple[Tuple[str, str, str], ...]]] = None
        
        # Query result cache settings
        self._enable_query_cache = enable_query_cache
        self._query_cache_maxsize = query_cache_maxsize
        self._query_cache: Dict[str, Tuple[Dict[str, Any], int]] = {}  # key -> (result, access_count)
        self._cache_order: List[str] = []  # for LRU eviction

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

    def _get_pool(self) -> "ConnectionPool":
        """Get or create connection pool."""
        if self._pool is None:
            if ConnectionPool is None:
                raise RuntimeError("psycopg_pool not available, install psycopg[pool]")
            config = self.db_config.copy()
            if "database" in config:
                config["dbname"] = config.pop("database")
            self._pool = ConnectionPool(
                kwargs=config,
                min_size=self._pool_min,
                max_size=self._pool_max,
                open=True,
                max_idle=10,  # Close idle connections after 10 seconds
            )
        return self._pool

    @contextmanager
    def _connect(self) -> Generator[PgConnection, None, None]:
        """Get connection from pool."""
        pool = self._get_pool()
        with pool.connection() as conn:
            yield conn

    def close(self, timeout: float = 0.5) -> None:
        """Close connection pool.
        
        Args:
            timeout: Max seconds to wait for pool to close (default: 0.5s)
        """
        if self._pool is not None:
            try:
                # Try graceful close with short timeout
                self._pool.close(timeout=timeout)
            except Exception:
                pass
            self._pool = None
    def prewarm(self, force_rebuild: bool = False, fast: bool = True, warm_pool: bool = True) -> bool:
        """Pre-warm indexes and connection pool for faster subsequent queries.
        
        Uses mmap cache to avoid reloading from DB on restart.
        
        Args:
            force_rebuild: If True, ignore cache and rebuild from DB
            fast: If True, skip DB validation for faster startup (default: True)
                  Use fast=False when data might have changed externally
            warm_pool: If True, pre-warm connection pool (default: True)
        
        Returns:
            True if cache was used, False if rebuilt from DB
        """
        # 1. Try to load from mmap cache (fast mode: skip DB validation)
        if not force_rebuild:
            if fast:
                # Fast mode: load directly from mmap without DB validation
                vocab, index = self._cache.load_fast()
                if vocab is not None and index is not None:
                    self._vocabulary_set = vocab
                    self._name_index = index
                    
                    # Warm connection pool if requested
                    if warm_pool:
                        self._warm_connection_pool()
                    
                    return True  # Cache hit (fast)
            else:
                # Safe mode: validate with DB
                with self._connect() as conn:
                    vocab, index = self._cache.load(conn)
                    if vocab is not None and index is not None:
                        self._vocabulary_set = vocab
                        self._name_index = index
                        
                        return True  # Cache hit
        
        # 2. Cache miss or force rebuild - load from DB
        self._build_name_index()
        self._build_vocabulary_set()
        
        # 3. Save to mmap cache
        with self._connect() as conn:
            self._cache.save(conn, self._vocabulary_set or set(), self._name_index or {})
        
        return False  # Cache miss, rebuilt from DB
    
    def _warm_connection_pool(self) -> None:
        """Warm up connection pool by executing a simple query.
        
        This establishes connections in the pool upfront,
        so subsequent queries don't pay the connection setup cost.
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT 1 FROM {self.schema}.term LIMIT 1")  # type: ignore[arg-type]
                    cur.fetchall()
        except Exception:
            pass  # Ignore errors during warmup

    def _format_knowledge_content(self, summary: Optional[str], desc: Optional[str]) -> str:
        """Format knowledge summary and description into a single string.
        
        Args:
            summary: Knowledge summary (will be bracketed)
            desc: Full description
            
        Returns:
            Formatted knowledge string
        """
        parts = []
        if summary:
            parts.append(f"【{summary}】")
        if desc:
            parts.append(desc)
        return "\n".join(parts) if parts else ""
    
    def _ensure_fuzzy_matcher(self) -> None:
        """Ensure fuzzy matcher is ready for use.
        
        rapidfuzz does not require pre-built index, so this just ensures
        term_metadata is available from name_index.
        """
        if self._fuzzy_term_metadata is not None:
            return  # Already ready
        
        if self._name_index is None:
            return  # No name_index available
        
        # Convert name_index to the format expected by create_matcher
        term_metadata: Dict[str, Tuple[Tuple[str, str, str], ...]] = {
            name: tuple(postings)
            for name, postings in self._name_index.items()
        }
        
        (
            self._fuzzy_term_metadata,
            self._fuzzy_config,
            self._fuzzy_stopwords,
        ) = create_matcher(term_metadata)

    def _build_name_index(self) -> Dict[str, List[Tuple[str, str, str]]]:
        """Build name -> term_id index from DB (cached).
        
        Uses term_name table to get all names (standard names + aliases)
        based on the term-term_name-term_vocabulary relationship:
        - term: stores term metadata (term_id, term_name as standard name, term_type_code)
        - term_name: stores all name_text values for each term (standard + aliases)
        - term_vocabulary: stores unique vocabulary words for jieba dictionary

        Returns:
            Dict mapping name -> [(term_id, node_type, match_type), ...]
        """
        if self._name_index is not None:
            return self._name_index

        index: Dict[str, List[Tuple[str, str, str]]] = {}

        with self._connect() as conn:
            with conn.cursor() as cur:
                # Query all names from term_name table joined with term table
                # to get term_type_code and determine if it's a standard name or alias
                query = f"""
                    SELECT
                        t.term_id,
                        t.term_name AS standard_name,
                        t.term_type_code,
                        tn.name_text,
                        CASE
                            WHEN tn.name_text = t.term_name THEN 'standard_name'
                            ELSE 'alias'
                        END AS match_type
                    FROM {self.schema}.term_name tn
                    JOIN {self.schema}.term t ON tn.term_id = t.term_id
                """
                cur.execute(SQL(query))  # type: ignore
                for term_id, standard_name, term_type, name_text, match_type in cur.fetchall():
                    if name_text not in index:
                        index[name_text] = []
                    index[name_text].append((term_id, term_type, match_type))

        self._name_index = index
        return index

    def _build_vocabulary_set(self) -> Set[str]:
        """Build vocabulary set from term_vocabulary table for word segmentation.

        Queries term_vocabulary table which stores unique vocabulary words
        (deduplicated from term_name.name_text) for efficient matching.

        Returns:
            Set of unique vocabulary words for maximum matching algorithm.
        """
        if self._vocabulary_set is not None:
            return self._vocabulary_set

        vocab: Set[str] = set()

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT word FROM {self.schema}.term_vocabulary")  # type: ignore[arg-type]
                for row in cur.fetchall():
                    if row[0]:
                        vocab.add(row[0])

        self._vocabulary_set = vocab
        return vocab

    def _forward_max_match(self, text: str, vocab: Set[str]) -> List[Tuple[str, int, int]]:
        """Forward Maximum Matching (FMM) algorithm.

        Args:
            text: Input text to segment
            vocab: Vocabulary set for matching

        Returns:
            List of (word, start_pos, end_pos) tuples
        """
        if not text:
            return []

        max_word_len = max((len(w) for w in vocab), default=1)
        result: List[Tuple[str, int, int]] = []
        pos = 0
        text_len = len(text)

        while pos < text_len:
            # Try longest possible word first
            matched = False
            for length in range(min(max_word_len, text_len - pos), 0, -1):
                word = text[pos : pos + length]
                if word in vocab:
                    result.append((word, pos, pos + length))
                    pos += length
                    matched = True
                    break

            if not matched:
                # Single character as unmatched
                pos += 1

        return result

    def _backward_max_match(self, text: str, vocab: Set[str]) -> List[Tuple[str, int, int]]:
        """Backward Maximum Matching (BMM) algorithm.

        Args:
            text: Input text to segment
            vocab: Vocabulary set for matching

        Returns:
            List of (word, start_pos, end_pos) tuples
        """
        if not text:
            return []

        max_word_len = max((len(w) for w in vocab), default=1)
        result: List[Tuple[str, int, int]] = []
        pos = len(text)

        while pos > 0:
            # Try longest possible word first (from right)
            matched = False
            for length in range(min(max_word_len, pos), 0, -1):
                start = pos - length
                word = text[start:pos]
                if word in vocab:
                    result.append((word, start, pos))
                    pos = start
                    matched = True
                    break

            if not matched:
                # Single character as unmatched
                pos -= 1

        # Reverse to get left-to-right order
        result.reverse()
        return result

    def _bidirectional_max_match(self, text: str, vocab: Set[str]) -> List[Tuple[str, int, int]]:
        """Bidirectional Maximum Matching algorithm.

        Combines FMM and BMM, selects the better result based on:
        1. Fewer words is better
        2. If same word count, fewer single-char words is better

        Args:
            text: Input text to segment
            vocab: Vocabulary set for matching

        Returns:
            List of (word, start_pos, end_pos) tuples
        """
        fmm_result = self._forward_max_match(text, vocab)
        bmm_result = self._backward_max_match(text, vocab)

        # Count matched words (not single chars)
        fmm_words = [w for w, s, e in fmm_result if e - s > 1 or w in vocab]
        bmm_words = [w for w, s, e in bmm_result if e - s > 1 or w in vocab]

        # Count single-char words
        fmm_single = sum(1 for w, s, e in fmm_result if e - s == 1 and w not in vocab)
        bmm_single = sum(1 for w, s, e in bmm_result if e - s == 1 and w not in vocab)

        # Selection strategy
        if len(fmm_words) > len(bmm_words):
            return bmm_result
        elif len(fmm_words) < len(bmm_words):
            return fmm_result
        else:
            # Same word count, choose one with fewer single-char words
            if fmm_single <= bmm_single:
                return fmm_result
            else:
                return bmm_result

    def extract_entities(
        self, query: str
    ) -> Tuple[List[QueryEntity], List[FuzzySuggestion]]:
        """Extract matching entities and fuzzy suggestions from query.

        Uses Bidirectional Maximum Matching (BIMM) algorithm for word segmentation,
        then maps matched words to term entities via name_index.

        Requires prewarm() to be called first to load vocabulary and name_index.

        Algorithm:
        1. Apply bidirectional max matching to segment query
        2. Map matched words to term entities (dedupe by term_id)
        3. Collect unmatched spans and perform fuzzy matching

        Returns:
            (entities, fuzzy_suggestions) tuple where:
            - entities: List of exactly matched QueryEntity (for graph queries)
            - fuzzy_suggestions: List of FuzzySuggestion for display only
        """
        # Ensure vocabulary and name_index are loaded
        if self._vocabulary_set is None or self._name_index is None:
            # Auto-prewarm if not done yet
            self.prewarm()

        vocab = self._vocabulary_set
        name_index = self._name_index

        # Apply bidirectional maximum matching
        matched_words = self._bidirectional_max_match(query, vocab or set())

        # Initialize fuzzy_suggestions as empty list
        fuzzy_suggestions: List[FuzzySuggestion] = []

        # Dedupe by term_id while iterating, O(1) lookup
        # term_id -> (word, term_type, match_type)
        seen: Dict[str, Tuple[str, str, str]] = {}

        for word, start, end in matched_words:
            if name_index is None or word not in name_index:
                continue

            for term_id, term_type, match_type in name_index[word]:
                # Keep first occurrence for each term_id
                if term_id not in seen:
                    seen[term_id] = (word, term_type, match_type)

        # Create entity objects
        entities: List[QueryEntity] = [
            QueryEntity(
                name=data[0],
                node_id=term_id,
                node_type=data[1],
                match_score=1.0 if data[2] == "standard_name" else 0.9,
                match_type=data[2],
                matched_text=data[0],
            )
            for term_id, data in seen.items()
        ]

        # Perform fuzzy matching on unmatched spans
        fuzzy_suggestions = self._fuzzy_match_unmatched(query, matched_words, name_index)

        return entities, fuzzy_suggestions

    def _fuzzy_match_unmatched(
        self,
        query: str,
        matched_words: List[Tuple[str, int, int]],
        name_index: Optional[Dict[str, List[Tuple[str, str, str]]]]
    ) -> List[FuzzySuggestion]:
        """Perform fuzzy matching on unmatched text spans.

        Finds contiguous regions of the query that were NOT covered by exact matches,
        then performs fuzzy matching using rapidfuzz.

        Args:
            query: The original query string
            matched_words: List of (word, start, end) tuples from bidirectional max matching
            name_index: Name index for checking if words are valid matches

        Returns:
            List of FuzzySuggestion for display (not used in graph queries)
        """
        # Build a set of covered character positions
        covered_positions: Set[int] = set()
        for word, start, end in matched_words:
            if name_index is not None and word in name_index:
                covered_positions.update(range(start, end))

        # Find uncovered contiguous regions
        unmatched_spans: List[UnmatchedSpan] = []
        if len(covered_positions) < len(query):
            i = 0
            while i < len(query):
                if i not in covered_positions:
                    start = i
                    while i < len(query) and i not in covered_positions:
                        i += 1
                    end = i
                    if end - start >= 2:
                        unmatched_text = query[start:end].strip()
                        # Strip various quote characters
                        quotes = '"\'\'“”\'\''
                        unmatched_text = unmatched_text.strip(quotes)
                        if len(unmatched_text) >= 2:
                            unmatched_spans.append(UnmatchedSpan(
                                text=unmatched_text,
                                start=start,
                                end=end
                            )),
                else:
                    i += 1

        # Perform fuzzy matching
        if not unmatched_spans:
            return []

        self._ensure_fuzzy_matcher()
        if self._fuzzy_term_metadata is None:
            return []

        return list(match_all_unmatched(
            spans=tuple(unmatched_spans),
            term_metadata=self._fuzzy_term_metadata,
            config=self._fuzzy_config,
            stopwords=self._fuzzy_stopwords,
        ))


    def query_n_hop_subgraph(
        self,
        entity: QueryEntity,
        n_hops: int = 4,
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
                    SQL(self._bfs_cte_sql()), (entity.node_id, n_hops)  # type: ignore
                )
                rows = cur.fetchall()

                if not rows:
                    return SubgraphResult(center_entity=entity, hops=n_hops)

                # Build nodes, edges, and path-based tree from results
                # Key insight: use path (not term_id) as unique identifier to allow
                # same physical node to appear in different branches of the tree
                nodes: Dict[str, Dict[str, Any]] = {}
                edges: List[Dict[str, Any]] = []

                # path_edges: maps path_tuple -> list of (child_path_tuple, relation)
                # This allows building a tree where same node can appear multiple times
                # if reached via different paths
                path_edges: Dict[Tuple[str, ...], List[Tuple[Tuple[str, ...], str]]] = {}
                path_to_node: Dict[Tuple[str, ...], Dict[str, Any]] = {}

                for row in rows:
                    term_id, term_name, term_type, depth, path, parent_id, relation = row

                    # Store node (first occurrence)
                    if term_id not in nodes:
                        nodes[term_id] = {
                            "_id": term_id,
                            "id": term_id,
                            "name": term_name,
                            "node_type": term_type,
                            "depth": depth,
                        }

                    # Convert path array to tuple for dict key
                    path_tuple = tuple(path) if path else (term_id,)

                    # Store path -> node mapping
                    if path_tuple not in path_to_node:
                        path_to_node[path_tuple] = {
                            "term_id": term_id,
                            "name": term_name,
                            "node_type": term_type,
                            "depth": depth,
                        }

                    # Store edge based on path (not just term_id)
                    # This allows multiple edges to same target via different paths
                    if parent_id and relation:
                        # Find parent's path (current path without last element)
                        parent_path = path_tuple[:-1] if len(path_tuple) > 1 else (parent_id,)

                        if parent_path not in path_edges:
                            path_edges[parent_path] = []

                        # Add child path with relation
                        child_entry = (path_tuple, relation)
                        if child_entry not in path_edges[parent_path]:
                            path_edges[parent_path].append(child_entry)

                        # Also store flat edge for API response (deduplicate)
                        if not any(
                            e["source"] == parent_id
                            and e["target"] == term_id
                            and e["relation"] == relation
                            for e in edges
                        ):
                            edges.append(
                                {
                                    "source": parent_id,
                                    "target": term_id,
                                    "relation": relation,
                                    "data": {"relation": relation},
                                }
                            )

                # Batch fetch knowledge facts for all nodes (post-processing)
                # This is more efficient than JOIN in recursive CTE
                if nodes:
                    cur.execute(
                        SQL("""
                        SELECT term_id, knowledge_id, desc_summary, "desc"
                        FROM {}.term_knowledge
                        WHERE term_id = ANY(%s)
                        """).format(Identifier(self.schema)),
                        (list(nodes.keys()),),
                    )
                    knowledge_rows = cur.fetchall()
                    
                    # Group knowledge by term_id (one term can have multiple knowledge)
                    # Combine desc_summary and desc into a single content field for better display
                    knowledge_map: Dict[str, List[str]] = {}
                    for k_row in knowledge_rows:
                        k_term_id, k_id, k_summary, k_desc = k_row
                        if k_term_id not in knowledge_map:
                            knowledge_map[k_term_id] = []
                        knowledge_map[k_term_id].append(
                            self._format_knowledge_content(k_summary, k_desc)
                        )
                    
                    # Attach knowledge to nodes
                    for term_id, node in nodes.items():
                        if term_id in knowledge_map:
                            node["knowledge"] = "\n\n".join(knowledge_map[term_id])

                # Build tree structure using path-based edges
                tree = self._build_tree_from_path_edges(
                    entity.node_id, nodes, path_edges, path_to_node, n_hops
                )

                result = SubgraphResult(
                    center_entity=entity,
                    hops=n_hops,
                    nodes=list(nodes.values()),
                    edges=edges,
                    tree=tree,
                )

                return result

    def _bfs_cte_sql(self) -> str:
        """Generate BFS recursive CTE SQL.

        Simplified: only forward traversal (双向边已在数据层存储).
        
        The CTE traverses the graph from a starting node:
        - Anchor: starting term_id
        - Recursive: expand via term_relation (forward edges only)
        - Cycle detection: path array tracking
        - Depth limit: n_hops parameter
        """
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
                
                -- Recursive: expand neighbors via forward edges
                SELECT 
                    e.target_term_id,
                    t2.term_name,
                    t2.term_type_code,
                    tr.depth + 1,
                    (tr.path || e.target_term_id)::varchar(64)[],
                    tr.term_id,  -- current becomes parent
                    e.relation_name
                FROM traversal tr
                JOIN {self.schema}.term_relation e ON tr.term_id = e.source_term_id
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

    def _build_tree_from_path_edges(
        self,
        root_id: str,
        nodes: Dict[str, Dict[str, Any]],
        path_edges: Dict[Tuple[str, ...], List[Tuple[Tuple[str, ...], str]]],
        path_to_node: Dict[Tuple[str, ...], Dict[str, Any]],
        max_depth: int,
    ) -> TreeNode:
        """Build TreeNode hierarchy from path-based edges.

        n        This allows the same physical node to appear in multiple branches
                of the tree when reached via different paths (fixes multi-parent issue).

        n        Args:
                    root_id: Root term ID
                    nodes: term_id -> node data mapping
                    path_edges: path_tuple -> [(child_path_tuple, relation), ...]
                    path_to_node: path_tuple -> {term_id, name, node_type, depth}
                    max_depth: Maximum depth to traverse
        """
        root_data = nodes.get(root_id, {})
        root_path = (root_id,)

        root = TreeNode(
            id=root_id,
            name=root_data.get("name", root_id),
            node_type=root_data.get("node_type", "Unknown"),
            properties={"knowledge": root_data.get("knowledge", [])} if root_data.get("knowledge") else {},
            level=0,
        )

        # DFS to build tree, tracking by path (not term_id)
        # This allows same node to appear multiple times in different branches
        visited_paths: Set[Tuple[str, ...]] = {root_path}
        stack: List[Tuple[Tuple[str, ...], TreeNode, int]] = [(root_path, root, 0)]

        while stack:
            current_path, current_node, current_level = stack.pop()

            if current_level >= max_depth:
                continue

            # Find all children of current path
            children = path_edges.get(current_path, [])
            for child_path, relation in children:
                if child_path in visited_paths:
                    continue
                visited_paths.add(child_path)

                child_data = path_to_node.get(child_path, {})
                child_term_id = child_data.get("term_id", child_path[-1] if child_path else "")
                child_node_data = nodes.get(child_term_id, {})

                child = TreeNode(
                    id=child_term_id,
                    name=child_data.get("name") or child_term_id,
                    node_type=child_data.get("node_type", "Unknown"),
                    properties={"knowledge": child_node_data.get("knowledge", [])} if child_node_data.get("knowledge") else {},
                    relation=relation,  # 直接使用原始关系名（双边存储后无需处理_REVERSE）
                    level=current_level + 1,
                )

                current_node.children.append(child)
                stack.append((child_path, child, current_level + 1))

        return root

    def query(
        self,
        natural_language: str,
        n_hops: Optional[int] = None,
        include_knowledge: bool = True,
    ) -> Dict[str, Any]:
        """Main query interface - matches original API.

        Optimized: uses batch SQL query for multiple entities with caching.
        
        Args:
            natural_language: Natural language query text
            n_hops: Number of hops to traverse (default: self.default_hops)
            include_knowledge: Whether to include knowledge descriptions (default: True)
            
        Returns:
            Dict with query, entities_found, n_hops, and results
        """
        hops = n_hops if n_hops is not None else self.default_hops
        
        # Check cache first
        if self._enable_query_cache:
            cache_key = self._make_cache_key(natural_language, hops, include_knowledge)
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached
        
        # 1. Extract entities and fuzzy suggestions
        entities, fuzzy_suggestions = self.extract_entities(natural_language)

        if not entities and not fuzzy_suggestions:
            return {
                "query": natural_language,
                "entities_found": [],
                "fuzzy_suggestions": [],
                "results": [],
                "message": "未找到匹配的实体",
            }

        # 2. Batch query subgraphs (optimized)
        results = self._batch_query_subgraphs(entities, hops, include_knowledge=include_knowledge)

        result = {
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
            "fuzzy_suggestions": [
                {
                    "original": fs.span.text,
                    "matches": [
                        {
                            "term": m.term,
                            "term_id": m.term_id,
                            "term_type": m.term_type,
                            "similarity": m.similarity,
                            "edit_distance": m.edit_distance,
                        }
                        for m in fs.matches
                    ],
                }
                for fs in fuzzy_suggestions
            ],
            "n_hops": hops,
            "results": results,
        }
        
        # Store in cache
        if self._enable_query_cache:
            cache_key = self._make_cache_key(natural_language, hops, include_knowledge)
            self._put_in_cache(cache_key, result)
        
        return result
    
    def _make_cache_key(self, query: str, n_hops: int, include_knowledge: bool) -> str:
        """Generate cache key from query parameters."""
        # Normalize query (strip whitespace, lowercase)
        normalized = query.strip().lower()
        # Create hash for long queries
        if len(normalized) > 100:
            key_str = f"{md5(normalized.encode()).hexdigest()}:{n_hops}:{include_knowledge}"
        else:
            key_str = f"{normalized}:{n_hops}:{include_knowledge}"
        return key_str
    
    def _get_from_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """Get result from LRU cache."""
        if key not in self._query_cache:
            return None
        result, _ = self._query_cache[key]
        # Move to end (most recently used)
        if key in self._cache_order:
            self._cache_order.remove(key)
            self._cache_order.append(key)
        return result
    
    def _put_in_cache(self, key: str, result: Dict[str, Any]) -> None:
        """Put result in LRU cache with eviction."""
        # Evict if at capacity
        while len(self._query_cache) >= self._query_cache_maxsize and self._cache_order:
            oldest = self._cache_order.pop(0)
            self._query_cache.pop(oldest, None)
        
        # Add new entry
        self._query_cache[key] = (result, 1)
        self._cache_order.append(key)
    
    def clear_cache(self) -> None:
        """Clear query result cache."""
        self._query_cache.clear()
        self._cache_order.clear()

    def _batch_query_subgraphs(
        self,
        entities: List[QueryEntity],
        n_hops: int,
        include_knowledge: bool = True,
    ) -> List[Dict[str, Any]]:
        """Batch query multiple entity subgraphs using single SQL.

        Performance optimizations:
        1. Single recursive CTE with multi-source seeds (instead of N CTEs)
        2. O(E) edge deduplication using set (instead of O(E²) with any())
        3. Optional knowledge loading (lazy mode)
        """
        if not entities:
            return []

        # Filter entities with valid node_id
        valid_entities = [e for e in entities if e.node_id]
        if not valid_entities:
            return [self._format_subgraph_result(SubgraphResult(center_entity=e, hops=n_hops)) for e in entities]

        # Build single CTE with all seeds in VALUES clause
        # This is more efficient than N separate CTEs
        seed_values = ", ".join(f"('{e.node_id}')" for e in valid_entities)
        
        # Build knowledge JOIN conditionally
        knowledge_join = f"LEFT JOIN {self.schema}.term_knowledge k ON t.term_id = k.term_id" if include_knowledge else ""
        knowledge_cols = "k.desc_summary AS knowledge_summary, k.\"desc\" AS knowledge_desc" if include_knowledge else "NULL AS knowledge_summary, NULL AS knowledge_desc"
        
        sql = f"""
        WITH RECURSIVE seeds(source_id) AS (
            VALUES {seed_values}
        ),
        traversal AS (
            -- Anchor: start from all seeds
            SELECT 
                s.source_id,
                t.term_id,
                t.term_name,
                t.term_type_code,
                       0 AS depth, ARRAY[t.term_id]::varchar(64)[] AS path,
                       NULL::varchar AS parent_id, NULL::varchar AS relation,
                {knowledge_cols}
            FROM seeds s
            JOIN {self.schema}.term t ON t.term_id = s.source_id
            {knowledge_join}
            
            UNION ALL
            
            -- Recursive: expand neighbors
            SELECT 
                tr.source_id,
                e.target_term_id,
                t2.term_name,
                t2.term_type_code,
                       tr.depth + 1, (tr.path || e.target_term_id)::varchar(64)[],
                       tr.term_id, e.relation_name,
                       NULL, NULL
            FROM traversal tr
            JOIN {self.schema}.term_relation e ON tr.term_id = e.source_term_id
            JOIN {self.schema}.term t2 ON t2.term_id = e.target_term_id
                WHERE tr.depth < {n_hops} AND NOT e.target_term_id = ANY(tr.path)
        )
        SELECT * FROM traversal
        """

        # Execute batch query (single round trip)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)  # type: ignore[arg-type]
                rows = cur.fetchall()
        # Group results by source_id and build knowledge_map
        results_by_source: Dict[str, List] = defaultdict(list)
        knowledge_map: Dict[str, List[str]] = {}
        
        for row in rows:
            source_id, term_id, term_name, term_type, depth, path, parent_id, relation, k_summary, k_desc = row
            results_by_source[source_id].append(row)
            
            # Build knowledge from embedded columns (only if include_knowledge)
            if include_knowledge and (k_summary or k_desc):
                if term_id not in knowledge_map:
                    knowledge_map[term_id] = []
                knowledge_map[term_id].append(
                    self._format_knowledge_content(k_summary, k_desc)
                )
        
        # Build subgraph results for each entity
        results = []
        for entity in entities:
            if not entity.node_id:
                results.append(self._format_subgraph_result(SubgraphResult(center_entity=entity, hops=n_hops)))
                continue

            entity_rows = results_by_source.get(entity.node_id, [])
            if not entity_rows:
                results.append(self._format_subgraph_result(SubgraphResult(center_entity=entity, hops=n_hops)))
                continue

            # Build nodes and edges from rows
            nodes: Dict[str, Dict[str, Any]] = {}
            edges: List[Dict[str, Any]] = []
            # O(E) edge deduplication using set
            seen_edges: Set[Tuple[str, str, str]] = set()
            path_edges: Dict[Tuple[str, ...], List[Tuple[Tuple[str, ...], str]]] = {}
            path_to_node: Dict[Tuple[str, ...], Dict[str, Any]] = {}

            for row in entity_rows:
                # Row format: (source_id, term_id, term_name, term_type, depth, path, parent_id, relation, k_summary, k_desc)
                term_id, term_name, term_type, depth, path, parent_id, relation = row[1:8]

                if term_id not in nodes:
                    nodes[term_id] = {
                        "_id": term_id,
                        "id": term_id,
                        "name": term_name,
                        "node_type": term_type,
                        "depth": depth,
                    }
                    # Only add knowledge if present and enabled
                    if include_knowledge and term_id in knowledge_map:
                        nodes[term_id]["knowledge"] = "\n\n".join(knowledge_map[term_id])

                path_tuple = tuple(path) if path else (term_id,)
                if path_tuple not in path_to_node:
                    path_to_node[path_tuple] = {
                        "term_id": term_id,
                        "name": term_name,
                        "node_type": term_type,
                        "depth": depth,
                    }

                if parent_id and relation:
                    parent_path = path_tuple[:-1] if len(path_tuple) > 1 else (parent_id,)
                    if parent_path not in path_edges:
                        path_edges[parent_path] = []
                    child_entry = (path_tuple, relation)
                    if child_entry not in path_edges[parent_path]:
                        path_edges[parent_path].append(child_entry)

                    # O(1) edge deduplication using set
                    edge_key = (parent_id, term_id, relation)
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        edges.append({
                            "source": parent_id,
                            "target": term_id,
                            "relation": relation,
                            "data": {"relation": relation},
                        })
            
            # Build tree
            tree = self._build_tree_from_path_edges(
                entity.node_id, nodes, path_edges, path_to_node, n_hops
            )

            subgraph = SubgraphResult(
                center_entity=entity,
                hops=n_hops,
                nodes=list(nodes.values()),
                edges=edges,
                tree=tree,
            )
            results.append(self._format_subgraph_result(subgraph))

        return results

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

    def to_semantic_string(
        self,
        natural_language: str,
        n_hops: Optional[int] = None,
        include_knowledge: bool = True,
    ) -> str:
        """将自然语言查询转换为富含语义的树形文本描述.

        Args:
            natural_language: 自然语言查询文本
            n_hops: 查询跳数，默认使用 self.default_hops
            include_knowledge: 是否包含知识描述，默认 True

        Returns:
            树形结构的语义文本描述
        """
        result = self.query(natural_language, n_hops=n_hops, include_knowledge=include_knowledge)
        return self._format_result_as_tree_text(result)

    def _format_result_as_tree_text(self, result: Dict[str, Any]) -> str:
        """将查询结果格式化为树形文本."""
        lines = []
        lines.append(f"查询: {result.get('query', '')}")

        entities = result.get("entities_found", [])
        fuzzy_suggestions = result.get("fuzzy_suggestions", [])

        # 只有两个都为空才算真正没找到
        if not entities and not fuzzy_suggestions:
            lines.append("未找到匹配的实体")
            return "\n".join(lines)

        # 显示精确匹配（entities 只包含标准名称和别名匹配）
        if entities:
            lines.append(f"精确匹配 ({len(entities)} 个):")
            for i, entity in enumerate(entities, 1):
                match_type_str = "精确匹配" if entity.get("match_type") == "standard_name" else "别名匹配"
                lines.append(f"  {i}. {entity['name']} ({entity['node_type']}) - {match_type_str}")

        # 显示模糊推荐（独立的数据结构，不在 entities 中）
        if fuzzy_suggestions:
            lines.append(f"\n模糊推荐 ({len(fuzzy_suggestions)} 个):")
            for sugg in fuzzy_suggestions:
                original = sugg.get("original", "")
                matches = sugg.get("matches", [])
                if matches:
                    lines.append(f'  "{original}" 可能匹配:')
                    for m in matches:
                        sim_pct = int(m.get("similarity", 0) * 100)
                        lines.append(f'    → {m["term"]} ({m["term_type"]}) 相似度 {sim_pct}%')

        results = result.get("results", [])

        for i, subgraph in enumerate(results, 1):
            center_entity = subgraph.get("center_entity", {})
            lines.append("")
            lines.append(f"【中心实体 {i}】{center_entity.get('name')}")

            # 解析 node_id，展示术语库编码、术语类型编码、术语编码
            node_id = center_entity.get('node_id', '')
            if node_id and '#' in node_id:
                parts = node_id.split('#')
                if len(parts) >= 3:
                    lines.append(f"  术语库编码: {parts[0]}")
                    lines.append(f"  术语类型编码: {parts[1]}")
                    lines.append(f"  术语编码: {parts[2]}\n")

            lines.append(f"节点数: {subgraph.get('node_count')}, 边数: {subgraph.get('edge_count')}")

            tree_dict = subgraph.get("tree")
            if tree_dict:
                lines.append("\n知识图谱:")
                lines.append(self._tree_dict_to_text(tree_dict, ""))

        return "\n".join(lines)

    def _tree_dict_to_text(
        self, node_dict: Dict[str, Any], prefix: str = "", is_last: bool = True
    ) -> str:
        """将树形字典转换为树形文本."""
        lines = []

        connector = "└── " if is_last else "├── "
        relation_str = f"[{node_dict.get('relation', '')}] -> " if node_dict.get('relation') else ""
        lines.append(
            f"{prefix}{connector}{relation_str}{node_dict.get('name', '')} [{node_dict.get('node_type', '')}]"
        )

        new_prefix = prefix + ("    " if is_last else "│   ")

        properties = node_dict.get("properties", {})
        children = node_dict.get("children", [])

        if properties:
            lines.append(f"{new_prefix}├── 属性:")
            prop_prefix = new_prefix + "│   "
            props = list(properties.items())
            for j, (key, value) in enumerate(props):
                is_last_prop = (j == len(props) - 1) and not children
                prop_connector = "└── " if is_last_prop else "├── "
                
                # Special handling for knowledge - display full content with line breaks
                if key == "knowledge":
                    lines.append(f"{prop_prefix}{prop_connector}{key}:")
                    # Split knowledge into lines and indent each line
                    knowledge_lines = str(value).split("\n")
                    for k_line in knowledge_lines:
                        lines.append(f"{prop_prefix}    {k_line}")
                else:
                    value_str = str(value)
                    if len(value_str) > 100:
                        value_str = value_str[:97] + "..."
                    lines.append(f"{prop_prefix}{prop_connector}{key}: {value_str}")

        for k, child in enumerate(children):
            is_last_child = k == len(children) - 1
            lines.append(self._tree_dict_to_text(child, new_prefix, is_last_child))

        return "\n".join(lines)


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
) -> SQLKnowledgeGraphQuery:
    """Factory function to create SQLKnowledgeGraphQuery with explicit config.

    Args override environment variables.
    """
    config = {
        "host": host or os.getenv("DB_HOST", "localhost"),
        "port": port or int(os.getenv("DB_PORT", "5432")),
        "user": user or os.getenv("DB_USER", "postgres"),
        "password": password or os.getenv("DB_PASSWORD", ""),
        "database": database or os.getenv("DB_NAME", "postgres"),
    }
    return SQLKnowledgeGraphQuery(db_config=config, schema=schema)


# ============================================================================
# Singleton Service Instance (for performance optimization)
# ============================================================================

# Global singleton service instance
_singleton_service: Optional[SQLKnowledgeGraphQuery] = None
_singleton_n_hops: int = 4


def get_singleton_service(n_hops: int = 4, fast: bool = True, warm_pool: bool = False) -> SQLKnowledgeGraphQuery:
    """Get or create singleton service instance with prewarm.
    
    This is the recommended way to get a service instance for
    production use - it caches the instance and prewarms it
    on first access for optimal performance.
    
    Args:
        n_hops: Default number of hops for queries
        fast: If True, skip DB validation for faster startup (default: True)
              Use fast=False when data might have changed externally
        warm_pool: If True, pre-warm connection pool (default: False).
                   Connection pool warmup takes ~0.5s. Set to True only if
                   you expect many queries in quick succession.
    
    Returns:
        Pre-warmed SQLKnowledgeGraphQuery instance
    """
    global _singleton_service, _singleton_n_hops
    
    if _singleton_service is None or _singleton_n_hops != n_hops:
        _singleton_service = SQLKnowledgeGraphQuery(default_hops=n_hops)
        _singleton_n_hops = n_hops
        # Prewarm: load vocabulary and name_index into memory
        # By default, skip pool warmup for faster first query
        _singleton_service.prewarm(fast=fast, warm_pool=warm_pool)
    
    return _singleton_service


def reset_singleton_service(timeout: float = 0.5) -> None:
    """Reset singleton service instance (for testing).
    
    Args:
        timeout: Max seconds to wait for pool close (default: 0.5s)
    """
    global _singleton_service
    if _singleton_service is not None:
        try:
            _singleton_service.close(timeout=timeout)
        except Exception:
            pass  # Ignore close errors during reset
        _singleton_service = None


def nl_to_semantic_tree(
    natural_language: str,
    service: Optional["SQLKnowledgeGraphQuery"] = None,
    n_hops: int = 4,
    include_knowledge: bool = True,
    use_singleton: bool = True,
    fast: bool = True,
) -> str:
    """将自然语言查询转换为富含语义的树形文本描述.

    这是 SDK 提供的便捷函数，直接输入自然语言，输出语义化的树形文本。
    
    性能优化：
    - 默认使用单例模式 (use_singleton=True)，首次调用时预热缓存
    - 后续调用复用同一实例，避免重复初始化开销
    - 支持查询结果缓存，重复查询极速响应

    Args:
        natural_language: 自然语言查询文本
        service: SQLKnowledgeGraphQuery 实例（可选，不传则使用单例）
        n_hops: 查询跳数，默认 4
        include_knowledge: 是否包含知识描述，默认 True（设为 False 可加速）
        use_singleton: 是否使用单例实例，默认 True（推荐）
        fast: 是否跳过DB验证加速启动，默认 True（仅首次创建单例时生效）

    Returns:
        树形结构的语义文本描述

    Example:
        >>> text = nl_to_semantic_tree('北京亦庄经济技术开发区亩产效益最低的10家企业')
        >>> print(text)
        查询: 北京亦庄经济技术开发区亩产效益最低的10家企业
        识别到 1 个实体:
          1. 北京亦庄经济技术开发区 (区域) - 精确匹配
        【中心实体 1】北京亦庄经济技术开发区
        节点数: 15, 边数: 14
        知识图谱:
        └── 北京亦庄经济技术开发区 [区域]
            ├── [位于] -> 北京市 [城市]
            ├── [包含] -> 企业A [企业]
            └── 属性:
                └── area_code: 110105
    """
    if service is None:
        if use_singleton:
            service = get_singleton_service(n_hops, fast=fast)
        else:
            service = SQLKnowledgeGraphQuery(default_hops=n_hops)
            service.prewarm(fast=fast)
    return service.to_semantic_string(natural_language, n_hops=n_hops, include_knowledge=include_knowledge)

# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "SQLKnowledgeGraphQuery",
    "QueryEntity",
    "TreeNode",
    "SubgraphResult",
    "create_sql_graph_query",
    "nl_to_semantic_tree",
    "get_singleton_service",
    "reset_singleton_service",
]
