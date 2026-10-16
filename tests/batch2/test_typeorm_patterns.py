"""
Tests for the `typeorm-patterns` skill task (variant ext2):
"Build a Blog Tagging Persistence Layer".

The agent must add, under `test/functional/blog-tagging/`, a self-contained
TypeORM many-to-many feature exercised through the repo's own public API:
  - entity/Article.ts   (id auto-generated, title; owns many Tags via a junction table)
  - entity/Tag.ts       (id auto-generated, name UNIQUE; shared across many Articles)
  - tag-service.ts      (createArticleWithTags / getArticleTags / articlesForTag /
                         mostUsedTags) built from a DataSource
  - blog-tagging.test.ts(functional test wiring the above via createTestingConnections)

This pytest verifies the deliverables two ways:
  1. L1 — the four files exist and are minimally well-formed (decorated entities with
     generated PKs, a UNIQUE tag name, a ManyToMany/JoinTable association, the four
     service operations, and a SQLite-only testing connection).
  2. L2 — DYNAMIC EXECUTION against the real TypeORM toolchain: it writes an
     ormconfig.json restricted to the better-sqlite3 driver, compiles the repo
     (`pnpm run compile`), runs the agent's own compiled functional test under mocha,
     and then runs INDEPENDENT node driver scripts (written by THIS test, compiled in
     place next to the agent's emitted modules) to deep-validate real behavior:
        * a tag name shared by two articles yields exactly ONE Tag row, referenced by both
        * the junction table stores each (article, tag) pair exactly once (no duplicates)
        * getArticleTags(id) returns exactly the article's tags in a single round trip
        * getArticleTags(<missing id>) returns null (not [] and not a throw)
        * articlesForTag(name) returns matching articles ordered by id asc; [] when unknown
        * mostUsedTags(limit) is a real DB COUNT aggregate, bounded by limit, desc order
        * Tag.name UNIQUE is enforced at the DATABASE level

A naive solution (duplicating tags by name, an N+1 per-tag query loop, or counting tag
usage in JavaScript instead of via a database aggregate) must fail at least one assertion.
"""

import json
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/typeorm"
FEATURE_DIR = os.path.join(REPO_DIR, "test/functional/blog-tagging")
ENTITY_DIR = os.path.join(FEATURE_DIR, "entity")
ARTICLE_TS = os.path.join(ENTITY_DIR, "Article.ts")
TAG_TS = os.path.join(ENTITY_DIR, "Tag.ts")
SERVICE_TS = os.path.join(FEATURE_DIR, "tag-service.ts")
TEST_TS = os.path.join(FEATURE_DIR, "blog-tagging.test.ts")

COMPILED_TEST_JS = os.path.join(
    REPO_DIR, "build/compiled/test/functional/blog-tagging/blog-tagging.test.js"
)
COMPILED_FEATURE_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/blog-tagging"
)

# Build/compile is heavy in this repo.
COMPILE_TIMEOUT = 1200
RUN_TIMEOUT = 600

# Directory (under build/compiled, next to the agent's emitted modules) where this
# pytest drops its own independent driver scripts so their `./` imports resolve to the
# real compiled Article/Tag/TagService.
PROBE_OUT_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/blog-tagging/__probe__"
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

        ensure_npm_dependencies(REPO_DIR)
    except Exception:
        pass
    if os.path.isdir(os.path.join(REPO_DIR, "node_modules", "better-sqlite3")):
        return
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
    """Write a TS probe next to the agent's compiled modules and return its .js path.

    The probe is compiled with a standalone tsc invocation (decorators enabled) that
    emits into build/compiled/.../blog-tagging/__probe__ so the relative `../` imports
    resolve to the real compiled Article/Tag/TagService modules.
    """
    os.makedirs(PROBE_OUT_DIR, exist_ok=True)
    ts_path = os.path.join(PROBE_OUT_DIR, rel_name + ".ts")
    with open(ts_path, "w", encoding="utf-8") as f:
        f.write(ts_source)
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
    """Relative imports (from the probe's compiled __probe__ dir) to agent modules."""
    # Probe sits at build/compiled/test/functional/blog-tagging/__probe__/X.js
    # Agent compiled modules sit one dir up; src is at build/compiled/src.
    return {
        "article": "../entity/Article",
        "tag": "../entity/Tag",
        "service": "../tag-service",
        "datasource": "../../../../../src",  # build/compiled/src
    }


