"""Benchmark test for skill `samber-lo-functional` (variant ext9).

Verifies the agent-built **dependency topology validator** under
`examples/depgraph` of the `github.com/samber/lo` module.

The task (tasks/ext9/samber-lo-functional.md) asks for a new package
`examples/depgraph/depgraph.go` (package depgraph) exporting:

    type Node struct { Name string; DependsOn []string }
    type Layer []string
    func Layers(nodes []Node) ([]Layer, error)

with strict rules:
  - layer 0 = all targets with no dependencies; layer k = targets whose deps
    are all satisfied by layers 0..k-1 (transitive layering);
  - names within each Layer sorted ascending lexicographically;
  - duplicate Node.Name -> (nil, error);
  - DependsOn naming an undefined target (dangling) -> (nil, error);
  - any cycle, including a self-loop -> (nil, error);
  - duplicate DependsOn entries tolerated (no effect);
  - empty input -> empty non-nil []Layer, nil error;
  - Layers must not mutate caller input or any node's DependsOn slice.

The native acceptance command is:
    go test ./examples/depgraph/ -run TestLayers -count=1

Strategy for discriminative power: rather than trusting the agent's own
`depgraph_test.go`, most L2 cases write an INDEPENDENT Go test file
(`package depgraphdriver`) into a fresh sub-package directory under REPO_DIR
and run it with the native `go test` toolchain. Each driver imports
`github.com/samber/lo/examples/depgraph` and asserts on the real returned
`[]Layer` / error. A naive solution (ignores cycles, misses dangling/duplicate
detection, mis-layers transitive deps, leaves a layer unsorted, or mutates
input) fails these drivers.
"""

import os
import shutil
import subprocess
import uuid

import pytest

REPO_DIR_DEFAULT = "/workspace/lo"


