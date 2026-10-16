#!/bin/bash
# Pre-cache all enroot images to shared storage so parallel jobs don't race.
set -u

CACHE="${SWE_ENROOT_IMAGE_CACHE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/data/enroot-images}"
mkdir -p "$CACHE"
cd "$CACHE"

# Every base_image referenced by the config ("-ext" images may need a local build,
# see the README).
CFG="${CONFIG:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/config/benchmark_config.yaml}"
mapfile -t IMAGES < <(python3 -c "import yaml,sys; print('\n'.join(sorted({s['environment']['base_image'] for s in yaml.safe_load(open(sys.argv[1]))['skills']})))" "$CFG")

for img in "${IMAGES[@]}"; do
    # Derive sqsh filename (matches EnrootManager._docker_ref_to_sqsh_name)
    fname="$(echo "$img" | tr '/:' '++').sqsh"
    if [[ -f "$CACHE/$fname" ]]; then
        echo "[skip] $fname already cached"
        continue
    fi
    echo "[import] $img -> $fname"
    ts_start=$(date +%s)
    enroot import -o "$fname" "docker://$img" 2>&1 | tail -2 || { echo "FAILED: $img"; exit 1; }
    echo "  done in $(($(date +%s) - ts_start))s, size=$(ls -lh "$fname" | awk '{print $5}')"
done

echo "=== cache state ==="
ls -lh "$CACHE"
