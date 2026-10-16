# shellcheck shell=bash
# ------------------------------------------------------------------------------------
# lib_local_ccr.sh  —  start a local claude-code-router (CCR) gateway for this run.
#
# WHY: for OpenAI-compatible models the Claude Code CLI is driven through CCR (Anthropic<->OpenAI
# protocol gateway + reasoning transformer). A single shared gateway is a single point of
# failure under many concurrent streams, so each run starts its own local instance.
#
# HOW IT WORKS: enroot shares the host network namespace, so the in-container claude reaches
# the gateway on the host loopback (http://127.0.0.1:$PORT). Per-instance state is isolated with
# HOME=/tmp/ccr-$RUN_ID (CCR resolves its dir from $HOME).
#
# CONTRACT: source AFTER conda activate, BEFORE invoking run_all_skills.py. Requires
# RUN_ID (falls back to SLURM_JOB_ID, then the shell PID). Optional env: KIMI_BASE_URL
# (override the provider api_base_url),
# SERVICE_PORT (default 3456), CCR_NODE_BIN (node bin dir). On success it EXPORTS
# ANTHROPIC_BASE_URL=http://127.0.0.1:$PORT and installs an EXIT trap to stop CCR + clean up.
# On failure to become healthy it exits the run LOUDLY (never run against a dead gateway).
# ------------------------------------------------------------------------------------

RUN_ID="${RUN_ID:-${SLURM_JOB_ID:-$$}}"
# Per-run port (same scheme as the codex bridge): a fixed :3456 breaks node-sharing —
# the 2nd job's CCR fails to bind, its health probe then hits the 1st job's CCR (200!),
# and when either job exits its trap kills the shared instance -> ConnectionRefused
# mid-run for the survivor (2026-07-24 gf6: 6 cells). SERVICE_PORT still overrides.
_LCCR_PORT="${SERVICE_PORT:-$((31000 + RUN_ID % 20000))}"
_LCCR_HOME="/tmp/ccr-${RUN_ID}"
_LCCR_NODE_BIN="${CCR_NODE_BIN:-$(dirname "$(command -v node)")}"
_LCCR_TEMPLATE="$HOME/.claude-code-router/config.json"

mkdir -p "$_LCCR_HOME/.claude-code-router" "$_LCCR_HOME/tmp"
# Clean up the isolated CCR on ANY job exit (set the trap before doing anything killable).
trap '_lccr_teardown' EXIT
_lccr_teardown() {
    # Kill the CCR server by the pid it wrote (avoid `ccr stop`, which can hang like start).
    local _pid
    _pid="$(cat "$_LCCR_HOME/.claude-code-router/.claude-code-router.pid" 2>/dev/null)"
    [[ -n "$_pid" ]] && kill "$_pid" 2>/dev/null || true
    rm -rf "$_LCCR_HOME" 2>/dev/null || true
}

if [[ ! -f "$_LCCR_TEMPLATE" ]]; then
    echo "ERROR(lib_local_ccr): CCR config template not found: $_LCCR_TEMPLATE" >&2
    exit 1
fi
cp "$_LCCR_TEMPLATE" "$_LCCR_HOME/.claude-code-router/config.json"
if [[ -n "${KIMI_BASE_URL:-}" ]]; then
    python3 - "$_LCCR_HOME/.claude-code-router/config.json" "$KIMI_BASE_URL" <<'PY'
import json, sys
path, url = sys.argv[1], sys.argv[2]
cfg = json.load(open(path))
for prov in cfg.get("Providers", []):
    if prov.get("name") == "kimi":
        prov["api_base_url"] = url
json.dump(cfg, open(path, "w"), indent=2)
PY
fi

export PATH="$_LCCR_NODE_BIN:$PATH"
# Start CCR with an ISOLATED HOME (relocates config.json / pid / logs off shared WeKa).
# NOTE: `ccr start` HANGS in this env (the detached child keeps the redirected stdio pipe
# open, so the parent never returns). Launch the underlying server FULLY detached via
# setsid + </dev/null + & so this script proceeds to the readiness gate below.
_LCCR_CLI="$(dirname "$_LCCR_NODE_BIN")/lib/node_modules/@musistudio/claude-code-router/dist/cli.js"
if [[ ! -f "$_LCCR_CLI" ]]; then
    echo "ERROR(lib_local_ccr): CCR cli.js not found: $_LCCR_CLI" >&2; exit 1
fi
setsid env HOME="$_LCCR_HOME" TMPDIR="$_LCCR_HOME/tmp" SERVICE_PORT="$_LCCR_PORT" \
    node "$_LCCR_CLI" start >"$_LCCR_HOME/ccr_start.log" 2>&1 </dev/null &

# Readiness gate: <=60s; fail the job loudly rather than run against a dead gateway.
_lccr_ok=0
for _i in $(seq 1 60); do
    if [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 "http://127.0.0.1:${_LCCR_PORT}/" 2>/dev/null)" == "200" ]]; then
        _lccr_ok=1; break
    fi
    sleep 1
done
if [[ "$_lccr_ok" != "1" ]]; then
    echo "ERROR(lib_local_ccr): local CCR not healthy on 127.0.0.1:${_LCCR_PORT} within 60s" >&2
    tail -5 "$_LCCR_HOME/ccr_start.log" 2>/dev/null >&2 || true
    exit 1
fi

export ANTHROPIC_BASE_URL="http://127.0.0.1:${_LCCR_PORT}"
echo "lib_local_ccr: node-local CCR healthy on ${ANTHROPIC_BASE_URL} (HOME=$_LCCR_HOME) on $(hostname)"
