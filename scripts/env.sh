#!/bin/bash
# Canonical project paths — single source of truth. Source this for interactive use:
#     source scripts/env.sh

# Resolve the project root from this file's location (works when sourced).
_ENV_SH="${BASH_SOURCE[0]:-$0}"
PROJECT_DIR="$(cd "$(dirname "$_ENV_SH")/.." && pwd)"
export PROJECT_DIR

# enroot squashfs image store (see data/enroot-images/README.md). Overridable.
export SWE_ENROOT_IMAGE_CACHE="${SWE_ENROOT_IMAGE_CACHE:-$PROJECT_DIR/data/enroot-images}"

# Generated outputs root (run reports, API traces, run logs).
export OUTPUTS_DIR="${OUTPUTS_DIR:-$PROJECT_DIR/outputs}"
