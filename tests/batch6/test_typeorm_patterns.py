"""
Tests for the `typeorm-patterns` skill task (variant ext6):
"Build a Hierarchical Category Tree Layer".

The agent must add, under `test/functional/category-tree/`, a self-contained TypeORM
functional feature backed by the repo's own `src/`:
  - entity/Category.ts       (id auto-generated, name:string; self-referential
                              parent/children forming a tree of arbitrary depth)
  - tree-service.ts          (a class/factory built from a DataSource exposing
                              addRoot / addChild / getSubtree / getAncestors / getRoots)
  - category-tree.test.ts    (functional test wiring the entity through
                              createTestingConnections, restricted to SQLite)

Verification strategy (mirrors the ext1 harness style, retargeted to THIS task):
  1. L1 -- the three deliverable files exist and are minimally well-formed:
       Category is a decorated TypeORM entity with a generated PK and a
       self-referential tree relation (NOT a flattened denormalized path column),
       tree-service.ts exports the five operations, and the functional test uses
       createTestingConnections restricted to a sqlite-family driver.
  2. L2 -- DYNAMIC EXECUTION against the real TypeORM toolchain. We write an
       ormconfig.json restricted to better-sqlite3, compile the repo
       (`pnpm run compile`), run the agent's own compiled mocha functional test,
       and then run INDEPENDENT node driver scripts (written by THIS test) against
       the agent's compiled Category/TreeService to deep-validate real behavior:
         * addRoot returns a generated id; getRoots returns only roots
         * a 3-level tree round-trips: getSubtree(root) nests child under root and
           grandchild under child (reconstructed by the ORM, exact nested shape)
         * getAncestors(grandchild) returns the parent->root ancestor chain
         * getRoots over a 2-root forest returns exactly the two roots, no descendants
         * addChild attaches a child that appears in the parent's subtree and reports
           the parent as an ancestor
         * getSubtree is loaded by the ORM's tree-aware loading, NOT a per-node
           query loop (N+1): we instrument the query logger and bound the SELECT
           count well below the node count

A naive solution -- one that flattens the hierarchy into a denormalized path string
(losing the ability to reconstruct nested parent/child objects), or that rebuilds the
tree by issuing one query per node -- must fail at least one assertion.

Native acceptance command this L2 drives (from the repo root):

    pnpm run compile && npx mocha ./build/compiled/test/functional/category-tree/category-tree.test.js
"""

import json
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/typeorm"
FEATURE_DIR = os.path.join(REPO_DIR, "test/functional/category-tree")
ENTITY_DIR = os.path.join(FEATURE_DIR, "entity")
CATEGORY_TS = os.path.join(ENTITY_DIR, "Category.ts")
SERVICE_TS = os.path.join(FEATURE_DIR, "tree-service.ts")
TEST_TS = os.path.join(FEATURE_DIR, "category-tree.test.ts")

COMPILED_TEST_JS = os.path.join(
    REPO_DIR, "build/compiled/test/functional/category-tree/category-tree.test.js"
)
COMPILED_FEATURE_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/category-tree"
)

# Build/compile is heavy in this repo.
COMPILE_TIMEOUT = 1200
RUN_TIMEOUT = 600

# Directory (under the compiled feature dir) where this pytest drops its own
# independent driver scripts so their relative `./` imports resolve to the
# agent's already-compiled Category/TreeService modules.
PROBE_OUT_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/category-tree/__probe__"
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
    """Write a TS probe under the compiled feature dir and return its .js path.

    The probe is compiled in place (CommonJS, decorators enabled) so its relative
    `./` / `../` imports resolve to the agent's already-compiled Category /
    TreeService / src modules.
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
    return subprocess.run(
        ["bash", "-lc", "node " + js_path],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
    )


def _import_paths():
    """Relative imports (from the probe's compiled location) to the agent modules.

    Probe sits at build/compiled/test/functional/category-tree/__probe__/X.js
    Agent compiled modules sit one dir up; compiled src is five dirs up.
    """
    return {
        "category": "../entity/Category",
        "service": "../tree-service",
        "datasource": "../../../../../src",  # build/compiled/src
    }


_DRIVER_PREAMBLE = """
"use strict";
const {{ DataSource }} = require("{datasource}");
const CategoryMod = require("{category}");
const ServiceMod = require("{service}");

function pickClass(mod, names) {{
    for (const n of names) if (mod[n]) return mod[n];
    for (const k of Object.keys(mod)) {{
        if (typeof mod[k] === "function") return mod[k];
    }}
    if (mod.default) return mod.default;
    throw new Error("could not locate export in module");
}}

const Category = pickClass(CategoryMod, ["Category", "default"]);
const ServiceExport = pickClass(
    ServiceMod,
    ["TreeService", "CategoryTreeService", "CategoryService", "default"],
);

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
        entities: [Category],
        synchronize: true,
        dropSchema: true,
    }}, extra || {{}}));
    await ds.initialize();
    return ds;
}}

