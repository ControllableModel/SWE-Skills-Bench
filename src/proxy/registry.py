"""
Harness proxy registry.

Maps the AGENT env var (via get_agent_name()) to the CLI proxy class the lifecycle should drive.
Default is claude → ClaudeCodeProxy, so AGENT unset / "claude" is byte-identical to the original
single-harness behaviour. Imports are lazy so a codex-only run never imports claude-specific deps
and vice-versa (both actually share deps today, but keep the seam clean for future harnesses).
"""

from typing import Type

from ..utils import get_agent_name


def get_proxy_class(agent: str = None) -> Type:
    """Return the proxy CLASS for the given agent (default: current AGENT env)."""
    name = (agent or get_agent_name() or "claude").lower()
    if name == "codex":
        from .codex_proxy import CodexCliProxy
        return CodexCliProxy
    # claude (and any unknown value) -> the original Claude Code proxy.
    from .claude_code_proxy import ClaudeCodeProxy
    return ClaudeCodeProxy
