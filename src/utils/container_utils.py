"""
Container Utils - Container-related utility functions
Provides helper functionality for container naming and status queries.
"""

import re
from typing import Optional, Tuple


def generate_container_name(
    skill_id: str,
    use_skill,
    use_agent: bool,
    model_name: Optional[str] = None,
    batch: Optional[str] = None,
    agent: Optional[str] = None,
) -> str:
    """
    Generate a standardized container name.

    Container naming format:
        benchmark[_{agent}][_{batch}]_{skill_id}_use-skill-{true|false|one}_use-agent-{true|false}[_{model_name}]

    Args:
        skill_id: Skill ID
        use_skill: bool OR str. bool is mapped to "true"/"false" (legacy);
                   a str is used verbatim (supports "one" for with-one-skill mode).
        use_agent: Whether to use the agent
        model_name: Optional model name suffix for multi-model evaluation
        batch: Optional batch prefix (e.g. "batch1") placed at the front
        agent: Optional agent name (claude | codex | gemini) placed right after
               ``benchmark_``, so the same model under different agents does not collide.

    Returns:
        str: Container name
    """
    # Strip illegal characters (keep only letters, digits, dots, underscores, hyphens)
    safe_skill = re.sub(r"[^A-Za-z0-9._-]+", "-", skill_id)
    if not safe_skill:
        safe_skill = "skill"

    if isinstance(use_skill, bool):
        use_skill_flag = "true" if use_skill else "false"
    else:
        use_skill_flag = str(use_skill)
    use_agent_flag = "true" if use_agent else "false"

    safe_agent = re.sub(r"[^A-Za-z0-9._-]+", "-", agent) if agent else None
    safe_batch = re.sub(r"[^A-Za-z0-9._-]+", "-", batch) if batch else None

    prefix = "benchmark"
    if safe_agent:
        prefix = f"{prefix}_{safe_agent}"
    if safe_batch:
        prefix = f"{prefix}_{safe_batch}"
    name = f"{prefix}_{safe_skill}_use-skill-{use_skill_flag}_use-agent-{use_agent_flag}"

    if model_name:
        safe_model = re.sub(r"[^A-Za-z0-9._-]+", "-", model_name)
        if safe_model:
            name = f"{name}_{safe_model}"

    return name


def parse_container_name(container_name: str) -> Tuple[str, bool, bool]:
    """
    Parse parameters from a container name.

    Args:
        container_name: Container name

    Returns:
        Tuple[str, bool, bool]: (skill_id, use_skill, use_agent)

    Raises:
        ValueError: If the container name format is invalid
    """
    # agent prefix, batch prefix (batchN_) and model_name suffix are all optional.
    # The batch segment is anchored on the literal "batch\d+" so the optional agent
    # segment (when present) is consumed before it without ambiguity.
    pattern = (
        r"^benchmark_(?:[A-Za-z0-9._-]+?_)?(?:batch\d+_)?(.+?)"
        r"_use-skill-(true|false|one)_use-agent-(true|false)(?:_.+)?$"
    )
    match = re.match(pattern, container_name)

    if not match:
        raise ValueError(f"Invalid container name format: {container_name}")

    skill_id = match.group(1)
    # Returns True for both "true" and "one" (both mean "some skill is loaded");
    # callers that need the distinction should parse the raw name themselves.
    use_skill = match.group(2) != "false"
    use_agent = match.group(3) == "true"

    return skill_id, use_skill, use_agent
