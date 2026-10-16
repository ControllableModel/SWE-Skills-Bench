"""
Test for the 'sequelize-orm' skill (variant ext3) — Enforce Account Field Constraints.

The agent must create two files inside @sequelize/core's unit-test tree:
  - packages/core/test/unit/model/account-rules.ts       (the domain module)
  - packages/core/test/unit/model/account-rules.test.ts  (its unit test)

The module exports `defineAccount(sequelize)` which defines and returns an
`Account` model on the passed-in Sequelize instance. The model enforces a set
of business rules at the model layer, triggered in-process by building an
instance and calling `.validate()` (no database write):

  - handle (text, required): length 3..20 inclusive; out-of-range fails with
    `handle length must be 3 to 20` on the `handle` path.
  - email  (text, required): valid email; invalid fails with
    `email is not valid` on the `email` path.
  - age    (integer, optional): when present, 13..120; out-of-range fails with
    `age must be between 13 and 120` on the `age` path.
  - slug   (text, required): kebab-case only (lowercase letters, digits,
    hyphens); a bad value fails with `slug must be kebab-case` on `slug`.
  - referralCount (integer, optional): a custom rule rejects negatives with
    `referralCount cannot be negative` on `referralCount`; 0 and positive pass.

Verification strategy
---------------------
L1 cases check that the deliverable files exist and are minimally well-formed.

L2 cases DO NOT trust the agent's own test file. Instead we drop independent
mocha specs into the repo that *import the agent's account-rules module* and
exercise the real model behaviour: each rule is checked for the exact message
substring AND that the error is reported on the correct field path, valid
boundary values pass, a fully valid instance validates, and the model is
defined only on the passed-in instance (no leakage between Sequelize
instances). Each spec runs via the repository's native command:

    yarn mocha "test/unit/model/<spec>.test.ts"

A naive module that hardcodes return values, omits any single rule, reports the
error on the wrong field, or skips the custom referralCount rule cannot pass
these introspective assertions.
"""

import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/sequelize"
CORE_DIR = os.path.join(REPO_DIR, "packages", "core")
MODEL_DIR = os.path.join(CORE_DIR, "test", "unit", "model")
MODULE_FILE = os.path.join(MODEL_DIR, "account-rules.ts")
AGENT_TEST_FILE = os.path.join(MODEL_DIR, "account-rules.test.ts")

# Where we drop our own independent specs (relative to CORE_DIR for the mocha glob).
_BENCH_BASENAME = "zzz-bench-account-rules"


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


