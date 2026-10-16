"""Benchmark test for skill `samber-lo-functional` (variant ext4).

Verifies the agent-built CSV column projector under `examples/csvproj`
of the `github.com/samber/lo` module.

The task (tasks/ext4/samber-lo-functional.md) asks for a new package
`github.com/samber/lo/examples/csvproj` with:

    examples/csvproj/project.go       (package csvproj)
    examples/csvproj/project_test.go  (package csvproj, table-driven, stdlib only)

exporting:

    func Project(header []string, rows [][]string, selection []string) ([][]string, error)

Rules (re-derived from THIS doc, NOT ext1's sales-report task):
  * Output[0] is the projected header == exactly `selection`, in that order.
  * Each data row is projected to values at the columns named by `selection`,
    in selection order (reordering is meaningful, not header order).
  * Missing column in selection  -> (nil, non-nil error naming the column).
  * Duplicate column in selection -> (nil, non-nil error).
  * Ragged data row (len != len(header)) -> (nil, non-nil error).
  * Output has len(rows)+1 rows; each row has length len(selection).
  * Empty selection -> every output row is an empty NON-NIL []string.
  * Zero data rows + valid selection -> exactly one row (the header).
  * Project must not mutate header, rows, or any inner row slice.

Discriminative strategy: rather than trusting the agent's own
`project_test.go`, the L2 cases write an INDEPENDENT Go test file
(package `csvprojdriver`) into a fresh sub-package under
`examples/` and run it with the native `go test` toolchain. Each driver
imports `github.com/samber/lo/examples/csvproj` and asserts on the real
returned `[][]string` / error. A naive solution (projects by header order,
ignores missing/duplicate columns, mishandles empty selection, or mutates
input) fails these drivers.

Native acceptance command (driven verbatim in an L2 case):
    go test ./examples/csvproj/ -run TestProject -count=1
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
        """Create a fresh test-only sub-package dir under examples/ containing a
        single driver test that imports the real `csvproj` package. Returns the
        `go test ./...` relative path plus the absolute dir for cleanup."""
        name = "csvprojverify_" + uuid.uuid4().hex[:10]
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

    # Common Go preamble for drivers: import the real package + reflect/strings.
    _IMPORT = (
        'package csvprojdriver\n\n'
        'import (\n'
        '\t"reflect"\n'
        '\t"strings"\n'
        '\t"testing"\n\n'
        '\tcsvproj "github.com/samber/lo/examples/csvproj"\n'
        ')\n\n'
        '// silence unused imports if a particular driver omits one\n'
        'var _ = reflect.DeepEqual\n'
        'var _ = strings.Contains\n\n'
    )

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_project_go_exists(self):
        """L1: examples/csvproj/project.go exists and declares package csvproj."""
        p = os.path.join(self._repo(), "examples", "csvproj", "project.go")
        assert os.path.isfile(p), "examples/csvproj/project.go is missing"
        with open(p) as fh:
            head = fh.read(8000)
        assert "package csvproj" in head, "project.go must declare `package csvproj`"
        assert "func Project" in head, "project.go must export func Project"

    def test_project_test_go_exists(self):
        """L1: examples/csvproj/project_test.go exists (agent's own table-driven test)."""
        p = os.path.join(self._repo(), "examples", "csvproj", "project_test.go")
        assert os.path.isfile(p), "examples/csvproj/project_test.go is missing"
        with open(p) as fh:
            head = fh.read(8000)
        assert "package csvproj" in head, "project_test.go must declare `package csvproj`"

    def test_package_compiles(self):
        """L1: the new package compiles via `go build`."""
        res = self._run_go(["go", "build", "./examples/csvproj/"], timeout=300)
        assert res.returncode == 0, (
            "package github.com/samber/lo/examples/csvproj failed to build:\n"
            + res.stdout + res.stderr
        )

    def test_agents_own_tests_pass(self):
        """L1/L2: the exact native acceptance command passes.

        `go test ./examples/csvproj/ -run TestProject -count=1`
        """
        res = self._run_go(
            ["go", "test", "./examples/csvproj/", "-run", "TestProject", "-count=1"],
            timeout=300,
        )
        assert res.returncode == 0, (
            "acceptance command failed:\n" + res.stdout + res.stderr
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against real Project
    # ------------------------------------------------------------------ #
    def test_header_is_selection_in_order(self):
        """L2: output[0] equals `selection` verbatim, in selection order."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	header := []string{"id", "name", "age"}
	rows := [][]string{{"1", "alice", "30"}}
	sel := []string{"age", "id"}
	out, err := csvproj.Project(header, rows, sel)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(out) != 2 {
		t.Fatalf("want 2 output rows (header+1), got %d", len(out))
	}
	if !reflect.DeepEqual(out[0], []string{"age", "id"}) {
		t.Fatalf("header must equal selection in order, got %#v", out[0])
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_reorder_columns_by_selection(self):
        """L2: data values follow selection order, not header order.

        A naive projector that emits columns in header order would fail here.
        """
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	header := []string{"id", "name", "age"}
	rows := [][]string{
		{"1", "alice", "30"},
		{"2", "bob", "41"},
	}
	sel := []string{"age", "name"} // reversed/subset vs header order
	out, err := csvproj.Project(header, rows, sel)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	want := [][]string{
		{"age", "name"},
		{"30", "alice"},
		{"41", "bob"},
	}
	if !reflect.DeepEqual(out, want) {
		t.Fatalf("projection by selection order wrong:\n got %#v\nwant %#v", out, want)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_value_extraction_by_name(self):
        """L2: each projected value is the cell at the named column index."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	header := []string{"a", "b", "c", "d"}
	rows := [][]string{
		{"av", "bv", "cv", "dv"},
		{"a2", "b2", "c2", "d2"},
	}
	sel := []string{"d", "a", "c"}
	out, err := csvproj.Project(header, rows, sel)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	want := [][]string{
		{"d", "a", "c"},
		{"dv", "av", "cv"},
		{"d2", "a2", "c2"},
	}
	if !reflect.DeepEqual(out, want) {
		t.Fatalf("value extraction by name wrong:\n got %#v\nwant %#v", out, want)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_missing_column_errors(self):
        """L2: selection naming a column not in header -> (nil, non-nil error)."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	header := []string{"id", "name"}
	rows := [][]string{{"1", "alice"}}
	sel := []string{"id", "missingcol"}
	out, err := csvproj.Project(header, rows, sel)
	if err == nil {
		t.Fatalf("want non-nil error for missing column, got nil (out=%#v)", out)
	}
	if out != nil {
		t.Fatalf("want nil result on error, got %#v", out)
	}
	if !strings.Contains(err.Error(), "missingcol") {
		t.Fatalf("error should name the missing column, got %q", err.Error())
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_duplicate_selection_errors(self):
        """L2: a duplicate column name in selection -> (nil, non-nil error)."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	header := []string{"id", "name", "age"}
	rows := [][]string{{"1", "alice", "30"}}
	sel := []string{"id", "name", "id"} // duplicate "id"
	out, err := csvproj.Project(header, rows, sel)
	if err == nil {
		t.Fatalf("want non-nil error for duplicate selection, got nil (out=%#v)", out)
	}
	if out != nil {
		t.Fatalf("want nil result on duplicate-selection error, got %#v", out)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_ragged_row_errors(self):
        """L2: any data row whose length != len(header) -> (nil, non-nil error)."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	header := []string{"id", "name", "age"}
	rows := [][]string{
		{"1", "alice", "30"},
		{"2", "bob"}, // ragged: width 2 != 3
	}
	sel := []string{"id", "age"}
	out, err := csvproj.Project(header, rows, sel)
	if err == nil {
		t.Fatalf("want non-nil error for ragged row, got nil (out=%#v)", out)
	}
	if out != nil {
		t.Fatalf("want nil result on ragged-row error, got %#v", out)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_empty_selection_nonnil_empty_rows(self):
        """L2: empty selection -> each output row is an empty NON-NIL []string,
        with len(rows)+1 rows total."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	header := []string{"id", "name"}
	rows := [][]string{
		{"1", "alice"},
		{"2", "bob"},
	}
	sel := []string{}
	out, err := csvproj.Project(header, rows, sel)
	if err != nil {
		t.Fatalf("empty selection should not error, got %v", err)
	}
	if len(out) != 3 {
		t.Fatalf("want len(rows)+1 = 3 output rows, got %d", len(out))
	}
	for i, r := range out {
		if r == nil {
			t.Fatalf("output row %d must be non-nil empty slice, got nil", i)
		}
		if len(r) != 0 {
			t.Fatalf("output row %d must be empty (len 0), got len %d (%#v)", i, len(r), r)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_zero_rows_returns_only_header(self):
        """L2: zero data rows + valid selection -> exactly one row (the header)."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	header := []string{"id", "name", "age"}
	rows := [][]string{}
	sel := []string{"name", "id"}
	out, err := csvproj.Project(header, rows, sel)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(out) != 1 {
		t.Fatalf("zero data rows must yield exactly 1 row (header), got %d (%#v)", len(out), out)
	}
	if !reflect.DeepEqual(out[0], []string{"name", "id"}) {
		t.Fatalf("header row must equal selection, got %#v", out[0])
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_output_shape_widths(self):
        """L2: every output row has length len(selection) and there are len(rows)+1 rows."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	header := []string{"c0", "c1", "c2", "c3", "c4"}
	rows := [][]string{
		{"00", "01", "02", "03", "04"},
		{"10", "11", "12", "13", "14"},
		{"20", "21", "22", "23", "24"},
	}
	sel := []string{"c3", "c0"}
	out, err := csvproj.Project(header, rows, sel)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(out) != len(rows)+1 {
		t.Fatalf("want %d rows, got %d", len(rows)+1, len(out))
	}
	for i, r := range out {
		if len(r) != len(sel) {
			t.Fatalf("row %d width want %d got %d (%#v)", i, len(sel), len(r), r)
		}
	}
	// spot-check a projected value
	if out[2][0] != "13" || out[2][1] != "10" {
		t.Fatalf("row 2 projection wrong: got %#v", out[2])
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_input_not_mutated(self):
        """L2: Project must not mutate header, rows, or any inner row slice."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	header := []string{"id", "name", "age"}
	rows := [][]string{
		{"1", "alice", "30"},
		{"2", "bob", "41"},
	}
	sel := []string{"age", "id"}

	// deep snapshots
	hSnap := append([]string(nil), header...)
	rSnap := make([][]string, len(rows))
	for i := range rows {
		rSnap[i] = append([]string(nil), rows[i]...)
	}
	selSnap := append([]string(nil), sel...)

	out, err := csvproj.Project(header, rows, sel)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	_ = out

	if !reflect.DeepEqual(header, hSnap) {
		t.Fatalf("header mutated: got %#v want %#v", header, hSnap)
	}
	if !reflect.DeepEqual(sel, selSnap) {
		t.Fatalf("selection mutated: got %#v want %#v", sel, selSnap)
	}
	if len(rows) != len(rSnap) {
		t.Fatalf("rows length changed")
	}
	for i := range rows {
		if !reflect.DeepEqual(rows[i], rSnap[i]) {
			t.Fatalf("inner row %d mutated: got %#v want %#v", i, rows[i], rSnap[i])
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_output_rows_independent_of_input(self):
        """L2: mutating a returned row must not corrupt the source data, i.e.
        the projector copies values rather than aliasing inner slices."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	header := []string{"id", "name"}
	rows := [][]string{{"1", "alice"}}
	sel := []string{"name", "id"}
	out, err := csvproj.Project(header, rows, sel)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// out[1] = ["alice","1"]; mutate it and ensure source unchanged.
	out[1][0] = "MUTATED"
	if rows[0][1] != "alice" {
		t.Fatalf("mutating output corrupted source row: %#v", rows[0])
	}
	if header[1] != "name" {
		t.Fatalf("mutating output corrupted header: %#v", header)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_combined_realistic_projection(self):
        """L2: end-to-end scenario exercising reorder + subset + multi-row at once."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	header := []string{"sku", "name", "price", "qty", "region"}
	rows := [][]string{
		{"s1", "Widget", "9.99", "3", "West"},
		{"s2", "Gadget", "4.50", "7", "East"},
		{"s3", "Gizmo", "1.00", "0", "North"},
	}
	sel := []string{"region", "sku", "qty"} // reorder + drop name/price
	out, err := csvproj.Project(header, rows, sel)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	want := [][]string{
		{"region", "sku", "qty"},
		{"West", "s1", "3"},
		{"East", "s2", "7"},
		{"North", "s3", "0"},
	}
	if !reflect.DeepEqual(out, want) {
		t.Fatalf("combined projection wrong:\n got %#v\nwant %#v", out, want)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v", "--tb=short"]))
