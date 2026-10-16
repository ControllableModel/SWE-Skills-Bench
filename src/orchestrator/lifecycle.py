"""
Benchmark Lifecycle - Run workflow control
Manages the lifecycle of the main benchmark run.
"""

import os
import re
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum

from .docker_manager import DockerManager, ContainerConfig, ExecutionResult
from .logger import get_logger, log_section
from ..utils import (
    generate_container_name,
    generate_report_filename,
    get_model_name,
    get_agent_name,
    get_container_skill_name,
    get_active_batch,
    get_resolved_tasks_dir,
)

logger = get_logger(__name__)


class LifecycleStage(Enum):
    """Lifecycle stages."""

    INIT = "initialization"
    ENV_SETUP = "environment_setup"
    PRE_PROCESS = "pre_process"
    SANITY_CHECK = "sanity_check"
    INTERACTION = "interaction"
    EVALUATION = "evaluation"
    CLEANUP = "cleanup"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BenchmarkResult:
    """Benchmark run result."""

    skill_id: str
    success: bool
    stage: str
    start_time: str
    end_time: str
    duration_sec: float
    iterations: int
    evaluation_scores: Dict[str, Any]
    logs: List[str]
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


class BenchmarkLifecycle:
    """
    Benchmark lifecycle manager.

    Responsibilities:
    1. Load Config: load YAML and determine the skill to run
    2. Environment Setup: start Docker, mount source code, run pre_process
    3. Sanity Check: run environment alignment and build check
    4. Interaction Loop: agent interaction loop
    5. Cleanup: stop or remove the container and finalize run state
    """

    def __init__(
        self,
        config: Dict[str, Any],
        skill_id: str,
        use_skill: bool = True,
        use_agent: bool = True,
        clean_container: bool = False,
        skill_mode: Optional[str] = None,
    ):
        """
        Initialize the lifecycle manager.

        Args:
            config: Full configuration dictionary
            skill_id: ID of the skill to run
            use_skill: Legacy bool flag. True -> skill_mode="all", False -> "none".
                       Ignored when skill_mode is provided.
            use_agent: Whether to run the agent interaction stage
            clean_container: Whether to remove the container after completion
            skill_mode: One of "all", "none", "one". Preferred over use_skill.
                        "all"  = copy every skill under skills/ (legacy --use-skill)
                        "none" = copy nothing (legacy --no-use-skill)
                        "one"  = copy only skills/<skill_id>/ AND prepend
                                "/<skill_id>\\n\\n" to the task prompt so the
                                claude CLI explicitly invokes that one skill.
        """
        self.config = config
        self.skill_id = skill_id
        self.skill_config = self._find_skill_config(skill_id)

        if not self.skill_config:
            raise ValueError(f"Skill not found: {skill_id}")

        # Select container backend based on config (global.container_backend).
        # Defaults to "docker" for backward compatibility with the paper's setup.
        backend = (config.get("global", {}) or {}).get("container_backend", "docker")
        self.container_backend = backend
        if backend == "enroot":
            from .enroot_manager import EnrootManager
            self.docker_manager = EnrootManager()
        else:
            self.docker_manager = DockerManager()
        self.stage = LifecycleStage.INIT
        self.logs: List[str] = []
        self.start_time: Optional[datetime] = None
        self.iterations = 0
        self.evaluation_scores: Dict[str, Any] = {}
        # Skill loading mode: "all" | "none" | "one"
        if skill_mode is not None:
            if skill_mode not in ("all", "none", "one"):
                raise ValueError(f"Invalid skill_mode: {skill_mode!r} (expected 'all'|'none'|'one')")
            self.skill_mode = skill_mode
        else:
            self.skill_mode = "all" if bool(use_skill) else "none"
        # Legacy bool field kept for any callers that still read .use_skill
        self.use_skill = self.skill_mode != "none"
        # Suffix used in report filenames / container names (preserves legacy naming)
        self.skill_mode_suffix = {
            "all": "true",
            "none": "false",
            "one": "one",
        }[self.skill_mode]
        # Controls whether to run the agent interaction stage (set via CLI --use-agent)
        self.use_agent = bool(use_agent)
        # Controls whether to remove the container after completion (set via CLI --clean-container)
        self.clean_container = bool(clean_container)
        # Active batch derived from config (global.active_batch or first in global.batches)
        self.batch = get_active_batch(config)
        # Actual repository path inside the container (e.g. /workspace/upgradle)
        self.repo_dir: Optional[str] = None

        # Deferred imports to avoid circular dependencies
        self._initializer = None
        self._proxy = None
        self._evaluator = None

    def _resolve_image(self, image: str) -> str:
        """Hook for backend-specific image remapping. Identity for docker/enroot."""
        return image

    def _find_skill_config(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Find the configuration for a given skill ID."""
        skills = self.config.get("skills", [])
        for skill in skills:
            if skill.get("id") == skill_id:
                return skill
        return None

    def _log(self, message: str):
        """Record a log entry."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        logger.info(message)

    def _transition_to(self, stage: LifecycleStage):
        """Transition to a new lifecycle stage."""
        self._log(f"Stage transition: {self.stage.value} -> {stage.value}")
        self.stage = stage

    async def _validate_task_file(self):
        """
        Validate the task file before starting any environment.

        If the task file is missing the program exits immediately without
        spinning up a Docker container, saving time and resources.
        """
        import sys

        log_section("Task File Validation")
        self._log(f"Validating task file for skill: {self.skill_id}")

        # Get task file path
        tasks_dir = get_resolved_tasks_dir(self.config)
        task_file_path = os.path.join(tasks_dir, f"{self.skill_id}.md")

        try:
            # Check if task file exists
            if not os.path.exists(task_file_path):
                raise FileNotFoundError(f"Task file not found: {task_file_path}")

            # Read task file content
            with open(task_file_path, "r", encoding="utf-8") as f:
                task_content = f.read()

            self._log(f"[OK] Task file validated: {task_file_path}")
            self._log(f"Task content loaded ({len(task_content)} chars)")

            # Save task content for later stages
            self._task_content = task_content

        except FileNotFoundError as e:
            # Task file is missing — exit immediately
            error_banner = f"""
{'='*70}
CRITICAL ERROR: Task file missing! Benchmark cannot proceed.
{'='*70}

{e}

To fix this issue:
1. Create the missing task file: {task_file_path}
2. The task file should contain the specific mission description for the agent

{'='*70}
"""
            print(error_banner, file=sys.stderr)
            logger.critical(str(e))
            self._log(f"CRITICAL: {e}")
            sys.exit(1)

    async def run(self) -> BenchmarkResult:
        """
        Run the complete benchmark workflow.

        Returns:
            BenchmarkResult: Benchmark run result
        """
        self.start_time = datetime.now()
        error = None
        completed_successfully = False

        try:
            # Stage 0: Strict task validation (verify task file before starting any environment)
            await self._validate_task_file()

            # Stage 1: Environment setup
            await self._stage_environment_setup()

            # Stage 2: Pre-processing (code degradation etc.)
            await self._stage_pre_process()

            # Stage 3: Sanity check
            await self._stage_sanity_check()

            # Stage 4: Agent interaction loop
            await self._stage_interaction_loop()

            # Note: evaluation stage has moved to eval.py and is not part of the main flow

            self._transition_to(LifecycleStage.COMPLETED)
            completed_successfully = True  # Record success state before cleanup

        except Exception as e:
            error = str(e)
            logger.error(f"Benchmark failed: {e}")
            self._transition_to(LifecycleStage.FAILED)

        finally:
            # Stage 6: Cleanup (based on clean_container, either fully remove or just stop)
            await self._stage_cleanup()

        # Generate result
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()

        return BenchmarkResult(
            skill_id=self.skill_id,
            success=completed_successfully,  # Use the pre-saved success state
            stage=self.stage.value,
            start_time=self.start_time.isoformat(),
            end_time=end_time.isoformat(),
            duration_sec=duration,
            iterations=self.iterations,
            evaluation_scores=self.evaluation_scores,
            logs=self.logs,
            error=error,
        )

    async def _stage_environment_setup(self):
        """Environment setup stage."""
        log_section("Environment Setup")
        self._transition_to(LifecycleStage.ENV_SETUP)

        env_config = self.skill_config.get("environment", {})
        global_config = self.config.get("global", {})

        # Prepare container configuration
        limits = env_config.get("limits", {})

        # Claude Code config file paths (on host) - will be copied into the container later
        # Use .claude-default/ for benchmark template configs (not .claude/ which may be the user's session)
        claude_default_dir = os.path.join(os.getcwd(), ".claude-default")
        self._claude_config_files = {
            "settings": os.path.join(claude_default_dir, "settings.json"),
            "settings_user": os.path.join(claude_default_dir, "settings.user.json"),
            "claude_json": os.path.join(claude_default_dir, ".claude.json"),
            "claudeignore": os.path.join(claude_default_dir, ".claudeignore"),
            "credentials": os.path.join(str(Path.home()), ".claude", ".credentials.json"),
        }

        volumes = {}

        container_config = ContainerConfig(
            image=self._resolve_image(env_config.get("base_image", "python:3.10")),
            name=generate_container_name(
                self.skill_id,
                self.skill_mode_suffix,
                self.use_agent,
                model_name=get_model_name(),
                batch=self.batch,
                agent=get_agent_name(),
            ),
            working_dir=global_config.get("workspace_dir", "/workspace"),
            network_mode=global_config.get("network_mode", "none"),
            cpus=float(limits.get("cpus", 4)),
            memory=limits.get("memory", "16g"),
            env_vars={
                **env_config.get("env_vars", {}),
                # OAuth (Max subscription) auth: only inject when NOT pointing the CLI
                # at a custom base URL. If ANTHROPIC_BASE_URL is set (e.g. a litellm
                # gateway fronting a non-Anthropic model like Kimi), the OAuth token
                # would make the CLI prefer subscription auth and bypass the gateway —
                # so we drop it and rely on ANTHROPIC_AUTH_TOKEN instead.
                **({"CLAUDE_CODE_OAUTH_TOKEN": os.environ["CLAUDE_CODE_OAUTH_TOKEN"]}
                   if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
                   and not os.environ.get("ANTHROPIC_BASE_URL") else {}),
                # Forward ANTHROPIC_BASE_URL so the container's claude CLI can be
                # pointed at a gateway (litellm translation proxy, or a logging proxy).
                **({"ANTHROPIC_BASE_URL": os.environ["ANTHROPIC_BASE_URL"]}
                   if os.environ.get("ANTHROPIC_BASE_URL") else {}),
                # Gateway auth token (litellm master_key) for the base-URL case.
                **({"ANTHROPIC_AUTH_TOKEN": os.environ["ANTHROPIC_AUTH_TOKEN"]}
                   if os.environ.get("ANTHROPIC_AUTH_TOKEN") else {}),
                # Model id the CLI's --model flag will send; also drives report paths.
                **({"ANTHROPIC_DEFAULT_SONNET_MODEL": os.environ["ANTHROPIC_DEFAULT_SONNET_MODEL"]}
                   if os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL") else {}),
            },
            volumes=volumes,
            timeout_per_command=limits.get("timeout_per_command", 300),
        )

        # Create and start container
        self._log(f"Creating container with image: {container_config.image}")
        if not self.docker_manager.create_container(container_config):
            raise RuntimeError("Failed to create container")

        if not self.docker_manager.start_container():
            raise RuntimeError("Failed to start container")

        self._log("Container started successfully")

        # Copy Claude config files to the container (not mounted, to avoid modifying the host)
        await self._copy_claude_config_to_container()

        # Clone repository
        repo_config = self.skill_config.get("repo", {})
        repo_url = repo_config.get("url")
        commit = repo_config.get("commit", "HEAD")

        if repo_url:
            await self._clone_repository(
                repo_url, commit, repo_config.get("sparse_checkout")
            )

        # Execute the skill's environment setup_commands (dependency installs, toolchain
        # fetches). These were defined in config but NEVER run in the enroot flow, leaving
        # a handful of skills (terraform / go-mod / pnpm) with un-runnable test envs.
        await self._run_setup_commands()

    async def _run_setup_commands(self):
        """Run the skill's configured environment.setup_commands in the repo dir.

        Some configs hardcode `cd /workspace/<skill-id> && ...`, but repos clone to
        /workspace/<repo-name>; strip that leading cd and run from the real repo_dir.
        """
        cmds = self.skill_config.get("environment", {}).get("setup_commands", [])
        if not cmds:
            return
        repo_dir = self.repo_dir or "/workspace"
        setup_timeout = int(os.environ.get("SWE_SETUP_TIMEOUT", "1200"))
        self._log(f"Running {len(cmds)} environment setup_command(s) in {repo_dir}")
        for cmd in cmds:
            body = re.sub(r"^\s*cd\s+/workspace/\S+\s*&&\s*", "", cmd)
            res = self.docker_manager.execute_command(
                f"cd {repo_dir} && {body}", timeout=setup_timeout
            )
            # A TIMEOUT is pathological — abort loudly rather than proceed with a
            # half-provisioned env that would silently produce a misleading score.
            if getattr(res, "timed_out", False):
                raise RuntimeError(
                    f"setup_command exceeded {setup_timeout}s (aborting to avoid a "
                    f"silently-broken env): {body[:120]}"
                )
            self._log(f"setup_command exit={res.exit_code}: {body[:90]}")
            # Non-zero (but not timed out) is only a WARNING: some are benign (e.g. an
            # apt-utils notice with exit=100 while the package still installs). The env
            # preflight gate is the real safety net for whether the env ended up usable.
            if res.exit_code != 0:
                tail = (res.stderr or res.stdout or "")[-400:]
                self._log(f"  setup_command WARNING (non-zero): {tail}")

    async def _copy_claude_config_to_container(self):
        """
        Copy Claude config files into the container (instead of mounting).
        This ensures container-side changes do not affect the host.
        Files are owned by the dev user so they can be modified.
        """
        # Harness dispatch: codex provisions ~/.codex/{auth.json,config.toml}+skills instead of
        # the Anthropic .claude tree. Claude path below is unchanged (AGENT=claude byte-identical).
        if get_agent_name() == "codex":
            await self._copy_codex_config_to_container()
            return

        self._log("Copying Claude config files to container...")

        # Create target directory inside the container
        self.docker_manager.execute_command(
            "mkdir -p /home/dev/.claude", timeout=30, user="root"
        )

        # Copy settings.json (template + local override + env var injection)
        try:
            content = self._build_claude_settings_content()
            if content is not None:
                success, msg = self.docker_manager.write_file_direct(
                    "/home/dev/.claude/settings.json", content
                )
                if success:
                    self._log(
                        f"Copied settings.json to container ({len(content)} bytes)"
                    )
                else:
                    self._log(f"Failed to copy settings.json: {msg}")
        except Exception as e:
            self._log(f"Error copying settings.json: {e}")

        # Copy .claude.json (onboarding configuration)
        claude_json_path = self._claude_config_files.get("claude_json")
        if claude_json_path and os.path.exists(claude_json_path):
            try:
                with open(claude_json_path, "rb") as f:
                    content = f.read()
                success, msg = self.docker_manager.write_file_direct(
                    "/home/dev/.claude.json", content
                )
                if success:
                    self._log(
                        f"Copied .claude.json to container ({len(content)} bytes)"
                    )
                else:
                    self._log(f"Failed to copy .claude.json: {msg}")
            except Exception as e:
                self._log(f"Error copying .claude.json: {e}")

        # Copy .claudeignore
        claudeignore_path = self._claude_config_files.get("claudeignore")
        if claudeignore_path and os.path.exists(claudeignore_path):
            try:
                with open(claudeignore_path, "rb") as f:
                    content = f.read()
                success, msg = self.docker_manager.write_file_direct(
                    "/workspace/.claudeignore", content
                )
                if success:
                    self._log(
                        f"Copied .claudeignore to container ({len(content)} bytes)"
                    )
                else:
                    self._log(f"Failed to copy .claudeignore: {msg}")
            except Exception as e:
                self._log(f"Error copying .claudeignore: {e}")

        # Copy .credentials.json (OAuth subscription credentials) if available
        credentials_path = self._claude_config_files.get("credentials")
        if credentials_path and os.path.exists(credentials_path):
            try:
                with open(credentials_path, "rb") as f:
                    content = f.read()
                success, msg = self.docker_manager.write_file_direct(
                    "/home/dev/.claude/.credentials.json", content
                )
                if success:
                    self._log(
                        f"Copied .credentials.json to container ({len(content)} bytes)"
                    )
                else:
                    self._log(f"Failed to copy .credentials.json: {msg}")
            except Exception as e:
                self._log(f"Error copying .credentials.json: {e}")
        else:
            self._log("No .credentials.json found; skipping (API key auth will be used)")

        # Ensure all files are owned by the dev user
        try:
            self._log("Adjusting ownership of Claude files to dev:dev")
            chown_cmds = [
                "chown -R dev:dev /home/dev/.claude || true",
                "chown dev:dev /home/dev/.claude.json || true",
                "chown dev:dev /workspace/.claudeignore || true",
            ]
            for cmd in chown_cmds:
                res = self.docker_manager.execute_command(cmd, timeout=30, user="root")
                self._log(f"Chown '{cmd}' exit_code={res.exit_code}")
        except Exception as e:
            self._log(f"Failed to chown claude files: {e}")

        # Copy local skills directory to ~/.claude/skills in the container
        # (controlled by self.skill_mode: "all" | "none" | "one")
        try:
            mode = getattr(self, "skill_mode", "all")
            if mode == "none":
                self._log(
                    "Skipping copying local skills to container (skill_mode=none)"
                )
            else:
                local_skills_root = os.path.join(os.getcwd(), "skills")
                if mode == "one":
                    local_skills_dir = os.path.join(local_skills_root, self.skill_id)
                    # Reserved-name skills (e.g. security-review collides with the
                    # built-in /security-review) are installed under an alias so the
                    # slash invocation resolves to OUR skill. Host side unchanged.
                    container_skill_name = get_container_skill_name(self.skill_id)
                    if container_skill_name != self.skill_id:
                        self._log(
                            f"Reserved skill name: installing skills/{self.skill_id} "
                            f"as {container_skill_name} in the container"
                        )
                    target_dir_suffix = f"/{container_skill_name}"
                    if not os.path.isdir(local_skills_dir):
                        self._log(
                            f"skill_mode=one but skills/{self.skill_id}/ not found; "
                            f"nothing to copy"
                        )
                        local_skills_dir = None
                else:  # mode == "all"
                    local_skills_dir = local_skills_root
                    target_dir_suffix = ""

                if local_skills_dir and os.path.exists(local_skills_dir) and os.path.isdir(local_skills_dir):
                    self._log(
                        f"Copying local skills (mode={mode}) from {local_skills_dir} "
                        f"to /home/dev/.claude/skills{target_dir_suffix}"
                    )

                    # assume /home/dev/.claude already exists in the container

                    # Count copied files
                    copied_count = 0
                    failed_count = 0

                    # Recursively copy each file (preserving directory structure).
                    # For mode="one" we walk skills/<skill_id>/, so files land under
                    # /home/dev/.claude/skills/<skill_id>/... (target_dir_suffix = "/<skill_id>")
                    base_target = f"/home/dev/.claude/skills{target_dir_suffix}"
                    for root, dirs, files in os.walk(local_skills_dir):
                        rel = os.path.relpath(root, local_skills_dir)
                        if rel == ".":
                            dest_dir = base_target
                        else:
                            # Convert path separator to POSIX style (cross-platform)
                            rel_posix = rel.replace(os.sep, "/")
                            dest_dir = f"{base_target}/{rel_posix}"

                        # Create directory (silent)
                        self.docker_manager.execute_command(
                            f"mkdir -p {dest_dir}", user="root"
                        )

                        for fname in files:
                            local_file = os.path.join(root, fname)
                            container_path = f"{dest_dir}/{fname}"
                            try:
                                # Aliased skill: Claude Code registers the skill by
                                # the SKILL.md frontmatter `name:` — rewrite it to
                                # the alias so /skill-<id> resolves. Copy via a temp
                                # file; the host SKILL.md is never touched.
                                if (
                                    mode == "one"
                                    and fname == "SKILL.md"
                                    and rel == "."
                                    and target_dir_suffix == f"/{get_container_skill_name(self.skill_id)}"
                                    and get_container_skill_name(self.skill_id) != self.skill_id
                                ):
                                    import tempfile
                                    alias = get_container_skill_name(self.skill_id)
                                    text = open(local_file, encoding="utf-8").read()
                                    text = re.sub(
                                        rf"^name:\s*{re.escape(self.skill_id)}\s*$",
                                        f"name: {alias}",
                                        text,
                                        count=1,
                                        flags=re.M,
                                    )
                                    with tempfile.NamedTemporaryFile(
                                        "w", suffix=".md", delete=False, encoding="utf-8"
                                    ) as tf:
                                        tf.write(text)
                                        tmp_path = tf.name
                                    try:
                                        self.docker_manager.copy_to_container(
                                            tmp_path, container_path
                                        )
                                    finally:
                                        os.unlink(tmp_path)
                                else:
                                    self.docker_manager.copy_to_container(
                                        local_file, container_path
                                    )
                                copied_count += 1
                            except Exception as e:
                                failed_count += 1
                                self._log(
                                    f"Failed to copy skill file {local_file}: {e}"
                                )

                    # Print copy summary
                    self._log(
                        f"Skills copy completed: {copied_count} files copied, {failed_count} failed"
                    )

                    # Set ownership to dev:dev
                    chown_skills = self.docker_manager.execute_command(
                        "chown -R dev:dev /home/dev/.claude/skills || true",
                        timeout=30,
                        user="root",
                    )
                    self._log(f"Chown skills exit_code={chown_skills.exit_code}")
                else:
                    self._log(
                        f"No local skills directory at {local_skills_dir}; skipping skills copy"
                    )
        except Exception as e:
            self._log(f"Error while copying skills to container: {e}")

    async def _copy_codex_config_to_container(self):
        """
        Provision the Codex CLI's config into the container (AGENT=codex):
          - /home/dev/.codex/auth.json   (host ~/.codex/auth.json — ChatGPT subscription OAuth)
          - /home/dev/.codex/config.toml (chatgpt login method + trust the workdir)
          - /home/dev/.codex/skills/...  (native SKILL.md tree, per skill_mode none|one|all)
        Copied (not mounted) so container-side token refresh never touches the host file.
        """
        self._log("Copying Codex config files to container...")
        self.docker_manager.execute_command("mkdir -p /home/dev/.codex", timeout=30, user="root")

        # Two provider modes:
        #   default    — ChatGPT subscription OAuth (host ~/.codex/auth.json + forced chatgpt login)
        #   selfhosted — CODEX_BASE_URL set: OpenAI-compatible endpoint (e.g. SGLang Kimi).
        #                No auth.json; codex authenticates via env_key. Output cap defaults to
        #                32000 to match the claude+kimi CCR run; context window must be declared
        #                explicitly or codex can't trigger auto-compaction for unknown model slugs.
        base_url = os.environ.get("CODEX_BASE_URL")
        if not base_url:
            # auth.json (subscription OAuth) — required.
            host_auth = os.path.expanduser("~/.codex/auth.json")
            if os.path.exists(host_auth):
                with open(host_auth, "rb") as f:
                    content = f.read()
                ok, msg = self.docker_manager.write_file_direct("/home/dev/.codex/auth.json", content)
                self._log(f"Copied codex auth.json ({len(content)} bytes): ok={ok} {('' if ok else msg)}")
            else:
                self._log(f"WARNING: {host_auth} not found — codex will be unauthenticated (run `codex login`)")

        # Minimal config.toml: provider setup + trust the workspace so exec never prompts.
        # Dedupe project paths — repo_dir is often unset here (config copied before clone) so it
        # collapses to /workspace, and a duplicate [projects."..."] key makes codex reject the file.
        trust_dir = self.repo_dir or self.config.get("global", {}).get("workspace_dir", "/workspace")
        trust_paths = list(dict.fromkeys([p for p in (trust_dir, "/workspace") if p]))
        if base_url:
            model_slug = os.environ.get("CODEX_MODEL") or get_model_name()
            max_out = os.environ.get("CODEX_MAX_OUTPUT_TOKENS", "32000")
            ctx_win = os.environ.get("CODEX_CONTEXT_WINDOW", "262144")
            config_toml = (
                f'model = "{model_slug}"\n'
                'model_provider = "selfhosted"\n'
                f'model_max_output_tokens = {max_out}\n'
                f'model_context_window = {ctx_win}\n'
                '[model_providers.selfhosted]\n'
                'name = "selfhosted"\n'
                f'base_url = "{base_url}"\n'
                'env_key = "SELFHOSTED_API_KEY"\n'
                'wire_api = "responses"\n'
            )
            self._log(f"codex selfhosted provider: {base_url} model={model_slug} "
                      f"max_out={max_out} ctx={ctx_win}")
        else:
            config_toml = 'forced_login_method = "chatgpt"\n'
        for p in trust_paths:
            config_toml += f'[projects."{p}"]\ntrust_level = "trusted"\n'
        ok, msg = self.docker_manager.write_file_direct(
            "/home/dev/.codex/config.toml", config_toml.encode("utf-8"))
        self._log(f"Wrote codex config.toml (trust {trust_dir}): ok={ok} {('' if ok else msg)}")

        # Skills → /home/dev/.codex/skills, same none|one|all semantics as the claude path.
        try:
            mode = getattr(self, "skill_mode", "all")
            if mode == "none":
                self._log("Skipping codex skills copy (skill_mode=none)")
            else:
                local_skills_root = os.path.join(os.getcwd(), "skills")
                if mode == "one":
                    local_skills_dir = os.path.join(local_skills_root, self.skill_id)
                    base_target = f"/home/dev/.codex/skills/{self.skill_id}"
                    if not os.path.isdir(local_skills_dir):
                        self._log(f"skill_mode=one but skills/{self.skill_id}/ not found; nothing to copy")
                        local_skills_dir = None
                else:  # all
                    local_skills_dir = local_skills_root
                    base_target = "/home/dev/.codex/skills"

                if local_skills_dir and os.path.isdir(local_skills_dir):
                    self._log(f"Copying codex skills (mode={mode}) -> {base_target}")
                    copied = failed = 0
                    for root, _dirs, files in os.walk(local_skills_dir):
                        rel = os.path.relpath(root, local_skills_dir)
                        dest_dir = base_target if rel == "." else f"{base_target}/{rel.replace(os.sep, '/')}"
                        self.docker_manager.execute_command(f"mkdir -p {dest_dir}", user="root")
                        for fname in files:
                            try:
                                self.docker_manager.copy_to_container(
                                    os.path.join(root, fname), f"{dest_dir}/{fname}")
                                copied += 1
                            except Exception as e:
                                failed += 1
                                self._log(f"Failed to copy codex skill file {fname}: {e}")
                    self._log(f"Codex skills copy: {copied} copied, {failed} failed")
        except Exception as e:
            self._log(f"Error while copying codex skills: {e}")

        # Own everything as dev:dev; codex requires auth.json be 0600.
        for cmd in [
            "chown -R dev:dev /home/dev/.codex || true",
            "chmod 600 /home/dev/.codex/auth.json || true",
        ]:
            res = self.docker_manager.execute_command(cmd, timeout=30, user="root")
            self._log(f"codex '{cmd}' exit={res.exit_code}")

    def _build_claude_settings_content(self) -> Optional[bytes]:
        """Build the Claude settings content to write into the container."""
        settings_path = self._claude_config_files.get("settings")
        settings_user_path = self._claude_config_files.get("settings_user")

        if not settings_path or not os.path.exists(settings_path):
            return None

        with open(settings_path, "r", encoding="utf-8") as f:
            settings_data = json.load(f)

        if settings_user_path and os.path.exists(settings_user_path):
            with open(settings_user_path, "r", encoding="utf-8") as f:
                user_settings = json.load(f)
            settings_data = self._deep_merge_dicts(settings_data, user_settings)

        env_config = settings_data.get("env", {})
        resolved_env = {}

        for key, value in env_config.items():
            resolved_value = self._resolve_claude_env_value(key, value)
            if resolved_value not in (None, ""):
                resolved_env[key] = resolved_value

        settings_data["env"] = resolved_env

        return json.dumps(settings_data, indent=2, ensure_ascii=False).encode("utf-8")

    def _resolve_claude_env_value(self, key: str, value: Any) -> Any:
        """Prefer host environment variables; fall back to resolving ${VAR} placeholders."""
        if key in os.environ and os.environ[key]:
            return os.environ[key]

        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            env_key = value[2:-1].strip()
            return os.environ.get(env_key, "")

        return value

    def _deep_merge_dicts(
        self, base: Dict[str, Any], override: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Recursively merge dictionaries; override file values take precedence."""
        merged = dict(base)
        for key, value in override.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = self._deep_merge_dicts(merged[key], value)
            else:
                merged[key] = value
        return merged

    async def _clone_repository(
        self, repo_url: str, commit: str, sparse_checkout: Optional[List[str]] = None
    ):
        """Clone a repository into the container."""
        self._log(f"Cloning repository: {repo_url}")

        # Check and install Git
        self._log("Checking/installing Git")
        exit_code, _ = self.docker_manager.container.exec_run("which git")
        self._log(f"which git exit code: {exit_code}")
        if exit_code != 0:
            self._log("Installing Git (may take 1-2 minutes)")
            # Update package list (quiet mode)
            self.docker_manager.container.exec_run("apt-get update -qq", user="root")
            # Install git (ignore return code; apt may produce warnings)
            self.docker_manager.container.exec_run(
                "apt-get install -y -qq git 2>/dev/null || apt-get install -y git",
                user="root",
            )
            # Wait for installation to complete
            import time

            time.sleep(2)

        # Final verification
        exit_code, output = self.docker_manager.container.exec_run("git --version")
        self._log(f"git --version exit code: {exit_code}")
        if exit_code == 0:
            git_version = output.decode().strip() if output else "unknown"
            self._log(f"Git is available: {git_version}")
        else:
            # Try again with --fix-missing to handle network issues
            self._log("Retrying Git installation with --fix-missing")
            self.docker_manager.container.exec_run("apt-get update", user="root")
            self.docker_manager.container.exec_run(
                "apt-get install -y --fix-missing git", user="root"
            )
            exit_code, output = self.docker_manager.container.exec_run("git --version")
            self._log(f"git --version (retry) exit code: {exit_code}")
            if exit_code == 0:
                git_version = output.decode().strip() if output else "unknown"
                self._log(f"Git is available: {git_version}")
            else:
                error_msg = output.decode() if output else "Unknown error"
                self._log(f"Git installation failed: {error_msg[:200]}")
                raise RuntimeError(f"Failed to install git: {error_msg}")

        # Extract repo name from URL
        repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
        base_workspace = self.config.get("global", {}).get(
            "workspace_dir", "/workspace"
        )
        workspace_dir = f"{base_workspace}/{repo_name}"

        # Save actual repo path for use in later stages
        self.repo_dir = workspace_dir
        self._log(f"Repository will be cloned to: {workspace_dir}")

        # Initialize git repository. Clean the target dir first so a reused/leftover
        # rootfs (orphaned enroot rootfs on shared WeKa DATA_PATH) with a pre-existing
        # clone doesn't make `git remote add origin` fail ("already exists").
        init_commands = [
            f"rm -rf {workspace_dir}",
            f"git init {workspace_dir}",
            f"cd {workspace_dir} && git remote add origin {repo_url}",
        ]

        # Sparse checkout configuration
        if sparse_checkout:
            init_commands.extend(
                [
                    f"cd {workspace_dir} && git config core.sparseCheckout true",
                ]
            )
            # Write sparse checkout configuration
            sparse_paths = "\\n".join(sparse_checkout)
            init_commands.append(
                f"echo -e '{sparse_paths}' > {workspace_dir}/.git/info/sparse-checkout"
            )

        for cmd in init_commands:
            bash_cmd = f"bash -c '{cmd}'"
            result = self.docker_manager.execute_command(bash_cmd)
            if result.exit_code != 0:
                self._log(f"Command failed: {cmd}")
                self._log(f"Error: {result.stderr or result.stdout}")
                raise RuntimeError(
                    f"Failed to initialize repository: {result.stderr or result.stdout}"
                )

        # Pull code (use HEAD if commit is None)
        # Use --filter=blob:none for a blobless clone: fetch commits+tree only, blobs on demand
        # More suitable for large repos than --depth 1; avoids timeouts from pack computation
        ref = commit if commit else "HEAD"
        fetch_cmd = (
            f"cd {workspace_dir} && git fetch --depth 1 --filter=blob:none origin {ref}"
        )
        checkout_cmd = f"cd {workspace_dir} && git checkout FETCH_HEAD"

        # git fetch special handling for large repos: retries + extended timeout
        git_fetch_timeout = 1200  # 20 minutes, for large repositories
        max_retries = 3
        last_error = ""
        for attempt in range(1, max_retries + 1):
            self._log(
                f"git fetch attempt {attempt}/{max_retries} (timeout={git_fetch_timeout}s)"
            )
            result = self.docker_manager.execute_command(
                f"bash -c '{fetch_cmd}'",
                timeout=git_fetch_timeout,
            )
            if result.exit_code == 0:
                break
            last_error = result.stderr or result.stdout
            self._log(f"git fetch attempt {attempt} failed: {last_error[:300]}")
            if result.timed_out:
                self._log("Fetch timed out, retrying...")
            if attempt < max_retries:
                import time as _time

                _time.sleep(5 * attempt)  # Exponential backoff: 5s, 10s
        else:
            raise RuntimeError(
                f"git fetch failed after {max_retries} attempts: {last_error}"
            )

        # checkout
        result = self.docker_manager.execute_command(f"bash -c '{checkout_cmd}'")
        if result.exit_code != 0:
            self._log(f"git checkout failed: {result.stderr or result.stdout}")
            raise RuntimeError(
                f"Failed to checkout repository: {result.stderr or result.stdout}"
            )

        # Remove any residual .claude directories in the workspace repo
        cleanup_cmd = f"find {workspace_dir} -type d -name '.claude' -prune -exec rm -rf {{}} + || true"
        cleanup_bash = f"bash -c '{cleanup_cmd}'"
        cleanup_res = self.docker_manager.execute_command(cleanup_bash)
        stdout = getattr(cleanup_res, "stdout", None) or getattr(
            cleanup_res, "output", None
        )
        self._log(
            f"Removed repo .claude directories under {workspace_dir}: exit_code={cleanup_res.exit_code} stdout={stdout}"
        )

        self._log("Repository cloned successfully")

    async def _stage_pre_process(self):
        """Pre-processing stage (code degradation etc.)"""
        log_section("Pre-Process")
        self._transition_to(LifecycleStage.PRE_PROCESS)

        pre_process = self.skill_config.get("pre_process")

        if not pre_process:
            self._log("No pre-processing required")
            return

        mode = pre_process.get("mode", "degradation")

        if mode == "degradation":
            await self._run_degradation(pre_process)
        else:
            self._log(f"Pre-process mode: {mode} (no action needed)")

    async def _run_degradation(self, pre_process_config: Dict[str, Any]):
        """Run code degradation."""
        from ..initializer import DegradationHandler

        self._log("Running code degradation...")

        handler = DegradationHandler(self.docker_manager, self.config)
        await handler.run(pre_process_config)

        self._log("Code degradation completed")

    async def _stage_sanity_check(self):
        """Sanity check stage."""
        log_section("Sanity Check")
        self._transition_to(LifecycleStage.SANITY_CHECK)

        # Check whether code passes the base build (to rule out environment issues)
        evaluation = self.skill_config.get("evaluation", [])

        for eval_item in evaluation:
            if (
                eval_item.get("level") == "L1"
                and eval_item.get("method") == "build_check"
            ):
                # After degradation the build may fail — this is expected.
                # We only check that the environment is functional.
                self._log("Checking build environment...")
                params = eval_item.get("params", {})
                build_cmd = params.get("build_command", "python --version")
                # Use the actual repository directory
                repo_dir = self.repo_dir or "/workspace"

                result = self.docker_manager.execute_command(
                    f"cd {repo_dir} && {build_cmd}"
                )
                self._log(f"Build check result: exit_code={result.exit_code}")

                # Do not raise here because the degraded code may not compile
                break

        self._log("Sanity check completed")

    async def _stage_interaction_loop(self):
        """
        Agent interaction loop stage (Claude Code CLI mode).

        Workflow:
        1. Write task file into the container
        2. Invoke the claude CLI to operate autonomously inside the container
        3. Wait for completion
        """
        log_section("Interaction Loop (Claude Code CLI)")
        self._transition_to(LifecycleStage.INTERACTION)

        # Decide whether to skip the interaction stage based on config
        if not getattr(self, "use_agent", True):
            self._log("Skipping Interaction Loop because use_agent is False")
            self.iterations = 0
            return

        from ..proxy import get_proxy_class

        # Select the harness proxy by AGENT (claude -> ClaudeCodeProxy [default/byte-identical];
        # codex -> CodexCliProxy). Both honour the same duck-typed contract this stage consumes.
        ProxyClass = get_proxy_class()

        # Initialize the harness proxy with the corrected working directory
        proxy_config = self.config.copy()
        proxy_config["skill_id"] = self.skill_id
        proxy_config["use_skill"] = self.use_skill
        proxy_config["skill_mode"] = self.skill_mode
        proxy_config["skill_mode_suffix"] = self.skill_mode_suffix
        proxy_config["use_agent"] = self.use_agent
        proxy_config["batch"] = self.batch
        proxy_config.setdefault("metadata", {})["skill_id"] = self.skill_id
        if self.repo_dir:
            # Use the actual repository directory rather than /workspace
            if "global" not in proxy_config:
                proxy_config["global"] = {}
            proxy_config["global"]["workspace_dir"] = self.repo_dir
            self._log(f"Using repo directory for Claude Code: {self.repo_dir}")

        claude_proxy = ProxyClass(
            docker_manager=self.docker_manager, config=proxy_config
        )

        self._log(f"Starting {get_agent_name()} interaction ({ProxyClass.__name__})...")

        # Execute task
        result = await claude_proxy.execute_task(self._task_content)

        self.iterations = 1  # Claude Code CLI executes in a single pass

        # Rate-limit guard: a Max-rate-limited run did nothing; remove the
        # container so the eval step cannot score a bogus 0, and fail the run so
        # it is re-run later (when quota is available) rather than silently
        # contaminating the baseline (cf. the 2026-04 rate-limit zeros).
        if getattr(result, "rate_limited", False):
            self._log("RATE LIMITED — removing container and failing this run for re-run")
            try:
                self.docker_manager.remove_container()
            except Exception as e:
                self._log(f"(rate-limit) container removal note: {e}")
            raise RuntimeError("Claude Code run was RATE LIMITED (Max quota); must re-run")

        # Infra-clean gate: a 0-turn / gateway-dead run did no work. Remove the
        # container so eval can NEVER score the initial repo as a fake 0, and
        # fail loudly for re-run. (2026-07-26 audit: 63 'Unknown command' cells
        # were silently scored ~0 and flipped the claude one-vs-none verdict.)
        _invalid = getattr(result, "invalid_reason", None)
        if _invalid:
            self._log(f"INFRA ERROR ({_invalid}) — removing container and failing this run for re-run")
            try:
                self.docker_manager.remove_container()
            except Exception as e:
                self._log(f"(infra-error) container removal note: {e}")
            raise RuntimeError(f"INFRA ERROR — run invalid, must re-run: {_invalid}")

        if result.success:
            self._log(
                f"Claude Code completed successfully in {result.duration_sec:.2f}s"
            )
            self._log(f"Output length: {len(result.output)} chars")
        else:
            self._log(f"Claude Code failed with exit code: {result.exit_code}")
            if result.stderr:
                self._log(f"Stderr: {result.stderr[:500]}")
            # Raise exception when Claude fails to prevent marking as success
            raise RuntimeError(
                f"Claude Code execution failed with exit code {result.exit_code}"
            )

        # Output result summary
        self._log(
            f"Claude Code result: success={result.success}, duration={result.duration_sec:.2f}s"
        )

    async def _stage_cleanup(self):
        """Cleanup stage."""
        log_section("Cleanup")
        self._transition_to(LifecycleStage.CLEANUP)

        try:
            if self.clean_container:
                # Full cleanup: stop and remove container
                self.docker_manager.cleanup()
                self._log("Cleanup completed (container removed)")
            else:
                # Stop container only, preserve it for a later eval.py run
                container_name = generate_container_name(
                    self.skill_id, self.skill_mode_suffix, self.use_agent,
                    model_name=get_model_name(), batch=self.batch, agent=get_agent_name()
                )
                self.docker_manager.stop_container()
                self._log(f"Container stopped but preserved: {container_name}")
                self._log("Run eval.py with matching parameters to evaluate")
        except Exception as e:
            self._log(f"Cleanup error (non-fatal): {e}")

    def save_report(self, result: BenchmarkResult, output_dir: str = None):
        """
        Save the benchmark run report.

        Args:
            result: Benchmark run result
            output_dir: Output directory
        """
        if output_dir is None:
            output_dir = self.config.get("global", {}).get("reports_dir", "./outputs/reports")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Encode skill_mode/use_agent state in the report filename
        # (skill_mode_suffix: "true" | "false" | "one")
        use_skill_flag = getattr(self, "skill_mode_suffix", "true")
        use_agent_flag = getattr(self, "use_agent", True)

        report_filename = generate_report_filename(
            prefix="report",
            skill=self.skill_id,
            use_agent=use_agent_flag,
            use_skill=use_skill_flag,
            timestamp=timestamp,
            ext=".json",
        )
        report_file = output_path / report_filename

        with open(report_file, "w", encoding="utf-8") as f:
            f.write(result.to_json())

        logger.info(f"Report saved to: {report_file}")
        return report_file