_DRIVER_PREAMBLE = """
"use strict";
const {{ DataSource }} = require("{datasource}");
const ArticleMod = require("{article}");
const TagMod = require("{tag}");
const ServiceMod = require("{service}");

function pickClass(mod, names) {{
    for (const n of names) if (mod[n]) return mod[n];
    for (const k of Object.keys(mod)) {{
        if (typeof mod[k] === "function") return mod[k];
    }}
    if (mod.default) return mod.default;
    throw new Error("could not locate export in module");
}}

const Article = pickClass(ArticleMod, ["Article", "default"]);
const Tag = pickClass(TagMod, ["Tag", "default"]);
const ServiceExport = pickClass(ServiceMod, ["TagService", "BlogTaggingService", "default"]);

function makeService(ds) {{
    // Support both `new Class(ds)` and a factory `fn(ds)`.
    try {{
        return new ServiceExport(ds);
    }} catch (e) {{
        return ServiceExport(ds);
    }}
}}

async function newDataSource(extra) {{
    const ds = new DataSource(Object.assign({{
        type: "better-sqlite3",
        database: ":memory:",
        entities: [Article, Tag],
        synchronize: true,
        dropSchema: true,
    }}, extra || {{}}));
    await ds.initialize();
    return ds;
}}

// Discover the name of the article<->tag junction table at runtime so probes do not
// have to guess the agent's @JoinTable naming.
async function junctionTable(ds) {{
    const rows = await ds.query(
        "SELECT name FROM sqlite_master WHERE type='table'");
    const names = rows.map((r) => r.name);
    // entity tables are 'article' and 'tag'; the join table references both.
    const cand = names.filter((n) =>
        n !== "article" && n !== "tag" &&
        /article/i.test(n) && /tag/i.test(n));
    if (cand.length) return cand[0];
    // fall back: any extra table that is neither entity table nor sqlite internal
    const extra = names.filter((n) =>
        n !== "article" && n !== "tag" && !/^sqlite_/i.test(n) &&
        !/migrations/i.test(n) && !/typeorm_metadata/i.test(n));
    return extra.length ? extra[0] : null;
}}

function out(obj) {{ process.stdout.write("RESULT_JSON:" + JSON.stringify(obj) + "\\n"); }}
"""


