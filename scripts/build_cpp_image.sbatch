#!/bin/bash
#SBATCH --job-name=build-cpp-img
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=256G
#SBATCH --time=02:00:00
#SBATCH --output=outputs/slurm_logs/%x-%j.out
#SBATCH --error=outputs/slurm_logs/%x-%j.err
#
# Build swe-skills-bench-cpp-ext image via enroot export (NO docker).
# Derives from the already-built node-ext sqsh (has node20 + claude-cli 2.1.168
# + g++/make via build-essential + python3 + pytest); only adds cmake.
# Output sqsh is the harness-expected name for base_image
# "zhangyiiiiii/swe-skills-bench-cpp-ext".  Lives in the same cache dir as the
# other benchmark images.
set -euo pipefail

IMG="${SWE_ENROOT_IMAGE_CACHE:-${PROJECT_DIR:-${SLURM_SUBMIT_DIR:-$(pwd)}}/data/enroot-images}"
export SWE_ENROOT_IMAGE_CACHE="$IMG"

SRC="$IMG/zhangyiiiiii+swe-skills-bench-node-ext.sqsh"   # node-ext base (has cli2168 + g++)
OUT="$IMG/zhangyiiiiii+swe-skills-bench-cpp-ext.sqsh"

[ -f "$SRC" ] || { echo "[build] missing base $SRC"; exit 1; }
if [ -f "$OUT" ]; then echo "[build] already exists: $OUT (remove to rebuild)"; exit 0; fi

NAME="buildcpp_${SLURM_JOB_ID:-manual}"
echo "[build] host=$(hostname)  $SRC -> $OUT"

enroot remove -f "$NAME" 2>/dev/null || true
enroot create --name "$NAME" "$SRC" 2>&1 | tail -1

echo "[build] base: g++ $(enroot start "$NAME" bash -lc 'g++ --version 2>/dev/null | head -1')"
echo "[build] base: cmake $(enroot start "$NAME" bash -lc 'cmake --version 2>/dev/null | head -1 || echo none')"

# Add cmake (+ ninja, pkg-config). apt needs root -> --root at BUILD time is fine
# (claude only refuses euid=0 at RUN time).
enroot start --rw --root "$NAME" bash -lc \
  'apt-get update >/dev/null 2>&1 && apt-get install -y --no-install-recommends cmake ninja-build pkg-config >/dev/null 2>&1 && echo "[build] cmake installed" || { echo "[build] apt cmake FAILED"; exit 1; }'

echo "[build] verify toolchain:"
enroot start "$NAME" bash -lc '
  echo "  cmake:  $(cmake --version | head -1)"
  echo "  g++:    $(g++ --version | head -1)"
  echo "  make:   $(make --version | head -1)"
  echo "  claude: $(claude --version 2>&1 | head -1)"
  echo "  pytest: $(python3 -m pytest --version 2>&1 | head -1)"
'
CLAUDE_V=$(enroot start "$NAME" bash -lc 'claude --version 2>&1 | head -1')
case "$CLAUDE_V" in 2.1.168*) echo "[build] claude version OK ($CLAUDE_V)";; *) echo "[build] WARN: unexpected claude '$CLAUDE_V'";; esac

# Export finished rootfs to the harness-expected sqsh name.
enroot export --output "$OUT" "$NAME" 2>&1 | tail -1
enroot remove -f "$NAME" 2>&1 | tail -1
ls -la "$OUT"
echo "[build] DONE swe-skills-bench-cpp-ext at $(date -Iseconds)"
