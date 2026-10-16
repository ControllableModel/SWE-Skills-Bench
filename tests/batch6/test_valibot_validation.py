"""
Benchmark test for the `valibot-validation` skill (variant ext6).

Skill task: implement a self-contained NESTED COMMENT TREE validation module
(`library/src/commentTree/`) built on Valibot's own public API. The module
exports `parseComment(input: unknown)` plus the underlying recursive schema and
the inferred `Comment` type. Unlike the ext1 variant (which returns a
discriminated `{ ok, data | errors }` result), this variant's `parseComment`
returns the validated/normalized comment DIRECTLY and THROWS on invalid input.

Each comment node has:
  * id     - non-empty string (required)
  * author - string, trimmed, non-empty after trimming (required)
  * text   - string, trimmed, length 1..500 after trimming (required; output is trimmed)
  * replies- optional array of comment nodes of the SAME shape; defaults to []
             at every node where it was absent; validated recursively to any depth.
Unknown extra keys are stripped at every node.

What this test verifies:
  * L1 - the deliverable files exist and are minimally well-formed (the module,
    its barrel re-export, and an agent-authored test suite with >= 10 cases).
  * L2 - DYNAMIC EXECUTION: we drop our OWN vitest driver into the repo that
    imports the agent's `parseComment` from `library/src/commentTree/index.ts`
    and exercises recursion, per-node defaulting of `replies`, trimming of
    `author`/`text`, unknown-key stripping at nested nodes, the empty-id /
    empty-author / empty-text / over-length-text rejections, deep invalid-node
    rejection, and non-object input rejection -- deep-validating the returned
    tree. The agent's own test file is NOT trusted for behavior; we exercise
    the real exported function instead.

Run by the harness with:
    python -m pytest /tmp/benchmark_tests/test_valibot_validation.py -v --tb=short
"""

import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/valibot"
LIB_DIR = os.path.join(REPO_DIR, "library")
SRC_DIR = os.path.join(LIB_DIR, "src")
MODULE_DIR = os.path.join(SRC_DIR, "commentTree")
# Temp dir for our own driver vitest files (kept inside src so vite resolves it).
DRIVER_DIR = os.path.join(SRC_DIR, "__benchmark_commenttree__")

NPX = "npx"
VITEST_TIMEOUT = 600


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module", autouse=True)
def ensure_deps_and_cleanup():
    """Make sure vitest is runnable and clean up our driver dir afterwards."""
    try:
        from _dependency_utils import ensure_npm_dependencies  # type: ignore

        try:
            ensure_npm_dependencies(LIB_DIR)
        except Exception:
            # Container is expected to already have deps installed; ignore.
            pass
    except Exception:
        pass
    os.makedirs(DRIVER_DIR, exist_ok=True)
    yield
    # Best-effort cleanup of anything we wrote.
    try:
        import shutil

        shutil.rmtree(DRIVER_DIR, ignore_errors=True)
    except Exception:
        pass


def _run_vitest(test_filename):
    """Run a single vitest file (relative to library/) and return CompletedProcess."""
    rel = os.path.relpath(os.path.join(DRIVER_DIR, test_filename), LIB_DIR)
    return subprocess.run(
        [NPX, "vitest", "run", "--no-coverage", rel],
        cwd=LIB_DIR,
        capture_output=True,
        text=True,
        timeout=VITEST_TIMEOUT,
    )


def _write_driver(test_filename, body):
    """Write a vitest driver that imports the agent's module and asserts `body`.

    `body` is TypeScript placed inside a single `test(...)` block. The driver
    imports `parseComment` from the agent's barrel file via a relative path. A
    small `expectThrow` helper asserts that a call throws regardless of error
    class (parseComment is required to throw, not return a result object).
    """
    path = os.path.join(DRIVER_DIR, test_filename)
    content = textwrap.dedent(
        """
        import {{ describe, expect, test }} from 'vitest';
        import {{ parseComment }} from '../commentTree/index.ts';

        // A canonical valid leaf used across cases.
        const LEAF = {{ id: '1', author: 'Ada', text: 'hi' }};

        function expectThrow(fn: () => unknown) {{
          let threw = false;
          try {{
            fn();
          }} catch (e) {{
            threw = true;
          }}
          expect(threw).toBe(true);
        }}

        describe('commentTree benchmark driver', () => {{
          test('case', () => {{
        {body}
          }});
        }});
        """
    ).format(body=textwrap.indent(textwrap.dedent(body), "    "))
    with open(path, "w") as fh:
        fh.write(content)
    return path


