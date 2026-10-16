"""
Test for the 'sequelize-orm' skill (variant ext5) — Compose Reusable Query Presets.

The agent must create two files inside @sequelize/core's unit-test tree:
  - packages/core/test/unit/model/ticket-presets.ts       (the domain module)
  - packages/core/test/unit/model/ticket-presets.test.ts  (its unit test)

The module exports `defineTicket(sequelize)` which defines and returns a `Ticket`
model on the passed-in Sequelize instance. The model carries:
  - fields: subject (text, required), status (text: open|pending|closed),
    priority (integer, default 0), assigneeId (integer, optional).
  - a DEFAULT query view that restricts results to status != 'closed'.
  - a named preset `closed`         -> status == 'closed'.
  - a named preset `highPriority`   -> priority >= 3.
  - a parameterized preset `assignedTo(userId)` -> assigneeId == userId.

In this Sequelize version, "named query presets" are implemented as scopes:
the default view is the model's `defaultScope`, named presets are entries in
`scopes`, and the effective options of a (composed) view are introspectable in
process via `Model._scope` (and `Model.withScope(...)._scope`). Parameterized
scopes are applied with `withScope({ method: ['assignedTo', userId] })`.

Verification strategy
---------------------
L1 cases check that the deliverable files exist and are minimally well-formed.

L2 cases DO NOT trust the agent's own test file. Each L2 test writes an
INDEPENDENT mocha spec into the repo that imports the agent's ticket-presets
module, builds a fresh model on a fresh Sequelize instance, and introspects the
real effective query options (`_scope.where`) of each view:
  * default view restricts status != 'closed' and carries NO priority/assignee
    restriction;
  * `closed` restricts status == 'closed';
  * `highPriority` restricts priority >= 3;
  * `assignedTo(7)` restricts assigneeId == 7 (the exact arg is reflected, and a
    different arg 99 produces 99, defeating any hardcoded implementation);
  * composing `highPriority` + `assignedTo(7)` carries BOTH restrictions;
  * applying a preset does not mutate the base/default view (independence);
  * field metadata (subject required, priority default 0) holds.

Because the merge of multiple `where` scopes nests sub-conditions under an
`Op.and` array in this Sequelize version, every assertion uses a recursive
`findCond` helper that locates an attribute restriction anywhere inside the
effective `where` tree, and reads its concrete value/operator. A naive module
that hardcodes options, ignores the `assignedTo` argument, or lets one preset
leak into another cannot pass.

Native acceptance command driven by the L2 layer (and the agent's own test):

    yarn mocha "test/unit/model/<spec>.test.ts"
"""

import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/sequelize"
CORE_DIR = os.path.join(REPO_DIR, "packages", "core")
MODEL_DIR = os.path.join(CORE_DIR, "test", "unit", "model")
MODULE_FILE = os.path.join(MODEL_DIR, "ticket-presets.ts")
AGENT_TEST_FILE = os.path.join(MODEL_DIR, "ticket-presets.test.ts")

# Where we drop our own independent specs (relative to CORE_DIR for the mocha glob).
_BENCH_BASENAME = "zzz-bench-ticket-presets"


