"""
Test skill: distributed-tracing
Verify that the Agent creates a pipeline config generator for
OpenTelemetry Collector (Go).
"""

import os
import re
import subprocess
import pytest


class TestDistributedTracing:
    REPO_DIR = "/workspace/opentelemetry-collector"

    # === File Path Checks ===

    def test_pipeline_generator_files_exist(self):
        """Verify pipeline config generator files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".go") and ("pipeline" in f.lower() or "config" in f.lower() or "generator" in f.lower()):
                    found = True
                    break
            if found:
                break
        assert found, "Pipeline config generator files not found"

    # === Semantic Checks ===

    def test_receiver_config_defined(self):
        """Verify receiver configuration is defined"""
        content = self._collect_content()
        content_lower = content.lower()
        has_receiver = "receiver" in content_lower or "Receiver" in content
        assert has_receiver, "Receiver config not found"

    def test_processor_config_defined(self):
        """Verify processor configuration is defined"""
        content = self._collect_content()
        content_lower = content.lower()
        has_processor = "processor" in content_lower or "Processor" in content
        assert has_processor, "Processor config not found"

    def test_exporter_config_defined(self):
        """Verify exporter configuration is defined"""
        content = self._collect_content()
        content_lower = content.lower()
        has_exporter = "exporter" in content_lower or "Exporter" in content
        assert has_exporter, "Exporter config not found"

    def test_pipeline_struct_defined(self):
        """Verify pipeline struct or config is defined"""
        content = self._collect_content()
        has_pipeline = "Pipeline" in content or "pipeline" in content
        assert has_pipeline, "Pipeline struct not found"

    def test_otlp_support(self):
        """Verify OTLP protocol support"""
        content = self._collect_content()
        content_lower = content.lower()
        has_otlp = "otlp" in content_lower or "grpc" in content_lower or "http" in content_lower
        assert has_otlp, "OTLP protocol support not found"

    # === Functional Checks ===

    def test_go_files_have_package(self):
        """Verify Go files have proper package declarations"""
        go_files = self._find_go_files()
        assert len(go_files) > 0, "No pipeline generator Go files found"
        for gf in go_files:
            with open(gf) as fh:
                content = fh.read()
            assert "package " in content[:200], f"{gf} missing package declaration"

    def test_go_files_balanced_braces(self):
        """Verify Go files have balanced braces"""
        go_files = self._find_go_files()
        for gf in go_files:
            with open(gf) as fh:
                content = fh.read()
            cleaned = re.sub(r'"[^"]*"', '', content)
            cleaned = re.sub(r'`[^`]*`', '', cleaned)
            cleaned = re.sub(r'//[^\n]*', '', cleaned)
            cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
            opens = cleaned.count('{')
            closes = cleaned.count('}')
            assert opens == closes, f"Unbalanced braces in {gf}: {opens} vs {closes}"

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
            related = [
                line for line in result.stderr.splitlines()
                if any(kw in line.lower() for kw in ["pipeline", "config", "generator", "receiver", "processor", "exporter"])
            ]
            assert len(related) == 0, f"Build errors: {related[:5]}"

    def test_yaml_config_generation(self):
        """Verify YAML config generation capability"""
        content = self._collect_content()
        content_lower = content.lower()
        has_yaml = (
            "yaml" in content_lower
            or "marshal" in content_lower
            or "config" in content_lower
        )
        assert has_yaml, "YAML config generation not found"

    def _collect_content(self):
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".go"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            c = fh.read()
                        if any(kw in c for kw in ["Pipeline", "pipeline", "Receiver", "Processor", "Exporter", "Config"]):
                            all_content += c + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content

    def _find_go_files(self):
        go_files = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".go") and ("pipeline" in f.lower() or "config" in f.lower() or "generator" in f.lower()):
                    go_files.append(os.path.join(root, f))
        return go_files
