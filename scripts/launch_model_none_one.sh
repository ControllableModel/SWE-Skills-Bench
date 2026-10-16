#!/bin/bash
# Launch the none-vs-one experiment (batch1..10 × {none,one} = 20 jobs, 98 skills each)
# for an ARBITRARY agent/model via run_batch.sbatch, capping concurrency at N_CHAINS via
# afterany chains. Reusable across models (Kimi, and future OpenAI-compatible endpoints).
#
# Caller MUST export the model env first (these flow into the container; lifecycle.py drops
# CLAUDE_CODE_OAUTH_TOKEN when ANTHROPIC_BASE_URL is set so the gateway is used):
#   export AGENT=claude MODEL_NAME=Kimi-K2.6 \
#          ANTHROPIC_BASE_URL=http://127.0.0.1:3456 ANTHROPIC_AUTH_TOKEN=sk-ccr-local \
#          ANTHROPIC_DEFAULT_SONNET_MODEL=Kimi-K2.6
#   bash scripts/launch_model_none_one.sh [N_CHAINS=12] [QOS=iq] [MEM=128G]
#
# NOTE: requires the translation gateway (claude-code-router `ccr start`) up at ANTHROPIC_BASE_URL.
set -euo pipefail
PROJECT_DIR="${PROJECT_DIR:-${SLURM_SUBMIT_DIR:-$(pwd)}}"
SB="$PROJECT_DIR/scripts/run_batch.sbatch"

N_CHAINS="${1:-12}"
QOS="${2:-${QOS:-}}"
MEM="${3:-384G}"
CPUS="${CPUS:-16}"
# Cluster resources are site-specific: set PARTITION, QOS, GRES via env (all optional).
PARTITION="${PARTITION:-}"
GRES="${GRES:-}"
: "${AGENT:?export AGENT}"
: "${MODEL_NAME:?export MODEL_NAME}"
: "${ANTHROPIC_BASE_URL:?export ANTHROPIC_BASE_URL (translation gateway)}"
ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:-}"
ANTHROPIC_DEFAULT_SONNET_MODEL="${ANTHROPIC_DEFAULT_SONNET_MODEL:-$MODEL_NAME}"

DRY=""; [ "${DRY_RUN:-}" = "1" ] && DRY="echo [dry] "

FORCE_RERUN="${FORCE_RERUN:-true}"  # set false to resume (skip skills already in .batch_run_completed)
COMMON_EXPORT="ALL,FORCE_RERUN=${FORCE_RERUN},AGENT=${AGENT},MODEL_NAME=${MODEL_NAME}"
COMMON_EXPORT+=",ANTHROPIC_BASE_URL=${ANTHROPIC_BASE_URL},ANTHROPIC_AUTH_TOKEN=${ANTHROPIC_AUTH_TOKEN}"
COMMON_EXPORT+=",ANTHROPIC_DEFAULT_SONNET_MODEL=${ANTHROPIC_DEFAULT_SONNET_MODEL}"

echo "Launching ${AGENT} / ${MODEL_NAME} none-vs-one : 20 jobs, ${N_CHAINS} chains, qos=${QOS}, mem=${MEM}"
echo "  gateway: ${ANTHROPIC_BASE_URL}"

# MODES env restricts which skill_modes to launch (default both). e.g. MODES=one to launch
# only one-mode (keeps an in-flight none-mode run untouched). Space-separated.
MODES="${MODES:-none one}"
JOBS=(); for n in $(seq 1 10); do for m in $MODES; do JOBS+=("batch${n}:${m}"); done; done
declare -A PREV
for i in "${!JOBS[@]}"; do
    entry="${JOBS[$i]}"; batch="${entry%:*}"; mode="${entry#*:}"; ch=$(( i % N_CHAINS ))
    dep=""; [ -n "${PREV[$ch]:-}" ] && dep="--dependency=afterany:${PREV[$ch]}"
    jid=$(${DRY}sbatch --parsable --job-name="${AGENT}-${MODEL_NAME}-${batch}-${mode}" \
        ${PARTITION:+--partition=$PARTITION} ${GRES:+--gres=$GRES} ${QOS:+--qos=$QOS} --mem="$MEM" --cpus-per-task="$CPUS" \
        --time=24:00:00 $dep \
        --export="${COMMON_EXPORT},BATCH=${batch},SKILL_MODE=${mode}" "$SB")
    PREV[$ch]="$jid"
    printf "  [chain%2d] %s-%s -> %s%s\n" "$ch" "$batch" "$mode" "$jid" "${dep:+ (after prev)}"
done
echo "Submitted. Watch: squeue -u \$USER -o '%.10i %.28j %.8T %R'"
