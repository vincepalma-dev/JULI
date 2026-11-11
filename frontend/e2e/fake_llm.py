"""A tiny OpenAI-compatible server for JULI end-to-end checks.

GET /v1/models, streamed POST /v1/chat/completions with a final usage chunk.
The reply is chosen by the system prompt's first line. Model "fake-slow"
streams one word every 0.3 s (for Stop). max_tokens cuts the reply to that
many words.
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
        text = reply_for(body)
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
            done = {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
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
