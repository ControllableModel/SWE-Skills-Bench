"""Tests for the go-errors-oops skill task (variant ext10): "Build a Per-Layer
Error Annotation Module".

Verifies that the agent created a self-contained Go example module at
examples/pipeline that uses github.com/samber/oops to push a single failure up
through a fixed three-stage stack (storage -> domain -> api), where EACH stage
annotates the forwarded error so the final value records the full path.

Strategy
--------
L1 cases check the required deliverable files exist, are minimally well-formed,
and that go.work / go.mod wiring is present (module path, use directive).

L2 cases EXERCISE the agent's actual Process(recordID) function. Rather than
trusting the agent-authored pipeline_test.go, this file injects its own
independent Go driver test (oops_zz_bench_driver_test.go) into the module and
runs it with `go test`, deep-validating, for the failure path:
  * oops.AsOops(err) == true (single oops error returned),
  * deepest .Code() == "record_unreadable",
  * deepest .Domain() == "storage",
  * flattened .Context() contains BOTH "record_id" (from the storage layer,
    equal to the supplied recordID) AND "stage" == "domain" (from the domain
    layer) -> proves two DIFFERENT layers each contributed context,
  * len(.Layers()) >= 3  -> proves three distinct annotating stages,
and for the success path: Process("ok") returns nil cleanly even though it flows
through all three wrapping stages (no nil checks may break this).

A naive solution that produces the error at a single layer (no per-stage
annotation, fewer than three layers), that hardcodes record_id, or that adds
explicit nil checks breaking the clean success path, fails these tests.

Native acceptance command driven: go test ./examples/pipeline/...
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/oops"
MODULE_DIR = os.path.join(REPO_DIR, "examples", "pipeline")
PIPELINE_GO = os.path.join(MODULE_DIR, "pipeline.go")
PIPELINE_TEST_GO = os.path.join(MODULE_DIR, "pipeline_test.go")
MODULE_GO_MOD = os.path.join(MODULE_DIR, "go.mod")
GO_WORK = os.path.join(REPO_DIR, "go.work")

DRIVER_NAME = "oops_zz_bench_driver_test.go"
DRIVER_PATH = os.path.join(MODULE_DIR, DRIVER_NAME)

# Independent driver test. Package name is filled in at write time to match the
# agent's chosen package. It exercises Process(recordID) directly.
DRIVER_TEMPLATE = r'''package %(pkg)s

import (
	"fmt"
	"testing"

	"github.com/samber/oops"
)

func zzAsOops(t *testing.T, err error) oops.OopsError {
	t.Helper()
	if err == nil {
		t.Fatalf("expected non-nil error")
	}
	oe, ok := oops.AsOops(err)
	if !ok {
		t.Fatalf("error is not an oops error: %%v", err)
	}
	return oe
}

// Success path: Process("ok") MUST return nil cleanly even though the value
// flows through all three wrapping stages. A naive impl that adds explicit nil
// checks that break the clean success path, or that always produces an error,
// fails here.
func TestZZSuccessNil(t *testing.T) {
	if err := Process("ok"); err != nil {
		t.Fatalf("Process(\"ok\") = %%v, want nil", err)
	}
}

// Failure path: deepest code + deepest domain are surfaced from the storage
// stage, even though the value is wrapped twice more (domain, api).
func TestZZFailureCodeAndDomain(t *testing.T) {
	oe := zzAsOops(t, Process("missing"))
	if got := fmt.Sprint(oe.Code()); got != "record_unreadable" {
		t.Fatalf("Code() = %%q, want record_unreadable", got)
	}
	if got := oe.Domain(); got != "storage" {
		t.Fatalf("Domain() = %%q, want storage", got)
	}
}

// Flattened context must aggregate metadata from TWO DIFFERENT layers:
// record_id from the storage (deepest) stage AND stage==domain from the
// middle stage. A single-layer naive impl cannot satisfy both.
func TestZZContextFromTwoLayers(t *testing.T) {
	oe := zzAsOops(t, Process("missing"))
	ctx := oe.Context()

	rid, ok := ctx["record_id"]
	if !ok {
		t.Fatalf("Context() missing key record_id; got %%v", ctx)
	}
	if fmt.Sprint(rid) != "missing" {
		t.Fatalf("Context()[record_id] = %%v, want missing", rid)
	}

	stage, ok := ctx["stage"]
	if !ok {
		t.Fatalf("Context() missing key stage; got %%v", ctx)
	}
	if fmt.Sprint(stage) != "domain" {
		t.Fatalf("Context()[stage] = %%v, want domain", stage)
	}
}

// record_id must reflect the ACTUAL recordID, not a hardcoded constant.
func TestZZRecordIDNotHardcoded(t *testing.T) {
	o1 := zzAsOops(t, Process("alpha-123"))
	o2 := zzAsOops(t, Process("beta-456"))

	if fmt.Sprint(o1.Context()["record_id"]) != "alpha-123" {
		t.Fatalf("Context()[record_id] = %%v, want alpha-123", o1.Context()["record_id"])
	}
	if fmt.Sprint(o2.Context()["record_id"]) != "beta-456" {
		t.Fatalf("Context()[record_id] = %%v, want beta-456", o2.Context()["record_id"])
	}
	if fmt.Sprint(o1.Context()["record_id"]) == fmt.Sprint(o2.Context()["record_id"]) {
		t.Fatalf("record_id is hardcoded: identical across different inputs")
	}
	// Even with differing record_id, the deepest code/domain stay constant.
	if fmt.Sprint(o1.Code()) != "record_unreadable" || fmt.Sprint(o2.Code()) != "record_unreadable" {
		t.Fatalf("deepest code drifted across inputs: %%v / %%v", o1.Code(), o2.Code())
	}
	if o1.Domain() != "storage" || o2.Domain() != "storage" {
		t.Fatalf("deepest domain drifted across inputs: %%v / %%v", o1.Domain(), o2.Domain())
	}
}

// At least three distinct oops layers: storage + domain + api each annotated.
// A single-wrap naive impl has < 3 layers and fails.
func TestZZThreeLayers(t *testing.T) {
	oe := zzAsOops(t, Process("missing"))
	layers := oe.Layers()
	if len(layers) < 3 {
		t.Fatalf("len(Layers()) = %%d, want >= 3 (storage, domain, api)", len(layers))
	}
}

// Every non-ok recordID fails (storage originates a failure), but the
// distinguishing structured datum (record_id) tracks the input. Confirms the
// failure is not gated on a single magic value like "missing".
func TestZZAnyNonOkFails(t *testing.T) {
	for _, id := range []string{"missing", "x", "42", "deleted"} {
		oe := zzAsOops(t, Process(id))
		if fmt.Sprint(oe.Code()) != "record_unreadable" {
			t.Fatalf("Process(%%q) code = %%v, want record_unreadable", id, oe.Code())
		}
		if fmt.Sprint(oe.Context()["record_id"]) != id {
			t.Fatalf("Process(%%q) record_id = %%v, want %%q", id, oe.Context()["record_id"], id)
		}
	}
}
'''


def _run_go(args, timeout=600):
    env = dict(os.environ)
    env.setdefault("GOFLAGS", "")
    return subprocess.run(
        ["go"] + args,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _detect_package():
    """Read the package name the agent used in pipeline.go."""
    try:
        with open(PIPELINE_GO, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"\s*package\s+([A-Za-z_][A-Za-z0-9_]*)", line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return "pipeline"


@pytest.fixture(scope="module", autouse=True)
def _driver_lifecycle():
    """Install the independent Go driver test, then remove it on teardown."""
    pkg = "pipeline"
    if os.path.isfile(PIPELINE_GO):
        pkg = _detect_package()
    if os.path.isdir(MODULE_DIR):
        with open(DRIVER_PATH, "w", encoding="utf-8") as f:
            f.write(DRIVER_TEMPLATE % {"pkg": pkg})
    yield
    try:
        os.remove(DRIVER_PATH)
    except OSError:
        pass


class TestGoErrorsOops:
    REPO_DIR = "/workspace/oops"

    # ---------- L1: deliverables exist and are well-formed ----------

    def test_module_dir_exists(self):
        """L1: the examples/pipeline module directory was created."""
        assert os.path.isdir(MODULE_DIR), f"missing module dir {MODULE_DIR}"

    def test_pipeline_go_exists(self):
        """L1: pipeline.go exists, declares a package and a Process func."""
        assert os.path.isfile(PIPELINE_GO), "missing examples/pipeline/pipeline.go"
        with open(PIPELINE_GO, encoding="utf-8", errors="replace") as f:
            src = f.read()
        assert re.search(r"\bpackage\s+\w+", src), "no package clause in pipeline.go"
        assert re.search(r"func\s+Process\s*\(", src), "no Process function"

    def test_go_mod_declares_module(self):
        """L1: go.mod declares the exact module path and requires samber/oops."""
        assert os.path.isfile(MODULE_GO_MOD), "missing examples/pipeline/go.mod"
        with open(MODULE_GO_MOD, encoding="utf-8", errors="replace") as f:
            mod = f.read()
        assert "module github.com/samber/oops/examples/pipeline" in mod, mod
        assert "github.com/samber/oops" in mod

    def test_go_work_lists_module(self):
        """L1: go.work uses ./examples/pipeline so the in-repo lib resolves."""
        assert os.path.isfile(GO_WORK), "missing go.work"
        with open(GO_WORK, encoding="utf-8", errors="replace") as f:
            work = f.read()
        assert "./examples/pipeline" in work, "go.work does not use ./examples/pipeline"

    def test_module_compiles(self):
        """L1/L2: the new module builds against the in-repo library."""
        res = _run_go(["build", "./examples/pipeline/..."])
        assert res.returncode == 0, f"build failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"

    # ---------- L2: behavior, driven by the injected independent test ----------

    def _run_driver(self, run_filter):
        return _run_go(
            ["test", "-v", "-count=1", "-run", run_filter, "./examples/pipeline/..."]
        )

    def test_success_path_returns_nil(self):
        """L2: Process("ok") returns nil cleanly through all three wrapping stages."""
        res = self._run_driver("TestZZSuccessNil$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZSuccessNil" in res.stdout, (
            f"driver test did not run/pass:\n{res.stdout}\n{res.stderr}"
        )

    def test_failure_code_and_domain(self):
        """L2: failing record -> deepest Code()==record_unreadable, Domain()==storage."""
        res = self._run_driver("TestZZFailureCodeAndDomain$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_context_from_two_layers(self):
        """L2: flattened Context() carries record_id (storage) AND stage==domain (domain)."""
        res = self._run_driver("TestZZContextFromTwoLayers$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_record_id_not_hardcoded(self):
        """L2: record_id tracks the actual input; code/domain stay invariant."""
        res = self._run_driver("TestZZRecordIDNotHardcoded$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_three_distinct_layers(self):
        """L2: len(Layers()) >= 3 -> storage, domain, api each annotated."""
        res = self._run_driver("TestZZThreeLayers$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_any_non_ok_fails(self):
        """L2: every non-"ok" recordID fails with record_unreadable and tracked record_id."""
        res = self._run_driver("TestZZAnyNonOkFails$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_agent_native_suite_passes(self):
        """L2: the spec's native command `go test ./examples/pipeline/...` passes overall."""
        res = _run_go(["test", "-count=1", "./examples/pipeline/..."])
        assert res.returncode == 0, f"native suite failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"
