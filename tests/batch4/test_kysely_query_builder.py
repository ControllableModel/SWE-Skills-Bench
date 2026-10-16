"""
Test for the 'kysely-query-builder' skill (variant ext4) — Add a ``jsonQuote``
helper for MySQL.

Variant task
------------
The agent must add and export a new scalar helper ``jsonQuote`` to the MySQL
helper module (``src/helpers/mysql.ts``) that compiles to MySQL's
``json_quote(<arg>)`` scalar function with EXACTLY ONE argument, and create a
deterministic node compilation test at
``test/node/src/json-quote-mysql.test.ts``.

Required compiled behavior (MySQL dialect — backtick identifier quoting, ``?``
parameter placeholders):

  * ``jsonQuote(eb.ref('first_name'))`` aliased ``q`` selected from ``person``
    → ``select json_quote(`first_name`) as `q` from `person` `` with NO params.
  * ``jsonQuote(eb.val('hi'))``  → argument compiles to ``?`` and ``'hi'`` is
    collected into the ``parameters`` list, NEVER inlined into the SQL text.
  * ``jsonQuote(sql`concat(first_name, last_name)`)`` → the raw fragment is
    emitted verbatim inside a single pair of parentheses, with no params.
  * Exactly ONE pair of parentheses and exactly ONE argument; no comma
    separators (this is a scalar, single-argument helper — unlike the multi-arg
    json_build_* helpers).

Strategy / discriminative power
-------------------------------
L1 checks confirm the deliverable files exist, that ``jsonQuote`` is exported
from ``src/helpers/mysql.ts``, and that the pre-existing helpers
(``jsonArrayFrom`` / ``jsonObjectFrom`` / ``jsonBuildObject``) are untouched in
their public signatures.

L2 checks do NOT trust the agent's own test file. Instead this harness:
  1. builds the kysely library (``pnpm build``) once,
  2. writes its OWN TypeScript driver test into ``test/node/src/`` that imports
     the freshly-built ``jsonQuote`` from ``dist/helpers/mysql.js``, builds a
     ``Kysely`` instance with the MySQL adapter + query compiler + DummyDriver
     (no DB / network), calls ``.compile()`` and ``console.log``s the produced
     ``sql`` + ``parameters`` as JSON,
  3. compiles the node test sources (``pnpm test:node:build`` — this also
     type-checks the agent's new ``jsonQuote`` signature, since our driver
     invokes it as ``Expression<unknown> -> RawBuilder<...>``),
  4. runs only our driver under mocha and parses the emitted JSON, asserting on
     exact SQL strings, exact parameter arrays, single-argument shape, verbatim
     raw fragments, and bound-parameter (non-inlined) values.

A naive solution fails these tests: a wrong function name (``json_quote`` is
required), an inlined ``eb.val`` literal, multiple arguments / stray commas, a
missing or non-compiling signature, or accidentally calling one of the
multi-row aggregation helpers all produce SQL or parameters that differ from the
asserted exact values, because the real Kysely MySQL compiler is exercised
end-to-end.
"""

import json
import os
import re
import subprocess

import pytest


REPO_DIR = "/workspace/kysely"

MYSQL_HELPER = os.path.join(REPO_DIR, "src", "helpers", "mysql.ts")
NEW_TEST_TS = os.path.join(
    REPO_DIR, "test", "node", "src", "json-quote-mysql.test.ts"
)

# Where this harness drops its own independent driver (NOT the agent's file).
DRIVER_NAME = "zzz-json-quote-mysql-probe"
DRIVER_TS = os.path.join(REPO_DIR, "test", "node", "src", DRIVER_NAME + ".ts")
DRIVER_JS = os.path.join(REPO_DIR, "test", "node", "dist", DRIVER_NAME + ".js")

# Markers used to extract our JSON payloads from the mocha stdout stream.
BEGIN = "@@PROBE_BEGIN@@"
END = "@@PROBE_END@@"


# ---------------------------------------------------------------------------
# Driver test (TypeScript) written into the repo by this harness.
# Uses the MySQL adapter/compiler/introspector + DummyDriver pattern.
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
import { jsonQuote } from '../../../dist/helpers/mysql.js'

interface DB {
  person: {
    id: number
    first_name: string | null
    last_name: string | null
  }
}

