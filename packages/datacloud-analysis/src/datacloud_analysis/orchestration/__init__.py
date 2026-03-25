"""Orchestration package — Agent core workflow (design §3.1 AGENT_ORCH).

Workflow nodes (executed in order by the LangGraph graph):

① intent.py           Intent parsing: tokenise, attach 1-hop knowledge,
                       classify intent, load short/long-term memory.
② dag.py              Dynamic DAG generation: parse dependencies, build
                       serial/parallel sub-task tree.
③ loop.py             ReAct execution loop + state router + HITL interrupt.
   sandbox_executor.py Trigger atomic tools inside the sandbox.
④ insight.py          Summarise results, generate reply, bind Trace evidence.

Optional streaming entry: ``run_agent()`` in ``runner.py`` (TaskPaths + run_config).
"""
