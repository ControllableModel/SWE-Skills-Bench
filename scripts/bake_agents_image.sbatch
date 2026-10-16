#!/bin/bash
#SBATCH --job-name=bake-codex
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=01:00:00
#SBATCH --output=outputs/slurm_logs/%x-%j.out
#SBATCH --error=outputs/slurm_logs/%x-%j.err
#
# Bake @openai/codex into a benchmark image via enroot export (no docker), on top of the
# already-CLI-baked `-cli2168` set. Same mechanism as scripts/bake_image.sbatch — the CLI is
# PHYSICALLY installed into a --rw instance then frozen with `enroot export` into a self-contained
# sqsh (NOT a runtime mount). Basing on `-cli2168` keeps the validated claude 2.1.168 byte-identical.
#
# Env:
#   BASE          sqsh basename WITHOUT .sqsh, e.g. zhangyiiiiii+swe-skills-bench-python-cli2168 (required)
#   CODEX_VERSION @openai/codex version to pin (default 0.144.1)
#   SMOKE         1 = after export, run a real `codex exec` headless smoke with host ~/.codex auth
#                 mounted at /home/dev/.codex (default 1). Set 0 for batch bakes after the first is green.
#   SMOKE_MODEL   model slug for the smoke exec (default gpt-5.5)
#
# Output: $IMG/${BASE}-codex.sqsh  (contains claude + codex)
set -euo pipefail
IMG="${SWE_ENROOT_IMAGE_CACHE:-${PROJECT_DIR:-${SLURM_SUBMIT_DIR:-$(pwd)}}/data/enroot-images}"
: "${BASE:?set BASE (e.g. zhangyiiiiii+swe-skills-bench-python-cli2168)}"
CODEX_VERSION="${CODEX_VERSION:-0.144.1}"
SMOKE="${SMOKE:-1}"
SMOKE_MODEL="${SMOKE_MODEL:-gpt-5.5}"
SRC="$IMG/${BASE}.sqsh"
OUT="$IMG/${BASE}-codex.sqsh"
[ -f "$SRC" ] || { echo "missing $SRC"; exit 1; }

echo "=================================================="
echo "[bake-codex] host=$(hostname)  enroot=$(enroot version 2>/dev/null)"
echo "[bake-codex] SRC=$SRC"
echo "[bake-codex] OUT=$OUT"
echo "[bake-codex] codex pin=$CODEX_VERSION  SMOKE=$SMOKE  SMOKE_MODEL=$SMOKE_MODEL"
echo "=================================================="

# Some base images (pytorch, the -cli2168 variants) bake NVIDIA_VISIBLE_DEVICES=all; on a
# CPU-only node lacking nvidia-container-cli the enroot 98-nvidia.sh hook then fails EVERY
# `enroot start`. NVIDIA_VISIBLE_DEVICES=void makes the hook short-circuit (same fix as the
# runtime in enroot_manager.py). Apply to ALL bake starts, not just the smoke.
NV="-e NVIDIA_VISIBLE_DEVICES=void"
NAME="bakecodex_${BASE//[^a-zA-Z0-9]/_}_${SLURM_JOB_ID}"
cleanup() { enroot remove -f "$NAME" 2>/dev/null || true; enroot remove -f "${NAME}_smoke" 2>/dev/null || true; rm -rf "/tmp/codexhome-${SLURM_JOB_ID}" 2>/dev/null || true; }
trap cleanup EXIT

if [ -f "$OUT" ]; then
    echo "[bake-codex] already baked: $OUT (skipping bake; still running smoke if SMOKE=1)"
