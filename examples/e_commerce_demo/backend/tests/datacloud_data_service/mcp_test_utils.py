"""MCP 测试工具：解析 SSE 响应等。"""
import json
import re


def parse_sse_response(resp) -> dict:
    """解析 MCP SSE 响应，提取 JSON-RPC 消息。兼容 application/json 和 text/event-stream。"""
    if resp.headers.get("content-type", "").startswith("application/json"):
        return resp.json()
    text = resp.text
    data_match = re.search(r"^data:\s*(.+)$", text, re.MULTILINE)
    if data_match:
        return json.loads(data_match.group(1).strip())
    raise ValueError(f"Cannot parse response: {text[:200]}")
