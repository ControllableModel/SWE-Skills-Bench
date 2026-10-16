"""
Test for the 'sequelize-orm' skill (variant ext10) — Soft-Deletable Documents.

The agent must create two files inside @sequelize/core's INTEGRATION-test tree:
  - packages/core/test/integration/soft-documents.ts       (the domain module)
  - packages/core/test/integration/soft-documents.test.ts  (its integration test)

The module exports:
  - setupDocuments(sequelize) -> defines + returns the `Document` model and
    creates its table. `Document` has `title` (text, required) and `body`
    (text, optional), and records a deletion timestamp on soft-delete (paranoid).
  - archive(Document, id)  -> soft-deletes a VISIBLE document by primary key;
    returns true on a real archive, false when nothing visible matched.
  - restore(Document, id)  -> un-deletes a previously soft-deleted document;
    returns true on a real restore, false when nothing deleted matched.
  - listVisible(Document)  -> only non-deleted rows, ordered by title ascending.
  - listAll(Document)      -> all rows including soft-deleted, title ascending.

Verification strategy
---------------------
L1 cases check that the deliverable files exist and are minimally well-formed
(right exports referenced, the test imports the module).

L2 cases DO NOT trust the agent's own test file. Instead we drop independent
mocha specs into the repo's integration tree that *import the agent's
soft-documents module* and exercise the REAL behaviour in-process against the
default integration test database (sqlite by default):

    yarn mocha "test/integration/<spec>.test.ts"

The independent specs assert concrete, discriminative facts:
  - archive hides a row from listVisible but keeps it in listAll, and stamps a
    deletion timestamp on the row.
  - restore brings the row back into listVisible.
  - archive/restore boolean returns for BOTH the hit and the miss case, with
    counts unchanged on a miss.
  - a visible-only lookup cannot see a soft-deleted row, while an
    include-deleted lookup can.
  - listVisible / listAll are ordered by title ascending.

A naive implementation that physically deletes rows (so the archived row
vanishes from listAll / has no deletion timestamp / can never be restored), or
that hardcodes the boolean returns, cannot pass these assertions.
"""

import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/sequelize"
CORE_DIR = os.path.join(REPO_DIR, "packages", "core")
INTEG_DIR = os.path.join(CORE_DIR, "test", "integration")
MODULE_FILE = os.path.join(INTEG_DIR, "soft-documents.ts")
AGENT_TEST_FILE = os.path.join(INTEG_DIR, "soft-documents.test.ts")

