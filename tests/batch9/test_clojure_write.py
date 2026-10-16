"""
Test skill: clojure-write
Verify that the Agent implements a migration validator in Clojure for Metabase,
with core, schema_diff, integrity, and report namespaces.
"""

import os
import re
import pytest


class TestClojureWrite:
    REPO_DIR = "/workspace/metabase"

    # === File Path Checks ===

    def test_core_namespace_exists(self):
        """Verify migration validator core namespace file exists"""
        found = False
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src")):
            for f in files:
                if "migration" in f.lower() and "core" in f.lower() and f.endswith(".clj"):
                    found = True
                    break
                if f == "core.clj" and "migration" in root.lower():
                    found = True
                    break
            if found:
                break
        assert found, "Migration validator core.clj not found"

    def test_schema_diff_namespace_exists(self):
        """Verify schema_diff namespace file exists"""
        found = False
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src")):
            for f in files:
                if "schema" in f.lower() and "diff" in f.lower() and f.endswith(".clj"):
                    found = True
                    break
            if found:
                break
        assert found, "schema_diff.clj not found"

    def test_integrity_namespace_exists(self):
        """Verify integrity namespace file exists"""
        found = False
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src")):
            for f in files:
                if "integrity" in f.lower() and f.endswith(".clj"):
                    found = True
                    break
            if found:
                break
        assert found, "integrity.clj not found"

    def test_report_namespace_exists(self):
        """Verify report namespace file exists"""
        found = False
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src")):
            for f in files:
                if "report" in f.lower() and "migration" in root.lower() and f.endswith(".clj"):
                    found = True
                    break
            if found:
                break
        assert found, "report.clj not found"

    # === Semantic Checks ===

    def test_core_has_validate_function(self):
        """Verify core namespace defines a validate or run function"""
        core_file = None
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src")):
            for f in files:
                if ("migration" in f.lower() or "migration" in root.lower()) and "core" in f.lower() and f.endswith(".clj"):
                    core_file = os.path.join(root, f)
                    break
            if core_file:
                break
        if core_file is None:
            pytest.skip("core.clj not found")
        with open(core_file) as fh:
            content = fh.read()
        has_validate = (
            "defn validate" in content
            or "defn run" in content
            or "defn check" in content
        )
        assert has_validate, "core namespace missing validate/run/check function"

    def test_schema_diff_compares_schemas(self):
        """Verify schema_diff namespace has diff/compare logic"""
        diff_file = None
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src")):
            for f in files:
                if "schema" in f.lower() and "diff" in f.lower() and f.endswith(".clj"):
                    diff_file = os.path.join(root, f)
                    break
            if diff_file:
                break
        if diff_file is None:
            pytest.skip("schema_diff.clj not found")
        with open(diff_file) as fh:
            content = fh.read()
        content_lower = content.lower()
        has_diff = "diff" in content_lower or "compare" in content_lower or "change" in content_lower
        assert has_diff, "schema_diff namespace missing diff/compare logic"

    def test_integrity_checks_constraints(self):
        """Verify integrity namespace checks database constraints"""
        int_file = None
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src")):
            for f in files:
                if "integrity" in f.lower() and f.endswith(".clj"):
                    int_file = os.path.join(root, f)
                    break
            if int_file:
                break
        if int_file is None:
            pytest.skip("integrity.clj not found")
        with open(int_file) as fh:
            content = fh.read()
        content_lower = content.lower()
        has_check = (
            "constraint" in content_lower
            or "foreign" in content_lower
            or "index" in content_lower
            or "integrity" in content_lower
        )
        assert has_check, "integrity namespace missing constraint checking logic"

    def test_report_generates_output(self):
        """Verify report namespace has output generation"""
        report_file = None
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src")):
            for f in files:
                if "report" in f.lower() and f.endswith(".clj") and "migration" in root.lower():
                    report_file = os.path.join(root, f)
                    break
            if report_file:
                break
        if report_file is None:
            pytest.skip("report.clj not found")
        with open(report_file) as fh:
            content = fh.read()
        content_lower = content.lower()
        has_report = (
            "generate" in content_lower
            or "render" in content_lower
            or "format" in content_lower
            or "print" in content_lower
            or "report" in content_lower
        )
        assert has_report, "report namespace missing output generation logic"

    # === Functional Checks ===

    def test_all_clj_files_have_valid_syntax(self):
        """Verify all migration validator .clj files have balanced parens"""
        clj_files = []
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src")):
            for f in files:
                if "migration" in root.lower() and f.endswith(".clj"):
                    clj_files.append(os.path.join(root, f))
        assert len(clj_files) > 0, "No migration validator .clj files found"
        for cljf in clj_files:
            with open(cljf) as fh:
                content = fh.read()
            cleaned = re.sub(r'"[^"]*"', '', content)
            cleaned = re.sub(r';[^\n]*', '', cleaned)
            opens = cleaned.count('(') + cleaned.count('[') + cleaned.count('{')
            closes = cleaned.count(')') + cleaned.count(']') + cleaned.count('}')
            assert opens == closes, (
                f"Unbalanced delimiters in {cljf}: opens={opens}, closes={closes}"
            )

    def test_all_clj_files_have_ns_declarations(self):
        """Verify all .clj files start with proper ns declarations"""
        clj_files = []
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src")):
            for f in files:
                if "migration" in root.lower() and f.endswith(".clj"):
                    clj_files.append(os.path.join(root, f))
        for cljf in clj_files:
            with open(cljf) as fh:
                content = fh.read()
            assert "(ns " in content[:500], f"{cljf} missing (ns ...) declaration"

    def test_namespaces_reference_each_other(self):
        """Verify core namespace requires other migration sub-namespaces"""
        core_file = None
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src")):
            for f in files:
                if "core" in f.lower() and "migration" in root.lower() and f.endswith(".clj"):
                    core_file = os.path.join(root, f)
                    break
            if core_file:
                break
        if core_file is None:
            pytest.skip("core.clj not found")
        with open(core_file) as fh:
            content = fh.read()
        has_requires = (
            "schema" in content.lower()
            or "integrity" in content.lower()
            or "report" in content.lower()
        )
        assert has_requires, "core namespace does not reference other sub-namespaces"