class TestSamberLoFunctional:
    REPO_DIR = "/workspace/lo"

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def _repo(cls):
        return cls.REPO_DIR if os.path.isdir(cls.REPO_DIR) else REPO_DIR_DEFAULT

    @classmethod
    def _go_env(cls):
        env = dict(os.environ)
        env.setdefault("GOFLAGS", "-mod=mod")
        env.setdefault("GO111MODULE", "on")
        env.setdefault("CGO_ENABLED", "0")
        return env

    @classmethod
    def _run_go(cls, args, timeout=300, cwd=None):
        return subprocess.run(
            args,
            cwd=cwd or cls._repo(),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=cls._go_env(),
        )

    @classmethod
    def _make_driver_pkg(cls, body_go):
        """Create a fresh test-only sub-package under examples/ containing only a
        driver test that imports the real `depgraph` package. Returns the
        `go test ./<dir>/` relative path and the absolute dir for cleanup.
        """
        name = "depverify_" + uuid.uuid4().hex[:10]
        abs_dir = os.path.join(cls._repo(), "examples", name)
        os.makedirs(abs_dir, exist_ok=True)
        with open(os.path.join(abs_dir, "driver_test.go"), "w") as fh:
            fh.write(body_go)
        rel = "./examples/" + name + "/"
        return rel, abs_dir

    @classmethod
    def _run_driver(cls, body_go, run="TestDriver", timeout=300):
        rel, abs_dir = cls._make_driver_pkg(body_go)
        try:
            return cls._run_go(
                ["go", "test", rel, "-run", run, "-count=1", "-v"],
                timeout=timeout,
            )
        finally:
            shutil.rmtree(abs_dir, ignore_errors=True)

    # Common Go preamble for drivers: import the real package + helpers.
    _IMPORT = (
        "package depgraphdriver\n\n"
        "import (\n"
        '\t"testing"\n\n'
        '\tdepgraph "github.com/samber/lo/examples/depgraph"\n'
        ")\n\n"
        # equalLayer: compare a Layer to expected names in order.
        "func equalLayer(got depgraph.Layer, want []string) bool {\n"
        "\tif len(got) != len(want) {\n"
        "\t\treturn false\n"
        "\t}\n"
        "\tfor i := range got {\n"
        "\t\tif got[i] != want[i] {\n"
        "\t\t\treturn false\n"
        "\t\t}\n"
        "\t}\n"
        "\treturn true\n"
        "}\n\n"
    )

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_depgraph_go_exists(self):
        """L1: examples/depgraph/depgraph.go exists and declares package depgraph."""
        p = os.path.join(self._repo(), "examples", "depgraph", "depgraph.go")
        assert os.path.isfile(p), "examples/depgraph/depgraph.go is missing"
        with open(p) as fh:
            head = fh.read(4000)
        assert "package depgraph" in head, "depgraph.go must declare `package depgraph`"

    def test_depgraph_test_go_exists(self):
        """L1: examples/depgraph/depgraph_test.go exists (agent's own table-driven test)."""
        p = os.path.join(self._repo(), "examples", "depgraph", "depgraph_test.go")
        assert os.path.isfile(p), "examples/depgraph/depgraph_test.go is missing"
        with open(p) as fh:
            head = fh.read(4000)
        assert "package depgraph" in head, "depgraph_test.go must declare `package depgraph`"

    def test_package_compiles(self):
        """L1: the new package compiles via `go build`."""
        res = self._run_go(["go", "build", "./examples/depgraph/"], timeout=300)
        assert res.returncode == 0, (
            "package github.com/samber/lo/examples/depgraph failed to build:\n"
            + res.stdout + res.stderr
        )

    def test_agents_own_tests_pass(self):
        """L1/L2: the exact native acceptance command passes.

        `go test ./examples/depgraph/ -run TestLayers -count=1`
        """
        res = self._run_go(
            ["go", "test", "./examples/depgraph/", "-run", "TestLayers", "-count=1"],
            timeout=300,
        )
        assert res.returncode == 0, (
            "acceptance command failed:\n" + res.stdout + res.stderr
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against the real Layers()
    # ------------------------------------------------------------------ #
    def test_linear_chain_layering(self):
        """L2: chain a<-b<-c yields three layers [a],[b],[c] in order."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// b depends on a, c depends on b. Order shuffled to defeat insertion-order impls.
	nodes := []depgraph.Node{
		{Name: "c", DependsOn: []string{"b"}},
		{Name: "a"},
		{Name: "b", DependsOn: []string{"a"}},
	}
	layers, err := depgraph.Layers(nodes)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(layers) != 3 {
		t.Fatalf("want 3 layers, got %d: %+v", len(layers), layers)
	}
	if !equalLayer(layers[0], []string{"a"}) {
		t.Fatalf("layer0 want [a] got %v", layers[0])
	}
	if !equalLayer(layers[1], []string{"b"}) {
		t.Fatalf("layer1 want [b] got %v", layers[1])
	}
	if !equalLayer(layers[2], []string{"c"}) {
		t.Fatalf("layer2 want [c] got %v", layers[2])
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_independent_roots_layer0_sorted(self):
        """L2: two independent roots both land in layer 0, sorted ascending."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// Insert "z" before "a" so an unsorted impl would emit [z a].
	nodes := []depgraph.Node{
		{Name: "z"},
		{Name: "a"},
	}
	layers, err := depgraph.Layers(nodes)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(layers) != 1 {
		t.Fatalf("want 1 layer, got %d: %+v", len(layers), layers)
	}
	if !equalLayer(layers[0], []string{"a", "z"}) {
		t.Fatalf("layer0 want [a z] (sorted) got %v", layers[0])
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_diamond_transitive_layering(self):
        """L2: diamond a<-{b,c}<-d places d in layer 2, not layer 1.

        A naive impl that only checks 'all deps defined' (ignoring depth) would
        wrongly put d in layer 1. d must wait for b and c (layer 1).
        """
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	nodes := []depgraph.Node{
		{Name: "a"},
		{Name: "b", DependsOn: []string{"a"}},
		{Name: "c", DependsOn: []string{"a"}},
		{Name: "d", DependsOn: []string{"b", "c"}},
	}
	layers, err := depgraph.Layers(nodes)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(layers) != 3 {
		t.Fatalf("want 3 layers, got %d: %+v", len(layers), layers)
	}
	if !equalLayer(layers[0], []string{"a"}) {
		t.Fatalf("layer0 want [a] got %v", layers[0])
	}
	if !equalLayer(layers[1], []string{"b", "c"}) {
		t.Fatalf("layer1 want [b c] got %v", layers[1])
	}
	if !equalLayer(layers[2], []string{"d"}) {
		t.Fatalf("layer2 want [d] got %v", layers[2])
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_duplicate_name_error(self):
        """L2: two nodes with the same Name return a non-nil error and nil layers."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	nodes := []depgraph.Node{
		{Name: "a"},
		{Name: "a"},
		{Name: "b", DependsOn: []string{"a"}},
	}
	layers, err := depgraph.Layers(nodes)
	if err == nil {
		t.Fatalf("want error on duplicate node name, got nil (layers=%+v)", layers)
	}
	if layers != nil {
		t.Fatalf("layers must be nil on error, got %+v", layers)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_dangling_dependency_error(self):
        """L2: DependsOn naming an undefined target returns a non-nil error."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	nodes := []depgraph.Node{
		{Name: "a", DependsOn: []string{"ghost"}}, // ghost not defined
		{Name: "b"},
	}
	layers, err := depgraph.Layers(nodes)
	if err == nil {
		t.Fatalf("want error on dangling dependency, got nil (layers=%+v)", layers)
	}
	if layers != nil {
		t.Fatalf("layers must be nil on error, got %+v", layers)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_cycle_error(self):
        """L2: a multi-node cycle a<->b returns a non-nil error and nil layers.

        A naive layered/topo impl that loops a bounded number of times instead
        of detecting unsatisfiable nodes must not silently succeed.
        """
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	nodes := []depgraph.Node{
		{Name: "a", DependsOn: []string{"b"}},
		{Name: "b", DependsOn: []string{"a"}},
	}
	layers, err := depgraph.Layers(nodes)
	if err == nil {
		t.Fatalf("want error on cycle a<->b, got nil (layers=%+v)", layers)
	}
	if layers != nil {
		t.Fatalf("layers must be nil on error, got %+v", layers)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_self_loop_is_cycle_error(self):
        """L2: a target depending on itself is a cycle -> non-nil error."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	nodes := []depgraph.Node{
		{Name: "a", DependsOn: []string{"a"}},
		{Name: "b"},
	}
	layers, err := depgraph.Layers(nodes)
	if err == nil {
		t.Fatalf("want error on self-loop, got nil (layers=%+v)", layers)
	}
	if layers != nil {
		t.Fatalf("layers must be nil on error, got %+v", layers)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_duplicate_dependency_tolerated(self):
        """L2: duplicate entries in a DependsOn list have no extra effect.

        b lists "a" twice; result must be identical to listing it once:
        layer0=[a], layer1=[b].
        """
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	nodes := []depgraph.Node{
		{Name: "a"},
		{Name: "b", DependsOn: []string{"a", "a", "a"}},
	}
	layers, err := depgraph.Layers(nodes)
	if err != nil {
		t.Fatalf("duplicate dep must be tolerated, got error: %v", err)
	}
	if len(layers) != 2 {
		t.Fatalf("want 2 layers, got %d: %+v", len(layers), layers)
	}
	if !equalLayer(layers[0], []string{"a"}) {
		t.Fatalf("layer0 want [a] got %v", layers[0])
	}
	if !equalLayer(layers[1], []string{"b"}) {
		t.Fatalf("layer1 want [b] got %v", layers[1])
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_empty_input_nonnil_layers(self):
        """L2: empty input -> empty non-nil []Layer and a nil error."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	layers, err := depgraph.Layers([]depgraph.Node{})
	if err != nil {
		t.Fatalf("empty input must not error, got %v", err)
	}
	if layers == nil {
		t.Fatalf("layers must be non-nil for empty input")
	}
	if len(layers) != 0 {
		t.Fatalf("layers must be empty for empty input, got %+v", layers)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_input_not_mutated(self):
        """L2: Layers must not mutate/reorder the caller's input slice or any
        node's DependsOn slice (e.g. via in-place sort/dedup)."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	nodes := []depgraph.Node{
		{Name: "d", DependsOn: []string{"b", "a", "a"}}, // unsorted + dup on purpose
		{Name: "a"},
		{Name: "b", DependsOn: []string{"a"}},
	}
	// snapshot node order and the exact DependsOn contents of node "d".
	wantOrder := []string{"d", "a", "b"}
	wantDDeps := []string{"b", "a", "a"}

	_, err := depgraph.Layers(nodes)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for i := range nodes {
		if nodes[i].Name != wantOrder[i] {
			t.Fatalf("input node order mutated at %d: got %q want %q",
				i, nodes[i].Name, wantOrder[i])
		}
	}
	d := nodes[0]
	if len(d.DependsOn) != len(wantDDeps) {
		t.Fatalf("node d DependsOn length changed: got %v want %v", d.DependsOn, wantDDeps)
	}
	for i := range d.DependsOn {
		if d.DependsOn[i] != wantDDeps[i] {
			t.Fatalf("node d DependsOn mutated at %d: got %v want %v", i, d.DependsOn, wantDDeps)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_combined_multilayer_sorted(self):
        """L2: end-to-end graph exercising transitive depth + intra-layer sort.

        Layout:
            layer0: a, x   (no deps)
            layer1: b (a), y (x)
            layer2: c (b), m (a,y)   -> m needs y (layer1) so depth 2
            layer3: d (c, m)
        Each layer must be sorted ascending and depth-correct.
        """
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	nodes := []depgraph.Node{
		{Name: "d", DependsOn: []string{"c", "m"}},
		{Name: "m", DependsOn: []string{"a", "y"}},
		{Name: "c", DependsOn: []string{"b"}},
		{Name: "b", DependsOn: []string{"a"}},
		{Name: "y", DependsOn: []string{"x"}},
		{Name: "a"},
		{Name: "x"},
	}
	layers, err := depgraph.Layers(nodes)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(layers) != 4 {
		t.Fatalf("want 4 layers, got %d: %+v", len(layers), layers)
	}
	if !equalLayer(layers[0], []string{"a", "x"}) {
		t.Fatalf("layer0 want [a x] got %v", layers[0])
	}
	if !equalLayer(layers[1], []string{"b", "y"}) {
		t.Fatalf("layer1 want [b y] got %v", layers[1])
	}
	if !equalLayer(layers[2], []string{"c", "m"}) {
		t.Fatalf("layer2 want [c m] got %v", layers[2])
	}
	if !equalLayer(layers[3], []string{"d"}) {
		t.Fatalf("layer3 want [d] got %v", layers[3])
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v", "--tb=short"]))
