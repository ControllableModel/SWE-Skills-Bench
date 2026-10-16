"""
Test for the 'kysely-query-builder' skill (variant ext9) — Add a
``jsonMergePatch`` helper for the MySQL dialect.

Variant task
------------
The agent must add and export a new ``jsonMergePatch`` function from
``src/helpers/mysql.ts``. The function takes a single argument: an array
(tuple) of ``Expression<unknown>`` documents and returns a single
``RawBuilder`` expression that can be aliased with ``.as(...)`` inside a
``select(...)`` callback. It must compile to MySQL's
``json_merge_patch(<arg0>, <arg1>, ...)`` with:

  * column references rendered with MySQL backtick identifier quoting,
  * ``eb.val(...)`` values emitted as ``?`` bound-parameter placeholders and
    collected, in order, into the ``parameters`` array (NEVER inlined),
  * raw ``sql`` fragments emitted verbatim,
  * arguments joined left-to-right in input order with ``, `` and exactly one
    pair of call parentheses (no trailing separator),
  * a single-argument call still compiling to a valid
    ``json_merge_patch(<arg0>)``.

The agent must also create ``test/node/src/json-merge-patch-mysql.test.ts``.

Strategy / discriminative power
-------------------------------
L1 checks confirm the deliverable files exist and export the symbol, and that
the existing helpers are left intact.

L2 checks do NOT trust the agent's own test file. Instead this harness:
  1. builds the kysely library (``pnpm build``) once,
  2. writes its OWN TypeScript driver into ``test/node/src/`` that imports the
     freshly-built ``jsonMergePatch`` helper, builds a ``Kysely`` instance with
     the MySQL adapter + query compiler + ``DummyDriver`` (no DB / network),
     constructs ``select`` queries, calls ``.compile()`` and ``console.log``s
     the produced ``sql`` + ``parameters`` as JSON,
  3. compiles the node test sources (``pnpm test:node:build`` — this also
     type-checks the new ``jsonMergePatch`` signature, since our driver invokes
     it), and runs the driver under mocha,
  4. parses the emitted JSON and asserts on exact SQL strings, exact parameter
     arrays, argument ordering, the MySQL ``json_merge_patch`` function name,
     verbatim raw fragments and the single-argument edge case.

A naive solution (wrong SQL function name, inlined values, wrong ordering,
trailing separator, hard-coded output, or a non-compiling type signature) fails
these tests because the real Kysely compiler is exercised end-to-end.
"""

import json
import os
import re
import subprocess

import pytest


REPO_DIR = "/workspace/kysely"

MYSQL_HELPER = os.path.join(REPO_DIR, "src", "helpers", "mysql.ts")
NEW_TEST_TS = os.path.join(
    REPO_DIR, "test", "node", "src", "json-merge-patch-mysql.test.ts"
)

# Where this harness drops its own independent driver (NOT the agent's file).
DRIVER_NAME = "zzz-json-merge-patch-mysql-probe"
DRIVER_TS = os.path.join(REPO_DIR, "test", "node", "src", DRIVER_NAME + ".ts")
DRIVER_JS = os.path.join(REPO_DIR, "test", "node", "dist", DRIVER_NAME + ".js")

# Markers used to extract our JSON payloads from the mocha stdout stream.
BEGIN = "@@PROBE_BEGIN@@"
END = "@@PROBE_END@@"


