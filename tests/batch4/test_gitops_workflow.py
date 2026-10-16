"""
Tests for skill: gitops-workflow
Repo: fluxcd/flux2
Image: zhangyiiiiii/swe-skills-bench-golang
Task: Implement GitOps application deployment manifests with multi-environment
      promotion for Flux CD using Kustomize overlays.
"""

import os
import re

import pytest
import yaml

REPO_DIR = "/workspace/flux2"
DEMO_DIR = os.path.join(REPO_DIR, "examples", "gitops-demo")

BASE_DIR = os.path.join(DEMO_DIR, "base")
DEV_DIR = os.path.join(DEMO_DIR, "overlays", "development")
STG_DIR = os.path.join(DEMO_DIR, "overlays", "staging")
PRD_DIR = os.path.join(DEMO_DIR, "overlays", "production")
FLUX_DIR = os.path.join(DEMO_DIR, "flux")

DEPLOYMENT_FILE = os.path.join(BASE_DIR, "deployment.yaml")
SERVICE_FILE = os.path.join(BASE_DIR, "service.yaml")
BASE_KUSTOMIZATION = os.path.join(BASE_DIR, "kustomization.yaml")
DEV_KUSTOMIZATION = os.path.join(DEV_DIR, "kustomization.yaml")
STG_KUSTOMIZATION = os.path.join(STG_DIR, "kustomization.yaml")
PRD_KUSTOMIZATION = os.path.join(PRD_DIR, "kustomization.yaml")
PDB_FILE = os.path.join(PRD_DIR, "pdb.yaml")
GITREPO_FILE = os.path.join(FLUX_DIR, "gitrepository.yaml")
KUSTOMIZATIONS_FILE = os.path.join(FLUX_DIR, "kustomizations.yaml")
IMAGE_UPDATE_FILE = os.path.join(FLUX_DIR, "image-update.yaml")


def _load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_yaml_all(path):
    with open(path, "r", encoding="utf-8") as f:
        return list(yaml.safe_load_all(f))


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required GitOps manifest files exist."""

    def test_base_deployment_exists(self):
        assert os.path.isfile(DEPLOYMENT_FILE), f"Missing {DEPLOYMENT_FILE}"

    def test_base_service_exists(self):
        assert os.path.isfile(SERVICE_FILE), f"Missing {SERVICE_FILE}"

    def test_base_kustomization_exists(self):
        assert os.path.isfile(BASE_KUSTOMIZATION), f"Missing {BASE_KUSTOMIZATION}"

    def test_dev_overlay_exists(self):
        assert os.path.isfile(DEV_KUSTOMIZATION), f"Missing {DEV_KUSTOMIZATION}"

    def test_staging_overlay_exists(self):
        assert os.path.isfile(STG_KUSTOMIZATION), f"Missing {STG_KUSTOMIZATION}"

    def test_production_overlay_exists(self):
        assert os.path.isfile(PRD_KUSTOMIZATION), f"Missing {PRD_KUSTOMIZATION}"

    def test_pdb_exists(self):
        assert os.path.isfile(PDB_FILE), f"Missing {PDB_FILE}"

    def test_flux_gitrepository_exists(self):
        assert os.path.isfile(GITREPO_FILE), f"Missing {GITREPO_FILE}"

    def test_flux_kustomizations_exists(self):
        assert os.path.isfile(KUSTOMIZATIONS_FILE), f"Missing {KUSTOMIZATIONS_FILE}"

    def test_flux_image_update_exists(self):
        assert os.path.isfile(IMAGE_UPDATE_FILE), f"Missing {IMAGE_UPDATE_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticBaseDeployment:
    """Verify base deployment manifest structure and content."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.doc = _load_yaml(DEPLOYMENT_FILE)

    def test_kind_is_deployment(self):
        assert self.doc["kind"] == "Deployment"

    def test_app_name_label(self):
        labels = self.doc["metadata"].get("labels", {})
        assert labels.get("app") == "gitops-demo", f"Expected app=gitops-demo; got {labels}"

    def test_container_image(self):
        containers = self.doc["spec"]["template"]["spec"]["containers"]
        images = [c["image"] for c in containers]
        assert any("ghcr.io/example/gitops-demo" in img for img in images), (
            f"Expected ghcr.io/example/gitops-demo image; got {images}"
        )

    def test_container_port(self):
        containers = self.doc["spec"]["template"]["spec"]["containers"]
        ports = [p["containerPort"] for c in containers for p in c.get("ports", [])]
        assert 8080 in ports, f"Expected container port 8080; got {ports}"

    def test_liveness_probe(self):
        containers = self.doc["spec"]["template"]["spec"]["containers"]
        for c in containers:
            probe = c.get("livenessProbe", {})
            http = probe.get("httpGet", {})
            if http.get("path") == "/healthz":
                return
        pytest.fail("Expected liveness probe at /healthz")

    def test_readiness_probe(self):
        containers = self.doc["spec"]["template"]["spec"]["containers"]
        for c in containers:
            probe = c.get("readinessProbe", {})
            http = probe.get("httpGet", {})
            if http.get("path") == "/readyz":
                return
        pytest.fail("Expected readiness probe at /readyz")

    def test_resource_requests(self):
        containers = self.doc["spec"]["template"]["spec"]["containers"]
        for c in containers:
            req = c.get("resources", {}).get("requests", {})
            if req.get("cpu") and req.get("memory"):
                return
        pytest.fail("Expected resource requests on containers")

    def test_part_of_label(self):
        labels = self.doc["spec"]["template"]["metadata"].get("labels", {})
        assert labels.get("app.kubernetes.io/part-of") == "demo", (
            f"Expected app.kubernetes.io/part-of=demo; got {labels}"
        )


