#!/usr/bin/env python3
"""
Minimal OpenAI Responses-API -> Chat-Completions bridge.

Codex CLI (>=0.81) speaks only the Responses API; SGLang/vLLM speak only chat
completions (SGLang's native /v1/responses is broken for non-harmony models).
LiteLLM's responses bridge passes through / template-dumps, so this is a small,
dependency-free translation layer covering exactly the subset codex emits:

  POST /v1/responses  {model, instructions, input[], tools[], tool_choice,
                       max_output_tokens, stream, ...}

Translation:
  instructions               -> system message
  input message items        -> chat messages (input_text/output_text joined)
  function_call items        -> assistant message with tool_calls
  function_call_output items -> role:tool messages (matched by call_id)
  flat Responses tools       -> nested chat tools
  max_output_tokens          -> max_tokens

The backend is always called NON-streaming; when the client asks for stream we
re-emit the finished response as a burst of Responses SSE events (fake-stream,
same trick CCR used for claude+kimi). Usage is mapped to Responses shape with
reasoning_tokens carried through so codex rollout token_count stays truthful.

Env: BRIDGE_UPSTREAM (e.g. http://host:8000/v1), BRIDGE_API_KEY, BRIDGE_PORT.
Stateless; store/previous_response_id are ignored (codex sends full history).
"""
import json
import os
import sys
import time
import uuid
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("BRIDGE_UPSTREAM", "http://127.0.0.1:8000/v1").rstrip("/")
API_KEY = os.environ.get("BRIDGE_API_KEY", "")
PORT = int(os.environ.get("BRIDGE_PORT", "41100"))
TIMEOUT = int(os.environ.get("BRIDGE_TIMEOUT_SEC", "1800"))


def _content_to_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") in ("input_text", "output_text", "text", "summary_text"):
                parts.append(c.get("text", ""))
        return "".join(parts)
    return ""


def responses_to_chat(req):
    messages = []
    instructions = req.get("instructions")
    if instructions:
        messages.append({"role": "system", "content": instructions})

    inp = req.get("input")
    if isinstance(inp, str):
        messages.append({"role": "user", "content": inp})
    else:
        for item in inp or []:
            itype = item.get("type", "message")
            if itype == "message":
                role = item.get("role", "user")
                if role == "developer":
                    role = "system"
                messages.append({"role": role, "content": _content_to_text(item.get("content"))})
            elif itype == "function_call":
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": item.get("call_id") or item.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                        "type": "function",
                        "function": {"name": item.get("name", ""),
                                     "arguments": item.get("arguments", "{}")},
                    }],
                })
            elif itype == "function_call_output":
                out = item.get("output", "")
                if not isinstance(out, str):
                    out = _content_to_text(out) or json.dumps(out)
                messages.append({"role": "tool",
                                 "tool_call_id": item.get("call_id", ""),
                                 "content": out})
            elif itype == "reasoning":
                continue  # never replay CoT back to the model
            # local_shell_call etc. don't occur with our config; ignore.

    # Merge consecutive assistant tool_call messages into one (parallel calls).
    merged = []
    for m in messages:
        if (merged and m.get("tool_calls") and merged[-1].get("role") == "assistant"
                and merged[-1].get("tool_calls") is not None and not merged[-1].get("content")):
            merged[-1]["tool_calls"].extend(m["tool_calls"])
        else:
            merged.append(m)
    messages = merged

    chat = {"model": req.get("model", "default"), "messages": messages}
    if req.get("max_output_tokens"):
        chat["max_tokens"] = req["max_output_tokens"]
    if req.get("temperature") is not None:
        chat["temperature"] = req["temperature"]
    if req.get("top_p") is not None:
        chat["top_p"] = req["top_p"]

    tools = []
    for t in req.get("tools") or []:
        if t.get("type") == "function":
            if "function" in t:          # already nested
                tools.append(t)
            else:                        # flat Responses form
                tools.append({"type": "function", "function": {
                    "name": t.get("name", ""),
                    "description": t.get("description") or "",
                    "parameters": t.get("parameters") or {"type": "object", "properties": {}},
                }})
        # non-function tool types (web_search etc.) are unsupported: skip.
    if tools:
        chat["tools"] = tools
        tc = req.get("tool_choice")
        if tc in ("auto", "none", "required"):
            chat["tool_choice"] = tc
    return chat