# ---------------------------------------------------------------------------
# Driver test (TypeScript) written into the repo by this harness.
# Uses the MySQL adapter/compiler + DummyDriver pattern from the kysely repo.
# ---------------------------------------------------------------------------
DRIVER_SOURCE = r"""
import {
  DummyDriver,
  Kysely,
  MysqlAdapter,
  MysqlIntrospector,
  MysqlQueryCompiler,
  sql,
} from '../../../dist/index.js'
import { jsonMergePatch } from '../../../dist/helpers/mysql.js'

interface DB {
  person: {
    id: number
    a: unknown
    b: unknown
  }
}

const db = new Kysely<DB>({
  dialect: {
    createAdapter: () => new MysqlAdapter(),
    createDriver: () => new DummyDriver(),
    createIntrospector: (db) => new MysqlIntrospector(db),
    createQueryCompiler: () => new MysqlQueryCompiler(),
  },
})

function emit(label: string, sqlText: string, parameters: readonly unknown[]) {
  console.log('@@PROBE_BEGIN@@' + JSON.stringify({
    label,
    sql: sqlText,
    parameters,
  }) + '@@PROBE_END@@')
}

describe('json-merge-patch-mysql probe', () => {
  it('emits compiled output for every scenario', () => {
    // --- two column refs ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) =>
          jsonMergePatch([eb.ref('a'), eb.ref('b')]).as('merged'),
        )
        .compile()
      emit('two_refs', c.sql, c.parameters)
    }

    // --- ref + eb.val (bound parameter) ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) =>
          jsonMergePatch([eb.ref('a'), eb.val('{"x":1}')]).as('merged'),
        )
        .compile()
      emit('ref_val', c.sql, c.parameters)
    }

    // --- raw sql fragment + two refs (ordering, verbatim raw first) ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) =>
          jsonMergePatch([sql`'{}'`, eb.ref('a'), eb.ref('b')]).as('merged'),
        )
        .compile()
      emit('raw_first', c.sql, c.parameters)
    }

    // --- single argument edge case ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) => jsonMergePatch([eb.ref('a')]).as('merged'))
        .compile()
      emit('single', c.sql, c.parameters)
    }

    // --- multiple eb.val args, parameter ordering ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) =>
          jsonMergePatch([eb.val('p'), eb.val('q'), eb.val('r')]).as('merged'),
        )
        .compile()
      emit('multi_val', c.sql, c.parameters)
    }

    // --- mixed: ref, val, raw (ordering + selective parameter collection) ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) =>
          jsonMergePatch([
            eb.ref('a'),
            eb.val('mid'),
            sql`'{}'`,
          ]).as('merged'),
        )
        .compile()
      emit('mixed', c.sql, c.parameters)
    }
  })
})
"""


# ---------------------------------------------------------------------------
# Module-scoped fixture: build lib + node tests once, run the probe, capture.
# ---------------------------------------------------------------------------
_PROBE_CACHE = {}


def _run(cmd, timeout, cwd=REPO_DIR):
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=True,
    )


@pytest.fixture(scope="module")
def probe():
    """Build the lib, compile + run the harness's own driver, return parsed results."""
    if _PROBE_CACHE:
        return _PROBE_CACHE

    assert os.path.isdir(REPO_DIR), f"repo dir missing: {REPO_DIR}"

    # 1. install deps only if they are missing. In the benchmark container the
    #    repo toolchain is already installed; if so we skip the (network-bound)
    #    install entirely. We never hard-fail on install output — the build step
    #    below is the real gate.
    if not os.path.isdir(os.path.join(REPO_DIR, "node_modules", ".bin")):
        try:
            _run("pnpm install --prefer-offline", timeout=600)
        except subprocess.TimeoutExpired:
            pass

    # 2. build the library (produces dist/, dist/helpers/*.js)
    build = _run("pnpm build", timeout=600)
    assert build.returncode == 0, (
        "pnpm build failed:\nSTDOUT:\n"
        + build.stdout[-4000:]
        + "\nSTDERR:\n"
        + build.stderr[-4000:]
    )
    assert os.path.isfile(
        os.path.join(REPO_DIR, "dist", "helpers", "mysql.js")
    ), "dist/helpers/mysql.js not produced by build"

    # 3. drop our independent driver into the node test sources.
    with open(DRIVER_TS, "w") as f:
        f.write(DRIVER_SOURCE)

    try:
        # 4. compile the node test sources (this also type-checks the agent's
        #    new jsonMergePatch signature, since our driver invokes it).
        tsb = _run("pnpm test:node:build", timeout=600)
        assert tsb.returncode == 0, (
            "pnpm test:node:build (tsc) failed — the jsonMergePatch helper does "
            "not type-check:\nSTDOUT:\n"
            + tsb.stdout[-4000:]
            + "\nSTDERR:\n"
            + tsb.stderr[-4000:]
        )
        assert os.path.isfile(DRIVER_JS), "compiled probe driver missing"

        # 5. run only our driver under mocha.
        run = _run(
            "npx mocha --timeout 15000 " + DRIVER_JS,
            timeout=300,
        )
        out = run.stdout + "\n" + run.stderr
        assert run.returncode == 0, (
            "probe driver failed under mocha:\n" + out[-6000:]
        )
    finally:
        # tidy up our injected files so we don't pollute the repo.
        for p in (DRIVER_TS, DRIVER_JS):
            try:
                os.remove(p)
            except OSError:
                pass

    results = {}
    for m in re.finditer(re.escape(BEGIN) + r"(.*?)" + re.escape(END), out, re.S):
        payload = json.loads(m.group(1))
        results[payload["label"]] = payload

    assert results, "no probe output captured from mocha run:\n" + out[-4000:]
    _PROBE_CACHE.update(results)
    return _PROBE_CACHE