class TestSemanticBaseService:
    """Verify base service manifest."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.doc = _load_yaml(SERVICE_FILE)

    def test_kind_is_service(self):
        assert self.doc["kind"] == "Service"

    def test_type_cluster_ip(self):
        stype = self.doc.get("spec", {}).get("type", "ClusterIP")
        assert stype == "ClusterIP", f"Expected ClusterIP; got {stype}"

    def test_port_80_target_8080(self):
        ports = self.doc["spec"]["ports"]
        for p in ports:
            if p.get("port") == 80 and p.get("targetPort") == 8080:
                return
        pytest.fail("Expected port 80 → targetPort 8080")


class TestSemanticBaseKustomization:
    """Verify base kustomization references deployment and service."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.doc = _load_yaml(BASE_KUSTOMIZATION)

    def test_resources_include_deployment(self):
        resources = self.doc.get("resources", [])
        assert any("deployment" in r for r in resources), (
            f"Expected deployment.yaml in resources; got {resources}"
        )

    def test_resources_include_service(self):
        resources = self.doc.get("resources", [])
        assert any("service" in r for r in resources), (
            f"Expected service.yaml in resources; got {resources}"
        )

    def test_configmap_generator(self):
        generators = self.doc.get("configMapGenerator", [])
        assert len(generators) > 0, "Expected configMapGenerator in base kustomization"


class TestSemanticOverlays:
    """Verify environment overlays have correct namespaces and overrides."""

    def test_dev_namespace(self):
        doc = _load_yaml(DEV_KUSTOMIZATION)
        ns = doc.get("namespace", "")
        assert "dev" in ns, f"Dev overlay namespace should contain 'dev'; got '{ns}'"

    def test_staging_namespace(self):
        doc = _load_yaml(STG_KUSTOMIZATION)
        ns = doc.get("namespace", "")
        assert "staging" in ns, f"Staging overlay namespace should contain 'staging'; got '{ns}'"

    def test_production_namespace(self):
        doc = _load_yaml(PRD_KUSTOMIZATION)
        ns = doc.get("namespace", "")
        assert "prod" in ns, f"Production overlay namespace should contain 'prod'; got '{ns}'"

    def test_dev_references_base(self):
        doc = _load_yaml(DEV_KUSTOMIZATION)
        resources = doc.get("resources", doc.get("bases", []))
        raw = yaml.dump(doc)
        assert "base" in raw.lower() or "../../base" in raw, (
            "Dev overlay must reference the base directory"
        )


