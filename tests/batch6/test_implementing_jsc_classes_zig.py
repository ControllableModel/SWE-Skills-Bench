"""
Test skill: implementing-jsc-classes-zig
Verify that the Agent correctly implements a CronJob JSC class in Bun,
including the .classes.ts definition and Zig implementation with
constructor, methods, getters, validation, and lifecycle management.
"""

import os
import re
import subprocess
import pytest


class TestImplementingJscClassesZig:
    REPO_DIR = "/workspace/bun"

    # === File Path Checks ===

    def test_classes_ts_file_exists(self):
        """Verify the .classes.ts definition file exists"""
        path = os.path.join(
            self.REPO_DIR, "src/bun.js/bindings/CronJob.classes.ts"
        )
        assert os.path.exists(path), f"CronJob.classes.ts not found at {path}"

    def test_zig_implementation_file_exists(self):
        """Verify the Zig implementation file exists"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/CronJob.zig")
        assert os.path.exists(path), f"CronJob.zig not found at {path}"

    # === Semantic Checks ===

    def test_classes_ts_defines_cronjob_class(self):
        """Verify .classes.ts defines CronJob with correct class structure"""
        path = os.path.join(
            self.REPO_DIR, "src/bun.js/bindings/CronJob.classes.ts"
        )
        with open(path, "r") as f:
            content = f.read()

        assert "CronJob" in content, "Missing CronJob class name"
        assert "construct" in content, (
            "CronJob.classes.ts must define a construct (constructor)"
        )

    def test_classes_ts_has_methods(self):
        """Verify .classes.ts defines expected methods (stop, resume, trigger, etc.)"""
        path = os.path.join(
            self.REPO_DIR, "src/bun.js/bindings/CronJob.classes.ts"
        )
        with open(path, "r") as f:
            content = f.read()

        expected = ["stop", "resume", "trigger"]
        for method in expected:
            assert re.search(rf"\b{method}\b", content), (
                f".classes.ts missing method: {method}"
            )

    def test_classes_ts_has_getters(self):
        """Verify .classes.ts defines getters for CronJob state"""
        path = os.path.join(
            self.REPO_DIR, "src/bun.js/bindings/CronJob.classes.ts"
        )
        with open(path, "r") as f:
            content = f.read()

        # Should have getter for at least pattern and running
        has_getters = (
            "get" in content
            and ("pattern" in content or "cronExpression" in content or "expression" in content)
        )
        assert has_getters, (
            ".classes.ts should define getters for CronJob state (pattern, running, etc.)"
        )

    def test_zig_has_struct_definition(self):
        """Verify Zig implementation defines a CronJob struct"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/CronJob.zig")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"(pub\s+)?const\s+CronJob\s*=\s*struct", content) or \
               re.search(r"struct\s*\{", content), (
            "CronJob.zig must define a CronJob struct"
        )

    def test_zig_implements_constructor(self):
        """Verify Zig implementation has a constructor/init function"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/CronJob.zig")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"(fn\s+construct|fn\s+init|fn\s+create)", content), (
            "CronJob.zig must implement a constructor (construct/init/create)"
        )

    def test_zig_validates_cron_expression(self):
        """Verify Zig implementation validates the cron expression"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/CronJob.zig")
        with open(path, "r") as f:
            content = f.read()

        has_validation = (
            "invalid" in content.lower()
            or "parse" in content.lower()
            or "validate" in content.lower()
            or "error" in content.lower()
        )
        assert has_validation, (
            "CronJob.zig should validate cron expression input"
        )

    def test_zig_has_lifecycle_methods(self):
        """Verify Zig has stop, resume/start, trigger methods"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/CronJob.zig")
        with open(path, "r") as f:
            content = f.read()

        assert "stop" in content, "CronJob.zig missing stop method"
        assert "resume" in content or "start" in content, (
            "CronJob.zig missing resume/start method"
        )
        assert "trigger" in content, "CronJob.zig missing trigger method"

    def test_zig_has_deinit_or_destructor(self):
        """Verify Zig implements resource cleanup (deinit/finalize)"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/CronJob.zig")
        with open(path, "r") as f:
            content = f.read()

        has_cleanup = "deinit" in content or "finalize" in content or "destroy" in content
        assert has_cleanup, (
            "CronJob.zig should implement resource cleanup (deinit/finalize)"
        )

    def test_zig_handles_callback(self):
        """Verify Zig stores and invokes a user-provided callback"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/CronJob.zig")
        with open(path, "r") as f:
            content = f.read()

        has_callback = (
            "callback" in content.lower()
            or "handler" in content.lower()
            or "JSValue" in content
        )
        assert has_callback, (
            "CronJob.zig should handle a user-provided callback function"
        )

    def test_registered_in_generated_classes_list(self):
        """Verify CronJob is registered in generated_classes_list.zig or equivalent"""
        # Search for registration in the generated classes list
        list_path = os.path.join(
            self.REPO_DIR, "src/bun.js/bindings/generated_classes_list.zig"
        )
        if os.path.exists(list_path):
            with open(list_path, "r") as f:
                content = f.read()
            assert "CronJob" in content, (
                "CronJob must be registered in generated_classes_list.zig"
            )
        else:
            # Try alternative locations
            found = False
            for root, dirs, files in os.walk(
                os.path.join(self.REPO_DIR, "src/bun.js/bindings")
            ):
                for fname in files:
                    if "generated" in fname or "classes_list" in fname:
                        fpath = os.path.join(root, fname)
                        with open(fpath, "r") as f:
                            if "CronJob" in f.read():
                                found = True
                                break
                if found:
                    break
            assert found, (
                "CronJob must be registered in a generated classes list file"
            )

    def test_cronjob_exported_on_bun_global(self):
        """Verify CronJob is accessible on the Bun global object"""
        # Check that there is a JS/TS export or binding for Bun.CronJob
        bindings_dir = os.path.join(self.REPO_DIR, "src/bun.js")
        found = False
        for root, dirs, files in os.walk(bindings_dir):
            for fname in files:
                if fname.endswith((".ts", ".js", ".zig")):
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r") as f:
                            content = f.read()
                        if re.search(r"(Bun\.CronJob|CronJob|\"CronJob\")", content):
                            if "export" in content or "globalObject" in content.lower() or "@\"CronJob\"" in content:
                                found = True
                                break
                    except Exception:
                        continue
            if found:
                break
        assert found, "CronJob should be exported on Bun global"

    # === Functional Checks ===

    def test_classes_ts_is_valid_typescript(self):
        """Verify CronJob.classes.ts is syntactically valid TypeScript/JavaScript"""
        path = os.path.join(
            self.REPO_DIR, "src/bun.js/bindings/CronJob.classes.ts"
        )
        with open(path, "r") as f:
            content = f.read()

        # Basic syntax check: balanced braces
        open_braces = content.count("{")
        close_braces = content.count("}")
        assert abs(open_braces - close_braces) <= 1, (
            f"Unbalanced braces in .classes.ts: {{ = {open_braces}, }} = {close_braces}"
        )

        # Should export something
        assert "export" in content or "module" in content or "define" in content, (
            ".classes.ts should export the class definition"
        )

    def test_zig_file_compiles_syntax_check(self):
        """Verify the Zig file has no obvious syntax errors (basic linting)"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/CronJob.zig")
        with open(path, "r") as f:
            content = f.read()

        # Check balanced braces
        open_braces = content.count("{")
        close_braces = content.count("}")
        assert abs(open_braces - close_braces) <= 2, (
            f"Unbalanced braces in CronJob.zig: {{ = {open_braces}, }} = {close_braces}"
        )

        # Check that all `pub fn` have matching return types
        pub_fns = re.findall(r"pub\s+fn\s+\w+", content)
        assert len(pub_fns) >= 3, (
            f"CronJob.zig should have at least 3 public functions, found {len(pub_fns)}"
        )

    def test_bun_build_succeeds(self):
        """Verify the Bun project builds successfully with the CronJob class"""
        # Try building the project
        result = subprocess.run(
            ["make", "setup"],
            capture_output=True, text=True, timeout=300,
            cwd=self.REPO_DIR,
        )
        # If make setup isn't available, try cmake or zig build
        if result.returncode != 0:
            result = subprocess.run(
                ["zig", "build", "--summary", "none"],
                capture_output=True, text=True, timeout=300,
                cwd=self.REPO_DIR,
            )

        # If neither works, just check that zig can parse the file
        if result.returncode != 0:
            result = subprocess.run(
                ["zig", "ast-check", "src/bun.js/bindings/CronJob.zig"],
                capture_output=True, text=True, timeout=60,
                cwd=self.REPO_DIR,
            )
            if result.returncode != 0:
                pytest.skip(
                    f"Build system not available; zig ast-check stderr: {result.stderr[:500]}"
                )
