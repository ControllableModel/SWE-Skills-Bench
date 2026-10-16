#!/bin/bash
# Full codex (GPT-5.4-mini) none-vs-one run: 10 batches × {none, one} × 98 skills.
# codex native arm — subscription OAuth (~/.codex/auth.json provisioned per container),
# NO CCR gateway (SWE_LOCAL_CCR=0). Selects the *-codex images (AGENT=codex).
#
# 20 jobs (batch1..10 × {none,one}). Submitted as 10 parallel chains, one chain per
# batch (none -> one sequential via afterany), so at most 10 nodes are busy at
# once — leaving headroom on the cluster. Each job is --exclusive on its node.
#
# Usage: bash scripts/launch_codex_none_one.sh [--dry-run]
set -euo pipefail
PROJECT_DIR="${PROJECT_DIR:-${SLURM_SUBMIT_DIR:-$(pwd)}}"
SB="$PROJECT_DIR/scripts/run_batch.sbatch"
MODEL="${CODEX_MODEL:-gpt-5.4-mini}"

RES=(${PARTITION:+--partition=$PARTITION} ${QOS:+--qos=$QOS} --exclusive --cpus-per-task=8 --mem=256G --time=24:00:00)
# Per-cell interaction cap (codex cells ~3-5min; heavy cargo/jvm skills need headroom).
COMMON_ENV="AGENT=codex,MODEL_NAME=${MODEL},CODEX_MODEL=${MODEL},SWE_LOCAL_CCR=0,SWE_FRESH_CONTAINER=1,FORCE_RERUN=true,SWE_TOTAL_TIMEOUT_SEC=2400"

DRY=""; [[ "${1:-}" == "--dry-run" ]] && DRY=1 && echo "[dry-run] model=$MODEL"

submit_chain() {
    local batch="$1"; local prev=""
    for mode in none one; do
        local dep=""; [[ -n "$prev" ]] && dep="--dependency=afterany:$prev"
        local exp="ALL,${COMMON_ENV},BATCH=${batch},SKILL_MODE=${mode}"
        local cmd=(sbatch --job-name="cx-${batch}-${mode}" "${RES[@]}" $dep --export="$exp" "$SB")
        if [[ -n "$DRY" ]]; then
            echo "  [$batch] ${prev:+after $prev } sbatch ... BATCH=$batch SKILL_MODE=$mode"
            prev="DRY_${batch}_${mode}"
        else
            local jid; jid=$("${cmd[@]}" | awk '{print $NF}')
            echo "  [$batch] cx-${batch}-${mode} -> $jid${prev:+ (after $prev)}"; prev="$jid"
        fi
    done
}

for b in batch1 batch2 batch3 batch4 batch5 batch6 batch7 batch8 batch9 batch10; do
    submit_chain "$b"
done
echo; squeue -u "$USER" -o "%.10i %.16j %.9T %.20E %R" 2>/dev/null | head -25
