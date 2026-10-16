"""
Agent Skills Benchmark - Orchestrator Module
General control layer: manages container lifecycle and global logging.
"""

from .logger import get_logger, log_section, setup_logger

__all__ = [
    "DockerManager",
    "BenchmarkLifecycle",
    "setup_logger",
    "get_logger",
    "log_section",
]


def __getattr__(name):
    if name == "DockerManager":
        from .docker_manager import DockerManager

        return DockerManager
    if name == "BenchmarkLifecycle":
        from .lifecycle import BenchmarkLifecycle

        return BenchmarkLifecycle
    raise AttributeError(name)
