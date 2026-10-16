"""
Test skill: prompt-engineering-patterns
Verify that the Agent builds a multi-stage prompt pipeline for SQL
generation with few-shot selection, chain-of-thought decomposition,
SQL validation, and injection detection.
"""

import os
import re
import ast
import json
import subprocess
import pytest


class TestPromptEngineeringPatterns:
    REPO_DIR = "/workspace/langchain"

    # === File Path Checks ===

    def test_templates_file_exists(self):
        path = os.path.join(self.REPO_DIR, "src/prompt_pipeline/templates.py")
        assert os.path.exists(path), f"templates.py not found at {path}"

    def test_few_shot_file_exists(self):
        path = os.path.join(self.REPO_DIR, "src/prompt_pipeline/few_shot.py")
        assert os.path.exists(path), f"few_shot.py not found at {path}"

    def test_pipeline_file_exists(self):
        path = os.path.join(self.REPO_DIR, "src/prompt_pipeline/pipeline.py")
        assert os.path.exists(path), f"pipeline.py not found at {path}"

    def test_validators_file_exists(self):
        path = os.path.join(self.REPO_DIR, "src/prompt_pipeline/validators.py")
        assert os.path.exists(path), f"validators.py not found at {path}"

    def test_few_shot_examples_exists(self):
        path = os.path.join(self.REPO_DIR, "data/few_shot_examples.jsonl")
        assert os.path.exists(path), f"few_shot_examples.jsonl not found at {path}"

    def test_schema_json_exists(self):
        path = os.path.join(self.REPO_DIR, "data/schema.json")
        assert os.path.exists(path), f"schema.json not found at {path}"

    # === Semantic Checks ===

    def test_schema_defines_five_tables(self):
        """Verify schema.json defines users, orders, products, order_items, categories"""
        path = os.path.join(self.REPO_DIR, "data/schema.json")
        with open(path, "r") as f:
            schema = json.load(f)

        if isinstance(schema, dict) and "tables" in schema:
            tables = schema["tables"]
            if isinstance(tables, list):
                table_names = [t.get("name", "") for t in tables]
            else:
                table_names = list(tables.keys())
        else:
            table_names = list(schema.keys()) if isinstance(schema, dict) else []

        expected = ["users", "orders", "products", "order_items", "categories"]
        for t in expected:
            assert t in table_names, f"Schema missing table: {t}. Found: {table_names}"

    def test_few_shot_has_15_examples(self):
        """Verify few_shot_examples.jsonl has 15 examples"""
        path = os.path.join(self.REPO_DIR, "data/few_shot_examples.jsonl")
        with open(path, "r") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]

        examples = []
        for line in lines:
            try:
                examples.append(json.loads(line))
            except json.JSONDecodeError:
                pass

        assert len(examples) >= 15, (
            f"Expected 15 few-shot examples, found {len(examples)}"
        )

    def test_few_shot_examples_have_required_fields(self):
        """Verify each example has input, sql, explanation"""
        path = os.path.join(self.REPO_DIR, "data/few_shot_examples.jsonl")
        with open(path, "r") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]

        for i, line in enumerate(lines[:15]):
            example = json.loads(line)
            assert "input" in example or "question" in example, (
                f"Example {i} missing input/question field"
            )
            assert "sql" in example, f"Example {i} missing sql field"

    def test_templates_have_render_method(self):
        """Verify template classes have render() method"""
        path = os.path.join(self.REPO_DIR, "src/prompt_pipeline/templates.py")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"def\s+render", content), (
            "Template classes must have a render() method"
        )

    def test_four_template_types_defined(self):
        """Verify all 4 template types are defined"""
        path = os.path.join(self.REPO_DIR, "src/prompt_pipeline/templates.py")
        with open(path, "r") as f:
            content = f.read()

        content_lower = content.lower()
        expected = ["schema", "decomposition", "generation", "verification"]
        found = [t for t in expected if t in content_lower]
        assert len(found) >= 3, (
            f"Templates should define 4 types. Found matching: {found}"
        )

    def test_few_shot_selector_uses_mmr(self):
        """Verify FewShotSelector uses MMR for diversity"""
        path = os.path.join(self.REPO_DIR, "src/prompt_pipeline/few_shot.py")
        with open(path, "r") as f:
            content = f.read()

        assert "FewShotSelector" in content, "Must define FewShotSelector class"
        has_mmr = (
            "mmr" in content.lower()
            or "diversity" in content
            or "diversity_weight" in content
        )
        assert has_mmr, "FewShotSelector should use MMR or diversity weighting"

    def test_validator_has_three_validation_functions(self):
        """Verify validators define syntax, schema, injection detection"""
        path = os.path.join(self.REPO_DIR, "src/prompt_pipeline/validators.py")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"def\s+validate_syntax", content), "Missing validate_syntax"
        assert re.search(r"def\s+validate_schema", content), "Missing validate_schema"
        assert re.search(r"def\s+detect_injection", content), "Missing detect_injection"

    def test_injection_detector_covers_dangerous_keywords(self):
        """Verify injection detector flags DROP, DELETE, INSERT, UPDATE, ALTER, UNION"""
        path = os.path.join(self.REPO_DIR, "src/prompt_pipeline/validators.py")
        with open(path, "r") as f:
            content = f.read()

        dangerous = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "UNION"]
        found = [kw for kw in dangerous if kw in content or kw.lower() in content]
        assert len(found) >= 4, (
            f"Injection detector should flag dangerous keywords. Found: {found}"
        )

    def test_pipeline_has_generate_method(self):
        """Verify SQLPromptPipeline has generate() method"""
        path = os.path.join(self.REPO_DIR, "src/prompt_pipeline/pipeline.py")
        with open(path, "r") as f:
            content = f.read()

        assert "SQLPromptPipeline" in content, "Must define SQLPromptPipeline class"
        assert re.search(r"def\s+generate", content), "Missing generate() method"

    def test_pipeline_has_max_correction_attempts(self):
        """Verify pipeline limits correction attempts to 2"""
        path = os.path.join(self.REPO_DIR, "src/prompt_pipeline/pipeline.py")
        with open(path, "r") as f:
            content = f.read()

        has_limit = "2" in content and ("attempt" in content.lower() or "retri" in content.lower())
        assert has_limit, "Pipeline should limit correction attempts to 2"

    # === Functional Checks ===

    def test_all_python_files_parse(self):
        """Verify all Python files parse without syntax errors"""
        files = [
            "src/prompt_pipeline/templates.py",
            "src/prompt_pipeline/few_shot.py",
            "src/prompt_pipeline/pipeline.py",
            "src/prompt_pipeline/validators.py",
        ]
        for filename in files:
            path = os.path.join(self.REPO_DIR, filename)
            with open(path, "r") as f:
                source = f.read()
            try:
                ast.parse(source)
            except SyntaxError as e:
                pytest.fail(f"{filename} has syntax error: {e}")

    def test_schema_json_is_valid(self):
        """Verify schema.json is valid JSON"""
        path = os.path.join(self.REPO_DIR, "data/schema.json")
        with open(path, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                pytest.fail(f"schema.json is invalid JSON: {e}")
        assert isinstance(data, dict), "schema.json should be a JSON object"

    def test_validators_import(self):
        """Verify validators module can be imported"""
        result = subprocess.run(
            ["python", "-c",
             "import sys; sys.path.insert(0, 'src'); "
             "from prompt_pipeline.validators import validate_syntax, detect_injection; "
             "print('OK')"],
            capture_output=True, text=True, timeout=30,
            cwd=self.REPO_DIR,
        )
        assert result.returncode == 0, (
            f"Failed to import validators:\n{result.stderr[:500]}"
        )