class TestSemanticPDB:
    """Verify production PodDisruptionBudget."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.doc = _load_yaml(PDB_FILE)

    def test_kind_is_pdb(self):
        assert self.doc["kind"] == "PodDisruptionBudget"

    def test_min_available(self):
        spec = self.doc.get("spec", {})
        assert spec.get("minAvailable") == 2, (
            f"Expected minAvailable=2; got {spec.get('minAvailable')}"
        )


class TestSemanticFluxGitRepository:
    """Verify Flux GitRepository resource."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.doc = _load_yaml(GITREPO_FILE)

    def test_kind(self):
        assert self.doc["kind"] == "GitRepository"

    def test_url(self):
        url = self.doc["spec"].get("url", "")
        assert "gitops-demo" in url, f"Expected gitops-demo repo URL; got '{url}'"

    def test_branch(self):
        ref = self.doc["spec"].get("ref", {})
        assert ref.get("branch") == "main", f"Expected branch=main; got {ref}"

    def test_interval(self):
        interval = self.doc["spec"].get("interval", "")
        assert interval, "GitRepository must have an interval"


class TestSemanticFluxKustomizations:
    """Verify Flux Kustomization resources for all environments."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.docs = _load_yaml_all(KUSTOMIZATIONS_FILE)
        self.by_name = {}
        for d in self.docs:
            if d and d.get("kind") == "Kustomization":
                name = d["metadata"]["name"]
                self.by_name[name] = d

    def test_three_kustomizations(self):
        kustomizations = [d for d in self.docs if d and d.get("kind") == "Kustomization"]
        assert len(kustomizations) >= 3, (
            f"Expected 3 Flux Kustomization resources; found {len(kustomizations)}"
        )

    def test_prune_enabled(self):
        for name, doc in self.by_name.items():
            prune = doc["spec"].get("prune", False)
            assert prune is True, f"Kustomization '{name}' must have prune: true"

    def test_staging_depends_on_development(self):
        staging = None
        for name, doc in self.by_name.items():
            if "staging" in name.lower() or "stg" in name.lower():
                staging = doc
                break
        assert staging, "Missing staging Flux Kustomization"
        deps = [d.get("name", "") for d in staging["spec"].get("dependsOn", [])]
        assert any("dev" in d for d in deps), (
            f"Staging must dependOn development; found deps={deps}"
        )

    def test_production_depends_on_staging(self):
        production = None
        for name, doc in self.by_name.items():
            if "prod" in name.lower() or "prd" in name.lower():
                production = doc
                break
        assert production, "Missing production Flux Kustomization"
        deps = [d.get("name", "") for d in production["spec"].get("dependsOn", [])]
        assert any("stag" in d or "stg" in d for d in deps), (
            f"Production must dependOn staging; found deps={deps}"
        )

    def test_source_ref(self):
        for name, doc in self.by_name.items():
            src = doc["spec"].get("sourceRef", {})
            assert src.get("kind") == "GitRepository", (
                f"Kustomization '{name}' sourceRef must point to a GitRepository"
            )


class TestSemanticFluxImageUpdate:
    """Verify image update automation resources."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.docs = _load_yaml_all(IMAGE_UPDATE_FILE)

    def test_image_repository_present(self):
        kinds = [d["kind"] for d in self.docs if d]
        assert "ImageRepository" in kinds, f"Expected ImageRepository; found {kinds}"

    def test_image_policy_present(self):
        kinds = [d["kind"] for d in self.docs if d]
        assert "ImagePolicy" in kinds, f"Expected ImagePolicy; found {kinds}"

    def test_image_update_automation_present(self):
        kinds = [d["kind"] for d in self.docs if d]
        assert "ImageUpdateAutomation" in kinds, f"Expected ImageUpdateAutomation; found {kinds}"

    def test_image_repo_scans_correct_image(self):
        for d in self.docs:
            if d and d.get("kind") == "ImageRepository":
                img = d["spec"].get("image", "")
                assert "ghcr.io/example/gitops-demo" in img, (
                    f"ImageRepository should scan ghcr.io/example/gitops-demo; got '{img}'"
                )
                return
        pytest.fail("ImageRepository not found")

    def test_image_policy_semver(self):
        for d in self.docs:
            if d and d.get("kind") == "ImagePolicy":
                policy = d["spec"].get("policy", {})
                semver = policy.get("semver", {})
                rng = semver.get("range", "")
                assert "1.0.0" in rng, f"Expected semver range containing 1.0.0; got '{rng}'"
                return
        pytest.fail("ImagePolicy not found")


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalOverlayValues:
    """Functionally verify overlay-specific values in kustomization files."""

    def _read(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_dev_replicas_1(self):
        raw = self._read(DEV_KUSTOMIZATION)
        assert "1" in raw, "Dev overlay should configure 1 replica"

    def test_staging_replicas_2(self):
        raw = self._read(STG_KUSTOMIZATION)
        assert "2" in raw, "Staging overlay should configure 2 replicas"

    def test_production_replicas_3(self):
        raw = self._read(PRD_KUSTOMIZATION)
        assert "3" in raw, "Production overlay should configure 3 replicas"

    def test_dev_log_level_debug(self):
        raw = self._read(DEV_KUSTOMIZATION)
        assert "debug" in raw.lower(), "Dev overlay should set APP_LOG_LEVEL=debug"

    def test_staging_log_level_info(self):
        raw = self._read(STG_KUSTOMIZATION)
        assert "info" in raw.lower(), "Staging overlay should set APP_LOG_LEVEL=info"

    def test_production_log_level_warn(self):
        raw = self._read(PRD_KUSTOMIZATION)
        assert "warn" in raw.lower(), "Production overlay should set APP_LOG_LEVEL=warn"

    def test_production_pdb_referenced(self):
        raw = self._read(PRD_KUSTOMIZATION)
        assert "pdb" in raw.lower(), "Production overlay must reference the PDB file"


class TestFunctionalPromotionChain:
    """Verify the development → staging → production promotion dependency chain."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.docs = _load_yaml_all(KUSTOMIZATIONS_FILE)
        self.by_name = {}
        for d in self.docs:
            if d and d.get("kind") == "Kustomization":
                self.by_name[d["metadata"]["name"]] = d

    def test_dev_has_no_depends(self):
        dev = None
        for name, doc in self.by_name.items():
            if "dev" in name.lower():
                dev = doc
                break
        assert dev, "Missing dev Flux Kustomization"
        deps = dev["spec"].get("dependsOn", [])
        assert len(deps) == 0, f"Dev should have no dependencies; found {deps}"

    def test_intervals_increase(self):
        """Production interval should be longer than staging, which is longer than dev."""
        intervals = {}
        for name, doc in self.by_name.items():
            intervals[name] = doc["spec"].get("interval", "")

        def _minutes(iv):
            m = re.search(r"(\d+)", iv)
            return int(m.group(1)) if m else 0

        vals = sorted(intervals.items(), key=lambda x: _minutes(x[1]))
        assert len(vals) >= 3, f"Expected at least 3 Kustomizations; got {len(vals)}"
        minutes = [_minutes(v) for _, v in vals]
        assert minutes == sorted(minutes), (
            f"Intervals should increase: {dict(intervals)}"
        )

    def test_paths_point_to_overlays(self):
        for name, doc in self.by_name.items():
            path = doc["spec"].get("path", "")
            assert "overlays" in path or "overlay" in path, (
                f"Kustomization '{name}' path should reference overlays; got '{path}'"
            )


class TestFunctionalImageAutomation:
    """Verify image automation targets the production overlay."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.docs = _load_yaml_all(IMAGE_UPDATE_FILE)

    def test_update_targets_production(self):
        for d in self.docs:
            if d and d.get("kind") == "ImageUpdateAutomation":
                raw = yaml.dump(d)
                assert "production" in raw or "prod" in raw, (
                    "ImageUpdateAutomation should target the production overlay"
                )
                return
        pytest.fail("ImageUpdateAutomation not found")

    def test_update_uses_git_commit(self):
        for d in self.docs:
            if d and d.get("kind") == "ImageUpdateAutomation":
                git = d["spec"].get("git", d["spec"].get("update", {}))
                assert git, "ImageUpdateAutomation should have a git/update spec"
                return
        pytest.fail("ImageUpdateAutomation not found")

    def test_all_yaml_valid(self):
        """All YAML files in the demo directory must be parseable."""
        for dirpath, _, filenames in os.walk(DEMO_DIR):
            for fn in filenames:
                if fn.endswith(".yaml") or fn.endswith(".yml"):
                    fpath = os.path.join(dirpath, fn)
                    with open(fpath, "r", encoding="utf-8") as f:
                        docs = list(yaml.safe_load_all(f))
                    assert docs, f"Failed to parse {fpath}"
