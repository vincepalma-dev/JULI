"""A tiny OpenAI-compatible server for JULI end-to-end checks.

GET /v1/models, streamed POST /v1/chat/completions with a final usage chunk.
The reply is chosen by the system prompt's first line. Model "fake-slow"
streams one word every 0.3 s (for Stop). max_tokens cuts the reply to that
many words.

Tool calls: when a request offers tools and nothing has been called yet in
the conversation, the Reviewer first reads calc.py, and the Tester first
calls an MCP tool if one is offered. The next request (with the results)
gets the usual reply.
"""

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FENCE = "```"
REPLIES = {
    "Planner": "Plan: 1. Write add() in calc.py. 2. Test it with pytest. 3. Document it.",
    "Coder": (
        f"Here is the code.\n{FENCE}python path=calc.py\ndef add(a, b):\n    return a + b\n{FENCE}\n"
        f"Run the tests:\n{FENCE}bash run\npytest -q\n{FENCE}\n"
    ),
    "Reviewer": "The code is small and correct.\nVERDICT: APPROVED",
    "Test": f"Tests:\n{FENCE}python path=test_calc.py\nfrom calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n{FENCE}\n",
    "Documentation": f"{FENCE}markdown path=README.md\n# Calc\n\nadd(a, b) returns the sum.\n{FENCE}\n",
}


def tool_call_for(body: dict) -> dict | None:
    """The tool call to make first, if any: {"name", "arguments"}."""
    offered = [t["function"]["name"] for t in body.get("tools") or []]
    if not offered or any(m["role"] == "tool" for m in body["messages"]):
        return None
    system = next((m["content"] for m in body["messages"] if m["role"] == "system"), "")
    first = system.splitlines()[0] if system else ""
    if "Reviewer" in first and "read_file" in offered:
        return {"name": "read_file", "arguments": json.dumps({"path": "calc.py"})}
    mcp = next((name for name in offered if name.startswith("mcp__")), None)
    if "Test" in first and mcp:
        return {"name": mcp, "arguments": json.dumps({"text": "from the tester"})}
    return None


def reply_for(body: dict) -> str:
    system = next((m["content"] for m in body["messages"] if m["role"] == "system"), "")
    first = system.splitlines()[0] if system else ""
    text = next((r for key, r in REPLIES.items() if key in first), "Okay. " * 5)
    if body.get("max_tokens"):
        text = " ".join(text.split(" ")[: int(body["max_tokens"])])
    return text


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, data, status=200):
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._json({"object": "list", "data": [{"id": "fake", "object": "model"}, {"id": "fake-slow", "object": "model"}]})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        length = self.headers.get("Content-Length", "")
        if not length.isdigit():
            self._json({"error": "Content-Length is required"}, 400)
            return
        body = json.loads(self.rfile.read(int(length)))
        call = tool_call_for(body)
        text = "" if call else reply_for(body)
        delay = 0.3 if body.get("model") == "fake-slow" else 0.0
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        base = {"id": "c1", "object": "chat.completion.chunk", "created": int(time.time()), "model": body.get("model")}
        try:
            for i, word in enumerate(text.split(" ")):
                piece = word if i == 0 else " " + word
                chunk = {**base, "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.flush()
                time.sleep(delay)
            if call:
                delta = {"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": call}]}
                chunk = {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            done = {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls" if call else "stop"}]}
            usage = {
                **base,
                "choices": [],
                "usage": {"prompt_tokens": 100, "completion_tokens": len(text.split()), "total_tokens": 100 + len(text.split())},
            }
            self.wfile.write(f"data: {json.dumps(done)}\n\ndata: {json.dumps(usage)}\n\ndata: [DONE]\n\n".encode())
        except (BrokenPipeError, ConnectionResetError):
            pass  # the client stopped the run


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    print(f"fake LLM on http://127.0.0.1:{port}/v1", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
