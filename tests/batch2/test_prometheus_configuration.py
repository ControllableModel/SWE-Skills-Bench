"""
Test skill: prometheus-configuration
Verify that the Agent correctly creates a multi-job Prometheus scrape
configuration example with relabeling rules, service discovery, and
global settings.
"""

import os
import subprocess
import pytest


class TestPrometheusConfiguration:
    REPO_DIR = "/workspace/prometheus"

    @staticmethod
    def _load_yaml(path):
        try:
            import yaml
        except ImportError:
            subprocess.run(["pip", "install", "pyyaml"], capture_output=True, timeout=60)
            import yaml
        with open(path) as f:
            return yaml.safe_load(f)

    # === File Path Checks ===

    def test_multi_job_scrape_config_exists(self):
        """Verify multi_job_scrape.yml exists in documentation/examples/"""
        path = os.path.join(
            self.REPO_DIR, "documentation/examples/multi_job_scrape.yml"
        )
        assert os.path.exists(path), f"multi_job_scrape.yml not found at {path}"

    def test_test_fixture_config_exists(self):
        """Verify test fixture multi_job.good.yml exists"""
        path = os.path.join(self.REPO_DIR, "config/testdata/multi_job.good.yml")
        assert os.path.exists(path), f"multi_job.good.yml not found at {path}"

    def test_configs_are_valid_yaml(self):
        """Verify both config files are parseable YAML"""
        files = [
            "documentation/examples/multi_job_scrape.yml",
            "config/testdata/multi_job.good.yml",
        ]
        for rel_path in files:
            path = os.path.join(self.REPO_DIR, rel_path)
            if os.path.exists(path):
                config = self._load_yaml(path)
                assert config is not None, f"{rel_path} is empty or invalid YAML"
                assert isinstance(config, dict), f"{rel_path} root should be a mapping"

    # === Semantic Checks ===

    def test_config_has_global_settings(self):
        """Verify config defines global scrape_interval, evaluation_interval, and external_labels"""
        path = os.path.join(
            self.REPO_DIR, "documentation/examples/multi_job_scrape.yml"
        )
        config = self._load_yaml(path)

        global_config = config.get("global", {})
        assert "scrape_interval" in global_config, (
            "Global config should define 'scrape_interval'"
        )
        assert "evaluation_interval" in global_config, (
            "Global config should define 'evaluation_interval'"
        )
        assert "external_labels" in global_config, (
            "Global config should define 'external_labels'"
        )
        ext_labels = global_config["external_labels"]
        assert isinstance(ext_labels, dict) and len(ext_labels) >= 1, (
            f"external_labels should have at least one label. Got: {ext_labels}"
        )

    def test_config_has_at_least_three_scrape_jobs(self):
        """Verify config defines at least 3 distinct scrape jobs"""
        path = os.path.join(
            self.REPO_DIR, "documentation/examples/multi_job_scrape.yml"
        )
        config = self._load_yaml(path)

        scrape_configs = config.get("scrape_configs", [])
        assert len(scrape_configs) >= 3, (
            f"Config should have at least 3 scrape jobs. Found {len(scrape_configs)}"
        )

        # Verify jobs have distinct names
        job_names = [job.get("job_name", f"unnamed_{i}")
                     for i, job in enumerate(scrape_configs)]
        unique_names = set(job_names)
        assert len(unique_names) >= 3, (
            f"Jobs should have distinct names. Found: {job_names}"
        )

    def test_config_jobs_have_scrape_settings(self):
        """Verify each job has appropriate scrape_interval and metrics_path"""
        path = os.path.join(
            self.REPO_DIR, "documentation/examples/multi_job_scrape.yml"
        )
        config = self._load_yaml(path)

        scrape_configs = config.get("scrape_configs", [])
        jobs_with_settings = 0
        for job in scrape_configs:
            has_interval = "scrape_interval" in job
            has_path = "metrics_path" in job
            if has_interval or has_path:
                jobs_with_settings += 1

        assert jobs_with_settings >= 1, (
            "At least one job should have custom scrape_interval or metrics_path"
        )

    def test_config_has_relabeling_rules(self):
        """Verify at least one job has relabel_configs with multiple actions"""
        path = os.path.join(
            self.REPO_DIR, "documentation/examples/multi_job_scrape.yml"
        )
        config = self._load_yaml(path)

        scrape_configs = config.get("scrape_configs", [])
        relabel_actions = []
        for job in scrape_configs:
            relabel_configs = job.get("relabel_configs", [])
            for rule in relabel_configs:
                action = rule.get("action", "replace")
                relabel_actions.append(action)

        assert len(relabel_actions) >= 2, (
            f"At least one job should have relabel_configs with multiple rules. "
            f"Actions found: {relabel_actions}"
        )

        # Should demonstrate keep or drop for target filtering
        action_types = set(relabel_actions)
        has_filtering = "keep" in action_types or "drop" in action_types
        has_replacement = "replace" in action_types or "labelmap" in action_types
        assert has_filtering or has_replacement, (
            f"Relabeling should demonstrate filtering (keep/drop) or replacement. "
            f"Action types found: {action_types}"
        )

    def test_config_has_static_targets(self):
        """Verify at least one job uses static_configs"""
        path = os.path.join(
            self.REPO_DIR, "documentation/examples/multi_job_scrape.yml"
        )
        config = self._load_yaml(path)

        scrape_configs = config.get("scrape_configs", [])
        has_static = False
        for job in scrape_configs:
            if "static_configs" in job:
                has_static = True
                static = job["static_configs"]
                assert isinstance(static, list) and len(static) >= 1, (
                    f"static_configs should have at least one target group"
                )
                break

        assert has_static, "At least one job should use static_configs"

    def test_config_has_dynamic_service_discovery(self):
        """Verify at least one job uses a dynamic service discovery mechanism"""
        path = os.path.join(
            self.REPO_DIR, "documentation/examples/multi_job_scrape.yml"
        )
        config = self._load_yaml(path)

        scrape_configs = config.get("scrape_configs", [])
        sd_types = [
            "file_sd_configs", "dns_sd_configs", "kubernetes_sd_configs",
            "consul_sd_configs", "ec2_sd_configs", "gce_sd_configs",
            "azure_sd_configs", "http_sd_configs",
        ]

        found_sd = []
        for job in scrape_configs:
            for sd in sd_types:
                if sd in job:
                    found_sd.append(sd)

        assert len(found_sd) >= 1, (
            f"At least one job should use dynamic service discovery. "
            f"None of {sd_types} found in any job."
        )

    # === Functional Checks ===

    def test_config_passes_promtool_check(self):
        """Verify config passes promtool check-config if available"""
        path = os.path.join(
            self.REPO_DIR, "documentation/examples/multi_job_scrape.yml"
        )
        # Try to find promtool
        promtool = None
        for candidate in ["promtool", "./promtool", os.path.join(self.REPO_DIR, "promtool")]:
            check = subprocess.run(
                ["which", candidate] if not candidate.startswith((".", "/")) else ["test", "-f", candidate],
                capture_output=True, text=True, timeout=10,
            )
            if check.returncode == 0:
                promtool = candidate
                break

        if promtool is None:
            # Try to build promtool
            result = subprocess.run(
                ["go", "build", "-o", "/tmp/promtool", "./cmd/promtool"],
                cwd=self.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                promtool = "/tmp/promtool"
            else:
                pytest.skip("promtool not available and could not be built")

        result = subprocess.run(
            [promtool, "check", "config", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"promtool check-config failed: {result.stderr[:1000]}"
        )

    def test_test_fixture_is_valid_config(self):
        """Verify test fixture multi_job.good.yml has valid structure"""
        path = os.path.join(self.REPO_DIR, "config/testdata/multi_job.good.yml")
        config = self._load_yaml(path)

        assert "scrape_configs" in config or "global" in config, (
            f"Test fixture should have scrape_configs or global sections. "
            f"Keys: {list(config.keys())}"
        )

    def test_config_job_names_are_descriptive(self):
        """Verify job names are descriptive and not generic"""
        path = os.path.join(
            self.REPO_DIR, "documentation/examples/multi_job_scrape.yml"
        )
        config = self._load_yaml(path)

        scrape_configs = config.get("scrape_configs", [])
        for job in scrape_configs:
            name = job.get("job_name", "")
            assert len(name) >= 3, (
                f"Job name '{name}' is too short to be descriptive"
            )
            assert name not in ("job1", "job2", "job3", "test"), (
                f"Job name '{name}' is too generic"
            )