def _assert_vitest_pass(proc, label):
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, (
        f"[{label}] vitest run failed (rc={proc.returncode}).\n"
        f"----- stdout/stderr -----\n{combined[-4000:]}"
    )
    # Guard against "0 passed" / no-tests-found situations.
    assert "1 passed" in combined or "passed" in combined, (
        f"[{label}] vitest produced no passing tests.\n{combined[-2000:]}"
    )


# --------------------------------------------------------------------------- #
# L1 - deliverable files exist and are minimally well-formed
# --------------------------------------------------------------------------- #
class TestValibotValidation:
    REPO_DIR = REPO_DIR

    def test_module_file_exists(self):
        """L1: commentTree.ts exists and is non-trivially sized."""
        path = os.path.join(MODULE_DIR, "commentTree.ts")
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 100, "commentTree.ts is suspiciously small"

    def test_barrel_index_exists(self):
        """L1: index.ts barrel exists and re-exports from the module file."""
        path = os.path.join(MODULE_DIR, "index.ts")
        assert os.path.isfile(path), f"missing barrel: {path}"
        with open(path) as fh:
            text = fh.read()
        assert "commentTree" in text, "index.ts does not re-export the commentTree module"

    def test_agent_test_suite_exists(self):
        """L1: the agent authored a test suite with at least 10 test cases."""
        path = os.path.join(MODULE_DIR, "commentTree.test.ts")
        assert os.path.isfile(path), f"missing test file: {path}"
        with open(path) as fh:
            text = fh.read()
        # Count `test(`/`it(` occurrences as a coarse lower bound.
        n = text.count("test(") + text.count("it(")
        assert n >= 10, f"expected >= 10 test cases in suite, found ~{n}"

    # ----------------------------------------------------------------------- #
    # L2 - dynamic execution against the real exported function
    # ----------------------------------------------------------------------- #
    def test_leaf_defaults_replies_to_empty_array(self):
        """L2: a valid leaf node returns the comment with replies defaulted to []."""
        _write_driver(
            "leaf.test.ts",
            """
            const out = parseComment({ id: '1', author: 'Ada', text: 'hi' }) as any;
            expect(out.id).toBe('1');
            expect(out.author).toBe('Ada');
            expect(out.text).toBe('hi');
            // replies must be present and an empty array (a naive impl that
            // omits this default will fail here).
            expect(Array.isArray(out.replies)).toBe(true);
            expect(out.replies).toEqual([]);
            """,
        )
        _assert_vitest_pass(_run_vitest("leaf.test.ts"), "leaf")

    def test_author_and_text_are_trimmed(self):
        """L2: author/text are trimmed in the returned output."""
        _write_driver(
            "trim.test.ts",
            """
            const out = parseComment({ id: '1', author: '  Bo  ', text: '  hey  ' }) as any;
            expect(out.author).toBe('Bo');
            expect(out.text).toBe('hey');
            // a stub that returns the input unchanged would still carry the
            // surrounding whitespace and fail above.
            """,
        )
        _assert_vitest_pass(_run_vitest("trim.test.ts"), "trim")

    def test_multi_level_tree_validates_and_defaults_recursively(self):
        """L2: a two-level nested tree validates; defaults/trimming apply at every node."""
        _write_driver(
            "nested.test.ts",
            """
            const out = parseComment({
              id: 'root',
              author: '  Root  ',
              text: '  top  ',
              replies: [
                {
                  id: 'c1',
                  author: ' Child1 ',
                  text: ' first ',
                  replies: [
                    { id: 'g1', author: '  G  ', text: '  deep  ' },
                  ],
                },
                { id: 'c2', author: 'Child2', text: 'second' },
              ],
            }) as any;

            // root
            expect(out.author).toBe('Root');
            expect(out.text).toBe('top');
            expect(out.replies.length).toBe(2);

            // ordering preserved
            expect(out.replies[0].id).toBe('c1');
            expect(out.replies[1].id).toBe('c2');

            // nested level 1 trimming + recursion
            expect(out.replies[0].author).toBe('Child1');
            expect(out.replies[0].text).toBe('first');
            expect(out.replies[0].replies.length).toBe(1);

            // nested level 2 (deepest) trimming + defaulted replies
            const deep = out.replies[0].replies[0];
            expect(deep.id).toBe('g1');
            expect(deep.author).toBe('G');
            expect(deep.text).toBe('deep');
            expect(deep.replies).toEqual([]);

            // sibling without replies -> defaulted []
            expect(out.replies[1].replies).toEqual([]);
            """,
        )
        _assert_vitest_pass(_run_vitest("nested.test.ts"), "nested")

    def test_unknown_keys_stripped_at_every_node(self):
        """L2: unknown extra keys are stripped at the root AND at nested nodes."""
        _write_driver(
            "strip.test.ts",
            """
            const out = parseComment({
              id: '1',
              author: 'Ada',
              text: 'hi',
              evil: 'x',
              isAdmin: true,
              replies: [
                { id: '2', author: 'Bo', text: 'yo', secret: 42, __proto__nope: 1 },
              ],
            }) as any;

            // root keys are exactly the schema keys
            expect(Object.keys(out).sort()).toEqual(
              ['author', 'id', 'replies', 'text'].sort()
            );
            expect('evil' in out).toBe(false);
            expect('isAdmin' in out).toBe(false);

            // nested node also stripped
            const child = out.replies[0];
            expect(Object.keys(child).sort()).toEqual(
              ['author', 'id', 'replies', 'text'].sort()
            );
            expect('secret' in child).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("strip.test.ts"), "strip")

    def test_empty_id_rejected(self):
        """L2: an empty `id` causes a throw."""
        _write_driver(
            "empty_id.test.ts",
            """
            expectThrow(() => parseComment({ id: '', author: 'x', text: 'y' }));
            // sanity: the same node with a non-empty id is accepted
            const ok = parseComment({ id: '1', author: 'x', text: 'y' }) as any;
            expect(ok.id).toBe('1');
            """,
        )
        _assert_vitest_pass(_run_vitest("empty_id.test.ts"), "empty_id")

    def test_empty_author_after_trim_rejected(self):
        """L2: an author that is empty after trimming causes a throw."""
        _write_driver(
            "empty_author.test.ts",
            """
            expectThrow(() => parseComment({ id: '1', author: '   ', text: 'y' }));
            expectThrow(() => parseComment({ id: '1', author: '', text: 'y' }));
            """,
        )
        _assert_vitest_pass(_run_vitest("empty_author.test.ts"), "empty_author")

    def test_text_length_bounds(self):
        """L2: empty text (<1) and over-length text (>500) after trim are rejected; bounds accepted."""
        _write_driver(
            "text_bounds.test.ts",
            """
            // too short (empty after trim)
            expectThrow(() => parseComment({ id: '1', author: 'x', text: '' }));
            expectThrow(() => parseComment({ id: '1', author: 'x', text: '     ' }));

            // over length: 501 chars after trim -> throw
            const tooLong = 'a'.repeat(501);
            expectThrow(() => parseComment({ id: '1', author: 'x', text: tooLong }));

            // boundary 1 char accepted
            const lo = parseComment({ id: '1', author: 'x', text: 'a' }) as any;
            expect(lo.text).toBe('a');

            // boundary 500 chars accepted, output preserved
            const exactly500 = 'b'.repeat(500);
            const hi = parseComment({ id: '1', author: 'x', text: exactly500 }) as any;
            expect(hi.text).toBe(exactly500);
            expect(hi.text.length).toBe(500);
            """,
        )
        _assert_vitest_pass(_run_vitest("text_bounds.test.ts"), "text_bounds")

    def test_invalid_sibling_child_rejects_whole_parse(self):
        """L2: one valid child + one child missing `text` -> the whole parse throws."""
        _write_driver(
            "bad_child.test.ts",
            """
            expectThrow(() => parseComment({
              id: 'root',
              author: 'Root',
              text: 'top',
              replies: [
                { id: 'good', author: 'A', text: 'ok' },
                { id: 'bad', author: 'B' },   // missing text
              ],
            }));
            """,
        )
        _assert_vitest_pass(_run_vitest("bad_child.test.ts"), "bad_child")

    def test_deeply_nested_invalid_node_rejects(self):
        """L2: a 5-level tree with one invalid node at the deepest level throws."""
        _write_driver(
            "deep_invalid.test.ts",
            """
            // Build a valid 5-level chain, then corrupt the deepest node.
            const deepBad = {
              id: 'L1', author: 'a', text: 't',
              replies: [{
                id: 'L2', author: 'a', text: 't',
                replies: [{
                  id: 'L3', author: 'a', text: 't',
                  replies: [{
                    id: 'L4', author: 'a', text: 't',
                    replies: [{
                      id: 'L5', author: 'a', text: '',   // invalid: empty text at deepest
                    }],
                  }],
                }],
              }],
            };
            expectThrow(() => parseComment(deepBad));

            // The same chain with a valid deepest node parses fine.
            const deepOk = {
              id: 'L1', author: 'a', text: 't',
              replies: [{
                id: 'L2', author: 'a', text: 't',
                replies: [{
                  id: 'L3', author: 'a', text: 't',
                  replies: [{
                    id: 'L4', author: 'a', text: 't',
                    replies: [{ id: 'L5', author: 'a', text: 'deep' }],
                  }],
                }],
              }],
            };
            const out = parseComment(deepOk) as any;
            expect(out.replies[0].replies[0].replies[0].replies[0].text).toBe('deep');
            expect(out.replies[0].replies[0].replies[0].replies[0].replies).toEqual([]);
            """,
        )
        _assert_vitest_pass(_run_vitest("deep_invalid.test.ts"), "deep_invalid")

    def test_non_object_inputs_rejected(self):
        """L2: null, numbers, strings, arrays, undefined and booleans all throw."""
        _write_driver(
            "nonobject.test.ts",
            """
            for (const input of [null, 42, 'hello', [], undefined, true]) {
              expectThrow(() => parseComment(input as unknown));
            }
            // a leaf is still accepted (sanity)
            const ok = parseComment(LEAF) as any;
            expect(ok.id).toBe('1');
            """,
        )
        _assert_vitest_pass(_run_vitest("nonobject.test.ts"), "nonobject")

    def test_wrong_field_types_rejected(self):
        """L2: non-string id/author/text and non-array replies are rejected."""
        _write_driver(
            "types.test.ts",
            """
            expectThrow(() => parseComment({ id: 1, author: 'x', text: 'y' }));
            expectThrow(() => parseComment({ id: '1', author: 5, text: 'y' }));
            expectThrow(() => parseComment({ id: '1', author: 'x', text: 7 }));
            expectThrow(() => parseComment({ id: '1', author: 'x', text: 'y', replies: 'nope' }));
            expectThrow(() => parseComment({ id: '1', author: 'x', text: 'y', replies: [42] }));
            // missing required fields entirely
            expectThrow(() => parseComment({ author: 'x', text: 'y' }));
            expectThrow(() => parseComment({}));
            """,
        )
        _assert_vitest_pass(_run_vitest("types.test.ts"), "types")

    def test_agent_own_suite_passes(self):
        """L2: the agent's authored suite passes under the native acceptance command."""
        proc = subprocess.run(
            [NPX, "vitest", "run", "--no-coverage", "src/commentTree/commentTree.test.ts"],
            cwd=LIB_DIR,
            capture_output=True,
            text=True,
            timeout=VITEST_TIMEOUT,
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "agent's own commentTree.test.ts suite did not pass.\n"
            f"{combined[-4000:]}"
        )
