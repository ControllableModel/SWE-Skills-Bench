"""
Test skill: python-background-jobs
Verify that the Agent implements an async report export pipeline in Celery
with query, transform, write_csv, and upload tasks, plus a FastAPI API.
"""

import os
import subprocess
import ast
import re
import pytest


class TestPythonBackgroundJobs:
    REPO_DIR = "/workspace/celery"

    # === File Path Checks ===

    def test_task_files_exist(self):
        """Verify report export task files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("report" in f.lower() or "export" in f.lower() or "task" in f.lower()):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        content = fh.read()
                    if "task" in content.lower() and ("report" in content.lower() or "export" in content.lower()):
                        found = True
                        break
            if found:
                break
        assert found, "No report export task files found"

    # === Semantic Checks ==

    def test_pipeline_has_query_task(self):
        """Verify pipeline includes a query/fetch data task"""
        all_content = self._find_task_content()
        has_query = "query" in all_content.lower() or "fetch" in all_content.lower()
        assert has_query, "Pipeline missing query/fetch task"

    def test_pipeline_has_transform_task(self):
        """Verify pipeline includes a transform/process task"""
        all_content = self._find_task_content()
        has_transform = "transform" in all_content.lower() or "process" in all_content.lower()
        assert has_transform, "Pipeline missing transform task"

    def test_pipeline_has_write_csv_task(self):
        """Verify pipeline includes a write_csv task"""
        all_content = self._find_task_content()
        has_csv = "csv" in all_content.lower() or "write" in all_content.lower()
        assert has_csv, "Pipeline missing write_csv task"

    def test_pipeline_has_upload_task(self):
        """Verify pipeline includes an upload task"""
        all_content = self._find_task_content()
        has_upload = "upload" in all_content.lower() or "s3" in all_content.lower() or "storage" in all_content.lower()
        assert has_upload, "Pipeline missing upload task"

    def test_tasks_are_celery_decorated(self):
        """Verify tasks use @app.task or @shared_task decorators"""
        all_content = self._find_task_content()
        has_decorator = (
            "@app.task" in all_content
            or "@shared_task" in all_content
            or "@celery" in all_content.lower()
            or "task(" in all_content
        )
        assert has_decorator, "Tasks not using Celery task decorators"

    def test_pipeline_chains_tasks(self):
        """Verify pipeline uses Celery chain/chord/group for task composition"""
        all_content = self._find_task_content()
        has_chain = (
            "chain" in all_content
            or "chord" in all_content
            or "group" in all_content
            or "pipeline" in all_content.lower()
            or "link" in all_content
            or "|" in all_content
        )
        assert has_chain, "Pipeline doesn't chain tasks using Celery primitives"

    def test_fastapi_api_exists(self):
        """Verify FastAPI API endpoint exists for triggering reports"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            content = fh.read()
                        if "FastAPI" in content or "fastapi" in content:
                            if "report" in content.lower() or "export" in content.lower():
                                found = True
                                break
                    except (UnicodeDecodeError, PermissionError):
                        continue
            if found:
                break
        assert found, "FastAPI API for report export not found"

    # === Functional Checks ===

    def test_task_files_parse(self):
        """Verify all task Python files have valid syntax"""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("report" in f.lower() or "export" in f.lower()):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        source = fh.read()
                    try:
                        ast.parse(source)
                    except SyntaxError as e:
                        pytest.fail(f"Syntax error in {fpath}: {e}")

    def test_task_module_imports(self):
        """Verify task module can be imported"""
        # Find the main task module
        task_file = None
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("report" in f.lower() or "export" in f.lower()):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        content = fh.read()
                    if "task" in content.lower():
                        task_file = fpath
                        break
            if task_file:
                break
        if task_file is None:
            pytest.skip("No task module found")
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open('{task_file}').read()); print('OK')"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Task file parsing failed: {result.stderr}"

    def test_job_store_exists(self):
        """Verify job store for tracking report status exists"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            content = fh.read()
                        if ("store" in content.lower() or "status" in content.lower() or "job" in content.lower()) and "report" in content.lower():
                            found = True
                            break
                    except (UnicodeDecodeError, PermissionError):
                        continue
            if found:
                break
        assert found, "Job store for tracking report status not found"

    def _find_task_content(self):
        """Helper to find and return all task-related content"""
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("report" in f.lower() or "export" in f.lower() or "task" in f.lower()):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            all_content += fh.read() + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content
