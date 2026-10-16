"""Benchmark verification for skill: jest-advanced-patterns (variant ext7).

Task: Add a runtime *props-shape validator* to the React monorepo's ``shared``
package (``packages/shared/validateShape.js``) plus a deterministic Jest suite
(``packages/shared/__tests__/validateShape-test.js``).

The validator's public API is::

    validateShape(schema, value) -> string[]   // one message per violation

where ``schema`` maps field names to ``{ type, required }`` descriptors with
``type`` in {'string','number','boolean','function','array','object'}. It
returns an array of human-readable violation strings (empty == valid) and
throws ``TypeError`` when ``schema`` or ``value`` is not a non-null object.

Strategy
--------
L1 cases assert the two deliverable files exist, are non-empty, and that the
validator exposes a default export.

L2 cases independently EXERCISE the real validator behavior. Rather than
trusting the agent's own ``validateShape-test.js``, each L2 method writes ITS
OWN focused Jest probe spec into ``packages/shared/__tests__/`` and runs that
single spec through the repo's native Jest CLI (``yarn test <path>`` ->
``node scripts/jest/jest-cli.js <path>``, which forwards the path as a
testPathPattern). Each probe ``require``s ``'shared/validateShape'`` exactly
like the repo's own shared tests (Jest haste: ``roots: ['<rootDir>/packages']``)
and deep-validates exactly ONE behavior from the requirement doc:

  * valid value matching every field -> returns ``[]``
  * a missing required field -> exactly one violation referencing that field
  * an absent non-required field -> no violation
  * precise type checks: number rejects ``NaN``; array vs plain object;
    object vs array/null
  * a present, well-typed value -> no violation for that field
  * an unexpected (unknown) key -> one "unexpected field" violation
  * ordering: declared-field violations in schema order, then unexpected
    fields in lexicographic order
  * messages carry concrete content (field name, expected/actual type)
  * ``TypeError`` thrown for a non-object ``schema`` and for a non-object
    ``value`` (including ``null`` and arrays where the doc forbids them)

Because each behavior is its own probe spec and its own pytest method, a
partial / stubbed solution (e.g. one that always returns ``[]``, ignores
``required``, or skips the unexpected-key / ordering rules) fails the SPECIFIC
behavior it got wrong instead of one monolithic probe. We also confirm the
agent's own suite runs green via the exact Acceptance-Criteria command.
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

SRC_REL = "packages/shared/validateShape.js"
AGENT_TEST_REL = "packages/shared/__tests__/validateShape-test.js"

PROBE_DIR_REL = "packages/shared/__tests__"
PROBE_PREFIX = "validateShape-probe-"


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


# Shared JS preamble. Pulls the validator's default export and provides a tiny
# helper to find how many messages mention a given field name. Fully
# deterministic: no timers, network, or randomness.
_PREAMBLE = """\
'use strict';

function load() {
  return require('shared/validateShape').default;
}

