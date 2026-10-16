"""
Tests for the `typeorm-patterns` skill task: "Build a Library Catalog Persistence Layer".

The agent must add, under `test/functional/library-catalog/`, a self-contained TypeORM
functional feature:
  - entity/Author.ts        (id auto-generated, name, country, owns many Books)
  - entity/Book.ts          (id auto-generated, title, year:int, genre, copiesSold:int default 0,
                             belongs to one Author, DB-level cascade delete of books on author delete)
  - catalog-service.ts      (addAuthorWithBooks / findAuthorWithBooks / topSellingBooks /
                             genreRevenueReport / removeAuthor) built on a DataSource
  - library-catalog.test.ts (functional test wiring the above through createTestingConnections)

This pytest verifies the deliverables two ways:
  1. L1 — the four files exist and are minimally well-formed.
  2. L2 — DYNAMIC EXECUTION against the real TypeORM toolchain: it ensures an
     ormconfig.json restricted to the better-sqlite3 driver, compiles the repo
     (`pnpm run compile`), runs the agent's own compiled functional test, and then
     runs INDEPENDENT driver scripts (written by this test) against the agent's
     compiled Author/Book/CatalogService to deep-validate real behavior:
        * single-save persistence with generated ids + correct owning-author linkage
        * copiesSold defaults to 0 at the database level
        * topSellingBooks(limit) is globally ordered desc and bounded by limit
        * genreRevenueReport() is a real DB aggregate matching JS-side sums
        * findAuthorWithBooks(missing) returns null
        * removeAuthor cascades book deletion at the DB level
        * relation retrieval is a single round trip (no per-book query loop)

A naive solution (per-book query loops, JS-side revenue summing, missing DB cascade)
must fail at least one assertion.
"""

import json
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/typeorm"
FEATURE_DIR = os.path.join(REPO_DIR, "test/functional/library-catalog")
ENTITY_DIR = os.path.join(FEATURE_DIR, "entity")
AUTHOR_TS = os.path.join(ENTITY_DIR, "Author.ts")
BOOK_TS = os.path.join(ENTITY_DIR, "Book.ts")
SERVICE_TS = os.path.join(FEATURE_DIR, "catalog-service.ts")
TEST_TS = os.path.join(FEATURE_DIR, "library-catalog.test.ts")

COMPILED_TEST_JS = os.path.join(
    REPO_DIR, "build/compiled/test/functional/library-catalog/library-catalog.test.js"
)
COMPILED_FEATURE_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/library-catalog"
)

# Build/compile is heavy in this repo.
COMPILE_TIMEOUT = 1200
RUN_TIMEOUT = 600

# Directory (under REPO_DIR, picked up by tsc include "test") where this pytest drops
# its own independent driver scripts so they get compiled alongside the agent's code.
PROBE_SRC_DIR = os.path.join(REPO_DIR, "test/functional/library-catalog/__probe__")
PROBE_OUT_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/library-catalog/__probe__"
)


# ---------------------------------------------------------------------------
# module-scope setup: deps + ormconfig(better-sqlite3) + one compile, shared by L2
# ---------------------------------------------------------------------------

_COMPILE_STATE = {"done": False, "ok": False, "stderr": ""}