class TestKyselyQueryBuilder:
    """jsonMergePatch helper for the MySQL dialect."""

    REPO_DIR = "/workspace/kysely"

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and export the symbol
    # ------------------------------------------------------------------

    def test_mysql_helper_file_exists(self):
        """src/helpers/mysql.ts must exist."""
        assert os.path.isfile(MYSQL_HELPER), f"missing {MYSQL_HELPER}"

    def test_mysql_exports_json_merge_patch(self):
        """mysql.ts must declare an exported `jsonMergePatch` function."""
        with open(MYSQL_HELPER) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+jsonMergePatch\b", src
        ), "no `export function jsonMergePatch` in src/helpers/mysql.ts"

    def test_existing_helpers_preserved(self):
        """The three existing exported helpers must remain exported and untouched."""
        with open(MYSQL_HELPER) as f:
            src = f.read()
        for name in ("jsonArrayFrom", "jsonObjectFrom", "jsonBuildObject"):
            assert re.search(
                r"export\s+function\s+" + name + r"\b", src
            ), f"existing helper `{name}` no longer exported from mysql.ts"

    def test_new_node_test_file_exists(self):
        """The required new node test file must be created by the agent."""
        assert os.path.isfile(
            NEW_TEST_TS
        ), "test/node/src/json-merge-patch-mysql.test.ts was not created"

    # ------------------------------------------------------------------
    # L2 — dynamic compilation behavior (via the harness's own driver)
    # ------------------------------------------------------------------

    def test_two_column_refs_sql(self, probe):
        """Two column refs compile to json_merge_patch with backtick idents, no params."""
        r = probe["two_refs"]
        assert (
            r["sql"].rstrip()
            == "select json_merge_patch(`a`, `b`) as `merged` from `person`"
        ), f"unexpected sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"

    def test_uses_correct_mysql_function_name(self, probe):
        """Must use MySQL json_merge_patch (not json_merge / json_merge_preserve / json_object)."""
        s = probe["two_refs"]["sql"]
        assert "json_merge_patch(" in s, f"missing json_merge_patch(): {s!r}"
        # the close variants must not be emitted
        assert (
            "json_merge_preserve(" not in s
        ), f"must not use json_merge_preserve(): {s!r}"
        assert not re.search(
            r"json_merge\s*\(", s
        ), f"must not use bare json_merge(): {s!r}"
        assert "json_object(" not in s, f"must not use json_object(): {s!r}"

    def test_backtick_identifier_quoting(self, probe):
        """Column refs must be wrapped with MySQL backticks, not double quotes."""
        s = probe["two_refs"]["sql"]
        assert "`a`" in s and "`b`" in s, f"refs not backtick-quoted: {s!r}"
        # MySQL must not use ANSI double-quoted identifiers here.
        assert '"a"' not in s and '"b"' not in s, f"used double quotes: {s!r}"

    def test_val_is_bound_parameter(self, probe):
        """eb.val('{\"x\":1}') must become a ? placeholder collected as a param."""
        r = probe["ref_val"]
        assert (
            r["sql"].rstrip()
            == "select json_merge_patch(`a`, ?) as `merged` from `person`"
        ), f"unexpected ref+val sql: {r['sql']!r}"
        assert r["parameters"] == [
            '{"x":1}'
        ], f"expected ['{{\"x\":1}}'] params, got {r['parameters']!r}"
        # value must NOT be inlined as a literal in the SQL text.
        assert (
            '{"x":1}' not in r["sql"]
        ), f"value was inlined into SQL: {r['sql']!r}"

    def test_raw_fragment_verbatim_and_order(self, probe):
        """A raw sql`'{}'` fragment must be emitted verbatim as the first arg, refs after."""
        r = probe["raw_first"]
        assert (
            r["sql"].rstrip()
            == "select json_merge_patch('{}', `a`, `b`) as `merged` from `person`"
        ), f"unexpected raw-first sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"
        inner = re.search(r"json_merge_patch\((.*?)\) as", r["sql"]).group(1)
        assert inner == "'{}', `a`, `b`", f"bad arg order/list: {inner!r}"

    def test_single_argument_compiles(self, probe):
        """A single-argument call must still compile to a valid json_merge_patch(<arg0>)."""
        r = probe["single"]
        assert (
            r["sql"].rstrip()
            == "select json_merge_patch(`a`) as `merged` from `person`"
        ), f"unexpected single-arg sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"
        inner = re.search(r"json_merge_patch\((.*?)\) as", r["sql"]).group(1)
        assert inner == "`a`", f"single arg should have no separator: {inner!r}"
        assert "," not in inner, f"single-arg call must have no comma: {inner!r}"

    def test_multi_val_parameter_ordering(self, probe):
        """Multiple eb.val args produce ?, ?, ? with params collected in input order."""
        r = probe["multi_val"]
        assert (
            r["sql"].rstrip()
            == "select json_merge_patch(?, ?, ?) as `merged` from `person`"
        ), f"unexpected multi-val sql: {r['sql']!r}"
        assert r["parameters"] == [
            "p",
            "q",
            "r",
        ], f"bad params/ordering: {r['parameters']!r}"

    def test_mixed_args_order_and_selective_params(self, probe):
        """Mixed ref/val/raw args: ordering preserved; only the val becomes a param."""
        r = probe["mixed"]
        assert (
            r["sql"].rstrip()
            == "select json_merge_patch(`a`, ?, '{}') as `merged` from `person`"
        ), f"unexpected mixed sql: {r['sql']!r}"
        assert r["parameters"] == [
            "mid"
        ], f"only the eb.val should be a param, got {r['parameters']!r}"
        inner = re.search(r"json_merge_patch\((.*?)\) as", r["sql"]).group(1)
        assert inner == "`a`, ?, '{}'", f"bad mixed arg list/order: {inner!r}"

    def test_no_trailing_separator_and_single_paren(self, probe):
        """No trailing `, `, exactly one json_merge_patch( call, balanced parens."""
        for label in ("two_refs", "raw_first", "multi_val", "mixed", "single"):
            s = probe[label]["sql"]
            assert ", )" not in s, f"trailing separator in {label}: {s!r}"
            assert (
                s.count("json_merge_patch(") == 1
            ), f"expected exactly one json_merge_patch( in {label}: {s!r}"
            assert s.count("(") == s.count(")"), f"unbalanced parens in {label}: {s!r}"

    def test_arguments_comma_space_separated(self, probe):
        """Three-arg calls must join arguments with `, ` (comma + single space)."""
        for label in ("raw_first", "multi_val", "mixed"):
            inner = re.search(
                r"json_merge_patch\((.*?)\) as", probe[label]["sql"]
            ).group(1)
            parts = inner.split(", ")
            assert len(parts) == 3, f"{label}: expected 3 comma-space parts: {inner!r}"
            # no part should carry a stray leading/trailing space (no `,` only joins).
            for p in parts:
                assert p == p.strip(), f"{label}: stray spacing in part {p!r}"
