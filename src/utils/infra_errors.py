"""
Single source of truth for INFRASTRUCTURE error detection.

A cell's result is only valid if ZERO infra errors occurred during the run.
Everything here is an error of OUR harness/environment — never of the model —
so an affected run must be re-run (or the env fixed first), NEVER scored.

Used by:
  - claude_code_proxy: head-of-log runtime guard (0-turn failures)
  - unit_test_runner / eval: stamp `infra_error` into eval reports
  - scripts/build_final_results.py: refuse infra-stamped / infra-classified reports
  - scripts/infra_scan.py: full-corpus proactive scan (run after every wave)

Catalog (every class we have actually hit in this project):
  unknown_command       /skill-id failed to resolve -> CLI dies at turn 0
  api_unreachable       ConnectionRefused (CCR/bridge dead, port collision)
  rate_limited          subscription quota / access-disabled mid-run
  workspace_missing     eval can't cd to /workspace/<repo> (rootfs/container lost)
  tool_missing          eval env lacks a required binary (bun/zip/cabal/...)
  oom_killed            build/test SIGKILLed — job memory under-provisioned
  setup_failed          setup_commands / enroot create / repo init failed
  container_lost        eval attached to nonexistent container / empty report
NOTE 'timeout' is deliberately NOT an infra class: by project policy a run that
exceeds the raised cap is COUNTED as failed (score 0), not re-run forever.
"""

from __future__ import annotations
import re

# --- log-head classes (first bytes of the interaction log decide) -----------
LOG_HEAD_CLASSES = (
    ("unknown_command", re.compile(r"^Unknown command: /")),
    ("api_unreachable", re.compile(r"^API Error: Unable to connect to API")),
)

# --- eval-output classes (pytest/build stdout+stderr in the report) ---------
EVAL_OUTPUT_CLASSES = (
    # workspace_missing = the repo ROOT is gone. Match `cd` failures and
    # single-component /workspace/<repo> paths ONLY — a deeper path like
    # '/workspace/repo/src/x.py' missing is an AGENT failure (undelivered
    # file), not infra (2026-07-26: loose pattern false-refused valid reports).
    ("workspace_missing", re.compile(
        r"can't cd to /workspace/|No such file or directory: '/workspace/[^/']+/?'")),
    # Both shapes are restricted to the SAME allowlist of binaries the eval
    # genuinely requires. An unrestricted "X: not found" match false-flags
    # harmless probe noise from build scripts — e.g. bun's build:debug greps
    # for `docker` and prints "docker: not found" on every run while the real
    # failure is elsewhere (2026-07-26: 13 jsc cells mis-blamed this way).
    # `docker` is deliberately ABSENT: this cluster has none by design, and no
    # eval requires it.
    ("tool_missing", re.compile(
        r"(?:^|[;&|]\s*|/bin/sh: (?:\d+: )?|bash: (?:line \d+: )?)"
        r"(?:bun|zip|unzip|cabal|stack|ghc|clang(?:-\d+)?|zig|bazel|mvn|cargo|rustc|go|node|pnpm|pytest)"
        r": (?:command )?not found", re.M)),
    ("tool_missing", re.compile(
        r"\[Errno 2\] No such file or directory: "
        r"'(?:bun|zip|unzip|cabal|stack|ghc|clang(?:-\d+)?|zig|bazel|mvn|cargo|rustc|go|node|pnpm)'")),
    # OOM-killed build/test: the harness under-provisioned memory, not an
    # agent defect (bun's debug build needs ~200G; 96G gets SIGKILLed).
    ("oom_killed", re.compile(
        r"terminated by signal SIGKILL|Build failed with exit code 137|exit code[:= ]+137\b")),
)

# --- report-level classes ----------------------------------------------------
def classify_report(report: dict) -> str | None:
    """Classify an eval-report dict. Returns an infra class or None (clean).

    Timeout-terminated reports are policy-counted (return None) — see module
    docstring — but any OTHER success:false + error report is infra.
    """
    stamped = report.get("infra_error")
    if stamped:
        return str(stamped)
    if report.get("stage") == "timeout":
        return None  # policy: counted as 0, not infra
    if report.get("success") is False or report.get("error"):
        return "setup_failed"
    ev = report.get("evaluation_scores") or {}
    if ev.get("overall_score") is None:
        return "container_lost"
    text = _report_text(report)
    for cls, pat in EVAL_OUTPUT_CLASSES:
        if pat.search(text):
            return cls
    return None


def classify_log_head(head: str) -> str | None:
    """Classify the first bytes of an interaction log. None = clean."""
    head = (head or "").lstrip()
    for cls, pat in LOG_HEAD_CLASSES:
        if pat.search(head):
            return cls
    return None


def _report_text(report: dict) -> str:
    """Concatenate the free-text fields of a report for pattern scans."""
    parts = []
    ev = report.get("evaluation_scores") or {}
    for d in ev.get("details") or []:
        parts.append(str(d.get("message", "")))
        det = d.get("details")
        if det:
            parts.append(str(det))
    return "\n".join(parts)