# Basename for the independent specs we drop into the integration tree.
_BENCH_BASENAME = "zzz-bench-soft-documents"


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
    Write a self-contained mocha .test.ts spec into the integration dir, run it,
    then clean it up. Returns the CompletedProcess.
    """
    spec_path = os.path.join(INTEG_DIR, spec_name)
    rel_path = os.path.join("test", "integration", spec_name)
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


# Common TS preamble used by every independent spec. It builds a fresh Document
# model on the shared integration `sequelize` instance via the agent's
# setupDocuments(), (re)creates its table, and seeds three documents whose
# titles are deliberately inserted out of order so that "ordered by title
# ascending" is observable. It then imports the agent's helpers directly.
_PREAMBLE = textwrap.dedent(
    """\
    import { expect } from 'chai';
    import { sequelize } from './support';
    import {
      setupDocuments,
      archive,
      restore,
      listVisible,
      listAll,
    } from './soft-documents';

    async function freshDocuments() {
      const Document = await setupDocuments(sequelize as any);
      // Ensure a clean, empty table for this spec regardless of setup details.
      await Document.sync({ force: true });
      return Document;
    }

    async function seedThree(Document: any) {
      // Insert deliberately OUT of title order: Charlie, Alpha, Bravo.
      const charlie = await Document.create({ title: 'Charlie', body: 'c' });
      const alpha = await Document.create({ title: 'Alpha', body: 'a' });
      const bravo = await Document.create({ title: 'Bravo' }); // body optional
      return { charlie, alpha, bravo };
    }

    function titles(rows: any[]): string[] {
      return rows.map((r: any) => r.title);
    }
    """
)


# ---------------------------------------------------------------------------
# Module-scope dependency guard. The container already has the toolchain that
# runs `yarn mocha`; we best-effort ensure node_modules is present so the
# native command can resolve mocha/chai/esbuild/the sqlite dialect.
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
            # If install fails here, the native test calls below will surface an
            # explicit, debuggable error.
            pass
    yield


class TestSequelizeOrm:
    """Verify the soft-deletable documents deliverable (variant ext10)."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """The domain module soft-documents.ts must exist."""
        assert os.path.isfile(MODULE_FILE), f"missing module file: {MODULE_FILE}"

    def test_agent_test_file_exists(self):
        """The agent's own integration test soft-documents.test.ts must exist."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing test file: {AGENT_TEST_FILE}"

    def test_module_exports_required_symbols(self):
        """soft-documents.ts must export every required helper + setup symbol."""
        src = _read(MODULE_FILE)
        assert "export" in src, "module does not export anything"
        for sym in ("setupDocuments", "archive", "restore", "listVisible", "listAll"):
            assert sym in src, f"module does not reference required export `{sym}`"

    def test_agent_test_imports_module(self):
        """The agent's test must import from the local soft-documents module."""
        src = _read(AGENT_TEST_FILE)
        assert "soft-documents" in src, "test does not reference the soft-documents module"

    # ------------------------------------------------------------------
    # L2 — independent dynamic execution via native `yarn mocha`.
    # Each test writes its own spec, so failures are isolated and specific.
    # ------------------------------------------------------------------

    def test_setup_returns_document_model_with_fields(self):
        """setupDocuments returns a real Document model carrying title + body columns."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('soft-documents: setup + model shape', () => {
              it('returns a real Sequelize model with title and body attributes', async () => {
                const Document = await freshDocuments();
                expect(Document, 'setupDocuments returned nothing').to.exist;
                expect(typeof Document.getAttributes, 'not a model class').to.equal('function');
                expect(typeof Document.create, 'not a model class').to.equal('function');

                const attrs: any = Document.getAttributes();
                expect(attrs, 'Document has no title column').to.have.property('title');
                expect(attrs, 'Document has no body column').to.have.property('body');
              });

              it('can persist a document and read it back', async () => {
                const Document = await freshDocuments();
                const created = await Document.create({ title: 'Solo', body: 'x' });
                expect(created.title).to.equal('Solo');
                const all = await listAll(Document);
                expect(titles(all)).to.deep.equal(['Solo']);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-setup.test.ts", spec)
        _assert_mocha_passed(result, "setupDocuments returns Document model with fields")

    def test_archive_hides_from_visible_but_kept_in_all(self):
        """archive() removes a doc from listVisible while listAll still contains it."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('soft-documents: archive hides but keeps row', () => {
              it('archived doc leaves listVisible but stays in listAll', async () => {
                const Document = await freshDocuments();
                const { bravo } = await seedThree(Document);

                const ok = await archive(Document, bravo.id);
                expect(ok, 'archive of a visible doc must return true').to.equal(true);

                const visible = await listVisible(Document);
                expect(titles(visible),
                  'archived Bravo must not appear in listVisible')
                  .to.deep.equal(['Alpha', 'Charlie']);

                const all = await listAll(Document);
                expect(titles(all),
                  'archived Bravo must STILL appear in listAll (not physically deleted)')
                  .to.deep.equal(['Alpha', 'Bravo', 'Charlie']);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-archive-hide.test.ts", spec)
        _assert_mocha_passed(result, "archive hides from visible but kept in all")

    def test_archive_stamps_deletion_timestamp(self):
        """An archived row carries a non-null deletion timestamp; a live row does not."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('soft-documents: deletion timestamp', () => {
              // Find the paranoid deletion-timestamp attribute name on the model.
              function deletedAtField(Document: any): string {
                const attrs: any = Document.getAttributes();
                // Common defaults / configured names for the soft-delete column.
                for (const cand of ['deletedAt', 'archivedAt', 'destroyTime', 'deletionDate']) {
                  if (Object.prototype.hasOwnProperty.call(attrs, cand)) return cand;
                }
                // Fall back to the model-configured paranoid option if present.
                const opt = (Document.options && Document.options.deletedAt)
                  || (Document.modelDefinition && Document.modelDefinition.options
                      && Document.modelDefinition.options.deletedAt);
                if (typeof opt === 'string' && attrs[opt]) return opt;
                throw new Error('No soft-delete timestamp column found on Document; attrs='
                  + JSON.stringify(Object.keys(attrs)));
              }

              it('archived row has a deletion timestamp, visible rows do not', async () => {
                const Document = await freshDocuments();
                const { charlie, alpha } = await seedThree(Document);
                const field = deletedAtField(Document);

                await archive(Document, charlie.id);

                // Reload the archived row INCLUDING soft-deleted rows.
                const all = await listAll(Document);
                const archived = all.find((r: any) => r.id === charlie.id);
                expect(archived, 'archived Charlie missing from listAll').to.exist;
                expect((archived as any)[field],
                  'archived row must carry a non-null deletion timestamp')
                  .to.not.equal(null);
                expect((archived as any)[field],
                  'archived row deletion timestamp must be defined')
                  .to.exist;

                // A still-visible row must NOT have a deletion timestamp.
                const live = all.find((r: any) => r.id === alpha.id);
                expect(live, 'live Alpha missing from listAll').to.exist;
                expect((live as any)[field] == null,
                  'a non-archived row must not have a deletion timestamp').to.equal(true);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-timestamp.test.ts", spec)
        _assert_mocha_passed(result, "archive stamps deletion timestamp")

    def test_restore_brings_row_back_to_visible(self):
        """restore() un-deletes an archived doc so it reappears in listVisible."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('soft-documents: restore', () => {
              it('restores a previously archived doc back into listVisible', async () => {
                const Document = await freshDocuments();
                const { alpha } = await seedThree(Document);

                const archived = await archive(Document, alpha.id);
                expect(archived).to.equal(true);

                let visible = await listVisible(Document);
                expect(titles(visible)).to.deep.equal(['Bravo', 'Charlie']);

                const restored = await restore(Document, alpha.id);
                expect(restored, 'restore of an archived doc must return true').to.equal(true);

                visible = await listVisible(Document);
                expect(titles(visible),
                  'restored Alpha must reappear in listVisible, ordered by title')
                  .to.deep.equal(['Alpha', 'Bravo', 'Charlie']);

                // After restore, listAll and listVisible agree again (nothing archived).
                const all = await listAll(Document);
                expect(titles(all)).to.deep.equal(['Alpha', 'Bravo', 'Charlie']);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-restore.test.ts", spec)
        _assert_mocha_passed(result, "restore brings row back to visible")

    def test_archive_returns_false_on_miss(self):
        """archive() returns false for a non-existent id and for an already-archived id; counts unchanged."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('soft-documents: archive miss cases', () => {
              it('archiving a non-existent id returns false and changes nothing', async () => {
                const Document = await freshDocuments();
                await seedThree(Document);

                const beforeVisible = (await listVisible(Document)).length;
                const beforeAll = (await listAll(Document)).length;

                const res = await archive(Document, 999999);
                expect(res, 'archiving a non-existent id must return false').to.equal(false);

                expect((await listVisible(Document)).length,
                  'visible count must be unchanged after a no-op archive').to.equal(beforeVisible);
                expect((await listAll(Document)).length,
                  'total count must be unchanged after a no-op archive').to.equal(beforeAll);
              });

              it('archiving an already-archived id returns false', async () => {
                const Document = await freshDocuments();
                const { charlie } = await seedThree(Document);

                expect(await archive(Document, charlie.id)).to.equal(true);
                // Second archive of the same (now invisible) row: nothing visible to archive.
                const second = await archive(Document, charlie.id);
                expect(second,
                  'archiving an already-archived id must return false').to.equal(false);

                // Still exactly one archived row (not double-counted / not resurrected).
                const all = await listAll(Document);
                expect(all.length).to.equal(3);
                const visible = await listVisible(Document);
                expect(visible.length).to.equal(2);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-archive-miss.test.ts", spec)
        _assert_mocha_passed(result, "archive returns false on miss")

    def test_restore_returns_false_on_miss(self):
        """restore() returns false for a never-archived id and a non-existent id; counts unchanged."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('soft-documents: restore miss cases', () => {
              it('restoring a never-archived id returns false and changes nothing', async () => {
                const Document = await freshDocuments();
                const { alpha } = await seedThree(Document);

                const beforeVisible = titles(await listVisible(Document));

                const res = await restore(Document, alpha.id);
                expect(res,
                  'restoring a row that was never archived must return false').to.equal(false);

                expect(titles(await listVisible(Document)),
                  'listVisible must be unchanged after a no-op restore')
                  .to.deep.equal(beforeVisible);
              });

              it('restoring a non-existent id returns false', async () => {
                const Document = await freshDocuments();
                await seedThree(Document);
                const res = await restore(Document, 999999);
                expect(res,
                  'restoring a non-existent id must return false').to.equal(false);
                expect((await listAll(Document)).length).to.equal(3);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-restore-miss.test.ts", spec)
        _assert_mocha_passed(result, "restore returns false on miss")

    def test_visible_lookup_cannot_see_deleted_include_can(self):
        """A visible-only lookup cannot find a soft-deleted row; an include-deleted lookup can."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('soft-documents: lookup visibility semantics', () => {
              it('the normal (visible-only) findByPk cannot see an archived row', async () => {
                const Document = await freshDocuments();
                const { bravo } = await seedThree(Document);
                await archive(Document, bravo.id);

                // Default lookup excludes soft-deleted rows.
                const found = await Document.findByPk(bravo.id);
                expect(found,
                  'a default lookup must NOT find a soft-deleted row').to.equal(null);
              });

              it('an include-deleted lookup can see the archived row', async () => {
                const Document = await freshDocuments();
                const { bravo } = await seedThree(Document);
                await archive(Document, bravo.id);

                const foundParanoidOff = await Document.findByPk(bravo.id, { paranoid: false });
                expect(foundParanoidOff,
                  'an include-deleted lookup MUST find the soft-deleted row').to.exist;
                expect((foundParanoidOff as any).title).to.equal('Bravo');
              });

              it('the archived row is still physically present (count via listAll)', async () => {
                const Document = await freshDocuments();
                const { bravo } = await seedThree(Document);
                await archive(Document, bravo.id);
                const all = await listAll(Document);
                expect(all.map((r: any) => r.id)).to.include(bravo.id);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-lookup.test.ts", spec)
        _assert_mocha_passed(result, "visible vs include-deleted lookup semantics")

    def test_listings_are_ordered_by_title_ascending(self):
        """listVisible and listAll are both ordered by title ascending."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('soft-documents: ordering', () => {
              it('listVisible and listAll order rows by title ascending', async () => {
                const Document = await freshDocuments();
                // Insert in a scrambled order on purpose.
                await Document.create({ title: 'Delta' });
                await Document.create({ title: 'Alpha' });
                await Document.create({ title: 'Charlie' });
                await Document.create({ title: 'Bravo' });

                const visible = titles(await listVisible(Document));
                expect(visible,
                  'listVisible must be sorted by title ascending')
                  .to.deep.equal(['Alpha', 'Bravo', 'Charlie', 'Delta']);

                const all = titles(await listAll(Document));
                expect(all,
                  'listAll must be sorted by title ascending')
                  .to.deep.equal(['Alpha', 'Bravo', 'Charlie', 'Delta']);
              });

              it('ordering holds even when some rows are archived (listAll)', async () => {
                const Document = await freshDocuments();
                const d = await Document.create({ title: 'Delta' });
                await Document.create({ title: 'Alpha' });
                await Document.create({ title: 'Charlie' });

                await archive(Document, d.id);

                // listAll still includes Delta, still ordered ascending.
                expect(titles(await listAll(Document)))
                  .to.deep.equal(['Alpha', 'Charlie', 'Delta']);
                // listVisible drops Delta but stays ordered.
                expect(titles(await listVisible(Document)))
                  .to.deep.equal(['Alpha', 'Charlie']);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-order.test.ts", spec)
        _assert_mocha_passed(result, "listings ordered by title ascending")

    def test_full_lifecycle_end_to_end(self):
        """Full scenario: seed 3, archive 1, restore it, and exercise both miss cases."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('soft-documents: end-to-end lifecycle', () => {
              it('archive -> restore -> miss cases all behave as specified', async () => {
                const Document = await freshDocuments();
                const { charlie } = await seedThree(Document);

                // Initial state: 3 visible, 3 total.
                expect(titles(await listVisible(Document)))
                  .to.deep.equal(['Alpha', 'Bravo', 'Charlie']);
                expect((await listAll(Document)).length).to.equal(3);

                // Archive Charlie.
                expect(await archive(Document, charlie.id)).to.equal(true);
                expect(titles(await listVisible(Document)))
                  .to.deep.equal(['Alpha', 'Bravo']);
                expect((await listAll(Document)).length).to.equal(3);

                // Miss: archive non-existent.
                expect(await archive(Document, 424242)).to.equal(false);
                expect((await listVisible(Document)).length).to.equal(2);

                // Restore Charlie.
                expect(await restore(Document, charlie.id)).to.equal(true);
                expect(titles(await listVisible(Document)))
                  .to.deep.equal(['Alpha', 'Bravo', 'Charlie']);

                // Miss: restore something that is not archived.
                expect(await restore(Document, charlie.id)).to.equal(false);
                expect(titles(await listVisible(Document)))
                  .to.deep.equal(['Alpha', 'Bravo', 'Charlie']);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-e2e.test.ts", spec, timeout=600)
        _assert_mocha_passed(result, "full lifecycle end-to-end")

    def test_agent_supplied_test_passes(self):
        """The agent's own acceptance command must pass: yarn mocha soft-documents.test.ts."""
        result = _run_mocha(
            os.path.join("test", "integration", "soft-documents.test.ts"),
            timeout=600,
        )
        _assert_mocha_passed(result, "agent-supplied soft-documents.test.ts")
