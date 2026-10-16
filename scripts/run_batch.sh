#!/bin/bash
#
# Runner for the unified 98 skills (config/benchmark_config.yaml).
# Processes ONE (batch, skill_mode) combination end-to-end: run -> eval -> cleanup.
# Plain bash; also works unchanged as a SLURM batch script (sbatch scripts/run_batch.sh).
#
# Env vars:
#   SKILL_MODE        all|none|one (required)
#   BATCH             batchN, N in 1..10 (default batch1)
#   ONLY_SKILLS       comma-separated skill ids
#   ONLY_SKILLS_FILE  path to a file with one skill id per line (preferred for multi-skill)
#   FORCE_RERUN       true to wipe the completion marker first
set -euo pipefail
RUN_ID="${RUN_ID:-${SLURM_JOB_ID:-$$}}"

BATCH="${BATCH:-batch1}"
# AGENT + MODEL_NAME are the report/container dimensions. Defaults reproduce the
# original claude+haiku behaviour. For a different model, pass MODEL_NAME (must equal
# the sanitized get_model_name() output, i.e. = MODEL_NAME env / ANTHROPIC_DEFAULT_SONNET_MODEL);
# for a different agent, pass AGENT (claude|codex|gemini). e.g. for Kimi via CCR:
#   AGENT=claude MODEL_NAME=Kimi-K2.6 ANTHROPIC_DEFAULT_SONNET_MODEL=Kimi-K2.6 bash scripts/run_batch.sh
AGENT="${AGENT:-claude}"
MODEL_NAME="${MODEL_NAME:-claude-haiku-4-5}"
export AGENT MODEL_NAME
: "${SKILL_MODE:?set SKILL_MODE (all|none|one)}"
case "$SKILL_MODE" in
    all)  SUFFIX=true ;;
    none) SUFFIX=false ;;
    one)  SUFFIX=one ;;
    *) echo "ERROR: bad SKILL_MODE=$SKILL_MODE" >&2; exit 1 ;;
esac

PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
ENV_NAME="${CONDA_ENV:-swe-skills-bench}"
export SWE_ENROOT_IMAGE_CACHE="${SWE_ENROOT_IMAGE_CACHE:-$PROJECT_DIR/data/enroot-images}"
export SWE_FRESH_CONTAINER=1

# SWE_ISOLATE_ENROOT=1 → give this job its OWN enroot state (data/shared/pid/runtime), keyed by
# RUN_ID, so MULTIPLE benchmark runs can pack onto ONE node WITHOUT the node-level enroot
# state collision that poisons skill registration. Big rootfs -> shared FS; pids/runtime -> local tmp.
if [[ "${SWE_ISOLATE_ENROOT:-0}" == "1" ]]; then
    # SWE_ISOLATE_ROOT overrides where per-run rootfs live. Default (home) has a SMALL quota:
    # 6 concurrent jobs unpacking rootfs there blew it (ENOSPC across 4 nodes, 2026-07-15).
    # Point it at a large-quota filesystem for multi-job packing.
    _ISO_WEKA="${SWE_ISOLATE_ROOT:-$PROJECT_DIR/enroot-state}/job-${RUN_ID}"
    _ISO_LOCAL="/tmp/enroot-state-${RUN_ID}"
    export ENROOT_DATA_PATH="${_ISO_WEKA}/data"
    export SWE_ENROOT_SHARED_ROOT="${_ISO_WEKA}/shared"
    export SWE_ENROOT_PID_ROOT="${_ISO_LOCAL}/pids"
    export ENROOT_RUNTIME_PATH="${_ISO_LOCAL}/runtime"
    mkdir -p "$ENROOT_DATA_PATH" "$SWE_ENROOT_SHARED_ROOT" "$SWE_ENROOT_PID_ROOT" "$ENROOT_RUNTIME_PATH"
    trap 'rm -rf "${_ISO_WEKA}" "${_ISO_LOCAL}" 2>/dev/null || true' EXIT
    echo "SWE_ISOLATE_ENROOT=1: per-run enroot state (DATA=$ENROOT_DATA_PATH RUNTIME=$ENROOT_RUNTIME_PATH)"
fi

cd "$PROJECT_DIR"
mkdir -p outputs/logs
# Activate the conda env if conda is available (skip with CONDA_ENV=none).
if [[ "$ENV_NAME" != "none" ]] && command -v conda >/dev/null 2>&1; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate "$ENV_NAME"
fi

# Sanity: the requested batch must have its task + test files on disk.
if [[ ! -d "tasks/$BATCH" || ! -d "tests/$BATCH" ]]; then
    echo "ERROR: batch '$BATCH' missing tasks/ or tests/ dir" >&2; exit 1
fi

