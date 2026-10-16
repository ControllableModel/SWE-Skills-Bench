#!/usr/bin/env python3
"""
Batch script to run all skills across all configured batches.

Iterates over global.batches in the config file, writes a temporary config
per batch (with active_batch overridden), and invokes main.py for each skill.
Progress logs and resume state are stored per model/batch under reports/.

Usage:
    python run_all_skills.py                          # run all skills in all batches
    python run_all_skills.py --skip skill1,skill2     # skip specified skills
    python run_all_skills.py --only skill1,skill2     # run only specified skills
    python run_all_skills.py --resume                 # resume from last interruption (per batch)
    python run_all_skills.py --dry-run                # preview commands to run
    python run_all_skills.py --config path/to/cfg     # use a custom config file
    python run_all_skills.py --no-use-skill           # disable skill injection
"""

import argparse
import subprocess
import sys
import os
import re
import shutil
import threading
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
from typing import List, Set, Optional

from dotenv import load_dotenv

load_dotenv()


def _get_model_name() -> str:
    """Sanitized model name: MODEL_NAME env preferred, else ANTHROPIC_DEFAULT_SONNET_MODEL.
    Must match src.utils.get_model_name() so report globs find harness-written reports."""
    raw = os.environ.get("MODEL_NAME") or os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL") or "unknown-model"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", raw) or "unknown-model"


def _get_agent_name() -> str:
    """Sanitized agent name from AGENT env (default 'claude'). Matches src.utils.get_agent_name()."""
    raw = os.environ.get("AGENT") or "claude"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", raw) or "claude"


