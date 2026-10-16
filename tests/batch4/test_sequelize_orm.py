"""
Test for the 'sequelize-orm' skill (variant ext4) — Normalize Records Through
Lifecycle Callbacks.

The agent must create two files inside @sequelize/core's unit-test tree:
  - packages/core/test/unit/model/contact-normalize.ts       (the model module)
  - packages/core/test/unit/model/contact-normalize.test.ts  (its unit test)

The module exports `defineContact(sequelize)` which defines and returns a
`Contact` model whose lifecycle callbacks:
  * before validation: lowercase + trim `email`
  * before validation: derive a missing/empty `displayName` from the local part
    (text before '@') of the *already normalized* email
  * before persisting: derive `searchKey` from the normalized email with '@' and
    every '.' removed
  * on each successful save: increment `saveCount` by exactly one and persist it.

Fields: email (text, required, unique), displayName (text, optional),
searchKey (text, optional, derived), saveCount (integer, default 0).

Verification strategy
---------------------
L1 cases check that the deliverable files exist and are minimally well-formed
(module exports `defineContact`, the agent test imports the module).

L2 cases DO NOT trust the agent's own test file. Instead we drop our own
independent mocha specs into the repo that import the agent's
`contact-normalize` module, build a *fresh in-memory* sqlite Sequelize, sync it,
and exercise the real lifecycle by creating / updating / reloading instances.
We assert concrete persisted values:
  - '  USER@Example.COM  ' -> stored email 'user@example.com'
  - '  Mixed@Case.IO ' + no displayName -> email 'mixed@case.io',
    displayName 'mixed', searchKey 'mixedcaseio', saveCount 1
  - explicit displayName 'Custom' is preserved
  - second save (after a field change) yields saveCount 2
  - reloading from the database confirms the derived values were persisted,
    not merely set on the in-memory object (defeats stubs).

A naive module that hardcodes any derived value, that does not actually run on
the lifecycle, that overwrites an explicit displayName, or that fails to persist
the saveCount increment cannot pass these introspective assertions.

The native acceptance command driven by L2 (per the variant doc) is:

    yarn mocha "test/unit/model/<spec>.test.ts"

run from packages/core with DIALECT=sqlite3.
"""

import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/sequelize"
CORE_DIR = os.path.join(REPO_DIR, "packages", "core")
MODEL_DIR = os.path.join(CORE_DIR, "test", "unit", "model")
MODULE_FILE = os.path.join(MODEL_DIR, "contact-normalize.ts")
AGENT_TEST_FILE = os.path.join(MODEL_DIR, "contact-normalize.test.ts")

# Where we drop our own independent specs (relative to CORE_DIR for the glob).
_BENCH_BASENAME = "zzz-bench-contact-normalize"


def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _mocha_env():
    """Native unit tests require DIALECT to be set; default to in-memory sqlite3."""
    env = dict(os.environ)
    env.setdefault("DIALECT", "sqlite3")
    return env


