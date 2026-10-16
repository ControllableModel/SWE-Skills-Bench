"""
Test skill: similarity-search-patterns
Verify that the Agent implements hybrid search with RRF/Convex/Relative score fusion in Milvus (Go).
"""

import os
import re
import subprocess
import pytest


class TestSimilaritySearchPatterns:
    REPO_DIR = "/workspace/milvus"

    # === File Path Checks ===

    def test_hybrid_search_files_exist(self):
        """Verify hybrid search implementation files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".go") and ("hybrid" in f.lower() or "fusion" in f.lower()):
                    found = True
                    break
            if found:
                break
        assert found, "Hybrid search Go files not found"

    # === Semantic Checks ===

    def test_rrf_fusion_implemented(self):
        """Verify RRF (Reciprocal Rank Fusion) is implemented"""
        content = self._find_content()
        content_lower = content.lower()
        has_rrf = "rrf" in content_lower or "reciprocalrank" in content_lower or "reciprocal_rank" in content_lower
        assert has_rrf, "RRF (Reciprocal Rank Fusion) not found"

    def test_convex_fusion_implemented(self):
        """Verify Convex score fusion is implemented"""
        content = self._find_content()
        content_lower = content.lower()
        has_convex = "convex" in content_lower or "weighted" in content_lower
        assert has_convex, "Convex score fusion not found"

    def test_relative_score_fusion_implemented(self):
        """Verify Relative score fusion is implemented"""
        content = self._find_content()
        content_lower = content.lower()
        has_relative = "relative" in content_lower or "normalize" in content_lower
        assert has_relative, "Relative score fusion not found"

    def test_fusion_strategy_interface(self):
        """Verify a common interface/type for fusion strategies exists"""
        content = self._find_content()
        has_interface = (
            "interface" in content
            or "type " in content and "func" in content
            or "Fusion" in content
        )
        assert has_interface, "Fusion strategy interface not found"

    def test_search_handles_multiple_vectors(self):
        """Verify search implementation handles multiple vector fields"""
        content = self._find_content()
        content_lower = content.lower()
        has_multi = (
            "vector" in content_lower
            and ("multiple" in content_lower or "fields" in content_lower or "[]" in content)
        )
        assert has_multi, "Implementation doesn't handle multiple vector fields"

    # === Functional Checks ===

    def test_go_files_compile(self):
        """Verify Go files have no syntax errors"""
        go_files = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".go") and ("hybrid" in f.lower() or "fusion" in f.lower()):
                    go_files.append(os.path.join(root, f))
        assert len(go_files) > 0, "No Go files found to compile"
        for gf in go_files:
            result = subprocess.run(
                ["go", "vet", gf],
                cwd=self.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=120,
            )
            # go vet on individual files may fail without proper module context
            # Just check for obvious syntax issues
            if result.returncode != 0:
                assert "syntax error" not in result.stderr.lower(), (
                    f"Syntax error in {gf}: {result.stderr[:500]}"
                )

    def test_go_build(self):
        """Verify the project builds"""
        result = subprocess.run(
            ["go", "build", "./..."],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            # Check that fusion-related files aren't causing the errors
            fusion_errors = [
                line for line in result.stderr.splitlines()
                if "hybrid" in line.lower() or "fusion" in line.lower()
            ]
            assert len(fusion_errors) == 0, (
                f"Build errors in hybrid/fusion files: {fusion_errors[:5]}"
            )

    def test_go_files_have_package(self):
        """Verify Go files have proper package declarations"""
        go_files = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".go") and ("hybrid" in f.lower() or "fusion" in f.lower()):
                    go_files.append(os.path.join(root, f))
        for gf in go_files:
            with open(gf) as fh:
                content = fh.read()
            assert "package " in content[:200], f"{gf} missing package declaration"

    def test_go_tests_exist(self):
        """Verify test files for hybrid search exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith("_test.go") and ("hybrid" in f.lower() or "fusion" in f.lower()):
                    found = True
                    break
            if found:
                break
        # Tests may not be required, just check
        if not found:
            pytest.skip("No test files for hybrid search found (not required)")

    def _find_content(self):
        """Helper to find hybrid search content"""
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".go") and ("hybrid" in f.lower() or "fusion" in f.lower() or "search" in f.lower()):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            all_content += fh.read() + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content
