"""Benchmark tests for the `graphql-schema-design` skill (variant ext5).

Skill task: "Evolve a Profile Schema Without Breaking Existing Clients".

The agent must build a self-contained user-profile module inside the
`@apollo/server` package:
  - `packages/server/src/examples/profileEvolution.ts` (new) -- exports
    `typeDefs` (a GraphQL SDL string), `resolvers`, and an in-memory data-store
    factory; importable on its own; must NOT import other example files.
  - `packages/server/src/__tests__/examples/profileEvolution.test.ts` (new) --
    a Jest suite that builds an `ApolloServer` and asserts via
    `executeOperation`.

Domain rules (the source of truth is tasks/ext5/graphql-schema-design.md):
  * Each profile has a stable id + a person's full name.
  * The OLD combined-name field (single string) must keep working AND be marked
    *superseded* in the schema with a machine-readable marker carrying a
    non-empty human-readable reason -- discoverable via GraphQL introspection
    (i.e. the standard `@deprecated` directive => `isDeprecated` /
    `deprecationReason`).  The NEW firstName / lastName fields must NOT be
    marked superseded, and together must be consistent with the combined name.
  * Email was historically directly on the profile; it now ALSO lives on a
    nested contact-info object.  The directly-attached email must remain
    queryable, be marked superseded the same way, and equal the nested value
    for EVERY profile.
  * Root query: fetch a single profile by id (null, no error, on unknown id)
    and list all profiles (never null, never containing null entries).
  * Determinism: a fixed, seeded set of profiles, no randomness / time / I/O.

Verification strategy
---------------------
L1 (existence / minimal well-formedness):
  - both deliverable files exist,
  - the module exports `typeDefs` / `resolvers` / a store factory,
  - the module does not import other example files,
  - the agent's own Jest suite declares >= 10 it/test cases,
  - the agent's own suite (the acceptance command) passes.

L2 (dynamic execution -- the discriminative core):
  Rather than trusting the agent's own test file, we synthesize an INDEPENDENT
  TypeScript Jest harness, drop it next to the module, and run it through the
  repo's native `jest` toolchain.  The harness builds an `ApolloServer`
  directly from the module's `typeDefs`/`resolvers`, then:
    * introspects the schema to discover the real field names without
      hard-coding the agent's naming choices,
    * asserts the OLD combined-name field and the directly-attached email field
      are reported deprecated (superseded) WITH a non-empty reason, while the
      replacement firstName/lastName/nested-email fields are NOT deprecated,
    * resolves the combined name and checks first+last are consistent with it
      for every seeded profile,
    * checks the directly-attached email equals the nested contact-info email
      for every profile,
    * checks list never null / never contains null entries,
    * checks an unknown id resolves to null with no execution error.

A stub that drops the old fields, forgets the deprecation marker, returns an
empty reason, marks the NEW fields deprecated, hardcodes a single profile, or
lets the old email diverge from the nested one will fail at least one case.

We run jest with `--json` and assert on individual named test outcomes.
"""

import json
import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _dependency_utils import ensure_npm_dependencies
except Exception:  # pragma: no cover - helper always present at runtime
    ensure_npm_dependencies = None


