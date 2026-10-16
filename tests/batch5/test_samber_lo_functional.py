"""Benchmark test for skill `samber-lo-functional` (variant ext5).

Verifies the agent-built **Tag Co-occurrence Counter** under
`examples/tagstats` of the `github.com/samber/lo` module.

The task asks for `examples/tagstats/tags.go` (package tagstats) exporting
`Document`, `Pair`, `Stats` and `func Compute(docs []Document, topN int) Stats`
with strict rules:

  * intra-document tag de-duplication (repeated tag within one doc counts once);
  * `TagCounts[tag]` = number of DISTINCT documents containing that tag;
  * pairs normalized so `A <= B`, counting documents whose distinct tag set
    contains BOTH A and B;
  * `TopPairs` sorted by Count descending, tie-broken by A then B ascending,
    truncated to `topN`; `topN <= 0` yields an empty (non-nil) slice;
  * empty input yields empty non-nil `TagCounts`/`TopPairs`;
  * `Compute` must not mutate the caller's input or any `Tags` slice.

Strategy for discriminative power: rather than trusting the agent's own
`tags_test.go`, the L2 cases write INDEPENDENT Go test files (package
`tagstatsdriver` in a fresh throwaway sub-package directory under
`examples/`) that import the real `github.com/samber/lo/examples/tagstats`
package and assert on the actual returned `Stats` struct. A naive solution
(double-counts repeated tags, emits pairs with `A > B`, skips the tie-break,
ignores `topN`, or mutates the input) fails these drivers.

Native acceptance command (driven verbatim in `test_acceptance_command`):
    go test ./examples/tagstats/ -run TestCompute -count=1
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
        # Keep module mode deterministic & avoid CGO/network where possible.
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
        """Create a fresh sub-package dir under examples/ containing only a
        driver test that imports the real `tagstats` package. Returns the
        relative path (for `go test ./<dir>/`) and absolute dir for cleanup.

        We place it inside the module tree (under examples/) and give it a
        unique name so it has no non-test source — go test allows a test-only
        package.
        """
        name = "tagstatsverify_" + uuid.uuid4().hex[:10]
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
            res = cls._run_go(
                ["go", "test", rel, "-run", run, "-count=1", "-v"],
                timeout=timeout,
            )
            return res
        finally:
            shutil.rmtree(abs_dir, ignore_errors=True)

    # Common Go preamble for drivers: import the real package + sort helper.
    _IMPORT = (
        'package tagstatsdriver\n\n'
        'import (\n'
        '\t"sort"\n'
        '\t"testing"\n\n'
        '\ttagstats "github.com/samber/lo/examples/tagstats"\n'
        ')\n\n'
        '// pairKey is a stable string form used only for set comparisons.\n'
        'func pairKey(p tagstats.Pair) string { return p.A + "|" + p.B }\n\n'
    )

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_tags_go_exists(self):
        """L1: examples/tagstats/tags.go exists and declares package tagstats."""
        p = os.path.join(self._repo(), "examples", "tagstats", "tags.go")
        assert os.path.isfile(p), "examples/tagstats/tags.go is missing"
        with open(p) as fh:
            head = fh.read(8000)
        assert "package tagstats" in head, "tags.go must declare `package tagstats`"
        # The three exported types and the entry point must be declared.
        for sym in ("Document", "Pair", "Stats", "func Compute"):
            assert sym in head, "tags.go must declare %s" % sym

    def test_tags_test_go_exists(self):
        """L1: examples/tagstats/tags_test.go exists (agent's own table tests)."""
        p = os.path.join(self._repo(), "examples", "tagstats", "tags_test.go")
        assert os.path.isfile(p), "examples/tagstats/tags_test.go is missing"
        with open(p) as fh:
            head = fh.read(8000)
        assert "package tagstats" in head, (
            "tags_test.go must declare `package tagstats`"
        )

    def test_package_compiles(self):
        """L1: the new package compiles via `go build`."""
        res = self._run_go(["go", "build", "./examples/tagstats/"], timeout=300)
        assert res.returncode == 0, (
            "package github.com/samber/lo/examples/tagstats failed to build:\n"
            + res.stdout + res.stderr
        )

    def test_acceptance_command(self):
        """L1/L2: the exact native acceptance command passes.

        `go test ./examples/tagstats/ -run TestCompute -count=1`
        """
        res = self._run_go(
            ["go", "test", "./examples/tagstats/", "-run", "TestCompute", "-count=1"],
            timeout=300,
        )
        assert res.returncode == 0, (
            "acceptance command failed:\n" + res.stdout + res.stderr
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against real Compute
    # ------------------------------------------------------------------ #
    def test_intra_document_dedup(self):
        """L2: a repeated tag within one document counts ONCE toward TagCounts.

        A naive impl that double-counts repeated tags would report 3 for "go".
        """
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	docs := []tagstats.Document{
		{ID: "d1", Tags: []string{"go", "go", "go"}},
	}
	s := tagstats.Compute(docs, 5)
	if s.TagCounts == nil {
		t.Fatalf("TagCounts must be non-nil")
	}
	if got := s.TagCounts["go"]; got != 1 {
		t.Fatalf("TagCounts[go] want 1 (distinct docs), got %d", got)
	}
	if len(s.TagCounts) != 1 {
		t.Fatalf("want exactly 1 tag key, got %d (%v)", len(s.TagCounts), s.TagCounts)
	}
	// A single distinct tag yields no pairs.
	if len(s.TopPairs) != 0 {
		t.Fatalf("single-distinct-tag doc must produce no pairs, got %+v", s.TopPairs)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_distinct_document_tag_counts(self):
        """L2: TagCounts[tag] is the count of DISTINCT documents holding tag."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	docs := []tagstats.Document{
		{ID: "d1", Tags: []string{"a", "b"}},
		{ID: "d2", Tags: []string{"a", "a", "c"}}, // repeated "a" still 1 doc
		{ID: "d3", Tags: []string{"b"}},
	}
	s := tagstats.Compute(docs, 10)
	want := map[string]int{"a": 2, "b": 2, "c": 1}
	if len(s.TagCounts) != len(want) {
		t.Fatalf("TagCounts keys want %v got %v", want, s.TagCounts)
	}
	for k, v := range want {
		if s.TagCounts[k] != v {
			t.Fatalf("TagCounts[%q] want %d got %d (full %v)", k, v, s.TagCounts[k], s.TagCounts)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_absent_tags_not_keys(self):
        """L2: tags appearing in no document must NOT be keys in TagCounts."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	docs := []tagstats.Document{
		{ID: "d1", Tags: []string{"x"}},
	}
	s := tagstats.Compute(docs, 1)
	if _, ok := s.TagCounts["y"]; ok {
		t.Fatalf("absent tag 'y' must not be a key: %v", s.TagCounts)
	}
	if len(s.TagCounts) != 1 {
		t.Fatalf("want only 'x' key, got %v", s.TagCounts)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_pair_normalization_a_le_b(self):
        """L2: every emitted Pair has A <= B lexicographically, regardless of
        the order tags appear in the source documents.

        A naive impl that emits pairs in insertion order produces A="z",B="a".
        """
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	docs := []tagstats.Document{
		// "z" appears before "a" in the tag list on purpose.
		{ID: "d1", Tags: []string{"z", "a"}},
		{ID: "d2", Tags: []string{"z", "a"}},
	}
	s := tagstats.Compute(docs, 10)
	if len(s.TopPairs) != 1 {
		t.Fatalf("want exactly 1 pair, got %+v", s.TopPairs)
	}
	p := s.TopPairs[0]
	if p.A != "a" || p.B != "z" {
		t.Fatalf("pair not normalized A<=B: got A=%q B=%q", p.A, p.B)
	}
	if p.Count != 2 {
		t.Fatalf("pair {a,z} count want 2 got %d", p.Count)
	}
	if !(p.A <= p.B) {
		t.Fatalf("invariant A<=B violated: %+v", p)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_pair_count_distinct_documents(self):
        """L2: pair Count counts DISTINCT docs holding both tags; a doc that
        repeats a tag does not inflate the pair count."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	docs := []tagstats.Document{
		{ID: "d1", Tags: []string{"a", "b"}},
		{ID: "d2", Tags: []string{"a", "a", "b", "b"}}, // still 1 doc for {a,b}
		{ID: "d3", Tags: []string{"a", "b"}},
		{ID: "d4", Tags: []string{"a"}}, // no pair
	}
	s := tagstats.Compute(docs, 10)
	if len(s.TopPairs) != 1 {
		t.Fatalf("want exactly 1 distinct pair, got %+v", s.TopPairs)
	}
	p := s.TopPairs[0]
	if p.A != "a" || p.B != "b" {
		t.Fatalf("want pair {a,b}, got %+v", p)
	}
	if p.Count != 3 {
		t.Fatalf("pair {a,b} count want 3 (d1,d2,d3) got %d", p.Count)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_topn_ordering_count_desc(self):
        """L2: TopPairs ordered by Count descending."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// {a,b} co-occurs in 3 docs; {c,d} in 1 doc.
	docs := []tagstats.Document{
		{ID: "1", Tags: []string{"a", "b"}},
		{ID: "2", Tags: []string{"a", "b"}},
		{ID: "3", Tags: []string{"a", "b"}},
		{ID: "4", Tags: []string{"c", "d"}},
	}
	s := tagstats.Compute(docs, 10)
	if len(s.TopPairs) != 2 {
		t.Fatalf("want 2 pairs, got %+v", s.TopPairs)
	}
	if s.TopPairs[0].Count < s.TopPairs[1].Count {
		t.Fatalf("pairs not sorted by Count desc: %+v", s.TopPairs)
	}
	if s.TopPairs[0].A != "a" || s.TopPairs[0].B != "b" || s.TopPairs[0].Count != 3 {
		t.Fatalf("top pair want {a,b,3}, got %+v", s.TopPairs[0])
	}
	if s.TopPairs[1].A != "c" || s.TopPairs[1].B != "d" || s.TopPairs[1].Count != 1 {
		t.Fatalf("second pair want {c,d,1}, got %+v", s.TopPairs[1])
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_tie_break_lexicographic(self):
        """L2: pairs that tie on Count are ordered by A asc then B asc.

        A naive impl that skips the tie-break (relying on map iteration order)
        is non-deterministic and will eventually fail this exact ordering.
        """
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// Three pairs, each Count==1, deliberately created out of sorted order:
	//   {x,y}, {a,z}, {a,b}  -> sorted want: {a,b},{a,z},{x,y}
	docs := []tagstats.Document{
		{ID: "1", Tags: []string{"x", "y"}},
		{ID: "2", Tags: []string{"z", "a"}}, // normalizes to {a,z}
		{ID: "3", Tags: []string{"a", "b"}},
	}
	s := tagstats.Compute(docs, 10)
	if len(s.TopPairs) != 3 {
		t.Fatalf("want 3 pairs, got %+v", s.TopPairs)
	}
	wantOrder := [][2]string{{"a", "b"}, {"a", "z"}, {"x", "y"}}
	for i, w := range wantOrder {
		got := s.TopPairs[i]
		if got.A != w[0] || got.B != w[1] {
			t.Fatalf("tie-break order wrong at %d: want {%s,%s} got %+v (all %+v)",
				i, w[0], w[1], got, s.TopPairs)
		}
		if got.Count != 1 {
			t.Fatalf("pair %+v count want 1 got %d", got, got.Count)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_count_desc_then_tie_break_combined(self):
        """L2: ordering applies Count desc FIRST, then lexicographic tie-break
        only within equal counts."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// {m,n}: 2 docs (highest).
	// {a,b} and {c,d}: 1 doc each (tie -> {a,b} before {c,d}).
	docs := []tagstats.Document{
		{ID: "1", Tags: []string{"m", "n"}},
		{ID: "2", Tags: []string{"n", "m"}}, // still {m,n}, 2nd doc
		{ID: "3", Tags: []string{"c", "d"}},
		{ID: "4", Tags: []string{"a", "b"}},
	}
	s := tagstats.Compute(docs, 10)
	if len(s.TopPairs) != 3 {
		t.Fatalf("want 3 pairs, got %+v", s.TopPairs)
	}
	if !(s.TopPairs[0].A == "m" && s.TopPairs[0].B == "n" && s.TopPairs[0].Count == 2) {
		t.Fatalf("first must be {m,n,2}, got %+v", s.TopPairs[0])
	}
	if !(s.TopPairs[1].A == "a" && s.TopPairs[1].B == "b" && s.TopPairs[1].Count == 1) {
		t.Fatalf("second must be {a,b,1}, got %+v", s.TopPairs[1])
	}
	if !(s.TopPairs[2].A == "c" && s.TopPairs[2].B == "d" && s.TopPairs[2].Count == 1) {
		t.Fatalf("third must be {c,d,1}, got %+v", s.TopPairs[2])
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_topn_truncation(self):
        """L2: TopPairs is limited to topN entries (the highest-Count ones)."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	docs := []tagstats.Document{
		{ID: "1", Tags: []string{"a", "b"}}, // {a,b}
		{ID: "2", Tags: []string{"a", "b"}}, // {a,b} count 2
		{ID: "3", Tags: []string{"c", "d"}}, // {c,d} count 1
		{ID: "4", Tags: []string{"e", "f"}}, // {e,f} count 1
	}
	s := tagstats.Compute(docs, 1)
	if len(s.TopPairs) != 1 {
		t.Fatalf("topN=1 must return exactly 1 pair, got %+v", s.TopPairs)
	}
	if s.TopPairs[0].A != "a" || s.TopPairs[0].B != "b" || s.TopPairs[0].Count != 2 {
		t.Fatalf("topN=1 must return highest-count pair {a,b,2}, got %+v", s.TopPairs[0])
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_topn_le_zero_empty_nonnil(self):
        """L2: topN <= 0 yields an empty NON-NIL TopPairs (TagCounts still filled)."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	docs := []tagstats.Document{
		{ID: "1", Tags: []string{"a", "b"}},
		{ID: "2", Tags: []string{"a", "b"}},
	}
	for _, n := range []int{0, -1, -100} {
		s := tagstats.Compute(docs, n)
		if s.TopPairs == nil {
			t.Fatalf("topN=%d: TopPairs must be non-nil", n)
		}
		if len(s.TopPairs) != 0 {
			t.Fatalf("topN=%d: TopPairs must be empty, got %+v", n, s.TopPairs)
		}
		// TagCounts must still be populated even when topN<=0.
		if s.TagCounts["a"] != 2 || s.TagCounts["b"] != 2 {
			t.Fatalf("topN=%d: TagCounts still expected, got %v", n, s.TagCounts)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_topn_exceeds_pair_count(self):
        """L2: when topN exceeds the number of distinct pairs, all pairs return."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	docs := []tagstats.Document{
		{ID: "1", Tags: []string{"a", "b"}},
		{ID: "2", Tags: []string{"c", "d"}},
	}
	s := tagstats.Compute(docs, 100)
	if len(s.TopPairs) != 2 {
		t.Fatalf("want all 2 pairs when topN>count, got %+v", s.TopPairs)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_empty_input_nonnil(self):
        """L2: empty docs -> empty non-nil TagCounts and empty non-nil TopPairs."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	s := tagstats.Compute([]tagstats.Document{}, 5)
	if s.TagCounts == nil {
		t.Fatalf("TagCounts must be non-nil for empty input")
	}
	if len(s.TagCounts) != 0 {
		t.Fatalf("TagCounts must be empty for empty input, got %v", s.TagCounts)
	}
	if s.TopPairs == nil {
		t.Fatalf("TopPairs must be non-nil for empty input")
	}
	if len(s.TopPairs) != 0 {
		t.Fatalf("TopPairs must be empty for empty input, got %+v", s.TopPairs)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_input_not_mutated(self):
        """L2: Compute must not mutate the caller's slice or any Tags slice.

        We snapshot the documents (including a deep copy of each Tags slice)
        and confirm nothing changed after Compute returns — catching impls that
        sort/dedup the caller's Tags in place.
        """
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	docs := []tagstats.Document{
		{ID: "d1", Tags: []string{"z", "a", "a"}},
		{ID: "d2", Tags: []string{"b", "z"}},
	}
	// Deep snapshot.
	type snap struct {
		id   string
		tags []string
	}
	before := make([]snap, len(docs))
	for i, d := range docs {
		cp := make([]string, len(d.Tags))
		copy(cp, d.Tags)
		before[i] = snap{id: d.ID, tags: cp}
	}
	_ = tagstats.Compute(docs, 10)
	if len(docs) != len(before) {
		t.Fatalf("input length changed: %d != %d", len(docs), len(before))
	}
	for i := range docs {
		if docs[i].ID != before[i].id {
			t.Fatalf("doc %d ID mutated: %q != %q", i, docs[i].ID, before[i].id)
		}
		if len(docs[i].Tags) != len(before[i].tags) {
			t.Fatalf("doc %d Tags length changed: %v != %v", i, docs[i].Tags, before[i].tags)
		}
		for j := range docs[i].Tags {
			if docs[i].Tags[j] != before[i].tags[j] {
				t.Fatalf("doc %d Tags mutated at %d: %v != %v",
					i, j, docs[i].Tags, before[i].tags)
			}
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_combined_realistic_stats(self):
        """L2: end-to-end scenario exercising dedup, distinct-doc counts, pair
        normalization, count-desc + lexicographic ordering and topN at once."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	docs := []tagstats.Document{
		{ID: "d1", Tags: []string{"go", "go", "cli"}},   // distinct {cli,go}
		{ID: "d2", Tags: []string{"cli", "go"}},          // {cli,go}
		{ID: "d3", Tags: []string{"go", "web"}},          // {go,web}
		{ID: "d4", Tags: []string{"web", "cli"}},         // {cli,web}
		{ID: "d5", Tags: []string{"solo"}},               // single tag, no pair
	}
	s := tagstats.Compute(docs, 2)

	// TagCounts (distinct docs): go=3, cli=3, web=2, solo=1
	wantCounts := map[string]int{"go": 3, "cli": 3, "web": 2, "solo": 1}
	if len(s.TagCounts) != len(wantCounts) {
		t.Fatalf("TagCounts want %v got %v", wantCounts, s.TagCounts)
	}
	for k, v := range wantCounts {
		if s.TagCounts[k] != v {
			t.Fatalf("TagCounts[%q] want %d got %d (full %v)", k, v, s.TagCounts[k], s.TagCounts)
		}
	}

	// Distinct pairs & counts:
	//   {cli,go}: d1,d2 -> 2
	//   {go,web}: d3 -> 1
	//   {cli,web}: d4 -> 1
	// topN=2 -> highest is {cli,go,2}; then tie between {cli,web,1} and {go,web,1}
	// tie-break A asc then B asc -> {cli,web} before {go,web}.
	if len(s.TopPairs) != 2 {
		t.Fatalf("topN=2 must yield 2 pairs, got %+v", s.TopPairs)
	}
	p0, p1 := s.TopPairs[0], s.TopPairs[1]
	if !(p0.A == "cli" && p0.B == "go" && p0.Count == 2) {
		t.Fatalf("first pair want {cli,go,2}, got %+v", p0)
	}
	if !(p1.A == "cli" && p1.B == "web" && p1.Count == 1) {
		t.Fatalf("second pair want {cli,web,1} (tie-break), got %+v (all %+v)", p1, s.TopPairs)
	}

	// Every emitted pair must satisfy A<=B and be ordered.
	if !sort.SliceIsSorted(s.TopPairs, func(i, j int) bool {
		a, b := s.TopPairs[i], s.TopPairs[j]
		if a.Count != b.Count {
			return a.Count > b.Count
		}
		if a.A != b.A {
			return a.A < b.A
		}
		return a.B < b.B
	}) {
		t.Fatalf("TopPairs not in canonical order: %+v", s.TopPairs)
	}
	for _, p := range s.TopPairs {
		if p.A > p.B {
			t.Fatalf("pair violates A<=B: %+v", p)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v", "--tb=short"]))