def _driver(body):
    paths = _import_paths()
    preamble = _DRIVER_PREAMBLE.format(
        datasource=paths["datasource"],
        article=paths["article"],
        tag=paths["tag"],
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


class TestTypeormPatterns:
    REPO_DIR = "/workspace/typeorm"

    # ---- L1: deliverable files exist and are minimally well-formed -------

    def test_l1_feature_files_exist(self):
        """All four required deliverable files exist under blog-tagging/."""
        for p in (ARTICLE_TS, TAG_TS, SERVICE_TS, TEST_TS):
            assert os.path.isfile(p), f"missing required deliverable file: {p}"

    def test_l1_entities_are_typeorm_entities_with_generated_pks(self):
        """Article and Tag are decorated TypeORM entities with generated primary keys."""
        article = _read(ARTICLE_TS)
        tag = _read(TAG_TS)
        for name, src in (("Article", article), ("Tag", tag)):
            assert "@Entity" in src, f"{name} is not annotated with @Entity"
            assert (
                "@PrimaryGeneratedColumn" in src
            ), f"{name} lacks a database-generated primary key"
        assert "title" in article, "Article entity does not declare a `title` field"
        assert "name" in tag, "Tag entity does not declare a `name` field"

    def test_l1_tag_name_is_unique(self):
        """Tag.name is declared UNIQUE (at the schema/decorator level, not app-only)."""
        tag = _read(TAG_TS)
        # Accept @Column({ unique: true }) or a @Unique/@Index({ unique: true }) form.
        assert "unique" in tag.lower(), (
            "Tag.name must be declared UNIQUE (e.g. @Column({ unique: true }) or "
            "@Unique([...])); application-only de-duplication is insufficient"
        )

    def test_l1_article_tags_many_to_many_with_join_table(self):
        """Article<->Tag is modeled as a many-to-many with a dedicated junction table."""
        article = _read(ARTICLE_TS)
        tag = _read(TAG_TS)
        both = article + "\n" + tag
        assert "ManyToMany" in both, (
            "the Article/Tag association must be declared @ManyToMany so a tag "
            "instance can be shared by many articles"
        )
        assert "JoinTable" in both, (
            "a dedicated junction table is required: exactly one side must declare "
            "@JoinTable()"
        )

    def test_l1_service_exports_required_operations(self):
        """tag-service.ts defines the four named tagging operations."""
        src = _read(SERVICE_TS)
        for op in (
            "createArticleWithTags",
            "getArticleTags",
            "articlesForTag",
            "mostUsedTags",
        ):
            assert op in src, f"tag-service.ts does not define `{op}`"

    def test_l1_test_uses_sqlite_only_testing_connections(self):
        """The functional test restricts testing connections to the SQLite driver family."""
        src = _read(TEST_TS)
        assert "createTestingConnections" in src, (
            "blog-tagging.test.ts must use createTestingConnections from "
            "../../utils/test-utils"
        )
        assert "enabledDrivers" in src, (
            "blog-tagging.test.ts must restrict to SQLite-based driver(s) via "
            "enabledDrivers (no external DB server)"
        )
        assert (
            "sqlite" in src or "sqljs" in src
        ), "enabledDrivers must name a sqlite-family driver (better-sqlite3/sqlite/sqljs)"

    # ---- L2: build & the agent's own functional test --------------------

    def test_l2_repo_compiles(self):
        """`pnpm run compile` succeeds with the deliverables in place (tsc, strict)."""
        _require_compiled()
        assert os.path.isfile(COMPILED_TEST_JS), (
            "expected compiled functional test at "
            + COMPILED_TEST_JS
            + " (compile succeeded but the test file was not emitted)"
        )
        for fname in ("entity/Article.js", "entity/Tag.js", "tag-service.js"):
            p = os.path.join(COMPILED_FEATURE_DIR, fname)
            assert os.path.isfile(p), f"expected compiled deliverable {p}"

    def test_l2_agent_functional_test_passes(self):
        """The agent's own blog-tagging.test.ts passes under mocha (no failures/leaks)."""
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

    def test_l2_create_article_with_tags_persists_and_links(self):
        """createArticleWithTags persists the article with a generated id and links its tags."""
        _require_compiled()
        js = _write_probe(
            "probe_create",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const saved = await svc.createArticleWithTags("Hello", ["a", "b", "c"]);
                    const articleRepo = ds.getRepository(Article);
                    const tagRepo = ds.getRepository(Tag);
                    // Re-read independently of the service via the relation.
                    const reread = await articleRepo.findOne({
                        where: { id: saved.id },
                        relations: { tags: true },
                    });
                    const tagCount = await tagRepo.count();
                    out({
                        savedId: saved.id,
                        rereadTagCount: reread && reread.tags ? reread.tags.length : -1,
                        rereadTagNames: reread && reread.tags
                            ? reread.tags.map((t) => t.name).sort() : [],
                        tagRowCount: tagCount,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert isinstance(res["savedId"], int) and res["savedId"] > 0, res
        assert res["rereadTagCount"] == 3, res
        assert res["rereadTagNames"] == ["a", "b", "c"], res
        assert res["tagRowCount"] == 3, res

    def test_l2_shared_tag_name_is_deduplicated_and_shared(self):
        """Two articles using the same tag name share ONE Tag row (no per-article dup)."""
        _require_compiled()
        js = _write_probe(
            "probe_dedup",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const a1 = await svc.createArticleWithTags("First", ["news", "tech"]);
                    const a2 = await svc.createArticleWithTags("Second", ["tech", "life"]);
                    const tagRepo = ds.getRepository(Tag);
                    const allTags = await tagRepo.find();
                    const techRows = allTags.filter((t) => t.name === "tech");
                    // The same Tag instance (same id) must back both articles.
                    const articleRepo = ds.getRepository(Article);
                    const r1 = await articleRepo.findOne({ where: { id: a1.id }, relations: { tags: true } });
                    const r2 = await articleRepo.findOne({ where: { id: a2.id }, relations: { tags: true } });
                    const techIn1 = (r1.tags || []).filter((t) => t.name === "tech").map((t) => t.id);
                    const techIn2 = (r2.tags || []).filter((t) => t.name === "tech").map((t) => t.id);
                    out({
                        distinctTagCount: allTags.length,
                        techRowCount: techRows.length,
                        techId1: techIn1[0] !== undefined ? techIn1[0] : -1,
                        techId2: techIn2[0] !== undefined ? techIn2[0] : -2,
                        names: allTags.map((t) => t.name).sort(),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        # 3 distinct tag names total: news, tech, life. A naive dup-per-article impl
        # would create 4 (tech twice).
        assert res["distinctTagCount"] == 3, (
            "tag rows were duplicated by name instead of reused: " + json.dumps(res)
        )
        assert res["techRowCount"] == 1, (
            "expected exactly one 'tech' Tag row shared across articles: "
            + json.dumps(res)
        )
        assert res["techId1"] == res["techId2"] and res["techId1"] > 0, (
            "the two articles do not reference the SAME shared Tag instance: "
            + json.dumps(res)
        )
        assert res["names"] == ["life", "news", "tech"], res

    def test_l2_junction_stores_each_pair_once(self):
        """The junction table stores each (article, tag) pair exactly once, no duplicates."""
        _require_compiled()
        js = _write_probe(
            "probe_junction",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    // Same tag name passed twice for one article must not double-link it.
                    await svc.createArticleWithTags("Dup", ["x", "x", "y"]);
                    const jt = await junctionTable(ds);
                    if (!jt) { out({ jt: null }); await ds.destroy(); return; }
                    const total = await ds.query("SELECT COUNT(*) AS c FROM " + jt);
                    const distinct = await ds.query(
                        "SELECT COUNT(*) AS c FROM (SELECT DISTINCT * FROM " + jt + ")");
                    const tagCount = await ds.getRepository(Tag).count();
                    out({
                        jt: jt,
                        totalLinks: Number(total[0].c),
                        distinctLinks: Number(distinct[0].c),
                        tagRows: tagCount,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res.get("jt"), "could not locate the article<->tag junction table: " + json.dumps(res)
        # x + y => 2 distinct tags, 2 distinct (article,tag) links.
        assert res["tagRows"] == 2, (
            "passing 'x' twice created duplicate Tag rows: " + json.dumps(res)
        )
        assert res["distinctLinks"] == 2, res
        assert res["totalLinks"] == res["distinctLinks"], (
            "the (article, tag) pair was stored more than once in the junction table: "
            + json.dumps(res)
        )

    def test_l2_get_article_tags_returns_exact_set(self):
        """getArticleTags(id) returns exactly the article's tags."""
        _require_compiled()
        js = _write_probe(
            "probe_get_tags",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const saved = await svc.createArticleWithTags("Trip", ["red", "green", "blue"]);
                    // Create a second article with unrelated tags to ensure scoping.
                    await svc.createArticleWithTags("Other", ["yellow"]);
                    const tags = await svc.getArticleTags(saved.id);
                    out({
                        count: tags ? tags.length : -1,
                        names: tags ? tags.map((t) => t.name).sort() : [],
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["count"] == 3, res
        assert res["names"] == ["blue", "green", "red"], res

    def test_l2_get_article_tags_missing_returns_null(self):
        """getArticleTags(<missing id>) returns null (not [] and not a throw)."""
        _require_compiled()
        js = _write_probe(
            "probe_missing",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    await svc.createArticleWithTags("Real", ["t"]);
                    const res = await svc.getArticleTags(987654);
                    out({
                        isNull: res === null,
                        isUndefined: res === undefined,
                        isEmptyArray: Array.isArray(res) && res.length === 0,
                        kind: res === null ? "null" : (Array.isArray(res) ? "array" : typeof res),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error("THREW", e); process.exit(2); });
                """
            ),
        )
        proc = _run_node(js)
        assert proc.returncode == 0, (
            "getArticleTags(missing) threw instead of returning null:\n"
            + proc.stdout
            + "\n"
            + proc.stderr
        )
        res = _parse_result(proc)
        # The doc requires null specifically for a missing article (distinct from the
        # empty-list result of a real article with no tags).
        assert res["isNull"] is True, (
            "getArticleTags(missing) must return null, got: " + json.dumps(res)
        )
        assert res["isEmptyArray"] is False, (
            "getArticleTags(missing) returned [] instead of null: " + json.dumps(res)
        )

    def test_l2_articles_for_tag_ordered_by_id(self):
        """articlesForTag(name) returns the matching articles ordered by id ascending."""
        _require_compiled()
        js = _write_probe(
            "probe_articles_for_tag",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const a1 = await svc.createArticleWithTags("Alpha", ["share", "solo1"]);
                    const a2 = await svc.createArticleWithTags("Beta", ["solo2"]);
                    const a3 = await svc.createArticleWithTags("Gamma", ["share"]);
                    const list = await svc.articlesForTag("share");
                    out({
                        ids: list.map((a) => a.id),
                        titles: list.map((a) => a.title),
                        expectAscending: [a1.id, a3.id],
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        # Only Alpha (a1) and Gamma (a3) carry "share"; must be ordered by id asc.
        assert res["ids"] == res["expectAscending"], (
            "articlesForTag must return only matching articles ordered by id asc: "
            + json.dumps(res)
        )
        assert res["titles"] == ["Alpha", "Gamma"], res

    def test_l2_articles_for_unknown_tag_is_empty(self):
        """articlesForTag(<unknown name>) returns an empty list, not null/throw."""
        _require_compiled()
        js = _write_probe(
            "probe_unknown_tag",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    await svc.createArticleWithTags("Only", ["present"]);
                    const list = await svc.articlesForTag("does-not-exist");
                    out({
                        isArray: Array.isArray(list),
                        len: Array.isArray(list) ? list.length : -1,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["isArray"] is True, "articlesForTag(unknown) must return a list: " + json.dumps(res)
        assert res["len"] == 0, res

    def test_l2_most_used_tags_is_db_aggregate_ordered_and_bounded(self):
        """mostUsedTags(limit) returns up to `limit` tags ordered by DB-counted usage desc."""
        _require_compiled()
        js = _write_probe(
            "probe_most_used",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    // Usage counts: 'pop' -> 3, 'mid' -> 2, 'rare' -> 1.
                    await svc.createArticleWithTags("a1", ["pop", "mid", "rare"]);
                    await svc.createArticleWithTags("a2", ["pop", "mid"]);
                    await svc.createArticleWithTags("a3", ["pop"]);
                    const top2 = await svc.mostUsedTags(2);
                    out({
                        len: top2.length,
                        names: top2.map((t) => t.name),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["len"] == 2, (
            "mostUsedTags(2) must be bounded by the limit: " + json.dumps(res)
        )
        # Most-used desc: pop(3) then mid(2). 'rare' must be excluded.
        assert res["names"] == ["pop", "mid"], (
            "mostUsedTags must order by DB-computed usage count desc: "
            + json.dumps(res)
        )

    def test_l2_most_used_tags_counts_match_db_truth(self):
        """mostUsedTags ranking equals the ranking from an independent SQL COUNT aggregate."""
        _require_compiled()
        js = _write_probe(
            "probe_most_used_truth",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    await svc.createArticleWithTags("a1", ["x", "y", "z"]);
                    await svc.createArticleWithTags("a2", ["x", "y"]);
                    await svc.createArticleWithTags("a3", ["x"]);
                    await svc.createArticleWithTags("a4", ["y"]);
                    // Independent ground truth straight from the junction table.
                    const jt = await junctionTable(ds);
                    const cols = await ds.query("PRAGMA table_info(" + jt + ")");
                    const colNames = cols.map((r) => r.name);
                    const tagFk = colNames.find((n) => /tag/i.test(n));
                    const tagPk = (await ds.query("PRAGMA table_info(tag)"))
                        .map((r) => r.name).find((n) => /^id$/i.test(n)) || "id";
                    const truth = await ds.query(
                        "SELECT t.name AS name, COUNT(*) AS c FROM " + jt + " j " +
                        "JOIN tag t ON t." + tagPk + " = j." + tagFk + " " +
                        "GROUP BY t.name ORDER BY c DESC, t.name ASC");
                    const svcTop = await svc.mostUsedTags(10);
                    out({
                        truthOrder: truth.map((r) => r.name),
                        truthCounts: truth.map((r) => Number(r.c)),
                        svcOrder: svcTop.map((t) => t.name),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        # x->3, y->3, z->1 by junction-table truth.
        assert res["truthCounts"][:2] == [3, 3], res
        # The service's descending ranking must agree with the DB aggregate ranking
        # on the top spots (x and y outrank z).
        assert set(res["svcOrder"][:2]) == {"x", "y"}, (
            "mostUsedTags ranking disagrees with the DB COUNT aggregate (likely "
            "counted in JavaScript or wrong order): " + json.dumps(res)
        )
        assert res["svcOrder"][-1] == "z", (
            "least-used tag 'z' should rank last: " + json.dumps(res)
        )

    def test_l2_get_article_tags_single_round_trip(self):
        """getArticleTags loads tags in a single query round trip (no per-tag N+1 loop)."""
        _require_compiled()
        js = _write_probe(
            "probe_roundtrip",
            _driver(
                """
                (async () => {
                    let tagSelects = 0;
                    const ds = new DataSource({
                        type: "better-sqlite3",
                        database: ":memory:",
                        entities: [Article, Tag],
                        synchronize: true,
                        dropSchema: true,
                        logging: ["query"],
                        logger: {
                            logQuery(q) {
                                const s = String(q || "").toLowerCase();
                                if (s.startsWith("select") && /(\\btag\\b|"tag"|`tag`|from tag)/.test(s)) {
                                    tagSelects++;
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
                    const names = [];
                    for (let i = 0; i < 12; i++) names.push("t" + i);
                    const saved = await svc.createArticleWithTags("Big", names);
                    tagSelects = 0; // count only the read phase
                    const tags = await svc.getArticleTags(saved.id);
                    out({
                        tagCount: tags ? tags.length : -1,
                        tagSelects: tagSelects,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["tagCount"] == 12, res
        # A naive N+1 loop would issue >= 12 tag SELECTs; a single round trip (join or
        # one IN-query) issues only a couple.
        assert res["tagSelects"] <= 3, (
            "tags appear to be loaded with a per-tag query loop (N+1) instead of a "
            "single round trip: " + json.dumps(res)
        )

    def test_l2_tag_name_unique_enforced_at_db_level(self):
        """Tag.name UNIQUE is enforced by the DATABASE (direct insert of a dup must fail)."""
        _require_compiled()
        js = _write_probe(
            "probe_unique",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const tagRepo = ds.getRepository(Tag);
                    await tagRepo.save({ name: "uniqueone" });
                    let threw = false;
                    try {
                        // Bypass the service: insert a second row with the same name
                        // straight through the DB to prove the UNIQUE constraint exists.
                        await ds.query("INSERT INTO tag (name) VALUES ('uniqueone')");
                    } catch (e) {
                        threw = true;
                    }
                    const count = await tagRepo.count();
                    out({ threw: threw, tagRows: count });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["threw"] is True, (
            "a duplicate tag name was accepted by the database; Tag.name is not "
            "UNIQUE at the schema level: " + json.dumps(res)
        )
        assert res["tagRows"] == 1, (
            "duplicate tag row persisted despite the expected UNIQUE constraint: "
            + json.dumps(res)
        )
