"""Memory integration layer — Agent side (design §4.3).

This package is the *Agent-side* memory façade.  It does NOT implement
memory storage or distillation — that responsibility belongs to the
``datacloud-memory`` service.

Sub-modules
-----------
loader   Pull ``global_rules`` at task startup and mount ``MEMORY.md``.
tools    MCP tool wrappers (recall_memory, search_memory, read_memory)
         that the Agent calls during inference.
"""

from .loader import MemoryLoader
from .tools import recall_memory, read_memory, search_memory

__all__ = ["MemoryLoader", "recall_memory", "search_memory", "read_memory"]