# Build a temp config from the unified config with the CLI-baked / -ext images.
TMP_CFG=/tmp/ext_cfg_${RUN_ID}.yaml
python - <<PY
import yaml, os
cfg = yaml.safe_load(open("$PROJECT_DIR/config/benchmark_config.yaml"))
cfg.setdefault("global", {})["batches"] = ["$BATCH"]
cfg["global"]["active_batch"] = "$BATCH"
cache = os.environ.get("SWE_ENROOT_IMAGE_CACHE", "")
agent = (os.environ.get("AGENT") or "claude").lower()
def sqsh(img): return os.path.join(cache, img.replace("/", "+").replace(":", "+") + ".sqsh")
for s in cfg.get("skills", []):
    img = s.get("environment", {}).get("base_image", "")
    up = img + "-cli2168"
    if agent == "codex":
        # codex arm: prefer the -codex overlay (claude+codex). cli2168 lineage -> <img>-cli2168-codex;
        # ext lineage (node-ext/cpp-ext) -> <img>-codex. Fall back to cli2168/base if unbaked.
        cli_codex, ext_codex = up + "-codex", img + "-codex"
        if img and os.path.exists(sqsh(cli_codex)):
            s["environment"]["base_image"] = cli_codex
        elif img and os.path.exists(sqsh(ext_codex)):
            s["environment"]["base_image"] = ext_codex
        elif img and os.path.exists(sqsh(up)):
            s["environment"]["base_image"] = up
            print(f"WARN: no -codex image for {s.get('id')}; using {up} (codex may be missing)")
        elif img:
            print(f"WARN: no cached sqsh for {s.get('id')} ({img}); enroot will try import at runtime")
    elif img and os.path.exists(sqsh(up)):
        s["environment"]["base_image"] = up           # python/golang/rust/jvm -> baked CLI
    elif img and os.path.exists(sqsh(img)):
        pass                                           # node-ext/cpp-ext already CLI-baked
    elif img:
        print(f"WARN: no cached sqsh for {s.get('id')} ({img}); enroot will try import at runtime")
with open("$TMP_CFG", "w") as f:
    yaml.safe_dump(cfg, f)
PY

echo "=================================================="
echo "  Job:       run $RUN_ID   Node: $(hostname)"
echo "  BATCH:     $BATCH   SkillMode: $SKILL_MODE (suffix=$SUFFIX)"
echo "  Config:    $TMP_CFG (from benchmark_config.yaml)"
echo "  Model:     ${ANTHROPIC_DEFAULT_SONNET_MODEL:-(from .env)}"
echo "  Enroot:    $(enroot version 2>/dev/null)"
echo "=================================================="

COMPLETION_FILE="outputs/reports/${AGENT}/${MODEL_NAME}/$BATCH/.batch_run_completed_use-skill-${SUFFIX}.txt"
if [[ "${FORCE_RERUN:-false}" == "true" && -f "$COMPLETION_FILE" ]]; then
    echo "FORCE_RERUN=true — removing $COMPLETION_FILE"; rm -f "$COMPLETION_FILE"
fi

ONLY_FLAG=""; RESUME_FLAG="--resume"
# Guard: if ONLY_SKILLS_FILE is requested but unreadable on THIS node, fail loudly
# rather than silently falling back to a full-batch run. (/tmp is node-local — put
# the file on the shared WeKa FS, e.g. under the project dir.)
if [[ -n "${ONLY_SKILLS_FILE:-}" ]]; then
    if [[ ! -f "${ONLY_SKILLS_FILE}" ]]; then
        echo "ERROR: ONLY_SKILLS_FILE='${ONLY_SKILLS_FILE}' not found on $(hostname). Use a shared-FS path, not /tmp." >&2
        exit 1
    fi
    ONLY_SKILLS=$(paste -sd, "${ONLY_SKILLS_FILE}")
fi
if [[ -n "${ONLY_SKILLS:-}" ]]; then
    ONLY_FLAG="--only ${ONLY_SKILLS}"; RESUME_FLAG=""
    echo "ONLY_SKILLS: $ONLY_SKILLS (no --resume)"
fi

# Interleaved interaction+eval: each skill is interacted, then evaluated
# IMMEDIATELY (container still warm), then its container is torn down. This
# avoids holding ~50 stopped containers across a long Phase-1->Phase-2 gap —
# the cause of the heavy-tail "Container not found" missing cells. The per-skill
# short-circuit guard (0-assistant-turn retry) lives inside --eval-after too.
# Node-local CCR gateway (isolated per run); exports ANTHROPIC_BASE_URL=127.0.0.1.
# Replaces the crash-prone shared login-node CCR. See scripts/lib_local_ccr.sh.
if [[ "${SWE_LOCAL_CCR:-1}" == "1" ]]; then
    source "$PROJECT_DIR/scripts/lib_local_ccr.sh"
