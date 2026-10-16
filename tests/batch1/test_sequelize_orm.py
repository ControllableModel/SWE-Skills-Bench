"""
Test for the 'sequelize-orm' skill — Build a Library Catalog Domain Model.

The agent must create two files inside @sequelize/core's unit-test tree:
  - packages/core/test/unit/model/library-catalog.ts       (the domain module)
  - packages/core/test/unit/model/library-catalog.test.ts  (its unit test)

The module exports `defineLibraryCatalog(sequelize)` which defines three models
(Author, Book, Tag), wires up their relationships, attaches field validations
(required name, unique email with `must be a valid email`, integer pageCount
with `pageCount must be at least 1`), and registers a reusable `published`
named-query preset (a Sequelize scope) on Book.

Verification strategy
---------------------
L1 cases check that the deliverable files exist and are minimally well-formed.

L2 cases DO NOT trust the agent's own test file. Instead we drop an independent
mocha spec into the repo that *imports the agent's library-catalog module* and
introspects/exercises the real model behaviour (validation paths with exact
message texts, association accessor names + foreign key, junction model name,
base-vs-`published` scope query options, per-instance independence). Each spec
is run via the repository's native command:

    yarn mocha "test/unit/model/<spec>.test.ts"

A naive module that hardcodes return values, skips the relationships, omits the
validations, or fakes the preset cannot pass these introspective assertions.
"""

import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/sequelize"
CORE_DIR = os.path.join(REPO_DIR, "packages", "core")
MODEL_DIR = os.path.join(CORE_DIR, "test", "unit", "model")
MODULE_FILE = os.path.join(MODEL_DIR, "library-catalog.ts")
AGENT_TEST_FILE = os.path.join(MODEL_DIR, "library-catalog.test.ts")

