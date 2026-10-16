#!/bin/bash
# Full none-vs-one sweep: batch1..10 x {none, one}, each pair run by scripts/run_batch.sh.
# Up to N_PARALLEL pairs run concurrently on this machine (default 1). Each run gets its
# own RUN_ID, so set SWE_ISOLATE_ENROOT=1 when N_PARALLEL > 1.
#
# Export the model settings first, e.g.
#   Claude Code + Anthropic API:  export AGENT=claude MODEL_NAME=claude-haiku-4-5 ANTHROPIC_AUTH_TOKEN=...
#   Claude Code + CCR gateway:    export AGENT=claude MODEL_NAME=Kimi-K2.6 ANTHROPIC_DEFAULT_SONNET_MODEL=Kimi-K2.6
#   Codex + OpenAI:               export AGENT=codex MODEL_NAME=gpt-5.4-mini CODEX_MODEL=gpt-5.4-mini SWE_LOCAL_CCR=0
#
# Usage: bash scripts/run_sweep.sh            (BATCHES / MODES / N_PARALLEL env to restrict)
set -euo pipefail
PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export PROJECT_DIR
: "${AGENT:?export AGENT (claude|codex)}"
: "${MODEL_NAME:?export MODEL_NAME}"
export FORCE_RERUN="${FORCE_RERUN:-true}"
BATCHES="${BATCHES:-$(echo batch{1..10})}"
MODES="${MODES:-none one}"
N_PARALLEL="${N_PARALLEL:-1}"
mkdir -p "$PROJECT_DIR/outputs/logs"

run_pair() {  # one batch: modes sequentially, one log per run
    local batch="$1" mode
    for mode in $MODES; do
        local id="$(date +%s)$RANDOM"
        echo "[start] $batch $mode (RUN_ID=$id)"
        BATCH="$batch" SKILL_MODE="$mode" RUN_ID="$id" \
            bash "$PROJECT_DIR/scripts/run_batch.sh" \
            > "$PROJECT_DIR/outputs/logs/${AGENT}-${MODEL_NAME}-${batch}-${mode}.log" 2>&1 \
            && echo "[done]  $batch $mode" || echo "[fail]  $batch $mode (see outputs/logs/)"
    done
}
export -f run_pair; export MODES AGENT MODEL_NAME

echo "Sweep ${AGENT}/${MODEL_NAME}: batches=[${BATCHES}] modes=[${MODES}] parallel=${N_PARALLEL}"
printf '%s\n' $BATCHES | xargs -P "$N_PARALLEL" -I{} bash -c 'run_pair "$@"' _ {}
