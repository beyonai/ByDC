"""mmap-based cache for vocabulary and name index.

Provides persistent, cross-process shared cache for:
- vocabulary_set: Set[str] of all vocabulary words
- name_index: Dict[str, List[Tuple[str, str, str]]] mapping names to term info

Cache validity is checked via:
1. Fast check: relfilenode + reltuples (~2ms)
2. Precise check: COUNT + MAX(updated_time) (~30ms, only when fast check fails)

Cache file format:
┌────────────────────────────────────────────┐
│ JSON Header (null-padded to 4KB boundary)  │
├────────────────────────────────────────────┤
│ Pickled vocabulary_set                     │
├────────────────────────────────────────────┤
│ Pickled name_index                         │
└────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import mmap
import os
import pickle
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import mmap
import os
import pickle
import struct
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, BinaryIO

# Default cache directory
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "datacloud_knowledge"

# Environment variable for custom cache path
CACHE_DIR_ENV = "DATACLOUD_KNOWLEDGE_CACHE_DIR"

# Cache file name template
CACHE_FILE_NAME = "vocab_cache_{schema}.bin"

# Header size (4KB, page-aligned)
HEADER_SIZE = 4096

# Magic number for cache file validation
CACHE_MAGIC = b"DCKV"  # DataCloud Knowledge Vocabulary
CACHE_VERSION = 1


@dataclass
class CacheMetadata:
    """Cache file metadata stored in header."""

    magic: str = CACHE_MAGIC.decode()
    version: int = CACHE_VERSION
    schema: str = ""

    # Database state for validity check
    relfilenode_term: int = 0
    relfilenode_name: int = 0
    relfilenode_vocab: int = 0
    reltuples_term: float = 0.0
    reltuples_name: float = 0.0
    reltuples_vocab: float = 0.0
    count_term: int = 0
    count_name: int = 0
    count_vocab: int = 0
    max_updated_term: Optional[str] = None
    max_updated_name: Optional[str] = None

    # Cache creation time
    created_at: str = ""

    # Data offsets in file (bytes from start)
    vocab_offset: int = 0
    vocab_size: int = 0
    index_offset: int = 0
    index_size: int = 0


class VocabularyCache:
    """mmap-based persistent cache for vocabulary and name index."""

    def __init__(self, schema: str = "whale_datacloud", cache_dir: Optional[Path] = None):
        """Initialize cache manager.

        Args:
            schema: Database schema name
            cache_dir: Cache directory path (default: ~/.cache/datacloud_knowledge
                      or DATACLOUD_KNOWLEDGE_CACHE_DIR env var)
        """
        self.schema = schema

        # Determine cache directory
        if cache_dir is not None:
            self.cache_dir = Path(cache_dir)
        else:
            env_dir = os.environ.get(CACHE_DIR_ENV)
            if env_dir:
                self.cache_dir = Path(env_dir)
            else:
                self.cache_dir = DEFAULT_CACHE_DIR

        self.cache_file = self.cache_dir / CACHE_FILE_NAME.format(schema=schema)

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # In-memory cache (loaded from mmap or DB)
        self._vocabulary_set: Optional[Set[str]] = None
        self._name_index: Optional[Dict[str, List[Tuple[str, str, str]]]] = None
        self._metadata: Optional[CacheMetadata] = None

    def get_cache_path(self) -> Path:
        """Get cache file path."""
        return self.cache_file

    def _fetch_db_state(self, conn) -> CacheMetadata:
        """Fetch current database state for cache validation.

        Single query to get all needed metadata (~5ms).
        """
        with conn.cursor() as cur:
            # Get relfilenode and reltuples from pg_class
            cur.execute(
                f"""
                SELECT 
                    c.relname,
                    c.relfilenode,
                    c.reltuples
                FROM pg_class c
                JOIN pg_namespace n ON c.relnamespace = n.oid
                WHERE n.nspname = %s 
                AND c.relname IN ('term', 'term_name', 'term_vocabulary')
            """,
                (self.schema,),
            )

            relfilenodes = {row[0]: (row[1], row[2]) for row in cur.fetchall()}

            # Get counts and max updated times
            cur.execute(f"""
                SELECT 
                    (SELECT COUNT(*) FROM {self.schema}.term) as count_term,
                    (SELECT COUNT(*) FROM {self.schema}.term_name) as count_name,
                    (SELECT COUNT(*) FROM {self.schema}.term_vocabulary) as count_vocab,
                    (SELECT MAX(updated_time) FROM {self.schema}.term) as max_term,
                    (SELECT MAX(updated_time) FROM {self.schema}.term_name) as max_name
            """)

            row = cur.fetchone()

            term_fn, term_tup = relfilenodes.get("term", (0, 0.0))
            name_fn, name_tup = relfilenodes.get("term_name", (0, 0.0))
            vocab_fn, vocab_tup = relfilenodes.get("term_vocabulary", (0, 0.0))

            return CacheMetadata(
                magic=CACHE_MAGIC.decode(),
                version=CACHE_VERSION,
                schema=self.schema,
                relfilenode_term=term_fn,
                relfilenode_name=name_fn,
                relfilenode_vocab=vocab_fn,
                reltuples_term=term_tup,
                reltuples_name=name_tup,
                reltuples_vocab=vocab_tup,
                count_term=row[0] or 0,
                count_name=row[1] or 0,
                count_vocab=row[2] or 0,
                max_updated_term=row[3].isoformat() if row[3] else None,
                max_updated_name=row[4].isoformat() if row[4] else None,
            )

    def _check_cache_valid(self, cached_meta: CacheMetadata, current_meta: CacheMetadata) -> bool:
        """Check if cached data is still valid.

        Two-level check:
        1. Fast: relfilenode + reltuples (detects TRUNCATE, VACUUM FULL)
        2. Precise: counts + max_updated_time (detects any data change)
        """
        # Fast check: relfilenode unchanged
        if (
            cached_meta.relfilenode_term != current_meta.relfilenode_term
            or cached_meta.relfilenode_name != current_meta.relfilenode_name
            or cached_meta.relfilenode_vocab != current_meta.relfilenode_vocab
        ):
            return False

        # Precise check: counts and timestamps
        if (
            cached_meta.count_term != current_meta.count_term
            or cached_meta.count_name != current_meta.count_name
            or cached_meta.count_vocab != current_meta.count_vocab
        ):
            return False

        # Check max updated time (if available)
        if current_meta.max_updated_term and cached_meta.max_updated_term:
            if current_meta.max_updated_term > cached_meta.max_updated_term:
                return False

        if current_meta.max_updated_name and cached_meta.max_updated_name:
            if current_meta.max_updated_name > cached_meta.max_updated_name:
                return False

        return True

    def load(
        self, conn
    ) -> Tuple[Optional[Set[str]], Optional[Dict[str, List[Tuple[str, str, str]]]]]:
        """Load vocabulary and name index from cache if valid.

        Returns:
            Tuple of (vocabulary_set, name_index) if cache valid, else (None, None)
        """
        if not self.cache_file.exists():
            return None, None

        try:
            with open(self.cache_file, "rb") as f:
                # Use mmap for efficient reading
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    # Read header
                    header_bytes = mm[:HEADER_SIZE]
                    header_json = header_bytes.split(b"\x00")[0].decode("utf-8")
                    cached_meta = CacheMetadata(**json.loads(header_json))

                    # Get current DB state
                    current_meta = self._fetch_db_state(conn)

                    # Check validity
                    if not self._check_cache_valid(cached_meta, current_meta):
                        return None, None

                    # Read vocabulary_set
                    vocab_offset = cached_meta.vocab_offset
                    vocab_size = cached_meta.vocab_size
                    vocab_bytes = mm[vocab_offset : vocab_offset + vocab_size]
                    vocabulary_set = pickle.loads(vocab_bytes)

                    # Read name_index
                    index_offset = cached_meta.index_offset
                    index_size = cached_meta.index_size
                    index_bytes = mm[index_offset : index_offset + index_size]
                    name_index = pickle.loads(index_bytes)

                    self._metadata = cached_meta
                    self._vocabulary_set = vocabulary_set
                    self._name_index = name_index

                    return vocabulary_set, name_index

        except Exception as e:
            # Cache corrupted or unreadable, rebuild
            return None, None
    
    def load_fast(
        self,
    ) -> Tuple[Optional[Set[str]], Optional[Dict[str, List[Tuple[str, str, str]]]]]:
        """Load vocabulary and name index from cache WITHOUT DB validation.
        
        Fast startup mode - assumes cache is valid.
        Use this when:
        - You're sure data hasn't changed
        - You want fastest possible startup
        - You're willing to risk stale data
        
        Returns:
            Tuple of (vocabulary_set, name_index) if cache exists, else (None, None)
        """
        if not self.cache_file.exists():
            return None, None
        
        try:
            with open(self.cache_file, "rb") as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    # Read header
                    header_bytes = mm[:HEADER_SIZE]
                    header_json = header_bytes.split(b"\x00")[0].decode("utf-8")
                    cached_meta = CacheMetadata(**json.loads(header_json))
                    
                    # Read vocabulary_set (skip validation)
                    vocab_offset = cached_meta.vocab_offset
                    vocab_size = cached_meta.vocab_size
                    vocab_bytes = mm[vocab_offset : vocab_offset + vocab_size]
                    vocabulary_set = pickle.loads(vocab_bytes)
                    
                    # Read name_index
                    index_offset = cached_meta.index_offset
                    index_size = cached_meta.index_size
                    index_bytes = mm[index_offset : index_offset + index_size]
                    name_index = pickle.loads(index_bytes)
                    
                    self._metadata = cached_meta
                    self._vocabulary_set = vocabulary_set
                    self._name_index = name_index
                    
                    return vocabulary_set, name_index
        
        except Exception as e:
            # Cache corrupted or unreadable, rebuild
            return None, None

    def save(
        self,
        conn,
        vocabulary_set: Set[str],
        name_index: Dict[str, List[Tuple[str, str, str]]],
    ) -> None:
        """Save vocabulary and name index to cache file."""
        # Get current DB state
        meta = self._fetch_db_state(conn)
        meta.created_at = datetime.now().isoformat()

        # Serialize data
        vocab_bytes = pickle.dumps(vocabulary_set, protocol=pickle.HIGHEST_PROTOCOL)
        index_bytes = pickle.dumps(name_index, protocol=pickle.HIGHEST_PROTOCOL)

        # Calculate offsets
        meta.vocab_offset = HEADER_SIZE
        meta.vocab_size = len(vocab_bytes)
        meta.index_offset = HEADER_SIZE + len(vocab_bytes)
        meta.index_size = len(index_bytes)

        # Calculate total file size
        total_size = meta.index_offset + meta.index_size

        # Write to temp file first (atomic write)
        temp_file = self.cache_file.with_suffix(".tmp")
        try:
            with open(temp_file, "wb") as f:
                # Pre-allocate file
                f.seek(total_size - 1)
                f.write(b"\x00")
                f.seek(0)

                # Write header (padded to HEADER_SIZE)
                header_json = json.dumps(asdict(meta))
                header_bytes = header_json.encode("utf-8")
                if len(header_bytes) > HEADER_SIZE:
                    raise ValueError(f"Header too large: {len(header_bytes)} > {HEADER_SIZE}")
                f.write(header_bytes)
                f.write(b"\x00" * (HEADER_SIZE - len(header_bytes)))

                # Write vocabulary_set
                f.write(vocab_bytes)

                # Write name_index
                f.write(index_bytes)

            # Atomic rename
            temp_file.rename(self.cache_file)

            self._metadata = meta
            self._vocabulary_set = vocabulary_set
            self._name_index = name_index

        finally:
            # Cleanup temp file on error
            if temp_file.exists():
                temp_file.unlink()

    def clear(self) -> None:
        """Clear cache file and in-memory data."""
        if self.cache_file.exists():
            self.cache_file.unlink()
        self._vocabulary_set = None
        self._name_index = None
        self._metadata = None

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = {
            "cache_file": str(self.cache_file),
            "exists": self.cache_file.exists(),
        }

        if self.cache_file.exists():
            stats["file_size_mb"] = self.cache_file.stat().st_size / 1024 / 1024

        if self._metadata:
            stats["metadata"] = asdict(self._metadata)

        if self._vocabulary_set:
            stats["vocab_count"] = len(self._vocabulary_set)

        if self._name_index:
            stats["name_count"] = len(self._name_index)

        return stats
