"""
Tests for skill: distributed-tracing
Repo: open-telemetry/opentelemetry-collector
Image: zhangyiiiiii/swe-skills-bench-golang
Task: Implement a distributed tracing pipeline with OTel Collector config,
      Docker Compose, and instrumented Python services.
"""

import os
import re

import pytest
import yaml

REPO_DIR = "/workspace/opentelemetry-collector"
DEMO_DIR = os.path.join(REPO_DIR, "examples", "tracing-demo")

COLLECTOR_CONFIG = os.path.join(DEMO_DIR, "collector", "otel-collector-config.yaml")
DOCKER_COMPOSE = os.path.join(DEMO_DIR, "docker-compose.yaml")
GATEWAY_APP = os.path.join(DEMO_DIR, "services", "gateway", "app.py")
USER_APP = os.path.join(DEMO_DIR, "services", "user", "app.py")
ORDER_APP = os.path.join(DEMO_DIR, "services", "order", "app.py")
TRACING_CONFIG = os.path.join(DEMO_DIR, "services", "tracing_config.py")


def _load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required tracing demo files exist."""

    def test_collector_config_exists(self):
        assert os.path.isfile(COLLECTOR_CONFIG), f"Missing {COLLECTOR_CONFIG}"

    def test_docker_compose_exists(self):
        assert os.path.isfile(DOCKER_COMPOSE), f"Missing {DOCKER_COMPOSE}"

    def test_gateway_app_exists(self):
        assert os.path.isfile(GATEWAY_APP), f"Missing {GATEWAY_APP}"

    def test_user_app_exists(self):
        assert os.path.isfile(USER_APP), f"Missing {USER_APP}"

    def test_order_app_exists(self):
        assert os.path.isfile(ORDER_APP), f"Missing {ORDER_APP}"

    def test_tracing_config_exists(self):
        assert os.path.isfile(TRACING_CONFIG), f"Missing {TRACING_CONFIG}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticCollectorConfig:
    """Verify OTel Collector configuration structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(COLLECTOR_CONFIG)

    def test_receivers_section(self):
        assert "receivers" in self.cfg, "Collector config must have receivers"

    def test_otlp_receiver(self):
        receivers = self.cfg.get("receivers", {})
        assert "otlp" in receivers, f"Expected otlp receiver; found {list(receivers.keys())}"

    def test_otlp_grpc_port(self):
        otlp = self.cfg["receivers"]["otlp"]
        protocols = otlp.get("protocols", {})
        grpc = protocols.get("grpc", {})
        endpoint = grpc.get("endpoint", "")
        assert "4317" in endpoint, f"OTLP gRPC should be on port 4317; got '{endpoint}'"

    def test_jaeger_receiver(self):
        receivers = self.cfg.get("receivers", {})
        assert "jaeger" in receivers, f"Expected jaeger receiver; found {list(receivers.keys())}"

    def test_processors_batch(self):
        processors = self.cfg.get("processors", {})
        assert "batch" in processors, f"Expected batch processor; found {list(processors.keys())}"

    def test_processors_memory_limiter(self):
        processors = self.cfg.get("processors", {})
        assert "memory_limiter" in processors, (
            f"Expected memory_limiter; found {list(processors.keys())}"
        )

    def test_processors_attributes(self):
        processors = self.cfg.get("processors", {})
        assert "attributes" in processors, (
            f"Expected attributes processor; found {list(processors.keys())}"
        )

    def test_exporters_jaeger(self):
        exporters = self.cfg.get("exporters", {})
        assert "jaeger" in exporters or "otlp" in exporters, (
            f"Expected jaeger exporter; found {list(exporters.keys())}"
        )

    def test_exporters_prometheus(self):
        exporters = self.cfg.get("exporters", {})
        assert "prometheus" in exporters, (
            f"Expected prometheus exporter; found {list(exporters.keys())}"
        )

    def test_service_pipelines(self):
        service = self.cfg.get("service", {})
        pipelines = service.get("pipelines", {})
        assert "traces" in pipelines, f"Expected traces pipeline; found {list(pipelines.keys())}"

    def test_traces_pipeline_receivers(self):
        pipelines = self.cfg["service"]["pipelines"]
        traces = pipelines.get("traces", {})
        receivers = traces.get("receivers", [])
        assert "otlp" in receivers, f"Traces receivers should include otlp; got {receivers}"

    def test_extensions(self):
        extensions = self.cfg.get("extensions", {})
        assert "health_check" in extensions, (
            f"Expected health_check extension; found {list(extensions.keys())}"
        )


class TestSemanticDockerCompose:
    """Verify Docker Compose services."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(DOCKER_COMPOSE)

    def test_jaeger_service(self):
        services = self.cfg.get("services", {})
        assert "jaeger" in services, f"Expected jaeger service; found {list(services.keys())}"

    def test_collector_service(self):
        services = self.cfg.get("services", {})
        found = any("collector" in k for k in services.keys())
        assert found, f"Expected otel-collector service; found {list(services.keys())}"

    def test_gateway_service(self):
        services = self.cfg.get("services", {})
        assert "gateway" in services, f"Expected gateway service; found {list(services.keys())}"

    def test_user_service(self):
        services = self.cfg.get("services", {})
        found = any("user" in k for k in services.keys())
        assert found, f"Expected user-service; found {list(services.keys())}"

    def test_order_service(self):
        services = self.cfg.get("services", {})
        found = any("order" in k for k in services.keys())
        assert found, f"Expected order-service; found {list(services.keys())}"

    def test_jaeger_ui_port(self):
        services = self.cfg["services"]
        jaeger = services.get("jaeger", {})
        ports = str(jaeger.get("ports", []))
        assert "16686" in ports, f"Jaeger UI should expose port 16686; got {ports}"


class TestSemanticTracingConfig:
    """Verify shared tracing configuration module."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(TRACING_CONFIG, "r", encoding="utf-8") as f:
            self.src = f.read()

    def test_init_tracing_function(self):
        assert "def init_tracing" in self.src, "Expected init_tracing function"

    def test_get_tracer_function(self):
        assert "def get_tracer" in self.src or "get_tracer" in self.src, (
            "Expected get_tracer function"
        )

    def test_otlp_exporter(self):
        assert "OTLPSpanExporter" in self.src or "otlp" in self.src.lower(), (
            "Should use OTLPSpanExporter"
        )

    def test_batch_span_processor(self):
        assert "BatchSpanProcessor" in self.src, "Should use BatchSpanProcessor"

    def test_trace_propagator(self):
        assert "TraceContext" in self.src or "propagat" in self.src.lower(), (
            "Should set up W3C TraceContext propagator"
        )