# Common TS preamble used by every independent spec: a fresh Sequelize and the
# agent's factory, a fully-valid baseline attribute set, plus helpers to assert
# that .validate() rejects on a specific field with an expected message
# substring, or resolves cleanly.
_PREAMBLE = textwrap.dedent(
    """\
    import { expect } from 'chai';
    import { createSequelizeInstance } from '../../support';
    import { defineAccount } from './account-rules';

    function buildModel() {
      const sequelize = createSequelizeInstance();
      const Account = defineAccount(sequelize as any);
      return { sequelize, Account };
    }

    // A fully valid baseline; override one field per case to isolate a rule.
    function valid(overrides: any = {}) {
      return Object.assign({
        handle: 'alice',
        email: 'a@b.com',
        age: 30,
        slug: 'cool-account-1',
        referralCount: 0,
      }, overrides);
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

    async function expectValid(instance: any) {
      await instance.validate(); // must not throw
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
    """Verify the account-rules domain model deliverable (ext3 variant)."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """The domain module account-rules.ts must exist."""
        assert os.path.isfile(MODULE_FILE), f"missing module file: {MODULE_FILE}"

    def test_agent_test_file_exists(self):
        """The agent's own unit test account-rules.test.ts must exist."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing test file: {AGENT_TEST_FILE}"

    def test_module_exports_factory(self):
        """account-rules.ts must export a `defineAccount` function symbol."""
        src = _read(MODULE_FILE)
        assert "defineAccount" in src, "defineAccount not found in module"
        assert "export" in src, "module does not export anything"

    def test_agent_test_imports_module(self):
        """The agent's test must import from the local account-rules module."""
        src = _read(AGENT_TEST_FILE)
        assert "account-rules" in src, "test does not reference the account-rules module"

    # ------------------------------------------------------------------
    # L2 — independent dynamic execution via native `yarn mocha`.
    # Each test writes its own spec, so failures are isolated and specific.
    # ------------------------------------------------------------------

    def test_factory_returns_account_model_on_instance(self):
        """defineAccount returns a real Account model bound to the passed instance only."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('account-rules: factory shape', () => {
              it('returns a real Sequelize model named Account', () => {
                const { sequelize, Account } = buildModel();
                expect(Account, 'Account missing').to.exist;
                expect(typeof Account.getAttributes, 'not a model class').to.equal('function');
                expect(typeof Account.build, 'not a model class').to.equal('function');
                // Bound to the passed-in instance.
                expect((Account as any).sequelize).to.equal(sequelize);
                // Defines the documented fields.
                const attrs: any = Account.getAttributes();
                for (const f of ['handle', 'email', 'age', 'slug', 'referralCount']) {
                  expect(attrs, 'missing attribute ' + f).to.have.property(f);
                }
              });

              it('defines the model only on the passed instance (no leakage)', () => {
                const a = buildModel();
                const b = buildModel();
                expect(a.sequelize).to.not.equal(b.sequelize);
                expect(a.Account).to.not.equal(b.Account);
                expect((a.Account as any).sequelize).to.equal(a.sequelize);
                expect((b.Account as any).sequelize).to.equal(b.sequelize);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-shape.test.ts", spec)
        _assert_mocha_passed(result, "factory shape / instance binding")

    def test_handle_length_rule(self):
        """handle length must be 3..20 inclusive; out-of-range fails on `handle` with the message."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('account-rules: handle length 3..20', () => {
              it('rejects a too-short handle (2 chars) on the handle path', async () => {
                const { Account } = buildModel();
                const a = Account.build(valid({ handle: 'ab' }));
                await expectFieldError(a, 'handle', 'handle length must be 3 to 20');
              });

              it('rejects a too-long handle (21 chars) on the handle path', async () => {
                const { Account } = buildModel();
                const a = Account.build(valid({ handle: 'a'.repeat(21) }));
                await expectFieldError(a, 'handle', 'handle length must be 3 to 20');
              });

              it('accepts the lower boundary length 3', async () => {
                const { Account } = buildModel();
                await expectValid(Account.build(valid({ handle: 'abc' })));
              });

              it('accepts the upper boundary length 20', async () => {
                const { Account } = buildModel();
                await expectValid(Account.build(valid({ handle: 'a'.repeat(20) })));
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-handle.test.ts", spec)
        _assert_mocha_passed(result, "handle length rule")

    def test_email_format_rule(self):
        """An invalid email fails on `email` with `email is not valid`; a valid one passes."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('account-rules: email format', () => {
              it('rejects a non-email with the required message text on email path', async () => {
                const { Account } = buildModel();
                const a = Account.build(valid({ email: 'nope' }));
                await expectFieldError(a, 'email', 'email is not valid');
              });

              it('accepts a syntactically valid email', async () => {
                const { Account } = buildModel();
                await expectValid(Account.build(valid({ email: 'user@example.com' })));
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-email.test.ts", spec)
        _assert_mocha_passed(result, "email format rule")

    def test_age_range_rule(self):
        """age (when present) must be 13..120; out-of-range fails on `age`; omitting age passes."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('account-rules: age 13..120 (optional)', () => {
              it('rejects age = 5 on the age path with the message', async () => {
                const { Account } = buildModel();
                const a = Account.build(valid({ age: 5 }));
                await expectFieldError(a, 'age', 'age must be between 13 and 120');
              });

              it('rejects age = 121 on the age path', async () => {
                const { Account } = buildModel();
                const a = Account.build(valid({ age: 121 }));
                await expectFieldError(a, 'age', 'age must be between 13 and 120');
              });

              it('accepts the lower boundary age 13', async () => {
                const { Account } = buildModel();
                await expectValid(Account.build(valid({ age: 13 })));
              });

              it('accepts the upper boundary age 120', async () => {
                const { Account } = buildModel();
                await expectValid(Account.build(valid({ age: 120 })));
              });

              it('accepts an omitted (optional) age', async () => {
                const { Account } = buildModel();
                const attrs = valid();
                delete (attrs as any).age;
                await expectValid(Account.build(attrs));
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-age.test.ts", spec)
        _assert_mocha_passed(result, "age range rule")

    def test_slug_kebab_case_rule(self):
        """slug must be kebab-case; uppercase/space/punctuation fail on `slug` with the message."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('account-rules: slug kebab-case', () => {
              it('rejects a slug with spaces and uppercase on the slug path', async () => {
                const { Account } = buildModel();
                const a = Account.build(valid({ slug: 'Not Kebab' }));
                await expectFieldError(a, 'slug', 'slug must be kebab-case');
              });

              it('rejects a slug containing an underscore', async () => {
                const { Account } = buildModel();
                const a = Account.build(valid({ slug: 'bad_slug' }));
                await expectFieldError(a, 'slug', 'slug must be kebab-case');
              });

              it('accepts a valid kebab-case slug with digits and hyphens', async () => {
                const { Account } = buildModel();
                await expectValid(Account.build(valid({ slug: 'cool-account-1' })));
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-slug.test.ts", spec)
        _assert_mocha_passed(result, "slug kebab-case rule")

    def test_referral_count_custom_rule(self):
        """The custom referralCount rule rejects negatives on `referralCount`; 0 and positives pass."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('account-rules: referralCount non-negative', () => {
              it('rejects -1 on the referralCount path with the message', async () => {
                const { Account } = buildModel();
                const a = Account.build(valid({ referralCount: -1 }));
                await expectFieldError(a, 'referralCount', 'referralCount cannot be negative');
              });

              it('accepts zero', async () => {
                const { Account } = buildModel();
                await expectValid(Account.build(valid({ referralCount: 0 })));
              });

              it('accepts a positive value', async () => {
                const { Account } = buildModel();
                await expectValid(Account.build(valid({ referralCount: 42 })));
              });

              it('accepts an omitted (optional) referralCount', async () => {
                const { Account } = buildModel();
                const attrs = valid();
                delete (attrs as any).referralCount;
                await expectValid(Account.build(attrs));
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-referral.test.ts", spec)
        _assert_mocha_passed(result, "referralCount custom rule")

    def test_fully_valid_instance_validates(self):
        """A fully valid instance must validate successfully without throwing."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('account-rules: fully valid instance', () => {
              it('validates the documented happy-path instance', async () => {
                const { Account } = buildModel();
                const a = Account.build({
                  handle: 'alice',
                  email: 'a@b.com',
                  age: 30,
                  slug: 'cool-account-1',
                  referralCount: 0,
                });
                await expectValid(a);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-valid.test.ts", spec)
        _assert_mocha_passed(result, "fully valid instance validates")

    def test_each_error_on_correct_field_only(self):
        """Each single broken field reports its error on that field's path, not an unrelated one."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('account-rules: error path correctness', () => {
              async function offendingPaths(instance: any): Promise<string[]> {
                let err: any;
                try { await instance.validate(); } catch (e) { err = e; }
                expect(err, 'expected validate() to reject').to.exist;
                return (err.errors || []).map((x: any) => x.path);
              }

              it('a broken handle does not surface as an email/age/slug error', async () => {
                const { Account } = buildModel();
                const paths = await offendingPaths(Account.build(valid({ handle: 'ab' })));
                expect(paths).to.include('handle');
                expect(paths).to.not.include('email');
                expect(paths).to.not.include('age');
                expect(paths).to.not.include('slug');
                expect(paths).to.not.include('referralCount');
              });

              it('a broken referralCount surfaces only on referralCount', async () => {
                const { Account } = buildModel();
                const paths = await offendingPaths(Account.build(valid({ referralCount: -5 })));
                expect(paths).to.include('referralCount');
                expect(paths).to.not.include('handle');
                expect(paths).to.not.include('email');
                expect(paths).to.not.include('age');
                expect(paths).to.not.include('slug');
              });

              it('a broken slug surfaces only on slug', async () => {
                const { Account } = buildModel();
                const paths = await offendingPaths(Account.build(valid({ slug: 'BAD SLUG!' })));
                expect(paths).to.include('slug');
                expect(paths).to.not.include('handle');
                expect(paths).to.not.include('email');
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-paths.test.ts", spec)
        _assert_mocha_passed(result, "error path correctness")

    def test_two_instances_are_independent(self):
        """Two separate Sequelize instances each get a fully independent Account model."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('account-rules: per-instance independence', () => {
              it('models and validation do not bleed across instances', async () => {
                const a = buildModel();
                const b = buildModel();

                expect(a.Account).to.not.equal(b.Account);
                expect((a.Account as any).sequelize).to.equal(a.sequelize);
                expect((b.Account as any).sequelize).to.equal(b.sequelize);

                // Validation works independently on each instance.
                const badA = a.Account.build(valid({ handle: 'x' }));
                await expectFieldError(badA, 'handle', 'handle length must be 3 to 20');
                const goodB = b.Account.build(valid());
                await goodB.validate();
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-independence.test.ts", spec)
        _assert_mocha_passed(result, "per-instance independence")

    def test_agent_supplied_test_passes(self):
        """The agent's own acceptance command must pass: yarn mocha account-rules.test.ts."""
        result = _run_mocha(
            os.path.join("test", "unit", "model", "account-rules.test.ts"),
            timeout=600,
        )
        _assert_mocha_passed(result, "agent-supplied account-rules.test.ts")
