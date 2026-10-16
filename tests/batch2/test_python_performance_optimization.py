"""
Test skill: python-performance-optimization
Verify that the Agent implements a collapsed flame graph output format
for py-spy in Rust with module info, min-sample filtering,
exclusion patterns, top-N limiting, and CLI integration.
"""

import os
import re
import subprocess
import pytest


class TestPythonPerformanceOptimization:
    REPO_DIR = "/workspace/py-spy"

    # === File Path Checks ===

    def test_collapsed_rs_exists(self):
        """Verify flamegraph_collapsed.rs exists"""
        path = os.path.join(self.REPO_DIR, "src", "flamegraph_collapsed.rs")
        assert os.path.exists(path), (
            f"flamegraph_collapsed.rs not found at {path}"
        )

    def test_main_rs_exists(self):
        """Verify main.rs exists"""
        path = os.path.join(self.REPO_DIR, "src", "main.rs")
        assert os.path.exists(path), f"main.rs not found at {path}"

    # === Semantic Checks ===

    def test_collapsed_format_output(self):
        """Verify the collapsed format: semicolon-separated stacks with counts"""
        path = os.path.join(self.REPO_DIR, "src", "flamegraph_collapsed.rs")
        with open(path) as f:
            content = f.read()

        format_indicators = [
            ";", "count", "sample", "write", "format",
            "stack", "frame",
        ]
        found = [ind for ind in format_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should produce collapsed format output. Found: {found}"
        )

    def test_module_info_in_names(self):
        """Verify module information is included in function names"""
        path = os.path.join(self.REPO_DIR, "src", "flamegraph_collapsed.rs")
        with open(path) as f:
            content = f.read()

        module_indicators = [
            "module", "Module", "filename", "file_name",
            "path", "short_filename", "name",
        ]
        found = [ind for ind in module_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should include module info in frame names. Found: {found}"
        )

    def test_min_sample_filtering(self):
        """Verify minimum sample count filtering"""
        path = os.path.join(self.REPO_DIR, "src", "flamegraph_collapsed.rs")
        with open(path) as f:
            content = f.read()

        min_indicators = [
            "min", "minimum", "threshold", "filter",
            "min_count", "min_sample",
        ]
        found = [ind for ind in min_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should support min sample count filtering. Found: {found}"
        )

    def test_exclusion_patterns(self):
        """Verify exclusion pattern support"""
        path = os.path.join(self.REPO_DIR, "src", "flamegraph_collapsed.rs")
        with open(path) as f:
            content = f.read()

        exclude_indicators = [
            "exclude", "Exclude", "ignore", "filter",
            "pattern", "skip", "regex",
        ]
        found = [ind for ind in exclude_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should support exclusion patterns. Found: {found}"
        )

    def test_top_n_limiting(self):
        """Verify top-N stack limiting"""
        path = os.path.join(self.REPO_DIR, "src", "flamegraph_collapsed.rs")
        with open(path) as f:
            content = f.read()

        top_indicators = [
            "top", "limit", "max", "sort", "truncate",
            "Top", "Limit",
        ]
        found = [ind for ind in top_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should support top-N limiting. Found: {found}"
        )

    def test_main_rs_references_collapsed(self):
        """Verify main.rs integrates the collapsed flame graph module"""
        path = os.path.join(self.REPO_DIR, "src", "main.rs")
        with open(path) as f:
            content = f.read()

        ref_indicators = [
            "flamegraph_collapsed", "collapsed", "Collapsed",
        ]
        found = [ind for ind in ref_indicators if ind in content]
        assert len(found) >= 1, (
            f"main.rs should reference collapsed module. Found: {found}"
        )

    def test_cli_integration(self):
        """Verify CLI argument for collapsed output format"""
        path = os.path.join(self.REPO_DIR, "src", "main.rs")
        with open(path) as f:
            content = f.read()

        cli_indicators = [
            "collapsed", "Collapsed", "format", "output",
            "clap", "arg", "subcommand",
        ]
        found = [ind for ind in cli_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should integrate collapsed format into CLI. Found: {found}"
        )

    # === Functional Checks ===

    def test_collapsed_rs_rust_syntax(self):
        """Verify flamegraph_collapsed.rs looks like valid Rust"""
        path = os.path.join(self.REPO_DIR, "src", "flamegraph_collapsed.rs")
        with open(path) as f:
            content = f.read()

        rust_constructs = [
            "fn ", "pub ", "struct ", "use ", "impl ",
            "let ", "mod ", "trait ",
        ]
        found = [c for c in rust_constructs if c in content]
        assert len(found) >= 3, (
            f"Should be valid Rust code. Found: {found}"
        )

    def test_function_definitions(self):
        """Verify collapsed module defines Rust functions"""
        path = os.path.join(self.REPO_DIR, "src", "flamegraph_collapsed.rs")
        with open(path) as f:
            content = f.read()

        fn_defs = re.findall(r"\bfn\s+\w+", content)
        assert len(fn_defs) >= 2, (
            f"Should define at least 2 functions. Found: {fn_defs}"
        )

    def test_collapsed_rs_has_struct(self):
        """Verify a config or options struct is defined"""
        path = os.path.join(self.REPO_DIR, "src", "flamegraph_collapsed.rs")
        with open(path) as f:
            content = f.read()

        structs = re.findall(r"struct\s+\w+", content)
        assert len(structs) >= 1, (
            f"Should define at least 1 struct. Found: {structs}"
        )

    def test_mod_declaration_in_main(self):
        """Verify main.rs has mod declaration for collapsed module"""
        path = os.path.join(self.REPO_DIR, "src", "main.rs")
        with open(path) as f:
            content = f.read()

        mod_indicators = [
            "mod flamegraph_collapsed",
            "flamegraph_collapsed::",
        ]
        found = [ind for ind in mod_indicators if ind in content]
        assert len(found) >= 1, (
            f"main.rs should declare/use flamegraph_collapsed module. "
            f"Found: {found}"
        )
