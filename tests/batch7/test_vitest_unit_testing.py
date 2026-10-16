"""
Test for the 'vitest-unit-testing' skill — variant ext7.

Task (re-derived from tasks/ext7/vitest-unit-testing.md):
  Add an exported TYPE `DeepReadonly<T>` to
  packages/vite/src/node/typeUtils.ts that recursively makes every property
  of an object/array/tuple type `readonly` at every depth, while leaving
  primitives and function types unchanged and preserving optionality.
  Pin its behavior with a dedicated Vitest type-testing spec at
  packages/vite/src/node/__tests__/deepReadonly.spec.ts that uses
  `expectTypeOf` / `assertType` (>= 8 type-level assertions).

  Native acceptance command (from the doc):
      pnpm exec vitest run packages/vite/src/node/__tests__/deepReadonly.spec.ts

Verification strategy:
- L1: deliverable files exist; the type is exported from typeUtils.ts; the
  agent's spec imports the type from '../typeUtils' and uses the Vitest
  type-testing API with a meaningful number of assertions.
- L2: DYNAMIC verification of the *type behavior*. The repo's plain
  `vitest run` does NOT enable typecheck mode, so `expectTypeOf` calls are
  no-ops at runtime; a wrong type would still "pass" a bare runtime run.
  Therefore we verify the TYPE semantics two ways:
    (a) Run the native acceptance command itself, but with type checking
        enabled — `pnpm exec vitest --typecheck run <agent spec>` — so the
        agent's own type assertions are actually enforced.
    (b) INDEPENDENT harness: we drop our OWN `.ts` driver files that import
        the real `DeepReadonly` from `../typeUtils` and we compile them with
        the repo's TypeScript via `pnpm exec tsc --noEmit` against a strict
        tsconfig we generate. The drivers use `@ts-expect-error` on lines that
        MUST error (e.g. mutating a deeply-nested property) and plain
        assignments on lines that MUST type-check (e.g. reading nested values,
        assigning a `readonly number[]` into `DeepReadonly<number[]>`,
        round-tripping a primitive, preserving optionality). A shallow-only
        implementation (`type DeepReadonly<T> = Readonly<T>`), one that
        descends into functions, or one that drops optionality makes at least
        one `@ts-expect-error` become unused (tsc error) or makes a
        must-compile line fail — either way tsc returns nonzero.
"""

import json
import os
import re
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/vite"
NODE_DIR = os.path.join(REPO_DIR, "packages", "vite", "src", "node")
TESTS_DIR = os.path.join(NODE_DIR, "__tests__")
TYPEUTILS_TS = os.path.join(NODE_DIR, "typeUtils.ts")
AGENT_SPEC = os.path.join(TESTS_DIR, "deepReadonly.spec.ts")

# absolute paths of any scratch files we create; cleaned up at module teardown.
_SCRATCH_FILES = []
# dedicated scratch dir for tsc driver harnesses (inside src/node so the
# relative import '../typeUtils' resolves exactly like the real spec).
_SCRATCH_DIR = os.path.join(NODE_DIR, "__ext7_typecheck__")


def _run(cmd, timeout=600, cwd=REPO_DIR):
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )


def _vitest_typecheck(rel_spec_path, timeout=600):
    """Run a single spec through native vitest WITH typecheck enabled.

    With `--typecheck`, vitest type-tests (expectTypeOf/assertType) are
    actually enforced; a wrong DeepReadonly fails the run.
    """
    cmd = ["pnpm", "exec", "vitest", "--typecheck", "run", rel_spec_path]
    return _run(cmd, timeout=timeout)


def _vitest_run(rel_spec_path, timeout=600):
    """Run a single spec through the plain native acceptance command."""
    cmd = ["pnpm", "exec", "vitest", "run", rel_spec_path]
    return _run(cmd, timeout=timeout)