else
    enroot create --name "$NAME" "$SRC" 2>&1 | tail -1
    # NOTE: GPU base images (pytorch) print a large CUDA banner on every `enroot start`, which
    # pollutes `head -1` and (via early pipe close) raises SIGPIPE -> exit 13 under pipefail.
    # Detect versions by grepping the version PATTERN with `grep -m1`, guarded with `|| true`.
    echo "[bake-codex] claude before: $(enroot start $NV "$NAME" claude --version 2>&1 | grep -m1 -oiE '[0-9]+\.[0-9]+\.[0-9]+ \(Claude Code\)' || true)"
    echo "[bake-codex] codex before:  $(enroot start $NV "$NAME" bash -lc 'command -v codex || echo NONE' 2>&1 | grep -m1 -oE '(/[^ ]*codex|NONE)' || true)"
    echo "[bake-codex] installing @openai/codex@${CODEX_VERSION} ..."
    enroot start --rw $NV "$NAME" bash -lc "npm i -g @openai/codex@${CODEX_VERSION} >/tmp/npm_codex.log 2>&1 && echo NPM_OK || (echo NPM_FAIL; tail -20 /tmp/npm_codex.log)"
    CODEX_VER_IN=$(enroot start $NV "$NAME" bash -lc 'codex --version 2>&1' | grep -m1 -oiE 'codex-cli[ ]*[0-9][0-9.]*' || true)
    CLAUDE_VER_IN=$(enroot start $NV "$NAME" claude --version 2>&1 | grep -m1 -oiE '[0-9]+\.[0-9]+\.[0-9]+ \(Claude Code\)' || true)
    echo "[bake-codex] codex after:  $CODEX_VER_IN"
    echo "[bake-codex] claude after: $CLAUDE_VER_IN  (must be unchanged)"
    case "$CODEX_VER_IN" in
        *"$CODEX_VERSION"*|*codex*[0-9]*) echo "[bake-codex] codex install OK" ;;
        *) echo "[bake-codex] ERROR: codex not runnable in image ('$CODEX_VER_IN')"; exit 1 ;;
    esac
    enroot export --output "$OUT" "$NAME" 2>&1 | tail -1
    enroot remove -f "$NAME" 2>&1 | tail -1
    ls -la "$OUT"
    echo "[bake-codex] EXPORT DONE"
fi

# ---------------------------------------------------------------------------------------
# SMOKE: prove `codex exec` runs headless inside the EXPORTED image, reaching the ChatGPT
# subscription backend via host ~/.codex auth mounted at /home/dev/.codex (same HOME/USER as
# the real benchmark container: -e HOME=/home/dev -e USER=dev, NVIDIA_VISIBLE_DEVICES=void).
# ---------------------------------------------------------------------------------------
if [ "$SMOKE" != "1" ]; then
    echo "[bake-codex] SMOKE=0 — skipping runtime smoke."; echo "[bake-codex] DONE $BASE $(date -Iseconds)"; exit 0
fi

[ -f "$HOME/.codex/auth.json" ] || { echo "[smoke] ERROR: $HOME/.codex/auth.json missing (run \`codex login\` first)"; exit 1; }
CODEX_HOME="/tmp/codexhome-${SLURM_JOB_ID}"
mkdir -p "$CODEX_HOME"
cp "$HOME/.codex/auth.json" "$CODEX_HOME/auth.json"
# Minimal config: chatgpt subscription login, trust the workdir so exec won't prompt.
cat > "$CODEX_HOME/config.toml" <<'TOML'
forced_login_method = "chatgpt"
[projects."/home/dev"]
trust_level = "trusted"
TOML
chmod 600 "$CODEX_HOME/auth.json"

SMK="${NAME}_smoke"
enroot create --name "$SMK" "$OUT" 2>&1 | tail -1
echo "[smoke] running: codex exec (model=$SMOKE_MODEL) inside $SMK ..."
set +e
SMOKE_OUT=$(enroot start \
    -e HOME=/home/dev -e USER=dev -e CI=true -e NVIDIA_VISIBLE_DEVICES=void \
    --mount "${CODEX_HOME}:/home/dev/.codex:bind,rw,x-create=dir" \
    "$SMK" bash -lc '
        cd /home/dev
        codex --version
        echo "---EXEC---"
        codex exec "Reply with exactly the single word: PONG" \
            -m '"$SMOKE_MODEL"' \
            --dangerously-bypass-approvals-and-sandbox \
            --skip-git-repo-check 2>&1
        echo "---EXIT=$?---"
    ' 2>&1)
SMK_RC=$?
set -e
echo "===================== SMOKE OUTPUT ====================="
echo "$SMOKE_OUT"
echo "======================================================="
if echo "$SMOKE_OUT" | grep -qiE '\bPONG\b'; then
    echo "[smoke] ✅ PASS — codex exec reached backend and produced output (found PONG)."
    echo "[bake-codex] DONE $BASE $(date -Iseconds)"
    exit 0
else
    echo "[smoke] ❌ FAIL — no PONG in output (rc=$SMK_RC). Inspect above (auth expired? no egress? model slug?)."
    exit 2
fi
