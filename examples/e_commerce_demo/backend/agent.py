"""LangGraph entrypoint for datacloud-analysis — used by langgraph dev and deep-agents-ui."""

import logging
import os
import sys
import importlib.util

# Configure root logger so that INFO+ messages appear in langgraph dev console.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)

# Suppress noisy internal heartbeat / file-watcher logs that clutter the console.
for _noisy in (
    "watchfiles",
    "watchfiles.main",
    "langgraph_runtime_inmem.queue",
    "langgraph_runtime_inmem._persistence",
    "langgraph_api.metadata",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# Directly load the agent.py file since the directory 'datacloud-analysis' has a hyphen
agent_py_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../packages/datacloud-analysis/src/datacloud_analysis/agent.py")
)
spec = importlib.util.spec_from_file_location("datacloud_analysis_mod", agent_py_path)
datacloud_analysis_mod = importlib.util.module_from_spec(spec)
sys.modules["datacloud_analysis_mod"] = datacloud_analysis_mod
spec.loader.exec_module(datacloud_analysis_mod)

create_agent = datacloud_analysis_mod.create_agent

# graph must be an instance of langgraph Pregel (CompiledGraph) — do NOT wrap it.
graph = create_agent()
