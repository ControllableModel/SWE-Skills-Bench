"""Benchmark test for skill `samber-lo-functional` (variant ext8).

Verifies the agent-built "slug and keyword extractor" example application under
`examples/textkit` of the `github.com/samber/lo` module.

The task (tasks/ext8/samber-lo-functional.md) asks for a new package
`github.com/samber/lo/examples/textkit` (package `textkit`) exporting:

    func Slugify(title string) string
    type Keyword struct { Word string; Count int }
    func Keywords(title string, stopWords []string, minLen int, topN int) []Keyword

with strict rules:
  * Slugify: whitespace split -> lowercase -> strip non-[a-z0-9] -> drop empty
    words -> join survivors with single '-'; empty/all-punctuation -> "".
  * Keywords: same normalization, exclude stop words (case-insensitive) and
    tokens with len < minLen, count occurrences, return top `topN` ordered by
    Count desc then Word asc; topN<=0 -> empty non-nil slice; result always
    non-nil.

Discriminative strategy: rather than trusting the agent's own
`textkit_test.go`, the L2 cases write an INDEPENDENT external test file
(`package textkitdriver`) into a fresh sub-package directory under
`examples/`, import the real `github.com/samber/lo/examples/textkit`, and
assert on concrete return values via the native `go test` toolchain.

A naive implementation FAILS these drivers if it:
  * leaves punctuation/uppercase in slugs,
  * emits empty hyphen segments on double spaces/tabs,
  * ignores stopWords or minLen filtering,
  * skips the Count-desc / Word-asc tie-break,
  * fails to truncate to topN or returns nil for empty results.

Native acceptance command this file drives (verbatim from the doc):
    go test ./examples/textkit/ -run 'TestSlugify|TestKeywords' -count=1
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
        single external driver test that imports the real `textkit` package.
        Returns the `./examples/<name>/` path and the absolute dir for cleanup.
        """
        name = "textkitverify_" + uuid.uuid4().hex[:10]
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

    # Common Go preamble for drivers: import the real package + helpers.
    _IMPORT = (
        'package textkitdriver\n\n'
        'import (\n'
        '\t"testing"\n\n'
        '\ttextkit "github.com/samber/lo/examples/textkit"\n'
        ')\n\n'
    )

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_textkit_go_exists(self):
        """L1: examples/textkit/textkit.go exists and declares package textkit."""
        p = os.path.join(self._repo(), "examples", "textkit", "textkit.go")
        assert os.path.isfile(p), "examples/textkit/textkit.go is missing"
        with open(p) as fh:
            head = fh.read(8000)
        assert "package textkit" in head, "textkit.go must declare `package textkit`"

    def test_textkit_test_go_exists(self):
        """L1: examples/textkit/textkit_test.go exists (agent's own table tests)."""
        p = os.path.join(self._repo(), "examples", "textkit", "textkit_test.go")
        assert os.path.isfile(p), "examples/textkit/textkit_test.go is missing"
        with open(p) as fh:
            head = fh.read(8000)
        assert "package textkit" in head, (
            "textkit_test.go must declare `package textkit`"
        )

    def test_package_compiles(self):
        """L1: the new package compiles via `go build`."""
        res = self._run_go(["go", "build", "./examples/textkit/"], timeout=300)
        assert res.returncode == 0, (
            "package github.com/samber/lo/examples/textkit failed to build:\n"
            + res.stdout + res.stderr
        )

    def test_agents_own_tests_pass(self):
        """L1/L2: the exact acceptance command passes.

        `go test ./examples/textkit/ -run 'TestSlugify|TestKeywords' -count=1`
        """
        res = self._run_go(
            [
                "go", "test", "./examples/textkit/",
                "-run", "TestSlugify|TestKeywords", "-count=1",
            ],
            timeout=300,
        )
        assert res.returncode == 0, (
            "acceptance command failed:\n" + res.stdout + res.stderr
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against the real symbols
    # ------------------------------------------------------------------ #
    def test_slugify_basic_lowercase_punctuation(self):
        """L2: 'Hello, World!' -> 'hello-world' (lowercase + strip punctuation)."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	if got := textkit.Slugify("Hello, World!"); got != "hello-world" {
		t.Fatalf("Slugify(%q) = %q, want %q", "Hello, World!", got, "hello-world")
	}
	// Original casing/punctuation must not matter: normalizes identically.
	if got := textkit.Slugify("hELLo... WORLD"); got != "hello-world" {
		t.Fatalf("Slugify(%q) = %q, want %q", "hELLo... WORLD", got, "hello-world")
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_slugify_collapses_whitespace_no_empty_segments(self):
        """L2: runs of spaces/tabs/newlines collapse; no empty hyphen segments."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	cases := map[string]string{
		"a   b":         "a-b",
		"a\t\tb":        "a-b",
		"  lead  trail ": "lead-trail",
		"one\ntwo\tthree three": "one-two-three-three",
	}
	for in, want := range cases {
		if got := textkit.Slugify(in); got != want {
			t.Fatalf("Slugify(%q) = %q, want %q", in, got, want)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_slugify_strips_nonalnum_keeps_digits(self):
        """L2: non-[a-z0-9] removed in place; ASCII digits kept; empties dropped."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// punctuation glued to a word is stripped but the word survives
	if got := textkit.Slugify("c++ & go2!"); got != "c-go2" {
		t.Fatalf("Slugify(%q) = %q, want %q", "c++ & go2!", got, "c-go2")
	}
	// a word that is purely punctuation becomes empty and is dropped
	if got := textkit.Slugify("alpha *** beta"); got != "alpha-beta" {
		t.Fatalf("Slugify(%q) = %q, want %q", "alpha *** beta", got, "alpha-beta")
	}
	// digits-only words are kept
	if got := textkit.Slugify("Top 10 Songs"); got != "top-10-songs" {
		t.Fatalf("Slugify(%q) = %q, want %q", "Top 10 Songs", got, "top-10-songs")
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_slugify_empty_and_all_punctuation(self):
        """L2: empty input and all-punctuation input both yield "" (no panic)."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	if got := textkit.Slugify(""); got != "" {
		t.Fatalf("Slugify(\"\") = %q, want empty string", got)
	}
	if got := textkit.Slugify("   "); got != "" {
		t.Fatalf("Slugify(whitespace) = %q, want empty string", got)
	}
	if got := textkit.Slugify("!!! ??? ---"); got != "" {
		t.Fatalf("Slugify(all-punct) = %q, want empty string", got)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_keywords_count_descending_ranking(self):
        """L2: repeated tokens get higher Count and rank above rarer ones."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// "apple" x3, "banana" x2, "cherry" x1
	title := "apple banana apple cherry banana apple"
	kw := textkit.Keywords(title, nil, 1, 10)
	if len(kw) != 3 {
		t.Fatalf("want 3 keywords, got %d (%+v)", len(kw), kw)
	}
	if kw[0].Word != "apple" || kw[0].Count != 3 {
		t.Fatalf("rank0 want {apple 3}, got %+v", kw[0])
	}
	if kw[1].Word != "banana" || kw[1].Count != 2 {
		t.Fatalf("rank1 want {banana 2}, got %+v", kw[1])
	}
	if kw[2].Word != "cherry" || kw[2].Count != 1 {
		t.Fatalf("rank2 want {cherry 1}, got %+v", kw[2])
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_keywords_tie_break_word_ascending(self):
        """L2: equal counts break ties by Word ascending (not insertion order)."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// zebra and apple each appear twice; apple must come first lexicographically.
	// zebra is seen first so a naive "first seen wins" impl would mis-order.
	title := "zebra apple zebra apple"
	kw := textkit.Keywords(title, nil, 1, 10)
	if len(kw) != 2 {
		t.Fatalf("want 2 keywords, got %d (%+v)", len(kw), kw)
	}
	if kw[0].Word != "apple" || kw[0].Count != 2 {
		t.Fatalf("tie-break rank0 want {apple 2}, got %+v", kw[0])
	}
	if kw[1].Word != "zebra" || kw[1].Count != 2 {
		t.Fatalf("tie-break rank1 want {zebra 2}, got %+v", kw[1])
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_keywords_stopwords_and_minlen_filtering(self):
        """L2: stop words excluded (case-insensitively) and len < minLen dropped."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// "the" is a stop word (given uppercase, compared case-insensitively).
	// "a", "of", "go" have len < 3 and must drop when minLen=3.
	// "golang" and "rocks" survive.
	title := "The GOLANG of a go golang rocks the"
	kw := textkit.Keywords(title, []string{"THE"}, 3, 10)
	for _, k := range kw {
		if k.Word == "the" {
			t.Fatalf("stop word 'the' must be excluded: %+v", kw)
		}
		if k.Word == "a" || k.Word == "of" || k.Word == "go" {
			t.Fatalf("token %q below minLen must be excluded: %+v", k.Word, kw)
		}
		if len(k.Word) < 3 {
			t.Fatalf("token %q shorter than minLen 3 present: %+v", k.Word, kw)
		}
	}
	if len(kw) != 2 {
		t.Fatalf("want 2 keywords (golang,rocks), got %d (%+v)", len(kw), kw)
	}
	if kw[0].Word != "golang" || kw[0].Count != 2 {
		t.Fatalf("rank0 want {golang 2}, got %+v", kw[0])
	}
	if kw[1].Word != "rocks" || kw[1].Count != 1 {
		t.Fatalf("rank1 want {rocks 1}, got %+v", kw[1])
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_keywords_stopword_excluded_even_if_long(self):
        """L2: a stop word longer than minLen is still excluded."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// "javascript" is long (> minLen) but is a stop word -> excluded.
	title := "javascript python javascript python ruby"
	kw := textkit.Keywords(title, []string{"javascript"}, 2, 10)
	for _, k := range kw {
		if k.Word == "javascript" {
			t.Fatalf("long stop word 'javascript' must still be excluded: %+v", kw)
		}
	}
	if len(kw) != 2 {
		t.Fatalf("want 2 keywords (python,ruby), got %d (%+v)", len(kw), kw)
	}
	if kw[0].Word != "python" || kw[0].Count != 2 {
		t.Fatalf("rank0 want {python 2}, got %+v", kw[0])
	}
	if kw[1].Word != "ruby" || kw[1].Count != 1 {
		t.Fatalf("rank1 want {ruby 1}, got %+v", kw[1])
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_keywords_topn_truncation(self):
        """L2: only the top `topN` keywords are returned after ranking."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// counts: alpha 4, bravo 3, charlie 2, delta 1
	title := "alpha alpha alpha alpha bravo bravo bravo charlie charlie delta"
	kw := textkit.Keywords(title, nil, 1, 2)
	if len(kw) != 2 {
		t.Fatalf("topN=2 must return exactly 2, got %d (%+v)", len(kw), kw)
	}
	if kw[0].Word != "alpha" || kw[0].Count != 4 {
		t.Fatalf("rank0 want {alpha 4}, got %+v", kw[0])
	}
	if kw[1].Word != "bravo" || kw[1].Count != 3 {
		t.Fatalf("rank1 want {bravo 3}, got %+v", kw[1])
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_keywords_topn_nonpositive_returns_empty_nonnil(self):
        """L2: topN <= 0 returns an empty but NON-nil slice."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	for _, n := range []int{0, -1, -5} {
		kw := textkit.Keywords("alpha beta gamma", nil, 1, n)
		if kw == nil {
			t.Fatalf("Keywords(topN=%d) returned nil, want empty non-nil slice", n)
		}
		if len(kw) != 0 {
			t.Fatalf("Keywords(topN=%d) want empty, got %+v", n, kw)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_keywords_fewer_than_topn_and_empty_input_nonnil(self):
        """L2: fewer keywords than topN -> all of them; empty input -> non-nil empty."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// Only 2 distinct surviving keywords but topN=10 -> return both.
	kw := textkit.Keywords("alpha beta alpha", nil, 1, 10)
	if len(kw) != 2 {
		t.Fatalf("want 2 keywords, got %d (%+v)", len(kw), kw)
	}
	if kw[0].Word != "alpha" || kw[0].Count != 2 {
		t.Fatalf("rank0 want {alpha 2}, got %+v", kw[0])
	}
	if kw[1].Word != "beta" || kw[1].Count != 1 {
		t.Fatalf("rank1 want {beta 1}, got %+v", kw[1])
	}
	// Empty / all-punctuation input: non-nil empty slice, no panic.
	for _, in := range []string{"", "   ", "!!! ???"} {
		e := textkit.Keywords(in, nil, 1, 5)
		if e == nil {
			t.Fatalf("Keywords(%q) returned nil, want non-nil empty slice", in)
		}
		if len(e) != 0 {
			t.Fatalf("Keywords(%q) want empty, got %+v", in, e)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_keywords_same_normalization_as_slugify(self):
        """L2: Keywords tokenizes with the SAME normalization as Slugify.

        Mixed-case + punctuation tokens collapse to their normalized form before
        counting, so 'Apple!' and 'apple' are the same keyword.
        """
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// "Apple!", "APPLE", "apple." all normalize to "apple" -> count 3.
	// "c++" normalizes to "c"; with minLen=2 it is dropped.
	title := "Apple! APPLE apple. c++ Banana, banana"
	kw := textkit.Keywords(title, nil, 2, 10)
	if len(kw) != 2 {
		t.Fatalf("want 2 keywords (apple,banana), got %d (%+v)", len(kw), kw)
	}
	if kw[0].Word != "apple" || kw[0].Count != 3 {
		t.Fatalf("rank0 want {apple 3}, got %+v", kw[0])
	}
	if kw[1].Word != "banana" || kw[1].Count != 2 {
		t.Fatalf("rank1 want {banana 2}, got %+v", kw[1])
	}
	for _, k := range kw {
		if k.Word == "c" {
			t.Fatalf("token 'c' below minLen 2 must be excluded: %+v", kw)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v", "--tb=short"]))
