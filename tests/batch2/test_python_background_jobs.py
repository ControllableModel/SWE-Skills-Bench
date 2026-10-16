"""
Test skill: python-background-jobs
Verify that the Agent correctly designs a video transcoding task
system using Celery including task definitions with retry logic,
workflow orchestration with chains/groups/chords, and progress tracking.
"""

import os
import re
import ast
import subprocess
import pytest


class TestPythonBackgroundJobs:
    REPO_DIR = "/workspace/celery"

    # === File Path Checks ===

    def test_tasks_file_exists(self):
        """Verify examples/transcoding/tasks.py exists"""
        path = os.path.join(self.REPO_DIR, "examples/transcoding/tasks.py")
        assert os.path.exists(path), f"tasks.py not found at {path}"

    def test_workflow_file_exists(self):
        """Verify examples/transcoding/workflow.py exists"""
        path = os.path.join(self.REPO_DIR, "examples/transcoding/workflow.py")
        assert os.path.exists(path), f"workflow.py not found at {path}"

    # === Semantic Checks ===

    def test_tasks_defines_pipeline_stages(self):
        """Verify tasks.py defines distinct transcoding pipeline stage tasks"""
        path = os.path.join(self.REPO_DIR, "examples/transcoding/tasks.py")
        with open(path) as f:
            content = f.read()

        # Expect tasks for validation, transcoding, thumbnail, notification
        stage_indicators = [
            "validat", "transcode", "transcod", "thumbnail",
            "notif", "extract", "upload", "encode",
        ]
        found = [ind for ind in stage_indicators if ind in content.lower()]
        assert len(found) >= 3, (
            f"tasks.py should define multiple pipeline stages. Found: {found}"
        )

    def test_tasks_use_celery_task_decorator(self):
        """Verify tasks use Celery's @app.task or @shared_task decorator"""
        path = os.path.join(self.REPO_DIR, "examples/transcoding/tasks.py")
        with open(path) as f:
            content = f.read()

        task_indicators = [
            "@app.task", "@shared_task", "@celery.task",
            "from celery import", "from celery.app",
        ]
        found = [ind for ind in task_indicators if ind in content]
        assert len(found) >= 1, (
            f"tasks.py should use Celery task decorators. "
            f"None of {task_indicators} found."
        )

    def test_tasks_have_retry_config(self):
        """Verify at least one task declares retry behavior"""
        path = os.path.join(self.REPO_DIR, "examples/transcoding/tasks.py")
        with open(path) as f:
            content = f.read()

        retry_indicators = [
            "max_retries", "retry", "autoretry_for",
            "retry_backoff", "default_retry_delay",
        ]
        found = [ind for ind in retry_indicators if ind in content]
        assert len(found) >= 2, (
            f"Tasks should declare retry configuration. Found: {found}"
        )

    def test_tasks_have_error_handling(self):
        """Verify tasks include error callbacks or handlers"""
        path = os.path.join(self.REPO_DIR, "examples/transcoding/tasks.py")
        with open(path) as f:
            content = f.read()

        error_indicators = [
            "on_failure", "link_error", "except", "try:",
            "raise", "Error", "Exception",
        ]
        found = [ind for ind in error_indicators if ind in content]
        assert len(found) >= 2, (
            f"Tasks should include error handling. Found: {found}"
        )

    def test_workflow_uses_celery_primitives(self):
        """Verify workflow.py uses chain, group, or chord"""
        path = os.path.join(self.REPO_DIR, "examples/transcoding/workflow.py")
        with open(path) as f:
            content = f.read()

        primitives = ["chain", "group", "chord"]
        found = [p for p in primitives if p in content]
        assert len(found) >= 2, (
            f"workflow.py should use Celery primitives (chain, group, chord). "
            f"Found: {found}"
        )

    def test_workflow_has_sequential_pipeline(self):
        """Verify workflow defines at least one sequential pipeline"""
        path = os.path.join(self.REPO_DIR, "examples/transcoding/workflow.py")
        with open(path) as f:
            content = f.read()

        sequential_indicators = [
            "chain(", "chain(",  # explicit chain
            "|",                  # pipe operator for chaining
            ".s()", ".si(",       # Celery signatures
        ]
        # Check for chain or pipe operator usage
        has_chain = "chain" in content or ".s()" in content
        has_pipe = "|" in content and (".s(" in content or ".si(" in content)
        assert has_chain or has_pipe, (
            "Workflow should define a sequential pipeline using chain or pipe operator"
        )

    def test_workflow_has_parallel_fanout(self):
        """Verify workflow includes at least one parallel fan-out step"""
        path = os.path.join(self.REPO_DIR, "examples/transcoding/workflow.py")
        with open(path) as f:
            content = f.read()

        parallel_indicators = ["group(", "chord("]
        found = [ind for ind in parallel_indicators if ind in content]
        assert len(found) >= 1, (
            f"Workflow should include parallel fan-out (group/chord). "
            f"Found: {found}"
        )

    def test_workflow_has_progress_tracking(self):
        """Verify workflow includes progress tracking or status reporting"""
        combined = ""
        for fname in ["tasks.py", "workflow.py"]:
            path = os.path.join(self.REPO_DIR, f"examples/transcoding/{fname}")
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        progress_indicators = [
            "progress", "status", "update_state", "meta",
            "PROGRESS", "state", "current", "total",
        ]
        found = [ind for ind in progress_indicators if ind in combined]
        assert len(found) >= 2, (
            f"Should include progress tracking. Found: {found}"
        )

    def test_tasks_structured_results(self):
        """Verify tasks return structured results (dict/dataclass)"""
        path = os.path.join(self.REPO_DIR, "examples/transcoding/tasks.py")
        with open(path) as f:
            content = f.read()

        # Look for dict returns or dataclass usage
        result_indicators = [
            "return {", 'return {"', "return dict(",
            "@dataclass", "TypedDict", "result",
        ]
        found = [ind for ind in result_indicators if ind in content]
        assert len(found) >= 1, (
            f"Tasks should return structured results. Found: {found}"
        )

    # === Functional Checks ===

    def test_tasks_valid_python(self):
        """Verify tasks.py is valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "examples/transcoding/tasks.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"tasks.py has syntax errors: {e}")

    def test_workflow_valid_python(self):
        """Verify workflow.py is valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "examples/transcoding/workflow.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"workflow.py has syntax errors: {e}")

    def test_workflow_defines_entry_point(self):
        """Verify workflow.py defines a main entry point function"""
        path = os.path.join(self.REPO_DIR, "examples/transcoding/workflow.py")
        with open(path) as f:
            content = f.read()

        tree = ast.parse(content)
        func_names = [
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        ]
        entry_candidates = [
            n for n in func_names
            if any(kw in n.lower() for kw in [
                "main", "run", "start", "launch", "execute", "pipeline",
                "workflow", "process",
            ])
        ]
        assert len(entry_candidates) >= 1, (
            f"workflow.py should define an entry point function. "
            f"Found functions: {func_names}"
        )

    def test_tasks_bind_parameter(self):
        """Verify at least one task uses bind=True for self access"""
        path = os.path.join(self.REPO_DIR, "examples/transcoding/tasks.py")
        with open(path) as f:
            content = f.read()

        assert "bind=True" in content or "bind = True" in content, (
            "At least one task should use bind=True for self access"
        )
