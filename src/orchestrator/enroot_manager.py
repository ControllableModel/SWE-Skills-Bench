"""
Enroot Manager - drop-in replacement for DockerManager on systems without
Docker daemon access (e.g. HPC clusters where users aren't in the docker group).

Uses the rootless NVIDIA enroot runtime (https://github.com/NVIDIA/enroot).

Design notes
------------
- Runs containers WITHOUT `--root` (enroot's --root remaps host user to UID 0,
  but Claude Code refuses to run as root). In enroot's user namespace, root-owned
  files in the image still appear owned by the host user, so /home/dev/ is
  accessible and writable without needing actual root.
- Uses `--rw` so writes to the rootfs persist across start/stop cycles.
- Long-running container is a backgrounded `sleep infinity` process whose PID
  is used for `enroot exec`. PID is persisted to /tmp/enroot-pids/ so eval.py
  can reattach.
- File transfers go through bind-mounted host directories set up at start time:
    /tmp/enroot-shared/<container_name>/
      claude_home/   -> /home/dev/.claude   (bind mount, rw)
      claude.json    -> /home/dev/.claude.json (bind mount, rw, single file)
    The container's /workspace lives in the writable rootfs itself, not a mount,
    so git clones and benchmark artifacts persist there for later eval.py runs.
- `execute_command(user=...)` ignores the user parameter: enroot exec inherits
  the container's namespace, and in that namespace the host user already has
  effective "root-in-namespace" capabilities (can read/write /home/dev, etc.).
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .docker_manager import ContainerConfig, ExecutionResult  # reuse dataclasses
from .logger import get_logger

logger = get_logger(__name__)


# Host paths. Env-overridable so multiple driver PROCESSES can run on ONE node (e.g. the login
# node) without colliding on shared enroot state — the node-level collision that poisons skill
# registration. Give each parallel worker its own SWE_ENROOT_SHARED_ROOT / SWE_ENROOT_PID_ROOT
# (+ ENROOT_DATA_PATH) on shared FS to isolate it. Defaults preserve the original /tmp behaviour.
_SHARED_ROOT = Path(os.environ.get("SWE_ENROOT_SHARED_ROOT", "/tmp/enroot-shared"))
_PID_ROOT = Path(os.environ.get("SWE_ENROOT_PID_ROOT", "/tmp/enroot-pids"))
# Default to the project-relative image store (data/enroot-images); SWE_ENROOT_IMAGE_CACHE
# overrides. enroot_manager.py lives at <project>/src/orchestrator/, so parents[2] = project root.
_DEFAULT_IMAGE_CACHE = Path(__file__).resolve().parents[2] / "data" / "enroot-images"
_IMAGE_CACHE_ROOT = Path(
    os.environ.get("SWE_ENROOT_IMAGE_CACHE", str(_DEFAULT_IMAGE_CACHE))
)

# Container-side mount points
_CONTAINER_CLAUDE_DIR = "/home/dev/.claude"
_CONTAINER_CLAUDE_JSON = "/home/dev/.claude.json"


def _sanitize_name(name: str) -> str:
    """enroot container names can't contain '/' or some shell metachars."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def _docker_ref_to_sqsh_name(image: str) -> str:
    """
    Convert a Docker Hub image reference to an enroot .sqsh filename.
      "zhangyiiiiii/swe-skills-bench-python:latest"
        -> "zhangyiiiiii+swe-skills-bench-python+latest.sqsh"
    """
    ref = image.replace(":", "+").replace("/", "+")
    return f"{ref}.sqsh"


class _ContainerShim:
    """
    Mimics the subset of docker-py's Container object used by lifecycle.py.

    Only `exec_run(cmd, user=None)` is implemented, returning `(exit_code, bytes)`
    to match docker-py's signature.
    """

    def __init__(self, manager: "EnrootManager"):
        self._mgr = manager

    def exec_run(self, command, user: Optional[str] = None) -> Tuple[int, bytes]:
        if isinstance(command, (list, tuple)):
            cmd_str = " ".join(shlex.quote(c) for c in command)
        else:
            cmd_str = command
        result = self._mgr.execute_command(cmd_str, user=user)
        # docker-py returns (exit_code, bytes). We merge stdout+stderr.
        merged = (result.stdout or "") + (result.stderr or "")
        return result.exit_code, merged.encode("utf-8", errors="replace")


