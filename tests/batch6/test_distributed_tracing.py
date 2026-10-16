"""
Test skill: distributed-tracing
Verify that the Agent implements distributed tracing for Python
microservices with shared tracing library, context propagation,
per-service instrumentation, Docker Compose, and K8s manifests.
"""

import os
import re
import ast
import pytest

try:
    import yaml
except ImportError:
    yaml = None


class TestDistributedTracing:
    REPO_DIR = "/workspace/opentelemetry-collector"

    # === File Path Checks ===

    def test_tracing_init_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "lib/tracing/__init__.py"))

    def test_tracing_middleware_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "lib/tracing/middleware.py"))

    def test_tracing_propagation_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "lib/tracing/propagation.py"))

    def test_service_tracing_setups_exist(self):
        for svc in ("api-gateway", "user-service", "order-service", "notification-service"):
            path = os.path.join(self.REPO_DIR, f"services/{svc}/tracing_setup.py")
            assert os.path.exists(path), f"Missing {svc}/tracing_setup.py"

    def test_docker_compose_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "docker-compose.tracing.yml"))

    def test_k8s_jaeger_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "k8s/tracing/jaeger.yaml"))

    def test_k8s_otel_collector_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "k8s/tracing/otel-collector.yaml"))

    # === Semantic Checks ===

    def test_init_tracer_function(self):
        """Tracing init should define init_tracer with OTLP exporter"""
        path = os.path.join(self.REPO_DIR, "lib/tracing/__init__.py")
        with open(path) as f:
            content = f.read()
        assert re.search(r"def\s+init_tracer", content), "Missing init_tracer function"
        assert "TracerProvider" in content, "Should configure TracerProvider"
        assert "BatchSpanProcessor" in content or "SpanProcessor" in content, (
            "Should use BatchSpanProcessor"
        )
        assert "OTLP" in content or "otlp" in content, "Should use OTLP exporter"

    def test_middleware_creates_spans(self):
        """TracingMiddleware should create per-request spans"""
        path = os.path.join(self.REPO_DIR, "lib/tracing/middleware.py")
        with open(path) as f:
            content = f.read()
        assert "TracingMiddleware" in content, "Missing TracingMiddleware class"
        assert "http.method" in content, "Should set http.method attribute"
        assert "http.status_code" in content, "Should set http.status_code"

    def test_propagation_injects_w3c(self):
        """Propagation should inject W3C traceparent headers"""
        path = os.path.join(self.REPO_DIR, "lib/tracing/propagation.py")
        with open(path) as f:
            content = f.read()
        assert "traceparent" in content or "inject" in content, (
            "Should inject W3C traceparent"
        )

    def test_api_gateway_instruments_fastapi_and_httpx(self):
        """API gateway should instrument FastAPI and httpx"""
        path = os.path.join(self.REPO_DIR, "services/api-gateway/tracing_setup.py")
        with open(path) as f:
            content = f.read()
        assert "FastAPI" in content or "fastapi" in content, "Should instrument FastAPI"
        assert "httpx" in content or "HTTPX" in content, "Should instrument httpx"

    def test_order_service_has_custom_spans(self):
        """Order service should create custom business spans"""
        path = os.path.join(self.REPO_DIR, "services/order-service/tracing_setup.py")
        with open(path) as f:
            content = f.read()
        assert "order" in content.lower(), "Should have order-related spans"

    def test_docker_compose_has_jaeger(self):
        """Docker compose should include Jaeger service"""
        path = os.path.join(self.REPO_DIR, "docker-compose.tracing.yml")
        with open(path) as f:
            content = f.read()
        assert "jaeger" in content.lower(), "Should include Jaeger service"
        assert "16686" in content, "Should expose Jaeger UI port"

    def test_docker_compose_has_otel_collector(self):
        """Docker compose should include OTel Collector"""
        path = os.path.join(self.REPO_DIR, "docker-compose.tracing.yml")
        with open(path) as f:
            content = f.read()
        assert "otel" in content.lower() or "collector" in content.lower(), (
            "Should include OTel Collector"
        )
        assert "4317" in content, "Should expose OTel gRPC port"

    def test_k8s_jaeger_uses_production_strategy(self):
        """K8s Jaeger should use production strategy with Elasticsearch"""
        path = os.path.join(self.REPO_DIR, "k8s/tracing/jaeger.yaml")
        with open(path) as f:
            content = f.read()
        assert "production" in content, "Should use production strategy"
        assert "elasticsearch" in content.lower(), "Should use Elasticsearch storage"

    # === Functional Checks ===

    def test_all_python_files_parse(self):
        """All Python files should parse without syntax errors"""
        dirs = ["lib/tracing"]
        for svc in ("api-gateway", "user-service", "order-service", "notification-service"):
            dirs.append(f"services/{svc}")
        for d in dirs:
            base = os.path.join(self.REPO_DIR, d)
            if not os.path.isdir(base):
                continue
            for root, _ds, files in os.walk(base):
                for fname in files:
                    if fname.endswith(".py"):
                        fp = os.path.join(root, fname)
                        with open(fp) as f:
                            src = f.read()
                        try:
                            ast.parse(src)
                        except SyntaxError as e:
                            pytest.fail(f"{fp} syntax error: {e}")

    def test_docker_compose_valid_yaml(self):
        """Docker compose file should be valid YAML"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        path = os.path.join(self.REPO_DIR, "docker-compose.tracing.yml")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "services" in data, "Docker compose should have services"

    def test_k8s_yamls_valid(self):
        """K8s YAML files should parse without errors"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        for f in ("jaeger.yaml", "otel-collector.yaml"):
            path = os.path.join(self.REPO_DIR, f"k8s/tracing/{f}")
            with open(path) as fh:
                try:
                    list(yaml.safe_load_all(fh))
                except yaml.YAMLError as e:
                    pytest.fail(f"{f} YAML error: {e}")
