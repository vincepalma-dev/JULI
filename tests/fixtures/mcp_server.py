"""A tiny stdio MCP server for tests: tools echo and fail, newline-delimited JSON-RPC."""

import json
import os
import sys

TOOLS = [
    {"name": "echo", "description": "Echo the text back.", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}}},
    {"name": "fail", "description": "Always fails.", "inputSchema": {"type": "object", "properties": {}}},
    {
        "name": "env",
        "description": "Says whether a variable is set.",
        "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}},
    },
]


def reply(message_id, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message_id, "result": result}) + "\n")
    sys.stdout.flush()


sys.stdout.write("a log line that isn't JSON-RPC\n")
for line in sys.stdin:
    message = json.loads(line)
    method, message_id = message.get("method"), message.get("id")
    if message_id is None:
        continue  # a notification
    if method == "initialize":
        reply(message_id, {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake", "version": "1"}})
    elif method == "tools/list":
        reply(message_id, {"tools": TOOLS})
    elif method == "tools/call":
        name, args = message["params"]["name"], message["params"].get("arguments") or {}
        if name == "echo":
            reply(message_id, {"content": [{"type": "text", "text": f"echo: {args.get('text', '')}"}]})
        elif name == "env":
            value = os.environ.get(args.get("name", ""))
            reply(message_id, {"content": [{"type": "text", "text": "set" if value else "unset"}]})
        else:
            reply(message_id, {"content": [{"type": "text", "text": "it broke"}], "isError": True})
    else:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message_id, "error": {"code": -32601, "message": "unknown"}}) + "\n")
        sys.stdout.flush()