class TestGraphqlSchemaDesign:
    REPO_DIR = "/workspace/apollo-server"

    SERVER_DIR = os.path.join(REPO_DIR, "packages", "server")
    MODULE_REL = "src/examples/profileEvolution.ts"
    SUITE_REL = "src/__tests__/examples/profileEvolution.test.ts"
    MODULE_PATH = os.path.join(SERVER_DIR, "src", "examples", "profileEvolution.ts")
    SUITE_PATH = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "profileEvolution.test.ts"
    )

    # Directory where we drop our own independent harness suite.
    HARNESS_DIR = os.path.join(SERVER_DIR, "src", "__tests__", "examples", "__bench__")
    HARNESS_NAME = "benchProfileEvolution.test.ts"
    HARNESS_PATH = os.path.join(HARNESS_DIR, HARNESS_NAME)
    HARNESS_REL = "src/__tests__/examples/__bench__/" + HARNESS_NAME

    # ----------------------------------------------------------------- helpers
    @classmethod
    def _read(cls, path):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()

    @classmethod
    def _jest_bin(cls):
        """Locate the workspace-hoisted jest binary (walk up from packages/server)."""
        d = cls.SERVER_DIR
        seen = set()
        while d and d not in seen:
            seen.add(d)
            cand = os.path.join(d, "node_modules", ".bin", "jest")
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        return None

    @classmethod
    def _run_jest(cls, test_rel, timeout=600):
        """Run jest for a single test file from packages/server, return (proc, json)."""
        jest = cls._jest_bin()
        if jest is not None:
            cmd = [jest]
        else:
            cmd = ["npx", "--no-install", "jest"]
        cmd += [test_rel, "--json", "--runInBand", "--no-coverage"]
        proc = subprocess.run(
            cmd,
            cwd=cls.SERVER_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        report = cls._extract_json(proc.stdout) or cls._extract_json(proc.stderr)
        return proc, report

    @staticmethod
    def _extract_json(text):
        if not text:
            return None
        start = text.find("{")
        while start != -1:
            depth = 0
            for i in range(start, len(text)):
                c = text[i]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        chunk = text[start : i + 1]
                        try:
                            obj = json.loads(chunk)
                            if isinstance(obj, dict) and "testResults" in obj:
                                return obj
                        except Exception:
                            break
            start = text.find("{", start + 1)
        return None

    @classmethod
    def _assertions_by_title(cls, report):
        out = {}
        if not report:
            return out
        for suite in report.get("testResults", []):
            for a in suite.get("assertionResults", []):
                out[a.get("title", "")] = a.get("status", "")
        return out

    # ----------------------------------------------------------- harness source
    @classmethod
    def _harness_source(cls):
        # NB: imports are relative to src/__tests__/examples/__bench__/
        #   - ApolloServer       -> ../../../index.js
        #   - module under test  -> ../../../examples/profileEvolution.js
        return r"""// @ts-nocheck
import { describe, it, expect } from '@jest/globals';
import { ApolloServer } from '../../../index.js';
import * as mod from '../../../examples/profileEvolution.js';

const typeDefs: any = (mod as any).typeDefs;
const resolvers: any = (mod as any).resolvers;

async function mkServer() {
  const server = new ApolloServer({ typeDefs, resolvers });
  await server.start();
  return server;
}

async function run(server: any, query: string, variables?: any) {
  const res = await server.executeOperation({ query, variables });
  if (res.body.kind !== 'single') throw new Error('expected single result');
  return res.body.singleResult as { data?: any; errors?: any[] };
}

function unwrap(t: any): any {
  let nonNull = false, list = false, cur = t;
  while (cur) {
    if (cur.kind === 'NON_NULL') { nonNull = true; cur = cur.ofType; continue; }
    if (cur.kind === 'LIST') { list = true; cur = cur.ofType; continue; }
    break;
  }
  return { kind: cur ? cur.kind : '', name: cur ? cur.name : null, nonNull, list };
}

const TYPEREF = `kind name ofType { kind name ofType { kind name ofType { kind name } } }`;
// includeDeprecated: true so introspection surfaces deprecated fields & reasons.
const INTRO = `
{
  __schema {
    queryType { name }
    types {
      kind name
      fields(includeDeprecated: true) {
        name
        isDeprecated
        deprecationReason
        args { name type { ${TYPEREF} } }
        type { ${TYPEREF} }
      }
    }
  }
}`;

// ---- schema-shape discovery (no hard-coded agent naming) -------------------
async function discover(server: any) {
  const intro = await run(server, INTRO);
  expect(intro.errors).toBeFalsy();
  const sch = intro.data.__schema;
  const types: any[] = sch.types;
  const qType = types.find((t) => t.name === sch.queryType.name);

  // The Profile object: an OBJECT type carrying an email-ish field and at least
  // one name-ish field; it is reachable from the root query (single + list).
  const looksLikeProfile = (t: any) =>
    t.kind === 'OBJECT' &&
    Array.isArray(t.fields) &&
    t.fields.some((f: any) => /email/i.test(f.name)) &&
    t.fields.some((f: any) => /name/i.test(f.name)) &&
    t.fields.some((f: any) => /^id$/i.test(f.name) || /id$/i.test(f.name));
  const profileObj = types.find(looksLikeProfile);
  expect(profileObj).toBeTruthy();

  const idField = (
    profileObj.fields.find((f: any) => /^id$/i.test(f.name)) ||
    profileObj.fields.find((f: any) => /id$/i.test(f.name))
  ).name;

  // Combined / full-name field: a String name-ish field that is NOT first/last.
  const combinedName = profileObj.fields.find(
    (f: any) =>
      /name/i.test(f.name) &&
      !/first/i.test(f.name) &&
      !/last/i.test(f.name) &&
      !/sur/i.test(f.name) &&
      !/given/i.test(f.name) &&
      unwrap(f.type).name === 'String',
  );
  const firstName = profileObj.fields.find(
    (f: any) => /(first|given)/i.test(f.name) && unwrap(f.type).name === 'String',
  );
  const lastName = profileObj.fields.find(
    (f: any) => /(last|sur|family)/i.test(f.name) && unwrap(f.type).name === 'String',
  );

  // Directly-attached email field (a String email field on the profile object).
  const directEmail = profileObj.fields.find(
    (f: any) => /email/i.test(f.name) && unwrap(f.type).name === 'String',
  );

  // Nested contact-info object field on the profile (an OBJECT-typed field).
  const contactField = profileObj.fields.find((f: any) => {
    const u = unwrap(f.type);
    if (u.kind !== 'OBJECT' || !u.name) return false;
    const ct = types.find((t: any) => t.name === u.name);
    return ct && ct.fields && ct.fields.some((cf: any) => /email/i.test(cf.name));
  });
  let contactObj: any = null, contactEmail: any = null;
  if (contactField) {
    contactObj = types.find((t: any) => t.name === unwrap(contactField.type).name);
    contactEmail = contactObj.fields.find(
      (cf: any) => /email/i.test(cf.name) && unwrap(cf.type).name === 'String',
    );
  }

  // Single-profile query: returns profileObj, takes >= 1 id-ish arg.
  const singleQ = qType.fields.find((f: any) => {
    const u = unwrap(f.type);
    return u.name === profileObj.name && !u.list && f.args.length >= 1;
  });
  // List query: a root field returning a LIST of profileObj.
  const listQ = qType.fields.find((f: any) => {
    const u = unwrap(f.type);
    return u.list && u.name === profileObj.name;
  });

  return {
    types, qType, profileObj, idField,
    combinedName, firstName, lastName,
    directEmail, contactField, contactObj, contactEmail,
    singleQ, listQ,
  };
}

function argTypeStr(arg: any): string {
  const go = (t: any): string => {
    if (!t) return 'ID';
    if (t.kind === 'NON_NULL') return go(t.ofType) + '!';
    if (t.kind === 'LIST') return '[' + go(t.ofType) + ']';
    return t.name || 'ID';
  };
  return go(arg.type);
}

describe('profile evolution (independent harness)', () => {

  it('schema builds and exposes a Profile with id, a combined name and split first/last names', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.profileObj).toBeTruthy();
    expect(d.idField).toBeTruthy();
    expect(d.combinedName).toBeTruthy();
    expect(d.firstName).toBeTruthy();
    expect(d.lastName).toBeTruthy();
    // id is never null for seeded profiles
    const idf = d.profileObj.fields.find((f: any) => f.name === d.idField);
    expect(unwrap(idf.type).nonNull).toBe(true);
    // combined name + split names are non-null Strings
    expect(unwrap(d.combinedName.type).nonNull).toBe(true);
    expect(unwrap(d.firstName.type).nonNull).toBe(true);
    expect(unwrap(d.lastName.type).nonNull).toBe(true);
    await server.stop();
  });

  it('OLD combined-name field is marked superseded with a NON-EMPTY reason (introspection)', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.combinedName.isDeprecated).toBe(true);
    expect(typeof d.combinedName.deprecationReason).toBe('string');
    expect((d.combinedName.deprecationReason || '').trim().length).toBeGreaterThan(0);
    await server.stop();
  });

  it('NEW first/last name fields are NOT marked superseded', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(!!d.firstName.isDeprecated).toBe(false);
    expect(!!d.lastName.isDeprecated).toBe(false);
    await server.stop();
  });

  it('directly-attached email field exists and IS marked superseded with a reason', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.directEmail).toBeTruthy();
    expect(d.directEmail.isDeprecated).toBe(true);
    expect((d.directEmail.deprecationReason || '').trim().length).toBeGreaterThan(0);
    await server.stop();
  });

  it('nested contact-info object exists with its own NON-deprecated email field', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.contactField).toBeTruthy();
    expect(d.contactObj).toBeTruthy();
    expect(d.contactEmail).toBeTruthy();
    expect(!!d.contactEmail.isDeprecated).toBe(false);
    expect(unwrap(d.contactEmail.type).name).toBe('String');
    await server.stop();
  });

  it('list query returns a non-null list with no null entries and >= 2 seeded profiles', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.listQ).toBeTruthy();
    const q = `query{ ${d.listQ.name} { ${d.idField} } }`;
    const res = await run(server, q);
    expect(res.errors).toBeFalsy();
    const list = res.data[d.listQ.name];
    expect(Array.isArray(list)).toBe(true);
    expect(list).not.toBeNull();
    // deterministic, seeded set => more than one profile
    expect(list.length).toBeGreaterThanOrEqual(2);
    for (const p of list) {
      expect(p).not.toBeNull();
      expect(p[d.idField]).toBeTruthy();
    }
    // ids unique
    const ids = list.map((p: any) => p[d.idField]);
    expect(new Set(ids).size).toBe(ids.length);
    await server.stop();
  });

  it('OLD combined name equals "first last" of the new split fields for EVERY profile', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const q = `query{ ${d.listQ.name} { ${d.idField} ${d.combinedName.name} ${d.firstName.name} ${d.lastName.name} } }`;
    const res = await run(server, q);
    expect(res.errors).toBeFalsy();
    const list = res.data[d.listQ.name];
    expect(list.length).toBeGreaterThanOrEqual(2);
    for (const p of list) {
      const combined = String(p[d.combinedName.name]);
      const first = String(p[d.firstName.name]);
      const last = String(p[d.lastName.name]);
      expect(combined.length).toBeGreaterThan(0);
      expect(first.length).toBeGreaterThan(0);
      expect(last.length).toBeGreaterThan(0);
      // combined must contain both parts AND be consistent with "first last"
      expect(combined).toContain(first);
      expect(combined).toContain(last);
      const norm = (s: string) => s.replace(/\s+/g, ' ').trim().toLowerCase();
      expect(norm(combined)).toBe(norm(first + ' ' + last));
    }
    await server.stop();
  });

  it('directly-attached email equals the nested contact-info email for EVERY profile', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const q =
      `query{ ${d.listQ.name} { ${d.idField} ${d.directEmail.name} ` +
      `${d.contactField.name} { ${d.contactEmail.name} } } }`;
    const res = await run(server, q);
    expect(res.errors).toBeFalsy();
    const list = res.data[d.listQ.name];
    expect(list.length).toBeGreaterThanOrEqual(2);
    for (const p of list) {
      const direct = p[d.directEmail.name];
      const nested = p[d.contactField.name] ? p[d.contactField.name][d.contactEmail.name] : null;
      expect(typeof direct).toBe('string');
      expect(direct.length).toBeGreaterThan(0);
      expect(typeof nested).toBe('string');
      expect(direct).toBe(nested);
    }
    // emails are distinct per profile (not a single hardcoded constant)
    const directs = list.map((p: any) => p[d.directEmail.name]);
    expect(new Set(directs).size).toBe(directs.length);
    await server.stop();
  });

  it('single-profile fetch HIT returns the same id and consistent name/email', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.singleQ).toBeTruthy();
    // pick a known id from the list
    const listRes = await run(server, `query{ ${d.listQ.name} { ${d.idField} } }`);
    const known = listRes.data[d.listQ.name][0][d.idField];

    const argName = d.singleQ.args[0].name;
    const q =
      `query($id: ${argTypeStr(d.singleQ.args[0])}){ ${d.singleQ.name}(${argName}: $id){ ` +
      `${d.idField} ${d.combinedName.name} ${d.firstName.name} ${d.lastName.name} ` +
      `${d.directEmail.name} ${d.contactField.name} { ${d.contactEmail.name} } } }`;
    const res = await run(server, q, { id: known });
    expect(res.errors).toBeFalsy();
    const p = res.data[d.singleQ.name];
    expect(p).toBeTruthy();
    expect(p[d.idField]).toBe(known);
    const norm = (s: string) => s.replace(/\s+/g, ' ').trim().toLowerCase();
    expect(norm(String(p[d.combinedName.name]))).toBe(
      norm(p[d.firstName.name] + ' ' + p[d.lastName.name]),
    );
    expect(p[d.directEmail.name]).toBe(p[d.contactField.name][d.contactEmail.name]);
    await server.stop();
  });

  it('single-profile fetch MISS (unknown id) yields null and NO execution error', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const argName = d.singleQ.args[0].name;
    const q = `query($id: ${argTypeStr(d.singleQ.args[0])}){ ${d.singleQ.name}(${argName}: $id){ ${d.idField} } }`;
    const res = await run(server, q, { id: 'definitely-not-a-real-profile-zzz' });
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    expect(res.data[d.singleQ.name]).toBeNull();
    await server.stop();
  });

  it('querying the OLD email and OLD combined name still succeeds (no deprecation removal)', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const listRes = await run(server, `query{ ${d.listQ.name} { ${d.idField} } }`);
    const known = listRes.data[d.listQ.name][0][d.idField];
    const argName = d.singleQ.args[0].name;
    // Selecting deprecated fields must still execute and return non-null values.
    const q =
      `query($id: ${argTypeStr(d.singleQ.args[0])}){ ${d.singleQ.name}(${argName}: $id){ ` +
      `${d.combinedName.name} ${d.directEmail.name} } }`;
    const res = await run(server, q, { id: known });
    expect(res.errors).toBeFalsy();
    const p = res.data[d.singleQ.name];
    expect(typeof p[d.combinedName.name]).toBe('string');
    expect(p[d.combinedName.name].length).toBeGreaterThan(0);
    expect(typeof p[d.directEmail.name]).toBe('string');
    expect(p[d.directEmail.name].length).toBeGreaterThan(0);
    await server.stop();
  });
});
"""

    @classmethod
    def _ensure_workspace_built(cls):
        """ts-jest type-checks server src, which imports sibling workspace packages
        by their built `dist` types.  If those dist outputs are missing, run the
        repo's `compile` build once so the sibling packages resolve."""
        gw_types = os.path.join(
            cls.REPO_DIR, "packages", "gateway-interface", "dist", "esm", "index.d.ts"
        )
        if os.path.isfile(gw_types):
            return
        subprocess.run(
            ["npm", "run", "compile"],
            cwd=cls.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=900,
        )

    # --------------------------------------------------------- module fixture
    @pytest.fixture(scope="class", autouse=True)
    def _install_deps(self):
        assert os.path.isdir(self.REPO_DIR), f"missing repo {self.REPO_DIR}"
        if ensure_npm_dependencies is not None:
            ensure_npm_dependencies(self.REPO_DIR)
        self._ensure_workspace_built()
        yield
        try:
            if os.path.exists(self.HARNESS_PATH):
                os.remove(self.HARNESS_PATH)
        except OSError:
            pass

    @pytest.fixture(scope="class")
    def harness_report(self):
        """Write our independent harness suite, run it once, return the jest json."""
        os.makedirs(self.HARNESS_DIR, exist_ok=True)
        with open(self.HARNESS_PATH, "w", encoding="utf-8") as fh:
            fh.write(self._harness_source())
        proc, report = self._run_jest(self.HARNESS_REL, timeout=600)
        return {"proc": proc, "report": report}

    # =========================== L1: deliverables ===========================
    def test_module_file_exists(self):
        """L1: the profile-evolution module exists at the required path."""
        assert os.path.isfile(self.MODULE_PATH), f"missing {self.MODULE_REL}"

    def test_suite_file_exists(self):
        """L1: the agent's Jest suite file exists at the required path."""
        assert os.path.isfile(self.SUITE_PATH), f"missing {self.SUITE_REL}"

    def test_module_exports_typedefs_resolvers_and_factory(self):
        """L1: module declares exported typeDefs, resolvers, and a store factory."""
        src = self._read(self.MODULE_PATH)
        assert re.search(r"export\s+(const|let|var|function)\s+typeDefs", src) or re.search(
            r"\btypeDefs\b", src
        ), "no typeDefs export"
        assert re.search(r"\bresolvers\b", src), "no resolvers export"
        assert re.search(
            r"export\s+(const|function)\s+\w*(create|make|store|seed|profile)\w*",
            src,
            re.IGNORECASE,
        ), "no store-factory export found"

    def test_module_has_no_other_example_imports(self):
        """L1: module is self-contained (does not import from sibling example files)."""
        src = self._read(self.MODULE_PATH)
        for m in re.finditer(r"""import[^;]*?from\s*['"]([^'"]+)['"]""", src):
            spec = m.group(1)
            if "examples/" in spec and "profileEvolution" not in spec:
                pytest.fail(f"module imports another example file: {spec}")

    def test_module_does_not_modify_public_index(self):
        """L1: the package's public index.ts must not be made to export this module."""
        index_path = os.path.join(self.SERVER_DIR, "src", "index.ts")
        if not os.path.isfile(index_path):
            pytest.skip("index.ts not present")
        src = self._read(index_path)
        assert "profileEvolution" not in src, (
            "public index.ts must not export the profileEvolution module"
        )

    def test_agent_suite_declares_at_least_10_cases(self):
        """L1: the agent's own suite declares >= 10 it/test cases (acceptance criterion)."""
        src = self._read(self.SUITE_PATH)
        count = len(re.findall(r"\b(it|test)\s*(\.\w+)?\s*\(", src))
        assert count >= 10, f"agent suite declares only {count} it/test cases"

    # ===================== L2: dynamic via independent harness ================
    def _passed(self, harness_report, title_regex):
        report = harness_report["report"]
        proc = harness_report["proc"]
        assert report is not None, (
            "jest produced no parseable JSON report.\n"
            f"returncode={proc.returncode}\n"
            f"stdout(tail)={proc.stdout[-3000:]}\n"
            f"stderr(tail)={proc.stderr[-3000:]}"
        )
        results = self._assertions_by_title(report)
        rx = re.compile(title_regex, re.IGNORECASE)
        matched = {t: s for t, s in results.items() if rx.search(t)}
        assert matched, (
            f"no harness test matched /{title_regex}/. "
            f"available titles={list(results.keys())}\n"
            f"stderr(tail)={proc.stderr[-2000:]}"
        )
        for title, status in matched.items():
            assert status == "passed", (
                f"harness case '{title}' status={status}\n"
                f"stderr(tail)={proc.stderr[-3000:]}"
            )

    def test_agent_acceptance_suite_passes(self, harness_report):
        """L2: the acceptance command (agent's own suite) passes all assertions."""
        proc, report = self._run_jest(self.SUITE_REL, timeout=600)
        assert report is not None, (
            "agent suite produced no JSON.\n"
            f"rc={proc.returncode}\nstdout(tail)={proc.stdout[-2500:]}\n"
            f"stderr(tail)={proc.stderr[-2500:]}"
        )
        num_total = report.get("numTotalTests", 0)
        num_passed = report.get("numPassedTests", 0)
        num_failed = report.get("numFailedTests", -1)
        assert num_total >= 10, f"agent suite ran only {num_total} tests"
        assert num_failed == 0 and num_passed == num_total, (
            f"agent suite failing: passed={num_passed} failed={num_failed} total={num_total}\n"
            f"stderr(tail)={proc.stderr[-3000:]}"
        )

    def test_harness_schema_and_profile_shape(self, harness_report):
        """L2: schema builds; Profile has id + combined name + split first/last names."""
        self._passed(harness_report, r"schema builds and exposes a Profile")

    def test_harness_old_name_superseded_with_reason(self, harness_report):
        """L2: old combined-name field is deprecated with a non-empty reason."""
        self._passed(harness_report, r"OLD combined-name field is marked superseded")

    def test_harness_new_names_not_superseded(self, harness_report):
        """L2: the new first/last name fields are NOT deprecated."""
        self._passed(harness_report, r"NEW first/last name fields are NOT marked superseded")

    def test_harness_old_email_superseded(self, harness_report):
        """L2: directly-attached email field exists and is deprecated with a reason."""
        self._passed(harness_report, r"directly-attached email field exists and IS marked superseded")

    def test_harness_nested_contact_email_not_superseded(self, harness_report):
        """L2: nested contact-info email exists and is not deprecated."""
        self._passed(harness_report, r"nested contact-info object exists")

    def test_harness_list_non_null_no_null_entries(self, harness_report):
        """L2: list query returns a non-null list with no null entries, >= 2 profiles."""
        self._passed(harness_report, r"list query returns a non-null list")

    def test_harness_name_consistency(self, harness_report):
        """L2: combined name == 'first last' for every seeded profile."""
        self._passed(harness_report, r'OLD combined name equals "first last"')

    def test_harness_email_agreement(self, harness_report):
        """L2: directly-attached email == nested contact email for every profile."""
        self._passed(harness_report, r"directly-attached email equals the nested contact-info email")

    def test_harness_single_fetch_hit(self, harness_report):
        """L2: single-profile fetch hit returns consistent name/email for a known id."""
        self._passed(harness_report, r"single-profile fetch HIT")

    def test_harness_single_fetch_miss_null(self, harness_report):
        """L2: unknown profile id resolves to null with no execution error."""
        self._passed(harness_report, r"single-profile fetch MISS")

    def test_harness_deprecated_fields_still_query(self, harness_report):
        """L2: selecting the deprecated old fields still executes and returns values."""
        self._passed(harness_report, r"querying the OLD email and OLD combined name still succeeds")