def chat_to_response(chat_resp, model):
    """Map a finished chat completion to a Responses-API response object."""
    choice = (chat_resp.get("choices") or [{}])[0]
    msg = choice.get("message", {})
    output = []

    reasoning = msg.get("reasoning_content")
    if reasoning:
        output.append({
            "id": f"rs_{uuid.uuid4().hex}", "type": "reasoning",
            "summary": [{"type": "summary_text", "text": reasoning}],
        })

    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        output.append({
            "id": f"fc_{uuid.uuid4().hex}", "type": "function_call",
            "status": "completed",
            "call_id": tc.get("id") or f"call_{uuid.uuid4().hex[:12]}",
            "name": fn.get("name", ""), "arguments": fn.get("arguments", "{}"),
        })

    content = msg.get("content")
    if content:
        output.append({
            "id": f"msg_{uuid.uuid4().hex}", "type": "message",
            "status": "completed", "role": "assistant",
            "content": [{"type": "output_text", "annotations": [], "text": content}],
        })

    u = chat_resp.get("usage") or {}
    usage = {
        "input_tokens": u.get("prompt_tokens", 0),
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens": u.get("completion_tokens", 0),
        "output_tokens_details": {"reasoning_tokens": u.get("reasoning_tokens", 0)},
        "total_tokens": u.get("total_tokens", 0),
    }
    return {
        "id": f"resp_{uuid.uuid4().hex}", "object": "response",
        "created_at": int(time.time()), "model": model,
        "status": "completed", "error": None, "incomplete_details": None,
        "output": output, "usage": usage,
        "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
    }


def sse_events(resp):
    """Fake-stream a finished Responses object as the SSE event sequence codex expects."""
    seq = [0]

    def ev(etype, **kw):
        d = {"type": etype, "sequence_number": seq[0]}
        seq[0] += 1
        d.update(kw)
        return f"event: {etype}\ndata: {json.dumps(d, ensure_ascii=False)}\n\n"

    working = dict(resp, status="in_progress")
    yield ev("response.created", response=working)
    yield ev("response.in_progress", response=working)
    for idx, item in enumerate(resp["output"]):
        pending = dict(item)
        if item["type"] == "message":
            pending["content"] = []
            pending["status"] = "in_progress"
        elif item["type"] == "function_call":
            pending = dict(item, arguments="", status="in_progress")
        yield ev("response.output_item.added", output_index=idx, item=pending)
        if item["type"] == "message":
            text = item["content"][0]["text"]
            yield ev("response.content_part.added", item_id=item["id"], output_index=idx,
                     content_index=0, part={"type": "output_text", "annotations": [], "text": ""})
            yield ev("response.output_text.delta", item_id=item["id"], output_index=idx,
                     content_index=0, delta=text, logprobs=[])
            yield ev("response.output_text.done", item_id=item["id"], output_index=idx,
                     content_index=0, text=text, logprobs=[])
            yield ev("response.content_part.done", item_id=item["id"], output_index=idx,
                     content_index=0, part=item["content"][0])
        elif item["type"] == "function_call":
            yield ev("response.function_call_arguments.delta", item_id=item["id"],
                     output_index=idx, delta=item["arguments"])
            yield ev("response.function_call_arguments.done", item_id=item["id"],
                     output_index=idx, arguments=item["arguments"])
        elif item["type"] == "reasoning":
            txt = item["summary"][0]["text"]
            yield ev("response.reasoning_summary_part.added", item_id=item["id"], output_index=idx,
                     summary_index=0, part={"type": "summary_text", "text": ""})
            yield ev("response.reasoning_summary_text.delta", item_id=item["id"], output_index=idx,
                     summary_index=0, delta=txt)
            yield ev("response.reasoning_summary_text.done", item_id=item["id"], output_index=idx,
                     summary_index=0, text=txt)
            yield ev("response.reasoning_summary_part.done", item_id=item["id"], output_index=idx,
                     summary_index=0, part=item["summary"][0])
        yield ev("response.output_item.done", output_index=idx, item=item)
    yield ev("response.completed", response=resp)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[bridge] %s\n" % (fmt % args))

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            # passthrough so health checks work
            try:
                r = urllib.request.urlopen(f"{UPSTREAM}/models", timeout=30)
                data = r.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self._send_json(502, {"error": str(e)})
        else:
            self._send_json(200, {"ok": True})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/responses"):
            self._send_json(404, {"error": {"message": f"unsupported path {self.path}"}})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
        except Exception as e:
            self._send_json(400, {"error": {"message": f"bad request: {e}"}})
            return

        chat = responses_to_chat(req)
        payload = json.dumps(chat).encode()
        upstream_req = urllib.request.Request(
            f"{UPSTREAM}/chat/completions", data=payload,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {API_KEY}"})
        try:
            with urllib.request.urlopen(upstream_req, timeout=TIMEOUT) as r:
                chat_resp = json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            sys.stderr.write(f"[bridge] upstream {e.code}: {detail[:300]}\n")
            self._send_json(e.code, {"error": {"message": f"upstream {e.code}: {detail}"}})
            return
        except Exception as e:
            self._send_json(502, {"error": {"message": f"upstream error: {e}"}})
            return

        resp = chat_to_response(chat_resp, req.get("model", "default"))
        if req.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                for chunk in sse_events(resp):
                    self.wfile.write(chunk.encode())
                self.wfile.flush()
            except BrokenPipeError:
                pass
        else:
            self._send_json(200, resp)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    sys.stderr.write(f"[bridge] responses->chat bridge on 127.0.0.1:{PORT} -> {UPSTREAM}\n")
    srv.serve_forever()


if __name__ == "__main__":
    main()
