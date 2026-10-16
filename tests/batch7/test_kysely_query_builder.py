"""
Test for the 'kysely-query-builder' skill (variant ext7) — add an MSSQL
``jsonValue`` path-extraction helper.

Variant task
------------
The agent must add and export a new ``jsonValue`` function to the MS SQL Server
helper module ``src/helpers/mssql.ts``. It takes two arguments in order:

  1. ``document``: an ``Expression<unknown>`` (column ref / ``eb.val(...)`` /
     raw ``sql`` fragment),
  2. ``path``: a ``string`` JSON path (e.g. ``'$.name'``),

and returns a ``RawBuilder`` that compiles to MSSQL's
``json_value(<document>, <path>)`` where:

  * the ``document`` argument is compiled through normal Kysely expression
    compilation — a column ref is double-quoted (``"data"``); an ``eb.val(...)``
    value becomes an ``@N`` placeholder collected into ``parameters``; a raw
    ``sql`` fragment is emitted verbatim,
  * the ``path`` argument is ALWAYS emitted as a single bound parameter
    (an ``@N`` placeholder collected into ``parameters``) — it must NOT be
    inlined into the SQL text as a literal,
  * exactly one pair of parentheses, the two arguments separated by ``, ``.

The agent must also create the node test file
``test/node/src/json-value-mssql.test.ts``.

Verification strategy / discriminative power
--------------------------------------------
L1 checks confirm the deliverable files exist and that ``jsonValue`` is
exported from the MSSQL helper module.

L2 checks do NOT trust the agent's own test file. Instead this harness:

  1. builds the kysely library (``pnpm build``) once,
  2. writes its OWN TypeScript driver into ``test/node/src/`` that imports the
     freshly-built ``jsonValue`` helper, builds a ``Kysely`` instance wired with
     the MSSQL adapter + ``MssqlQueryCompiler`` + ``DummyDriver`` (no DB /
     network), calls ``.compile()`` for several scenarios and ``console.log``s
     the produced ``sql`` + ``parameters`` as JSON,
  3. compiles the node test sources (``pnpm test:node:build`` — this also
     type-checks the agent's new ``jsonValue`` signature, since the driver calls
     it and assigns the result type to ``string | null``),
  4. parses the emitted JSON and asserts on the exact SQL strings, exact
     parameter arrays and argument ordering.

A naive solution fails these tests because the real Kysely compiler is run
end to end:

  * wrong function name (e.g. ``json_query`` / ``json_extract``) → SQL mismatch,
  * inlining the path as a literal (``'$.name'`` in the SQL text) instead of
    binding it → parameter array / SQL mismatch,
  * dropping/ignoring the ``document`` argument → SQL mismatch,
  * swapping argument order → parameter ordering mismatch,
  * a non-compiling or ``any``-typed signature → ``tsc`` failure in step 3.
"""

import json
import os
import re
import subprocess

import pytest


REPO_DIR = "/workspace/kysely"

MSSQL_HELPER = os.path.join(REPO_DIR, "src", "helpers", "mssql.ts")
NEW_TEST_TS = os.path.join(
    REPO_DIR, "test", "node", "src", "json-value-mssql.test.ts"
)

# Where this harness drops its own independent driver (NOT the agent's file).
DRIVER_NAME = "zzz-json-value-mssql-probe"
DRIVER_TS = os.path.join(REPO_DIR, "test", "node", "src", DRIVER_NAME + ".ts")
DRIVER_JS = os.path.join(REPO_DIR, "test", "node", "dist", DRIVER_NAME + ".js")

# Markers used to extract our JSON payloads from the mocha stdout stream.
BEGIN = "@@PROBE_BEGIN@@"
END = "@@PROBE_END@@"