def _tsc_check_driver(name, body, timeout=600):
    """Compile an independent .ts driver against the real DeepReadonly.

    The driver lives in src/node/__ext7_typecheck__/ so that an import of
    '../typeUtils' resolves to the real implementation. We generate a strict
    tsconfig that includes ONLY our driver, then run `pnpm exec tsc --noEmit`.
    Returns the CompletedProcess.
    """
    os.makedirs(_SCRATCH_DIR, exist_ok=True)
    ts_path = os.path.join(_SCRATCH_DIR, name + ".ts")
    with open(ts_path, "w") as f:
        f.write(textwrap.dedent(body).lstrip("\n"))
    _SCRATCH_FILES.append(ts_path)

    tsconfig_path = os.path.join(_SCRATCH_DIR, name + ".tsconfig.json")
    tsconfig = {
        "compilerOptions": {
            "target": "es2023",
            "module": "preserve",
            "moduleResolution": "bundler",
            "strict": True,
            "exactOptionalPropertyTypes": True,
            "noEmit": True,
            "skipLibCheck": True,
            "types": [],
        },
        # compile ONLY our driver (the import pulls typeUtils transitively).
        "files": [os.path.relpath(ts_path, _SCRATCH_DIR).replace(os.sep, "/")],
    }
    with open(tsconfig_path, "w") as f:
        json.dump(tsconfig, f)
    _SCRATCH_FILES.append(tsconfig_path)

    cmd = ["pnpm", "exec", "tsc", "--noEmit", "-p", tsconfig_path]
    return _run(cmd, timeout=timeout)


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    for p in _SCRATCH_FILES:
        try:
            os.remove(p)
        except OSError:
            pass
    try:
        # remove scratch dir if now empty
        if os.path.isdir(_SCRATCH_DIR) and not os.listdir(_SCRATCH_DIR):
            os.rmdir(_SCRATCH_DIR)
    except OSError:
        pass


