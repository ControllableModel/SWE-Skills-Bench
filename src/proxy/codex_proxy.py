"""
Codex CLI proxy.

Invokes the OpenAI Codex CLI (`codex exec`) directly inside an enroot container to execute a
task, mirroring ClaudeCodeProxy's contract so the lifecycle consumes both identically. The
returned object is a ClaudeCodeResult (same duck-typed fields the lifecycle reads:
success / output / stderr / exit_code / duration_sec / rate_limited).

Auth: the container's /home/dev/.codex/auth.json (ChatGPT subscription OAuth) is provisioned by
lifecycle._copy_codex_config_to_container BEFORE this runs. Model: MODEL_NAME env (== the codex
`-m` slug and the report/dir model identity), overridable with CODEX_MODEL.
"""

import os
import time
from datetime import datetime
from typing import Dict, Any

from ..orchestrator.docker_manager import DockerManager
from ..orchestrator.logger import get_logger
from ..utils import generate_report_filename, get_model_name, get_agent_name
from .claude_code_proxy import ClaudeCodeResult

logger = get_logger(__name__)


class CodexCliProxy:
    """
    Codex CLI interaction proxy (headless `codex exec`).

    Usage mirrors ClaudeCodeProxy:
    1. Write the task file into the container
    2. Invoke `codex exec` to let it operate autonomously inside the container
    3. Wait for completion, copy the transcript log to the host, return a ClaudeCodeResult
    """

    def __init__(self, docker_manager: DockerManager, config: Dict[str, Any]):
        self.docker_manager = docker_manager
        self.config = config

        limits = config.get("limits", {})
        self.timeout_per_command = limits.get("timeout_per_command", 300)
        # Same env override as the claude proxy — per-skill limits live under the skill's
        # environment, not config["limits"], so allow SWE_TOTAL_TIMEOUT_SEC to lift the cap.
        self.total_timeout_sec = int(
            os.environ.get("SWE_TOTAL_TIMEOUT_SEC") or limits.get("total_timeout_sec", 1800)
        )

        self.workspace_dir = config.get("global", {}).get("workspace_dir", "/workspace")
        self.runtime_root_dir = "/workspace"

        # Host-side trajectory dir: outputs/codex_process/{agent}/{model}/{batch}/codex_output
        _agent_name = get_agent_name()
        _model_name = get_model_name()
        _batch = config.get("batch", "")
        parts = [os.getcwd(), "outputs", "codex_process", _agent_name, _model_name]
        if _batch:
            parts.append(_batch)
        self.process_base_dir = os.path.join(*parts)
        self.output_log_dir = os.path.join(self.process_base_dir, "codex_output")
        # Structured per-event session rollouts (codex's analog of claude's thinking JSONL):
        # ~/.codex/sessions/<date>/rollout-*.jsonl inside the container — reasoning items,
        # function_call events, per-response token_count. The container is destroyed after
        # eval, so these MUST be copied out or they are lost.
        self.session_jsonl_dir = os.path.join(self.process_base_dir, "codex_sessions")
        os.makedirs(self.output_log_dir, exist_ok=True)
        os.makedirs(self.session_jsonl_dir, exist_ok=True)
        self.container_output_dir = f"{self.runtime_root_dir}/codex_output"
        self.container_sessions_dir = "/home/dev/.codex/sessions"

        logger.info("Codex CLI Proxy initialized")
        logger.info(f"  Output logs -> {self.output_log_dir}")

    async def execute_task(self, task_content: str) -> ClaudeCodeResult:
        start_time = time.time()

        # Pre-check: codex present in the image.
        try:
            check = self.docker_manager.execute_command("which codex", timeout=10)
            if check.exit_code != 0:
                err = ("codex CLI not found in container PATH. Bake it into the image "
                       "(scripts/bake_agents_image.sh -> *-codex.sqsh).")
                logger.error(err)
                return ClaudeCodeResult(
                    success=False, output="", stderr=err, exit_code=127,
                    duration_sec=time.time() - start_time,
                )
        except Exception:
            logger.debug("'which codex' check failed; continuing to run codex anyway")

        # Same mandatory execution instructions as the claude path — implement directly, no
        # plan-only / clarifying-question responses — so the two harnesses see the same task framing.
        instruction_prefix = (
            "INTERNAL_INSTRUCTION: DO_NOT_ASK_OR_PLAN\n"
            "You MUST directly modify files in the repository under the workspace to implement the task.\n"
            "Do NOT output a design plan or ask clarifying questions.\n"
            "Write/update the necessary files (provide full file paths and contents).\n"
            "Only output a concise summary of files changed and the final status.\n"
            "EndInstruction\n\n"
        )
        if not task_content.startswith("INTERNAL_INSTRUCTION: DO_NOT_ASK_OR_PLAN"):
            task_content = instruction_prefix + task_content

        # skill_mode=one: the single bound skill is provisioned natively under
        # /home/dev/.codex/skills/<id>/ (SKILL.md) by the lifecycle. Codex's native explicit
        # skill-invocation syntax is `$skill-name` (verified: loads SKILL.md + follows it) —
        # the faithful analog of Claude Code's `/skill-id`. Prepend it at position 0 (the
        # skill name equals the skill_id / SKILL.md `name:` field).
        skill_mode = self.config.get("skill_mode") if self.config else None
        skill_id = self.config.get("skill_id") if self.config else None
        if skill_mode == "one" and skill_id and not task_content.startswith(f"${skill_id}"):
            task_content = f"${skill_id}\n\n" + task_content
            logger.info(f"skill_mode=one: prepended ${skill_id} native skill trigger")

        # Step 1: write the task file (parity with claude; codex reads the prompt from argv).
        task_file_path = f"{self.runtime_root_dir}/task.md"
        self._write_task_to_container(task_file_path, task_content)

        # Step 2: build the codex command.
        codex_cmd = self._build_codex_command(task_content)

        print("\n" + "=" * 60)
        print("🤖 Codex CLI starting task execution...")
        print("=" * 60)

        # Prep dirs / ownership (task file + output dir) — codex runs as dev.
        try:
            self.docker_manager.execute_command(
                f"chown -R dev:dev {task_file_path} || true", timeout=30, user="root")
        except Exception:
            pass
        self.docker_manager.execute_command(
            f"mkdir -p {self.container_output_dir}", timeout=30, user="root")
        self.docker_manager.execute_command(
            f"chown -R dev:dev {self.container_output_dir} || true", timeout=30, user="root")

        # Step 3: run codex exec as dev.
        result = self.docker_manager.execute_command(
            codex_cmd, timeout=self.total_timeout_sec, user="dev")

        duration = time.time() - start_time
        status_icon = "✅" if result.exit_code == 0 else "❌"
        print(f"\n{status_icon} Codex execution finished (elapsed: {duration:.1f}s, exit code: {result.exit_code})")
        print("=" * 60 + "\n")

        # Step 4: copy the transcript log to the host (best-effort trajectory capture).
        self._copy_output_log_to_host()

        # Step 5: copy the structured session rollout JSONLs (per-event trajectory + tokens).
        self._copy_session_jsonl_to_host()

        return ClaudeCodeResult(
            success=result.exit_code == 0,
            output=result.stdout or "",
            stderr=result.stderr or "",
            exit_code=result.exit_code,
            duration_sec=duration,
            rate_limited=False,  # codex→subscription: no Max-style rate-limit contamination path
        )

    def _write_task_to_container(self, task_file_path: str, task_content: str):
        escaped_content = task_content.replace("'", "'\\''")
        cmd = f"echo '{escaped_content}' > {task_file_path}"
        result = self.docker_manager.execute_command(cmd, timeout=30)
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to write task file: {result.stderr}")
        logger.info(f"Task file written to: {task_file_path}")

    def _build_codex_command(self, task_content: str) -> str:
        """
        Build the `codex exec` command. Headless, non-interactive, full-auto:
          --dangerously-bypass-approvals-and-sandbox  (exec never prompts; we sandbox via enroot)
          --skip-git-repo-check                        (workspace may not be a git repo yet)
        stdin from /dev/null and output redirected to a per-run log (parity with the claude proxy).
        Model slug: CODEX_MODEL override, else MODEL_NAME/get_model_name().
        """
        escaped = task_content.replace("'", "'\\''")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        skill_id = None
        try:
            skill_id = self.config.get("skill_id") or self.config.get("metadata", {}).get("skill_id")
        except Exception:
            pass
        use_skill_flag = self.config.get("skill_mode_suffix") or self.config.get("use_skill")
        log_filename = generate_report_filename(
            prefix="codex_log", skill=skill_id,
            use_agent=self.config.get("use_agent"), use_skill=use_skill_flag,
            timestamp=timestamp, ext=".log",
        )
        log_file = f"{self.container_output_dir}/{log_filename}"
        self._current_log_file = log_file
        self._current_timestamp = timestamp

        model_name = os.environ.get("CODEX_MODEL") or get_model_name()
        model_flag = f"-m {model_name} " if model_name else ""
        # Self-hosted provider (CODEX_BASE_URL set): codex reads the endpoint key from the env
        # var named by config.toml's env_key; inline it since enroot exec doesn't forward host env.
        key_prefix = ""
        if os.environ.get("CODEX_BASE_URL"):
            api_key = os.environ.get("CODEX_API_KEY", "none")
            key_prefix = f"SELFHOSTED_API_KEY='{api_key}' "
        # HOME=/home/dev so codex resolves ~/.codex/auth.json; CODEX_HOME kept in sync for safety.
        cmd = (
            f"cd {self.workspace_dir} && "
            f"HOME=/home/dev CODEX_HOME=/home/dev/.codex {key_prefix}"
            f"codex exec '{escaped}' {model_flag}"
            f"--dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "
            f"< /dev/null > {log_file} 2>&1"
        )
        return cmd

    def _copy_output_log_to_host(self):
        if not getattr(self, "_current_log_file", None):
            return
        try:
            cat_result = self.docker_manager.execute_command(
                f"cat {self._current_log_file}", timeout=60, user="dev")
            if cat_result.exit_code == 0 and cat_result.stdout:
                host_log_path = os.path.join(self.output_log_dir, os.path.basename(self._current_log_file))
                with open(host_log_path, "w", encoding="utf-8") as f:
                    f.write(cat_result.stdout)
                logger.info(f"Codex transcript saved to: {host_log_path}")
            else:
                logger.warning(f"Failed to read codex log from container: {cat_result.stderr}")
        except Exception as e:
            logger.error(f"Failed to copy codex output log: {e}")

    def _copy_session_jsonl_to_host(self):
        """
        Copy codex's session rollout JSONLs (~/.codex/sessions/**/rollout-*.jsonl) from the
        container to the host codex_sessions dir — the structured analog of the claude
        thinking-JSONL capture. Renamed with the benchmark convention so the cell is
        identifiable; the original rollout basename is kept as a suffix (a cell can have
        several rollouts if codex was retried).
        """
        try:
            list_result = self.docker_manager.execute_command(
                f"find {self.container_sessions_dir} -name 'rollout-*.jsonl' -type f 2>/dev/null || true",
                timeout=30, user="dev",
            )
            files = [f.strip() for f in (list_result.stdout or "").strip().split("\n") if f.strip()]
            if not files:
                logger.warning(f"No codex session rollouts found under {self.container_sessions_dir}")
                return
            skill_id = None
            try:
                skill_id = self.config.get("skill_id") or self.config.get("metadata", {}).get("skill_id")
            except Exception:
                pass
            use_skill_flag = self.config.get("skill_mode_suffix") or self.config.get("use_skill")
            timestamp = getattr(self, "_current_timestamp", None) or datetime.now().strftime("%Y%m%d_%H%M%S")
            copied = 0
            for path in files:
                cat_result = self.docker_manager.execute_command(f"cat '{path}'", timeout=120, user="dev")
                if cat_result.exit_code != 0 or not cat_result.stdout:
                    logger.warning(f"Failed to read codex rollout {path}: {cat_result.stderr}")
                    continue
                base = generate_report_filename(
                    prefix="codex_session", skill=skill_id,
                    use_agent=self.config.get("use_agent"), use_skill=use_skill_flag,
                    timestamp=timestamp, ext="",
                )
                host_path = os.path.join(self.session_jsonl_dir, f"{base}_{os.path.basename(path)}")
                with open(host_path, "w", encoding="utf-8") as f:
                    f.write(cat_result.stdout)
                copied += 1
            logger.info(f"Codex session rollouts saved: {copied}/{len(files)} -> {self.session_jsonl_dir}")
        except Exception as e:
            logger.error(f"Failed to copy codex session rollouts: {e}")

    def get_stats(self) -> Dict[str, Any]:
        return {
            "workspace_dir": self.workspace_dir,
            "timeout_per_command": self.timeout_per_command,
            "total_timeout_sec": self.total_timeout_sec,
        }