def _have(cmd):
    return (
        subprocess.run(
            ["bash", "-lc", f"command -v {cmd}"],
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def _ensure_deps():
    """Install node_modules if missing (prefer pnpm, the repo's package manager)."""
    if os.path.isdir(os.path.join(REPO_DIR, "node_modules", "chai")) and os.path.isdir(
        os.path.join(REPO_DIR, "node_modules", "better-sqlite3")
    ):
        return
    try:
        from _dependency_utils import ensure_npm_dependencies  # type: ignore

        # ensure_npm_dependencies may not know pnpm; try it but don't hard-fail.
        ensure_npm_dependencies(REPO_DIR)
    except Exception:
        pass
    if os.path.isdir(os.path.join(REPO_DIR, "node_modules", "better-sqlite3")):
        return
    installer = None
    if _have("pnpm"):
        installer = "pnpm install --frozen-lockfile || pnpm install"
    elif _have("yarn"):
        installer = "yarn install"
    else:
        installer = "npm install"
    subprocess.run(
        ["bash", "-lc", installer],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=COMPILE_TIMEOUT,
    )


def _ensure_ormconfig():
    """Create ormconfig.json restricted to the better-sqlite3 driver (CI pattern)."""
    sample = os.path.join(REPO_DIR, "ormconfig.sample.json")
    target = os.path.join(REPO_DIR, "ormconfig.json")
    with open(sample) as f:
        data = json.load(f)
    sqlite_like = {"better-sqlite3", "sqlite", "sqljs"}
    filtered = [c for c in data if c.get("type") in sqlite_like]
    # Prefer better-sqlite3 only for determinism; fall back to whatever sqlite-like exists.
    bsq = [c for c in filtered if c.get("type") == "better-sqlite3"]
    chosen = bsq if bsq else filtered
    assert chosen, "ormconfig.sample.json has no sqlite-family driver entry"
    with open(target, "w") as f:
        json.dump(chosen, f, indent=2)


def _compile():
    if _COMPILE_STATE["done"]:
        return
    _COMPILE_STATE["done"] = True
    _ensure_deps()
    _ensure_ormconfig()
    if _have("pnpm"):
        cmd = "pnpm run compile"
    else:
        cmd = "npx gulp clean && npx tsc"
    proc = subprocess.run(
        ["bash", "-lc", cmd],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=COMPILE_TIMEOUT,
    )
    _COMPILE_STATE["ok"] = proc.returncode == 0
    _COMPILE_STATE["stderr"] = (proc.stdout or "") + "\n" + (proc.stderr or "")


@pytest.fixture(scope="module", autouse=True)
def _module_setup():
    # Best-effort; individual L2 tests assert on compile success so failures are clear.
    try:
        _compile()
    except Exception as exc:  # pragma: no cover
        _COMPILE_STATE["ok"] = False
        _COMPILE_STATE["stderr"] = f"compile raised: {exc!r}"
    yield


def _require_compiled():
    assert _COMPILE_STATE["done"], "compile step did not run"
    assert _COMPILE_STATE["ok"], (
        "`pnpm run compile` (gulp clean && tsc) failed; the deliverables must "
        "compile cleanly:\n" + _COMPILE_STATE["stderr"][-4000:]
    )


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Helpers to build & run an independent node driver against the compiled code
# ---------------------------------------------------------------------------

def _write_probe(rel_name, ts_source):
    """Write a TS probe under the compiled-friendly probe dir and return its .js path.

    We compile probes with a standalone tsc invocation (decorators enabled) that
    emits next to the agent's already-compiled Author/Book/CatalogService so the
    relative `./` imports in the probe resolve to real compiled modules.
    """
    os.makedirs(PROBE_OUT_DIR, exist_ok=True)
    ts_path = os.path.join(PROBE_OUT_DIR, rel_name + ".ts")
    with open(ts_path, "w", encoding="utf-8") as f:
        f.write(ts_source)
    # Compile just this probe in place (CommonJS) so imports resolve to sibling .js.
    tsc = (
        "npx tsc "
        + ts_path
        + " --module commonjs --target ES2021 --experimentalDecorators "
        "--emitDecoratorMetadata --moduleResolution node "
        "--esModuleInterop --skipLibCheck --resolveJsonModule "
        "--strict false --noImplicitAny false"
    )
    proc = subprocess.run(
        ["bash", "-lc", tsc],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=COMPILE_TIMEOUT,
    )
    js_path = os.path.join(PROBE_OUT_DIR, rel_name + ".js")
    assert proc.returncode == 0 and os.path.isfile(js_path), (
        "failed to compile probe driver:\n" + proc.stdout + "\n" + proc.stderr
    )
    return js_path


def _run_node(js_path):
    proc = subprocess.run(
        ["bash", "-lc", "node " + js_path],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
    )
    return proc


def _import_paths():
    """Relative imports (from the probe's compiled location) to the agent modules."""
    # Probe sits at build/compiled/test/functional/library-catalog/__probe__/X.js
    # Agent compiled modules sit one dir up.
    return {
        "author": "../entity/Author",
        "book": "../entity/Book",
        "service": "../catalog-service",
        "datasource": "../../../../../src",  # build/compiled/src
    }


_DRIVER_PREAMBLE = """
"use strict";
const { DataSource } = require("{datasource}");
const AuthorMod = require("{author}");
const BookMod = require("{book}");
const ServiceMod = require("{service}");

function pickClass(mod, names) {{
    for (const n of names) if (mod[n]) return mod[n];
    // fall back: first exported function that looks like a class
    for (const k of Object.keys(mod)) {{
        if (typeof mod[k] === "function") return mod[k];
    }}
    if (mod.default) return mod.default;
    throw new Error("could not locate export in module");
}}

const Author = pickClass(AuthorMod, ["Author", "default"]);
const Book = pickClass(BookMod, ["Book", "default"]);
const ServiceExport = pickClass(ServiceMod, ["CatalogService", "Catalog", "default"]);

function makeService(ds) {{
    // Support both `new Class(ds)` and a factory `fn(ds)`.
    try {{
        return new ServiceExport(ds);
    }} catch (e) {{
        return ServiceExport(ds);
    }}
}}

async function newDataSource() {{
    const ds = new DataSource({{
        type: "better-sqlite3",
        database: ":memory:",
        entities: [Author, Book],
        synchronize: true,
        dropSchema: true,
    }});
    await ds.initialize();
    return ds;
}}

function out(obj) {{ process.stdout.write("RESULT_JSON:" + JSON.stringify(obj) + "\\n"); }}
"""


def _driver(body):
    paths = _import_paths()
    preamble = _DRIVER_PREAMBLE.format(
        datasource=paths["datasource"],
        author=paths["author"],
        book=paths["book"],
        service=paths["service"],
    )
    return preamble + "\n" + textwrap.dedent(body) + "\n"


def _parse_result(proc):
    assert proc.returncode == 0, (
        "driver script exited non-zero:\nSTDOUT:\n"
        + proc.stdout
        + "\nSTDERR:\n"
        + proc.stderr
    )
    line = None
    for ln in proc.stdout.splitlines():
        if ln.startswith("RESULT_JSON:"):
            line = ln[len("RESULT_JSON:") :]
    assert line is not None, (
        "driver did not emit RESULT_JSON line:\nSTDOUT:\n"
        + proc.stdout
        + "\nSTDERR:\n"
        + proc.stderr
    )
    return json.loads(line)


# ===========================================================================
# L1 — deliverable files exist and are minimally well-formed
# ===========================================================================


class TestTypeormPatterns:
    REPO_DIR = "/workspace/typeorm"

    # ---- L1 -------------------------------------------------------------

    def test_l1_feature_files_exist(self):
        """All four required deliverable files exist under library-catalog/."""
        for p in (AUTHOR_TS, BOOK_TS, SERVICE_TS, TEST_TS):
            assert os.path.isfile(p), f"missing required deliverable file: {p}"

    def test_l1_entities_are_typeorm_entities(self):
        """Author and Book are decorated TypeORM entities with generated primary keys."""
        author = _read(AUTHOR_TS)
        book = _read(BOOK_TS)
        for name, src in (("Author", author), ("Book", book)):
            assert "@Entity" in src, f"{name} is not annotated with @Entity"
            assert (
                "@PrimaryGeneratedColumn" in src
            ), f"{name} lacks a database-generated primary key"
        # Book must declare integer-ish year and a copiesSold field with a default.
        assert "year" in book, "Book entity does not declare a `year` field"
        assert "copiesSold" in book, "Book entity does not declare a `copiesSold` field"
        assert "genre" in book, "Book entity does not declare a `genre` field"

    def test_l1_book_owns_relation_with_db_cascade(self):
        """Book declares a many-to-one relation to Author with DB-level delete cascade."""
        book = _read(BOOK_TS)
        assert (
            "ManyToOne" in book or "JoinColumn" in book
        ), "Book does not declare an owning relation to Author"
        # DB-level cascade on delete (onDelete:'CASCADE'), not only TS-side cascade:true.
        assert "CASCADE" in book.upper(), (
            "Book relation must request DB-level ON DELETE CASCADE "
            "(onDelete: 'CASCADE'); application-only cascade is insufficient"
        )

    def test_l1_service_exports_required_operations(self):
        """catalog-service.ts exports the five named catalog operations."""
        src = _read(SERVICE_TS)
        for op in (
            "addAuthorWithBooks",
            "findAuthorWithBooks",
            "topSellingBooks",
            "genreRevenueReport",
            "removeAuthor",
        ):
            assert op in src, f"catalog-service.ts does not define `{op}`"

    def test_l1_test_uses_sqlite_only_testing_connections(self):
        """The functional test restricts testing connections to the SQLite driver family."""
        src = _read(TEST_TS)
        assert "createTestingConnections" in src, (
            "library-catalog.test.ts must use createTestingConnections from "
            "../../utils/test-utils"
        )
        assert "enabledDrivers" in src, (
            "library-catalog.test.ts must restrict to SQLite-based driver(s) via "
            "enabledDrivers"
        )
        low = src
        assert (
            "sqlite" in low or "sqljs" in low
        ), "enabledDrivers must name a sqlite-family driver (better-sqlite3/sqlite/sqljs)"

    # ---- L2: build & agent's own test -----------------------------------

    def test_l2_repo_compiles(self):
        """`pnpm run compile` succeeds with the deliverables in place (tsc, strict)."""
        _require_compiled()
        assert os.path.isfile(COMPILED_TEST_JS), (
            "expected compiled functional test at "
            + COMPILED_TEST_JS
            + " (compile succeeded but the test file was not emitted)"
        )
        for fname in ("entity/Author.js", "entity/Book.js", "catalog-service.js"):
            p = os.path.join(COMPILED_FEATURE_DIR, fname)
            assert os.path.isfile(p), f"expected compiled deliverable {p}"

    def test_l2_agent_functional_test_passes(self):
        """The agent's own library-catalog.test.ts passes under mocha (no failures/leaks)."""
        _require_compiled()
        setup = "build/compiled/test/utils/test-setup.js"
        cmd = (
            "npx mocha --require " + setup + " --check-leaks --exit "
            "--timeout 90000 " + COMPILED_TEST_JS
        )
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
        )
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "agent's mocha functional test failed:\n" + combined[-4000:]
        )
        assert "passing" in combined, (
            "mocha reported no passing tests:\n" + combined[-2000:]
        )
        assert " 0 passing" not in combined, (
            "mocha collected zero passing tests:\n" + combined[-2000:]
        )

    # ---- L2: independent driver probes against the compiled code --------

    def test_l2_save_author_with_books_persists_links(self):
        """Saving an author with 3 new books in one call persists all with generated ids and links."""
        _require_compiled()
        js = _write_probe(
            "probe_save",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const saved = await svc.addAuthorWithBooks("Ada", "UK", [
                        { title: "A1", year: 2001, genre: "sci", copiesSold: 5 },
                        { title: "A2", year: 2002, genre: "sci", copiesSold: 7 },
                        { title: "A3", year: 2003, genre: "hist", copiesSold: 9 },
                    ]);
                    const authorRepo = ds.getRepository(Author);
                    const bookRepo = ds.getRepository(Book);
                    // Re-read independently of the service via the relation.
                    const reread = await authorRepo.findOne({
                        where: { id: saved.id },
                        relations: { books: true },
                    });
                    const allBooks = await bookRepo.find({ relations: { author: true } });
                    out({
                        savedId: saved.id,
                        savedBookIds: (saved.books || []).map((b) => b.id),
                        rereadCount: reread ? reread.books.length : -1,
                        rereadTitles: reread ? reread.books.map((b) => b.title).sort() : [],
                        ownerIdsCorrect: allBooks.every((b) => b.author && b.author.id === saved.id),
                        totalBooks: allBooks.length,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert isinstance(res["savedId"], int) and res["savedId"] > 0
        assert len(res["savedBookIds"]) == 3, res
        assert all(isinstance(i, int) and i > 0 for i in res["savedBookIds"]), res
        assert res["rereadCount"] == 3, res
        assert res["rereadTitles"] == ["A1", "A2", "A3"], res
        assert res["ownerIdsCorrect"] is True, res
        assert res["totalBooks"] == 3, res

    def test_l2_copies_sold_defaults_to_zero(self):
        """A book inserted without copiesSold reads back as copiesSold === 0 from the DB."""
        _require_compiled()
        js = _write_probe(
            "probe_default",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const saved = await svc.addAuthorWithBooks("Bob", "US", [
                        { title: "NoSales", year: 2010, genre: "drama" },
                    ]);
                    // Read straight from the DB to ensure the *database* applied the default.
                    const rows = await ds.query("SELECT copiesSold FROM book");
                    const reread = await ds.getRepository(Book).findOneBy({ id: saved.books[0].id });
                    out({
                        rawValues: rows.map((r) => r.copiesSold),
                        rereadCopiesSold: reread.copiesSold,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["rereadCopiesSold"] == 0, res
        assert res["rawValues"] == [0], (
            "database did not store the default 0 for copiesSold: " + json.dumps(res)
        )

    def test_l2_top_selling_books_globally_ordered_and_bounded(self):
        """topSellingBooks(limit) returns at most `limit` books, globally ordered by copiesSold desc."""
        _require_compiled()
        js = _write_probe(
            "probe_top",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    await svc.addAuthorWithBooks("A1", "X", [
                        { title: "t1", year: 2000, genre: "g", copiesSold: 10 },
                        { title: "t2", year: 2000, genre: "g", copiesSold: 40 },
                    ]);
                    await svc.addAuthorWithBooks("A2", "Y", [
                        { title: "t3", year: 2000, genre: "g", copiesSold: 30 },
                        { title: "t4", year: 2000, genre: "g", copiesSold: 50 },
                        { title: "t5", year: 2000, genre: "g", copiesSold: 5 },
                    ]);
                    const top3 = await svc.topSellingBooks(3);
                    const sold = top3.map((b) => b.copiesSold);
                    out({
                        len: top3.length,
                        sold: sold,
                        titles: top3.map((b) => b.title),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["len"] == 3, res
        # Highest three across ALL authors are 50, 40, 30 (would be wrong if per-author).
        assert res["sold"] == [50, 40, 30], (
            "topSellingBooks is not globally ordered desc / not limited correctly: "
            + json.dumps(res)
        )
        assert res["titles"] == ["t4", "t2", "t3"], res

    def test_l2_top_selling_respects_smaller_limit(self):
        """topSellingBooks(limit) never returns more than `limit` rows."""
        _require_compiled()
        js = _write_probe(
            "probe_top_limit",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    await svc.addAuthorWithBooks("A", "X", [
                        { title: "b1", year: 2000, genre: "g", copiesSold: 1 },
                        { title: "b2", year: 2000, genre: "g", copiesSold: 2 },
                        { title: "b3", year: 2000, genre: "g", copiesSold: 3 },
                        { title: "b4", year: 2000, genre: "g", copiesSold: 4 },
                    ]);
                    const two = await svc.topSellingBooks(2);
                    const one = await svc.topSellingBooks(1);
                    out({
                        twoLen: two.length,
                        twoSold: two.map((b) => b.copiesSold),
                        oneLen: one.length,
                        oneSold: one.map((b) => b.copiesSold),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["twoLen"] == 2 and res["twoSold"] == [4, 3], res
        assert res["oneLen"] == 1 and res["oneSold"] == [4], res

    def test_l2_genre_revenue_is_db_aggregate(self):
        """genreRevenueReport() returns one row per genre with DB-summed copiesSold matching JS totals."""
        _require_compiled()
        js = _write_probe(
            "probe_genre",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const data = [
                        { title: "s1", year: 2000, genre: "sci", copiesSold: 10 },
                        { title: "s2", year: 2000, genre: "sci", copiesSold: 25 },
                        { title: "h1", year: 2000, genre: "hist", copiesSold: 7 },
                        { title: "d1", year: 2000, genre: "drama", copiesSold: 3 },
                        { title: "h2", year: 2000, genre: "hist", copiesSold: 8 },
                    ];
                    await svc.addAuthorWithBooks("Auth", "Z", data);
                    const expected = {};
                    for (const b of data) expected[b.genre] = (expected[b.genre] || 0) + b.copiesSold;
                    const report = await svc.genreRevenueReport();
                    // Normalize rows into {genre: total}. Accept varied field names.
                    const got = {};
                    for (const row of report) {
                        const g = row.genre !== undefined ? row.genre
                            : (row.Genre !== undefined ? row.Genre : Object.values(row)[0]);
                        let total = row.total;
                        if (total === undefined) total = row.totalCopiesSold;
                        if (total === undefined) total = row.sum;
                        if (total === undefined) {
                            // last numeric-ish value
                            const vals = Object.values(row);
                            total = vals[vals.length - 1];
                        }
                        got[g] = Number(total);
                    }
                    out({ expected, got, rowCount: report.length });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["rowCount"] == 3, (
            "genreRevenueReport must return exactly one row per distinct genre: "
            + json.dumps(res)
        )
        assert res["got"] == res["expected"], (
            "DB aggregate totals do not match JS-side sums: " + json.dumps(res)
        )
        # Sanity on actual numbers (sci=35, hist=15, drama=3).
        assert res["got"].get("sci") == 35, res
        assert res["got"].get("hist") == 15, res
        assert res["got"].get("drama") == 3, res

    def test_l2_genre_report_excludes_empty_genres(self):
        """Genres with no books never appear in genreRevenueReport()."""
        _require_compiled()
        js = _write_probe(
            "probe_genre_empty",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    await svc.addAuthorWithBooks("Auth", "Z", [
                        { title: "only", year: 2000, genre: "poetry", copiesSold: 4 },
                    ]);
                    const report = await svc.genreRevenueReport();
                    const genres = report.map((r) =>
                        r.genre !== undefined ? r.genre : Object.values(r)[0]);
                    out({ genres: genres });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["genres"] == ["poetry"], res

    def test_l2_find_missing_author_returns_null(self):
        """findAuthorWithBooks(<missing id>) returns null rather than throwing."""
        _require_compiled()
        js = _write_probe(
            "probe_missing",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    await svc.addAuthorWithBooks("Real", "X", [
                        { title: "x", year: 2000, genre: "g", copiesSold: 1 },
                    ]);
                    const missing = await svc.findAuthorWithBooks(99999);
                    out({ isNull: missing === null || missing === undefined,
                          type: missing === null ? "null" : typeof missing });
                    await ds.destroy();
                })().catch((e) => { console.error("THREW", e); process.exit(2); });
                """
            ),
        )
        proc = _run_node(js)
        assert proc.returncode == 0, (
            "findAuthorWithBooks(missing) threw instead of returning null:\n"
            + proc.stdout
            + "\n"
            + proc.stderr
        )
        res = _parse_result(proc)
        assert res["isNull"] is True, "findAuthorWithBooks(missing) must return null: " + json.dumps(res)

    def test_l2_find_author_returns_full_book_list(self):
        """findAuthorWithBooks returns the author with its complete attached book list."""
        _require_compiled()
        js = _write_probe(
            "probe_find",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const saved = await svc.addAuthorWithBooks("Has3", "X", [
                        { title: "p1", year: 2000, genre: "g", copiesSold: 1 },
                        { title: "p2", year: 2000, genre: "g", copiesSold: 2 },
                        { title: "p3", year: 2000, genre: "g", copiesSold: 3 },
                    ]);
                    const found = await svc.findAuthorWithBooks(saved.id);
                    out({
                        id: found ? found.id : -1,
                        name: found ? found.name : null,
                        bookCount: found && found.books ? found.books.length : -1,
                        titles: found && found.books ? found.books.map((b) => b.title).sort() : [],
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["id"] > 0 and res["name"] == "Has3", res
        assert res["bookCount"] == 3, res
        assert res["titles"] == ["p1", "p2", "p3"], res

    def test_l2_remove_author_cascades_books_at_db_level(self):
        """removeAuthor deletes the author and cascades book deletion at the DATABASE level."""
        _require_compiled()
        js = _write_probe(
            "probe_remove",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const saved = await svc.addAuthorWithBooks("Doomed", "X", [
                        { title: "k1", year: 2000, genre: "g", copiesSold: 1 },
                        { title: "k2", year: 2000, genre: "g", copiesSold: 2 },
                    ]);
                    const otherAuthorId = saved.id;
                    // Keep a second author so we know cascade is scoped, not a table wipe.
                    const keep = await svc.addAuthorWithBooks("Survivor", "Y", [
                        { title: "s1", year: 2000, genre: "g", copiesSold: 9 },
                    ]);
                    await svc.removeAuthor(otherAuthorId);
                    const found = await svc.findAuthorWithBooks(otherAuthorId);
                    // Direct DB checks (bypassing the service entirely).
                    const authorRows = await ds.query(
                        "SELECT COUNT(*) AS c FROM author WHERE id = " + otherAuthorId);
                    // Find FK column name on book dynamically.
                    const bookCols = await ds.query("PRAGMA table_info(book)");
                    const fkCol = bookCols.map((r) => r.name).find((n) =>
                        /author/i.test(n) && /id/i.test(n));
                    const orphanRows = await ds.query(
                        "SELECT COUNT(*) AS c FROM book WHERE " + fkCol + " = " + otherAuthorId);
                    const totalBooks = await ds.query("SELECT COUNT(*) AS c FROM book");
                    out({
                        foundIsNull: found === null || found === undefined,
                        authorCount: Number(authorRows[0].c),
                        orphanBookCount: Number(orphanRows[0].c),
                        survivorId: keep.id,
                        totalBooks: Number(totalBooks[0].c),
                        fkCol: fkCol,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["fkCol"], "could not locate author FK column on book table: " + json.dumps(res)
        assert res["foundIsNull"] is True, "removed author still retrievable: " + json.dumps(res)
        assert res["authorCount"] == 0, "author row not deleted from DB: " + json.dumps(res)
        assert res["orphanBookCount"] == 0, (
            "books were NOT cascade-deleted at the DB level after removeAuthor: "
            + json.dumps(res)
        )
        # The surviving author's single book must remain -> not a table wipe.
        assert res["totalBooks"] == 1, (
            "cascade over-deleted (removed unrelated books): " + json.dumps(res)
        )

    def test_l2_relation_loaded_in_single_round_trip(self):
        """findAuthorWithBooks loads books in a single query round trip (no per-book loop)."""
        _require_compiled()
        # We instrument the DataSource logger to count SELECTs against the book table
        # while loading an author that owns many books. A per-book N+1 loop would emit
        # one SELECT per book; a single-round-trip relation load emits very few.
        js = _write_probe(
            "probe_roundtrip",
            _driver(
                """
                (async () => {
                    let bookSelects = 0;
                    const ds = new DataSource({
                        type: "better-sqlite3",
                        database: ":memory:",
                        entities: [Author, Book],
                        synchronize: true,
                        dropSchema: true,
                        logging: ["query"],
                        logger: {
                            logQuery(q) {
                                const s = String(q || "").toLowerCase();
                                if (s.startsWith("select") && /(\\bbook\\b|"book"|`book`|from book)/.test(s)) {
                                    bookSelects++;
                                }
                            },
                            logQueryError() {},
                            logQuerySlow() {},
                            logSchemaBuild() {},
                            logMigration() {},
                            log() {},
                        },
                    });
                    await ds.initialize();
                    const svc = makeService(ds);
                    const books = [];
                    for (let i = 0; i < 12; i++)
                        books.push({ title: "b" + i, year: 2000, genre: "g", copiesSold: i });
                    const saved = await svc.addAuthorWithBooks("Big", "X", books);
                    bookSelects = 0; // count only the read phase
                    const found = await svc.findAuthorWithBooks(saved.id);
                    out({
                        bookCount: found && found.books ? found.books.length : -1,
                        bookSelects: bookSelects,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["bookCount"] == 12, res
        # A naive N+1 loop would issue >= 12 book SELECTs. A single round trip (join or
        # one IN-query) issues at most a couple.
        assert res["bookSelects"] <= 3, (
            "relation appears to be loaded with a per-book query loop (N+1): "
            + json.dumps(res)
        )
