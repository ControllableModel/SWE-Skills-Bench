"""Benchmark verification for skill: jest-advanced-patterns (variant ext3).

Task: Add an async retry runner to the React monorepo's ``shared`` package
(``packages/shared/createRetryRunner.js``) plus a deterministic Jest suite
(``packages/shared/__tests__/createRetryRunner-test.js``).

The runner is a factory ``createRetryRunner({maxAttempts, shouldRetry})`` that
returns ``run(operation) -> Promise``. ``operation(attemptNumber)`` is retried,
up to ``maxAttempts`` total attempts, while it rejects and (optional)
``shouldRetry(error, attemptNumber)`` is truthy. The runner uses ONLY the
injected ``operation``/``shouldRetry`` — no timers, network, globals, or other
modules. Invalid ``maxAttempts`` throws ``RangeError`` from the factory.

Strategy
--------
L1 cases assert the two deliverable files exist, expose a default export, and
that the implementation imports no other module (a hard constraint from the doc:
"imports no other module").

L2 cases independently EXERCISE the real runner. Rather than trusting the
agent's own test file, each L2 method writes ITS OWN focused Jest probe spec
into ``packages/shared/__tests__/`` and runs that single spec through the repo's
native Jest CLI (``yarn test <path>`` -> ``node scripts/jest/jest-cli.js
<path>``, which forwards the path as a testPathPattern). Every probe drives the
runner with a fully controllable, deterministic mock ``operation`` (a queue of
scripted resolve/reject outcomes — no timers, network, or randomness) and
deep-validates exactly ONE behavior from the requirement doc:

  * eventual success after retries (resolves with the last value)
  * exact attempt-number sequencing (1, 2, 3, ...)
  * exhaustion rejects with the LAST error (not the first)
  * ``shouldRetry`` short-circuit rejects with the FIRST error, one call only
  * immediate success calls operation exactly once
  * ``shouldRetry`` receives the right (error, attemptNumber) arguments
  * operation invoked at most ``maxAttempts`` times, never more
  * the final-attempt failure is not retried even without ``shouldRetry``
  * the ``RangeError`` guard for invalid ``maxAttempts``
  * a non-function ``operation`` deterministically fails the run

A naive/stub implementation (always calls operation once, hardcodes a value,
ignores attempt numbers, surfaces the first error instead of the last, retries
past ``maxAttempts``, or never validates ``maxAttempts``) fails the specific
probe it got wrong. We also confirm the agent's own suite runs green via the
exact Acceptance-Criteria command.

Module resolution note: this repo resolves ``shared/<name>`` via Jest haste
(``roots: ['<rootDir>/packages', ...]``), so the probe ``require``s
``'shared/createRetryRunner'`` exactly like the repo's own shared tests.
"""

import os
import re
import subprocess
import textwrap

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies  # noqa: F401
except Exception:  # pragma: no cover - utils may be absent locally
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/react"

SRC_REL = "packages/shared/createRetryRunner.js"
AGENT_TEST_REL = "packages/shared/__tests__/createRetryRunner-test.js"

# Each probe is written under __tests__ (so the repo's testRegex matches it) and
# is removed after the run. Unique names avoid cross-test collisions.
PROBE_DIR_REL = "packages/shared/__tests__"
PROBE_PREFIX = "createRetryRunner-probe-"


def _src_path():
    return os.path.join(REPO_DIR, SRC_REL)


def _agent_test_path():
    return os.path.join(REPO_DIR, AGENT_TEST_REL)


def _probe_rel(name):
    return os.path.join(PROBE_DIR_REL, PROBE_PREFIX + name + ".bench-test.js")


def _probe_abs(name):
    return os.path.join(REPO_DIR, _probe_rel(name))


def _read_src():
    with open(_src_path()) as fh:
        return fh.read()


