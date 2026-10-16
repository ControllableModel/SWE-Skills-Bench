#!/bin/bash
#
# Build swe-skills-bench-node image via enroot export (NO docker).
# Derives from the existing python sqsh (already has python3.11 + pytest),
# adds Node.js 20 LTS, then bakes claude-cli 2.1.168. Output sqsh is named
# exactly as EnrootManager._docker_ref_to_sqsh_name expects for
# base_image "zhangyiiiiii/swe-skills-bench-node", so the harness picks it up
# from cache with zero code/registry changes.
set -euo pipefail

IMG="${SWE_ENROOT_IMAGE_CACHE:-${PROJECT_DIR:-$(pwd)}/data/enroot-images}"
export SWE_ENROOT_IMAGE_CACHE="$IMG"

SRC="$IMG/zhangyiiiiii+swe-skills-bench-python.sqsh"     # plain python base
OUT="$IMG/zhangyiiiiii+swe-skills-bench-node-ext.sqsh"
NODE_MAJOR=20

[ -f "$SRC" ] || { echo "[build] missing base $SRC"; exit 1; }
if [ -f "$OUT" ]; then echo "[build] already exists: $OUT (remove it to rebuild)"; exit 0; fi

NAME="buildnode_${RUN_ID:-$$}"
echo "[build] host=$(hostname)  $SRC -> $OUT"

# Clean up any stale container with this name, then create a fresh writable rootfs.
enroot remove -f "$NAME" 2>/dev/null || true
enroot create --name "$NAME" "$SRC" 2>&1 | tail -1

echo "[build] base node: $(enroot start "$NAME" bash -lc 'node --version 2>/dev/null || echo none')"
echo "[build] base python: $(enroot start "$NAME" bash -lc 'python3 --version 2>&1 | head -1')"

# (best-effort) ensure build toolchain for native node-gyp modules; needs root,
# which is fine at BUILD time (claude only refuses euid=0 at RUN time).
enroot start --rw --root "$NAME" bash -lc \
  'apt-get update >/dev/null 2>&1 && apt-get install -y build-essential curl ca-certificates >/dev/null 2>&1 && echo "[build] build-essential ok" || echo "[build] WARN: apt build-essential skipped (non-fatal)"'

# Install Node.js 20 LTS from the official prebuilt tarball into /usr/local
# (writes to /usr/local without --root in this enroot setup; .tar.gz avoids xz dep).
enroot start --rw "$NAME" bash -lc "
  set -e
  base='https://nodejs.org/dist/latest-v${NODE_MAJOR}.x'
  fn=\$(curl -fsSL \"\$base/\" | grep -oE 'node-v${NODE_MAJOR}[0-9.]*-linux-x64\.tar\.gz' | head -1)
  [ -n \"\$fn\" ] || { echo '[build] could not resolve node tarball name'; exit 1; }
  echo \"[build] downloading \$fn\"
  curl -fsSL \"\$base/\$fn\" -o /tmp/node.tgz
  tar -xzf /tmp/node.tgz -C /usr/local --strip-components=1
  rm -f /tmp/node.tgz
  hash -r
  echo \"[build] node \$(node --version)  npm \$(npm --version)\"
  case \"\$(node --version)\" in v${NODE_MAJOR}.*) ;; *) echo '[build] ERROR: node not v${NODE_MAJOR}'; exit 1;; esac
"

# Bake claude-cli 2.1.168 (headless skill-loading hard requirement; pinned for reproducibility).
enroot start --rw "$NAME" bash -lc \
  'npm i -g @anthropic-ai/claude-code@2.1.168 >/tmp/npm.log 2>&1 && echo "[build] claude npm ok" || (echo "[build] NPMFAIL"; tail -12 /tmp/npm.log; exit 1)'
CLAUDE_V=$(enroot start "$NAME" bash -lc 'claude --version 2>&1 | head -1')
echo "[build] claude --version: $CLAUDE_V"
case "$CLAUDE_V" in 2.1.168*) echo "[build] claude version OK" ;; *) echo "[build] WARN: unexpected claude version '$CLAUDE_V'";; esac

# Export the finished rootfs to the harness-expected sqsh name.
enroot export --output "$OUT" "$NAME" 2>&1 | tail -1
enroot remove -f "$NAME" 2>&1 | tail -1
ls -la "$OUT"
echo "[build] DONE swe-skills-bench-node at $(date -Iseconds)"