fi

# Node-local Responses->Chat bridge for codex + chat-only backends (SGLang/vLLM).
# codex >=0.81 dropped wire_api="chat"; SGLang's native /v1/responses is broken and
# litellm's responses bridge passes through to it. SWE_CODEX_BRIDGE_UPSTREAM points at
# the real endpoint; codex is then aimed at the local bridge via CODEX_BASE_URL.
if [[ -n "${SWE_CODEX_BRIDGE_UPSTREAM:-}" ]]; then
    # Port candidates: shared nodes mean any port can be squatted (a bind failure
    # kills the bridge and every cell fails fast). Try 3.
    BRIDGE_UP=0
    for _off in 0 7001 13501; do
        BRIDGE_PORT=$((41000 + (RUN_ID + _off) % 20000))
        BRIDGE_UPSTREAM="$SWE_CODEX_BRIDGE_UPSTREAM" \
        BRIDGE_API_KEY="${SWE_CODEX_BRIDGE_KEY:-}" \
        BRIDGE_PORT="$BRIDGE_PORT" \
            python "$PROJECT_DIR/src/proxy/responses_bridge.py" \
            >> "$PROJECT_DIR/outputs/logs/bridge_${RUN_ID}.log" 2>&1 &
        BRIDGE_PID=$!
        for _i in $(seq 1 15); do
            curl -sf -m 2 "http://127.0.0.1:${BRIDGE_PORT}/v1/models" >/dev/null 2>&1 && { BRIDGE_UP=1; break; }
            kill -0 "$BRIDGE_PID" 2>/dev/null || break   # bridge died (e.g. port in use)
            sleep 1
        done
        [[ "$BRIDGE_UP" == "1" ]] && break
        echo "bridge failed on :${BRIDGE_PORT}, trying next port"
    done
    if [[ "$BRIDGE_UP" != "1" ]]; then
        echo "FATAL: bridge failed on all candidate ports — aborting job (cells would all fail)"
        exit 1
    fi
    # single merged EXIT trap — a bare `trap` here would overwrite the enroot
    # isolation cleanup installed above and leak per-run rootfs into SWE_ISOLATE_ROOT
    trap 'kill ${BRIDGE_PID} 2>/dev/null || true; rm -rf "${_ISO_WEKA:-}" "${_ISO_LOCAL:-}" 2>/dev/null || true' EXIT
    export CODEX_BASE_URL="http://127.0.0.1:${BRIDGE_PORT}/v1"
    export CODEX_API_KEY="${CODEX_API_KEY:-bridge}"
    echo "codex responses-bridge up on :${BRIDGE_PORT} -> ${SWE_CODEX_BRIDGE_UPSTREAM} (pid ${BRIDGE_PID})"
fi

echo "=== Interaction + immediate eval (mode=$SKILL_MODE, --eval-after) ==="
python run_all_skills.py --skill-mode "$SKILL_MODE" --eval-after $RESUME_FLAG $ONLY_FLAG --config "$TMP_CFG" || true

echo; echo "=== Safety cleanup (containers already removed per-skill by --eval-after) ==="
pattern="^benchmark_${AGENT}_${BATCH}_.*_use-skill-${SUFFIX}_.*${MODEL_NAME}$"
for c in $(enroot list 2>/dev/null | grep -E "$pattern" || true); do
    echo "removing $c"; enroot remove -f "$c" 2>&1 | tail -1 || true
    rm -rf "/tmp/enroot-shared/$c" "/tmp/enroot-pids/$c.pid" "/tmp/enroot-pids/$c.log"
done

echo; echo "=== Eval summary ($BATCH, mode=$SKILL_MODE) ==="
python - <<PY
import json, glob, os
pattern = f"$PROJECT_DIR/outputs/reports/$AGENT/$MODEL_NAME/$BATCH/eval/eval_report_*_use-agent-true_use-skill-$SUFFIX"+"_*.json"
seen = {}
for p in sorted(glob.glob(pattern)):
    skill = os.path.basename(p).split("eval_report_")[1].split("_use-agent")[0]
    seen[skill] = p
for skill, p in sorted(seen.items()):
    d = json.load(open(p)); ev = d.get("evaluation_scores", {})
    raw = ""
    for det in ev.get("details", []):
        dd = det.get("details", {})
        if "passed" in dd and "total" in dd: raw = f"{dd['passed']}/{dd['total']}"; break
    print(f"  {skill:34s}  {raw:10s}  overall={ev.get('overall_score',0)*100:.1f}%")
PY

rm -f "$TMP_CFG"
echo "Finished at $(date -Iseconds)"