# Where we drop our own independent specs (relative to CORE_DIR for the mocha glob).
_BENCH_BASENAME = "zzz-bench-library-catalog"


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
# agent's factory, plus a tiny helper to assert that .validate() rejects with a
# field error whose message contains an expected substring.
_PREAMBLE = textwrap.dedent(
    """\
    import { expect } from 'chai';
    import { createSequelizeInstance } from '../../support';
    import { defineLibraryCatalog } from './library-catalog';

    function buildCatalog() {
      const sequelize = createSequelizeInstance();
      const models = defineLibraryCatalog(sequelize as any);
      return { sequelize, models };
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
        # Try a yarn install scoped to the repo root (yarn workspaces).
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
    """Verify the library-catalog domain model deliverable."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """The domain module library-catalog.ts must exist."""
        assert os.path.isfile(MODULE_FILE), f"missing module file: {MODULE_FILE}"

    def test_agent_test_file_exists(self):
        """The agent's own unit test library-catalog.test.ts must exist."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing test file: {AGENT_TEST_FILE}"

    def test_module_exports_factory(self):
        """library-catalog.ts must export a `defineLibraryCatalog` function symbol."""
        src = _read(MODULE_FILE)
        assert "defineLibraryCatalog" in src, "defineLibraryCatalog not found in module"
        assert "export" in src, "module does not export anything"

    def test_agent_test_imports_module(self):
        """The agent's test must import from the local library-catalog module."""
        src = _read(AGENT_TEST_FILE)
        assert "library-catalog" in src, "test does not reference the library-catalog module"

    # ------------------------------------------------------------------
    # L2 — independent dynamic execution via native `yarn mocha`.
    # Each test writes its own spec, so failures are isolated and specific.
    # ------------------------------------------------------------------

    def test_factory_returns_three_models(self):
        """defineLibraryCatalog returns { Author, Book, Tag } as real, distinct models."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('library-catalog: factory shape', () => {
              it('returns Author, Book and Tag distinct model classes', () => {
                const { models } = buildCatalog();
                expect(models).to.be.an('object');
                expect(models.Author, 'Author missing').to.exist;
                expect(models.Book, 'Book missing').to.exist;
                expect(models.Tag, 'Tag missing').to.exist;
                // Must be real Sequelize models (have getAttributes / build).
                for (const m of [models.Author, models.Book, models.Tag]) {
                  expect(typeof m.getAttributes, 'not a model class').to.equal('function');
                  expect(typeof m.build, 'not a model class').to.equal('function');
                }
                // Distinct classes.
                expect(models.Author).to.not.equal(models.Book);
                expect(models.Book).to.not.equal(models.Tag);
                expect(models.Author).to.not.equal(models.Tag);
              });

              it('defines models only on the passed instance (no leakage)', () => {
                const a = buildCatalog();
                const b = buildCatalog();
                expect(a.sequelize).to.not.equal(b.sequelize);
                expect(a.models.Author).to.not.equal(b.models.Author);
                expect(a.models.Book).to.not.equal(b.models.Book);
                // Each instance owns its own copy of the models.
                expect(a.sequelize.models.get('Author') || a.models.Author.sequelize)
                  .to.exist;
                expect(a.models.Book.sequelize).to.equal(a.sequelize);
                expect(b.models.Book.sequelize).to.equal(b.sequelize);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-shape.test.ts", spec)
        _assert_mocha_passed(result, "factory shape / independence")

    def test_author_required_name_validation(self):
        """An Author with an empty name fails validation on the `name` field."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('library-catalog: Author.name required', () => {
              it('rejects an empty name', async () => {
                const { models } = buildCatalog();
                const author = models.Author.build({ name: '', email: 'a@b.com' });
                await expectFieldError(author, 'name');
              });

              it('accepts a present name + valid email', async () => {
                const { models } = buildCatalog();
                const author = models.Author.build({ name: 'Ada', email: 'ada@example.com' });
                await author.validate(); // must not throw
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-authorname.test.ts", spec)
        _assert_mocha_passed(result, "Author.name required validation")

    def test_author_email_format_validation_message(self):
        """An invalid Author email fails with the exact `must be a valid email` message."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('library-catalog: Author.email format', () => {
              it('rejects a non-email with the required message text', async () => {
                const { models } = buildCatalog();
                const author = models.Author.build({ name: 'Ada', email: 'not-an-email' });
                await expectFieldError(author, 'email', 'must be a valid email');
              });

              it('accepts a syntactically valid email', async () => {
                const { models } = buildCatalog();
                const author = models.Author.build({ name: 'Ada', email: 'ada@example.com' });
                await author.validate();
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-authoremail.test.ts", spec)
        _assert_mocha_passed(result, "Author.email format validation message")

    def test_book_pagecount_range_validation_message(self):
        """A Book with pageCount < 1 fails with `pageCount must be at least 1`; >=1 passes."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('library-catalog: Book.pageCount range', () => {
              it('rejects pageCount = 0 with the required message text', async () => {
                const { models } = buildCatalog();
                const book = models.Book.build({ title: 'T', pageCount: 0 });
                await expectFieldError(book, 'pageCount', 'pageCount must be at least 1');
              });

              it('accepts pageCount = 200 (otherwise valid)', async () => {
                const { models } = buildCatalog();
                const book = models.Book.build({ title: 'T', pageCount: 200 });
                await book.validate(); // must not throw
              });

              it('accepts the boundary pageCount = 1', async () => {
                const { models } = buildCatalog();
                const book = models.Book.build({ title: 'T', pageCount: 1 });
                await book.validate();
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-pagecount.test.ts", spec)
        _assert_mocha_passed(result, "Book.pageCount range validation message")

    def test_book_title_required_validation(self):
        """A Book missing its required `title` fails validation."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('library-catalog: Book.title required', () => {
              it('rejects an empty title', async () => {
                const { models } = buildCatalog();
                const book = models.Book.build({ title: '', pageCount: 50 });
                await expectFieldError(book, 'title');
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-booktitle.test.ts", spec)
        _assert_mocha_passed(result, "Book.title required validation")

    def test_author_book_one_to_many_relationship(self):
        """Author has `books` (-> Book), Book has `author` (-> Author), FK = authorId."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('library-catalog: Author<->Book association', () => {
              it('wires books/author accessors with foreign key authorId', () => {
                const { models } = buildCatalog();
                const { Author, Book } = models;

                const booksAssoc = Author.associations.books;
                expect(booksAssoc, 'Author.associations.books missing').to.exist;
                expect(booksAssoc.target, 'books should target Book').to.equal(Book);

                const authorAssoc = Book.associations.author;
                expect(authorAssoc, 'Book.associations.author missing').to.exist;
                expect(authorAssoc.target, 'author should target Author').to.equal(Author);

                // Foreign key column linking book -> author must be authorId.
                const fk = (authorAssoc as any).foreignKey
                  || (booksAssoc as any).foreignKey;
                expect(fk, 'foreign key should be authorId').to.equal('authorId');

                // The Book model must actually carry an authorId attribute column.
                expect(Book.getAttributes(), 'Book has no authorId column')
                  .to.have.property('authorId');
              });

              it('exposes runtime accessor methods for the association', () => {
                const { models } = buildCatalog();
                const { Author, Book } = models;
                // Author.prototype should have a getBooks accessor; Book a getAuthor.
                expect(typeof (Author.prototype as any).getBooks).to.equal('function');
                expect(typeof (Book.prototype as any).getAuthor).to.equal('function');
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-authorbook.test.ts", spec)
        _assert_mocha_passed(result, "Author<->Book one-to-many association")

    def test_book_tag_many_to_many_through_junction(self):
        """Book has `tags`, Tag has `books`, both routed through the `BookTags` junction."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('library-catalog: Book<->Tag many-to-many', () => {
              it('wires tags/books accessors through the BookTags junction', () => {
                const { sequelize, models } = buildCatalog();
                const { Book, Tag } = models;

                const tagsAssoc = Book.associations.tags;
                expect(tagsAssoc, 'Book.associations.tags missing').to.exist;
                expect(tagsAssoc.target, 'tags should target Tag').to.equal(Tag);

                const booksAssoc = Tag.associations.books;
                expect(booksAssoc, 'Tag.associations.books missing').to.exist;
                expect(booksAssoc.target, 'books should target Book').to.equal(Book);

                // Junction model must be named BookTags and be registered.
                const through = (tagsAssoc as any).throughModel
                  || (tagsAssoc as any).through?.model;
                expect(through, 'tags association has no through model').to.exist;
                const throughName = through.name || (through.modelDefinition
                  && through.modelDefinition.modelName);
                expect(String(throughName)).to.equal('BookTags');

                // The junction must be retrievable from the instance's model registry.
                const fromRegistry = sequelize.models.getOrThrow('BookTags');
                expect(fromRegistry).to.exist;
              });

              it('exposes belongsToMany runtime accessors (getTags / getBooks)', () => {
                const { models } = buildCatalog();
                const { Book, Tag } = models;
                expect(typeof (Book.prototype as any).getTags).to.equal('function');
                expect(typeof (Book.prototype as any).addTag
                  || (Book.prototype as any).addTags).to.equal('function');
                expect(typeof (Tag.prototype as any).getBooks).to.equal('function');
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-booktag.test.ts", spec)
        _assert_mocha_passed(result, "Book<->Tag many-to-many through BookTags")

    def test_published_preset_distinct_from_base(self):
        """The `published` preset restricts published=truthy; base query has no such filter."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('library-catalog: published preset', () => {
              function scopeWhere(model: any): any {
                // Effective scope query options for the (possibly scoped) model.
                const sc = model._scope || (model.options && model.options.defaultScope) || {};
                return sc.where || {};
              }

              it('base Book carries no published restriction', () => {
                const { models } = buildCatalog();
                const baseWhere = scopeWhere(models.Book);
                expect(Object.prototype.hasOwnProperty.call(baseWhere, 'published'),
                  'base Book unexpectedly restricts published').to.equal(false);
              });

              it('published preset restricts published to a truthy value', () => {
                const { models } = buildCatalog();
                const scoped = models.Book.withScope('published');
                expect(scoped, 'withScope("published") returned nothing').to.exist;
                const where = scopeWhere(scoped);
                expect(Object.prototype.hasOwnProperty.call(where, 'published'),
                  'published preset does not restrict the published attribute').to.equal(true);
                // The restriction must be truthy (true / 1 / not false / not null).
                const val = (where as any).published;
                const truthy = val === true || val === 1
                  || (val && typeof val === 'object'); // Op-based restriction also accepted
                expect(Boolean(truthy),
                  'published preset restriction is not truthy: ' + JSON.stringify(val))
                  .to.equal(true);
                expect(val === false || val === 0 || val == null,
                  'published preset restriction must not be falsy').to.equal(false);
              });

              it('applying the preset does not mutate the base model', () => {
                const { models } = buildCatalog();
                models.Book.withScope('published'); // apply once
                const baseWhere = scopeWhere(models.Book);
                expect(Object.prototype.hasOwnProperty.call(baseWhere, 'published'),
                  'preset leaked into base model').to.equal(false);
              });

              it('Book has a published boolean attribute defaulting to not-published', () => {
                const { models } = buildCatalog();
                const attrs: any = models.Book.getAttributes();
                expect(attrs, 'Book has no published attribute').to.have.property('published');
                const built = models.Book.build({ title: 'T', pageCount: 5 });
                // default should be falsy (not published)
                expect(Boolean((built as any).published)).to.equal(false);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-preset.test.ts", spec, timeout=600)
        _assert_mocha_passed(result, "published preset vs base query options")

    def test_two_instances_are_independent(self):
        """Two separate Sequelize instances each get a fully independent model set."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('library-catalog: per-instance independence', () => {
              it('models, associations and scopes do not bleed across instances', async () => {
                const a = buildCatalog();
                const b = buildCatalog();

                // Distinct model classes per instance.
                expect(a.models.Book).to.not.equal(b.models.Book);
                expect(a.models.Author).to.not.equal(b.models.Author);

                // Associations resolve within their own instance only.
                expect(a.models.Author.associations.books.target).to.equal(a.models.Book);
                expect(b.models.Author.associations.books.target).to.equal(b.models.Book);
                expect(a.models.Author.associations.books.target).to.not.equal(b.models.Book);

                // Validation works independently on each instance.
                const badA = a.models.Book.build({ title: 'x', pageCount: 0 });
                await expectFieldError(badA, 'pageCount', 'pageCount must be at least 1');
                const goodB = b.models.Book.build({ title: 'y', pageCount: 10 });
                await goodB.validate();

                // The published preset is available on both instances.
                expect(a.models.Book.withScope('published')).to.exist;
                expect(b.models.Book.withScope('published')).to.exist;
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-independence.test.ts", spec)
        _assert_mocha_passed(result, "per-instance independence")

    def test_agent_supplied_test_passes(self):
        """The agent's own acceptance command must pass: yarn mocha library-catalog.test.ts."""
        result = _run_mocha(
            os.path.join("test", "unit", "model", "library-catalog.test.ts"),
            timeout=600,
        )
        _assert_mocha_passed(result, "agent-supplied library-catalog.test.ts")
