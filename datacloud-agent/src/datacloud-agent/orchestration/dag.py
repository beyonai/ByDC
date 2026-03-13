"""② Dynamic DAG generation (design §3.1 DAG_PLAN).

Responsibilities
----------------
- Parse the classified intent and decompose it into a tree of sub-tasks.
- Resolve intra-task dependencies (serial vs. parallel branches).
- Store the sub-task tree in the graph state for the loop to consume.

The DAG is represented as a plain Python dict in the LangGraph state so
it survives checkpointing without serialisation issues.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def dag_node(state: dict[str, Any]) -> dict[str, Any]:
    """Generate the execution DAG from the parsed intent.

    Input state keys
    ----------------
    ``messages``:   Conversation history (including intent classification result).

    Output state additions
    ----------------------
    ``dag``:        List of sub-task dicts, e.g.::

                    [
                        {"id": "t1", "type": "data_query", "deps": []},
                        {"id": "t2", "type": "code_exec",  "deps": ["t1"]},
                    ]

    TODO: implement with a reasoning LLM call that outputs structured JSON.
    """
    logger.debug("dag_node: generating execution DAG …")
    state.setdefault("dag", [])
    return state
