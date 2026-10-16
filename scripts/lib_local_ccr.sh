# shellcheck shell=bash
# ------------------------------------------------------------------------------------
# lib_local_ccr.sh  —  start a NODE-LOCAL claude-code-router (CCR) gateway for this job.
#
# WHY: the benchmark drives the Claude Code CLI through CCR (Anthropic<->OpenAI protocol
# gateway + reasoning transformer) to reach the self-hosted Kimi. A single SHARED CCR on
# the login node is a crash-prone SPOF: it dies under concurrent streams / when the session
# hops login nodes, silently turning dozens of cells into exit-1 empty runs. Since each job runs
# on its own --exclusive node, give each its OWN local CCR instead.
#
# HOW IT WORKS: enroot shares the host network namespace, so the in-container claude reaches
# a service on the compute node's loopback via http://127.0.0.1:3456 (same pattern as
# scripts/smoke_api_proxy.sbatch). Per-instance state is isolated with HOME=/tmp/ccr-$JOBID
# (CCR resolves its dir from $HOME; there is no dedicated CCR_DIR).
#
# CONTRACT: source AFTER conda activate, BEFORE invoking run_all_skills.py. Requires
# SLURM_JOB_ID. Optional env: KIMI_BASE_URL (override the kimi provider api_base_url),
# SERVICE_PORT (default 3456), CCR_NODE_BIN (node bin dir). On success it EXPORTS
# ANTHROPIC_BASE_URL=http://127.0.0.1:$PORT and installs an EXIT trap to stop CCR + clean up.
# On failure to become healthy it exits the job LOUDLY (never run against a dead gateway).
# ------------------------------------------------------------------------------------

: "${SLURM_JOB_ID:?lib_local_ccr: SLURM_JOB_ID required}"
# Per-job port (same scheme as the codex bridge): a fixed :3456 breaks node-sharing —
# the 2nd job's CCR fails to bind, its health probe then hits the 1st job's CCR (200!),
# and when either job exits its trap kills the shared instance -> ConnectionRefused
# mid-run for the survivor (2026-07-24 gf6: 6 cells). SERVICE_PORT still overrides.
_LCCR_PORT="${SERVICE_PORT:-$((31000 + SLURM_JOB_ID % 20000))}"
_LCCR_HOME="/tmp/ccr-${SLURM_JOB_ID}"
_LCCR_NODE_BIN="${CCR_NODE_BIN:-$HOME/.nvm/versions/node/v24.14.1/bin}"
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
