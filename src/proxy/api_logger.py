"""
Anthropic API logging proxy.

Sits between Claude Code CLI and api.anthropic.com. Logs each outbound
request's body (system prompt, messages, tools) so we can verify
experimentally what the CLI actually sends to the model — especially
useful to confirm whether SKILL.md content was injected into the system
prompt under different skill_mode settings.

Deploy: run as a background process; point Claude Code at it via
ANTHROPIC_BASE_URL=http://<host>:<port>. Requests are forwarded to the
real Anthropic API preserving auth, streaming, and headers.

Usage:
    PROXY_PORT=4100 PROXY_LOG_DIR=/tmp/api_trace \\
        uvicorn src.proxy.api_logger:app --host 0.0.0.0 --port $PROXY_PORT
"""

import json
import os
import time
import uuid
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse


UPSTREAM = os.environ.get("PROXY_UPSTREAM", "https://api.anthropic.com")
LOG_DIR = Path(os.environ.get("PROXY_LOG_DIR", "/tmp/api_trace"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Persistent client for connection reuse. Long timeout for long-running streams.
_timeout = httpx.Timeout(connect=30.0, read=600.0, write=120.0, pool=30.0)
_client = httpx.AsyncClient(timeout=_timeout, follow_redirects=False, http2=False)

# Strip hop-by-hop headers before forwarding. Keep Authorization untouched.
_HOP_HEADERS = {"host", "content-length", "connection", "keep-alive",
                "proxy-authenticate", "proxy-authorization", "te",
                "trailers", "transfer-encoding", "upgrade"}


app = FastAPI()


# NOTE: FastAPI/Starlette route resolution is in registration order. The
# catch-all passthrough below MUST come last — otherwise specific routes
# like /_proxy_health and /v1/messages get shadowed and forwarded upstream.
@app.get("/_proxy_health")
async def health():
    return {"ok": True, "upstream": UPSTREAM, "log_dir": str(LOG_DIR)}


def _redact(h: str) -> str:
    """Partially redact an auth token so it's safe to log."""
    if not h:
        return ""
    if len(h) <= 12:
        return "***"
    return h[:8] + "..." + h[-4:]


def _filtered_headers(request: Request) -> dict:
    return {k: v for k, v in request.headers.items() if k.lower() not in _HOP_HEADERS}


def _log_request(trace_id: str, parsed: dict, auth_redacted: str, meta: dict):
    """Write a JSON snapshot of an outbound request for later audit."""
    log_path = LOG_DIR / f"req_{trace_id}.json"
    snapshot = {
        "trace_id": trace_id,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "auth_prefix": auth_redacted,
        "meta": meta,
        "model": parsed.get("model"),
        # System prompt may be a string OR a list of content blocks.
        # Both shapes are kept verbatim so downstream greps see the text.
        "system": parsed.get("system"),
        "tools": parsed.get("tools"),
        "tool_choice": parsed.get("tool_choice"),
        "max_tokens": parsed.get("max_tokens"),
        "temperature": parsed.get("temperature"),
        "stream": parsed.get("stream"),
        "n_messages": len(parsed.get("messages", []) or []),
        # Full message array — large but necessary for provenance.
        "messages": parsed.get("messages"),
    }
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


@app.post("/v1/messages")
async def messages(request: Request) -> Response:
    body = await request.body()
    try:
        parsed = json.loads(body) if body else {}
    except Exception:
        parsed = {}

    # Trace id from client hint or random; used as filename suffix.
    trace_id = (
        request.headers.get("x-request-id")
        or request.headers.get("x-session-id")
        or f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    )

    auth_redacted = _redact(request.headers.get("authorization", "")
                            or request.headers.get("x-api-key", ""))

    # Per-task context hints — Claude Code may send these.
    meta = {
        "user-agent": request.headers.get("user-agent", ""),
        "x-claude-version": request.headers.get("x-claude-version", ""),
        "anthropic-version": request.headers.get("anthropic-version", ""),
    }
    _log_request(trace_id, parsed, auth_redacted, meta)

    headers = _filtered_headers(request)
    upstream_url = f"{UPSTREAM}/v1/messages"
    is_stream = bool(parsed.get("stream"))

    if is_stream:
        # One upstream POST. Open the response in stream mode, inspect status,
        # then either read fully (non-200) or yield chunks (200). Closing the
        # response is the stream_gen()'s responsibility via `finally`.
        req = _client.build_request("POST", upstream_url, content=body, headers=headers)
        upstream_resp = await _client.send(req, stream=True)
        resp_headers = {k: v for k, v in upstream_resp.headers.items()
                        if k.lower() not in _HOP_HEADERS}

        if upstream_resp.status_code != 200:
            content_bytes = await upstream_resp.aread()
            await upstream_resp.aclose()
            return Response(
                content=content_bytes,
                status_code=upstream_resp.status_code,
                headers=resp_headers,
            )

        async def stream_gen() -> AsyncIterator[bytes]:
            try:
                async for chunk in upstream_resp.aiter_raw():
                    yield chunk
            finally:
                await upstream_resp.aclose()

        return StreamingResponse(
            stream_gen(),
            status_code=200,
            media_type=upstream_resp.headers.get("content-type", "text/event-stream"),
            headers={k: v for k, v in resp_headers.items()
                     if k.lower() not in ("content-type", "content-length")},
        )

    # Non-streaming path
    upstream_resp = await _client.post(upstream_url, content=body, headers=headers)
    resp_headers = {k: v for k, v in upstream_resp.headers.items()
                    if k.lower() not in _HOP_HEADERS}
    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers=resp_headers,
    )


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def passthrough(path: str, request: Request) -> Response:
    """Transparent forward for non-/v1/messages endpoints (e.g. /v1/models)."""
    body = await request.body()
    headers = _filtered_headers(request)
    url = f"{UPSTREAM}/{path}"
    r = await _client.request(request.method, url, content=body, headers=headers,
                              params=dict(request.query_params))
    resp_headers = {k: v for k, v in r.headers.items() if k.lower() not in _HOP_HEADERS}
    return Response(content=r.content, status_code=r.status_code, headers=resp_headers)