class EnrootManager:
    """
    Drop-in replacement for DockerManager using enroot as the container runtime.

    Not all methods from DockerManager are implemented — only those actually
    called by the benchmark harness. See docstring at module top for scope.
    """

    def __init__(self):
        # Verify enroot CLI is available
        try:
            proc = subprocess.run(
                ["enroot", "version"], capture_output=True, text=True, timeout=10
            )
            if proc.returncode != 0:
                raise RuntimeError(f"enroot version failed: {proc.stderr}")
            logger.info(f"Enroot client initialized (version {proc.stdout.strip()})")
        except FileNotFoundError:
            raise RuntimeError(
                "enroot CLI not found on PATH. Install enroot: "
                "https://github.com/NVIDIA/enroot"
            )

        _SHARED_ROOT.mkdir(parents=True, exist_ok=True)
        _PID_ROOT.mkdir(parents=True, exist_ok=True)
        _IMAGE_CACHE_ROOT.mkdir(parents=True, exist_ok=True)

        # Same attribute names as DockerManager for drop-in compatibility
        self.config: Optional[ContainerConfig] = None
        self.container_name: Optional[str] = None
        self.container_pid: Optional[int] = None
        # Expose a shim that mimics docker-py Container.exec_run()
        self.container: Optional[_ContainerShim] = None

    # ------------------------------------------------------------------
    # Image management
    # ------------------------------------------------------------------

    def _image_sqsh_path(self, image: str) -> Path:
        return _IMAGE_CACHE_ROOT / _docker_ref_to_sqsh_name(image)

    def image_exists(self, image: str) -> bool:
        return self._image_sqsh_path(image).exists()

    def pull_image(self, image: str) -> bool:
        """enroot import of the Docker image into a cached .sqsh."""
        sqsh = self._image_sqsh_path(image)
        if sqsh.exists():
            logger.info(f"Image already cached: {sqsh}")
            return True

        logger.info(f"Importing image via enroot: docker://{image} -> {sqsh}")
        try:
            proc = subprocess.run(
                ["enroot", "import", "-o", str(sqsh), f"docker://{image}"],
                capture_output=True,
                text=True,
                timeout=1800,
            )
            if proc.returncode != 0:
                logger.error(f"enroot import failed: {proc.stderr[-500:]}")
                return False
            logger.info(f"Imported image: {sqsh}")
            return True
        except subprocess.TimeoutExpired:
            logger.error(f"enroot import timed out for {image}")
            return False

    # ------------------------------------------------------------------
    # Container lifecycle
    # ------------------------------------------------------------------

    def _host_shared_dir(self, name: str) -> Path:
        return _SHARED_ROOT / name

    def _host_claude_home(self, name: str) -> Path:
        return self._host_shared_dir(name) / "claude_home"

    def _host_claude_json(self, name: str) -> Path:
        return self._host_shared_dir(name) / "claude.json"

    def _pid_file(self, name: str) -> Path:
        return _PID_ROOT / f"{name}.pid"

    def _enroot_exists(self, name: str) -> bool:
        try:
            proc = subprocess.run(
                ["enroot", "list"], capture_output=True, text=True, timeout=10
            )
            lines = (proc.stdout or "").splitlines()
            return name in lines
        except Exception:
            return False

    def create_container(self, config: ContainerConfig) -> bool:
        """
        Prepare the enroot container entity and shared mount dirs. Does NOT
        yet spawn a running process — that happens in start_container().
        """
        name = _sanitize_name(config.name)
        logger.info(f"Creating enroot container: {name} (image {config.image})")
        self.config = config
        self.container_name = name

        # Ensure image is imported
        if not self.image_exists(config.image):
            if not self.pull_image(config.image):
                return False

        # Prepare host-side shared dirs
        host_shared = self._host_shared_dir(name)
        host_shared.mkdir(parents=True, exist_ok=True)
        self._host_claude_home(name).mkdir(parents=True, exist_ok=True)
        # .claude.json mount is a single file — must exist on host
        claude_json_host = self._host_claude_json(name)
        if not claude_json_host.exists():
            claude_json_host.write_text("{}\n")

        # enroot create. By default idempotent (reuse existing). For clean
        # benchmark runs set SWE_FRESH_CONTAINER=1 to force a fresh rootfs —
        # reusing a stale container carries the prior run's repo edits/skills
        # and contaminates results.
        if os.environ.get("SWE_FRESH_CONTAINER") == "1":
            # Purge any prior container AND any ORPHANED rootfs. enroot DATA_PATH is on
            # shared WeKa, so a job that died mid-run can leave a rootfs that a same-named
            # re-run would silently reuse (stale /workspace clone + deps) -> the
            # "git remote add origin already exists" failure and contaminated results.
            logger.info(f"SWE_FRESH_CONTAINER=1 — purging any stale container/rootfs: {name}")
            subprocess.run(["enroot", "remove", "-f", name], capture_output=True, text=True, timeout=120)
            data_root = os.environ.get("ENROOT_DATA_PATH") or os.path.join(
                os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "enroot")
            rootfs = os.path.join(data_root, name)
            if os.path.isdir(rootfs):
                shutil.rmtree(rootfs, ignore_errors=True)
            shared = self._host_shared_dir(name)
            if shared.exists():
                shutil.rmtree(shared, ignore_errors=True)
            self._host_shared_dir(name).mkdir(parents=True, exist_ok=True)
            self._host_claude_home(name).mkdir(parents=True, exist_ok=True)
            cjh = self._host_claude_json(name)
            if not cjh.exists():
                cjh.write_text("{}\n")
        elif self._enroot_exists(name):
            logger.info(f"Enroot container entity already exists: {name} (reusing)")
            self.container = _ContainerShim(self)
            return True

        sqsh = self._image_sqsh_path(config.image)
        # Large images (18.5GB pytorch) unsquashfs slower than 300s, esp. on few-cpu
        # nodes — the create times out before codex ever starts. Env-configurable.
        create_timeout = int(os.environ.get("SWE_ENROOT_CREATE_TIMEOUT", "1800"))
        proc = subprocess.run(
            ["enroot", "create", "--name", name, str(sqsh)],
            capture_output=True,
            text=True,
            timeout=create_timeout,
        )
        if proc.returncode != 0:
            logger.error(f"enroot create failed: {proc.stderr[-500:]}")
            return False
        logger.info(f"Enroot container created: {name}")
        self.container = _ContainerShim(self)
        return True

    def start_container(self) -> bool:
        """
        Spawn a long-running `sleep infinity` inside the container. Save its
        PID so execute_command can use `enroot exec <pid> ...`.
        """
        if not self.container_name:
            logger.error("No container to start (call create_container first)")
            return False

        name = self.container_name
        # If already running, nothing to do
        existing = self._read_pid(name)
        if existing and self._pid_alive(existing):
            self.container_pid = existing
            logger.info(f"Enroot container already running: {name} pid={existing}")
            return True

        mounts = self._build_mount_args(name)
        env_args: list[str] = [
            "-e", "HOME=/home/dev",
            "-e", "USER=dev",
            "-e", "CI=true",
            # CPU-only eval: force the enroot 98-nvidia.sh hook to skip. Some base
            # images bake NVIDIA_VISIBLE_DEVICES=all (pytorch + the -cli2168 variants);
            # on CPU-only nodes that lack nvidia-container-cli the hook then exits 1 and
            # `enroot start` fails ("Failed to start container") before interaction.
            # The hook short-circuits when NVIDIA_VISIBLE_DEVICES is "void".
            "-e", "NVIDIA_VISIBLE_DEVICES=void",
        ]
        for k, v in (self.config.env_vars or {}).items():
            env_args.extend(["-e", f"{k}={v}"])

        cmd = [
            "enroot", "start", "--rw",
            *env_args,
            *mounts,
            name,
            "sleep", "infinity",
        ]

        logger.info(f"Starting enroot container: {' '.join(shlex.quote(c) for c in cmd)}")
        log_path = _PID_ROOT / f"{name}.log"
        # Snapshot OUR pre-existing `sleep infinity` pids BEFORE starting, so the finder only
        # accepts a NEW one — on shared (mix) nodes other users' sleeps, or our own from a
        # concurrent job, must never be latched onto as this container's anchor.
        pre_existing = self._sleep_pids_snapshot()
        # Detach: new process group, stdout/stderr to file
        proc = subprocess.Popen(
            cmd,
            stdout=open(log_path, "wb"),
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        # Wait for sleep process to actually start inside the namespace
        deadline = time.time() + 15
        sleep_pid: Optional[int] = None
        while time.time() < deadline:
            sleep_pid = self._find_sleep_pid(proc.pid, exclude=pre_existing)
            if sleep_pid:
                break
            if proc.poll() is not None:
                # enroot start exited before sleep started — failure
                logger.error(
                    f"enroot start exited with code {proc.returncode} before sleep started. "
                    f"Log: {log_path.read_text()[-500:] if log_path.exists() else '(no log)'}"
                )
                return False
            time.sleep(0.3)

        if not sleep_pid:
            logger.error(f"Timed out waiting for sleep process; enroot start pid={proc.pid}")
            return False

        self._write_pid(name, sleep_pid)
        self.container_pid = sleep_pid
        logger.info(f"Enroot container started: {name} sleep_pid={sleep_pid}")
        return True

    def _build_mount_args(self, name: str) -> list[str]:
        host_claude_home = self._host_claude_home(name)
        host_claude_json = self._host_claude_json(name)
        return [
            "--mount", f"{host_claude_home}:{_CONTAINER_CLAUDE_DIR}:bind,rw,x-create=dir",
            "--mount", f"{host_claude_json}:{_CONTAINER_CLAUDE_JSON}:bind,rw,x-create=file",
        ]

    def _sleep_pids_snapshot(self) -> set:
        """OUR user's `sleep infinity` pids currently on this node."""
        try:
            proc = subprocess.run(
                ["pgrep", "-u", str(os.getuid()), "-f", "^sleep infinity$"],
                capture_output=True, text=True, timeout=5,
            )
            return {int(p) for p in proc.stdout.split() if p.strip()}
        except Exception:
            return set()

    def _find_sleep_pid(self, parent_pid: int, exclude: set = frozenset()) -> Optional[int]:
        """
        enroot start spawns `sleep infinity` somewhere in its process tree.
        Find OUR container's sleep: prefer a descendant of parent_pid; else any of
        our own NEW sleeps (not in the pre-start `exclude` snapshot).

        Shared-node safety: only this user's processes are candidates (on mix nodes
        other users commonly park `sleep infinity` in salloc sessions — latching onto
        a foreign pid made every enroot exec fail with EPERM -> "No running container").
        The old unconditional candidates[0] fallback is gone for the same reason.
        """
        try:
            proc = subprocess.run(
                ["pgrep", "-u", str(os.getuid()), "-f", "^sleep infinity$"],
                capture_output=True, text=True, timeout=5,
            )
            candidates = [int(p) for p in proc.stdout.split() if p.strip()]
        except Exception:
            return None

        # Filter to those descended from parent_pid
        for pid in candidates:
            if self._is_descendant_of(pid, parent_pid):
                return pid
        # Fallback: only a sleep of OURS that appeared after we launched enroot start.
        fresh = [p for p in candidates if p not in exclude]
        return fresh[0] if fresh else None

    def _is_descendant_of(self, pid: int, ancestor: int) -> bool:
        try:
            cur = pid
            for _ in range(20):  # cap depth
                if cur == ancestor:
                    return True
                if cur <= 1:
                    return False
                with open(f"/proc/{cur}/status") as f:
                    for line in f:
                        if line.startswith("PPid:"):
                            cur = int(line.split()[1])
                            break
                    else:
                        return False
        except Exception:
            return False
        return False

    def _pid_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _read_pid(self, name: str) -> Optional[int]:
        pf = self._pid_file(name)
        if not pf.exists():
            return None
        try:
            return int(pf.read_text().strip())
        except Exception:
            return None

    def _write_pid(self, name: str, pid: int) -> None:
        self._pid_file(name).write_text(str(pid))

    def stop_container(self, timeout: int = 10) -> bool:
        """Kill the sleep process. Container rootfs remains (reattachable)."""
        if not self.container_name:
            return True
        name = self.container_name
        pid = self.container_pid or self._read_pid(name)
        if not pid:
            return True
        try:
            os.kill(pid, signal.SIGTERM)
            # Give it a moment to die
            for _ in range(timeout * 10):
                if not self._pid_alive(pid):
                    break
                time.sleep(0.1)
            if self._pid_alive(pid):
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self._pid_file(name).unlink(missing_ok=True)
        self.container_pid = None
        logger.info(f"Enroot container stopped: {name}")
        return True

    def remove_container(self, force: bool = True) -> bool:
        """Stop (if running) and remove the enroot container entity."""
        if not self.container_name:
            return True
        name = self.container_name
        self.stop_container()
        try:
            args = ["enroot", "remove"]
            if force:
                args.append("-f")
            args += ["--", name]
            subprocess.run(args, capture_output=True, text=True, timeout=60)
        except Exception as e:
            logger.warning(f"enroot remove failed for {name}: {e}")
        # Clean shared dir
        try:
            import shutil
            shared = self._host_shared_dir(name)
            if shared.exists():
                shutil.rmtree(shared, ignore_errors=True)
        except Exception:
            pass
        self.container = None
        self.container_name = None
        self.container_pid = None
        logger.info(f"Enroot container removed: {name}")
        return True

    def cleanup(self):
        logger.info("Cleaning up enroot resources...")
        self.stop_container()
        self.remove_container(force=True)

    def restart_container(self, timeout: int = 10) -> bool:
        self.stop_container(timeout=timeout)
        return self.start_container()

    def attach_to_container(self, name: str) -> bool:
        """Reattach to an existing enroot container by name (for eval.py)."""
        name = _sanitize_name(name)
        if not self._enroot_exists(name):
            logger.info(f"Enroot container not found: {name}")
            return False
        self.container_name = name
        # Reconstruct config minimally (enough for execute_command)
        self.config = ContainerConfig(image="", name=name)
        self.container = _ContainerShim(self)
        # Read existing PID if container is still running
        pid = self._read_pid(name)
        if pid and self._pid_alive(pid):
            self.container_pid = pid
            logger.info(f"Attached to running enroot container: {name} pid={pid}")
        else:
            # Container entity exists but not running; caller should start it
            self.container_pid = None
            logger.info(f"Attached to stopped enroot container: {name}")
        return True

    def container_exists(self, name: str) -> bool:
        return self._enroot_exists(_sanitize_name(name))

    def get_container_by_name(self, name: str) -> Optional[Any]:
        if self._enroot_exists(_sanitize_name(name)):
            return _ContainerShim(self)
        return None

    def get_container_status(self) -> Optional[str]:
        if not self.container_name:
            return None
        pid = self.container_pid or self._read_pid(self.container_name)
        if pid and self._pid_alive(pid):
            return "running"
        if self._enroot_exists(self.container_name):
            return "exited"
        return None

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    def execute_command(
        self,
        command: str,
        timeout: Optional[int] = None,
        workdir: Optional[str] = None,
        user: Optional[str] = None,  # ignored — see module docstring
    ) -> ExecutionResult:
        """Run a shell command inside the container via `enroot exec <pid>`."""
        if not self.container_pid or not self._pid_alive(self.container_pid):
            # Try to recover by looking up pid file (attach scenario)
            if self.container_name:
                pid = self._read_pid(self.container_name)
                if pid and self._pid_alive(pid):
                    self.container_pid = pid
            if not self.container_pid or not self._pid_alive(self.container_pid):
                return ExecutionResult(
                    exit_code=-1, stdout="", stderr="No running container available",
                    duration=0, timed_out=False,
                )

        timeout = timeout or (self.config.timeout_per_command if self.config else 300)

        if workdir:
            full_cmd = f"cd {shlex.quote(workdir)} && {command}"
        else:
            full_cmd = command

        args = ["enroot", "exec", str(self.container_pid), "sh", "-c", full_cmd]
        start = time.time()
        try:
            proc = subprocess.run(
                args, capture_output=True, text=True, timeout=timeout,
            )
            return ExecutionResult(
                exit_code=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                duration=time.time() - start,
                timed_out=False,
            )
        except subprocess.TimeoutExpired as e:
            return ExecutionResult(
                exit_code=-1,
                stdout=(e.stdout or b"").decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""),
                stderr=f"Command timed out after {timeout}s",
                duration=time.time() - start,
                timed_out=True,
            )
        except Exception as e:
            return ExecutionResult(
                exit_code=-1, stdout="", stderr=str(e),
                duration=time.time() - start, timed_out=False,
            )

    # ------------------------------------------------------------------
    # File transfer
    # ------------------------------------------------------------------

    def _host_path_for(self, container_path: str) -> Optional[Path]:
        """
        If container_path is under a bind-mounted host directory, return the
        equivalent host path. Otherwise return None (caller should fall back
        to exec-based writing).
        """
        if not self.container_name:
            return None
        name = self.container_name
        if container_path == _CONTAINER_CLAUDE_JSON:
            return self._host_claude_json(name)
        if container_path.startswith(_CONTAINER_CLAUDE_DIR + "/"):
            rel = container_path[len(_CONTAINER_CLAUDE_DIR) + 1:]
            return self._host_claude_home(name) / rel
        return None

    def write_file_direct(self, path: str, content: bytes) -> Tuple[bool, str]:
        """
        Write content to a file inside the container.

        Fast path: if path is under a bind-mounted host dir, write directly to
        the host. Otherwise, stream through `enroot exec ... dd`.
        """
        try:
            host_path = self._host_path_for(path)
            if host_path is not None:
                host_path.parent.mkdir(parents=True, exist_ok=True)
                host_path.write_bytes(content)
                return True, f"Wrote {len(content)} bytes (via mount)"

            # Fallback: exec with stdin
            if not self.container_pid or not self._pid_alive(self.container_pid):
                return False, "No running container for exec-based write"

            # Ensure parent dir exists inside container
            parent = os.path.dirname(path)
            if parent:
                self.execute_command(f"mkdir -p {shlex.quote(parent)}")

            proc = subprocess.run(
                ["enroot", "exec", str(self.container_pid),
                 "sh", "-c", f"cat > {shlex.quote(path)}"],
                input=content, capture_output=True, timeout=120,
            )
            if proc.returncode != 0:
                return False, proc.stderr.decode("utf-8", errors="replace")[-500:]
            return True, f"Wrote {len(content)} bytes (via exec)"
        except Exception as e:
            logger.error(f"write_file_direct failed: {e}")
            return False, str(e)

    def write_files_batch(self, files: Dict[str, bytes]) -> Tuple[bool, str]:
        total = 0
        for path, content in files.items():
            ok, msg = self.write_file_direct(path, content)
            if not ok:
                return False, f"Failed on {path}: {msg}"
            total += len(content)
        return True, f"Wrote {len(files)} files ({total} bytes)"

    def copy_to_container(self, src_path: str, dst_path: str) -> bool:
        """Copy a single host file to a path inside the container."""
        try:
            with open(src_path, "rb") as f:
                content = f.read()
            ok, _ = self.write_file_direct(dst_path, content)
            return ok
        except Exception as e:
            logger.error(f"copy_to_container failed ({src_path} -> {dst_path}): {e}")
            return False

    def copy_from_container(self, src_path: str, dst_path: str) -> bool:
        """Copy a file from inside the container to the host."""
        try:
            host_path = self._host_path_for(src_path)
            if host_path is not None and host_path.exists():
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                with open(host_path, "rb") as fsrc, open(dst_path, "wb") as fdst:
                    fdst.write(fsrc.read())
                return True

            # Fallback: cat via exec
            if not self.container_pid or not self._pid_alive(self.container_pid):
                return False
            proc = subprocess.run(
                ["enroot", "exec", str(self.container_pid),
                 "cat", src_path],
                capture_output=True, timeout=120,
            )
            if proc.returncode != 0:
                return False
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            with open(dst_path, "wb") as f:
                f.write(proc.stdout)
            return True
        except Exception as e:
            logger.error(f"copy_from_container failed: {e}")
            return False

    # Context manager protocol (matches DockerManager)
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False