const db = new Kysely<DB>({
  dialect: {
    createAdapter: () => new MysqlAdapter(),
    createDriver: () => new DummyDriver(),
    createIntrospector: (d) => new MysqlIntrospector(d),
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

describe('json-quote-mysql probe', () => {
  it('emits compiled output for every scenario', () => {
    // --- column reference argument ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) => jsonQuote(eb.ref('first_name')).as('q'))
        .compile()
      emit('ref', c.sql, c.parameters)
    }

    // --- eb.val argument => bound parameter ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) => jsonQuote(eb.val('hi')).as('q'))
        .compile()
      emit('val', c.sql, c.parameters)
    }

    // --- raw sql fragment argument => verbatim ---
    {
      const c = db
        .selectFrom('person')
        .select(() => jsonQuote(sql`concat(first_name, last_name)`).as('q'))
        .compile()
      emit('raw', c.sql, c.parameters)
    }

    // --- different column reference (discriminative: must reflect input) ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) => jsonQuote(eb.ref('last_name')).as('lq'))
        .compile()
      emit('ref_last', c.sql, c.parameters)
    }

    // --- numeric-ish eb.val with a distinctive sentinel value ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) => jsonQuote(eb.val('SENTINEL_42')).as('s'))
        .compile()
      emit('val_sentinel', c.sql, c.parameters)
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

    # 1. install deps only if missing. In the benchmark container the toolchain
    #    is already installed; if so we skip the (network-bound) install. We
    #    never hard-fail on install output — the build step below is the gate.
    if not os.path.isdir(os.path.join(REPO_DIR, "node_modules", ".bin")):
        try:
            _run("pnpm install --prefer-offline", timeout=600)
        except subprocess.TimeoutExpired:
            pass

    # 2. build the library (produces dist/, dist/helpers/mysql.js)
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
        #    new jsonQuote signature, since our driver invokes it).
        tsb = _run("pnpm test:node:build", timeout=600)
        assert tsb.returncode == 0, (
            "pnpm test:node:build (tsc) failed — the jsonQuote helper does not "
            "type-check or is not exported:\nSTDOUT:\n"
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
    """jsonQuote scalar helper for the MySQL dialect."""

    REPO_DIR = "/workspace/kysely"

    # ------------------------------------------------------------------
    # L1 — deliverable files exist, symbol exported, existing API intact
    # ------------------------------------------------------------------

    def test_mysql_helper_file_exists(self):
        """src/helpers/mysql.ts must exist."""
        assert os.path.isfile(MYSQL_HELPER), f"missing {MYSQL_HELPER}"

    def test_mysql_exports_json_quote(self):
        """mysql.ts must declare an exported `jsonQuote` function."""
        with open(MYSQL_HELPER) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+jsonQuote\b", src
        ), "no `export function jsonQuote` in src/helpers/mysql.ts"

    def test_existing_helpers_preserved(self):
        """The pre-existing exported helpers must still be exported unchanged."""
        with open(MYSQL_HELPER) as f:
            src = f.read()
        for name in ("jsonArrayFrom", "jsonObjectFrom", "jsonBuildObject"):
            assert re.search(
                r"export\s+function\s+" + name + r"\b", src
            ), f"existing helper `{name}` no longer exported from mysql.ts"

    def test_json_quote_not_any_typed(self):
        """The jsonQuote signature must not be declared with an `: any` return/param."""
        with open(MYSQL_HELPER) as f:
            src = f.read()
        m = re.search(r"export\s+function\s+jsonQuote\b[^\n{]*", src)
        assert m, "jsonQuote signature not found"
        sig = m.group(0)
        assert ": any" not in sig and ":any" not in sig, (
            "jsonQuote must not be `any`-typed: " + sig
        )

    def test_new_node_test_file_exists(self):
        """The required new node test file must be created by the agent."""
        assert os.path.isfile(
            NEW_TEST_TS
        ), "test/node/src/json-quote-mysql.test.ts was not created"

    def test_new_node_test_file_uses_json_quote(self):
        """The agent's new test must actually exercise jsonQuote (not be empty)."""
        with open(NEW_TEST_TS) as f:
            src = f.read()
        assert "jsonQuote" in src, (
            "test/node/src/json-quote-mysql.test.ts does not reference jsonQuote"
        )
        assert ".compile(" in src, (
            "agent's test must call .compile() to assert on produced SQL"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic compilation behavior (via the harness's own driver)
    # ------------------------------------------------------------------

    def test_column_ref_compiles_to_json_quote(self, probe):
        """A column ref compiles to json_quote(`first_name`) aliased `q`, no params."""
        r = probe["ref"]
        assert (
            r["sql"]
            == "select json_quote(`first_name`) as `q` from `person`"
        ), f"unexpected ref sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"

    def test_uses_correct_function_name(self, probe):
        """Must emit json_quote — not an aggregation/object helper or other name."""
        s = probe["ref"]["sql"]
        assert "json_quote(" in s, f"missing json_quote(): {s!r}"
        for forbidden in (
            "json_arrayagg(",
            "json_array(",
            "json_object(",
            "json_quote(json_quote(",
        ):
            assert forbidden not in s, f"forbidden construct {forbidden!r} in: {s!r}"

    def test_single_argument_and_single_paren_pair(self, probe):
        """Scalar helper: exactly one json_quote(...) call, one arg, no comma."""
        s = probe["ref"]["sql"]
        assert s.count("json_quote(") == 1, f"expected single call: {s!r}"
        inner = re.search(r"json_quote\((.*?)\)\s+as", s).group(1)
        assert inner == "`first_name`", f"unexpected single-arg content: {inner!r}"
        assert "," not in inner, f"scalar helper must have no comma separators: {inner!r}"
        assert s.count("(") == s.count(")"), f"unbalanced parens: {s!r}"

    def test_val_is_bound_parameter_not_inlined(self, probe):
        """eb.val('hi') must compile to `?` and be collected as a param, not inlined."""
        r = probe["val"]
        assert (
            r["sql"] == "select json_quote(?) as `q` from `person`"
        ), f"unexpected val sql: {r['sql']!r}"
        assert r["parameters"] == ["hi"], f"expected ['hi'] params, got {r['parameters']!r}"
        # value must NOT be inlined as a literal in the SQL text.
        assert "'hi'" not in r["sql"], f"value was inlined: {r['sql']!r}"
        assert "hi" not in r["sql"], f"value leaked into SQL text: {r['sql']!r}"

    def test_raw_fragment_emitted_verbatim(self, probe):
        """A raw sql fragment is emitted verbatim inside one paren pair, no params."""
        r = probe["raw"]
        assert (
            r["sql"]
            == "select json_quote(concat(first_name, last_name)) as `q` from `person`"
        ), f"unexpected raw sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"
        # the raw inner SQL must not have been quoted as an identifier.
        assert "`concat`" not in r["sql"], f"raw fragment was wrongly quoted: {r['sql']!r}"

    def test_argument_reflects_input_column(self, probe):
        """jsonQuote must wrap the ACTUAL input column, not a hardcoded one."""
        r = probe["ref_last"]
        assert (
            r["sql"] == "select json_quote(`last_name`) as `lq` from `person`"
        ), f"helper ignored its input column: {r['sql']!r}"
        # discriminate against a stub that always emits first_name.
        assert "`first_name`" not in r["sql"], (
            "jsonQuote appears to hardcode `first_name` instead of using its arg: "
            + repr(r["sql"])
        )

    def test_val_parameter_value_is_passed_through(self, probe):
        """A distinctive eb.val value must surface in parameters and never in SQL."""
        r = probe["val_sentinel"]
        assert (
            r["sql"] == "select json_quote(?) as `s` from `person`"
        ), f"unexpected sentinel sql: {r['sql']!r}"
        assert r["parameters"] == ["SENTINEL_42"], (
            f"sentinel value not bound as parameter: {r['parameters']!r}"
        )
        assert "SENTINEL_42" not in r["sql"], (
            "sentinel value was inlined into SQL: " + repr(r["sql"])
        )

    def test_alias_is_applied(self, probe):
        """The .as('q') alias must be honored (RawBuilder is aliasable)."""
        assert probe["ref"]["sql"].endswith("as `q` from `person`"), (
            "alias not applied to jsonQuote result: " + repr(probe["ref"]["sql"])
        )
        assert probe["ref_last"]["sql"].endswith("as `lq` from `person`"), (
            "alias not applied: " + repr(probe["ref_last"]["sql"])
        )