def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _run_mocha(spec_rel_path, timeout=600):
    """Run one mocha spec from packages/core using the repo's native command."""
    cmd = ["yarn", "mocha", spec_rel_path]
    return subprocess.run(
        cmd,
        cwd=CORE_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _write_spec_and_run(spec_name, spec_body, timeout=600):
    """
    Write a self-contained mocha .test.ts spec into the model dir, run it,
    then clean it up. Returns the CompletedProcess.
    """
    spec_path = os.path.join(MODEL_DIR, spec_name)
    rel_path = os.path.join("test", "unit", "model", spec_name)
    with open(spec_path, "w", encoding="utf-8") as fh:
        fh.write(spec_body)
    try:
        return _run_mocha(rel_path, timeout=timeout)
    finally:
        try:
            os.remove(spec_path)
        except OSError:
            pass


def _assert_mocha_passed(result, context=""):
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    assert result.returncode == 0, (
        f"mocha spec failed ({context}).\n"
        f"returncode={result.returncode}\n"
        f"--- stdout (tail) ---\n{(result.stdout or '')[-6000:]}\n"
        f"--- stderr (tail) ---\n{(result.stderr or '')[-3000:]}"
    )
    # Guard against a silent zero-test run being treated as success.
    assert "0 passing" not in combined, (
        f"mocha reported 0 passing tests ({context}); the spec did not run.\n"
        f"{combined[-4000:]}"
    )


# Common TS preamble used by every independent spec. It builds the agent's
# Ticket model on a *fresh* Sequelize instance, then provides robust helpers
# that extract the effective `where` of a view and recursively search it for a
# restriction on a given attribute. The merge of several `where` scopes nests
# conditions under Op.and in this Sequelize version, so `findCond` walks arrays,
# plain objects and Op.and/Op.or symbol branches alike.
_PREAMBLE = textwrap.dedent(
    """\
    import { Op } from '@sequelize/core';
    import { expect } from 'chai';
    import { createSequelizeInstance } from '../../support';
    import { defineTicket } from './ticket-presets';

    function buildTicket() {
      const sequelize = createSequelizeInstance();
      const Ticket = defineTicket(sequelize as any);
      return { sequelize, Ticket };
    }

    // Effective `where` of a view: the model returned by withScope(...) (or the
    // base model for the default view) exposes its merged options on `_scope`.
    function scopeWhere(model: any): any {
      const sc = model && model._scope ? model._scope : {};
      return sc && sc.where ? sc.where : {};
    }

    // Apply named (and parameterized) presets and return the effective where.
    // Parameterized presets are applied as { method: ['name', ...args] }.
    function viewWhere(Ticket: any, presets: any[]): any {
      if (!presets || presets.length === 0) {
        return scopeWhere(Ticket); // default view = base model's defaultScope
      }
      const scoped = Ticket.withScope(presets);
      expect(scoped, 'withScope(' + JSON.stringify(presets) + ') returned nothing').to.exist;
      return scopeWhere(scoped);
    }

    // Recursively find every leaf restriction object that owns `attr` as a key,
    // walking arrays, plain-object branches and Op.and / Op.or symbol arrays.
    function collectConds(node: any, attr: string, out: any[]): void {
      if (node == null || typeof node !== 'object') return;
      if (Array.isArray(node)) {
        for (const item of node) collectConds(item, attr, out);
        return;
      }
      if (Object.prototype.hasOwnProperty.call(node, attr)) {
        out.push(node[attr]);
      }
      // Walk normal string keys.
      for (const k of Object.keys(node)) {
        if (k === attr) continue;
        collectConds(node[k], attr, out);
      }
      // Walk symbol keys (Op.and / Op.or branches).
      for (const s of Object.getOwnPropertySymbols(node)) {
        collectConds(node[s], attr, out);
      }
    }

    // Return the single restriction value for `attr` inside `where`, asserting
    // exactly one was present (so a leaked/duplicated restriction is caught).
    function condFor(where: any, attr: string): any {
      const found: any[] = [];
      collectConds(where, attr, found);
      expect(found.length,
        'expected exactly one restriction on "' + attr + '" but found ' +
        found.length + ' in ' + safeJson(where)).to.equal(1);
      return found[0];
    }

    function hasCond(where: any, attr: string): boolean {
      const found: any[] = [];
      collectConds(where, attr, found);
      return found.length > 0;
    }

    function safeJson(obj: any): string {
      try {
        return JSON.stringify(obj, (k, v) => (typeof v === 'function' ? '[fn]' : v));
      } catch (e) {
        return String(obj);
      }
    }

    // Read the operator->value pair out of a restriction value. Restrictions may
    // be a bare scalar (equality) or an object keyed by an Op symbol.
    function opValue(cond: any): { op: symbol | null; value: any } {
      if (cond != null && typeof cond === 'object' && !Array.isArray(cond)) {
        const syms = Object.getOwnPropertySymbols(cond);
        if (syms.length > 0) {
          return { op: syms[0], value: cond[syms[0]] };
        }
      }
      return { op: null, value: cond };
    }
    """
)


# ---------------------------------------------------------------------------
# Module-scope dependency guard. The container already has the toolchain that
# runs `yarn mocha`; we make sure node_modules is present (best-effort) so the
# native command can resolve mocha/chai/esbuild.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module", autouse=True)
def _ensure_dependencies():
    if not os.path.isdir(os.path.join(REPO_DIR, "node_modules")) and not os.path.isdir(
        os.path.join(CORE_DIR, "node_modules")
    ):
        try:
            subprocess.run(
                ["yarn", "install", "--immutable"],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=1800,
            )
        except Exception:
            # If install fails here, the native test calls below will surface
            # an explicit, debuggable error.
            pass
    yield


class TestSequelizeOrm:
    """Verify the ticket reusable-query-presets deliverable."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """The domain module ticket-presets.ts must exist."""
        assert os.path.isfile(MODULE_FILE), f"missing module file: {MODULE_FILE}"

    def test_agent_test_file_exists(self):
        """The agent's own unit test ticket-presets.test.ts must exist."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing test file: {AGENT_TEST_FILE}"

    def test_module_exports_factory(self):
        """ticket-presets.ts must export a `defineTicket` function symbol."""
        src = _read(MODULE_FILE)
        assert "defineTicket" in src, "defineTicket not found in module"
        assert "export" in src, "module does not export anything"

    def test_agent_test_imports_module(self):
        """The agent's test must import from the local ticket-presets module."""
        src = _read(AGENT_TEST_FILE)
        assert "ticket-presets" in src, "test does not reference the ticket-presets module"

    # ------------------------------------------------------------------
    # L2 — independent dynamic execution via native `yarn mocha`.
    # Each test writes its own spec, so failures are isolated and specific.
    # ------------------------------------------------------------------

    def test_factory_returns_ticket_model(self):
        """defineTicket returns a real Sequelize Ticket model bound to its instance."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('ticket-presets: factory shape', () => {
              it('returns a real Ticket model bound to the passed instance', () => {
                const { sequelize, Ticket } = buildTicket();
                expect(Ticket, 'Ticket missing').to.exist;
                expect(typeof Ticket.getAttributes, 'not a model class').to.equal('function');
                expect(typeof Ticket.build, 'not a model class').to.equal('function');
                expect(typeof Ticket.withScope, 'no withScope').to.equal('function');
                expect(Ticket.sequelize, 'Ticket not bound to passed instance')
                  .to.equal(sequelize);
              });

              it('defines a fresh model per instance (no leakage)', () => {
                const a = buildTicket();
                const b = buildTicket();
                expect(a.sequelize).to.not.equal(b.sequelize);
                expect(a.Ticket).to.not.equal(b.Ticket);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-shape.test.ts", spec)
        _assert_mocha_passed(result, "factory shape / independence")

    def test_fields_metadata(self):
        """Ticket carries subject/status/priority/assigneeId; priority defaults to 0;
        subject is required (empty subject fails validation)."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('ticket-presets: field metadata', () => {
              it('declares the four attribute columns', () => {
                const { Ticket } = buildTicket();
                const attrs: any = Ticket.getAttributes();
                for (const col of ['subject', 'status', 'priority', 'assigneeId']) {
                  expect(attrs, 'missing column ' + col).to.have.property(col);
                }
              });

              it('priority defaults to 0', () => {
                const { Ticket } = buildTicket();
                const t = Ticket.build({ subject: 'hello' });
                expect(Number((t as any).priority)).to.equal(0);
              });

              it('rejects an empty/missing subject', async () => {
                const { Ticket } = buildTicket();
                const bad = Ticket.build({ subject: '' });
                let err: any;
                try {
                  await bad.validate();
                } catch (e) {
                  err = e;
                }
                expect(err, 'expected validate() to reject empty subject').to.exist;
                const errors: any[] = (err && err.errors) || [];
                const match = errors.find((x: any) => x.path === 'subject');
                expect(match, 'expected a validation error on "subject": ' +
                  JSON.stringify(errors.map((x: any) => x.path))).to.exist;
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-fields.test.ts", spec)
        _assert_mocha_passed(result, "field metadata / required subject / priority default")

    def test_default_view_excludes_closed(self):
        """The default view (no preset) restricts status != 'closed' and carries no
        priority/assignee restriction."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('ticket-presets: default view', () => {
              it('restricts status to not-closed', () => {
                const { Ticket } = buildTicket();
                const where = viewWhere(Ticket, []);
                expect(hasCond(where, 'status'),
                  'default view has no status restriction: ' + safeJson(where))
                  .to.equal(true);
                const { op, value } = opValue(condFor(where, 'status'));
                // Must be a *negated* match against 'closed' (Op.ne) — NOT equality.
                expect(op === Op.ne || op === Op.not,
                  'default status restriction should be a not-equal on closed, got op=' +
                  String(op) + ' value=' + safeJson(value)).to.equal(true);
                expect(value).to.equal('closed');
              });

              it('carries NO priority or assignee restriction', () => {
                const { Ticket } = buildTicket();
                const where = viewWhere(Ticket, []);
                expect(hasCond(where, 'priority'),
                  'default view unexpectedly restricts priority').to.equal(false);
                expect(hasCond(where, 'assigneeId'),
                  'default view unexpectedly restricts assigneeId').to.equal(false);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-default.test.ts", spec)
        _assert_mocha_passed(result, "default view excludes closed")

    def test_closed_preset(self):
        """The `closed` preset restricts status == 'closed' (equality, not negation)."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('ticket-presets: closed preset', () => {
              it('restricts status to equal closed', () => {
                const { Ticket } = buildTicket();
                const where = viewWhere(Ticket, ['closed']);
                expect(hasCond(where, 'status'),
                  'closed preset has no status restriction: ' + safeJson(where))
                  .to.equal(true);
                const { op, value } = opValue(condFor(where, 'status'));
                // Equality: either a bare scalar 'closed' or Op.eq 'closed'.
                expect(op === null || op === Op.eq,
                  'closed preset should be equality on closed, got op=' + String(op))
                  .to.equal(true);
                expect(value).to.equal('closed');
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-closed.test.ts", spec)
        _assert_mocha_passed(result, "closed preset restricts status == closed")

    def test_high_priority_preset(self):
        """The `highPriority` preset restricts priority >= 3 (Op.gte, value 3)."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('ticket-presets: highPriority preset', () => {
              it('restricts priority to >= 3', () => {
                const { Ticket } = buildTicket();
                const where = viewWhere(Ticket, ['highPriority']);
                expect(hasCond(where, 'priority'),
                  'highPriority has no priority restriction: ' + safeJson(where))
                  .to.equal(true);
                const { op, value } = opValue(condFor(where, 'priority'));
                expect(op === Op.gte,
                  'highPriority must use Op.gte (>=), got op=' + String(op) +
                  ' value=' + safeJson(value)).to.equal(true);
                expect(Number(value)).to.equal(3);
              });

              it('does NOT restrict status or assignee', () => {
                const { Ticket } = buildTicket();
                const where = viewWhere(Ticket, ['highPriority']);
                expect(hasCond(where, 'assigneeId'),
                  'highPriority leaked an assignee restriction').to.equal(false);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-highprio.test.ts", spec)
        _assert_mocha_passed(result, "highPriority preset restricts priority >= 3")

    def test_assigned_to_reflects_argument(self):
        """`assignedTo(userId)` restricts assigneeId == userId and reflects the EXACT
        supplied argument (7 -> 7, 99 -> 99), defeating any hardcoded value."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('ticket-presets: assignedTo(userId)', () => {
              function assigneeValue(userId: number): any {
                const { Ticket } = buildTicket();
                const where = viewWhere(Ticket, [{ method: ['assignedTo', userId] }]);
                expect(hasCond(where, 'assigneeId'),
                  'assignedTo has no assigneeId restriction: ' + safeJson(where))
                  .to.equal(true);
                const { op, value } = opValue(condFor(where, 'assigneeId'));
                // Equality on the supplied id.
                expect(op === null || op === Op.eq,
                  'assignedTo should be equality on assigneeId, got op=' + String(op))
                  .to.equal(true);
                return value;
              }

              it('assignedTo(7) restricts assigneeId == 7', () => {
                expect(Number(assigneeValue(7))).to.equal(7);
              });

              it('assignedTo(99) restricts assigneeId == 99 (argument is honoured)', () => {
                expect(Number(assigneeValue(99))).to.equal(99);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-assignedto.test.ts", spec)
        _assert_mocha_passed(result, "assignedTo reflects its argument")

    def test_compose_high_priority_and_assigned_to(self):
        """Composing `highPriority` + `assignedTo(7)` carries BOTH restrictions:
        priority >= 3 AND assigneeId == 7."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('ticket-presets: composition', () => {
              it('carries both priority>=3 and assigneeId==7', () => {
                const { Ticket } = buildTicket();
                const where = viewWhere(Ticket,
                  ['highPriority', { method: ['assignedTo', 7] }]);

                expect(hasCond(where, 'priority'),
                  'composed view lost the priority restriction: ' + safeJson(where))
                  .to.equal(true);
                const prio = opValue(condFor(where, 'priority'));
                expect(prio.op === Op.gte, 'composed priority op should be >=').to.equal(true);
                expect(Number(prio.value)).to.equal(3);

                expect(hasCond(where, 'assigneeId'),
                  'composed view lost the assignee restriction: ' + safeJson(where))
                  .to.equal(true);
                const assignee = opValue(condFor(where, 'assigneeId'));
                expect(assignee.op === null || assignee.op === Op.eq,
                  'composed assignee should be equality').to.equal(true);
                expect(Number(assignee.value)).to.equal(7);
              });

              it('a different assignee arg composes correctly (3 + 42)', () => {
                const { Ticket } = buildTicket();
                const where = viewWhere(Ticket,
                  ['highPriority', { method: ['assignedTo', 42] }]);
                expect(Number(opValue(condFor(where, 'priority')).value)).to.equal(3);
                expect(Number(opValue(condFor(where, 'assigneeId')).value)).to.equal(42);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-compose.test.ts", spec)
        _assert_mocha_passed(result, "compose highPriority + assignedTo(7)")

    def test_presets_are_independent_no_mutation(self):
        """Applying a preset must not mutate the base/default view, and presets must
        not leak into one another."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('ticket-presets: independence / no mutation', () => {
              it('default view is unchanged after applying presets', () => {
                const { Ticket } = buildTicket();

                // Apply several presets (which should NOT mutate the base model).
                Ticket.withScope(['highPriority']);
                Ticket.withScope([{ method: ['assignedTo', 7] }]);
                Ticket.withScope(['closed']);

                // Re-read the default view: still only the non-closed status filter.
                const where = viewWhere(Ticket, []);
                const { op, value } = opValue(condFor(where, 'status'));
                expect(op === Op.ne || op === Op.not,
                  'default status filter mutated; op=' + String(op)).to.equal(true);
                expect(value).to.equal('closed');
                expect(hasCond(where, 'priority'),
                  'highPriority leaked into the default view').to.equal(false);
                expect(hasCond(where, 'assigneeId'),
                  'assignedTo leaked into the default view').to.equal(false);
              });

              it('highPriority alone does not carry the assignee restriction', () => {
                const { Ticket } = buildTicket();
                // Build a composed view first, then a fresh single-preset view.
                viewWhere(Ticket, ['highPriority', { method: ['assignedTo', 7] }]);
                const onlyHigh = viewWhere(Ticket, ['highPriority']);
                expect(hasCond(onlyHigh, 'assigneeId'),
                  'assignee restriction leaked into a standalone highPriority view')
                  .to.equal(false);
                expect(hasCond(onlyHigh, 'priority'),
                  'highPriority lost its own restriction').to.equal(true);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-independence.test.ts", spec)
        _assert_mocha_passed(result, "preset independence / no base mutation")

    def test_two_instances_are_independent(self):
        """Two separate Sequelize instances each get a fully independent Ticket model
        whose presets resolve within their own instance only."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('ticket-presets: per-instance independence', () => {
              it('presets work the same and independently on two instances', () => {
                const a = buildTicket();
                const b = buildTicket();
                expect(a.Ticket).to.not.equal(b.Ticket);

                const aWhere = viewWhere(a.Ticket, ['highPriority']);
                const bWhere = viewWhere(b.Ticket, [{ method: ['assignedTo', 11] }]);

                expect(Number(opValue(condFor(aWhere, 'priority')).value)).to.equal(3);
                expect(Number(opValue(condFor(bWhere, 'assigneeId')).value)).to.equal(11);

                // a's highPriority view must not carry b's assignee restriction.
                expect(hasCond(aWhere, 'assigneeId')).to.equal(false);

                // Default views on both instances exclude closed.
                for (const inst of [a, b]) {
                  const w = viewWhere(inst.Ticket, []);
                  const { value } = opValue(condFor(w, 'status'));
                  expect(value).to.equal('closed');
                }
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-twoinst.test.ts", spec)
        _assert_mocha_passed(result, "per-instance independence")

    def test_agent_supplied_test_passes(self):
        """The agent's own acceptance command must pass: yarn mocha ticket-presets.test.ts."""
        result = _run_mocha(
            os.path.join("test", "unit", "model", "ticket-presets.test.ts"),
            timeout=600,
        )
        _assert_mocha_passed(result, "agent-supplied ticket-presets.test.ts")
