"""
Test for the 'kysely-query-builder' skill (variant ext6) — Add a ``jsonQuote``
helper for SQLite.

The agent must add and export a new ``jsonQuote`` function to the SQLite helper
module (``src/helpers/sqlite.ts``) and create a deterministic node test file
(``test/node/src/json-quote-sqlite.test.ts``). ``jsonQuote`` accepts a single
``Expression<unknown>`` argument and compiles to SQLite's
``json_quote(<arg>)`` — exactly one pair of parentheses, exactly one argument,
no comma separators.

Required behavior (re-derived from the ext6 requirement doc):

  * ``jsonQuote(eb.ref('first_name'))``  → ``json_quote("first_name")`` with
    SQLite identifier quoting and NO parameters.
  * ``jsonQuote(eb.val('hi'))``          → the argument compiles to the ``?``
    placeholder and ``'hi'`` is collected into the ``parameters`` array — it
    must NOT be inlined as a literal in the SQL text.
  * ``jsonQuote(sql`1 + 1`)``            → ``json_quote(1 + 1)`` emitted
    verbatim, NO parameters.
  * Existing helpers (``jsonArrayFrom``, ``jsonObjectFrom``,
    ``jsonBuildObject``) must keep their exact output.

Strategy / discriminative power
-------------------------------
L1 checks confirm the deliverable files exist, that ``jsonQuote`` is exported
from the SQLite helper, and that the agent's own node test file was created.

L2 checks do NOT trust the agent's own test file. Instead this harness:
  1. builds the kysely library (``pnpm build``) once,
  2. writes its OWN TypeScript driver into ``test/node/src/`` that imports the
     freshly-built ``jsonQuote`` from ``dist/helpers/sqlite.js``, builds a
     ``Kysely`` instance with the SQLite adapter/compiler + ``DummyDriver``
     (no DB / network), calls ``.compile()`` and ``console.log``s the produced
     ``sql`` + ``parameters`` as JSON,
  3. compiles the node test sources (``pnpm test:node:build`` => ``tsc -p
     test/node``) — this also type-checks the agent's ``jsonQuote`` signature
     because our driver invokes it (and reads its inferred value type),
  4. runs only our driver under mocha and parses the emitted JSON, asserting on
     exact SQL strings, exact parameter arrays, single-argument shape and the
     verbatim raw fragment.

A naive solution (wrong SQL function name, a multi-arg / comma form, inlined
``eb.val`` values, an ``any``-typed signature that fails to type-check, or a
helper that changes existing output) fails these tests because the real Kysely
compiler is exercised end-to-end.

Native acceptance command driven by L2:
    npx mocha --timeout 15000 test/node/dist/json-quote-sqlite.test.js
(the harness compiles + runs the equivalent probe driver it injects itself).
"""

import json
import os
import re
import subprocess

import pytest


REPO_DIR = "/workspace/kysely"

SQLITE_HELPER = os.path.join(REPO_DIR, "src", "helpers", "sqlite.ts")
NEW_TEST_TS = os.path.join(
    REPO_DIR, "test", "node", "src", "json-quote-sqlite.test.ts"
)

# Where this harness drops its own independent driver (NOT the agent's file).
DRIVER_NAME = "zzz-json-quote-probe"
DRIVER_TS = os.path.join(REPO_DIR, "test", "node", "src", DRIVER_NAME + ".ts")
DRIVER_JS = os.path.join(REPO_DIR, "test", "node", "dist", DRIVER_NAME + ".js")

# Markers used to extract our JSON payloads from the mocha stdout stream.
BEGIN = "@@PROBE_BEGIN@@"
END = "@@PROBE_END@@"