def _run_mocha(spec_rel_path, timeout=600):
    """Run one mocha spec from packages/core using the repo's native command."""
    cmd = ["yarn", "mocha", spec_rel_path]
    return subprocess.run(
        cmd,
        cwd=CORE_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_mocha_env(),
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


# Common TS preamble used by every independent spec: build a *fresh in-memory*
# sqlite Sequelize via the repo's helper (overriding storage to ':memory:' so we
# get a clean, isolated DB), define the agent's Contact model, sync the schema,
# and expose a couple of small helpers.
_PREAMBLE = textwrap.dedent(
    """\
    import { expect } from 'chai';
    import { createSequelizeInstance } from '../../support';
    import { defineContact } from './contact-normalize';

    async function buildContact() {
      // ':memory:' guarantees a clean, isolated, in-process database per spec.
      const sequelize = createSequelizeInstance({ storage: ':memory:' } as any);
      const Contact = defineContact(sequelize as any);
      await (sequelize as any).sync({ force: true });
      return { sequelize, Contact };
    }

    async function expectFieldError(instance: any, field: string, msgIncludes?: string) {
      let err: any;
      try {
        await instance.validate();
      } catch (e) {
        err = e;
      }
      expect(err, 'expected validate() to reject').to.exist;
      const errors: any[] = err.errors || [];
      const match = errors.find((x: any) => x.path === field);
      expect(match, `expected a validation error on field "${field}", got: ` +
        JSON.stringify(errors.map((x: any) => ({ path: x.path, message: x.message })))).to.exist;
      if (msgIncludes != null) {
        expect(String(match.message)).to.contain(msgIncludes);
      }
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
                env=_mocha_env(),
            )
        except Exception:
            # If install fails here, the native test calls below will surface
            # an explicit, debuggable error.
            pass
    yield


class TestSequelizeOrm:
    """Verify the contact-normalize lifecycle-callback deliverable."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """The model module contact-normalize.ts must exist."""
        assert os.path.isfile(MODULE_FILE), f"missing module file: {MODULE_FILE}"

    def test_agent_test_file_exists(self):
        """The agent's own unit test contact-normalize.test.ts must exist."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing test file: {AGENT_TEST_FILE}"

    def test_module_exports_factory(self):
        """contact-normalize.ts must export a `defineContact` function symbol."""
        src = _read(MODULE_FILE)
        assert "defineContact" in src, "defineContact not found in module"
        assert "export" in src, "module does not export anything"

    def test_agent_test_imports_module(self):
        """The agent's test must import from the local contact-normalize module."""
        src = _read(AGENT_TEST_FILE)
        assert "contact-normalize" in src, (
            "test does not reference the contact-normalize module"
        )

    # ------------------------------------------------------------------
    # L2 — independent dynamic execution via native `yarn mocha`.
    # Each test writes its own spec, so failures are isolated and specific.
    # ------------------------------------------------------------------

    def test_factory_returns_contact_model_with_fields(self):
        """defineContact returns a real Contact model with the four required attributes."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('contact-normalize: model shape', () => {
              it('returns a real Sequelize model bound to the passed instance', async () => {
                const { sequelize, Contact } = await buildContact();
                expect(Contact, 'Contact missing').to.exist;
                expect(typeof Contact.getAttributes, 'not a model class').to.equal('function');
                expect(typeof Contact.build, 'not a model class').to.equal('function');
                expect(typeof Contact.create, 'no create()').to.equal('function');
                expect(Contact.sequelize, 'Contact not bound to passed instance')
                  .to.equal(sequelize);
              });

              it('declares email, displayName, searchKey and saveCount attributes', async () => {
                const { Contact } = await buildContact();
                const attrs: any = Contact.getAttributes();
                for (const f of ['email', 'displayName', 'searchKey', 'saveCount']) {
                  expect(attrs, 'missing attribute: ' + f).to.have.property(f);
                }
              });

              it('defines models only on the passed instance (no leakage)', async () => {
                const a = await buildContact();
                const b = await buildContact();
                expect(a.sequelize).to.not.equal(b.sequelize);
                expect(a.Contact).to.not.equal(b.Contact);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-shape.test.ts", spec)
        _assert_mocha_passed(result, "factory shape / required fields")

    def test_email_normalization_lowercase_trim(self):
        """'  USER@Example.COM  ' is normalized & PERSISTED as 'user@example.com'."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('contact-normalize: email normalization', () => {
              it('lowercases and trims email before validation, and persists it', async () => {
                const { Contact } = await buildContact();
                const c = await Contact.create({ email: '  USER@Example.COM  ' });
                expect(c.email, 'in-memory email not normalized')
                  .to.equal('user@example.com');

                // Re-read from the database: the normalized value must be persisted,
                // not merely set on the in-memory object.
                const reloaded: any = await Contact.findByPk(c.id);
                expect(reloaded, 'created row not found in DB').to.exist;
                expect(reloaded.email, 'persisted email not normalized')
                  .to.equal('user@example.com');
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-email.test.ts", spec)
        _assert_mocha_passed(result, "email lowercase/trim normalization")

    def test_uniqueness_sees_normalized_email(self):
        """Normalization runs early enough that two case/space-variant emails collide."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('contact-normalize: uniqueness sees normalized value', () => {
              it('rejects a second contact whose email normalizes to an existing one', async () => {
                const { Contact } = await buildContact();
                await Contact.create({ email: 'dup@example.com' });

                let err: any;
                try {
                  // Different casing / whitespace, but same normalized value.
                  await Contact.create({ email: '  DUP@Example.COM ' });
                } catch (e) {
                  err = e;
                }
                expect(err, 'expected a uniqueness violation on the normalized email')
                  .to.exist;

                // Only one row should exist.
                const count = await Contact.count();
                expect(count, 'duplicate normalized email was stored').to.equal(1);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-unique.test.ts", spec)
        _assert_mocha_passed(result, "uniqueness on normalized email")

    def test_displayname_derived_from_local_part(self):
        """Missing displayName is derived from the local part of the normalized email."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('contact-normalize: displayName derivation', () => {
              it('derives displayName from the normalized email local part', async () => {
                const { Contact } = await buildContact();
                const c: any = await Contact.create({ email: '  Mixed@Case.IO ' });
                // local part of 'mixed@case.io' is 'mixed'
                expect(c.displayName, 'displayName not derived').to.equal('mixed');

                const reloaded: any = await Contact.findByPk(c.id);
                expect(reloaded.displayName, 'derived displayName not persisted')
                  .to.equal('mixed');
              });

              it('treats an empty-string displayName as missing and derives it', async () => {
                const { Contact } = await buildContact();
                const c: any = await Contact.create({
                  email: 'alice@example.com',
                  displayName: '',
                });
                expect(c.displayName, 'empty displayName should be derived')
                  .to.equal('alice');
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-derive-name.test.ts", spec)
        _assert_mocha_passed(result, "displayName derivation from local part")

    def test_explicit_displayname_preserved(self):
        """An explicitly provided non-empty displayName is left unchanged."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('contact-normalize: explicit displayName preserved', () => {
              it('does not overwrite a provided non-empty displayName', async () => {
                const { Contact } = await buildContact();
                const c: any = await Contact.create({
                  email: 'bob@example.com',
                  displayName: 'Custom',
                });
                expect(c.displayName, 'explicit displayName was overwritten')
                  .to.equal('Custom');

                const reloaded: any = await Contact.findByPk(c.id);
                expect(reloaded.displayName, 'explicit displayName not persisted intact')
                  .to.equal('Custom');
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-explicit-name.test.ts", spec)
        _assert_mocha_passed(result, "explicit displayName preserved")

    def test_searchkey_derived_on_save(self):
        """searchKey is the normalized email with '@' and every '.' removed, persisted."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('contact-normalize: searchKey derivation', () => {
              it("derives searchKey by removing '@' and '.' from the normalized email", async () => {
                const { Contact } = await buildContact();
                const c: any = await Contact.create({ email: '  USER@Example.COM  ' });
                // 'user@example.com' -> 'userexamplecom'
                expect(c.searchKey, 'searchKey not derived on save')
                  .to.equal('userexamplecom');

                const reloaded: any = await Contact.findByPk(c.id);
                expect(reloaded.searchKey, 'derived searchKey not persisted')
                  .to.equal('userexamplecom');
              });

              it('handles a multi-dot email correctly', async () => {
                const { Contact } = await buildContact();
                const c: any = await Contact.create({ email: 'a.b.c@sub.example.co.uk' });
                expect(c.searchKey).to.equal('abcsubexamplecouk');
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-searchkey.test.ts", spec)
        _assert_mocha_passed(result, "searchKey derivation on save")

    def test_savecount_first_save_is_one(self):
        """A brand-new record saved once has saveCount === 1 (default 0 + one increment)."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('contact-normalize: saveCount first save', () => {
              it('yields saveCount === 1 after the initial create', async () => {
                const { Contact } = await buildContact();
                const c: any = await Contact.create({ email: 'count1@example.com' });
                expect(c.saveCount, 'saveCount not 1 after first save').to.equal(1);

                const reloaded: any = await Contact.findByPk(c.id);
                expect(reloaded.saveCount, 'saveCount increment not persisted')
                  .to.equal(1);
              });

              it('defaults saveCount to 0 on a freshly built (unsaved) instance', async () => {
                const { Contact } = await buildContact();
                const built: any = Contact.build({ email: 'fresh@example.com' });
                expect(Number(built.saveCount), 'saveCount default should be 0')
                  .to.equal(0);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-count1.test.ts", spec)
        _assert_mocha_passed(result, "saveCount === 1 after first save")

    def test_savecount_increments_on_second_save(self):
        """Updating then saving again increments saveCount to 2 (per-save, persisted)."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('contact-normalize: saveCount second save', () => {
              it('increments saveCount by exactly one on each successful save', async () => {
                const { Contact } = await buildContact();
                const c: any = await Contact.create({ email: 'count2@example.com' });
                expect(c.saveCount, 'unexpected saveCount after first save').to.equal(1);

                // Change a field and save again.
                c.displayName = 'Renamed';
                await c.save();
                expect(c.saveCount, 'saveCount not incremented on second save')
                  .to.equal(2);

                const reloaded: any = await Contact.findByPk(c.id);
                expect(reloaded.saveCount, 'second increment not persisted')
                  .to.equal(2);
                // The explicit displayName we set must survive the second save.
                expect(reloaded.displayName, 'explicit displayName lost on update')
                  .to.equal('Renamed');
              });

              it('does not increment by more than one per save (no double-fire)', async () => {
                const { Contact } = await buildContact();
                const c: any = await Contact.create({ email: 'once@example.com' });
                c.displayName = 'A';
                await c.save();
                c.displayName = 'B';
                await c.save();
                expect(c.saveCount, 'saveCount drifted; expected exactly 3 after 3 saves')
                  .to.equal(3);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-count2.test.ts", spec)
        _assert_mocha_passed(result, "saveCount increments per save")

    def test_email_required_validation(self):
        """A Contact with a missing/empty email must fail validation (required field)."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('contact-normalize: email required', () => {
              it('rejects an empty email', async () => {
                const { Contact } = await buildContact();
                const c = Contact.build({ email: '' });
                await expectFieldError(c, 'email');
              });

              it('rejects a missing email', async () => {
                const { Contact } = await buildContact();
                let err: any;
                try {
                  await Contact.create({} as any);
                } catch (e) {
                  err = e;
                }
                expect(err, 'expected create() with no email to reject').to.exist;
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-required.test.ts", spec)
        _assert_mocha_passed(result, "email required validation")

    def test_full_expected_functionality_scenario(self):
        """End-to-end scenario from the doc: all derived values for one record at once."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('contact-normalize: full scenario', () => {
              it("'  Mixed@Case.IO ' with no displayName yields all derived values", async () => {
                const { Contact } = await buildContact();
                const c: any = await Contact.create({ email: '  Mixed@Case.IO ' });
                expect(c.email, 'email').to.equal('mixed@case.io');
                expect(c.displayName, 'displayName').to.equal('mixed');
                expect(c.searchKey, 'searchKey').to.equal('mixedcaseio');
                expect(c.saveCount, 'saveCount').to.equal(1);

                const reloaded: any = await Contact.findByPk(c.id);
                expect(reloaded.email).to.equal('mixed@case.io');
                expect(reloaded.displayName).to.equal('mixed');
                expect(reloaded.searchKey).to.equal('mixedcaseio');
                expect(reloaded.saveCount).to.equal(1);
              });

              it('two independent instances do not share state', async () => {
                const a = await buildContact();
                const b = await buildContact();
                const ca: any = await a.Contact.create({ email: 'iso@example.com' });
                expect(ca.searchKey).to.equal('isoexamplecom');
                // b's table is empty and independent.
                const bCount = await b.Contact.count();
                expect(bCount, 'instances are not isolated').to.equal(0);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-scenario.test.ts", spec, timeout=600)
        _assert_mocha_passed(result, "full expected-functionality scenario")

    def test_agent_supplied_test_passes(self):
        """The agent's own acceptance command must pass: yarn mocha contact-normalize.test.ts."""
        result = _run_mocha(
            os.path.join("test", "unit", "model", "contact-normalize.test.ts"),
            timeout=600,
        )
        _assert_mocha_passed(result, "agent-supplied contact-normalize.test.ts")