class TestSemanticServiceInstrumentation:
    """Verify service instrumentation patterns."""

    def _read(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_gateway_spans(self):
        src = self._read(GATEWAY_APP)
        assert "gateway" in src.lower() and "span" in src.lower(), (
            "Gateway should create spans"
        )

    def test_user_service_spans(self):
        src = self._read(USER_APP)
        assert "span" in src.lower(), "User service should create spans"

    def test_user_service_db_span(self):
        src = self._read(USER_APP)
        assert "db" in src.lower() or "query" in src.lower(), (
            "User service should create a db.query child span"
        )

    def test_order_service_spans(self):
        src = self._read(ORDER_APP)
        assert "span" in src.lower(), "Order service should create spans"

    def test_gateway_calls_user_service(self):
        src = self._read(GATEWAY_APP)
        assert "user" in src.lower() and ("http" in src.lower() or "request" in src.lower()), (
            "Gateway should call user service via HTTP"
        )

    def test_traceparent_propagation(self):
        src = self._read(GATEWAY_APP)
        assert "traceparent" in src.lower() or "inject" in src.lower() or "propagat" in src.lower(), (
            "Gateway should propagate trace context (traceparent header)"
        )


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalCollectorPipeline:
    """Functionally verify collector pipeline configuration."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(COLLECTOR_CONFIG)

    def test_batch_settings(self):
        batch = self.cfg["processors"]["batch"]
        assert batch.get("send_batch_size") == 512, (
            f"batch.send_batch_size should be 512; got {batch.get('send_batch_size')}"
        )
        timeout = batch.get("timeout", "")
        assert "5s" in str(timeout), f"batch.timeout should be 5s; got {timeout}"

    def test_memory_limiter_settings(self):
        ml = self.cfg["processors"]["memory_limiter"]
        limit = ml.get("limit_mib", 0)
        assert limit == 512, f"memory_limiter.limit_mib should be 512; got {limit}"

    def test_attributes_environment(self):
        attrs = self.cfg["processors"]["attributes"]
        actions = attrs.get("actions", [])
        env_found = False
        for a in actions:
            if a.get("key") == "environment" and a.get("value") == "demo":
                env_found = True
        assert env_found, "attributes processor should insert environment=demo"

    def test_traces_processor_order(self):
        pipelines = self.cfg["service"]["pipelines"]
        processors = pipelines["traces"].get("processors", [])
        assert len(processors) >= 3, (
            f"Traces pipeline should have at least 3 processors; got {processors}"
        )
        # memory_limiter should come first
        assert processors[0] == "memory_limiter", (
            f"First processor should be memory_limiter; got {processors[0]}"
        )


class TestFunctionalDockerComposeWiring:
    """Verify Docker Compose service dependencies and environment."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(DOCKER_COMPOSE)

    def test_gateway_depends_on_collector(self):
        gateway = self.cfg["services"].get("gateway", {})
        deps = gateway.get("depends_on", [])
        if isinstance(deps, dict):
            deps = list(deps.keys())
        assert any("collector" in d for d in deps), (
            f"Gateway should depend on otel-collector; deps={deps}"
        )

    def test_gateway_otlp_endpoint(self):
        gateway = self.cfg["services"].get("gateway", {})
        env = gateway.get("environment", {})
        if isinstance(env, list):
            env_str = str(env)
        else:
            env_str = str(env)
        assert "4317" in env_str or "OTLP" in env_str, (
            "Gateway should have OTEL_EXPORTER_OTLP_ENDPOINT pointing to collector:4317"
        )

    def test_collector_volume_mount(self):
        services = self.cfg["services"]
        collector = None
        for k, v in services.items():
            if "collector" in k:
                collector = v
                break
        assert collector, "otel-collector service not found"
        volumes = str(collector.get("volumes", []))
        assert "config" in volumes.lower() or "otel" in volumes.lower(), (
            "Collector should mount config file"
        )


class TestFunctionalServiceNameAttributes:
    """Verify each service sets its service name."""

    def _read(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_gateway_service_name(self):
        src = self._read(GATEWAY_APP)
        assert "gateway" in src, "Gateway should set service.name = gateway"

    def test_user_service_name(self):
        src = self._read(USER_APP)
        assert "user" in src, "User service should set service.name = user-service"

    def test_order_service_name(self):
        src = self._read(ORDER_APP)
        assert "order" in src, "Order service should set service.name = order-service"

    def test_all_yaml_valid(self):
        for dirpath, _, filenames in os.walk(DEMO_DIR):
            for fn in filenames:
                if fn.endswith(".yaml") or fn.endswith(".yml"):
                    fpath = os.path.join(dirpath, fn)
                    with open(fpath, "r", encoding="utf-8") as f:
                        doc = yaml.safe_load(f)
                    assert doc is not None, f"Failed to parse {fpath}"
