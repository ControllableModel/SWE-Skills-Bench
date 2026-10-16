"""
Tests for the python-performance-optimization skill.

Validates that profiling-based optimizations were applied to py-spy's
flamegraph aggregation pipeline, including string interning, efficient
data structures, benchmarks, and correctness tests.

Repo: py-spy (https://github.com/benfred/py-spy)
"""

import os
import re
import subprocess

REPO_DIR = "/workspace/py-spy"


class TestFilePathCheck:
    """Verify all required files exist."""

    def test_flamegraph_rs_exists(self):
        path = os.path.join(REPO_DIR, "src", "flamegraph.rs")
        assert os.path.isfile(path), f"Expected src/flamegraph.rs at {path}"

    def test_stack_trace_rs_exists(self):
        path = os.path.join(REPO_DIR, "src", "stack_trace.rs")
        assert os.path.isfile(path), f"Expected src/stack_trace.rs at {path}"

    def test_benchmark_exists(self):
        path = os.path.join(REPO_DIR, "benches", "flamegraph_bench.rs")
        assert os.path.isfile(path), f"Expected benches/flamegraph_bench.rs"

    def test_perf_test_exists(self):
        path = os.path.join(REPO_DIR, "tests", "test_flamegraph_perf.rs")
        assert os.path.isfile(path), f"Expected tests/test_flamegraph_perf.rs"


class TestSemanticFlamegraph:
    """Verify flamegraph aggregation optimizations."""

    def _read(self):
        path = os.path.join(REPO_DIR, "src", "flamegraph.rs")
        with open(path, "r") as f:
            return f.read()

    def test_intern_mechanism(self):
        content = self._read()
        assert re.search(r"intern|Intern|interner|StringPool|string_pool", content), (
            "Expected string interning mechanism for frame deduplication"
        )

    def test_efficient_child_lookup(self):
        content = self._read()
        assert re.search(r"HashMap|BTreeMap|hash_map|btree", content), (
            "Expected efficient lookup structure (HashMap/BTreeMap) for child frames"
        )

    def test_pre_allocated_buffer(self):
        content = self._read()
        assert re.search(r"String::with_capacity|Vec::with_capacity|buf|buffer|Buffer", content), (
            "Expected pre-allocated buffer for collapsed format output"
        )


class TestSemanticStackTrace:
    """Verify stack frame memory optimizations."""

    def _read(self):
        path = os.path.join(REPO_DIR, "src", "stack_trace.rs")
        with open(path, "r") as f:
            return f.read()

    def test_stack_frame_struct(self):
        content = self._read()
        assert re.search(r"struct\s+StackFrame|StackFrame", content), (
            "Expected StackFrame struct"
        )

    def test_interned_strings(self):
        content = self._read()
        assert re.search(r"Rc<str>|Arc<str>|intern|InternedString|Cow<", content), (
            "Expected interned/shared string references in StackFrame"
        )

    def test_name_field(self):
        content = self._read()
        assert re.search(r"name|function_name|func_name", content), (
            "Expected name/function_name field in StackFrame"
        )

    def test_filename_field(self):
        content = self._read()
        assert re.search(r"filename|file_name|file", content), (
            "Expected filename field in StackFrame"
        )


class TestSemanticBenchmarks:
    """Verify benchmark suite."""

    def _read(self):
        path = os.path.join(REPO_DIR, "benches", "flamegraph_bench.rs")
        with open(path, "r") as f:
            return f.read()

    def test_criterion_usage(self):
        content = self._read()
        assert re.search(r"criterion|Criterion|criterion_group|criterion_main", content), (
            "Expected Criterion benchmark framework usage"
        )

    def test_small_benchmark(self):
        content = self._read()
        assert re.search(r"small|1.?000|1_000", content, re.IGNORECASE), (
            "Expected small benchmark (1,000 samples)"
        )

    def test_medium_benchmark(self):
        content = self._read()
        assert re.search(r"medium|100.?000|100_000", content, re.IGNORECASE), (
            "Expected medium benchmark (100,000 samples)"
        )

    def test_large_benchmark(self):
        content = self._read()
        assert re.search(r"large|1.?000.?000|1_000_000", content, re.IGNORECASE), (
            "Expected large benchmark (1,000,000 samples)"
        )


class TestSemanticPerfTests:
    """Verify integration tests for correctness after optimization."""

    def _read(self):
        path = os.path.join(REPO_DIR, "tests", "test_flamegraph_perf.rs")
        with open(path, "r") as f:
            return f.read()

    def test_output_correctness(self):
        content = self._read()
        assert re.search(r"assert|assert_eq|correct|identical|byte.*identical", content), (
            "Expected correctness assertions (byte-identical output)"
        )

    def test_test_functions(self):
        content = self._read()
        count = len(re.findall(r"#\[test\]|fn\s+test_", content))
        assert count >= 2, (
            f"Expected >= 2 test functions, found {count}"
        )


class TestSemanticInternPool:
    """Verify intern pool is bounded."""

    def _read_all(self):
        content = ""
        for fname in ["flamegraph.rs", "stack_trace.rs"]:
            path = os.path.join(REPO_DIR, "src", fname)
            if os.path.isfile(path):
                with open(path, "r") as f:
                    content += f.read()
        return content

    def test_pool_limit(self):
        content = self._read_all()
        assert re.search(r"100.?000|max.*capacity|limit|bounded", content, re.IGNORECASE), (
            "Expected intern pool bounded at 100,000 entries"
        )

    def test_fallback_allocation(self):
        content = self._read_all()
        assert re.search(r"fallback|warn|log.*warn|regular.*alloc", content, re.IGNORECASE), (
            "Expected fallback to regular allocation when pool is full"
        )


class TestFunctionalRustSyntax:
    """Validate Rust files compile."""

    def test_cargo_build(self):
        result = subprocess.run(
            ["cargo", "build", "--release"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"cargo build --release failed:\n{result.stderr[:1000]}"
        )

    def test_balanced_braces_flamegraph(self):
        path = os.path.join(REPO_DIR, "src", "flamegraph.rs")
        with open(path, "r") as f:
            content = f.read()
        opens = content.count("{")
        closes = content.count("}")
        assert opens == closes, (
            f"Unbalanced braces in flamegraph.rs: {opens} {{ vs {closes} }}"
        )

    def test_balanced_braces_stack_trace(self):
        path = os.path.join(REPO_DIR, "src", "stack_trace.rs")
        with open(path, "r") as f:
            content = f.read()
        opens = content.count("{")
        closes = content.count("}")
        assert opens == closes, (
            f"Unbalanced braces in stack_trace.rs: {opens} {{ vs {closes} }}"
        )
