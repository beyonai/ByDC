"""LangGraph entrypoint for datacloud-agent — used by langgraph dev and deep-agents-ui."""

import os
import sys
import importlib.util

# Directly load the agent.py file since the directory 'datacloud-agent' has a hyphen
agent_py_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../datacloud-agent/src/datacloud-agent/agent.py")
)
spec = importlib.util.spec_from_file_location("datacloud_agent_mod", agent_py_path)
datacloud_agent_mod = importlib.util.module_from_spec(spec)
sys.modules["datacloud_agent_mod"] = datacloud_agent_mod
spec.loader.exec_module(datacloud_agent_mod)

create_agent = datacloud_agent_mod.create_agent
graph = create_agent()