function out(obj) {{ process.stdout.write("RESULT_JSON:" + JSON.stringify(obj) + "\\n"); }}
"""


def _driver(body):
    paths = _import_paths()
    preamble = _DRIVER_PREAMBLE.format(
        datasource=paths["datasource"],
        category=paths["category"],
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
# Tests
# ===========================================================================


class TestTypeormPatterns:
    REPO_DIR = "/workspace/typeorm"

    # ---- L1: deliverables exist and are minimally well-formed -----------

    def test_l1_feature_files_exist(self):
        """All three required deliverable files exist under category-tree/."""
        for p in (CATEGORY_TS, SERVICE_TS, TEST_TS):
            assert os.path.isfile(p), f"missing required deliverable file: {p}"

    def test_l1_category_is_tree_entity_with_generated_pk(self):
        """Category is a decorated TypeORM entity with a database-generated primary key and a name."""
        src = _read(CATEGORY_TS)
        assert "@Entity" in src, "Category is not annotated with @Entity"
        assert (
            "@PrimaryGeneratedColumn" in src
        ), "Category lacks a database-generated primary key"
        assert "name" in src, "Category entity does not declare a `name` field"

    def test_l1_category_is_self_referential_tree_not_flattened_path(self):
        """Category models the hierarchy as a self-referential tree, not a denormalized path string.

        The doc forbids flattening into a single denormalized path column. A genuine
        self-referential tree uses TypeORM's tree decorators (@Tree + @TreeParent/
        @TreeChildren) or an explicit self-referential ManyToOne/OneToMany on Category.
        """
        src = _read(CATEGORY_TS)
        uses_tree_decorators = (
            "@Tree" in src and "@TreeParent" in src and "@TreeChildren" in src
        )
        uses_self_relation = (
            ("@ManyToOne" in src or "@OneToMany" in src) and "Category" in src
        )
        assert uses_tree_decorators or uses_self_relation, (
            "Category must model a self-referential tree (TypeORM @Tree/@TreeParent/"
            "@TreeChildren, or a self-referential ManyToOne/OneToMany to Category); "
            "a flattened denormalized path column is not acceptable"
        )

    def test_l1_service_exports_required_operations(self):
        """tree-service.ts references the five named tree operations."""
        src = _read(SERVICE_TS)
        for op in ("addRoot", "addChild", "getSubtree", "getAncestors", "getRoots"):
            assert op in src, f"tree-service.ts does not define `{op}`"

    def test_l1_test_uses_sqlite_only_testing_connections(self):
        """The functional test wires the entity via createTestingConnections, restricted to SQLite."""
        src = _read(TEST_TS)
        assert "createTestingConnections" in src, (
            "category-tree.test.ts must use createTestingConnections from "
            "../../utils/test-utils"
        )
        assert "enabledDrivers" in src, (
            "category-tree.test.ts must restrict to SQLite-based driver(s) via "
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
        for fname in ("entity/Category.js", "tree-service.js"):
            p = os.path.join(COMPILED_FEATURE_DIR, fname)
            assert os.path.isfile(p), f"expected compiled deliverable {p}"

    def test_l2_agent_functional_test_passes(self):
        """The agent's own category-tree.test.ts passes under mocha (no failures/leaks)."""
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

    def test_l2_add_root_returns_generated_id_and_is_a_root(self):
        """addRoot persists a top-level category with a generated id; getRoots lists it."""
        _require_compiled()
        js = _write_probe(
            "probe_add_root",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const root = await svc.addRoot("electronics");
                    const roots = await svc.getRoots();
                    out({
                        rootId: root && root.id,
                        rootName: root && root.name,
                        rootCount: roots.length,
                        rootNames: roots.map((r) => r.name),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert isinstance(res["rootId"], int) and res["rootId"] > 0, res
        assert res["rootName"] == "electronics", res
        assert res["rootCount"] == 1, res
        assert res["rootNames"] == ["electronics"], res

    def test_l2_three_level_subtree_is_nested_by_orm(self):
        """getSubtree(root) of a root->child->grandchild tree returns the exact nested shape."""
        _require_compiled()
        js = _write_probe(
            "probe_subtree",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const root = await svc.addRoot("root");
                    const child = await svc.addChild(root.id, "child");
                    const grand = await svc.addChild(child.id, "grand");
                    const tree = await svc.getSubtree(root.id);

                    // Locate the child-collection key (TypeORM tree entities expose a
                    // children array; we accept whatever array-of-nodes property holds it).
                    function childrenOf(node) {
                        if (!node) return null;
                        for (const k of Object.keys(node)) {
                            const v = node[k];
                            if (Array.isArray(v)) return v;
                        }
                        return null;
                    }

                    const rootChildren = childrenOf(tree) || [];
                    const childNode = rootChildren[0];
                    const grandChildren = childrenOf(childNode) || [];
                    const grandNode = grandChildren[0];

                    out({
                        rootName: tree && tree.name,
                        rootChildCount: rootChildren.length,
                        childName: childNode && childNode.name,
                        childGrandCount: grandChildren.length,
                        grandName: grandNode && grandNode.name,
                        rootId: tree && tree.id,
                        ids: { root: root.id, child: child.id, grand: grand.id },
                        childNodeId: childNode && childNode.id,
                        grandNodeId: grandNode && grandNode.id,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["rootName"] == "root" and res["rootId"] == res["ids"]["root"], res
        # root has exactly the one child nested beneath it
        assert res["rootChildCount"] == 1, (
            "getSubtree did not nest the direct child under the root: " + json.dumps(res)
        )
        assert res["childName"] == "child", res
        assert res["childNodeId"] == res["ids"]["child"], res
        # the child has exactly the grandchild nested beneath it (depth >= 3)
        assert res["childGrandCount"] == 1, (
            "getSubtree did not nest the grandchild under the child (tree not "
            "reconstructed to full depth): " + json.dumps(res)
        )
        assert res["grandName"] == "grand", res
        assert res["grandNodeId"] == res["ids"]["grand"], res

    def test_l2_get_ancestors_returns_full_chain(self):
        """getAncestors(grandchild) returns the grandchild plus its parent and the root."""
        _require_compiled()
        js = _write_probe(
            "probe_ancestors",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const root = await svc.addRoot("r");
                    const child = await svc.addChild(root.id, "c");
                    const grand = await svc.addChild(child.id, "g");
                    const ancestors = await svc.getAncestors(grand.id);
                    out({
                        names: ancestors.map((a) => a.name).sort(),
                        ids: ancestors.map((a) => a.id).sort((x, y) => x - y),
                        rootId: root.id, childId: child.id, grandId: grand.id,
                        count: ancestors.length,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        # ancestor chain of the grandchild includes its parent and the root.
        assert "r" in res["names"], "ancestor chain missing the root: " + json.dumps(res)
        assert "c" in res["names"], "ancestor chain missing the parent: " + json.dumps(res)
        expected_ids = sorted([res["rootId"], res["childId"], res["grandId"]])
        # TypeORM findAncestors includes the node itself; require at least parent+root.
        assert res["rootId"] in res["ids"] and res["childId"] in res["ids"], res
        assert res["count"] >= 2, res
        # If the node itself is included it must be the full chain of 3 distinct ids.
        if res["count"] == 3:
            assert res["ids"] == expected_ids, res

    def test_l2_get_roots_over_forest_excludes_descendants(self):
        """getRoots over a 2-root forest returns exactly the two roots and none of their descendants."""
        _require_compiled()
        js = _write_probe(
            "probe_forest_roots",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const r1 = await svc.addRoot("alpha");
                    const r2 = await svc.addRoot("beta");
                    // Give each root descendants that must NOT appear in getRoots().
                    const a1 = await svc.addChild(r1.id, "alpha-1");
                    await svc.addChild(a1.id, "alpha-1-1");
                    await svc.addChild(r2.id, "beta-1");
                    const roots = await svc.getRoots();
                    out({
                        names: roots.map((r) => r.name).sort(),
                        count: roots.length,
                        ids: roots.map((r) => r.id).sort((x, y) => x - y),
                        rootIds: [r1.id, r2.id].sort((x, y) => x - y),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["count"] == 2, (
            "getRoots must return exactly the two roots, not descendants: "
            + json.dumps(res)
        )
        assert res["names"] == ["alpha", "beta"], res
        assert res["ids"] == res["rootIds"], res

    def test_l2_add_child_appears_in_parent_subtree_and_ancestors(self):
        """A child added under a parent appears in the parent's subtree and reports that parent as an ancestor."""
        _require_compiled()
        js = _write_probe(
            "probe_add_child",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const parent = await svc.addRoot("parent");
                    const child = await svc.addChild(parent.id, "kid");

                    function childrenOf(node) {
                        if (!node) return null;
                        for (const k of Object.keys(node)) {
                            const v = node[k];
                            if (Array.isArray(v)) return v;
                        }
                        return null;
                    }

                    const subtree = await svc.getSubtree(parent.id);
                    const kids = childrenOf(subtree) || [];
                    const ancestors = await svc.getAncestors(child.id);
                    out({
                        childId: child.id,
                        childName: child.name,
                        kidNames: kids.map((k) => k.name),
                        kidIds: kids.map((k) => k.id),
                        ancestorNames: ancestors.map((a) => a.name),
                        parentId: parent.id,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert isinstance(res["childId"], int) and res["childId"] > 0, res
        assert res["childName"] == "kid", res
        assert "kid" in res["kidNames"], (
            "added child does not appear in the parent's subtree: " + json.dumps(res)
        )
        assert res["childId"] in res["kidIds"], res
        assert "parent" in res["ancestorNames"], (
            "child does not report its parent as an ancestor: " + json.dumps(res)
        )

    def test_l2_subtree_loaded_without_per_node_query_loop(self):
        """getSubtree is reconstructed by tree-aware loading, not an N+1 per-node query loop.

        We instrument the DataSource query logger and count SELECTs issued while
        loading a 13-node subtree. An application-level recursion that issues one
        query per node would emit >= 13 SELECTs; the ORM's tree-aware loading
        issues a small constant number.
        """
        _require_compiled()
        js = _write_probe(
            "probe_no_n_plus_1",
            _driver(
                """
                (async () => {
                    let selects = 0;
                    const ds = await newDataSource({
                        logging: ["query"],
                        logger: {
                            logQuery(q) {
                                const s = String(q || "").toLowerCase();
                                if (s.indexOf("select") === 0) selects++;
                            },
                            logQueryError() {},
                            logQuerySlow() {},
                            logSchemaBuild() {},
                            logMigration() {},
                            log() {},
                        },
                    });
                    const svc = makeService(ds);
                    // Build a deep + wide tree: root with 3 children, each child with 3
                    // children -> 1 + 3 + 9 = 13 nodes.
                    const root = await svc.addRoot("root");
                    for (let i = 0; i < 3; i++) {
                        const c = await svc.addChild(root.id, "c" + i);
                        for (let j = 0; j < 3; j++) {
                            await svc.addChild(c.id, "c" + i + "_" + j);
                        }
                    }
                    selects = 0; // count only the read phase
                    const tree = await svc.getSubtree(root.id);

                    function countNodes(node) {
                        if (!node) return 0;
                        let n = 1;
                        for (const k of Object.keys(node)) {
                            const v = node[k];
                            if (Array.isArray(v)) {
                                for (const ch of v) n += countNodes(ch);
                            }
                        }
                        return n;
                    }

                    out({ nodes: countNodes(tree), selects: selects });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["nodes"] == 13, (
            "getSubtree did not reconstruct all 13 nodes of the tree: " + json.dumps(res)
        )
        # Tree-aware loading (closure-table / nested-set / materialized-path) issues a
        # small constant number of SELECTs. A per-node loop would issue >= 13.
        assert res["selects"] <= 6, (
            "getSubtree appears to load the tree with a per-node query loop (N+1); "
            "it must use the ORM's tree-aware loading: " + json.dumps(res)
        )

    def test_l2_subtree_excludes_unrelated_root(self):
        """getSubtree(rootA) returns only rootA's descendants, never an unrelated root's nodes."""
        _require_compiled()
        js = _write_probe(
            "probe_subtree_isolation",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const a = await svc.addRoot("A");
                    await svc.addChild(a.id, "A-1");
                    const b = await svc.addRoot("B");
                    await svc.addChild(b.id, "B-1");

                    function names(node, acc) {
                        if (!node) return acc;
                        acc.push(node.name);
                        for (const k of Object.keys(node)) {
                            const v = node[k];
                            if (Array.isArray(v)) for (const ch of v) names(ch, acc);
                        }
                        return acc;
                    }

                    const subA = await svc.getSubtree(a.id);
                    const all = names(subA, []).sort();
                    out({ names: all });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["names"] == ["A", "A-1"], (
            "getSubtree leaked nodes from an unrelated root (subtree not scoped): "
            + json.dumps(res)
        )
