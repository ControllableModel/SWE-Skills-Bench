"""
Test skill: add-admin-api-endpoint
Verify that the Agent correctly adds announcements CRUD API to Ghost CMS.
"""

import os
import subprocess
import re
import json
import pytest


class TestAddAdminApiEndpoint:
    REPO_DIR = "/workspace/Ghost"

    # === File Path Checks ===

    def test_ghost_core_exists(self):
        """Verify Ghost core directory structure exists"""
        candidates = [
            os.path.join(self.REPO_DIR, "ghost/core"),
            os.path.join(self.REPO_DIR, "core"),
        ]
        found = any(os.path.isdir(c) for c in candidates)
        assert found, "Ghost core directory not found"

    # === Semantic Checks ===

    def test_announcement_model_or_schema_defined(self):
        """Verify an announcement model/schema with required fields exists"""
        found_files = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root:
                continue
            for f in files:
                if "announcement" in f.lower() and f.endswith((".js", ".ts", ".json")):
                    found_files.append(os.path.join(root, f))
        assert len(found_files) > 0, "No announcement-related files found"
        all_content = ""
        for fp in found_files[:10]:
            with open(fp) as fh:
                all_content += fh.read()
        required_fields = ["title", "content", "visibility"]
        found_fields = [f for f in required_fields if f in all_content.lower()]
        assert len(found_fields) >= 2, (
            f"Announcement schema missing expected fields. Found: {found_fields}, expected: {required_fields}"
        )

    def test_announcement_has_date_fields(self):
        """Verify announcement schema includes starts_at and ends_at fields"""
        found_files = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root:
                continue
            for f in files:
                if "announcement" in f.lower() and f.endswith((".js", ".ts")):
                    found_files.append(os.path.join(root, f))
        all_content = ""
        for fp in found_files[:10]:
            with open(fp) as fh:
                all_content += fh.read()
        content_lower = all_content.lower()
        has_starts = "starts_at" in content_lower or "startsat" in content_lower or "start_date" in content_lower
        has_ends = "ends_at" in content_lower or "endsat" in content_lower or "end_date" in content_lower
        assert has_starts and has_ends, "Announcement schema missing starts_at or ends_at fields"

    def test_crud_routes_defined(self):
        """Verify CRUD routes for announcements are defined"""
        found_routes = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root:
                continue
            for f in files:
                if f.endswith((".js", ".ts")):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            content = fh.read()
                        if "announcement" in content.lower() and (
                            "browse" in content.lower()
                            or "router" in content.lower()
                            or "route" in content.lower()
                        ):
                            found_routes = True
                            break
                    except (UnicodeDecodeError, PermissionError):
                        continue
            if found_routes:
                break
        assert found_routes, "No announcement routes found in codebase"

    def test_announcement_controller_has_all_crud_methods(self):
        """Verify announcement controller implements browse, read, add, edit, destroy"""
        controller_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root:
                continue
            for f in files:
                if "announcement" in f.lower() and f.endswith((".js", ".ts")):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            controller_content += fh.read() + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        if not controller_content:
            pytest.skip("No announcement controller files found")
        methods = ["browse", "read", "add", "edit", "destroy"]
        found = [m for m in methods if m in controller_content.lower()]
        assert len(found) >= 4, (
            f"Controller missing CRUD methods. Found: {found}, expected all of: {methods}"
        )

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify npm install completes"""
        result = subprocess.run(
            ["npm", "install"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, f"npm install failed: {result.stderr[:500]}"

    def test_ghost_lint_passes(self):
        """Verify lint passes on the codebase"""
        # Check if lint script exists in package.json
        pkg_path = os.path.join(self.REPO_DIR, "package.json")
        with open(pkg_path) as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})
        if "lint" not in scripts:
            pytest.skip("No lint script in package.json")
        result = subprocess.run(
            ["npm", "run", "lint"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Lint failed: {result.stdout[:500]}"

    def test_announcement_api_path_registered(self):
        """Verify /ghost/api/admin/announcements/ path is registered in routes"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root:
                continue
            for f in files:
                if f.endswith((".js", ".ts")):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            content = fh.read()
                        if "announcements" in content and ("api" in content.lower() or "admin" in content.lower()):
                            if re.search(r"['\"/]announcements['\"/]", content):
                                found = True
                                break
                    except (UnicodeDecodeError, PermissionError):
                        continue
            if found:
                break
        assert found, "Announcement API path not found in route definitions"

    def test_ghost_test_suite_passes(self):
        """Verify Ghost test suite passes"""
        pkg_path = os.path.join(self.REPO_DIR, "package.json")
        with open(pkg_path) as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})
        if "test" not in scripts:
            pytest.skip("No test script in package.json")
        result = subprocess.run(
            ["npm", "test"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
        )

    def test_announcement_visibility_field_validated(self):
        """Verify visibility field has validation (e.g., enum of allowed values)"""
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root:
                continue
            for f in files:
                if "announcement" in f.lower() and f.endswith((".js", ".ts")):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            all_content += fh.read() + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        if not all_content:
            pytest.skip("No announcement files found")
        has_validation = (
            "visibility" in all_content
            and (
                "enum" in all_content.lower()
                or "isIn" in all_content
                or "oneOf" in all_content
                or "members" in all_content.lower()
                or "public" in all_content.lower()
            )
        )
        assert has_validation, "Visibility field does not appear to have validation"