def _yarn_test(path_rel, timeout=300):
    """Run the repo's native Jest CLI scoped to a single test file.

    ``yarn test <path>`` invokes ``node ./scripts/jest/jest-cli.js <path>``;
    the trailing path is forwarded to Jest as a testPathPattern so only that
    one spec executes.
    """
    return subprocess.run(
        ["yarn", "test", path_rel],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _jest_passed(result):
    """Require real test execution plus an explicit green summary."""
    out = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.returncode != 0:
        return False, out
    if re.search(r"No tests found", out):
        return False, out
    if re.search(r"Tests:\s+.*\bfailed", out):
        return False, out
    if not re.search(r"Tests:\s+\d+ passed", out) and not re.search(r"PASS\b", out):
        return False, out
    return True, out


# Shared JS preamble: a deterministic, scripted mock ``operation``. ``script``
# is an ordered list of outcomes, one per allowed attempt:
#   {resolve: value}  -> the operation resolves with value
#   {reject: error}   -> the operation rejects with error
# The mock records the exact attemptNumber it was called with on each call, so
# probes can assert call count AND the 1,2,3,... sequencing without any timers,
# network, or randomness. Injected verbatim into each probe spec.
_OPERATION_PREAMBLE = """\
'use strict';

function makeOperation(script) {
  const attempts = [];           // attemptNumber values seen, in order
  let i = 0;
  function operation(attemptNumber) {
    attempts.push(attemptNumber);
    const step = script[i++];
    if (step === undefined) {
      // Called more times than scripted: surface a distinctive error so an
      // over-eager runner fails loudly rather than silently.
      return Promise.reject(new Error('OVER_INVOKED'));
    }
    if (Object.prototype.hasOwnProperty.call(step, 'resolve')) {
      return Promise.resolve(step.resolve);
    }
    return Promise.reject(step.reject);
  }
  operation.attempts = attempts;
  operation.count = () => attempts.length;
  return operation;
}

function load() {
  return require('shared/createRetryRunner').default;
}
"""


def _make_probe(body):
    """Wrap a single-behavior ``it(...)`` body in the shared preamble."""
    return _OPERATION_PREAMBLE + "\n" + textwrap.dedent(body) + "\n"


def _run_probe(name, body, timeout=300):
    """Write a one-behavior probe spec, run it via native Jest, clean up."""
    rel = _probe_rel(name)
    abs_path = _probe_abs(name)
    with open(abs_path, "w") as fh:
        fh.write(_make_probe(body))
    try:
        result = _yarn_test(rel, timeout=timeout)
    finally:
        try:
            os.remove(abs_path)
        except OSError:
            pass
    return result


@pytest.fixture(scope="module", autouse=True)
def _deps():
    """Ensure JS toolchain deps are present, and sweep stray probe files."""
    node_modules = os.path.join(REPO_DIR, "node_modules")
    jest_marker = os.path.join(node_modules, "chalk")
    if not os.path.isdir(jest_marker):
        try:
            subprocess.run(
                ["yarn", "install", "--frozen-lockfile"],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=1800,
            )
        except Exception:
            pass
        if not os.path.isdir(jest_marker) and ensure_npm_dependencies is not None:
            try:
                ensure_npm_dependencies(REPO_DIR)
            except Exception:
                pass
    yield
    probe_dir = os.path.join(REPO_DIR, PROBE_DIR_REL)
    try:
        for fname in os.listdir(probe_dir):
            if fname.startswith(PROBE_PREFIX):
                try:
                    os.remove(os.path.join(probe_dir, fname))
                except OSError:
                    pass
    except OSError:
        pass


class TestJestAdvancedPatterns:
    REPO_DIR = REPO_DIR

    # -----------------------------------------------------------------------
    # L1 — deliverables exist and respect the structural constraints.
    # -----------------------------------------------------------------------
    def test_runner_source_exists(self):
        """L1: the retry-runner module file exists and is non-empty."""
        path = _src_path()
        assert os.path.isfile(path), f"missing deliverable: {SRC_REL}"
        assert os.path.getsize(path) > 0, "runner source is empty"

    def test_agent_test_file_exists(self):
        """L1: the agent's Jest test suite file exists and is non-empty."""
        path = _agent_test_path()
        assert os.path.isfile(path), f"missing deliverable: {AGENT_TEST_REL}"
        assert os.path.getsize(path) > 0, "agent test file is empty"

    def test_runner_has_default_export(self):
        """L1: the runner exposes a default export (the factory)."""
        src = _read_src()
        assert "export default" in src or "module.exports" in src, (
            "runner must export the factory by default"
        )

    def test_runner_imports_no_other_module(self):
        """L1: hard constraint — the module imports/requires no other module."""
        src = _read_src()
        no_block = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
        no_line = re.sub(r"//[^\n]*", "", no_block)
        assert not re.search(r"^\s*import\s", no_line, flags=re.MULTILINE), (
            "runner must contain no `import` statement"
        )
        assert not re.search(r"\brequire\s*\(", no_line), (
            "runner must not `require` any other module"
        )

    # -----------------------------------------------------------------------
    # L2 — each behavior gets its OWN independent probe spec run via Jest.
    # -----------------------------------------------------------------------
    def test_eventual_success_after_retries(self):
        """L2: rejects twice then resolves -> run resolves with the third value.

        With ``maxAttempts: 3`` and an operation scripted to reject, reject,
        resolve, ``run`` must resolve to the final value and call ``operation``
        exactly three times.
        """
        result = _run_probe(
            "eventual-success",
            """
            it('rejects twice then resolves: resolves with third value, 3 calls', async () => {
              const op = makeOperation([
                {reject: new Error('e1')},
                {reject: new Error('e2')},
                {resolve: 'THIRD'},
              ]);
              const run = load()({maxAttempts: 3});
              await expect(run(op)).resolves.toBe('THIRD');
              expect(op.count()).toBe(3);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"eventual-success probe failed:\n{out[-4000:]}"

    def test_attempt_numbers_increase_by_one(self):
        """L2: operation receives attempt numbers 1, 2, 3 in order.

        The attempt number passed to ``operation`` must start at 1 and increase
        by exactly one on each retry — never repeated, skipped, or reordered.
        """
        result = _run_probe(
            "attempt-sequence",
            """
            it('attempt numbers are exactly 1,2,3 in order', async () => {
              const op = makeOperation([
                {reject: new Error('e1')},
                {reject: new Error('e2')},
                {resolve: 'ok'},
              ]);
              const run = load()({maxAttempts: 3});
              await run(op);
              expect(op.attempts).toEqual([1, 2, 3]);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"attempt-sequence probe failed:\n{out[-4000:]}"

    def test_exhaustion_rejects_with_last_error(self):
        """L2: always-rejecting op with maxAttempts:2 rejects with the SECOND error.

        On exhaustion ``run`` must reject with the LAST error encountered (e2),
        not the first (e1), and call ``operation`` exactly twice. A stub that
        surfaces the first error fails here.
        """
        result = _run_probe(
            "exhaust-last-error",
            """
            it('exhaustion rejects with the last error, 2 calls', async () => {
              const e1 = new Error('e1');
              const e2 = new Error('e2');
              const op = makeOperation([{reject: e1}, {reject: e2}]);
              const run = load()({maxAttempts: 2});
              await expect(run(op)).rejects.toBe(e2);
              expect(op.count()).toBe(2);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"exhaust-last-error probe failed:\n{out[-4000:]}"

    def test_should_retry_false_short_circuits(self):
        """L2: shouldRetry returning false after attempt 1 rejects with first error.

        With ``shouldRetry`` always false, the runner must stop after the first
        failure, reject with that first error, and call ``operation`` exactly
        once — even though ``maxAttempts`` allows more.
        """
        result = _run_probe(
            "short-circuit",
            """
            it('shouldRetry=false rejects with first error, one call', async () => {
              const e1 = new Error('first');
              const op = makeOperation([
                {reject: e1},
                {resolve: 'should-never-reach'},
              ]);
              const run = load()({maxAttempts: 3, shouldRetry: () => false});
              await expect(run(op)).rejects.toBe(e1);
              expect(op.count()).toBe(1);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"short-circuit probe failed:\n{out[-4000:]}"

    def test_immediate_success_calls_once(self):
        """L2: an operation that resolves immediately calls operation exactly once.

        First-try success must resolve with that value and never invoke the
        operation again, with attempt number 1.
        """
        result = _run_probe(
            "immediate-success",
            """
            it('immediate success: one call, attempt 1, resolves value', async () => {
              const op = makeOperation([{resolve: 'FIRST'}]);
              const run = load()({maxAttempts: 5});
              await expect(run(op)).resolves.toBe('FIRST');
              expect(op.attempts).toEqual([1]);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"immediate-success probe failed:\n{out[-4000:]}"

    def test_should_retry_receives_error_and_attempt(self):
        """L2: shouldRetry is called with (error, attemptNumber) per failure.

        The predicate must receive the exact error object and the failing
        attempt number. We capture the calls and assert they correspond to the
        scripted failures (e1 at attempt 1, e2 at attempt 2).
        """
        result = _run_probe(
            "should-retry-args",
            """
            it('shouldRetry receives (error, attemptNumber) for each failure', async () => {
              const e1 = new Error('e1');
              const e2 = new Error('e2');
              const seen = [];
              const op = makeOperation([
                {reject: e1},
                {reject: e2},
                {resolve: 'done'},
              ]);
              const run = load()({
                maxAttempts: 3,
                shouldRetry: (err, n) => { seen.push([err, n]); return true; },
              });
              await expect(run(op)).resolves.toBe('done');
              expect(seen).toEqual([[e1, 1], [e2, 2]]);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"should-retry-args probe failed:\n{out[-4000:]}"

    def test_operation_never_called_more_than_max_attempts(self):
        """L2: operation is invoked at most maxAttempts times, never more.

        With ``maxAttempts: 2`` and an always-rejecting operation, the runner
        must stop after two calls. The scripted mock returns OVER_INVOKED on a
        third call; if the runner over-invokes, the run would reject with that
        sentinel instead of e2 — so we assert both the count and the error.
        """
        result = _run_probe(
            "no-over-invoke",
            """
            it('operation called at most maxAttempts times', async () => {
              const e1 = new Error('e1');
              const e2 = new Error('e2');
              const op = makeOperation([{reject: e1}, {reject: e2}]);
              const run = load()({maxAttempts: 2});
              const err = await run(op).then(
                () => { throw new Error('unexpectedly resolved'); },
                e => e,
              );
              expect(err).toBe(e2);
              expect(err.message).not.toBe('OVER_INVOKED');
              expect(op.count()).toBe(2);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"no-over-invoke probe failed:\n{out[-4000:]}"

    def test_final_attempt_failure_not_retried_without_should_retry(self):
        """L2: with no shouldRetry, the last allowed attempt's failure is final.

        ``maxAttempts: 1`` and a rejecting operation must reject with that error
        after exactly one call — the runner must not retry the first/last
        attempt when it equals maxAttempts.
        """
        result = _run_probe(
            "final-attempt",
            """
            it('maxAttempts:1 failure rejects after a single call', async () => {
              const e1 = new Error('only');
              const op = makeOperation([{reject: e1}]);
              const run = load()({maxAttempts: 1});
              await expect(run(op)).rejects.toBe(e1);
              expect(op.count()).toBe(1);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"final-attempt probe failed:\n{out[-4000:]}"

    def test_invalid_max_attempts_throws_range_error(self):
        """L2: invalid maxAttempts makes the FACTORY throw a RangeError.

        Zero, a negative, a non-integer, and a non-number must each cause
        ``createRetryRunner`` to throw a ``RangeError`` at construction time
        (before any operation runs).
        """
        result = _run_probe(
            "range-error",
            """
            it('factory throws RangeError for invalid maxAttempts', () => {
              const factory = load();
              expect(() => factory({maxAttempts: 0})).toThrow(RangeError);
              expect(() => factory({maxAttempts: -1})).toThrow(RangeError);
              expect(() => factory({maxAttempts: 2.5})).toThrow(RangeError);
              expect(() => factory({maxAttempts: 'three'})).toThrow(RangeError);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"range-error probe failed:\n{out[-4000:]}"

    def test_valid_max_attempts_does_not_throw(self):
        """L2: a valid positive-integer maxAttempts constructs without throwing.

        Guards the RangeError check against being over-broad: a legitimate
        ``maxAttempts: 1`` (and 3) must build a usable runner.
        """
        result = _run_probe(
            "valid-max",
            """
            it('valid maxAttempts builds a working runner', async () => {
              const factory = load();
              expect(() => factory({maxAttempts: 1})).not.toThrow();
              const run = factory({maxAttempts: 3});
              const op = makeOperation([{resolve: 'v'}]);
              await expect(run(op)).resolves.toBe('v');
              expect(op.count()).toBe(1);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"valid-max probe failed:\n{out[-4000:]}"

    def test_non_function_operation_fails_run(self):
        """L2: a non-function operation makes run deterministically fail.

        The doc lets the impl either reject or throw synchronously for a
        non-function ``operation`` — but it must be deterministic. We accept
        either: a thrown error OR a rejected promise, for undefined and a number.
        """
        result = _run_probe(
            "bad-operation",
            """
            it('non-function operation: run throws or rejects deterministically', async () => {
              const run = load()({maxAttempts: 2});
              async function failsFor(bad) {
                let threwSync = false;
                let p;
                try {
                  p = run(bad);
                } catch (e) {
                  threwSync = true;
                }
                if (threwSync) return true;
                let rejected = false;
                await p.then(() => {}, () => { rejected = true; });
                return rejected;
              }
              expect(await failsFor(undefined)).toBe(true);
              expect(await failsFor(123)).toBe(true);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"bad-operation probe failed:\n{out[-4000:]}"

    # -----------------------------------------------------------------------
    # L2 — the agent's own suite must pass via the spec'd command.
    # -----------------------------------------------------------------------
    def test_agent_suite_passes(self):
        """L2: the agent's own Jest suite passes via the Acceptance command.

        Mirrors the Acceptance Criteria command exactly:
        ``yarn test packages/shared/__tests__/createRetryRunner-test.js``.
        """
        result = _yarn_test(AGENT_TEST_REL, timeout=300)
        ok, out = _jest_passed(result)
        assert ok, f"agent suite did not pass green:\n{out[-4000:]}"

    def test_agent_suite_has_multiple_independent_cases(self):
        """L2: the agent suite must contain several independent passing cases.

        The requirement mandates per-behavior independent cases (eventual
        success, exhaustion, shouldRetry short-circuit, single-attempt success,
        attempt sequencing, RangeError), so a single trivial test would not
        satisfy it; require a multi-case green run.
        """
        result = _yarn_test(AGENT_TEST_REL, timeout=300)
        out = (result.stdout or "") + "\n" + (result.stderr or "")
        assert result.returncode == 0, f"agent suite nonzero rc:\n{out[-3000:]}"
        m = re.search(r"Tests:\s+(\d+) passed", out)
        assert m is not None, f"no passing summary in agent run:\n{out[-3000:]}"
        assert int(m.group(1)) >= 5, (
            f"agent suite should have multiple cases, saw {m.group(1)}"
        )