# ---------------------------------------------------------------------------
# Driver test (TypeScript) written into the repo by this harness.
# Uses the MSSQL adapter/compiler + DummyDriver pattern from the kysely repo.
# Note: the result type of jsonValue is asserted to be `string | null` by
# assigning the compiled raw builder through a typed helper variable, so a
# wrong / `any` type signature fails `tsc` in test:node:build.
# ---------------------------------------------------------------------------
DRIVER_SOURCE = r"""
import {
  DummyDriver,
  Kysely,
  MssqlAdapter,
  MssqlIntrospector,
  MssqlQueryCompiler,
  RawBuilder,
  sql,
} from '../../../dist/index.js'
import { jsonValue } from '../../../dist/helpers/mssql.js'

interface DB {
  person: {
    id: number
    first_name: string | null
    last_name: string | null
    data: string
  }
}

const db = new Kysely<DB>({
  dialect: {
    createAdapter: () => new MssqlAdapter(),
    createDriver: () => new DummyDriver(),
    createIntrospector: (d) => new MssqlIntrospector(d),
    createQueryCompiler: () => new MssqlQueryCompiler(),
  },
})

function emit(label: string, sqlText: string, parameters: readonly unknown[]) {
  console.log('@@PROBE_BEGIN@@' + JSON.stringify({
    label,
    sql: sqlText,
    parameters,
  }) + '@@PROBE_END@@')
}

// Type-level assertion: jsonValue(...) must be a RawBuilder<string | null>.
// If the agent's signature returns `any` or a different value type this
// assignment / parameter type fails to compile under `tsc`.
function expectStringNull(rb: RawBuilder<string | null>): RawBuilder<string | null> {
  return rb
}

describe('json-value-mssql probe', () => {
  it('emits compiled output for every scenario', () => {
    // --- column-ref document + string path ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) => expectStringNull(jsonValue(eb.ref('data'), '$.name')).as('name'))
        .compile()
      emit('ref_doc', c.sql, c.parameters)
    }

    // --- eb.val document + string path (both bound, in arg order) ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) => expectStringNull(jsonValue(eb.val('{}'), '$.x')).as('x'))
        .compile()
      emit('val_doc', c.sql, c.parameters)
    }

    // --- raw sql fragment document + string path (fragment verbatim) ---
    {
      const c = db
        .selectFrom('person')
        .select(() => expectStringNull(jsonValue(sql`data`, '$.a.b')).as('ab'))
        .compile()
      emit('raw_doc', c.sql, c.parameters)
    }

    // --- two jsonValue calls in one select: parameter numbering / ordering ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) => [
          expectStringNull(jsonValue(eb.ref('data'), '$.first')).as('a'),
          expectStringNull(jsonValue(eb.ref('data'), '$.second')).as('b'),
        ])
        .compile()
      emit('two_calls', c.sql, c.parameters)
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
    #    install entirely. The build step below is the real gate.
    if not os.path.isdir(os.path.join(REPO_DIR, "node_modules", ".bin")):
        try:
            _run("pnpm install --prefer-offline", timeout=600)
        except subprocess.TimeoutExpired:
            pass

    # 2. build the library (produces dist/, dist/helpers/*.js)
    build = _run("pnpm build", timeout=900)
    assert build.returncode == 0, (
        "pnpm build failed:\nSTDOUT:\n"
        + build.stdout[-4000:]
        + "\nSTDERR:\n"
        + build.stderr[-4000:]
    )
    assert os.path.isfile(
        os.path.join(REPO_DIR, "dist", "helpers", "mssql.js")
    ), "dist/helpers/mssql.js not produced by build"

    # 3. drop our independent driver into the node test sources.
    with open(DRIVER_TS, "w") as f:
        f.write(DRIVER_SOURCE)

    try:
        # 4. compile the node test sources (this also type-checks the agent's
        #    new jsonValue signature, since our driver invokes it and binds the
        #    result through RawBuilder<string | null>).
        tsb = _run("pnpm test:node:build", timeout=900)
        assert tsb.returncode == 0, (
            "pnpm test:node:build (tsc) failed — the jsonValue helper does not "
            "type-check as RawBuilder<string | null>:\nSTDOUT:\n"
            + tsb.stdout[-4000:]
            + "\nSTDERR:\n"
            + tsb.stderr[-4000:]
        )
        assert os.path.isfile(DRIVER_JS), "compiled probe driver missing"

        # 5. run only our driver under mocha.
        run = _run("npx mocha --timeout 15000 " + DRIVER_JS, timeout=300)
        out = run.stdout + "\n" + run.stderr
        assert run.returncode == 0, "probe driver failed under mocha:\n" + out[-6000:]
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
    """MSSQL jsonValue path-extraction helper."""

    REPO_DIR = "/workspace/kysely"

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and export the symbol
    # ------------------------------------------------------------------

    def test_mssql_helper_file_exists(self):
        """src/helpers/mssql.ts must exist."""
        assert os.path.isfile(MSSQL_HELPER), f"missing {MSSQL_HELPER}"

    def test_mssql_exports_json_value(self):
        """mssql.ts must declare an exported `jsonValue` function."""
        with open(MSSQL_HELPER) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+jsonValue\b", src
        ), "no `export function jsonValue` in src/helpers/mssql.ts"

    def test_existing_helpers_still_exported(self):
        """Pre-existing helpers must remain exported (no accidental removal)."""
        with open(MSSQL_HELPER) as f:
            src = f.read()
        for name in ("jsonArrayFrom", "jsonObjectFrom", "jsonBuildObject"):
            assert re.search(
                r"export\s+function\s+" + name + r"\b", src
            ), f"existing helper `{name}` is no longer exported"

    def test_new_node_test_file_exists(self):
        """The required new node test file must be created by the agent."""
        assert os.path.isfile(
            NEW_TEST_TS
        ), "test/node/src/json-value-mssql.test.ts was not created"

    # ------------------------------------------------------------------
    # L2 — dynamic compilation behavior (via the harness's own driver)
    # ------------------------------------------------------------------

    def test_column_ref_document_sql(self, probe):
        """Column-ref doc compiles to json_value("data", @1) with the path bound."""
        r = probe["ref_doc"]
        assert (
            r["sql"]
            == 'select json_value("data", @1) as "name" from "person"'
        ), f"unexpected ref-doc sql: {r['sql']!r}"
        assert r["parameters"] == ["$.name"], (
            f"path must be the single bound param, got {r['parameters']!r}"
        )
        # the path must NOT be inlined as a literal anywhere in the SQL text.
        assert "$.name" not in r["sql"], f"path was inlined: {r['sql']!r}"
        assert "'" not in r["sql"], f"unexpected literal quoting: {r['sql']!r}"

    def test_uses_correct_function_name(self, probe):
        """Must use json_value( — not json_query/json_extract/json_object/etc."""
        s = probe["ref_doc"]["sql"]
        assert "json_value(" in s, f"missing json_value(): {s!r}"
        for wrong in ("json_query(", "json_extract(", "json_object(", "json_array("):
            assert wrong not in s, f"must not use {wrong}: {s!r}"
        # exactly one json_value call form.
        assert s.count("json_value(") == 1, f"expected one json_value(: {s!r}"

    def test_val_document_both_bound_in_order(self, probe):
        """eb.val doc + path: both bound as @1,@2 in argument order, neither inlined."""
        r = probe["val_doc"]
        assert (
            r["sql"] == 'select json_value(@1, @2) as "x" from "person"'
        ), f"unexpected val-doc sql: {r['sql']!r}"
        # document value first, then path — argument order preserved.
        assert r["parameters"] == ["{}", "$.x"], (
            f"params must be [doc, path] in order, got {r['parameters']!r}"
        )
        assert "'{}'" not in r["sql"], f"document value was inlined: {r['sql']!r}"
        assert "$.x" not in r["sql"], f"path was inlined: {r['sql']!r}"

    def test_raw_fragment_document_verbatim(self, probe):
        """Raw sql`data` doc emitted verbatim; path is the single bound param."""
        r = probe["raw_doc"]
        assert (
            r["sql"] == 'select json_value(data, @1) as "ab" from "person"'
        ), f"unexpected raw-doc sql: {r['sql']!r}"
        assert r["parameters"] == ["$.a.b"], (
            f"path must be the single bound param, got {r['parameters']!r}"
        )
        # the raw fragment `data` must be unquoted (verbatim), not "data".
        assert '"data"' not in r["sql"], f"raw fragment was quoted: {r['sql']!r}"
        assert "$.a.b" not in r["sql"], f"path was inlined: {r['sql']!r}"

    def test_single_paren_pair_and_separator(self, probe):
        """Exactly one paren pair around the two args, separated by ', '."""
        r = probe["ref_doc"]
        s = r["sql"]
        inner = re.search(r"json_value\((.*?)\) as", s)
        assert inner is not None, f"could not locate json_value(...) call: {s!r}"
        assert inner.group(1) == '"data", @1', (
            f"args must be '<doc>, <path-param>', got {inner.group(1)!r}"
        )
        assert ", )" not in s, f"trailing separator: {s!r}"
        assert s.count("(") == s.count(")"), f"unbalanced parens: {s!r}"

    def test_path_always_parameterized_for_all_doc_kinds(self, probe):
        """Across ref/val/raw document kinds, the path is always a bound @N param."""
        # The path string literal must never appear inline in any scenario.
        for label, path_str in (
            ("ref_doc", "$.name"),
            ("val_doc", "$.x"),
            ("raw_doc", "$.a.b"),
        ):
            s = probe[label]["sql"]
            assert path_str not in s, f"{label}: path inlined into sql: {s!r}"
            assert path_str in probe[label]["parameters"], (
                f"{label}: path {path_str!r} missing from params "
                f"{probe[label]['parameters']!r}"
            )

    def test_two_calls_parameter_numbering_and_ordering(self, probe):
        """Two jsonValue calls: placeholders @1,@2 in order, params in source order."""
        r = probe["two_calls"]
        assert (
            r["sql"]
            == 'select json_value("data", @1) as "a", '
            'json_value("data", @2) as "b" from "person"'
        ), f"unexpected two-call sql: {r['sql']!r}"
        assert r["parameters"] == ["$.first", "$.second"], (
            f"params must be in source order, got {r['parameters']!r}"
        )
        # both paths bound, neither inlined.
        for p in ("$.first", "$.second"):
            assert p not in r["sql"], f"path {p!r} was inlined: {r['sql']!r}"

    def test_document_argument_not_dropped(self, probe):
        """A stub that ignores `document` would lose the ref/val/raw arg — guard it."""
        # ref doc keeps "data"; val doc keeps its @1 param; raw doc keeps `data`.
        assert '"data"' in probe["ref_doc"]["sql"], probe["ref_doc"]["sql"]
        assert probe["val_doc"]["parameters"][0] == "{}", probe["val_doc"]
        assert re.search(
            r"json_value\(data,", probe["raw_doc"]["sql"]
        ), probe["raw_doc"]["sql"]