class TestVitestUnitTesting:
    """Verify the DeepReadonly<T> type utility and its type-level spec."""

    REPO_DIR = "/workspace/vite"

    # ------------------------------------------------------------------
    # L1 — deliverables exist / minimally well-formed
    # ------------------------------------------------------------------

    def test_typeutils_file_exists(self):
        """typeUtils.ts (the modify target) must exist."""
        assert os.path.isfile(TYPEUTILS_TS), f"missing {TYPEUTILS_TS}"

    def test_deepreadonly_is_exported(self):
        """typeUtils.ts must export a TYPE named DeepReadonly."""
        with open(TYPEUTILS_TS) as f:
            src = f.read()
        assert re.search(
            r"export\s+type\s+DeepReadonly\b", src
        ), "DeepReadonly is not exported as a `type` from typeUtils.ts"

    def test_deepreadonly_is_generic_and_recursive(self):
        """DeepReadonly must be generic in T and reference itself (recursion).

        A non-recursive `Readonly<T>` rename cannot satisfy the deep
        requirement; the definition must mention DeepReadonly again.
        """
        with open(TYPEUTILS_TS) as f:
            src = f.read()
        m = re.search(r"export\s+type\s+DeepReadonly\s*<\s*([A-Za-z_]\w*)", src)
        assert m, "DeepReadonly must be a generic type (export type DeepReadonly<T>)"
        # the RHS of the definition (after the first '=') must reference
        # DeepReadonly recursively somewhere.
        eq = src.index("DeepReadonly")
        after = src[eq:]
        rhs = after.split("=", 1)
        assert len(rhs) == 2, "DeepReadonly must be a type alias with a body"
        assert "DeepReadonly" in rhs[1][:600], (
            "DeepReadonly definition does not appear recursive "
            "(a shallow Readonly<T> alias will fail L2)"
        )

    def test_agent_spec_exists(self):
        """The dedicated type-testing spec file must be delivered."""
        assert os.path.isfile(AGENT_SPEC), f"missing {AGENT_SPEC}"

    def test_agent_spec_imports_type_and_uses_typetesting_api(self):
        """Spec must import DeepReadonly from '../typeUtils' and use the
        Vitest type-testing API with at least 8 assertions."""
        with open(AGENT_SPEC) as f:
            spec = f.read()
        assert "DeepReadonly" in spec, "spec does not reference DeepReadonly"
        assert re.search(
            r"from\s+['\"]\.\./typeUtils['\"]", spec
        ), "spec must import from '../typeUtils'"
        api_uses = len(re.findall(r"\bexpectTypeOf\b", spec)) + len(
            re.findall(r"\bassertType\b", spec)
        )
        assert api_uses >= 8, (
            "spec must contain >= 8 type-level assertions "
            f"(expectTypeOf/assertType); found {api_uses}"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic verification of the TYPE behavior.
    # (a) the agent's own spec, enforced via vitest --typecheck
    # (b) independent tsc harnesses that pin each required semantic
    # ------------------------------------------------------------------

    def test_agent_spec_passes_under_vitest_typecheck(self):
        """The agent's spec must pass under the native command WITH typecheck.

        Plain `vitest run` would not enforce type assertions, so we run the
        same spec with `--typecheck` (the meaningful execution of a
        type-testing file). It must exit 0 with its assertions enforced.
        """
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        rel = os.path.relpath(AGENT_SPEC, REPO_DIR)
        res = _vitest_typecheck(rel)
        assert res.returncode == 0, (
            "agent's deepReadonly.spec.ts fails under `vitest --typecheck run`\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
        combined = (res.stdout + res.stderr).lower()
        assert "no test" not in combined, "agent spec contains no tests"

    def test_agent_spec_also_runs_under_plain_native_command(self):
        """The exact doc acceptance command must also succeed (no runtime crash).

        `pnpm exec vitest run <spec>` is the literal acceptance command; the
        file must at least load and run cleanly (imports resolve, no thrown
        errors), independent of typecheck enforcement.
        """
        rel = os.path.relpath(AGENT_SPEC, REPO_DIR)
        res = _vitest_run(rel)
        assert res.returncode == 0, (
            "native `pnpm exec vitest run` of the agent spec failed\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_nested_object_is_deeply_readonly(self):
        """Independent tsc: a nested property must be readonly at every depth.

        Mutating `x.a.b.c` must be a type error. A shallow `Readonly<T>`
        leaves `.a` mutable, so the `@ts-expect-error` lines become unused
        => tsc errors => returncode != 0.
        """
        res = _tsc_check_driver(
            "nested_readonly",
            """
            import type { DeepReadonly } from '../typeUtils'

            type Deep = DeepReadonly<{ a: { b: { c: number } }; list: number[] }>
            declare const x: Deep

            // reads must compile (proves structure is preserved)
            const c: number = x.a.b.c
            void c

            // every level must be readonly -> these mutations MUST error
            // @ts-expect-error top-level property is readonly
            x.a = { b: { c: 1 } }
            // @ts-expect-error nested property is readonly
            x.a.b = { c: 1 }
            // @ts-expect-error deeply-nested property is readonly
            x.a.b.c = 5
            // @ts-expect-error array element write is rejected (readonly array)
            x.list[0] = 9
            """,
        )
        assert res.returncode == 0, (
            "DeepReadonly is not deeply readonly (a shallow Readonly<T> fails "
            "here because nested mutations are still allowed)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_array_becomes_readonly_array(self):
        """Independent tsc: DeepReadonly<U[]> behaves as ReadonlyArray<...>.

        A `readonly number[]` must be assignable INTO DeepReadonly<number[]>,
        mutation/push must be rejected, and the element type must itself be
        deeply readonly.
        """
        res = _tsc_check_driver(
            "array_readonly",
            """
            import type { DeepReadonly } from '../typeUtils'

            type RNums = DeepReadonly<number[]>
            // a readonly number[] is assignable into DeepReadonly<number[]>
            const src: readonly number[] = [1, 2, 3]
            const dr: RNums = src
            const first: number = dr[0]
            void first

            // mutation is rejected
            // @ts-expect-error cannot assign to readonly index
            dr[0] = 10
            // @ts-expect-error push does not exist on a readonly array
            dr.push(4)

            // element type is itself deeply readonly
            type RObjs = DeepReadonly<{ p: number }[]>
            declare const objs: RObjs
            const p: number = objs[0].p
            void p
            // @ts-expect-error element's property is readonly
            objs[0].p = 1
            """,
        )
        assert res.returncode == 0, (
            "DeepReadonly<U[]> is not a readonly array of deeply-readonly U\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_tuple_becomes_readonly_tuple(self):
        """Independent tsc: a tuple becomes a readonly tuple, element-wise deep."""
        res = _tsc_check_driver(
            "tuple_readonly",
            """
            import type { DeepReadonly } from '../typeUtils'

            type T = DeepReadonly<[number, { a: string }]>
            declare const t: T

            // reads preserve element types / positions
            const n: number = t[0]
            const s: string = t[1].a
            void n
            void s

            // tuple slots are readonly
            // @ts-expect-error tuple element 0 is readonly
            t[0] = 1
            // @ts-expect-error nested object inside tuple is readonly
            t[1].a = 'x'
            """,
        )
        assert res.returncode == 0, (
            "DeepReadonly of a tuple is not a deep readonly tuple\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_primitives_pass_through_unchanged(self):
        """Independent tsc: primitives are identity-mapped by DeepReadonly.

        DeepReadonly<string> must be bidirectionally assignable with string
        (i.e. equal), and likewise for number/boolean. If a buggy impl wrapped
        primitives in an object/branded type, one of these assignments errors.
        """
        res = _tsc_check_driver(
            "primitive_identity",
            """
            import type { DeepReadonly } from '../typeUtils'

            // bidirectional assignability == type equality
            const a: DeepReadonly<string> = 'hi'
            const b: string = a
            void b

            const n1: DeepReadonly<number> = 1
            const n2: number = n1
            void n2

            const bl1: DeepReadonly<boolean> = true
            const bl2: boolean = bl1
            void bl2

            // a function value typed via DeepReadonly<number> still usable as number
            const sum: number = n1 + 0
            void sum
            """,
        )
        assert res.returncode == 0, (
            "DeepReadonly does not leave primitives unchanged\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_function_types_pass_through_unchanged(self):
        """Independent tsc: function types are NOT descended into.

        DeepReadonly<Fn> must still be callable with the original signature
        and assignable from the original function type. A naive mapped type
        that recurses into every property would turn a function into an object
        and break callability.
        """
        res = _tsc_check_driver(
            "function_identity",
            """
            import type { DeepReadonly } from '../typeUtils'

            type Fn = (x: number, y: string) => boolean
            const f: DeepReadonly<Fn> = (x, y) => x > 0 && y.length > 0
            // still callable with the original signature
            const r: boolean = f(1, 'ok')
            void r

            // original function type assignable into DeepReadonly<Fn>
            const g: Fn = (x, y) => y.length === x
            const h: DeepReadonly<Fn> = g
            void h

            // an object property whose value is a function keeps it callable
            type Obj = DeepReadonly<{ run: (n: number) => number }>
            declare const o: Obj
            const out: number = o.run(2)
            void out
            """,
        )
        assert res.returncode == 0, (
            "DeepReadonly descended into a function type (broke callability)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_optional_property_stays_optional(self):
        """Independent tsc: optionality is preserved through the transform.

        With exactOptionalPropertyTypes, an optional property may be omitted.
        A buggy impl that strips `?` (making the property required) would make
        the omitting object literal error. We also assert the property is
        readonly.
        """
        res = _tsc_check_driver(
            "optional_preserved",
            """
            import type { DeepReadonly } from '../typeUtils'

            type O = DeepReadonly<{ a?: { b: number }; c: number }>

            // optional 'a' may be omitted -> must compile
            const ok: O = { c: 1 }
            void ok
            const ok2: O = { a: { b: 2 }, c: 1 }
            void ok2

            declare const o: O
            // when present, nested value is readonly
            // @ts-expect-error optional-but-present property is still readonly
            o.a = { b: 3 }
            // @ts-expect-error required sibling is readonly too
            o.c = 4
            """,
        )
        assert res.returncode == 0, (
            "DeepReadonly does not preserve optionality / readonly on optionals\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_shallow_impl_would_be_rejected(self):
        """Meta/negative control: prove the harness is DISCRIMINATIVE.

        We compile a LOCAL shallow-only `type ShallowReadonly<T> = Readonly<T>`
        against the SAME deep-mutation drivers. tsc MUST report errors for it
        (the nested-mutation `@ts-expect-error` lines become unused), proving
        our nested/array drivers truly separate a correct deep impl from a
        shallow stub. If this somehow compiled clean, our positive tests would
        be non-discriminative, so we assert failure here.
        """
        res = _tsc_check_driver(
            "shallow_control",
            """
            // Local shallow stub standing in for a naive implementation.
            type ShallowReadonly<T> = Readonly<T>

            type Deep = ShallowReadonly<{ a: { b: number }; list: number[] }>
            declare const x: Deep

            // Under a CORRECT deep impl these would each error; under the
            // shallow stub the nested writes are allowed, so the
            // @ts-expect-error directives are UNUSED -> tsc errors.
            // @ts-expect-error (deep impl: nested readonly)
            x.a.b = 5
            // @ts-expect-error (deep impl: readonly array element)
            x.list[0] = 9
            """,
        )
        assert res.returncode != 0, (
            "Negative control unexpectedly compiled: the tsc harness is not "
            "discriminating deep-vs-shallow. (A shallow Readonly<T> must leave "
            "nested writes allowed, making the @ts-expect-error lines unused.)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
