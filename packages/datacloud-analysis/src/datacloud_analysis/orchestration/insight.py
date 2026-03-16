"""④ Summary and reply generation (design §3.1 INSIGHT).

Responsibilities
----------------
- Collect outputs from all completed sub-tasks.
- Call the *reasoning* LLM to synthesise a coherent answer.
- Assemble the ``render_report`` data protocol (charts, tables, text).
- Bind Trace / evidence chain references to the final reply.
- Emit the ``Memory_Collection_Event`` so the Memory Worker can distil
  long-term memories asynchronously (design §4.3.2.1).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def insight_node(state: dict[str, Any]) -> dict[str, Any]:
    """Generate the final answer and report from completed sub-task outputs.

    Input state keys
    ----------------
    ``dag``:       Completed sub-task tree with ``output`` on each task.
    ``messages``:  Conversation history.

    Output state additions
    ----------------------
    ``answer``:    Natural-language answer string.
    ``report``:    Serialised report protocol (charts, tables, etc.).

    TODO: implement with a reasoning LLM call + render_report tool.
    """
    logger.debug("insight_node: synthesising final answer …")

    completed_outputs = [
        t.get("output")
        for t in state.get("dag", [])
        if t.get("status") == "done"
    ]

    # Placeholder — replace with reasoning LLM summarisation.
    state["answer"] = f"Analysis complete. {len(completed_outputs)} sub-tasks executed."
    state["report"] = {}

    # Signal memory distillation (fire-and-forget via event emitter).
    _emit_memory_collection_event(state)

    return state


def _emit_memory_collection_event(state: dict[str, Any]) -> None:
    """Asynchronously signal that memory distillation should start.

    The actual MQ push happens in the message handler layer; here we just set a
    flag in the state so the message handler can pick it up after streaming ends.
    """
    state["_emit_memory_event"] = True
