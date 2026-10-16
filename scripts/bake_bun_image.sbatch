#!/bin/bash
#SBATCH --job-name=bake-bun
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=02:00:00
#SBATCH --output=outputs/slurm_logs/%x-%j.out
#SBATCH --error=outputs/slurm_logs/%x-%j.err
#
# Bake the implementing-jsc-classes-zig toolchain (bun + LLVM-21 + rust stable)
# into a bun-ext image. Recipe validated by probe_jsc_zig_build round 4:
# `bun run build` at oven-sh/bun@2e610b14 exits 0 with exactly this stack.
# Everything installed SYSTEM-WIDE (eval runs as the dev user).
#
# Env: BASE (source sqsh basename, required), OUT (output basename, required)
set -euo pipefail
IMG="${SWE_ENROOT_IMAGE_CACHE:-${PROJECT_DIR:-${SLURM_SUBMIT_DIR:-$(pwd)}}/data/enroot-images}"
: "${BASE:?}"; : "${OUT:?}"
SRC="$IMG/${BASE}.sqsh"; DST="$IMG/${OUT}.sqsh"
[ -f "$SRC" ] || { echo "missing $SRC"; exit 1; }
NAME="bakebun_${SLURM_JOB_ID}"
cleanup() { enroot remove -f "$NAME" 2>/dev/null || true; rm -f "$IMG/${OUT}.sqsh.new"; }
trap cleanup EXIT

enroot create --name "$NAME" "$SRC"
enroot start --rw --root -e NVIDIA_VISIBLE_DEVICES=void "$NAME" bash -lc '
  set -ex
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq unzip curl git cmake ninja-build pkg-config golang lsb-release wget software-properties-common gnupg
  wget -qO- https://apt.llvm.org/llvm.sh | bash -s -- 21 >/tmp/llvm.log 2>&1 || tail -5 /tmp/llvm.log
  apt-get install -y -qq clang-21 lld-21
  clang-21 --version | head -1
  # rust stable, system-wide + world-writable caches (cargo fetches at eval time as dev)
  export RUSTUP_HOME=/usr/local/rustup CARGO_HOME=/usr/local/cargo
  curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain stable >/tmp/rustup.log 2>&1 || tail -5 /tmp/rustup.log
  # Link the REAL toolchain binaries, not the rustup shims: a shim resolves its
  # default toolchain via $RUSTUP_HOME, which is unset when eval runs as `dev`
  # ("rustup could not choose a version of rustc to run").
  TC=$(ls -d /usr/local/rustup/toolchains/stable-*/bin | head -1)
  for b in "$TC"/*; do ln -sf "$b" /usr/local/bin/$(basename "$b"); done
  printf "export RUSTUP_HOME=/usr/local/rustup\nexport CARGO_HOME=/usr/local/cargo\n" > /etc/profile.d/rust.sh
  chmod -R a+rwX /usr/local/cargo /usr/local/rustup
  su dev -c "rustc --version && cargo --version"
  # bun, system-wide
  export BUN_INSTALL=/usr/local/bun
  curl -fsSL https://bun.sh/install | bash >/tmp/bun.log 2>&1 || tail -5 /tmp/bun.log
  ln -sf /usr/local/bun/bin/bun /usr/local/bin/bun
  bun --version
  # zig on PATH: batch6/batch9 tests call `zig ast-check` / `zig build` directly
  # (bun run build uses its own vendored copy, so L1 passing does not imply this).
  ZIG_VER=0.15.1
  curl -fsSL "https://ziglang.org/download/${ZIG_VER}/zig-x86_64-linux-${ZIG_VER}.tar.xz" -o /tmp/zig.tar.xz \
    || curl -fsSL "https://ziglang.org/download/${ZIG_VER}/zig-linux-x86_64-${ZIG_VER}.tar.xz" -o /tmp/zig.tar.xz
  mkdir -p /usr/local/zig && tar -xJf /tmp/zig.tar.xz -C /usr/local/zig --strip-components=1
  ln -sf /usr/local/zig/zig /usr/local/bin/zig
  zig version
'
enroot export --output "$IMG/${OUT}.sqsh.new" "$NAME"
enroot remove -f "$NAME"
mv -f "$IMG/${OUT}.sqsh.new" "$DST"
echo "[bake-bun] exported $DST ($(du -h "$DST" | cut -f1))"

# verify as NON-root (eval runs as dev)
VN="${NAME}_v"
enroot create --name "$VN" "$DST"
enroot start -e NVIDIA_VISIBLE_DEVICES=void "$VN" bash -lc "bun --version && zig version && clang-21 --version | head -1 && rustc --version"
enroot remove -f "$VN"
echo "[bake-bun] done"