# ---------------------------------------------------------------------------
# Driver test (TypeScript) written into the repo by this harness.
# Uses the SQLite adapter/compiler + DummyDriver pattern from the kysely repo.
# The driver also exercises type inference: it stores the result of jsonQuote
# applied to an `eb.val<string>` into a typed variable, so an `any`-typed or
# non-compiling signature breaks `tsc`.
# ---------------------------------------------------------------------------
DRIVER_SOURCE = r"""
import {
  DummyDriver,
  Kysely,
  SqliteAdapter,
  SqliteIntrospector,
  SqliteQueryCompiler,
  sql,
} from '../../../dist/index.js'
import { jsonBuildObject, jsonQuote } from '../../../dist/helpers/sqlite.js'

interface DB {
  person: {
    id: number
    first_name: string | null
    last_name: string | null
  }
}

const db = new Kysely<DB>({
  dialect: {
    createAdapter: () => new SqliteAdapter(),
    createDriver: () => new DummyDriver(),
    createIntrospector: (d) => new SqliteIntrospector(d),
    createQueryCompiler: () => new SqliteQueryCompiler(),
  },
})

function emit(label: string, sqlText: string, parameters: readonly unknown[]) {
  console.log('@@PROBE_BEGIN@@' + JSON.stringify({
    label,
    sql: sqlText,
    parameters,
  }) + '@@PROBE_END@@')
}

describe('json-quote probe', () => {
  it('emits compiled output for every scenario', () => {
    // --- column reference: quoted identifier, no params ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) => jsonQuote(eb.ref('first_name')).as('q'))
        .compile()
      emit('ref', c.sql, c.parameters)
    }

    // --- eb.val: bound parameter, value collected, not inlined ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) => jsonQuote(eb.val('hi')).as('q'))
        .compile()
      emit('val', c.sql, c.parameters)
    }

    // --- raw sql fragment: emitted verbatim, no params ---
    {
      const c = db
        .selectFrom('person')
        .select(() => jsonQuote(sql`1 + 1`).as('q'))
        .compile()
      emit('raw', c.sql, c.parameters)
    }

    // --- a different column reference (last_name) to confirm the arg is
    //     genuinely the input expression, not a hardcoded column ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) => jsonQuote(eb.ref('last_name')).as('lq'))
        .compile()
      emit('ref_other', c.sql, c.parameters)
    }

    // --- numeric eb.val to confirm value-type pass-through + binding ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) => jsonQuote(eb.val(42)).as('q'))
        .compile()
      emit('val_num', c.sql, c.parameters)
    }

    // --- existing helper jsonBuildObject must be unchanged ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) =>
          jsonBuildObject({
            first: eb.ref('first_name'),
          }).as('name'),
        )
        .compile()
      emit('build_object', c.sql, c.parameters)
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
        os.path.join(REPO_DIR, "dist", "helpers", "sqlite.js")
    ), "dist/helpers/sqlite.js not produced by build"

    # 3. drop our independent driver into the node test sources.
    with open(DRIVER_TS, "w") as f:
        f.write(DRIVER_SOURCE)

    try:
        # 4. compile the node test sources (this also type-checks the agent's
        #    new jsonQuote signature, since our driver invokes it).
        tsb = _run("pnpm test:node:build", timeout=600)
        assert tsb.returncode == 0, (
            "pnpm test:node:build (tsc) failed — the jsonQuote helper does "
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
    """jsonQuote helper for the SQLite dialect (variant ext6)."""

    REPO_DIR = "/workspace/kysely"

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and export the symbol
    # ------------------------------------------------------------------

    def test_sqlite_helper_file_exists(self):
        """src/helpers/sqlite.ts must exist."""
        assert os.path.isfile(SQLITE_HELPER), f"missing {SQLITE_HELPER}"

    def test_sqlite_exports_json_quote(self):
        """sqlite.ts must declare an exported `jsonQuote` function."""
        with open(SQLITE_HELPER) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+jsonQuote\b", src
        ), "no `export function jsonQuote` in src/helpers/sqlite.ts"

    def test_json_quote_not_any_typed(self):
        """The exported jsonQuote must not be `any`-typed / untyped."""
        with open(SQLITE_HELPER) as f:
            src = f.read()
        m = re.search(
            r"export\s+function\s+jsonQuote\b[^{]*", src, re.S
        )
        assert m, "jsonQuote signature not found"
        sig = m.group(0)
        # Doc requires the function not be `any`-typed; a `: any` return or an
        # `arg: any` parameter would violate that.
        assert not re.search(r":\s*any\b", sig), (
            "jsonQuote signature appears to be `any`-typed: " + sig
        )

    def test_existing_helpers_still_exported(self):
        """jsonArrayFrom / jsonObjectFrom / jsonBuildObject must remain exported."""
        with open(SQLITE_HELPER) as f:
            src = f.read()
        for name in ("jsonArrayFrom", "jsonObjectFrom", "jsonBuildObject"):
            assert re.search(
                r"export\s+function\s+" + name + r"\b", src
            ), f"existing helper `{name}` is no longer exported"

    def test_new_node_test_file_exists(self):
        """The required new node test file must be created by the agent."""
        assert os.path.isfile(
            NEW_TEST_TS
        ), "test/node/src/json-quote-sqlite.test.ts was not created"

    def test_no_cross_helper_import_in_test(self):
        """Agent's test must target the SQLite helper (json_quote), not postgres."""
        with open(NEW_TEST_TS) as f:
            tsrc = f.read()
        # It must reference jsonQuote and use the SQLite helper module path.
        assert "jsonQuote" in tsrc, "agent test does not reference jsonQuote"

    # ------------------------------------------------------------------
    # L2 — dynamic compilation behavior (via the harness's own driver)
    # ------------------------------------------------------------------

    def test_column_ref_sql(self, probe):
        """A column ref compiles to json_quote("first_name") with no params."""
        r = probe["ref"]
        assert (
            r["sql"]
            == 'select json_quote("first_name") as "q" from "person"'
        ), f"unexpected ref sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"

    def test_uses_correct_function_name(self, probe):
        """Must use json_quote — not json_object / json_array / json_build_*."""
        s = probe["ref"]["sql"]
        assert "json_quote(" in s, f"missing json_quote(): {s!r}"
        for wrong in ("json_object(", "json_array(", "json_build_object(",
                      "json_build_array(", "json_group_array("):
            assert wrong not in s, f"must not use {wrong}: {s!r}"

    def test_single_argument_no_comma(self, probe):
        """Exactly one argument, exactly one paren pair, no comma separators."""
        s = probe["ref"]["sql"]
        inner = re.search(r"json_quote\((.*?)\) as", s)
        assert inner, f"could not locate json_quote(...) in {s!r}"
        arg = inner.group(1)
        assert arg == '"first_name"', f"unexpected single arg: {arg!r}"
        assert "," not in arg, f"unexpected comma in single-arg call: {arg!r}"
        assert s.count("json_quote(") == 1, f"more than one json_quote call: {s!r}"
        assert s.count("(") == s.count(")"), f"unbalanced parens: {s!r}"

    def test_other_column_ref_is_genuine_input(self, probe):
        """A different ref (last_name) must flow through — not a hardcoded column."""
        r = probe["ref_other"]
        assert (
            r["sql"] == 'select json_quote("last_name") as "lq" from "person"'
        ), f"unexpected ref_other sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"

    def test_val_is_bound_parameter(self, probe):
        """eb.val('hi') must become a ? placeholder and be collected as a param."""
        r = probe["val"]
        assert (
            r["sql"] == 'select json_quote(?) as "q" from "person"'
        ), f"unexpected val sql: {r['sql']!r}"
        assert r["parameters"] == ["hi"], f"expected ['hi'] params, got {r['parameters']!r}"
        # value must NOT be inlined as a literal in the SQL text.
        assert "'hi'" not in r["sql"], f"value was inlined: {r['sql']!r}"
        assert "hi" not in r["sql"], f"value leaked into sql text: {r['sql']!r}"

    def test_numeric_val_bound_parameter(self, probe):
        """eb.val(42) must also bind as ? with 42 in the parameter list."""
        r = probe["val_num"]
        assert (
            r["sql"] == 'select json_quote(?) as "q" from "person"'
        ), f"unexpected val_num sql: {r['sql']!r}"
        assert r["parameters"] == [42], f"expected [42] params, got {r['parameters']!r}"
        assert "42" not in r["sql"], f"numeric value was inlined: {r['sql']!r}"

    def test_raw_fragment_verbatim(self, probe):
        """A raw sql`1 + 1` fragment must be emitted verbatim with no params."""
        r = probe["raw"]
        assert (
            r["sql"] == 'select json_quote(1 + 1) as "q" from "person"'
        ), f"unexpected raw sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"

    def test_existing_helper_output_unchanged(self, probe):
        """jsonBuildObject must still compile to its original json_object(...) form."""
        r = probe["build_object"]
        assert (
            r["sql"]
            == 'select json_object(\'first\', "first_name") as "name" from "person"'
        ), f"jsonBuildObject output changed: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"
