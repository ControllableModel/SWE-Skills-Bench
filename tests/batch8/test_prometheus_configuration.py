"""
Test skill: prometheus-configuration
Verify that the Agent correctly builds a Prometheus configuration generator
and validator with scrape configs, recording/alerting rules, relabeling,
and config validation.
"""

import os
import subprocess
import sys
import ast
import inspect
import pytest


class TestPrometheusConfiguration:
    REPO_DIR = "/workspace/prometheus"

    # === File Path Checks ===

    def test_config_generator_exists(self):
        """Verify that config_generator.py exists"""
        filepath = os.path.join(self.REPO_DIR, "documentation/examples/config_generator.py")
        assert os.path.exists(filepath), f"config_generator.py not found at {filepath}"

    def test_rule_generator_exists(self):
        """Verify that rule_generator.py exists"""
        filepath = os.path.join(self.REPO_DIR, "documentation/examples/rule_generator.py")
        assert os.path.exists(filepath), f"rule_generator.py not found at {filepath}"

    def test_relabel_engine_exists(self):
        """Verify that relabel_engine.py exists"""
        filepath = os.path.join(self.REPO_DIR, "documentation/examples/relabel_engine.py")
        assert os.path.exists(filepath), f"relabel_engine.py not found at {filepath}"

    def test_config_validator_exists(self):
        """Verify that config_validator.py exists"""
        filepath = os.path.join(self.REPO_DIR, "documentation/examples/config_validator.py")
        assert os.path.exists(filepath), f"config_validator.py not found at {filepath}"

    def test_all_modules_valid_python(self):
        """Verify all modules are valid Python syntax"""
        modules = [
            "documentation/examples/config_generator.py",
            "documentation/examples/rule_generator.py",
            "documentation/examples/relabel_engine.py",
            "documentation/examples/config_validator.py",
        ]
        for mod in modules:
            filepath = os.path.join(self.REPO_DIR, mod)
            if os.path.exists(filepath):
                with open(filepath) as f:
                    content = f.read()
                try:
                    ast.parse(content)
                except SyntaxError as e:
                    pytest.fail(f"{mod} has syntax errors: {e}")

    # === Semantic Checks ===

    def test_config_generator_class_exists(self):
        """Verify PrometheusConfigGenerator class is defined"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "documentation/examples"))
        try:
            from config_generator import PrometheusConfigGenerator
            assert inspect.isclass(PrometheusConfigGenerator), (
                "PrometheusConfigGenerator must be a class"
            )
        except ImportError as e:
            pytest.fail(f"Cannot import PrometheusConfigGenerator: {e}")
        finally:
            sys.path.pop(0)

    def test_rule_generator_has_required_methods(self):
        """Verify RuleGenerator has required methods"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "documentation/examples"))
        try:
            from rule_generator import RuleGenerator
            required_methods = [
                "recording_rule", "alerting_rule",
                "sli_recording_rules", "burn_rate_alerts",
                "rule_group", "to_yaml"
            ]
            for method in required_methods:
                assert hasattr(RuleGenerator, method) or hasattr(RuleGenerator(), method), (
                    f"RuleGenerator missing method '{method}'"
                )
        except ImportError as e:
            pytest.fail(f"Cannot import RuleGenerator: {e}")
        finally:
            sys.path.pop(0)

    def test_relabel_engine_has_required_methods(self):
        """Verify RelabelEngine has required methods"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "documentation/examples"))
        try:
            from relabel_engine import RelabelEngine
            required_methods = [
                "keep_by_label", "drop_by_label", "rename_label",
                "extract_from_label", "drop_metric", "kubernetes_pod_relabels"
            ]
            for method in required_methods:
                assert hasattr(RelabelEngine, method) or hasattr(RelabelEngine(), method), (
                    f"RelabelEngine missing method '{method}'"
                )
        except ImportError as e:
            pytest.fail(f"Cannot import RelabelEngine: {e}")
        finally:
            sys.path.pop(0)

    # === Functional Checks ===

    def test_config_generator_produces_valid_yaml(self):
        """Verify PrometheusConfigGenerator.to_yaml() produces valid YAML"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "documentation/examples"))
        try:
            import yaml
            from config_generator import PrometheusConfigGenerator
            gen = PrometheusConfigGenerator()
            gen.add_scrape_config("test-job", targets=["localhost:9090"])
            yaml_str = gen.to_yaml()
            data = yaml.safe_load(yaml_str)
            assert data is not None, "Generated YAML is empty"
            assert "scrape_configs" in data, "Generated config missing 'scrape_configs'"
        except ImportError as e:
            pytest.skip(f"Cannot import: {e}")
        finally:
            sys.path.pop(0)

    def test_config_generator_rejects_duplicate_job(self):
        """Verify PrometheusConfigGenerator raises ValueError for duplicate job names"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "documentation/examples"))
        try:
            from config_generator import PrometheusConfigGenerator
            gen = PrometheusConfigGenerator()
            gen.add_scrape_config("my-job", targets=["localhost:9090"])
            with pytest.raises(ValueError) as exc_info:
                gen.add_scrape_config("my-job", targets=["localhost:9091"])
            assert "Duplicate" in str(exc_info.value) or "duplicate" in str(exc_info.value), (
                f"Expected 'Duplicate job name' error, got: {exc_info.value}"
            )
        except ImportError as e:
            pytest.skip(f"Cannot import: {e}")
        finally:
            sys.path.pop(0)

    def test_sli_recording_rules_produces_4_rules(self):
        """Verify sli_recording_rules produces 4 multi-window recording rules"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "documentation/examples"))
        try:
            from rule_generator import RuleGenerator
            rg = RuleGenerator()
            rules = rg.sli_recording_rules("api", "http_errors_total", "http_requests_total")
            assert isinstance(rules, list), f"Expected list, got {type(rules)}"
            assert len(rules) == 4, f"Expected 4 recording rules, got {len(rules)}"
            # Verify windows are present
            windows = ["5m", "30m", "1h", "6h"]
            rule_strs = str(rules)
            for window in windows:
                assert window in rule_strs, (
                    f"Missing {window} window in SLI recording rules"
                )
        except ImportError as e:
            pytest.skip(f"Cannot import: {e}")
        finally:
            sys.path.pop(0)

    def test_burn_rate_alerts_produces_page_and_ticket(self):
        """Verify burn_rate_alerts produces page and ticket alerts with correct thresholds"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "documentation/examples"))
        try:
            from rule_generator import RuleGenerator
            rg = RuleGenerator()
            alerts = rg.burn_rate_alerts("api", 0.999)
            assert isinstance(alerts, list), f"Expected list, got {type(alerts)}"
            assert len(alerts) >= 2, f"Expected at least 2 alerts (page + ticket), got {len(alerts)}"

            # Check for severity labels
            severities = [a.get("labels", {}).get("severity", "") for a in alerts]
            assert "critical" in severities, "Missing page alert with severity 'critical'"
            assert "warning" in severities, "Missing ticket alert with severity 'warning'"
        except ImportError as e:
            pytest.skip(f"Cannot import: {e}")
        finally:
            sys.path.pop(0)

    def test_relabel_keep_by_label(self):
        """Verify RelabelEngine.keep_by_label produces correct relabel config"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "documentation/examples"))
        try:
            from relabel_engine import RelabelEngine
            engine = RelabelEngine()
            config = engine.keep_by_label("__meta_kubernetes_namespace", "production")
            assert isinstance(config, dict), f"Expected dict, got {type(config)}"
            assert config.get("action") == "keep", f"Expected action 'keep', got {config.get('action')}"
            assert "source_labels" in config, "Missing source_labels in relabel config"
            assert "regex" in config, "Missing regex in relabel config"
        except ImportError as e:
            pytest.skip(f"Cannot import: {e}")
        finally:
            sys.path.pop(0)

    def test_config_validator_catches_invalid_scheme(self):
        """Verify ConfigValidator catches invalid scheme in scrape config"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "documentation/examples"))
        try:
            from config_validator import ConfigValidator
            validator = ConfigValidator()
            config = {
                "scrape_configs": [{
                    "job_name": "test",
                    "scheme": "ftp",
                    "static_configs": [{"targets": ["localhost:9090"]}]
                }]
            }
            errors = validator.validate_config(config)
            assert isinstance(errors, list), f"Expected list of errors, got {type(errors)}"
            assert len(errors) > 0, "Validator should catch invalid scheme 'ftp'"
            error_str = str(errors).lower()
            assert "scheme" in error_str or "ftp" in error_str, (
                f"Expected error about invalid scheme, got: {errors}"
            )
        except ImportError as e:
            pytest.skip(f"Cannot import: {e}")
        finally:
            sys.path.pop(0)

    def test_config_validator_catches_missing_expr(self):
        """Verify ConfigValidator catches missing expr in rules"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "documentation/examples"))
        try:
            from config_validator import ConfigValidator
            validator = ConfigValidator()
            rule_file = {
                "groups": [{
                    "name": "test",
                    "rules": [{"record": "test_metric"}]
                }]
            }
            errors = validator.validate_rules(rule_file)
            assert isinstance(errors, list), f"Expected list of errors, got {type(errors)}"
            assert len(errors) > 0, "Validator should catch missing 'expr' in rule"
            error_str = str(errors).lower()
            assert "expr" in error_str, (
                f"Expected error about missing expr, got: {errors}"
            )
        except ImportError as e:
            pytest.skip(f"Cannot import: {e}")
        finally:
            sys.path.pop(0)