class SkillRunner:
    """Batch skill executor"""

    def __init__(self, config_path: str = "config/benchmark_config.yaml"):
        self.config_path = Path(config_path)
        self.model_name = _get_model_name()
        self.agent_name = _get_agent_name()
        # Per-batch state — initialized by _setup_batch_dirs inside run_all_for_batch
        self.log_file: Optional[Path] = None
        self.completed_file: Optional[Path] = None
        # Used to disambiguate completion-tracking files when the same batch is
        # run in parallel with different --use-skill settings.
        self._condition_suffix: str = ""
        # When True, eval each skill immediately after its interaction (and tear
        # down its container) instead of holding all containers for a later phase.
        self.eval_after: bool = False
        # Skill-level parallelism (1 = legacy sequential). >1 makes sense with
        # backends where containers do not share node-local state (e.g. docker); the enroot backend has node-local state and should stay at 1
        # unless SWE_ISOLATE_ENROOT-style isolation is in place.
        self.n_parallel: int = 1
        self._lock = threading.Lock()
        # Backend from config global.container_backend — decides how
        # _eval_and_cleanup tears containers down (enroot CLI vs eval.py
        # --clean-container, which routes through the backend manager).
        self.container_backend: str = "docker"

    def _load_config(self) -> dict:
        """Load and return the benchmark YAML config."""
        if not self.config_path.exists():
            print(f"Error: config file not found: {self.config_path}")
            sys.exit(1)
        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _get_batches(self, config: dict) -> List[str]:
        """Return the list of batch names from config global.batches."""
        return [str(b) for b in config.get("global", {}).get("batches", [])]

    def _setup_batch_dirs(self, batch_name: str):
        """Create per-batch report/log directory and set log_file/completed_file."""
        reports_dir = Path("outputs/reports") / self.agent_name / self.model_name / batch_name
        reports_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{self._condition_suffix}" if self._condition_suffix else ""
        self.log_file = reports_dir / f"batch_run{suffix}_{ts}.log"
        self.completed_file = reports_dir / f".batch_run_completed{suffix}.txt"

    def _write_temp_config(self, config: dict, batch_name: str) -> Path:
        """Write a temporary YAML config with active_batch overridden to batch_name."""
        import copy

        cfg = copy.deepcopy(config)
        cfg.setdefault("global", {})["active_batch"] = batch_name
        # Unique per-process name: multiple concurrent run_all_skills invocations
        # (e.g. size-1 SLURM array tasks of the same batch) must NOT share this file
        # on the shared FS, or they race-delete each other's config -> "No such file".
        # Corralled under tmp_config/ so they don't litter the repo root.
        tmp_dir = Path("tmp_config")
        tmp_dir.mkdir(exist_ok=True)
        tmp_path = tmp_dir / f"_tmp_config_{batch_name}_{os.getpid()}.yaml"
        with open(tmp_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
        return tmp_path

    def load_skills(self, config: dict) -> List[str]:
        """Return all skill IDs from an already-loaded config dict."""
        return [s["id"] for s in config.get("skills", []) if "id" in s]

    def load_completed_skills(self) -> Set[str]:
        """Load completed skill IDs"""
        if not self.completed_file.exists():
            return set()

        with open(self.completed_file, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())

    def save_completed_skill(self, skill_id: str):
        """Save a completed skill ID (thread-safe for --n-parallel)."""
        with self._lock:
            with open(self.completed_file, "a", encoding="utf-8") as f:
                f.write(f"{skill_id}\n")

    def log(self, message: str):
        """Log a message (thread-safe for --n-parallel)."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        with self._lock:
            print(log_message)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_message + "\n")

    def run_skill(
        self,
        skill_id: str,
        config_file: Path,
        dry_run: bool = False,
        use_skill: Optional[bool] = None,
        skill_mode: Optional[str] = None,
    ) -> bool:
        """
        Run a single skill using the specified batch config file.

        Args:
            skill_id: skill ID
            config_file: path to the per-batch temp config YAML
            dry_run: dry-run mode only
            skill_mode: "all" | "none" | "one". Overrides use_skill when set.

        Returns:
            bool: whether successful
        """
        cmd = [sys.executable, "main.py", "run", "-s", skill_id, "--config", str(config_file)]
        if skill_mode is not None:
            cmd.extend(["--skill-mode", skill_mode])
        elif use_skill is True:
            cmd.append("--use-skill")
        elif use_skill is False:
            cmd.append("--no-use-skill")
        cmd_str = " ".join(cmd)

        self.log(f"{('[DRY-RUN] ' if dry_run else '')}Running: {cmd_str}")

        if dry_run:
            return True

        try:
            if self.n_parallel > 1:
                # Parallel mode: redirect each skill's interaction output to its
                # own file — N interleaved subprocesses on one terminal are useless.
                out_dir = self.log_file.parent / "skill_logs"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{skill_id}{('_' + self._condition_suffix) if self._condition_suffix else ''}.log"
                with open(out_path, "a", encoding="utf-8") as out:
                    result = subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT, text=True)
            else:
                result = subprocess.run(
                    cmd, capture_output=False, text=True  # print directly to terminal
                )

            if result.returncode == 0:
                self.log(f"\u2713 {skill_id} completed")
                return True
            else:
                self.log(f"\u2717 {skill_id} failed (exit code: {result.returncode})")
                return False

        except KeyboardInterrupt:
            self.log("Interrupted by user")
            raise
        except Exception as e:
            self.log(f"\u2717 {skill_id} exception: {e}")
            return False

    def _eval_and_cleanup(
        self,
        skill_id: str,
        batch_name: str,
        config_file: Path,
        use_skill: Optional[bool],
        skill_mode: Optional[str],
    ):
        """Eval this skill RIGHT NOW (container still warm from interaction), then
        tear down its container — so we never hold 50 stopped containers across a
        long Phase-1→Phase-2 gap (the cause of the missing-cell container loss)."""
        eff_mode = skill_mode or ("all" if use_skill else "none")
        suffix = {"all": "true", "none": "false", "one": "one"}[eff_mode]

        # Per-skill short-circuit guard: if interaction died with 0 assistant turns,
        # re-run interaction before evaluating (downsized from the old batch guard).
        max_retry = int(os.environ.get("MAX_RETRY", "2"))
        for attempt in range(1, max_retry + 1):
            chk = subprocess.run(
                [sys.executable, "scripts/detect_short_runs.py", "--batch", batch_name,
                 "--suffix", suffix, "--agent", self.agent_name, "--model", self.model_name,
                 "--skills", skill_id],
                capture_output=True, text=True,
            )
            if skill_id not in chk.stdout.split():
                break
            self.log(f"[eval-after] {skill_id} short-circuited; re-running interaction "
                     f"({attempt}/{max_retry})")
            self.run_skill(skill_id, config_file, False, use_skill, skill_mode)

        cmd = [sys.executable, "eval.py", "-s", skill_id, "--config", str(config_file)]
        if skill_mode is not None:
            cmd.extend(["--skill-mode", skill_mode])
        else:
            cmd.append("--use-skill" if use_skill else "--no-use-skill")
        cmd.append("--use-agent")
        if self.container_backend != "enroot":
            # Backend-agnostic teardown: eval.py --clean-container calls
            # docker_manager.cleanup(). The enroot-CLI removal below covers enroot only.
            cmd.append("--clean-container")
        self.log(f"[eval-after] {' '.join(cmd)}")
        subprocess.run(cmd, check=False)

        name = (f"benchmark_{self.agent_name}_{batch_name}_{skill_id}_use-skill-{suffix}"
                f"_use-agent-true_{self.model_name}")
        if self.container_backend == "enroot":
            # Tear down this skill's container + node-local state.
            # Must match generate_container_name(): benchmark_{agent}_{batch}_{skill}_use-skill-{x}_use-agent-true_{model}
            subprocess.run(["enroot", "remove", "-f", name], capture_output=True, text=True)
            for p in (f"/tmp/enroot-shared/{name}", f"/tmp/enroot-pids/{name}.pid",
                      f"/tmp/enroot-pids/{name}.log"):
                try:
                    shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
                except OSError:
                    pass
        self.log(f"[eval-after] evaluated + removed container {name}")

    def run_all_for_batch(
        self,
        batch_name: str,
        config: dict,
        all_skills: List[str],
        skip_skills: Optional[List[str]] = None,
        only_skills: Optional[List[str]] = None,
        resume: bool = False,
        dry_run: bool = False,
        use_skill: Optional[bool] = None,
        skill_mode: Optional[str] = None,
    ):
        """Run all skills for a single batch."""
        self._setup_batch_dirs(batch_name)
        tmp_config = self._write_temp_config(config, batch_name)

        try:
            skills_to_run = list(all_skills)
            if only_skills:
                skills_to_run = [s for s in skills_to_run if s in only_skills]
                self.log(
                    f"[{batch_name}] Running only {len(skills_to_run)} specified skill(s)"
                )
            if skip_skills:
                skills_to_run = [s for s in skills_to_run if s not in skip_skills]
                self.log(f"[{batch_name}] Skipping {len(skip_skills)} skill(s)")
            if resume:
                completed = self.load_completed_skills()
                skills_to_run = [s for s in skills_to_run if s not in completed]
                self.log(
                    f"[{batch_name}] Resume: {len(completed)} completed, {len(skills_to_run)} remaining"
                )

            if not skills_to_run:
                self.log(f"[{batch_name}] No skills to run")
                return

            total = len(skills_to_run)
            success_count = 0
            failed_count = 0
            failed_skills: List[str] = []

            self.log(f"{'=' * 60}")
            self.log(f"[{batch_name}] Starting batch run of {total} skill(s)")
            self.log(f"Log file: {self.log_file}")
            self.log(f"{'=' * 60}")

            def _run_one(skill_id: str) -> bool:
                """Full per-skill chain: interaction -> mark completed -> eval+teardown."""
                success = self.run_skill(skill_id, tmp_config, dry_run, use_skill, skill_mode)
                if success and not dry_run:
                    self.save_completed_skill(skill_id)
                    if self.eval_after:
                        self._eval_and_cleanup(
                            skill_id, batch_name, tmp_config, use_skill, skill_mode
                        )
                return success

            try:
                if self.n_parallel > 1 and not dry_run:
                    self.log(f"[{batch_name}] Parallel mode: {self.n_parallel} concurrent skills")
                    done = 0
                    with ThreadPoolExecutor(max_workers=self.n_parallel) as pool:
                        futures = {pool.submit(_run_one, s): s for s in skills_to_run}
                        for fut in as_completed(futures):
                            skill_id = futures[fut]
                            done += 1
                            try:
                                ok = fut.result()
                            except Exception as e:
                                self.log(f"✗ {skill_id} worker exception: {e}")
                                ok = False
                            if ok:
                                success_count += 1
                            else:
                                failed_count += 1
                                failed_skills.append(skill_id)
                            self.log(
                                f"Progress: {done}/{total} (succeeded: {success_count}, failed: {failed_count})"
                            )
                else:
                    for idx, skill_id in enumerate(skills_to_run, 1):
                        self.log(f"\n[{idx}/{total}] [{batch_name}] Running: {skill_id}")
                        if _run_one(skill_id):
                            success_count += 1
                        else:
                            failed_count += 1
                            failed_skills.append(skill_id)
                        self.log(
                            f"Progress: {idx}/{total} (succeeded: {success_count}, failed: {failed_count})"
                        )
            except KeyboardInterrupt:
                self.log(f"\n[{batch_name}] Interrupted by user")
                self.log(f"Completed: {success_count}/{total}")
                self.log(f"Use --resume to continue")
                sys.exit(1)

            self.log(f"\n{'=' * 60}")
            self.log(f"[{batch_name}] Batch run complete")
            self.log(
                f"Total: {total}, succeeded: {success_count}, failed: {failed_count}"
            )
            if failed_skills:
                self.log(f"\nFailed skills:")
                for s in failed_skills:
                    self.log(f"  - {s}")
            self.log(f"{'=' * 60}")

            if not dry_run and failed_count == 0 and self.completed_file.exists():
                self.completed_file.unlink()
        finally:
            if tmp_config.exists():
                tmp_config.unlink()

    def run_all(
        self,
        skip_skills: Optional[List[str]] = None,
        only_skills: Optional[List[str]] = None,
        resume: bool = False,
        dry_run: bool = False,
        use_skill: Optional[bool] = None,
        skill_mode: Optional[str] = None,
        eval_after: bool = False,
        n_parallel: int = 1,
    ):
        """Run all skills across all configured batches."""
        self.eval_after = eval_after
        self.n_parallel = max(1, int(n_parallel))
        # Record condition so that parallel --use-skill vs --no-use-skill vs
        # --skill-mode one runs don't stomp on each other's completion files.
        effective_mode = skill_mode
        if effective_mode is None:
            if use_skill is True:
                effective_mode = "all"
            elif use_skill is False:
                effective_mode = "none"
        suffix_map = {"all": "use-skill-true", "none": "use-skill-false", "one": "use-skill-one"}
        self._condition_suffix = suffix_map.get(effective_mode, "")

        config = self._load_config()
        self.container_backend = (config.get("global", {}) or {}).get(
            "container_backend", "docker"
        )
        batches = self._get_batches(config)
        if not batches:
            print("Error: no batches defined in config global.batches")
            sys.exit(1)

        all_skills = self.load_skills(config)
        print(
            f"Loaded {len(all_skills)} skill(s) across {len(batches)} batch(es): {batches}"
        )

        for batch_name in batches:
            self.run_all_for_batch(
                batch_name=batch_name,
                config=config,
                all_skills=all_skills,
                skip_skills=skip_skills,
                only_skills=only_skills,
                resume=resume,
                dry_run=dry_run,
                use_skill=use_skill,
                skill_mode=skill_mode,
            )


def main():
    parser = argparse.ArgumentParser(
        description="Run all skills in batch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_all_skills.py                           # run all skills
  python run_all_skills.py --skip add-uint-support   # skip a skill
  python run_all_skills.py --only skill1,skill2      # run only specified skills
  python run_all_skills.py --resume                  # resume from last interruption
  python run_all_skills.py --dry-run                 # preview commands
        """,
    )

    parser.add_argument("--skip", type=str, help="Skill IDs to skip (comma-separated)")

    parser.add_argument(
        "--only", type=str, help="Run only these skill IDs (comma-separated)"
    )

    parser.add_argument(
        "--resume", action="store_true", help="Resume from last interruption"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry-run mode (show commands, do not execute)",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--use-skill",
        dest="use_skill",
        action="store_true",
        help="Copy local skills/ into the container (maps to main.py --use-skill / skill_mode=all)",
    )
    group.add_argument(
        "--no-use-skill",
        dest="use_skill",
        action="store_false",
        help="Do not copy local skills/ into the container (maps to main.py --no-use-skill / skill_mode=none)",
    )
    parser.set_defaults(use_skill=None)
    parser.add_argument(
        "--skill-mode",
        choices=["all", "none", "one"],
        default=None,
        help="Skill loading mode: 'all'/'none' (legacy) or 'one' (copy only bound skill + "
             "explicit /<skill-id> invoke). Overrides --use-skill/--no-use-skill when set.",
    )

    parser.add_argument(
        "--config",
        type=str,
        default="config/benchmark_config.yaml",
        help="Config file path (default: config/benchmark_config.yaml)",
    )
    parser.add_argument(
        "--eval-after",
        action="store_true",
        help="Eval each skill immediately after its interaction (and remove its "
             "container) instead of holding all containers for a separate eval phase. "
             "Avoids container loss across a long Phase-1->Phase-2 gap.",
    )
    parser.add_argument(
        "--n-parallel",
        type=int,
        default=1,
        help="Concurrent skills per batch (default 1 = sequential). Use >1 only "
             "with backends that have no node-local state (e.g. docker); per-skill "
             "interaction output goes to reports/.../skill_logs/ in this mode.",
    )

    args = parser.parse_args()

    # Parse args
    skip_skills = args.skip.split(",") if args.skip else None
    only_skills = args.only.split(",") if args.only else None

    # Create runner and execute
    runner = SkillRunner(config_path=args.config)
    runner.run_all(
        skip_skills=skip_skills,
        only_skills=only_skills,
        resume=args.resume,
        dry_run=args.dry_run,
        use_skill=args.use_skill,
        skill_mode=args.skill_mode,
        eval_after=args.eval_after,
        n_parallel=args.n_parallel,
    )


if __name__ == "__main__":
    main()
