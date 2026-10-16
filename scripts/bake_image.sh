#!/bin/bash
#
# Bake claude-cli@latest into a benchmark image via enroot export (no docker).
# Env: BASE = sqsh basename without .sqsh, e.g. zhangyiiiiii+swe-skills-bench-bazel
set -euo pipefail
RUN_ID="${RUN_ID:-${SLURM_JOB_ID:-$$}}"
IMG="${SWE_ENROOT_IMAGE_CACHE:-${PROJECT_DIR:-$(pwd)}/data/enroot-images}"
: "${BASE:?set BASE (e.g. zhangyiiiiii+swe-skills-bench-bazel)}"
SRC="$IMG/${BASE}.sqsh"
OUT="$IMG/${BASE}-cli2168.sqsh"
[ -f "$SRC" ] || { echo "missing $SRC"; exit 1; }
if [ -f "$OUT" ]; then echo "already baked: $OUT"; exit 0; fi
NAME="bake_${BASE//[^a-zA-Z0-9]/_}_${RUN_ID}"
echo "[bake] host=$(hostname) $SRC -> $OUT"
enroot create --name "$NAME" "$SRC" 2>&1 | tail -1
echo "[bake] before: $(enroot start "$NAME" claude --version 2>&1 | head -1)"
enroot start --rw "$NAME" bash -lc 'npm i -g @anthropic-ai/claude-code@latest >/tmp/npm.log 2>&1 && echo OK || (echo NPMFAIL; tail -8 /tmp/npm.log)'
AFTER=$(enroot start "$NAME" claude --version 2>&1 | head -1)
echo "[bake] after: $AFTER"
case "$AFTER" in 2.1.16*|2.1.17*|2.1.18*|2.2*|2.3*) ;; *) echo "[bake] WARN: unexpected version '$AFTER'";; esac
enroot export --output "$OUT" "$NAME" 2>&1 | tail -1
enroot remove -f "$NAME" 2>&1 | tail -1
ls -la "$OUT"
echo "[bake] DONE $BASE at $(date -Iseconds)"
