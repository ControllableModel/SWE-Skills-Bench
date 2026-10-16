"""
Test skill: prompt-engineering-patterns
Verify that the Agent creates FewShotSelector, ChainOfThoughtTemplate,
SelfConsistencyChecker, and template library for LangChain.
"""

import os
import subprocess
import ast
import re
import pytest


class TestPromptEngineeringPatterns:
    REPO_DIR = "/workspace/langchain"

    # === File Path Checks ===

    def test_prompt_pattern_files_exist(self):
        """Verify prompt engineering pattern files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("few_shot" in f.lower() or "chain_of_thought" in f.lower() or "prompt" in f.lower()):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        content = fh.read()
                    if "FewShot" in content or "ChainOfThought" in content:
                        found = True
                        break
            if found:
                break
        assert found, "Prompt engineering pattern files not found"

    # === Semantic Checks ===

    def test_few_shot_selector_defined(self):
        """Verify FewShotSelector class is defined"""
        content = self._find_content()
        assert "FewShotSelector" in content or "few_shot" in content.lower(), (
            "FewShotSelector not found"
        )

    def test_chain_of_thought_template_defined(self):
        """Verify ChainOfThoughtTemplate class is defined"""
        content = self._find_content()
        has_cot = (
            "ChainOfThought" in content
            or "chain_of_thought" in content.lower()
            or "CoT" in content
        )
        assert has_cot, "ChainOfThoughtTemplate not found"

    def test_self_consistency_checker_defined(self):
        """Verify SelfConsistencyChecker class is defined"""
        content = self._find_content()
        has_sc = (
            "SelfConsistency" in content
            or "self_consistency" in content.lower()
            or "consistency" in content.lower()
        )
        assert has_sc, "SelfConsistencyChecker not found"

    def test_template_library_exists(self):
        """Verify a template library/registry is defined"""
        content = self._find_content()
        has_lib = (
            "template" in content.lower()
            and ("library" in content.lower() or "registry" in content.lower() or "collection" in content.lower() or "dict" in content)
        )
        assert has_lib, "Template library not found"

    def test_few_shot_selector_has_selection_logic(self):
        """Verify FewShotSelector implements example selection logic"""
        content = self._find_content()
        has_select = (
            "select" in content.lower()
            or "similarity" in content.lower()
            or "relevance" in content.lower()
            or "choose" in content.lower()
        )
        assert has_select, "FewShotSelector missing selection logic"

    # === Functional Checks ===

    def test_python_files_parse(self):
        """Verify all prompt pattern files have valid syntax"""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("few_shot" in f.lower() or "chain_of_thought" in f.lower() or "consistency" in f.lower()):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        source = fh.read()
                    try:
                        ast.parse(source)
                    except SyntaxError as e:
                        pytest.fail(f"Syntax error in {fpath}: {e}")

    def test_pattern_classes_use_langchain_imports(self):
        """Verify pattern files import from langchain"""
        content = self._find_content()
        has_langchain = "langchain" in content or "from langchain" in content
        assert has_langchain, "Pattern files do not import from langchain"

    def test_chain_of_thought_has_reasoning_steps(self):
        """Verify CoT template includes reasoning step logic"""
        content = self._find_content()
        has_steps = (
            "step" in content.lower()
            or "reasoning" in content.lower()
            or "think" in content.lower()
            or "intermediate" in content.lower()
        )
        assert has_steps, "ChainOfThought missing reasoning step logic"

    def test_self_consistency_has_voting(self):
        """Verify SelfConsistencyChecker implements majority voting or aggregation"""
        content = self._find_content()
        has_voting = (
            "vote" in content.lower()
            or "majority" in content.lower()
            or "aggregate" in content.lower()
            or "consensus" in content.lower()
            or "most_common" in content.lower()
        )
        assert has_voting, "SelfConsistencyChecker missing voting/aggregation logic"

    def _find_content(self):
        """Helper to find prompt engineering pattern content"""
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            content = fh.read()
                        if any(kw in content for kw in ["FewShot", "ChainOfThought", "SelfConsistency"]):
                            all_content += content + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content