function mentioning(messages, field) {
  return messages.filter(m => String(m).includes(field));
}
"""


def _make_probe(body):
    return _PREAMBLE + "\n" + textwrap.dedent(body) + "\n"


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
    def test_validator_source_exists(self):
        """L1: the validator module file exists and is non-empty."""
        path = _src_path()
        assert os.path.isfile(path), f"missing deliverable: {SRC_REL}"
        assert os.path.getsize(path) > 0, "validator source is empty"

    def test_agent_test_file_exists(self):
        """L1: the agent's Jest test suite file exists and is non-empty."""
        path = _agent_test_path()
        assert os.path.isfile(path), f"missing deliverable: {AGENT_TEST_REL}"
        assert os.path.getsize(path) > 0, "agent test file is empty"

    def test_validator_has_default_export(self):
        """L1: the validator exposes a default export (the function)."""
        src = _read_src()
        assert "export default" in src or "module.exports" in src, (
            "validateShape must export the function by default"
        )

    # -----------------------------------------------------------------------
    # L2 — each behavior gets its OWN independent probe spec run via Jest.
    # -----------------------------------------------------------------------
    def test_valid_value_returns_empty_array(self):
        """L2: a value matching every declared field returns ``[]``.

        A correct validator returns an empty array (not undefined/null) for a
        fully conforming value across all six supported types.
        """
        result = _run_probe(
            "valid",
            """
            it('valid value across all types returns []', () => {
              const validateShape = load();
              const schema = {
                s: {type: 'string', required: true},
                n: {type: 'number', required: true},
                b: {type: 'boolean'},
                f: {type: 'function'},
                a: {type: 'array'},
                o: {type: 'object'},
              };
              const value = {
                s: 'hi', n: 3, b: false, f: () => {}, a: [1, 2], o: {k: 1},
              };
              const errs = validateShape(schema, value);
              expect(Array.isArray(errs)).toBe(true);
              expect(errs).toEqual([]);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"valid-passthrough probe failed:\n{out[-4000:]}"

    def test_missing_required_field_one_violation(self):
        """L2: a missing required field yields exactly one violation for it.

        When a ``required: true`` key is absent from ``value``, the result has
        exactly one message and it references that field by name. A stub that
        ignores ``required`` (returns ``[]``) fails here.
        """
        result = _run_probe(
            "missing-required",
            """
            it('missing required field -> exactly one violation naming it', () => {
              const validateShape = load();
              const schema = {name: {type: 'string', required: true}};
              const errs = validateShape(schema, {});
              expect(errs).toHaveLength(1);
              expect(mentioning(errs, 'name')).toHaveLength(1);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"missing-required probe failed:\n{out[-4000:]}"

    def test_absent_optional_field_no_violation(self):
        """L2: an absent, non-required field produces no violation.

        A field with ``required`` omitted/false that is missing from ``value``
        must NOT be reported. A validator that flags every missing key fails.
        """
        result = _run_probe(
            "absent-optional",
            """
            it('absent optional field -> no violation', () => {
              const validateShape = load();
              const schema = {opt: {type: 'string'}};
              expect(validateShape(schema, {})).toEqual([]);
              const schema2 = {opt: {type: 'string', required: false}};
              expect(validateShape(schema2, {})).toEqual([]);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"absent-optional probe failed:\n{out[-4000:]}"

    def test_number_type_rejects_nan(self):
        """L2: a ``'number'`` field given ``NaN`` is a type mismatch.

        ``NaN`` is ``typeof 'number'`` but the doc requires it be rejected. A
        present, well-typed number must pass; ``NaN`` must produce exactly one
        violation naming the field.
        """
        result = _run_probe(
            "number-nan",
            """
            it('number field rejects NaN but accepts a real number', () => {
              const validateShape = load();
              const schema = {n: {type: 'number'}};
              expect(validateShape(schema, {n: 7})).toEqual([]);
              const errs = validateShape(schema, {n: NaN});
              expect(errs).toHaveLength(1);
              expect(mentioning(errs, 'n')).toHaveLength(1);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"number-NaN probe failed:\n{out[-4000:]}"

    def test_array_vs_object_distinction(self):
        """L2: ``'array'`` matches arrays only; a plain object is a mismatch.

        A field declared ``'array'`` accepts ``[]`` but rejects ``{}``, and a
        ``'object'`` field accepts ``{}`` but rejects ``[]`` and ``null``.
        """
        result = _run_probe(
            "array-object",
            """
            it('array/object type checks are precise', () => {
              const validateShape = load();
              const arrSchema = {a: {type: 'array'}};
              expect(validateShape(arrSchema, {a: [1]})).toEqual([]);
              expect(validateShape(arrSchema, {a: {}})).toHaveLength(1);

              const objSchema = {o: {type: 'object'}};
              expect(validateShape(objSchema, {o: {x: 1}})).toEqual([]);
              expect(validateShape(objSchema, {o: [1]})).toHaveLength(1);
              expect(validateShape(objSchema, {o: null})).toHaveLength(1);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"array-object probe failed:\n{out[-4000:]}"

    def test_type_mismatch_message_content(self):
        """L2: a type-mismatch message names the field and expected type.

        The doc requires messages naming the field, the expected type, and the
        actual type. We assert the field name and the declared type string both
        appear in the single mismatch message.
        """
        result = _run_probe(
            "mismatch-message",
            """
            it('type mismatch message carries field + expected type', () => {
              const validateShape = load();
              const schema = {age: {type: 'number'}};
              const errs = validateShape(schema, {age: 'not-a-number'});
              expect(errs).toHaveLength(1);
              const msg = errs[0];
              expect(msg).toContain('age');
              expect(msg).toContain('number');
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"mismatch-message probe failed:\n{out[-4000:]}"

    def test_unexpected_key_appended(self):
        """L2: an unknown key produces one trailing "unexpected field" violation.

        A key present in ``value`` but absent from ``schema`` is reported. With
        an otherwise-valid declared field, the only violation is the unexpected
        one and it names the offending key.
        """
        result = _run_probe(
            "unexpected-key",
            """
            it('unknown key -> one unexpected-field violation naming it', () => {
              const validateShape = load();
              const schema = {keep: {type: 'string'}};
              const errs = validateShape(schema, {keep: 'ok', extra: 1});
              expect(errs).toHaveLength(1);
              expect(mentioning(errs, 'extra')).toHaveLength(1);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"unexpected-key probe failed:\n{out[-4000:]}"

    def test_violation_ordering_declared_then_unexpected(self):
        """L2: declared-field violations precede unexpected ones (lex order).

        With multiple violations, declared-field messages appear in schema
        declaration order, then unexpected-field messages sorted
        lexicographically. We assert both the field that owns each message and
        the relative ordering by index.
        """
        result = _run_probe(
            "ordering",
            """
            it('declared violations in schema order, then unexpected lexicographic', () => {
              const validateShape = load();
              const schema = {
                first: {type: 'string', required: true},
                second: {type: 'number'},
              };
              // first missing (required), second wrong type, plus two extras.
              const value = {second: 'bad', zeta: 1, alpha: 2};
              const errs = validateShape(schema, value);
              expect(errs).toHaveLength(4);
              const idxFirst = errs.findIndex(m => m.includes('first'));
              const idxSecond = errs.findIndex(m => m.includes('second'));
              const idxAlpha = errs.findIndex(m => m.includes('alpha'));
              const idxZeta = errs.findIndex(m => m.includes('zeta'));
              // declared fields in schema order
              expect(idxFirst).toBe(0);
              expect(idxSecond).toBe(1);
              // unexpected fields after declared ones, lexicographically sorted
              expect(idxAlpha).toBe(2);
              expect(idxZeta).toBe(3);
              expect(idxAlpha).toBeGreaterThan(idxSecond);
              expect(idxZeta).toBeGreaterThan(idxAlpha);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"ordering probe failed:\n{out[-4000:]}"

    def test_boolean_and_function_types(self):
        """L2: ``'boolean'`` and ``'function'`` checks are exact.

        A boolean field rejects the string ``'true'``; a function field rejects
        a non-callable. Correct values for each pass with no violation.
        """
        result = _run_probe(
            "bool-fn",
            """
            it('boolean and function type checks are exact', () => {
              const validateShape = load();
              const bSchema = {flag: {type: 'boolean'}};
              expect(validateShape(bSchema, {flag: true})).toEqual([]);
              expect(validateShape(bSchema, {flag: 'true'})).toHaveLength(1);

              const fSchema = {cb: {type: 'function'}};
              expect(validateShape(fSchema, {cb: () => {}})).toEqual([]);
              expect(validateShape(fSchema, {cb: 123})).toHaveLength(1);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"boolean-function probe failed:\n{out[-4000:]}"

    def test_typeerror_for_non_object_inputs(self):
        """L2: a non-object ``schema`` or ``value`` throws ``TypeError``.

        ``null``, arrays, numbers, strings, and ``undefined`` are all invalid
        for either argument and must raise ``TypeError`` (not return an array).
        """
        result = _run_probe(
            "typeerror",
            """
            it('non-object schema or value -> TypeError', () => {
              const validateShape = load();
              const goodSchema = {x: {type: 'string'}};
              const goodValue = {x: 'ok'};
              // bad schema
              expect(() => validateShape(null, goodValue)).toThrow(TypeError);
              expect(() => validateShape(undefined, goodValue)).toThrow(TypeError);
              expect(() => validateShape(42, goodValue)).toThrow(TypeError);
              expect(() => validateShape('s', goodValue)).toThrow(TypeError);
              // bad value
              expect(() => validateShape(goodSchema, null)).toThrow(TypeError);
              expect(() => validateShape(goodSchema, undefined)).toThrow(TypeError);
              expect(() => validateShape(goodSchema, 7)).toThrow(TypeError);
              expect(() => validateShape(goodSchema, 'nope')).toThrow(TypeError);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"TypeError-guard probe failed:\n{out[-4000:]}"

    def test_required_and_type_independent(self):
        """L2: a present-but-wrong-typed required field is a single mismatch.

        A required field that IS present but has the wrong type must produce a
        type-mismatch (not a missing-required) violation — exactly one message,
        naming the field. This separates "checks presence" from "checks type".
        """
        result = _run_probe(
            "required-type",
            """
            it('present required field with wrong type -> one mismatch', () => {
              const validateShape = load();
              const schema = {id: {type: 'string', required: true}};
              const errs = validateShape(schema, {id: 99});
              expect(errs).toHaveLength(1);
              expect(mentioning(errs, 'id')).toHaveLength(1);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"required-type probe failed:\n{out[-4000:]}"

    # -----------------------------------------------------------------------
    # L2 — the agent's own suite must pass via the spec'd command.
    # -----------------------------------------------------------------------
    def test_agent_suite_passes(self):
        """L2: the agent's own Jest suite passes via the Acceptance command.

        Mirrors the Acceptance Criteria command exactly:
        ``yarn test packages/shared/__tests__/validateShape-test.js``.
        """
        result = _yarn_test(AGENT_TEST_REL, timeout=300)
        ok, out = _jest_passed(result)
        assert ok, f"agent suite did not pass green:\n{out[-4000:]}"

    def test_agent_suite_has_multiple_independent_cases(self):
        """L2: the agent suite must contain several independent passing cases.

        The requirement mandates independent cases per behavior, so a single
        trivial test would not satisfy it; require a multi-case green run.
        """
        result = _yarn_test(AGENT_TEST_REL, timeout=300)
        out = (result.stdout or "") + "\n" + (result.stderr or "")
        assert result.returncode == 0, f"agent suite nonzero rc:\n{out[-3000:]}"
        m = re.search(r"Tests:\s+(\d+) passed", out)
        assert m is not None, f"no passing summary in agent run:\n{out[-3000:]}"
        assert int(m.group(1)) >= 5, (
            f"agent suite should have multiple cases, saw {m.group(1)}"
        )
