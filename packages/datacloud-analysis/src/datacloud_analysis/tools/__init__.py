"""Tools package — atomic capabilities exposed to the Agent.

OQL tools (query_objects, execute_action) live in tools/oql/.
emit_result lives in tools/emit_result.py (injected by DatacloudOutputMiddleware).
knowledge tool lives in tools/knowledge.py (used internally by KnowledgeInjectionMiddleware).

Legacy tools (ask_user, code_exec, file_io, sandbox) have been removed:
- ask_user  → HumanInTheLoopMiddleware (SDK built-in)
- code_exec → CodeExecutorSubAgent
- file_io   → FilesystemMiddleware (SDK built-in)
- sandbox   → DatacloudBackend
"""

from .knowledge import search_knowledge

__all__ = [
    "search_knowledge",
]
